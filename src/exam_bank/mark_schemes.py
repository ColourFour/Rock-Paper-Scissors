from __future__ import annotations

import csv
from dataclasses import dataclass, field
import json
import re
from pathlib import Path

from .config import AppConfig
from .document_metadata import companion_candidates, parse_filename_metadata
from .image_limits import cap_image_pixels, render_pdf_area
from .identifiers import normalize_question_id, parent_question_id
from .models import BoundingBox, PageLayout, QuestionStart, TextBlock
from .mupdf_tools import quiet_mupdf
from .pdf_extract import _visual_box_from_rect
from .pdf_extract import extract_pdf_layout
from .question_detection import parse_question_start


@dataclass(frozen=True)
class MarkSchemeImageResult:
    question_number: str
    image_path: Path | None = None
    page_numbers: list[int] = field(default_factory=list)
    markscheme_question_number: str = ""
    crop_confidence: str = "low"
    mapping_method: str = ""
    table_detected: bool = False
    table_header_detected: list[str] = field(default_factory=list)
    detected_anchor_pages: list[int] = field(default_factory=list)
    nearby_anchors: list[str] = field(default_factory=list)
    debug_paths: list[str] = field(default_factory=list)
    review_flags: list[str] = field(default_factory=list)
    table_header_ok: bool = False
    continuation_rows_included: bool = False
    question_subparts: list[str] = field(default_factory=list)
    markscheme_subparts: list[str] = field(default_factory=list)
    question_marks_total: int | None = None
    markscheme_marks_total: int | None = None
    mapping_status: str = "fail"
    failure_reason: str = ""


@dataclass(frozen=True)
class MarkSchemeTable:
    page_number: int
    bbox: BoundingBox
    question_col_right: float
    marks_col_left: float
    marks_col_right: float
    header_bottom: float
    confidence: str
    header_detected: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MarkSchemeAnchor:
    question_number: str
    page_number: int
    y0: float
    y1: float
    x0: float
    text: str
    table: MarkSchemeTable | None


@dataclass(frozen=True)
class MarkSchemeCropRegion:
    page_number: int
    bbox: BoundingBox
    table_detected: bool
    continuation_rows_included: bool = False


@dataclass(frozen=True)
class MarkSchemeWord:
    page_number: int
    text: str
    bbox: BoundingBox


@dataclass(frozen=True)
class HeaderGeometry:
    header_box: BoundingBox
    question_header: BoundingBox
    answer_header: BoundingBox
    marks_header: BoundingBox
    guidance_header: BoundingBox
    header_detected: list[str]


def find_mark_scheme(
    question_pdf: str | Path,
    mark_schemes_dir: str | Path,
    mappings_dir: str | Path | None = None,
) -> Path | None:
    question_pdf = Path(question_pdf)
    mark_schemes_dir = Path(mark_schemes_dir)

    override = _find_mapping_override(question_pdf, mark_schemes_dir, Path(mappings_dir) if mappings_dir else None)
    if override:
        return override

    metadata = parse_filename_metadata(question_pdf)
    if metadata.canonical_key:
        candidates = companion_candidates(metadata, mark_schemes_dir, "MS")
        if candidates:
            return candidates[0]

    for candidate_name in _auto_candidate_names(question_pdf.name):
        candidate = mark_schemes_dir / candidate_name
        if candidate.exists():
            return candidate

    normalized_qp = _normalize_pair_key(question_pdf.stem)
    scored: list[tuple[int, Path]] = []
    for candidate in mark_schemes_dir.glob("*.pdf"):
        score = _pair_score(normalized_qp, _normalize_pair_key(candidate.stem))
        if score > 0:
            scored.append((score, candidate))
    if scored:
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[0][1]
    return None


def extract_mark_scheme_answers(
    mark_scheme_pdf: str | Path,
    config: AppConfig,
    expected_numbers: list[str] | None = None,
) -> dict[str, str]:
    mark_scheme_pdf = Path(mark_scheme_pdf)
    layouts = extract_pdf_layout(mark_scheme_pdf, config)
    words = _extract_mark_scheme_words(mark_scheme_pdf)
    tables = _detect_mark_scheme_tables(layouts, config, words)
    anchors = _detect_table_question_anchors(layouts, tables, config, expected_numbers, words)
    if not anchors:
        return {}
    answers: dict[str, str] = {}
    ordered = sorted(anchors, key=lambda item: (item.page_number, item.y0))
    for index, anchor in enumerate(ordered):
        next_anchor = ordered[index + 1] if index + 1 < len(ordered) else None
        table = anchor.table
        if table is None:
            continue
        end_page = next_anchor.page_number if next_anchor else anchor.page_number
        end_y = next_anchor.y0 if next_anchor and next_anchor.page_number == anchor.page_number else table.bbox.y1
        blocks = _blocks_between(layouts, anchor.page_number, anchor.y0, end_page, end_y)
        text = "\n".join(block.text for block in blocks).strip()
        if text:
            answers[anchor.question_number] = text
            parent = parent_question_id(anchor.question_number)
            if parent != anchor.question_number:
                answers[parent] = "\n".join(item for item in [answers.get(parent, ""), text] if item).strip()
    return answers


def render_mark_scheme_images(
    mark_scheme_pdf: str | Path,
    config: AppConfig,
    expected_numbers: list[str] | None = None,
    question_marks: dict[str, int | None] | None = None,
    question_subparts: dict[str, list[str]] | None = None,
) -> dict[str, MarkSchemeImageResult]:
    """Crop rendered mark-scheme answer regions by top-level question number.

    This keeps mathematical notation exactly as it appears in the source PDF.
    Text extraction is used only to locate the answer boundaries; the exported
    artifact is a crop of the original rendered mark-scheme page.
    """

    if not expected_numbers:
        return {}
    question_marks = question_marks or {}
    question_subparts = question_subparts or {}

    try:
        import fitz
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("PyMuPDF and Pillow are required for mark-scheme image export.") from exc
    quiet_mupdf(fitz)

    mark_scheme_pdf = Path(mark_scheme_pdf)
    words = _extract_mark_scheme_words(mark_scheme_pdf)
    layouts = extract_pdf_layout(mark_scheme_pdf, config)
    tables = _detect_mark_scheme_tables(layouts, config, words)
    anchors = _detect_table_question_anchors(layouts, tables, config, expected_numbers, words)
    if not tables or not anchors:
        return {
            number: MarkSchemeImageResult(
                question_number=number,
                crop_confidence="low",
                mapping_method="table_row_block",
                table_detected=False,
                mapping_status="fail",
                failure_reason="invalid_table_header",
                review_flags=[
                    "markscheme_image_missing",
                    "markscheme_no_valid_answer_table",
                    "markscheme_answer_table_header_missing",
                ],
            )
            for number in expected_numbers
        }

    output: dict[str, MarkSchemeImageResult] = {}
    with fitz.open(mark_scheme_pdf) as doc:
        rendered_pages = {}
        ordered_anchors = sorted(anchors, key=lambda item: (item.page_number, item.y0))
        for number in expected_numbers:
            canonical_number = normalize_question_id(number)
            anchor_index = next(
                (
                    index
                    for index, item in enumerate(ordered_anchors)
                    if item.question_number == canonical_number
                    or (
                        parent_question_id(item.question_number) == canonical_number
                        and canonical_number == parent_question_id(canonical_number)
                    )
                ),
                None,
            )
            anchor = ordered_anchors[anchor_index] if anchor_index is not None else None
            if anchor is not None:
                if canonical_number == parent_question_id(canonical_number):
                    next_anchor = next(
                        (
                            item
                            for item in ordered_anchors[anchor_index + 1 :]
                            if parent_question_id(item.question_number) != canonical_number
                        ),
                        None,
                    )
                else:
                    next_anchor = ordered_anchors[anchor_index + 1] if anchor_index is not None and anchor_index + 1 < len(ordered_anchors) else None
                regions, flags = _table_regions_for_anchor(layouts, tables, anchor, next_anchor, config)
                if anchor.question_number != canonical_number:
                    flags.append("markscheme_parent_label_match")
                mapping_method = "table_row_block"
                table_detected = True
                nearby_anchors = _nearby_anchor_labels(ordered_anchors, anchor)
            else:
                output[number] = MarkSchemeImageResult(
                    question_number=number,
                    crop_confidence="low",
                    mapping_method="table_row_block",
                    table_detected=bool(tables),
                    question_subparts=question_subparts.get(canonical_number, []),
                    question_marks_total=question_marks.get(canonical_number),
                    mapping_status="fail",
                    failure_reason="partial_question_block",
                    review_flags=["markscheme_image_missing", "markscheme_no_row_for_question"],
                    nearby_anchors=[item.question_number for item in ordered_anchors[:8]],
                )
                continue

            question_subpart_values = question_subparts.get(canonical_number, [])
            question_marks_total = question_marks.get(canonical_number)
            markscheme_subpart_values = (
                _detected_subparts_for_question(ordered_anchors, anchor_index, canonical_number)
                if anchor_index is not None
                else []
            )
            markscheme_marks_total = _mark_total_for_question_block(layouts, anchor, next_anchor, tables, words)
            validation_flags, failure_reason = _validate_mark_scheme_mapping(
                canonical_number,
                question_subpart_values,
                markscheme_subpart_values,
                question_marks_total,
                markscheme_marks_total,
                anchor,
                next_anchor,
                regions,
                flags,
            )
            flags.extend(validation_flags)
            if failure_reason:
                output[number] = MarkSchemeImageResult(
                    question_number=number,
                    markscheme_question_number=anchor.question_number if anchor else "",
                    crop_confidence="low",
                    mapping_method=mapping_method,
                    table_detected=table_detected,
                    table_header_detected=anchor.table.header_detected if anchor and anchor.table else [],
                    nearby_anchors=nearby_anchors,
                    review_flags=sorted(set(flags + ["markscheme_image_missing"])),
                    table_header_ok=bool(anchor and anchor.table and _table_header_ok(anchor.table)),
                    continuation_rows_included=any(region.continuation_rows_included for region in regions),
                    question_subparts=question_subpart_values,
                    markscheme_subparts=markscheme_subpart_values,
                    question_marks_total=question_marks_total,
                    markscheme_marks_total=markscheme_marks_total,
                    mapping_status="fail",
                    failure_reason=failure_reason,
                )
                continue

            if not regions:
                output[number] = MarkSchemeImageResult(
                    question_number=number,
                    markscheme_question_number=anchor.question_number if anchor else "",
                    crop_confidence="low",
                    mapping_method=mapping_method,
                    table_detected=table_detected,
                    table_header_detected=anchor.table.header_detected if anchor and anchor.table else [],
                    nearby_anchors=nearby_anchors,
                    review_flags=sorted(set(flags + ["markscheme_image_missing"])),
                    table_header_ok=bool(anchor and anchor.table and _table_header_ok(anchor.table)),
                    question_subparts=question_subpart_values,
                    markscheme_subparts=markscheme_subpart_values,
                    question_marks_total=question_marks_total,
                    markscheme_marks_total=markscheme_marks_total,
                    mapping_status="fail",
                    failure_reason=failure_reason or "partial_question_block",
                )
                continue

            crops = []
            debug_paths: list[str] = []
            for region in regions:
                page_number = region.page_number
                box = region.bbox
                page = doc[page_number - 1]
                rect = fitz.Rect(box.x0, box.y0, box.x1, box.y1)
                crop, used_zoom = render_pdf_area(
                    page,
                    fitz,
                    dpi=config.detection.render_dpi,
                    source_file=mark_scheme_pdf,
                    page_number=page_number,
                    context=f"markscheme_crop:{number}",
                    clip=rect,
                )
                crops.append(crop)
                if used_zoom * 72 < config.detection.render_dpi * 0.8:
                    flags.append("markscheme_render_dpi_capped")

                if config.debug.enabled and page_number not in rendered_pages:
                    page_image, page_zoom = render_pdf_area(
                        page,
                        fitz,
                        dpi=config.detection.render_dpi,
                        source_file=mark_scheme_pdf,
                        page_number=page_number,
                        context=f"markscheme_debug_page:{number}",
                    )
                    rendered_pages[page_number] = (page_image, page_zoom)
                    if config.debug.save_rendered_pages:
                        debug_paths.append(_save_mark_scheme_debug_image(page_image, mark_scheme_pdf, number, page_number, "rendered", config))

            if not crops:
                output[number] = MarkSchemeImageResult(
                    question_number=number,
                    markscheme_question_number=anchor.question_number if anchor else "",
                    crop_confidence="low",
                    mapping_method=mapping_method,
                    table_detected=table_detected,
                    table_header_detected=anchor.table.header_detected if anchor and anchor.table else [],
                    nearby_anchors=nearby_anchors,
                    review_flags=sorted(set(flags + ["markscheme_image_missing"])),
                    table_header_ok=bool(anchor and anchor.table and _table_header_ok(anchor.table)),
                    question_subparts=question_subpart_values,
                    markscheme_subparts=markscheme_subpart_values,
                    question_marks_total=question_marks_total,
                    markscheme_marks_total=markscheme_marks_total,
                    mapping_status="fail",
                    failure_reason=failure_reason or "partial_question_block",
                )
                continue

            if config.debug.enabled:
                debug_paths.extend(_write_mark_scheme_debug_overlays(rendered_pages, mark_scheme_pdf, number, layouts, tables, ordered_anchors, regions, config))
                debug_paths.append(_write_mark_scheme_debug_metadata(mark_scheme_pdf, number, tables, ordered_anchors, regions, config))

            output_path = _mark_scheme_image_path(mark_scheme_pdf, number, config)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            stitched = cap_image_pixels(
                _stitch_images(crops, config.detection.stitch_gap_px),
                source_file=mark_scheme_pdf,
                context=f"markscheme_output:{number}",
            )
            stitched.save(output_path)
            confidence = _mark_scheme_crop_confidence(regions, layouts, flags)
            output[number] = MarkSchemeImageResult(
                question_number=number,
                image_path=output_path,
                page_numbers=[region.page_number for region in regions],
                markscheme_question_number=anchor.question_number if anchor else "",
                crop_confidence=confidence,
                mapping_method=mapping_method,
                table_detected=table_detected,
                table_header_detected=anchor.table.header_detected if anchor and anchor.table else [],
                detected_anchor_pages=[anchor.page_number] if anchor else [],
                nearby_anchors=nearby_anchors,
                debug_paths=debug_paths,
                review_flags=sorted(set(flags)),
                table_header_ok=bool(anchor and anchor.table and _table_header_ok(anchor.table)),
                continuation_rows_included=any(region.continuation_rows_included for region in regions),
                question_subparts=question_subpart_values,
                markscheme_subparts=markscheme_subpart_values,
                question_marks_total=question_marks_total,
                markscheme_marks_total=markscheme_marks_total,
                mapping_status="pass",
            )

    found = set(output)
    for number in expected_numbers:
        if number not in found:
            output[number] = MarkSchemeImageResult(
                question_number=number,
                crop_confidence="low",
                mapping_method="table_row_block",
                table_detected=bool(tables),
                question_subparts=question_subparts.get(number, []),
                question_marks_total=question_marks.get(number),
                mapping_status="fail",
                failure_reason="partial_question_block",
                review_flags=["markscheme_image_missing"],
            )
    return output


def _find_mapping_override(question_pdf: Path, mark_schemes_dir: Path, mappings_dir: Path | None) -> Path | None:
    if mappings_dir is None or not mappings_dir.exists():
        return None

    question_keys = {question_pdf.name, question_pdf.stem, str(question_pdf)}
    for csv_path in mappings_dir.glob("*.csv"):
        with csv_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                question_value = (row.get("question_pdf") or row.get("question") or "").strip()
                ms_value = (row.get("mark_scheme_pdf") or row.get("mark_scheme") or "").strip()
                if question_value in question_keys and ms_value:
                    return _resolve_mark_scheme_path(ms_value, mark_schemes_dir, mappings_dir)

    for yaml_path in list(mappings_dir.glob("*.yaml")) + list(mappings_dir.glob("*.yml")):
        try:
            import yaml
        except ImportError:
            continue
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        entries = raw.get("pairs", raw) if isinstance(raw, dict) else raw
        if isinstance(entries, dict):
            for question_value, ms_value in entries.items():
                if str(question_value) in question_keys:
                    return _resolve_mark_scheme_path(str(ms_value), mark_schemes_dir, mappings_dir)
        elif isinstance(entries, list):
            for row in entries:
                if not isinstance(row, dict):
                    continue
                question_value = str(row.get("question_pdf") or row.get("question") or "").strip()
                ms_value = str(row.get("mark_scheme_pdf") or row.get("mark_scheme") or "").strip()
                if question_value in question_keys and ms_value:
                    return _resolve_mark_scheme_path(ms_value, mark_schemes_dir, mappings_dir)
    return None


def _resolve_mark_scheme_path(value: str, mark_schemes_dir: Path, mappings_dir: Path) -> Path | None:
    path = Path(value)
    candidates = [path]
    if not path.is_absolute():
        candidates.extend([mark_schemes_dir / path, mappings_dir / path])
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _auto_candidate_names(question_name: str) -> list[str]:
    replacements = [
        ("_qp_", "_ms_"),
        ("-qp-", "-ms-"),
        (" qp ", " ms "),
        ("_question_", "_mark_scheme_"),
        ("question_paper", "mark_scheme"),
        ("Question Paper", "Mark Scheme"),
    ]
    candidates: list[str] = []
    for old, new in replacements:
        if old in question_name:
            candidates.append(question_name.replace(old, new))
    if "_qp" in question_name:
        candidates.append(question_name.replace("_qp", "_ms"))
    if " qp" in question_name:
        candidates.append(question_name.replace(" qp", " ms"))
    return list(dict.fromkeys(candidates))


def _normalize_pair_key(stem: str) -> str:
    lowered = stem.lower()
    lowered = re.sub(r"\b(qp|ms|question|paper|mark|scheme)\b", "", lowered)
    lowered = lowered.replace("_qp_", "_").replace("_ms_", "_")
    lowered = re.sub(r"[^a-z0-9]+", "", lowered)
    return lowered


def _pair_score(question_key: str, mark_scheme_key: str) -> int:
    if not question_key or not mark_scheme_key:
        return 0
    if question_key == mark_scheme_key:
        return 100
    shared = len(set(_tokenize(question_key)) & set(_tokenize(mark_scheme_key)))
    return shared


def _tokenize(value: str) -> list[str]:
    return re.findall(r"[a-z]+|\d+", value)


def _detect_mark_scheme_starts(
    layouts: list[PageLayout],
    config: AppConfig,
    expected_numbers: list[str] | None,
) -> list[QuestionStart]:
    expected = set(expected_numbers or [])
    starts: list[QuestionStart] = []
    seen: set[str] = set()
    index = 0
    for page in layouts:
        for block in sorted(page.blocks, key=lambda item: (item.bbox.y0, item.bbox.x0)):
            parsed = parse_question_start(block.first_line, config)
            if parsed:
                number, label = parsed
                if expected and number not in expected:
                    index += 1
                    continue
                if number not in seen and block.bbox.x0 <= max(config.detection.question_start_max_x, 180):
                    starts.append(
                        QuestionStart(
                            question_number=number,
                            page_number=page.page_number,
                            y0=block.bbox.y0,
                            x0=block.bbox.x0,
                            label=label,
                            block_index=index,
                        )
                    )
                    seen.add(number)
            index += 1
    return starts


def _extract_mark_scheme_words(mark_scheme_pdf: Path) -> dict[int, list[MarkSchemeWord]]:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required for mark-scheme word extraction. Install requirements.txt first.") from exc
    quiet_mupdf(fitz)

    words_by_page: dict[int, list[MarkSchemeWord]] = {}
    with fitz.open(mark_scheme_pdf) as doc:
        for page_index, page in enumerate(doc):
            page_number = page_index + 1
            words: list[MarkSchemeWord] = []
            for raw_word in page.get_text("words"):
                x0, y0, x1, y1, text, *_ = raw_word
                if str(text).strip():
                    bbox = _visual_box_from_rect(page, (x0, y0, x1, y1))
                    words.append(
                        MarkSchemeWord(
                            page_number=page_number,
                            text=str(text),
                            bbox=bbox,
                        )
                    )
            words_by_page[page_number] = words
    return words_by_page


def _detect_mark_scheme_tables(
    layouts: list[PageLayout],
    config: AppConfig,
    words_by_page: dict[int, list[MarkSchemeWord]] | None = None,
) -> dict[int, MarkSchemeTable]:
    tables: dict[int, MarkSchemeTable] = {}
    for layout in layouts:
        if layout.page_number < 6:
            continue
        header_geometry = _mark_scheme_header_geometry(words_by_page.get(layout.page_number, []) if words_by_page else [])
        header_blocks = _mark_scheme_header_blocks(layout) if header_geometry is None else []
        header_detected = header_geometry.header_detected if header_geometry else _header_terms(header_blocks)
        if header_detected != ["Question", "Answer", "Marks", "Guidance"]:
            continue

        header_box = header_geometry.header_box if header_geometry else _union_boxes([block.bbox for block in header_blocks])
        content_blocks = [
            block
            for block in layout.blocks
            if block.bbox.y1 >= header_box.y0 - 6
            and block.bbox.y0 <= layout.height - config.detection.bottom_margin
            and not _is_footer_or_header_box(block.bbox, layout, config)
            and not _is_mark_scheme_boilerplate(block.text)
        ]
        if not content_blocks:
            continue

        content_box = _union_boxes([block.bbox for block in content_blocks])
        graphic_box = _table_graphic_bounds(layout, content_box)
        bbox = _union_boxes([content_box, graphic_box]) if graphic_box else content_box
        bbox = BoundingBox(
            max(0, bbox.x0 - 4),
            max(config.detection.crop_top_margin, header_box.y0 - 4),
            min(layout.width, bbox.x1 + 4),
            min(layout.height - config.detection.bottom_margin, bbox.y1 + 4),
        )
        if header_geometry:
            question_col_right = min(
                (header_geometry.question_header.x1 + header_geometry.answer_header.x0) / 2,
                header_geometry.question_header.x1 + 24,
            )
            marks_col_left = max(
                header_geometry.answer_header.x1 + 20,
                header_geometry.marks_header.x0 - 55,
            )
            marks_col_right = min(
                (header_geometry.marks_header.x1 + header_geometry.guidance_header.x0) / 2,
                header_geometry.marks_header.x1 + 18,
            )
        else:
            question_header = _best_header_block(header_blocks, "question")
            answer_header = _best_header_block(header_blocks, "answer")
            marks_header = _best_header_block(header_blocks, "marks")
            guidance_header = _best_header_block(header_blocks, "guidance")
            if question_header and answer_header and question_header is not answer_header:
                question_col_right = min((question_header.bbox.x1 + answer_header.bbox.x0) / 2, question_header.bbox.x1 + 24)
            else:
                question_col_right = min(layout.width * 0.22, bbox.x0 + 110)
            if answer_header and marks_header:
                marks_col_left = max(answer_header.bbox.x1 + 20, marks_header.bbox.x0 - 55)
            else:
                marks_col_left = bbox.x0 + (bbox.x1 - bbox.x0) * 0.58
            if marks_header and guidance_header:
                marks_col_right = min((marks_header.bbox.x1 + guidance_header.bbox.x0) / 2, marks_header.bbox.x1 + 18)
            else:
                marks_col_right = bbox.x0 + (bbox.x1 - bbox.x0) * 0.72
        tables[layout.page_number] = MarkSchemeTable(
            page_number=layout.page_number,
            bbox=bbox,
            question_col_right=question_col_right,
            marks_col_left=marks_col_left,
            marks_col_right=marks_col_right,
            header_bottom=header_box.y1,
            confidence="high",
            header_detected=header_detected,
        )
    return tables


def _mark_scheme_header_blocks(layout: PageLayout) -> list[TextBlock]:
    header_words = {"question", "answer", "marks", "guidance"}
    blocks: list[TextBlock] = []
    for block in layout.blocks:
        cleaned = _clean_cell_text(block.text)
        if cleaned in header_words or any(word in cleaned.split() for word in header_words):
            blocks.append(block)
    if not blocks:
        return []

    row_groups: dict[int, list[TextBlock]] = {}
    for block in blocks:
        row_key = round(block.bbox.y0 / 8)
        row_groups.setdefault(row_key, []).append(block)
    best = max(row_groups.values(), key=lambda group: len(_header_terms(group)))
    if _header_terms(best) != ["Question", "Answer", "Marks", "Guidance"]:
        return []
    return sorted(best, key=lambda block: block.bbox.x0)


def _mark_scheme_header_geometry(words: list[MarkSchemeWord]) -> HeaderGeometry | None:
    if not words:
        return None
    rows = _group_words_by_row(words, tolerance=4.0)
    for row in rows:
        by_word: dict[str, MarkSchemeWord] = {}
        for word in row:
            cleaned = _clean_cell_text(word.text)
            if cleaned in {"question", "answer", "marks", "guidance"} and cleaned not in by_word:
                by_word[cleaned] = word
        if set(by_word) != {"question", "answer", "marks", "guidance"}:
            continue
        ordered = [by_word["question"], by_word["answer"], by_word["marks"], by_word["guidance"]]
        if ordered != sorted(ordered, key=lambda item: item.bbox.x0):
            continue
        return HeaderGeometry(
            header_box=_union_boxes([word.bbox for word in ordered]),
            question_header=by_word["question"].bbox,
            answer_header=by_word["answer"].bbox,
            marks_header=by_word["marks"].bbox,
            guidance_header=by_word["guidance"].bbox,
            header_detected=["Question", "Answer", "Marks", "Guidance"],
        )
    return None


def _group_words_by_row(words: list[MarkSchemeWord], tolerance: float = 5.0) -> list[list[MarkSchemeWord]]:
    rows: list[list[MarkSchemeWord]] = []
    for word in sorted(words, key=lambda item: (_box_center_y(item.bbox), item.bbox.x0)):
        center = _box_center_y(word.bbox)
        best_index: int | None = None
        best_distance: float | None = None
        for index, row in enumerate(rows):
            row_center = sum(_box_center_y(item.bbox) for item in row) / len(row)
            distance = abs(center - row_center)
            if distance <= tolerance and (best_distance is None or distance < best_distance):
                best_index = index
                best_distance = distance
        if best_index is None:
            rows.append([word])
        else:
            rows[best_index].append(word)
    return [sorted(row, key=lambda item: item.bbox.x0) for row in rows]


def _box_center_x(box: BoundingBox) -> float:
    return (box.x0 + box.x1) / 2


def _box_center_y(box: BoundingBox) -> float:
    return (box.y0 + box.y1) / 2


def _best_header_block(blocks: list[TextBlock], word: str) -> TextBlock | None:
    return next((block for block in blocks if word in _clean_cell_text(block.text).split()), None)


def _header_terms(blocks: list[TextBlock]) -> list[str]:
    canonical = {
        "question": "Question",
        "answer": "Answer",
        "marks": "Marks",
        "guidance": "Guidance",
    }
    found: set[str] = set()
    for block in blocks:
        words = set(_clean_cell_text(block.text).split())
        found.update(label for word, label in canonical.items() if word in words)
    ordered = ["Question", "Answer", "Marks", "Guidance"]
    return [label for label in ordered if label in found]


def _table_graphic_bounds(layout: PageLayout, content_box: BoundingBox) -> BoundingBox | None:
    graphics = [
        box
        for box in layout.graphics
        if box.y1 >= content_box.y0 - 20
        and box.y0 <= content_box.y1 + 20
        and box.x1 >= content_box.x0 - 40
        and box.x0 <= content_box.x1 + 40
    ]
    if not graphics:
        return None
    return _union_boxes(graphics)


def _detect_table_question_anchors(
    layouts: list[PageLayout],
    tables: dict[int, MarkSchemeTable],
    config: AppConfig,
    expected_numbers: list[str] | None,
    words_by_page: dict[int, list[MarkSchemeWord]] | None = None,
) -> list[MarkSchemeAnchor]:
    expected = {normalize_question_id(number) for number in (expected_numbers or [])}
    expected_parents = {parent_question_id(number) for number in expected}
    anchors: list[MarkSchemeAnchor] = []
    seen: set[tuple[str, int, int]] = set()
    for layout in layouts:
        table = tables.get(layout.page_number)
        if not table:
            continue
        word_anchors = _detect_table_question_anchors_from_words(
            words_by_page.get(layout.page_number, []) if words_by_page else [],
            table,
            expected,
            expected_parents,
        )
        if word_anchors:
            for anchor in word_anchors:
                key = (anchor.question_number, anchor.page_number, round(anchor.y0))
                if key not in seen:
                    seen.add(key)
                    anchors.append(anchor)
            continue
        q_col_right = table.question_col_right
        table_top = table.header_bottom
        table_bottom = table.bbox.y1
        for block in sorted(layout.blocks, key=lambda item: (item.bbox.y0, item.bbox.x0)):
            if block.bbox.y1 < table_top or block.bbox.y0 > table_bottom:
                continue
            if block.bbox.x0 > q_col_right:
                continue
            number = _parse_mark_scheme_question_cell(block.text, expected, expected_parents)
            if not number:
                continue
            key = (number, layout.page_number, round(block.bbox.y0))
            if key in seen:
                continue
            seen.add(key)
            anchors.append(
                MarkSchemeAnchor(
                    question_number=number,
                    page_number=layout.page_number,
                    y0=block.bbox.y0,
                    y1=block.bbox.y1,
                    x0=block.bbox.x0,
                    text=block.text.strip(),
                    table=table,
                )
            )
    ordered = sorted(anchors, key=lambda item: (item.page_number, item.y0, item.x0))
    return _filter_out_of_sequence_mark_scheme_anchors(ordered)


def _filter_out_of_sequence_mark_scheme_anchors(anchors: list[MarkSchemeAnchor]) -> list[MarkSchemeAnchor]:
    accepted: list[MarkSchemeAnchor] = []
    highest_parent = 0
    for index, anchor in enumerate(anchors):
        parent = _anchor_parent_number(anchor)
        if parent is None:
            continue
        if not accepted:
            accepted.append(anchor)
            highest_parent = parent
            continue
        if parent < highest_parent:
            continue
        if parent > highest_parent + 1 and _future_parent_exists(anchors, index, highest_parent + 1):
            continue
        accepted.append(anchor)
        highest_parent = max(highest_parent, parent)
    return accepted


def _anchor_parent_number(anchor: MarkSchemeAnchor) -> int | None:
    match = re.match(r"\d{1,2}", parent_question_id(anchor.question_number))
    return int(match.group(0)) if match else None


def _future_parent_exists(anchors: list[MarkSchemeAnchor], after_index: int, parent_number: int) -> bool:
    return any(_anchor_parent_number(anchor) == parent_number for anchor in anchors[after_index + 1 :])


def _detect_table_question_anchors_from_words(
    words: list[MarkSchemeWord],
    table: MarkSchemeTable,
    expected: set[str],
    expected_parents: set[str],
) -> list[MarkSchemeAnchor]:
    anchors: list[MarkSchemeAnchor] = []
    if not words:
        return anchors
    rows = _group_words_by_row(
        [
            word
            for word in words
            if word.bbox.y1 >= table.header_bottom
            and word.bbox.y0 <= table.bbox.y1
            and table.bbox.x0 - 4 <= word.bbox.x0 <= table.bbox.x1 + 4
        ],
        tolerance=5.0,
    )
    for row in rows:
        label_zone_right = min(table.question_col_right, table.bbox.x0 + 70)
        question_words = [
            word
            for word in row
            if _box_center_x(word.bbox) <= table.question_col_right
            and word.bbox.x0 <= label_zone_right
        ]
        if not question_words:
            continue
        text = _leading_question_label_text(question_words)
        number = _parse_mark_scheme_question_cell(text, expected, expected_parents)
        if not number:
            continue
        bbox = _union_boxes([word.bbox for word in question_words])
        anchors.append(
            MarkSchemeAnchor(
                question_number=number,
                page_number=table.page_number,
                y0=bbox.y0,
                y1=bbox.y1,
                x0=bbox.x0,
                text=text,
                table=table,
            )
        )
    return anchors


def _leading_question_label_text(words: list[MarkSchemeWord]) -> str:
    if not words:
        return ""
    ordered = sorted(words, key=lambda item: item.bbox.x0)
    candidates = [" ".join(word.text for word in ordered[:count]) for count in range(1, min(3, len(ordered)) + 1)]
    for candidate in candidates:
        if _is_plausible_mark_scheme_label(candidate):
            return _clean_question_label_candidate(candidate)
    return _clean_question_label_candidate(ordered[0].text)


def _clean_question_label_candidate(text: str) -> str:
    cleaned = _clean_cell_text(text)
    cleaned = cleaned.replace("^{", "").replace("_{", "").replace("}", "")
    cleaned = re.sub(r"[^0-9a-z()]+", "", cleaned)
    return cleaned


def _parse_mark_scheme_question_cell(text: str, expected: set[str], expected_parents: set[str] | None = None) -> str | None:
    cleaned = _clean_cell_text(text)
    if not cleaned:
        return None
    if re.search(r"9709|page|mark|answer|guidance|scheme|paper", cleaned, re.IGNORECASE):
        return None
    if not _is_plausible_mark_scheme_label(cleaned):
        return None
    number = normalize_question_id(_clean_question_label_candidate(cleaned))
    if expected and number not in expected and parent_question_id(number) not in expected and number not in (expected_parents or set()):
        return None
    return number


def _is_plausible_mark_scheme_label(text: str) -> bool:
    cleaned = _clean_cell_text(text)
    if not cleaned or cleaned.startswith("("):
        return False
    label = _clean_question_label_candidate(cleaned)
    return bool(re.fullmatch(r"\d{1,2}(?:[a-h]|\([a-h]\))?(?:\((?:i{1,3}|iv|v|vi{0,3}|ix|x)\))?", label, re.IGNORECASE))


def _anchors_to_question_starts(anchors: list[MarkSchemeAnchor]) -> list[QuestionStart]:
    return [
        QuestionStart(
            question_number=anchor.question_number,
            page_number=anchor.page_number,
            y0=anchor.y0,
            x0=anchor.x0,
            label=anchor.text,
            block_index=index,
        )
        for index, anchor in enumerate(anchors)
    ]


def _table_regions_for_anchor(
    layouts: list[PageLayout],
    tables: dict[int, MarkSchemeTable],
    anchor: MarkSchemeAnchor,
    next_anchor: MarkSchemeAnchor | None,
    config: AppConfig,
) -> tuple[list[MarkSchemeCropRegion], list[str]]:
    flags: list[str] = []
    if not anchor.table:
        flags.append("markscheme_table_detection_failed")
        return [], flags

    end_page = next_anchor.page_number if next_anchor else layouts[-1].page_number
    regions: list[MarkSchemeCropRegion] = []
    for layout in layouts:
        if not anchor.page_number <= layout.page_number <= end_page:
            continue
        table = tables.get(layout.page_number)
        if not table:
            flags.append("partial_question_block")
            flags.append("invalid_table_header")
            continue

        if layout.page_number == anchor.page_number:
            # Each exported mark-scheme image should look like a manual crop of
            # the original answer table, so include the header row above the
            # target question row on the first page.
            top = table.bbox.y0
        elif table.confidence == "high":
            # On continuation pages, include the header only when the original
            # PDF page contains the answer-table header.
            top = table.bbox.y0
        else:
            top = table.header_bottom
        # CAIE mark schemes often show the question number once, then leave the
        # question-number cells blank on continuation rows. Those rows belong to
        # the current question until the next visible question-number anchor.
        bottom = next_anchor.y0 if next_anchor and layout.page_number == next_anchor.page_number else table.bbox.y1
        if (
            next_anchor
            and layout.page_number == next_anchor.page_number
            and layout.page_number != anchor.page_number
            and bottom <= table.header_bottom + 20
        ):
            continue
        bottom = _tighten_table_bottom_from_content(layout, table, top, bottom, config)
        box = BoundingBox(
            table.bbox.x0,
            max(config.detection.crop_top_margin, top),
            table.bbox.x1,
            min(layout.height - config.detection.bottom_margin, bottom + config.detection.crop_padding),
        )
        line_box = _line_based_table_crop(layout, table, box, next_anchor, config)
        if line_box:
            box = line_box
        if box.y1 <= box.y0 + 4:
            flags.append("markscheme_image_uncertain")
            continue
        continuation_rows_included = _has_continuation_rows(layout, table, anchor, next_anchor, box)
        regions.append(
            MarkSchemeCropRegion(
                layout.page_number,
                box,
                table_detected=table.confidence != "low",
                continuation_rows_included=continuation_rows_included,
            )
        )

    if len(regions) > 1:
        flags.append("markscheme_image_stitched")
    if anchor.table.confidence != "high":
        flags.append("markscheme_image_uncertain")
    return regions, flags


def _has_continuation_rows(
    layout: PageLayout,
    table: MarkSchemeTable,
    anchor: MarkSchemeAnchor,
    next_anchor: MarkSchemeAnchor | None,
    crop_box: BoundingBox,
) -> bool:
    bottom = next_anchor.y0 if next_anchor and next_anchor.page_number == layout.page_number else crop_box.y1
    for block in layout.blocks:
        if block.bbox.y0 <= anchor.y1 + 3 or block.bbox.y0 >= bottom:
            continue
        if block.bbox.x0 <= table.question_col_right:
            continue
        if crop_box.x0 - 5 <= block.bbox.x0 <= crop_box.x1 + 5:
            return True
    return False


def _tighten_table_bottom_from_content(
    layout: PageLayout,
    table: MarkSchemeTable,
    top: float,
    proposed_bottom: float,
    config: AppConfig,
) -> float:
    blocks = [
        block
        for block in layout.blocks
        if block.bbox.y1 >= top
        and block.bbox.y0 < proposed_bottom
        and table.bbox.x0 - 5 <= block.bbox.x0 <= table.bbox.x1 + 5
        and not _is_footer_or_header_box(block.bbox, layout, config)
        and not _is_mark_scheme_boilerplate(block.text)
    ]
    graphics = [
        graphic
        for graphic in layout.graphics
        if graphic.y1 >= top
        and graphic.y0 < proposed_bottom
        and table.bbox.x0 - 5 <= graphic.x0 <= table.bbox.x1 + 5
    ]
    boxes = [block.bbox for block in blocks] + graphics
    if not boxes:
        return proposed_bottom
    return min(proposed_bottom, max(box.y1 for box in boxes))


def _line_based_table_crop(
    layout: PageLayout,
    table: MarkSchemeTable,
    fallback_box: BoundingBox,
    next_anchor: MarkSchemeAnchor | None,
    config: AppConfig,
) -> BoundingBox | None:
    horizontal = _table_horizontal_rules(layout, table)
    vertical = _table_vertical_rules(layout, table)
    if len(horizontal) < 2:
        return None

    left = min(vertical) if len(vertical) >= 2 else table.bbox.x0
    right = max(vertical) if len(vertical) >= 2 else table.bbox.x1
    top = min((y for y in horizontal if y <= table.header_bottom + 2), default=table.bbox.y0)

    if next_anchor and next_anchor.page_number == layout.page_number:
        bottom_candidates = [y for y in horizontal if fallback_box.y0 < y < next_anchor.y0 - 1]
        bottom = max(bottom_candidates, default=fallback_box.y1)
    else:
        bottom_candidates = [y for y in horizontal if y >= fallback_box.y1 - config.detection.crop_padding - 2]
        bottom = min(bottom_candidates, default=max(horizontal))

    box = BoundingBox(
        max(config.detection.crop_left_margin, left),
        max(config.detection.crop_top_margin, top),
        min(layout.width - config.detection.crop_right_margin, right),
        min(layout.height - config.detection.bottom_margin, bottom),
    )
    if box.y1 <= box.y0 + 4 or box.x1 <= box.x0 + 4:
        return None
    return box


def _table_horizontal_rules(layout: PageLayout, table: MarkSchemeTable) -> list[float]:
    ys: list[float] = []
    min_width = max(80, (table.bbox.x1 - table.bbox.x0) * 0.45)
    for graphic in layout.graphics:
        width = graphic.x1 - graphic.x0
        height = graphic.y1 - graphic.y0
        if height > 4 or width < min_width:
            continue
        if graphic.x1 < table.bbox.x0 - 8 or graphic.x0 > table.bbox.x1 + 8:
            continue
        if graphic.y0 < table.bbox.y0 - 8 or graphic.y1 > table.bbox.y1 + 8:
            continue
        ys.extend([graphic.y0, graphic.y1])
    return _dedupe_positions(ys)


def _table_vertical_rules(layout: PageLayout, table: MarkSchemeTable) -> list[float]:
    xs: list[float] = []
    min_height = max(60, (table.bbox.y1 - table.bbox.y0) * 0.35)
    for graphic in layout.graphics:
        width = graphic.x1 - graphic.x0
        height = graphic.y1 - graphic.y0
        if width > 4 or height < min_height:
            continue
        if graphic.x0 < table.bbox.x0 - 8 or graphic.x1 > table.bbox.x1 + 8:
            continue
        if graphic.y1 < table.bbox.y0 - 8 or graphic.y0 > table.bbox.y1 + 8:
            continue
        xs.extend([graphic.x0, graphic.x1])
    return _dedupe_positions(xs)


def _dedupe_positions(values: list[float], tolerance: float = 2.0) -> list[float]:
    if not values:
        return []
    ordered = sorted(values)
    deduped = [ordered[0]]
    for value in ordered[1:]:
        if abs(value - deduped[-1]) > tolerance:
            deduped.append(value)
    return deduped


def _nearby_anchor_labels(anchors: list[MarkSchemeAnchor], anchor: MarkSchemeAnchor) -> list[str]:
    try:
        index = anchors.index(anchor)
    except ValueError:
        return [item.question_number for item in anchors[:8]]
    return [item.question_number for item in anchors[max(0, index - 2) : index + 3]]


def _table_header_ok(table: MarkSchemeTable | None) -> bool:
    return bool(table and table.header_detected == ["Question", "Answer", "Marks", "Guidance"])


def _detected_subparts_for_question(anchors: list[MarkSchemeAnchor], anchor_index: int, parent: str) -> list[str]:
    subparts: list[str] = []
    for item in anchors[anchor_index:]:
        if parent_question_id(item.question_number) != parent:
            break
        match = re.search(r"\(([a-h])\)", item.question_number)
        if match and match.group(1) not in subparts:
            subparts.append(match.group(1))
    return subparts


def _mark_total_for_question_block(
    layouts: list[PageLayout],
    anchor: MarkSchemeAnchor,
    next_anchor: MarkSchemeAnchor | None,
    tables: dict[int, MarkSchemeTable],
    words_by_page: dict[int, list[MarkSchemeWord]] | None = None,
) -> int | None:
    if words_by_page:
        criteria_total = 0
        standalone_totals: list[int] = []
        found = False
        for layout in layouts:
            if layout.page_number < anchor.page_number:
                continue
            if next_anchor and layout.page_number > next_anchor.page_number:
                continue
            table = tables.get(layout.page_number)
            if not table:
                continue
            top = anchor.y0 if layout.page_number == anchor.page_number else table.header_bottom
            bottom = next_anchor.y0 if next_anchor and layout.page_number == next_anchor.page_number else table.bbox.y1
            if (
                next_anchor
                and layout.page_number == next_anchor.page_number
                and layout.page_number != anchor.page_number
                and bottom <= table.header_bottom + 20
            ):
                continue
            rows = _group_words_by_row(
                [
                    word
                    for word in words_by_page.get(layout.page_number, [])
                    if word.bbox.y1 >= top
                    and word.bbox.y0 < bottom
                    and table.bbox.x0 - 4 <= word.bbox.x0 <= table.bbox.x1 + 4
                ],
                tolerance=5.0,
            )
            for row in rows:
                full_text = " ".join(word.text for word in row)
                if re.search(r"\balternative\s+method\b", full_text, re.IGNORECASE):
                    continue
                marks_cell = " ".join(
                    word.text
                    for word in row
                    if table.marks_col_left <= _box_center_x(word.bbox) <= table.marks_col_right
                )
                marks = _marks_from_marks_cell(marks_cell)
                if marks:
                    if _is_standalone_total_row(row, table, marks_cell):
                        standalone_totals.append(sum(marks))
                    else:
                        criteria_total += sum(marks)
                    found = True
        if not found:
            return None
        return sum(standalone_totals) if standalone_totals else criteria_total

    total = 0
    found = False
    for layout in layouts:
        if layout.page_number < anchor.page_number:
            continue
        if next_anchor and layout.page_number > next_anchor.page_number:
            continue
        table = tables.get(layout.page_number)
        if not table:
            continue
        top = anchor.y0 if layout.page_number == anchor.page_number else table.header_bottom
        bottom = next_anchor.y0 if next_anchor and layout.page_number == next_anchor.page_number else table.bbox.y1
        for block in layout.blocks:
            if block.bbox.y1 < top or block.bbox.y0 >= bottom:
                continue
            center_x = (block.bbox.x0 + block.bbox.x1) / 2
            if table.marks_col_left <= center_x <= table.marks_col_right:
                marks = _marks_from_marks_cell(block.text)
                if marks:
                    total += sum(marks)
                    found = True
    return total if found else None


def _is_standalone_total_row(row: list[MarkSchemeWord], table: MarkSchemeTable, marks_cell: str) -> bool:
    if not re.fullmatch(r"\s*\d{1,2}\s*", marks_cell):
        return False
    non_marks_words = [
        word
        for word in row
        if not (table.marks_col_left <= _box_center_x(word.bbox) <= table.marks_col_right)
    ]
    return not " ".join(word.text for word in non_marks_words).strip()


def _marks_from_marks_cell(text: str) -> list[int]:
    cleaned = " ".join(text.replace("\u00a0", " ").split())
    if re.search(r"marks|guidance|answer|question", cleaned, re.IGNORECASE):
        return []
    compact = re.sub(r"\s+", "", cleaned)
    rubric_match = re.fullmatch(r"[MBACE]?\d{1,2}(?:,\d{1,2})+(?:,0)?", compact, re.IGNORECASE)
    if rubric_match:
        values = [int(value) for value in re.findall(r"\d{1,2}", compact) if 0 < int(value) <= 15]
        return [max(values)] if values else []
    values: list[int] = []
    for match in re.finditer(r"(?<!\d)(?:[MBACE]\s*)?(\d{1,2})(?!\d)", cleaned, re.IGNORECASE):
        value = int(match.group(1))
        if 0 < value <= 15:
            values.append(value)
    return values


def _validate_mark_scheme_mapping(
    canonical_number: str,
    question_subparts: list[str],
    markscheme_subparts: list[str],
    question_marks_total: int | None,
    markscheme_marks_total: int | None,
    anchor: MarkSchemeAnchor | None,
    next_anchor: MarkSchemeAnchor | None,
    regions: list[MarkSchemeCropRegion],
    flags: list[str],
) -> tuple[list[str], str]:
    validation_flags: list[str] = []
    if not anchor or not _table_header_ok(anchor.table):
        validation_flags.append("invalid_table_header")
        return validation_flags, "invalid_table_header"
    if "invalid_table_header" in flags:
        validation_flags.append("invalid_table_header")
        return validation_flags, "invalid_table_header"
    if not regions:
        validation_flags.append("partial_question_block")
        return validation_flags, "partial_question_block"
    if next_anchor and parent_question_id(next_anchor.question_number) == canonical_number:
        validation_flags.append("partial_question_block")
        return validation_flags, "partial_question_block"
    missing = [part for part in question_subparts if part not in markscheme_subparts]
    if missing:
        validation_flags.append("missing_subparts")
        return validation_flags, "missing_subparts"
    if question_marks_total is None or markscheme_marks_total is None or question_marks_total != markscheme_marks_total:
        validation_flags.append("marks_total_mismatch")
        return validation_flags, "marks_total_mismatch"
    if _block_contains_adjacent_question(canonical_number, regions, anchor, next_anchor):
        validation_flags.append("adjacent_question_block_selected")
        return validation_flags, "adjacent_question_block_selected"
    return validation_flags, ""


def _block_contains_adjacent_question(
    canonical_number: str,
    regions: list[MarkSchemeCropRegion],
    anchor: MarkSchemeAnchor,
    next_anchor: MarkSchemeAnchor | None,
) -> bool:
    if next_anchor is None:
        return False
    for region in regions:
        if region.page_number != next_anchor.page_number:
            continue
        if region.bbox.y1 > next_anchor.y0 + 2 and parent_question_id(next_anchor.question_number) != canonical_number:
            return True
    return False


def _blocks_between(
    layouts: list[PageLayout],
    start_page: int,
    start_y: float,
    end_page: int,
    end_y: float,
) -> list[TextBlock]:
    blocks: list[TextBlock] = []
    for page in layouts:
        if not start_page <= page.page_number <= end_page:
            continue
        top = start_y if page.page_number == start_page else 0
        bottom = end_y if page.page_number == end_page else page.height
        for block in page.blocks:
            if block.bbox.y1 >= top and block.bbox.y0 < bottom:
                blocks.append(block)
    return sorted(blocks, key=lambda block: (block.page_number, block.bbox.y0, block.bbox.x0))


def _mark_scheme_regions_for_start(
    layouts: list[PageLayout],
    start: QuestionStart,
    next_start: QuestionStart | None,
    config: AppConfig,
) -> tuple[list[MarkSchemeCropRegion], list[str]]:
    flags: list[str] = []
    end_page = next_start.page_number if next_start else layouts[-1].page_number
    end_y = next_start.y0 if next_start else layouts[-1].height - config.detection.bottom_margin
    regions: list[MarkSchemeCropRegion] = []

    for layout in layouts:
        if not start.page_number <= layout.page_number <= end_page:
            continue
        top = start.y0 if layout.page_number == start.page_number else config.detection.crop_top_margin
        bottom = end_y if layout.page_number == end_page else layout.height - config.detection.bottom_margin
        top = max(config.detection.crop_top_margin, top)
        bottom = min(layout.height - config.detection.bottom_margin, bottom)
        if bottom <= top:
            continue

        text_blocks = [
            block
            for block in layout.blocks
            if block.bbox.y1 >= top
            and block.bbox.y0 < bottom
            and not _is_footer_or_header_box(block.bbox, layout, config)
            and not _is_mark_scheme_boilerplate(block.text)
        ]
        graphics = [
            graphic
            for graphic in layout.graphics
            if graphic.y1 >= top
            and graphic.y0 < bottom
            and not _is_footer_or_header_box(graphic, layout, config)
        ]
        boxes = [block.bbox for block in text_blocks] + graphics
        if not boxes:
            continue

        crop_box = _union_boxes(boxes).padded(config.detection.crop_padding, layout.width, layout.height)
        crop_box = BoundingBox(
            max(config.detection.crop_left_margin, crop_box.x0),
            max(config.detection.crop_top_margin, crop_box.y0),
            min(layout.width - config.detection.crop_right_margin, crop_box.x1),
            min(layout.height - config.detection.bottom_margin, crop_box.y1),
        )
        if crop_box.y1 <= crop_box.y0 or crop_box.x1 <= crop_box.x0:
            flags.append("markscheme_image_uncertain")
            continue
        if crop_box.y1 - crop_box.y0 > layout.height * 0.75:
            flags.append("markscheme_image_uncertain")
        regions.append(MarkSchemeCropRegion(layout.page_number, crop_box, table_detected=False))

    if len(regions) > 1:
        flags.append("markscheme_image_stitched")
    return regions, flags


def _mark_scheme_crop_confidence(
    regions: list[MarkSchemeCropRegion],
    layouts: list[PageLayout],
    flags: list[str],
) -> str:
    if not regions:
        return "low"
    if any(flag in flags for flag in {"markscheme_image_missing", "markscheme_image_no_boundaries"}):
        return "low"
    for region in regions:
        layout = next((layout for layout in layouts if layout.page_number == region.page_number), None)
        if layout and region.bbox.y1 - region.bbox.y0 > layout.height * 0.75:
            return "medium"
    if "markscheme_image_uncertain" in flags:
        return "medium"
    return "high"


def _mark_scheme_image_path(mark_scheme_pdf: Path, question_number: str, config: AppConfig) -> Path:
    paper_name = _safe_basename(mark_scheme_pdf.stem)
    if question_number.isdigit():
        qid = f"q{int(question_number):02d}"
    else:
        qid = f"q{_safe_basename(question_number)}"
    return config.output.images_dir / f"{paper_name}_ms_{qid}.png"


def _pdf_box_to_pixel_box(box: BoundingBox, zoom: float, image_size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = image_size
    left = max(0, min(width - 1, int(box.x0 * zoom)))
    top = max(0, min(height - 1, int(box.y0 * zoom)))
    right = max(left + 1, min(width, int(box.x1 * zoom)))
    bottom = max(top + 1, min(height, int(box.y1 * zoom)))
    return (left, top, right, bottom)


def _stitch_images(images: list["Image.Image"], gap_px: int) -> "Image.Image":
    from PIL import Image

    width = max(image.width for image in images)
    height = sum(image.height for image in images) + gap_px * max(0, len(images) - 1)
    stitched = Image.new("RGB", (width, height), "white")
    y = 0
    for image in images:
        stitched.paste(image, (0, y))
        y += image.height + gap_px
    return stitched


def _union_boxes(boxes: list[BoundingBox]) -> BoundingBox:
    return BoundingBox(
        min(box.x0 for box in boxes),
        min(box.y0 for box in boxes),
        max(box.x1 for box in boxes),
        max(box.y1 for box in boxes),
    )


def _is_footer_or_header_box(box: BoundingBox, layout: PageLayout, config: AppConfig) -> bool:
    return box.y1 < config.detection.crop_top_margin or box.y0 > layout.height - config.detection.bottom_margin


def _is_mark_scheme_boilerplate(text: str) -> bool:
    cleaned = " ".join(text.split())
    patterns = [
        r"^©\s*UCLES\b",
        r"^UCLES\b",
        r"^Cambridge International",
        r"^This document consists of",
        r"^BLANK PAGE$",
        r"^Mark Scheme$",
        r"^Question Paper$",
        r"^9709[/_ -]",
        r"^Page\s+\d+",
    ]
    return any(re.search(pattern, cleaned, re.IGNORECASE) for pattern in patterns)


def _clean_cell_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u00a0", " ")).strip().lower()


def _write_mark_scheme_debug_overlays(
    rendered_pages: dict[int, tuple["Image.Image", float]],
    mark_scheme_pdf: Path,
    question_number: str,
    layouts: list[PageLayout],
    tables: dict[int, MarkSchemeTable],
    anchors: list[MarkSchemeAnchor],
    regions: list[MarkSchemeCropRegion],
    config: AppConfig,
) -> list[str]:
    from PIL import ImageDraw

    paths: list[str] = []
    for page_number, (image, zoom) in rendered_pages.items():
        if not any(region.page_number == page_number for region in regions):
            continue
        page_image = image.copy()
        draw = ImageDraw.Draw(page_image)
        table = tables.get(page_number)
        if table:
            draw.rectangle(_pdf_box_to_pixel_box(table.bbox, zoom, page_image.size), outline="cyan", width=4)
            x = int(table.question_col_right * zoom)
            draw.line((x, 0, x, page_image.height), fill="orange", width=3)
        for anchor in [item for item in anchors if item.page_number == page_number]:
            y0 = int(anchor.y0 * zoom)
            y1 = int(anchor.y1 * zoom)
            draw.rectangle((0, y0, page_image.width, y1), outline="yellow", width=2)
        for region in [item for item in regions if item.page_number == page_number]:
            draw.rectangle(_pdf_box_to_pixel_box(region.bbox, zoom, page_image.size), outline="magenta", width=5)
        paths.append(_save_mark_scheme_debug_image(page_image, mark_scheme_pdf, question_number, page_number, "table_crop", config))
    return paths


def _write_mark_scheme_debug_metadata(
    mark_scheme_pdf: Path,
    question_number: str,
    tables: dict[int, MarkSchemeTable],
    anchors: list[MarkSchemeAnchor],
    regions: list[MarkSchemeCropRegion],
    config: AppConfig,
) -> str:
    config.output.debug_dir.mkdir(parents=True, exist_ok=True)
    paper_name = _safe_basename(mark_scheme_pdf.stem)
    qid = f"q{int(question_number):02d}" if question_number.isdigit() else f"q{_safe_basename(question_number)}"
    path = config.output.debug_dir / f"{paper_name}_ms_{qid}_crop_metadata.json"
    payload = {
        "question_number": question_number,
        "tables": [
            {
                "page_number": table.page_number,
                "bbox": _box_payload(table.bbox),
                "header_detected": table.header_detected,
                "header_bottom": table.header_bottom,
                "question_col_right": table.question_col_right,
                "confidence": table.confidence,
            }
            for table in tables.values()
        ],
        "question_number_anchors": [
            {
                "question_number": anchor.question_number,
                "page_number": anchor.page_number,
                "y0": anchor.y0,
                "y1": anchor.y1,
                "x0": anchor.x0,
                "text": anchor.text,
                "in_answer_table": bool(anchor.table),
            }
            for anchor in anchors
        ],
        "selected_row_range": [
            {
                "page_number": region.page_number,
                "crop_box": _box_payload(region.bbox),
                "table_detected": region.table_detected,
            }
            for region in regions
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return _display_path(path)


def _box_payload(box: BoundingBox) -> dict[str, float]:
    return {"x0": box.x0, "y0": box.y0, "x1": box.x1, "y1": box.y1}


def _save_mark_scheme_debug_image(
    image: "Image.Image",
    mark_scheme_pdf: Path,
    question_number: str,
    page_number: int,
    kind: str,
    config: AppConfig,
) -> str:
    config.output.debug_dir.mkdir(parents=True, exist_ok=True)
    paper_name = _safe_basename(mark_scheme_pdf.stem)
    qid = f"q{int(question_number):02d}" if question_number.isdigit() else f"q{_safe_basename(question_number)}"
    path = config.output.debug_dir / f"{paper_name}_ms_{qid}_p{page_number:02d}_{kind}.png"
    image.save(path)
    return _display_path(path)


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def _safe_basename(stem: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in stem).strip("_") or "paper"


def _fallback_regex_answers(layouts: list[PageLayout], expected_numbers: list[str] | None) -> dict[str, str]:
    if not expected_numbers:
        return {}
    full_text = "\n".join(layout.text for layout in layouts)
    answers: dict[str, str] = {}
    for position, number in enumerate(expected_numbers):
        next_number = expected_numbers[position + 1] if position + 1 < len(expected_numbers) else None
        pattern = rf"(?ms)^\s*{re.escape(number)}\b(?P<body>.*?)(?=^\s*{re.escape(next_number)}\b|\Z)" if next_number else rf"(?ms)^\s*{re.escape(number)}\b(?P<body>.*)\Z"
        match = re.search(pattern, full_text)
        if match:
            answers[number] = match.group(0).strip()
    return answers
