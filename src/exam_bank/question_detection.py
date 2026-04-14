from __future__ import annotations

import re
from pathlib import Path

from .config import AppConfig
from .models import BoundingBox, PageLayout, QuestionSpan, QuestionStart, TextBlock


QUESTION_START_RE = re.compile(
    r"^\s*(?P<number>[1-9]\d{0,2})(?P<label>(?:\s*\([a-zivxlcdm]+\))*)"
    r"(?=\s|[).,:;\-–—]|$)",
    re.IGNORECASE,
)
SUBPART_RE = re.compile(r"^\s*(?:\d+\s*)?(?P<label>\([a-z]\)(?:\([ivxlcdm]+\))*)", re.IGNORECASE)
MARK_RE = re.compile(r"\[(?P<marks>\d{1,2})\]")


def parse_question_start(text: str, config: AppConfig) -> tuple[str, str] | None:
    """Return top-level question number and visible label if text starts a question."""

    match = QUESTION_START_RE.match(text.strip())
    if not match:
        return None
    number = int(match.group("number"))
    if number > config.detection.max_question_number:
        return None
    label = f"{number}{match.group('label').replace(' ', '')}"
    return str(number), label


def detect_question_spans(layouts: list[PageLayout], source_pdf: str | Path, config: AppConfig) -> list[QuestionSpan]:
    starts = detect_question_starts(layouts, config)
    paper_name = _safe_paper_name(Path(source_pdf).stem)

    if not starts:
        return [_fallback_unknown_question(layouts, Path(source_pdf), paper_name, config)]

    spans: list[QuestionSpan] = []
    for index, start in enumerate(starts):
        next_start = starts[index + 1] if index + 1 < len(starts) else None
        if next_start is None:
            end_page = _last_content_page(layouts, start.page_number)
            end_y = _page_content_bottom(_layout_by_number(layouts, end_page), config)
        else:
            end_page = next_start.page_number
            end_y = next_start.y0

        page_numbers = list(range(start.page_number, end_page + 1))
        blocks = _blocks_within_span(layouts, start.page_number, start.y0, end_page, end_y, config)
        flags = _span_flags(blocks, layouts, page_numbers, config, start)
        if next_start and int(next_start.question_number) > int(start.question_number) + 1:
            flags.append("question_sequence_gap")
        flags.extend(_validate_span_blocks(start, blocks, layouts, config))

        full_label = _infer_full_label(start.question_number, blocks)
        spans.append(
            QuestionSpan(
                source_pdf=Path(source_pdf),
                paper_name=paper_name,
                question_number=start.question_number,
                start_page=start.page_number,
                start_y=start.y0,
                end_page=end_page,
                end_y=end_y,
                page_numbers=page_numbers,
                blocks=blocks,
                full_question_label=full_label,
                review_flags=flags,
                anchor=start,
            )
        )

    return spans


def detect_question_starts(layouts: list[PageLayout], config: AppConfig) -> list[QuestionStart]:
    raw_starts = [
        candidate
        for candidate in detect_question_anchor_candidates(layouts, config)
        if candidate.confidence >= config.detection.anchor_min_confidence
    ]

    starts: list[QuestionStart] = []
    seen_numbers: set[str] = set()
    last_number = 0
    for candidate in raw_starts:
        number = int(candidate.question_number)
        if candidate.question_number in seen_numbers:
            continue
        if not starts and number != 1:
            # The first real question in these papers should normally be 1.
            # If OCR/text extraction misses it, still accept later numbers so
            # the paper is not discarded.
            starts.append(candidate)
            seen_numbers.add(candidate.question_number)
            last_number = number
            continue
        if number > last_number:
            starts.append(candidate)
            seen_numbers.add(candidate.question_number)
            last_number = number

    return starts


def detect_question_anchor_candidates(layouts: list[PageLayout], config: AppConfig) -> list[QuestionStart]:
    """Find and score layout-positioned top-level question number anchors."""

    candidates: list[QuestionStart] = []
    global_index = 0
    for page in layouts:
        sorted_blocks = sorted(page.blocks, key=lambda item: (item.bbox.y0, item.bbox.x0))
        font_median = _median_font_size(sorted_blocks)
        previous_block: TextBlock | None = None
        for block in sorted_blocks:
            parsed = parse_question_start(block.first_line, config)
            if parsed and _anchor_block_can_be_question_start(block, page, config):
                number, label = parsed
                confidence, reasons = _score_anchor(block, previous_block, page, font_median, config)
                candidates.append(
                    QuestionStart(
                        question_number=number,
                        page_number=page.page_number,
                        y0=block.bbox.y0,
                        x0=block.bbox.x0,
                        label=label,
                        block_index=global_index,
                        bbox=block.bbox,
                        font_size=block.font_size,
                        confidence=confidence,
                        reasons=reasons,
                    )
                )
            if _is_question_content_block(block, page, config):
                previous_block = block
            global_index += 1

    return candidates


def extract_marks_from_text(text: str) -> int | None:
    """Extract the sum of bracketed Cambridge-style marks, e.g. [3] [4]."""

    marks = [int(match.group("marks")) for match in MARK_RE.finditer(text)]
    if not marks:
        return None
    return sum(marks)


def _fallback_unknown_question(
    layouts: list[PageLayout],
    source_pdf: Path,
    paper_name: str,
    config: AppConfig,
) -> QuestionSpan:
    page_numbers = [layout.page_number for layout in layouts]
    blocks = [block for layout in layouts for block in layout.blocks]
    end_page = page_numbers[-1] if page_numbers else 1
    end_y = _page_content_bottom(_layout_by_number(layouts, end_page), config) if layouts else 0
    return QuestionSpan(
        source_pdf=source_pdf,
        paper_name=paper_name,
        question_number="unknown",
        start_page=page_numbers[0] if page_numbers else 1,
        start_y=config.detection.crop_top_margin,
        end_page=end_page,
        end_y=end_y,
        page_numbers=page_numbers,
        blocks=blocks,
        full_question_label="unknown",
        review_flags=["no_question_boundaries_detected"],
    )


def _blocks_within_span(
    layouts: list[PageLayout],
    start_page: int,
    start_y: float,
    end_page: int,
    end_y: float,
    config: AppConfig,
) -> list[TextBlock]:
    selected: list[TextBlock] = []
    for page in layouts:
        if page.page_number < start_page or page.page_number > end_page:
            continue
        top = start_y if page.page_number == start_page else config.detection.crop_top_margin
        bottom = end_y if page.page_number == end_page else page.height - config.detection.crop_bottom_margin
        answer_rule_bands = _answer_rule_y_bands(page)
        for block in page.blocks:
            if block.bbox.y1 >= top and block.bbox.y0 < bottom:
                if _is_question_content_block(block, page, config, answer_rule_bands=answer_rule_bands):
                    selected.append(block)
    return sorted(selected, key=lambda block: (block.page_number, block.bbox.y0, block.bbox.x0))


def _span_flags(
    blocks: list[TextBlock],
    layouts: list[PageLayout],
    page_numbers: list[int],
    config: AppConfig,
    start: QuestionStart | None = None,
) -> list[str]:
    flags: list[str] = []
    text = extract_text_from_blocks(blocks)
    if len(text) < config.detection.min_question_chars:
        flags.append("short_question_text")
    if any(_layout_by_number(layouts, page).text_source == "ocr" for page in page_numbers):
        flags.append("ocr_question_text")
    warnings = [
        _layout_by_number(layouts, page).extraction_warning
        for page in page_numbers
        if _layout_by_number(layouts, page).extraction_warning
    ]
    flags.extend(sorted(set(warnings)))
    if start and start.confidence < 0.72:
        flags.append("question_start_uncertain")
    return flags


def extract_text_from_blocks(blocks: list[TextBlock]) -> str:
    """Extract local region text in coordinate order, never raw page-stream order."""

    return "\n".join(
        block.text.strip()
        for block in sorted(blocks, key=lambda item: (item.page_number, item.bbox.y0, item.bbox.x0))
        if block.text.strip()
    ).strip()


def _validate_span_blocks(
    start: QuestionStart,
    blocks: list[TextBlock],
    layouts: list[PageLayout],
    config: AppConfig,
) -> list[str]:
    flags: list[str] = []
    if not blocks:
        return ["short_question_text", "question_start_uncertain"]

    first = blocks[0]
    parsed_first = parse_question_start(first.first_line, config)
    if first.page_number == start.page_number and parsed_first and parsed_first[0] != start.question_number:
        flags.append("question_start_mismatch")
    if first.page_number == start.page_number and not parsed_first and first.bbox.y0 <= start.y0 + config.detection.anchor_y_tolerance:
        flags.append("question_start_uncertain")

    for block in blocks[1:]:
        parsed = parse_question_start(block.first_line, config)
        if parsed and parsed[0] != start.question_number:
            flags.append("possible_next_question_contamination")
        page = _layout_by_number(layouts, block.page_number)
        if _is_footer_or_header_block(block, page, config) or _is_boilerplate_text(block.text):
            flags.append("header_footer_contamination")

    answer_artifacts = _answer_artifact_count(layouts, start, blocks, config)
    text_len = len(extract_text_from_blocks(blocks))
    if answer_artifacts >= 5 and text_len < 250:
        flags.append("answer_space_heavy")
    return sorted(set(flags))


def _infer_full_label(question_number: str, blocks: list[TextBlock]) -> str:
    labels: list[str] = []
    for block in blocks:
        match = SUBPART_RE.match(block.first_line)
        if not match:
            continue
        label = match.group("label").lower()
        if label not in labels:
            labels.append(label)

    if not labels:
        return question_number
    if len(labels) == 1:
        return f"{question_number}{labels[0]}"
    return f"{question_number}{labels[0]}-{labels[-1]}"


def _layout_by_number(layouts: list[PageLayout], page_number: int) -> PageLayout:
    for layout in layouts:
        if layout.page_number == page_number:
            return layout
    raise ValueError(f"No layout for page {page_number}")


def _last_content_page(layouts: list[PageLayout], start_page: int) -> int:
    candidates = [
        layout.page_number
        for layout in layouts
        if layout.page_number >= start_page and (layout.blocks or layout.graphics)
    ]
    return max(candidates) if candidates else start_page


def _page_content_bottom(layout: PageLayout, config: AppConfig) -> float:
    boxes = [block.bbox for block in layout.blocks if _is_question_content_block(block, layout, config)] + [
        graphic for graphic in layout.graphics if not _is_answer_rule_like(graphic, layout)
    ]
    if not boxes:
        return layout.height - config.detection.crop_bottom_margin
    return min(layout.height - config.detection.crop_bottom_margin, max(box.y1 for box in boxes) + config.detection.crop_padding)


def _safe_paper_name(stem: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("_")
    return cleaned or "paper"


def _anchor_block_can_be_question_start(block: TextBlock, page: PageLayout, config: AppConfig) -> bool:
    if not _is_question_content_block(block, page, config):
        return False
    text = _clean_text_line(block.text)
    if re.match(r"^\s*\([a-zivxlcdm]+\)", text, re.IGNORECASE):
        return False
    if block.bbox.x0 > config.detection.question_start_max_x + config.detection.anchor_left_tolerance:
        return False
    return True


def _score_anchor(
    block: TextBlock,
    previous_block: TextBlock | None,
    page: PageLayout,
    font_median: float,
    config: AppConfig,
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    text = _clean_text_line(block.text)

    if block.bbox.x0 <= config.detection.question_start_max_x:
        score += 0.32
        reasons.append("left_aligned")
    elif block.bbox.x0 <= config.detection.question_start_max_x + config.detection.anchor_left_tolerance:
        score += 0.2
        reasons.append("near_left_anchor")

    if config.detection.min_question_start_y <= block.bbox.y0 <= page.height - config.detection.bottom_margin:
        score += 0.16
        reasons.append("body_band")

    if block.font_size and font_median and block.font_size >= font_median * config.detection.anchor_font_size_ratio:
        score += 0.14
        reasons.append("plausible_font_size")
    elif block.font_size is None:
        score += 0.07
        reasons.append("font_size_missing")

    if previous_block is None:
        score += 0.08
        reasons.append("first_body_block")
    else:
        gap = block.bbox.y0 - previous_block.bbox.y1
        if gap >= max(3.0, (block.font_size or font_median or 10) * 0.35):
            score += 0.1
            reasons.append("preceded_by_spacing")

    if re.match(r"^\s*\d+\s*$", text):
        score += 0.16
        reasons.append("standalone_number")
    elif re.match(r"^\s*\d+\s*(?:\([a-z]\))?\s+\S", text, re.IGNORECASE):
        score += 0.14
        reasons.append("number_then_prompt")
    elif re.match(r"^\s*\d+\s*\([a-z]\)", text, re.IGNORECASE):
        score += 0.12
        reasons.append("number_then_subpart")

    if block.is_bold:
        score += 0.04
        reasons.append("bold_anchor")

    return min(1.0, score), reasons


def _median_font_size(blocks: list[TextBlock]) -> float:
    sizes = sorted(block.font_size for block in blocks if block.font_size)
    if not sizes:
        return 0.0
    middle = len(sizes) // 2
    if len(sizes) % 2:
        return float(sizes[middle])
    return float((sizes[middle - 1] + sizes[middle]) / 2)


def _is_question_content_block(
    block: TextBlock,
    page: PageLayout,
    config: AppConfig,
    answer_rule_bands: list[float] | None = None,
) -> bool:
    text = " ".join(block.text.replace("\u00a0", " ").split())
    if not text:
        return False
    if _is_footer_or_header_block(block, page, config):
        return False

    # Remove page furniture that often appears inside continuation-page spans.
    if _is_boilerplate_text(text):
        return False
    if _is_answer_space_text(text):
        return False
    if answer_rule_bands and _is_in_answer_rule_band(block.bbox, answer_rule_bands):
        return False

    if text.isdigit() and (block.bbox.y0 < config.detection.crop_top_margin or block.bbox.y1 > page.height - config.detection.bottom_margin):
        return False

    return True


def _is_footer_or_header_block(block: TextBlock, page: PageLayout, config: AppConfig) -> bool:
    return block.bbox.y1 < config.detection.crop_top_margin or block.bbox.y0 > page.height - config.detection.bottom_margin


def _is_boilerplate_text(text: str) -> bool:
    text = _clean_text_line(text)
    boilerplate_patterns = [
        r"^©\s*UCLES\b",
        r"^UCLES\b",
        r"^9709[/_ -]",
        r"^\d{4}/\d{2}/[A-Z]/[A-Z]/\d{2}$",
        r"^Cambridge International",
        r"^This document consists of",
        r"^BLANK PAGE$",
        r"^Question Paper$",
        r"^Mark Scheme$",
        r"^Turn over$",
    ]
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in boilerplate_patterns)


def _is_answer_space_text(text: str) -> bool:
    if re.fullmatch(r"[._\-–—\s]{6,}", text):
        return True
    if re.fullmatch(r"(?:\.\s*){6,}", text):
        return True
    return bool(re.search(r"\bAnswer\b\s*[._\-–—]{6,}", text, re.IGNORECASE))


def _answer_artifact_count(
    layouts: list[PageLayout],
    start: QuestionStart,
    blocks: list[TextBlock],
    config: AppConfig,
) -> int:
    if not blocks:
        return 0
    by_page = {layout.page_number: layout for layout in layouts}
    count = 0
    for block in blocks:
        if _is_answer_space_text(block.text):
            count += 1
    for page_number in sorted({block.page_number for block in blocks}):
        page = by_page[page_number]
        ys = [block.bbox.y0 for block in blocks if block.page_number == page_number]
        ye = [block.bbox.y1 for block in blocks if block.page_number == page_number]
        if not ys or not ye:
            continue
        top = min(ys)
        bottom = max(ye)
        count += sum(
            1
            for graphic in page.graphics
            if top <= graphic.y0 <= bottom + config.detection.prompt_region_max_gap
            and _is_answer_rule_like(graphic, page)
        )
    return count


def _answer_rule_y_bands(layout: PageLayout) -> list[float]:
    rows: dict[int, list[BoundingBox]] = {}
    for graphic in layout.graphics:
        width = max(0.0, graphic.x1 - graphic.x0)
        height = max(0.0, graphic.y1 - graphic.y0)
        if height > 2.5 or width <= 1:
            continue
        y_key = round(((graphic.y0 + graphic.y1) / 2) / 2)
        rows.setdefault(y_key, []).append(graphic)

    bands: list[float] = []
    for y_key, boxes in rows.items():
        total_width = sum(box.x1 - box.x0 for box in boxes)
        if total_width >= layout.width * 0.25 or len(boxes) >= 5:
            bands.append(y_key * 2)
    return bands


def _is_answer_rule_like(box: BoundingBox, layout: PageLayout) -> bool:
    width = max(0.0, box.x1 - box.x0)
    height = max(0.0, box.y1 - box.y0)
    return height <= 2.5 and width >= layout.width * 0.28


def _is_in_answer_rule_band(box: BoundingBox, bands: list[float]) -> bool:
    if not bands:
        return False
    y_mid = (box.y0 + box.y1) / 2
    return any(abs(y_mid - band) <= 2.5 for band in bands)


def _clean_text_line(text: str) -> str:
    return " ".join(text.replace("\u00a0", " ").split())
