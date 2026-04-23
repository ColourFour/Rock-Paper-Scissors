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
SUBPART_RE = re.compile(
    r"^\s*(?:\d+\s*)?(?P<label>\((?:viii|vii|vi|iv|ix|iii|ii|i|v|x|[a-z])\)(?:\([ivxlcdm]+\))*)",
    re.IGNORECASE,
)
MARK_RE = re.compile(r"\[(?P<marks>\d{1,2})\]")
TERMINAL_MARK_RE = re.compile(r"\[(?P<marks>\d{1,2})\]\s*$")
RECOVERABLE_QUESTION_VALIDATION_FLAGS = {
    "question_subparts_incomplete",
    "missing_terminal_mark_total",
    "likely_truncated_question_crop",
    "weak_question_anchor",
}
BOILERPLATE_PATTERNS = [
    (r"^Additional Page\b", "additional_page"),
    (r"If you use the following lined page", "lined_page_instruction"),
    (r"write the question number", "lined_page_instruction"),
    (r"^©\s*UCLES\b", "copyright_footer"),
    (r"^UCLES\b", "copyright_footer"),
    (r"^9709[/_ -]", "paper_code_footer"),
    (r"^\d{4}/\d{2}/[A-Z]/[A-Z]/\d{2}$", "paper_code_footer"),
    (r"^Cambridge International", "publisher_footer"),
    (r"DO NOT WRITE IN THIS MARGIN", "margin_furniture"),
    (r"^This document consists of", "page_furniture"),
    (r"^BLANK PAGE$", "blank_page"),
    (r"^Question Paper$", "page_furniture"),
    (r"^Mark Scheme$", "page_furniture"),
    (r"^Turn over$", "footer"),
]


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
    max_question_number = _max_question_number_for_source(source_pdf, config)
    starts = detect_question_starts(layouts, config, source_pdf=source_pdf)
    paper_name = _safe_paper_name(Path(source_pdf).stem)
    format_profile = _paper_format_profile(source_pdf)

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
        blocks, boundary_flags = _blocks_within_span(
            layouts,
            start.page_number,
            start.y0,
            end_page,
            end_y,
            config,
            max_question_number,
            format_profile=format_profile,
        )
        flags = _span_flags(blocks, layouts, page_numbers, config, start)
        flags.extend(boundary_flags)
        if next_start and int(next_start.question_number) > int(start.question_number) + 1:
            flags.append("question_sequence_gap")
        if next_start and next_start.page_number == start.page_number:
            flags.append("same_page_secondary_anchor_detected")
            flags.append("same_page_split_performed")
        flags.extend(_validate_span_blocks(start, blocks, layouts, config))
        flags.extend(_subpart_sequence_flags(blocks))

        blocks, recovery_attempted, recovery_result = _recover_incomplete_span_blocks(
            start=start,
            blocks=blocks,
            layouts=layouts,
            start_page=start.page_number,
            start_y=start.y0,
            end_page=end_page,
            end_y=end_y,
            config=config,
            format_profile=format_profile,
        )
        if recovery_attempted:
            flags.append("recovery_attempted")
            if recovery_result == "improved":
                flags.append("recovery_improved_structure")
            elif recovery_result == "no_change":
                flags.append("recovery_no_change")

        validation_flags, structure_detected = _question_validation_flags(
            start=start,
            blocks=blocks,
            layouts=layouts,
            config=config,
            format_profile=format_profile,
            review_flags=flags,
        )
        flags.extend(validation_flags)
        if structure_detected.get("impossible_subpart_sequence_detected"):
            flags.append("impossible_subpart_sequence_detected")

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
                review_flags=sorted(set(flags)),
                anchor=start,
                validation_status=_question_validation_status(validation_flags, flags),
                validation_flags=validation_flags,
                recovery_attempted=recovery_attempted,
                recovery_result=recovery_result,
                structure_detected=structure_detected,
                question_total_detected=structure_detected.get("question_total_detected"),
                format_profile=format_profile,
            )
        )

    return spans


def detect_question_starts(layouts: list[PageLayout], config: AppConfig, source_pdf: str | Path | None = None) -> list[QuestionStart]:
    max_question_number = _max_question_number_for_source(source_pdf, config)
    raw_starts = [
        candidate
        for candidate in detect_question_anchor_candidates(layouts, config)
        if candidate.confidence >= config.detection.anchor_min_confidence
        and int(candidate.question_number) <= max_question_number
    ]
    first_question_one_index = next((index for index, candidate in enumerate(raw_starts) if candidate.question_number == "1"), None)
    if first_question_one_index is not None:
        raw_starts = raw_starts[first_question_one_index:]

    starts: list[QuestionStart] = []
    seen_numbers: set[str] = set()
    last_number = 0
    for candidate_index, candidate in enumerate(raw_starts):
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
            if number > last_number + 1 and _future_candidate_exists(raw_starts, candidate_index, str(last_number + 1)):
                continue
            starts.append(candidate)
            seen_numbers.add(candidate.question_number)
            last_number = number

    return starts


def _future_candidate_exists(candidates: list[QuestionStart], after_index: int, question_number: str) -> bool:
    return any(candidate.question_number == question_number for candidate in candidates[after_index + 1 :])


def detect_question_anchor_candidates(layouts: list[PageLayout], config: AppConfig) -> list[QuestionStart]:
    """Find and score layout-positioned top-level question number anchors."""

    candidates: list[QuestionStart] = []
    global_index = 0
    for page in layouts:
        if _is_cover_instruction_page(page):
            continue
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


def extract_question_total_from_text(text: str) -> int | None:
    """Prefer the terminal total when present, otherwise fall back to summed marks."""

    normalized = _strip_control_chars(text).replace("\u00a0", " ")
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    terminal_mark_total = None
    for line in reversed(lines[-3:]):
        match = TERMINAL_MARK_RE.search(line)
        if match:
            terminal_mark_total = int(match.group("marks"))
            break
    mark_values = [int(match.group("marks")) for match in MARK_RE.finditer(normalized)]
    subparts = _question_subparts_from_text_for_validation(normalized)
    return _detected_question_total(mark_values, terminal_mark_total, subparts)


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
        validation_status="fail",
        validation_flags=["weak_question_anchor"],
        recovery_attempted=False,
        recovery_result="not_attempted",
        structure_detected={"question_total_detected": None, "subparts": [], "format_profile": "legacy"},
        question_total_detected=None,
        format_profile="legacy",
    )


def _blocks_within_span(
    layouts: list[PageLayout],
    start_page: int,
    start_y: float,
    end_page: int,
    end_y: float,
    config: AppConfig,
    max_question_number: int | None = None,
    format_profile: str = "legacy",
) -> tuple[list[TextBlock], list[str]]:
    selected: list[TextBlock] = []
    flags: list[str] = []
    current_question_has_subparts = False
    page_flags: list[str] = []
    for page in layouts:
        if page.page_number < start_page or page.page_number > end_page:
            continue
        top = start_y if page.page_number == start_page else 0.0
        bottom = end_y if page.page_number == end_page else page.height - config.detection.crop_bottom_margin
        effective_bottom, boundary_flags = _effective_question_bottom(page, top, bottom, config)
        bottom = effective_bottom
        flags.extend(boundary_flags)
        answer_rule_bands = _answer_rule_y_bands(page)
        pending_rescues: list[TextBlock] = []
        page_selected: list[TextBlock] = []
        for block in sorted(page.blocks, key=lambda item: (item.bbox.y0, item.bbox.x0)):
            top_tolerance = 4.0 if page.page_number == start_page else 0.0
            if block.bbox.y0 < top - top_tolerance or block.bbox.y0 >= bottom:
                continue
            parsed = parse_question_start(block.first_line, config)
            if parsed and max_question_number is not None and int(parsed[0]) > max_question_number:
                flags.append("impossible_question_number_anchor_excluded")
                continue
            if _is_question_content_block(block, page, config, answer_rule_bands=answer_rule_bands):
                page_selected.append(block)
                current_question_has_subparts = current_question_has_subparts or _block_has_subpart_label(block)
                if current_question_has_subparts and pending_rescues:
                    page_selected.extend(_flush_pending_rescues(pending_rescues, page_selected))
                    pending_rescues = []
                continue
            rescued = _rescued_continuation_block(block, page, config, answer_rule_bands=answer_rule_bands)
            if rescued is not None:
                if current_question_has_subparts:
                    page_selected.extend(_flush_pending_rescues([rescued], page_selected))
                else:
                    pending_rescues.append(rescued)
        if current_question_has_subparts and pending_rescues:
            page_selected.extend(_flush_pending_rescues(pending_rescues, page_selected))
        if format_profile == "caie_2024_2025" and page.page_number > start_page:
            page_selected, stop_flags = _trim_foreign_top_of_page_continuations(
                page_selected,
                selected,
                page,
                config,
            )
            page_flags.extend(stop_flags)
        page_selected, suspicious_flags = _filter_suspicious_rescued_continuations(
            page_selected,
            page,
            bottom,
            config,
            is_start_page=page.page_number == start_page,
        )
        selected.extend(page_selected)
        page_flags.extend(suspicious_flags)
    flags.extend(page_flags)
    return sorted(selected, key=lambda block: (block.page_number, block.bbox.y0, block.bbox.x0)), sorted(set(flags))


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
        _clean_text_line(block.text)
        for block in sorted(blocks, key=lambda item: (item.page_number, item.bbox.y0, item.bbox.x0))
        if _clean_text_line(block.text)
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
    labels = _ordered_subpart_labels(blocks)

    if not labels:
        return question_number
    if len(labels) == 1:
        return f"{question_number}({labels[0]})"
    if _has_subpart_sequence_gap(labels):
        return f"{question_number}" + ",".join(f"({label})" for label in labels)
    return f"{question_number}({labels[0]})-({labels[-1]})"


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


def _max_question_number_for_source(source_pdf: str | Path | None, config: AppConfig) -> int:
    if source_pdf is None:
        return config.detection.max_question_number
    stem = Path(source_pdf).stem
    matches = re.findall(r"(?<!\d)([1-6][1-9])(?!\d)", stem)
    if not matches:
        return config.detection.max_question_number
    component = matches[-1]
    paper_digit = component[0]
    paper_maxima = {
        "1": 14,
        "2": 8,
        "3": 12,
        "4": 8,
        "5": 8,
        "6": 8,
    }
    return min(config.detection.max_question_number, paper_maxima.get(paper_digit, config.detection.max_question_number))


def _anchor_block_can_be_question_start(block: TextBlock, page: PageLayout, config: AppConfig) -> bool:
    if not _is_question_content_block(block, page, config):
        return False
    text = _clean_text_line(block.text)
    if re.match(r"^\s*\([a-zivxlcdm]+\)", text, re.IGNORECASE):
        return False
    if block.bbox.x0 > config.detection.question_start_max_x + config.detection.anchor_left_tolerance:
        return False
    return True


def _is_cover_instruction_page(page: PageLayout) -> bool:
    text = "\n".join(_clean_text_line(block.text) for block in page.blocks)
    lowered = text.lower()
    return (
        "instructions" in lowered
        and "information" in lowered
        and ("you will need" in lowered or "answer all questions" in lowered)
    )


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
    if _is_margin_furniture_text(block, page, config):
        return False
    if _is_control_artifact_text(text):
        return False
    if answer_rule_bands and _is_in_answer_rule_band(block.bbox, answer_rule_bands):
        return False

    if text.isdigit() and (block.bbox.y0 < config.detection.crop_top_margin or block.bbox.y1 > page.height - config.detection.bottom_margin):
        return False
    if _is_centered_page_number_block(block, page, config):
        return False

    return True


def _is_centered_page_number_block(block: TextBlock, page: PageLayout, config: AppConfig) -> bool:
    text = _clean_text_line(block.text)
    if not text.isdigit():
        return False
    if block.bbox.y0 > config.detection.min_question_start_y:
        return False
    center_x = (block.bbox.x0 + block.bbox.x1) / 2
    return page.width * 0.35 <= center_x <= page.width * 0.65


def _is_footer_or_header_block(block: TextBlock, page: PageLayout, config: AppConfig) -> bool:
    return block.bbox.y1 < config.detection.crop_top_margin or block.bbox.y0 > page.height - config.detection.bottom_margin


def _is_boilerplate_text(text: str) -> bool:
    return _boilerplate_reason(text) is not None


def _boilerplate_reason(text: str) -> str | None:
    text = _clean_text_line(text)
    for pattern, reason in BOILERPLATE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return reason
    return None


def _is_answer_space_text(text: str) -> bool:
    if re.fullmatch(r"[._\-–—\s]{6,}", text):
        return True
    if re.fullmatch(r"(?:\.\s*){6,}", text):
        return True
    return bool(re.search(r"\bAnswer\b\s*[._\-–—]{6,}", text, re.IGNORECASE))


def _is_margin_furniture_text(block: TextBlock, page: PageLayout, config: AppConfig) -> bool:
    text = _clean_text_line(block.text)
    if re.search(r"DO NOT WRITE IN THIS MARGIN", text, re.IGNORECASE):
        return True
    narrow_edge = (block.bbox.x1 - block.bbox.x0) <= 70 and (
        block.bbox.x0 <= config.detection.crop_left_margin or block.bbox.x1 >= page.width - config.detection.crop_right_margin
    )
    tall = (block.bbox.y1 - block.bbox.y0) >= 80
    return narrow_edge and tall


def _is_control_artifact_text(text: str) -> bool:
    control_count = sum(1 for char in text if ord(char) < 32 and char not in "\n\t\r")
    if control_count == 0:
        return False
    cleaned = _strip_control_chars(text).strip()
    visible_count = sum(1 for char in cleaned if not char.isspace())
    if visible_count <= 3:
        return True
    return control_count >= max(4, visible_count)


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


def _effective_question_bottom(
    layout: PageLayout,
    top: float,
    bottom: float,
    config: AppConfig,
) -> tuple[float, list[str]]:
    candidates: list[tuple[float, str]] = []
    answer_rule_bands = _answer_rule_y_bands(layout)
    for block in sorted(layout.blocks, key=lambda item: item.bbox.y0):
        if block.bbox.y0 <= top + 2 or block.bbox.y0 >= bottom:
            continue
        reason = _boilerplate_reason(block.text)
        if reason:
            if block.bbox.y0 <= max(top + 20, config.detection.crop_top_margin + 8):
                continue
            if _rescued_continuation_block(block, layout, config, answer_rule_bands=answer_rule_bands) is not None:
                continue
            candidates.append((block.bbox.y0, f"excluded_boilerplate_{reason}"))

    answer_start = _lined_answer_region_start(layout, top, bottom, config)
    if answer_start is not None:
        candidates.append((answer_start, "answer_line_space_excluded"))

    if not candidates:
        return bottom, []
    y, reason = min(candidates, key=lambda item: item[0])
    return max(top + config.detection.min_crop_height, min(bottom, y - config.detection.crop_padding)), [reason]


def _lined_answer_region_start(
    layout: PageLayout,
    top: float,
    bottom: float,
    config: AppConfig,
) -> float | None:
    bands = [band for band in sorted(_answer_rule_y_bands(layout)) if top + 35 <= band < bottom]
    if len(bands) < 4:
        return None

    runs: list[list[float]] = []
    current: list[float] = [bands[0]]
    for band in bands[1:]:
        if band - current[-1] <= 34:
            current.append(band)
        else:
            runs.append(current)
            current = [band]
    runs.append(current)

    for run in runs:
        if len(run) >= 4 and run[-1] - run[0] >= 60:
            later_subpart = any(
                block.bbox.y0 > run[-1] + 45
                and block.bbox.y0 < bottom
                and SUBPART_RE.match(block.first_line.strip())
                and not _is_answer_space_text(block.text)
                and not _is_boilerplate_text(block.text)
                for block in layout.blocks
            )
            if later_subpart:
                continue
            text_after = [
                block
                for block in layout.blocks
                if run[0] <= block.bbox.y0 <= min(bottom, run[-1] + 45)
                and not _is_answer_space_text(block.text)
                and not _is_boilerplate_text(block.text)
            ]
            if len(text_after) <= 1:
                return run[0]
    return None


def _is_answer_rule_like(box: BoundingBox, layout: PageLayout) -> bool:
    width = max(0.0, box.x1 - box.x0)
    height = max(0.0, box.y1 - box.y0)
    return height <= 2.5 and width >= layout.width * 0.28


def _is_in_answer_rule_band(box: BoundingBox, bands: list[float]) -> bool:
    if not bands:
        return False
    y_mid = (box.y0 + box.y1) / 2
    return any(abs(y_mid - band) <= 2.5 for band in bands)


def _rescued_continuation_block(
    block: TextBlock,
    page: PageLayout,
    config: AppConfig,
    *,
    answer_rule_bands: list[float] | None = None,
) -> TextBlock | None:
    text = _clean_text_line(block.text)
    if not text:
        return None
    match = re.search(
        r"(?P<label>\((?:a|b|c|d|e|f|g|h|viii|vii|vi|iv|ix|iii|ii|i|v|x)\))(?=\s*\S)",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    rescued_text = text[match.start() :].strip()
    if not rescued_text or _is_answer_space_text(rescued_text):
        return None
    rescued_block = TextBlock(
        page_number=block.page_number,
        text=rescued_text,
        bbox=block.bbox,
        source="rescued_continuation",
        confidence=block.confidence,
        font_size=block.font_size,
        font_name=block.font_name,
        is_bold=block.is_bold,
    )
    if _is_answer_space_text(rescued_text):
        return None
    if _is_control_artifact_text(rescued_text):
        return None
    if answer_rule_bands and _is_in_answer_rule_band(rescued_block.bbox, answer_rule_bands):
        return None
    return rescued_block


def _filter_suspicious_rescued_continuations(
    blocks: list[TextBlock],
    page: PageLayout,
    bottom: float,
    config: AppConfig,
    *,
    is_start_page: bool,
) -> tuple[list[TextBlock], list[str]]:
    if not blocks or not is_start_page:
        return blocks, []

    flags: list[str] = []
    later_question_starts = [
        block
        for block in page.blocks
        if parse_question_start(block.first_line, config)
        and _anchor_block_can_be_question_start(block, page, config)
        and block.bbox.y0 <= bottom + config.detection.anchor_y_tolerance
    ]
    filtered: list[TextBlock] = []
    subpart_blocks = [(block, _subpart_label_from_text(block.first_line)) for block in blocks if _subpart_label_from_text(block.first_line)]

    for block in blocks:
        if block.source != "rescued_continuation":
            filtered.append(block)
            continue

        label = _subpart_label_from_text(block.first_line)
        label_order = _subpart_sort_key(label) if label else None
        top_band = block.bbox.y0 <= config.detection.crop_top_margin + 8

        has_lower_later_subpart = any(
            other is not block
            and other.bbox.y0 > block.bbox.y0
            and other_label is not None
            and label_order is not None
            and (_subpart_sort_key(other_label) or 0) < label_order
            for other, other_label in subpart_blocks
        )
        if top_band and has_lower_later_subpart:
            flags.append("suspicious_top_continuation_excluded")
            continue

        nearby_next_question = any(
            other.bbox.y0 > block.bbox.y0
            and other.bbox.y0 - block.bbox.y1 <= 40
            for other in later_question_starts
        )
        if top_band and nearby_next_question:
            flags.append("suspicious_top_continuation_excluded")
            continue

        filtered.append(block)

    return filtered, flags


def _trim_foreign_top_of_page_continuations(
    blocks: list[TextBlock],
    prior_blocks: list[TextBlock],
    page: PageLayout,
    config: AppConfig,
) -> tuple[list[TextBlock], list[str]]:
    if not blocks or not prior_blocks:
        return blocks, []

    flags: list[str] = []
    filtered = list(blocks)
    prior_labels = _ordered_subpart_labels(prior_blocks)
    expected_next = _next_expected_subpart(prior_labels)
    prior_tokens = _content_overlap_tokens(extract_text_from_blocks(prior_blocks))

    while filtered:
        candidate = filtered[0]
        if candidate.source != "rescued_continuation":
            break
        if candidate.bbox.y0 > config.detection.crop_top_margin + 8:
            break

        candidate_text = _clean_text_line(candidate.text)
        candidate_label = _subpart_label_from_text(candidate.first_line)
        candidate_tokens = _content_overlap_tokens(candidate_text)
        overlap = prior_tokens & candidate_tokens
        has_filler = _is_answer_space_text(candidate_text) or bool(re.search(r"(?:\.\s*){12,}|[._\-–—]{30,}", candidate_text))
        has_furniture = bool(re.search(r"DO NOT WRITE IN THIS MARGIN|Turn over|write the question number|\b9709/", candidate_text, re.IGNORECASE))
        duplicate_label = bool(candidate_label and candidate_label in prior_labels)
        unexpected_label = bool(candidate_label and expected_next and candidate_label != expected_next)
        clearly_foreign = (has_filler or has_furniture) and not overlap and (duplicate_label or unexpected_label or len(candidate_tokens) >= 3)

        if not clearly_foreign:
            break

        filtered.pop(0)
        flags.append("newer_format_scope_stop_before_foreign_continuation")

    return filtered, flags


def _clean_text_line(text: str) -> str:
    return " ".join(_strip_control_chars(text).replace("\u00a0", " ").split())


def _strip_control_chars(text: str) -> str:
    return "".join(char if ord(char) >= 32 or char in "\n\t\r" else " " for char in text)


def _content_overlap_tokens(text: str) -> set[str]:
    stopwords = {
        "the", "and", "for", "that", "with", "from", "into", "then", "than", "find", "show", "draw", "complete",
        "make", "use", "given", "below", "their", "there", "this", "these", "those", "probability", "diagram",
        "value", "values", "mean", "median", "range", "data", "information", "random", "number", "numbers",
        "question", "answer", "work", "write", "margin", "side", "sides", "represent", "entering", "remaining",
        "probabilities", "players", "employee", "employees",
    }
    return {
        token
        for token in re.findall(r"[A-Za-z]{3,}", text.lower())
        if token not in stopwords
    }


def _block_has_subpart_label(block: TextBlock) -> bool:
    if SUBPART_RE.match(block.first_line):
        return True
    parsed = QUESTION_START_RE.match(block.first_line.strip())
    return bool(parsed and parsed.group("label"))


def _flush_pending_rescues(pending: list[TextBlock], selected: list[TextBlock]) -> list[TextBlock]:
    existing = {_subpart_label_from_text(block.first_line) for block in selected}
    flushed: list[TextBlock] = []
    for block in pending:
        label = _subpart_label_from_text(block.first_line)
        if label and label not in existing:
            flushed.append(block)
            existing.add(label)
    return flushed


def _ordered_subpart_labels(blocks: list[TextBlock]) -> list[str]:
    labels: list[str] = []
    for block in blocks:
        label = _subpart_label_from_text(block.first_line)
        if label and label not in labels:
            labels.append(label)
    sort_keys = [_subpart_sort_key(label) for label in labels]
    if labels and all(key is not None for key in sort_keys):
        return [label for label, _key in sorted(zip(labels, sort_keys), key=lambda item: item[1])]
    return labels


def _subpart_label_from_text(text: str) -> str | None:
    match = SUBPART_RE.match(text)
    if match:
        return match.group("label").strip("()").lower()
    parsed = QUESTION_START_RE.match(text.strip())
    if parsed and parsed.group("label"):
        labels = re.findall(r"\(([a-zivxlcdm]+)\)", parsed.group("label"), re.IGNORECASE)
        if labels:
            return labels[-1].lower()
    return None


def _subpart_sequence_flags(blocks: list[TextBlock]) -> list[str]:
    labels = _ordered_subpart_labels(blocks)
    if len(labels) < 2:
        return []
    flags: list[str] = []
    if _missing_internal_subparts(labels):
        flags.append("question_subpart_sequence_gap")
        flags.append("question_scope_incomplete")
    return flags


def _has_subpart_sequence_gap(labels: list[str]) -> bool:
    return bool(_missing_internal_subparts(labels))


def _missing_internal_subparts(labels: list[str]) -> list[str]:
    positions = [_subpart_sort_key(label) for label in labels]
    if any(position is None for position in positions):
        return []
    numeric_positions = [position for position in positions if position is not None]
    if not numeric_positions:
        return []
    label_series = _subpart_series(labels[0])
    if not label_series:
        return []
    missing: list[str] = []
    seen = set(labels)
    for position in range(numeric_positions[0], numeric_positions[-1] + 1):
        candidate = label_series[position - 1]
        if candidate not in seen:
            missing.append(candidate)
    return missing


def _subpart_sort_key(label: str) -> int | None:
    alpha_labels = ["a", "b", "c", "d", "e", "f", "g", "h"]
    roman_labels = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"]
    if label in alpha_labels:
        return alpha_labels.index(label) + 1
    if label in roman_labels:
        return roman_labels.index(label) + 1
    return None


def _subpart_series(label: str) -> list[str]:
    alpha_labels = ["a", "b", "c", "d", "e", "f", "g", "h"]
    roman_labels = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"]
    if label in alpha_labels:
        return alpha_labels
    if label in roman_labels:
        return roman_labels
    return []


def _question_validation_flags(
    *,
    start: QuestionStart,
    blocks: list[TextBlock],
    layouts: list[PageLayout],
    config: AppConfig,
    format_profile: str,
    review_flags: list[str],
) -> tuple[list[str], dict[str, object]]:
    text = extract_text_from_blocks(blocks)
    subparts = _ordered_subpart_labels(blocks)
    missing_internal_subparts = _missing_internal_subparts(subparts)
    subpart_sequence_gap = bool(missing_internal_subparts)
    contamination_detected, contamination_indicators = _question_scope_contamination(
        text=text,
        start=start,
        review_flags=review_flags,
        config=config,
    )
    mark_values = [int(match.group("marks")) for match in MARK_RE.finditer(text)]
    terminal_mark_total = _terminal_mark_total(text)
    question_total_detected = _detected_question_total(mark_values, terminal_mark_total, subparts)
    block_count = len(blocks)
    text_len = len(text.strip())
    anchor_text = blocks[0].first_line if blocks else ""
    body_after_anchor = re.sub(rf"^\s*{re.escape(start.question_number)}(?:\([^)]+\))*\s*", "", anchor_text).strip()
    weak_anchor = (
        not blocks
        or text_len < max(14, config.detection.min_question_chars // 2)
        or (len(body_after_anchor) < 4 and not _has_strong_follow_on_question_body(blocks, start.question_number, config))
        or (start.confidence < 0.6 and block_count <= 2 and text_len < 120)
        or ("question_start_uncertain" in review_flags and text_len < 80)
    )
    likely_truncated = (
        text_len < max(config.detection.min_question_chars, 28)
        or (block_count <= 1 and text_len < 32 and bool(subparts))
        or "short_question_text" in review_flags
        or "answer_space_heavy" in review_flags
    )
    first_label_incomplete = _first_label_incomplete(
        subparts=subparts,
        terminal_mark_total=terminal_mark_total,
        text_len=text_len,
        min_question_chars=config.detection.min_question_chars,
        mark_value_count=len(mark_values),
    )
    impossible_subpart_sequence_detected = subpart_sequence_gap or first_label_incomplete
    missing_terminal_mark_total = _missing_terminal_mark_total(
        subparts=subparts,
        terminal_mark_total=terminal_mark_total,
        format_profile=format_profile,
        first_label_incomplete=first_label_incomplete,
        mark_value_count=len(mark_values),
    )
    validation_flags = _question_validation_flag_list(
        contamination_detected=contamination_detected,
        subpart_sequence_gap=subpart_sequence_gap,
        first_label_incomplete=first_label_incomplete,
        missing_terminal_mark_total=missing_terminal_mark_total,
        weak_anchor=weak_anchor,
        likely_truncated=likely_truncated,
    )

    structure_detected: dict[str, object] = {
        "format_profile": format_profile,
        "subparts": subparts,
        "subpart_type": _subpart_type(subparts),
        "missing_internal_subparts": missing_internal_subparts,
        "subpart_sequence_gap": subpart_sequence_gap,
        "first_label_incomplete": first_label_incomplete,
        "impossible_subpart_sequence_detected": impossible_subpart_sequence_detected,
        "mark_values_detected": mark_values,
        "terminal_mark_total_detected": terminal_mark_total,
        "question_total_detected": question_total_detected,
        "has_terminal_mark_total": terminal_mark_total is not None,
        "missing_terminal_mark_total": missing_terminal_mark_total,
        "text_length": text_len,
        "block_count": block_count,
        "weak_anchor": weak_anchor,
        "likely_truncated": likely_truncated,
        "contamination_detected": contamination_detected,
        "contamination_indicators": contamination_indicators,
    }
    return sorted(set(validation_flags)), structure_detected


def _recover_incomplete_span_blocks(
    *,
    start: QuestionStart,
    blocks: list[TextBlock],
    layouts: list[PageLayout],
    start_page: int,
    start_y: float,
    end_page: int,
    end_y: float,
    config: AppConfig,
    format_profile: str,
) -> tuple[list[TextBlock], bool, str]:
    initial_flags, _ = _question_validation_flags(
        start=start,
        blocks=blocks,
        layouts=layouts,
        config=config,
        format_profile=format_profile,
        review_flags=[],
    )
    if not (set(initial_flags) & RECOVERABLE_QUESTION_VALIDATION_FLAGS):
        return blocks, False, "not_needed"

    selected_keys = {(block.page_number, round(block.bbox.y0, 1), round(block.bbox.x0, 1), _clean_text_line(block.text)) for block in blocks}
    recovered = list(blocks)
    expected_next = _next_expected_subpart(_ordered_subpart_labels(blocks))
    added = 0
    max_added = 4 if format_profile == "caie_2024_2025" else 2

    for page in layouts:
        if page.page_number < start_page or page.page_number > end_page:
            continue
        top = start_y if page.page_number == start_page else 0.0
        recovery_top = 0.0 if page.page_number == start_page else top
        bottom = end_y if page.page_number == end_page else page.height - config.detection.crop_bottom_margin
        answer_rule_bands = _answer_rule_y_bands(page)
        for raw_block in sorted(page.blocks, key=lambda item: (item.bbox.y0, item.bbox.x0)):
            if raw_block.bbox.y0 < recovery_top or raw_block.bbox.y0 >= bottom:
                continue
            if raw_block.bbox.y0 < top and page.page_number == start_page:
                candidate = _rescued_prefix_continuation_block(
                    raw_block,
                    page,
                    config,
                    answer_rule_bands=answer_rule_bands,
                )
            else:
                candidate = raw_block if _is_question_content_block(raw_block, page, config, answer_rule_bands=answer_rule_bands) else _rescued_continuation_block(
                    raw_block,
                    page,
                    config,
                    answer_rule_bands=answer_rule_bands,
                )
            if candidate is None:
                continue
            key = (candidate.page_number, round(candidate.bbox.y0, 1), round(candidate.bbox.x0, 1), _clean_text_line(candidate.text))
            if key in selected_keys:
                continue
            parsed = parse_question_start(candidate.first_line, config)
            if parsed and parsed[0] != start.question_number:
                continue
            label = _subpart_label_from_text(candidate.first_line)
            is_prefix_recovery = candidate.source == "rescued_prefix_continuation" and _allow_prefix_recovery_candidate(
                candidate=candidate,
                existing_blocks=recovered,
                current_labels=_ordered_subpart_labels(recovered),
                question_number=start.question_number,
            )
            is_expected_continuation = bool(
                label and expected_next and label == expected_next and candidate.source != "rescued_prefix_continuation"
            )
            is_terminal_mark = expected_next is None and _terminal_mark_total(candidate.text) is not None
            is_new_subpart_label = bool(
                label and label not in _ordered_subpart_labels(recovered) and candidate.source != "rescued_prefix_continuation"
            )
            if not is_expected_continuation and not is_terminal_mark and not is_prefix_recovery and not is_new_subpart_label:
                continue
            recovered.append(candidate)
            selected_keys.add(key)
            added += 1
            if label:
                expected_next = _next_expected_subpart(_ordered_subpart_labels(recovered))
            if added >= max_added:
                break
        if added >= max_added:
            break

    recovered = sorted(recovered, key=lambda block: (block.page_number, block.bbox.y0, block.bbox.x0))
    final_flags, _ = _question_validation_flags(
        start=start,
        blocks=recovered,
        layouts=layouts,
        config=config,
        format_profile=format_profile,
        review_flags=[],
    )
    if _recovery_improved_validation(initial_flags, final_flags):
        return recovered, True, "improved"
    return blocks, True, "no_change"


def _question_validation_status(validation_flags: list[str], review_flags: list[str]) -> str:
    if validation_flags:
        return "fail"
    if "question_start_uncertain" in review_flags:
        return "review"
    return "pass"


def _has_strong_follow_on_question_body(blocks: list[TextBlock], question_number: str, config: AppConfig) -> bool:
    if len(blocks) <= 1:
        return False
    follow_on_text = extract_text_from_blocks(blocks[1:])
    follow_on_text = re.sub(rf"^\s*{re.escape(question_number)}(?:\([^)]+\))*\s*", "", follow_on_text).strip()
    alpha_count = sum(1 for char in follow_on_text if char.isalpha())
    return alpha_count >= max(30, config.detection.min_question_chars * 2)


def _first_label_incomplete(
    *,
    subparts: list[str],
    terminal_mark_total: int | None,
    text_len: int,
    min_question_chars: int,
    mark_value_count: int,
) -> bool:
    if len(subparts) != 1 or subparts[0] not in {"a", "i"}:
        return False
    if mark_value_count > 1:
        return True
    strong_end_evidence = terminal_mark_total is not None and text_len >= max(min_question_chars, 24)
    return not strong_end_evidence


def _missing_terminal_mark_total(
    *,
    subparts: list[str],
    terminal_mark_total: int | None,
    format_profile: str,
    first_label_incomplete: bool,
    mark_value_count: int,
) -> bool:
    return bool(
        subparts
        and terminal_mark_total is None
        and (format_profile == "caie_2024_2025" or first_label_incomplete or mark_value_count < len(subparts))
    )


def _question_validation_flag_list(
    *,
    contamination_detected: bool,
    subpart_sequence_gap: bool,
    first_label_incomplete: bool,
    missing_terminal_mark_total: bool,
    weak_anchor: bool,
    likely_truncated: bool,
) -> list[str]:
    validation_flags: list[str] = []
    if contamination_detected:
        validation_flags.append("question_scope_contaminated")
    if subpart_sequence_gap or first_label_incomplete:
        validation_flags.append("question_subparts_incomplete")
    if missing_terminal_mark_total:
        validation_flags.append("missing_terminal_mark_total")
    if weak_anchor:
        validation_flags.append("weak_question_anchor")
    if likely_truncated:
        validation_flags.append("likely_truncated_question_crop")
    return sorted(set(validation_flags))


def _recovery_improved_validation(initial_flags: list[str], final_flags: list[str]) -> bool:
    if "question_scope_contaminated" in final_flags and "question_scope_contaminated" not in initial_flags:
        return False
    return len(final_flags) < len(initial_flags) or (
        "question_subparts_incomplete" in initial_flags
        and "question_subparts_incomplete" not in final_flags
        and "question_scope_contaminated" not in final_flags
    )


def _next_expected_subpart(labels: list[str]) -> str | None:
    if not labels:
        return None
    last = labels[-1]
    index = _subpart_sort_key(last)
    if index is None:
        return None
    series = ["a", "b", "c", "d", "e", "f", "g", "h"] if last in {"a", "b", "c", "d", "e", "f", "g", "h"} else ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"]
    if index >= len(series):
        return None
    return series[index]


def _terminal_mark_total(text: str) -> int | None:
    lines = [line.strip() for line in _strip_control_chars(text).replace("\u00a0", " ").splitlines() if line.strip()]
    for line in reversed(lines[-3:]):
        match = TERMINAL_MARK_RE.search(line)
        if match:
            return int(match.group("marks"))
    return None


def _rescued_prefix_continuation_block(
    block: TextBlock,
    page: PageLayout,
    config: AppConfig,
    *,
    answer_rule_bands: list[float] | None = None,
) -> TextBlock | None:
    if block.bbox.y0 > config.detection.crop_top_margin + 18:
        return None
    rescued = _rescued_continuation_block(block, page, config, answer_rule_bands=answer_rule_bands)
    if rescued is not None:
        return TextBlock(
            page_number=rescued.page_number,
            text=rescued.text,
            bbox=rescued.bbox,
            source="rescued_prefix_continuation",
            confidence=rescued.confidence,
            font_size=rescued.font_size,
            font_name=rescued.font_name,
            is_bold=rescued.is_bold,
        )

    stripped = _strip_leading_boilerplate(block.text)
    if not stripped:
        return None
    normalized = _clean_text_line(stripped)
    if not normalized or len(normalized) < 18:
        return None
    if _is_answer_space_text(normalized) or _is_control_artifact_text(normalized):
        return None
    if parse_question_start(normalized, config):
        return None
    alpha_count = sum(1 for char in normalized if char.isalpha())
    if alpha_count < 12:
        return None
    candidate = TextBlock(
        page_number=block.page_number,
        text=normalized,
        bbox=block.bbox,
        source="rescued_prefix_continuation",
        confidence=block.confidence,
        font_size=block.font_size,
        font_name=block.font_name,
        is_bold=block.is_bold,
    )
    if answer_rule_bands and _is_in_answer_rule_band(candidate.bbox, answer_rule_bands):
        return None
    return candidate


def _strip_leading_boilerplate(text: str) -> str:
    stripped = _strip_control_chars(text).replace("\u00a0", " ")
    stripped = re.sub(r"^\s*©\s*UCLES\b\s*\d{4}\s*", "", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"^\s*(?:DO NOT WRITE IN THIS MARGIN\s*)+", "", stripped, flags=re.IGNORECASE)
    return stripped.strip()


def _allow_prefix_recovery_candidate(
    *,
    candidate: TextBlock,
    existing_blocks: list[TextBlock],
    current_labels: list[str],
    question_number: str,
) -> bool:
    if not _span_anchor_is_trivial(existing_blocks, question_number):
        return False
    if not _prefix_candidate_has_context_overlap(candidate.text, existing_blocks):
        return False
    label = _subpart_label_from_text(candidate.first_line)
    if label and label not in current_labels:
        return True
    return _span_has_dangling_prompt_prefix(existing_blocks)


def _span_has_dangling_prompt_prefix(blocks: list[TextBlock]) -> bool:
    text = extract_text_from_blocks(blocks)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    tail = lines[-4:]
    return any(
        line in {"(a)", "(b)", "(c)", "(d)", "(i)", "(ii)", "(iii)", "(iv)", "x", "y"}
        or bool(re.fullmatch(r"\([a-zivxlcdm]+\)", line, re.IGNORECASE))
        for line in tail
    )


def _span_anchor_is_trivial(blocks: list[TextBlock], question_number: str) -> bool:
    if not blocks:
        return True
    anchor_line = blocks[0].first_line
    anchor_body = re.sub(rf"^\s*{re.escape(question_number)}(?:\([^)]+\))*\s*", "", anchor_line).strip()
    alpha_count = sum(1 for char in anchor_body if char.isalpha())
    return alpha_count < 4


def _prefix_candidate_has_context_overlap(candidate_text: str, existing_blocks: list[TextBlock]) -> bool:
    candidate_tokens = _content_overlap_tokens(candidate_text)
    if not candidate_tokens:
        return False
    context_tokens = _content_overlap_tokens(extract_text_from_blocks(existing_blocks))
    return bool(candidate_tokens & context_tokens)


def _detected_question_total(mark_values: list[int], terminal_mark_total: int | None, subparts: list[str]) -> int | None:
    if not mark_values:
        return terminal_mark_total
    if not subparts or len(mark_values) == 1:
        return terminal_mark_total if terminal_mark_total is not None else sum(mark_values)
    if terminal_mark_total is None:
        return sum(mark_values)
    if len(mark_values) > len(subparts):
        return terminal_mark_total
    if len(mark_values) == len(subparts) and terminal_mark_total == mark_values[-1] and sum(mark_values) > terminal_mark_total:
        return sum(mark_values)
    return terminal_mark_total


def _question_subparts_from_text_for_validation(text: str) -> list[str]:
    labels: list[str] = []
    for line in text.splitlines():
        line = _clean_text_line(line)
        if not line:
            continue
        label = _subpart_label_from_text(line)
        if label and label not in labels:
            labels.append(label)
    return labels


def _question_scope_contamination(
    *,
    text: str,
    start: QuestionStart,
    review_flags: list[str],
    config: AppConfig,
) -> tuple[bool, dict[str, object]]:
    normalized_lines = [_clean_text_line(line) for line in _strip_control_chars(text).replace("\u00a0", " ").splitlines()]
    lines = [line for line in normalized_lines if line]

    label_counts: dict[str, int] = {}
    duplicate_labels: list[str] = []
    line_labels: list[str | None] = []
    for line in lines:
        label = _subpart_label_from_text(line)
        line_labels.append(label)
        if not label:
            continue
        label_counts[label] = label_counts.get(label, 0) + 1
        if label_counts[label] == 2:
            duplicate_labels.append(label)

    filler_line_count = sum(
        1
        for line in lines
        if _is_answer_space_text(line)
        or bool(re.search(r"(?:\.\s*){12,}|[._\-–—]{30,}", line))
    )
    embedded_furniture = [
        line
        for line in lines
        if _is_boilerplate_text(line)
        or re.search(r"DO NOT WRITE IN THIS MARGIN|Turn over|write the question number", line, re.IGNORECASE)
    ]
    foreign_question_anchors = [
        parsed[0]
        for line in lines[1:]
        if (parsed := parse_question_start(line, config)) and parsed[0] != start.question_number
    ]
    review_hint_flags = sorted(
        {
            flag
            for flag in review_flags
            if flag in {"possible_next_question_contamination", "header_footer_contamination", "answer_space_heavy"}
        }
    )

    suspicious_indices = {
        index
        for index, line in enumerate(lines)
        if line_labels[index] in duplicate_labels
        or _is_answer_space_text(line)
        or bool(re.search(r"(?:\.\s*){12,}|[._\-–—]{30,}", line))
        or line in embedded_furniture
        or ((parsed := parse_question_start(line, config)) and parsed[0] != start.question_number)
    }
    foreign_content_segments = 0
    foreign_content_examples: list[str] = []
    for index in sorted(suspicious_indices):
        line = lines[index]
        line_tokens = _contamination_content_tokens(line)
        if len(line_tokens) < 3:
            continue
        context_tokens: set[str] = set()
        for earlier in lines[:index]:
            context_tokens.update(_contamination_content_tokens(earlier))
        overlap = line_tokens & context_tokens
        if not overlap:
            foreign_content_segments += 1
            if len(foreign_content_examples) < 2:
                foreign_content_examples.append(line[:160])

    signal_score = 0
    if duplicate_labels:
        signal_score += 2
    if foreign_question_anchors:
        signal_score += 2
    if foreign_content_segments:
        signal_score += 2
    if filler_line_count:
        signal_score += 1
    if embedded_furniture:
        signal_score += 1
    if review_hint_flags:
        signal_score += len(review_hint_flags)

    contaminated = bool(
        duplicate_labels
        or foreign_question_anchors
        or foreign_content_segments >= 1
    )
    indicators: dict[str, object] = {
        "duplicate_subpart_labels": duplicate_labels,
        "filler_line_count": filler_line_count,
        "embedded_furniture_count": len(embedded_furniture),
        "foreign_question_anchors": foreign_question_anchors,
        "foreign_content_segments": foreign_content_segments,
        "foreign_content_examples": foreign_content_examples,
        "review_hint_flags": review_hint_flags,
        "signal_score": signal_score,
    }
    return contaminated, indicators


def _contamination_content_tokens(line: str) -> set[str]:
    stopwords = {
        "the", "and", "for", "that", "with", "from", "into", "then", "than", "find", "show", "draw", "complete",
        "make", "use", "given", "below", "their", "there", "this", "these", "those", "probability", "diagram",
        "value", "values", "mean", "median", "range", "data", "information", "random", "number", "numbers",
        "question", "answer", "work", "write", "margin", "side", "sides", "represent", "entering", "remaining",
    }
    return {
        token
        for token in re.findall(r"[A-Za-z]{3,}", line.lower())
        if token not in stopwords
    }


def _subpart_type(labels: list[str]) -> str:
    if not labels:
        return "none"
    if labels[0] in {"a", "b", "c", "d", "e", "f", "g", "h"}:
        return "alpha"
    if labels[0] in {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"}:
        return "roman"
    return "mixed"


def _paper_format_profile(source_pdf: str | Path | None) -> str:
    if source_pdf is None:
        return "legacy"
    stem = Path(source_pdf).stem
    match = re.search(r"(20\d{2})", stem)
    if match and int(match.group(1)) >= 2024:
        return "caie_2024_2025"
    short_match = re.search(r"(?<!\d)([snjmoad])(\d{2})(?!\d)", stem, re.IGNORECASE)
    if short_match and int(short_match.group(2)) >= 24:
        return "caie_2024_2025"
    return "legacy"
