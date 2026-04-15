from __future__ import annotations

import csv
from dataclasses import dataclass, field
from io import BytesIO
import re
from pathlib import Path

from .config import AppConfig
from .models import BoundingBox, PageLayout, QuestionStart, TextBlock
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


@dataclass(frozen=True)
class MarkSchemeTable:
    page_number: int
    bbox: BoundingBox
    question_col_right: float
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
    layouts = extract_pdf_layout(mark_scheme_pdf, config)
    starts = _detect_mark_scheme_starts(layouts, config, expected_numbers)
    if not starts:
        return _fallback_regex_answers(layouts, expected_numbers)

    answers: dict[str, str] = {}
    for index, start in enumerate(starts):
        next_start = starts[index + 1] if index + 1 < len(starts) else None
        end_page = next_start.page_number if next_start else layouts[-1].page_number
        end_y = next_start.y0 if next_start else layouts[-1].height
        blocks = _blocks_between(layouts, start.page_number, start.y0, end_page, end_y)
        text = "\n".join(block.text for block in blocks).strip()
        if text:
            answers[start.question_number] = text
    return answers


def render_mark_scheme_images(
    mark_scheme_pdf: str | Path,
    config: AppConfig,
    expected_numbers: list[str] | None = None,
) -> dict[str, MarkSchemeImageResult]:
    """Crop rendered mark-scheme answer regions by top-level question number.

    This keeps mathematical notation exactly as it appears in the source PDF.
    Text extraction is used only to locate the answer boundaries; the exported
    artifact is a crop of the original rendered mark-scheme page.
    """

    if not expected_numbers:
        return {}

    try:
        import fitz
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("PyMuPDF and Pillow are required for mark-scheme image export.") from exc

    mark_scheme_pdf = Path(mark_scheme_pdf)
    layouts = extract_pdf_layout(mark_scheme_pdf, config)
    tables = _detect_mark_scheme_tables(layouts, config)
    anchors = _detect_table_question_anchors(layouts, tables, config, expected_numbers)
    starts = _anchors_to_question_starts(anchors)
    if not anchors:
        starts = _detect_mark_scheme_starts(layouts, config, expected_numbers)
    if not anchors and not starts:
        return {
            number: MarkSchemeImageResult(
                question_number=number,
                crop_confidence="low",
                mapping_method="fallback_nonstandard_table",
                table_detected=False,
                review_flags=["markscheme_image_missing", "markscheme_image_no_boundaries", "markscheme_answer_table_header_missing"],
            )
            for number in expected_numbers
        }

    output: dict[str, MarkSchemeImageResult] = {}
    zoom = config.detection.render_dpi / 72
    matrix = fitz.Matrix(zoom, zoom)

    with fitz.open(mark_scheme_pdf) as doc:
        rendered_pages = {}
        ordered_anchors = sorted(anchors, key=lambda item: (item.page_number, item.y0))
        ordered_starts = sorted(starts, key=lambda item: (item.page_number, item.y0))
        for number in expected_numbers:
            anchor_index = next((index for index, item in enumerate(ordered_anchors) if item.question_number == number), None)
            start_index = next((index for index, item in enumerate(ordered_starts) if item.question_number == number), None)
            anchor = ordered_anchors[anchor_index] if anchor_index is not None else None
            start = ordered_starts[start_index] if start_index is not None else None
            if anchor is not None:
                next_anchor = ordered_anchors[anchor_index + 1] if anchor_index is not None and anchor_index + 1 < len(ordered_anchors) else None
                regions, flags = _table_regions_for_anchor(layouts, tables, anchor, next_anchor, config)
                mapping_method = "table_by_question_number"
                table_detected = True
                nearby_anchors = _nearby_anchor_labels(ordered_anchors, anchor)
            elif start is not None:
                next_start = ordered_starts[start_index + 1] if start_index is not None and start_index + 1 < len(ordered_starts) else None
                regions, flags = _mark_scheme_regions_for_start(layouts, start, next_start, config)
                mapping_method = "fallback_nonstandard_table"
                table_detected = False
                nearby_anchors = [item.question_number for item in ordered_starts[max(0, start_index - 2) : start_index + 3]]
                flags.extend(["markscheme_table_detection_failed", "markscheme_answer_table_header_missing"])
            else:
                output[number] = MarkSchemeImageResult(
                    question_number=number,
                    crop_confidence="low",
                    mapping_method="fallback_nonstandard_table",
                    table_detected=bool(tables),
                    review_flags=["markscheme_image_missing", "markscheme_no_row_for_question"],
                    nearby_anchors=[item.question_number for item in ordered_anchors[:8]] or [item.question_number for item in ordered_starts[:8]],
                )
                continue

            if not regions:
                output[number] = MarkSchemeImageResult(
                    question_number=number,
                    markscheme_question_number=anchor.question_number if anchor else (start.question_number if start else ""),
                    crop_confidence="low",
                mapping_method=mapping_method,
                table_detected=table_detected,
                table_header_detected=anchor.table.header_detected if anchor and anchor.table else [],
                nearby_anchors=nearby_anchors,
                review_flags=sorted(set(flags + ["markscheme_image_missing"])),
                )
                continue

            crops = []
            debug_paths: list[str] = []
            for region in regions:
                page_number = region.page_number
                box = region.bbox
                if page_number not in rendered_pages:
                    page = doc[page_number - 1]
                    pix = page.get_pixmap(matrix=matrix, alpha=False)
                    rendered_pages[page_number] = Image.open(BytesIO(pix.tobytes("png"))).convert("RGB")
                    if config.debug.enabled and config.debug.save_rendered_pages:
                        debug_paths.append(_save_mark_scheme_debug_image(rendered_pages[page_number], mark_scheme_pdf, number, page_number, "rendered", config))
                crop_box = _pdf_box_to_pixel_box(box, zoom, rendered_pages[page_number].size)
                crops.append(rendered_pages[page_number].crop(crop_box))

            if not crops:
                output[number] = MarkSchemeImageResult(
                    question_number=number,
                    markscheme_question_number=anchor.question_number if anchor else (start.question_number if start else ""),
                    crop_confidence="low",
                mapping_method=mapping_method,
                table_detected=table_detected,
                table_header_detected=anchor.table.header_detected if anchor and anchor.table else [],
                nearby_anchors=nearby_anchors,
                review_flags=sorted(set(flags + ["markscheme_image_missing"])),
                )
                continue

            if config.debug.enabled:
                debug_paths.extend(_write_mark_scheme_debug_overlays(rendered_pages, mark_scheme_pdf, number, layouts, tables, ordered_anchors, regions, zoom, config))

            output_path = _mark_scheme_image_path(mark_scheme_pdf, number, config)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            _stitch_images(crops, config.detection.stitch_gap_px).save(output_path)
            confidence = _mark_scheme_crop_confidence(regions, layouts, flags)
            if mapping_method != "table_by_question_number" and confidence == "high":
                confidence = "medium"
            output[number] = MarkSchemeImageResult(
                question_number=number,
                image_path=output_path,
                page_numbers=[region.page_number for region in regions],
                markscheme_question_number=anchor.question_number if anchor else (start.question_number if start else ""),
                crop_confidence=confidence,
                mapping_method=mapping_method,
                table_detected=table_detected,
                table_header_detected=anchor.table.header_detected if anchor and anchor.table else [],
                detected_anchor_pages=[anchor.page_number] if anchor else ([start.page_number] if start else []),
                nearby_anchors=nearby_anchors,
                debug_paths=debug_paths,
                review_flags=sorted(set(flags)),
            )

    found = set(output)
    for number in expected_numbers:
        if number not in found:
            output[number] = MarkSchemeImageResult(
                question_number=number,
                crop_confidence="low",
                mapping_method="fallback_nonstandard_table",
                table_detected=bool(tables),
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


def _detect_mark_scheme_tables(layouts: list[PageLayout], config: AppConfig) -> dict[int, MarkSchemeTable]:
    tables: dict[int, MarkSchemeTable] = {}
    for layout in layouts:
        header_blocks = _mark_scheme_header_blocks(layout)
        header_detected = _header_terms(header_blocks)
        if header_detected != ["Question", "Answer", "Marks", "Guidance"]:
            continue

        header_box = _union_boxes([block.bbox for block in header_blocks])
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
        question_header = _best_header_block(header_blocks, "question")
        answer_header = _best_header_block(header_blocks, "answer")
        if question_header and answer_header and question_header is not answer_header:
            question_col_right = (question_header.bbox.x1 + answer_header.bbox.x0) / 2
        else:
            question_col_right = min(layout.width * 0.22, bbox.x0 + 110)
        tables[layout.page_number] = MarkSchemeTable(
            page_number=layout.page_number,
            bbox=bbox,
            question_col_right=question_col_right,
            header_bottom=header_box.y1,
            confidence="high",
            header_detected=header_detected,
        )
    return tables


def _mark_scheme_header_blocks(layout: PageLayout) -> list[TextBlock]:
    header_words = {"question", "answer", "marks", "mark", "guidance"}
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


def _best_header_block(blocks: list[TextBlock], word: str) -> TextBlock | None:
    return next((block for block in blocks if word in _clean_cell_text(block.text).split()), None)


def _header_terms(blocks: list[TextBlock]) -> list[str]:
    canonical = {
        "question": "Question",
        "answer": "Answer",
        "marks": "Marks",
        "mark": "Marks",
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
) -> list[MarkSchemeAnchor]:
    expected = set(expected_numbers or [])
    anchors: list[MarkSchemeAnchor] = []
    seen: set[tuple[str, int, int]] = set()
    for layout in layouts:
        table = tables.get(layout.page_number)
        if not table:
            continue
        q_col_right = table.question_col_right
        table_top = table.header_bottom
        table_bottom = table.bbox.y1
        for block in sorted(layout.blocks, key=lambda item: (item.bbox.y0, item.bbox.x0)):
            if block.bbox.y1 < table_top or block.bbox.y0 > table_bottom:
                continue
            if block.bbox.x0 > q_col_right:
                continue
            number = _parse_mark_scheme_question_cell(block.text, expected)
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
    return sorted(anchors, key=lambda item: (item.page_number, item.y0, item.x0))


def _parse_mark_scheme_question_cell(text: str, expected: set[str]) -> str | None:
    cleaned = _clean_cell_text(text)
    if not cleaned:
        return None
    candidates = re.findall(r"\d{1,2}", cleaned)
    if not candidates:
        return None
    if re.search(r"9709|page|mark|answer|guidance|scheme|paper", cleaned, re.IGNORECASE):
        return None
    if len(candidates) > 1 and cleaned not in set(candidates):
        return None
    number = candidates[0].lstrip("0") or "0"
    if expected and number not in expected:
        return None
    if not re.fullmatch(r"\d{1,2}(?:\s*\([a-zivx]+\))*", cleaned):
        return None
    return number


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
            flags.append("markscheme_table_continuation_inferred")
            table = MarkSchemeTable(
                page_number=layout.page_number,
                bbox=BoundingBox(config.detection.crop_left_margin, config.detection.crop_top_margin, layout.width - config.detection.crop_right_margin, layout.height - config.detection.bottom_margin),
                question_col_right=min(layout.width * 0.22, config.detection.question_start_max_x + 40),
                header_bottom=config.detection.crop_top_margin,
                confidence="low",
            )

        top = anchor.y0 if layout.page_number == anchor.page_number else table.header_bottom
        # CAIE mark schemes often show the question number once, then leave the
        # question-number cells blank on continuation rows. Those rows belong to
        # the current question until the next visible question-number anchor.
        bottom = next_anchor.y0 if next_anchor and layout.page_number == next_anchor.page_number else table.bbox.y1
        bottom = _tighten_table_bottom_from_content(layout, table, top, bottom, config)
        box = BoundingBox(
            table.bbox.x0,
            max(config.detection.crop_top_margin, top - config.detection.crop_padding),
            table.bbox.x1,
            min(layout.height - config.detection.bottom_margin, bottom + config.detection.crop_padding),
        )
        if box.y1 <= box.y0 + 4:
            flags.append("markscheme_image_uncertain")
            continue
        regions.append(MarkSchemeCropRegion(layout.page_number, box, table_detected=table.confidence != "low"))

    if len(regions) > 1:
        flags.append("markscheme_image_stitched")
    if anchor.table.confidence != "high":
        flags.append("markscheme_image_uncertain")
    return regions, flags


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


def _nearby_anchor_labels(anchors: list[MarkSchemeAnchor], anchor: MarkSchemeAnchor) -> list[str]:
    try:
        index = anchors.index(anchor)
    except ValueError:
        return [item.question_number for item in anchors[:8]]
    return [item.question_number for item in anchors[max(0, index - 2) : index + 3]]


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
    rendered_pages: dict[int, "Image.Image"],
    mark_scheme_pdf: Path,
    question_number: str,
    layouts: list[PageLayout],
    tables: dict[int, MarkSchemeTable],
    anchors: list[MarkSchemeAnchor],
    regions: list[MarkSchemeCropRegion],
    zoom: float,
    config: AppConfig,
) -> list[str]:
    from PIL import ImageDraw

    paths: list[str] = []
    for page_number, image in rendered_pages.items():
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
