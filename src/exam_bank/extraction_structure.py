from __future__ import annotations

from dataclasses import dataclass
import re

from .config import AppConfig
from .models import BoundingBox, PageLayout, QuestionSpan, TextBlock


_PART_LINE_RE = re.compile(
    r"^\s*(?:(?P<number>\d{1,2})\s*)?(?P<label>\((?:[a-h]|i{1,3}|iv|v|vi{0,3}|ix|x)\)(?:\((?:i{1,3}|iv|v|vi{0,3}|ix|x)\))?)",
    re.IGNORECASE,
)
_MATH_TOKEN_RE = re.compile(
    r"(?:=|<|>|≤|≥|\^|√|π|θ|∫|Σ|sin|cos|tan|sec|cosec|cot|ln|log|dy/dx|dx/dt|x\s*=|y\s*=|\|z\||arg|vector)",
    re.IGNORECASE,
)
_SUSPICIOUS_SYMBOL_RUN_RE = re.compile(r"[=<>^/*_]{4,}|[?�]{3,}|(?:[A-Za-z0-9][^A-Za-z0-9\s]){4,}")
_SIMPLE_DIAGRAM_LABEL_RE = re.compile(
    r"^(?:[A-Z](?:\s*[A-Z]){0,4}|[xyXY]|θ|π|\d+(?:\.\d+)?\s*(?:cm|mm|m|kg)|\d+(?:\.\d+)?°?)$"
)


@dataclass(frozen=True)
class StructuredQuestionText:
    body_text_raw: str
    body_text_normalized: str
    math_lines: list[str]
    diagram_text: list[str]
    extraction_quality_score: float
    extraction_quality_flags: list[str]
    combined_question_text: str
    part_texts: list[dict[str, object]]


@dataclass(frozen=True)
class _LineItem:
    text: str
    page_number: int
    bbox: BoundingBox
    font_size: float | None = None


def build_structured_question_text(
    span: QuestionSpan,
    layouts: list[PageLayout],
    config: AppConfig,
) -> StructuredQuestionText:
    lines = _lines_from_blocks(span.blocks)
    diagram_lines: list[str] = []
    body_lines: list[str] = []

    for line in lines:
        layout = _layout_by_number(layouts, line.page_number)
        if _looks_like_diagram_text(line, layout, span, config):
            diagram_lines.append(line.text)
        else:
            body_lines.append(line.text)

    body_text_raw = "\n".join(_clean_raw_line(line) for line in body_lines if _clean_raw_line(line)).strip()
    body_text_normalized = _normalize_preserving_structure(body_text_raw)
    math_lines = _extract_math_lines(body_text_raw)
    extraction_quality_flags = _extraction_quality_flags(body_text_raw, body_text_normalized, math_lines, diagram_lines)
    extraction_quality_score = _quality_score(extraction_quality_flags)
    combined_question_text = body_text_normalized
    part_texts = _part_texts(body_text_raw)

    return StructuredQuestionText(
        body_text_raw=body_text_raw,
        body_text_normalized=body_text_normalized,
        math_lines=math_lines,
        diagram_text=[_normalize_light(line) for line in diagram_lines if _normalize_light(line)],
        extraction_quality_score=extraction_quality_score,
        extraction_quality_flags=extraction_quality_flags,
        combined_question_text=combined_question_text,
        part_texts=part_texts,
    )


def _lines_from_blocks(blocks: list[TextBlock]) -> list[_LineItem]:
    items: list[_LineItem] = []
    for block in sorted(blocks, key=lambda item: (item.page_number, item.bbox.y0, item.bbox.x0)):
        raw_lines = [line for line in block.text.splitlines() if line.strip()]
        if not raw_lines:
            continue
        line_height = max(1.0, (block.bbox.y1 - block.bbox.y0) / max(1, len(raw_lines)))
        for index, line in enumerate(raw_lines):
            y0 = block.bbox.y0 + (index * line_height)
            y1 = min(block.bbox.y1, y0 + line_height)
            items.append(
                _LineItem(
                    text=line,
                    page_number=block.page_number,
                    bbox=BoundingBox(block.bbox.x0, y0, block.bbox.x1, y1),
                    font_size=block.font_size,
                )
            )
    return items


def _looks_like_diagram_text(line: _LineItem, layout: PageLayout, span: QuestionSpan, config: AppConfig) -> bool:
    cleaned = _normalize_light(line.text)
    if not cleaned:
        return False
    if re.match(rf"^\s*{re.escape(span.question_number)}(?:\b|[.)])", cleaned):
        return False
    if _PART_LINE_RE.match(cleaned):
        return False

    near_graphic = any(_distance_to_box(line.bbox, graphic) <= 26 for graphic in layout.graphics)
    short = len(cleaned) <= 16 and len(cleaned.split()) <= 4
    simple_label = bool(_SIMPLE_DIAGRAM_LABEL_RE.match(cleaned))
    sentence_like = bool(re.search(r"\b(the|find|show|calculate|solve|given|diagram)\b", cleaned, re.IGNORECASE))
    math_like = _line_is_math_heavy(cleaned)

    if near_graphic and short and not sentence_like and not math_like:
        return True
    if near_graphic and simple_label:
        return True
    if simple_label and short and line.bbox.x0 > config.detection.question_start_max_x + 40:
        return True
    return False


def _normalize_preserving_structure(text: str) -> str:
    normalized_lines = [_normalize_light(line) for line in text.splitlines()]
    return "\n".join(line for line in normalized_lines if line).strip()


def _normalize_light(text: str) -> str:
    value = text.replace("\u00a0", " ")
    value = value.replace("−", "-").replace("–", "-").replace("—", "-")
    value = re.sub(r"[ \t]+", " ", value.strip())
    return value


def _clean_raw_line(text: str) -> str:
    value = text.replace("\u00a0", " ")
    value = value.replace("\r", " ")
    return value.rstrip()


def _extract_math_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = _normalize_light(raw_line)
        if not line:
            continue
        if _line_is_math_heavy(line):
            lines.append(line)
    return lines


def _line_is_math_heavy(line: str) -> bool:
    math_tokens = len(_MATH_TOKEN_RE.findall(line))
    symbol_count = len(re.findall(r"[=<>^/√πθ∫Σ()+\-]", line))
    alpha_count = sum(char.isalpha() for char in line)
    digit_count = sum(char.isdigit() for char in line)
    return math_tokens >= 1 or symbol_count >= 3 or (digit_count >= 2 and alpha_count >= 2 and "=" in line)


def _extraction_quality_flags(
    body_text_raw: str,
    body_text_normalized: str,
    math_lines: list[str],
    diagram_lines: list[str],
) -> list[str]:
    flags: list[str] = []
    if len(body_text_normalized) < 24 or body_text_normalized.count("\n") == 0:
        flags.append("weak_text_structure")
    if math_lines and len(body_text_normalized.splitlines()) <= 2:
        flags.append("flattened_display_math")
    if diagram_lines and re.search(r"\n(?:[A-Z](?:\s+[A-Z]){1,}|x\s+y|\d+\s+cm)\n", f"\n{body_text_raw}\n"):
        flags.append("diagram_text_mixed_with_body")
    if _unmatched_parentheses(body_text_raw):
        flags.append("broken_fraction_structure")
    if re.search(r"(?:sin|cos|tan|ln|log)\s+[A-Za-z0-9]\b", body_text_raw):
        flags.append("broken_superscript_or_power")
    if _SUSPICIOUS_SYMBOL_RUN_RE.search(body_text_raw):
        flags.append("suspicious_symbol_run")
    if len(math_lines) >= max(2, len(body_text_normalized.splitlines()) // 2):
        flags.append("heavy_math_density")
    if any(flag in flags for flag in {"broken_superscript_or_power", "broken_fraction_structure", "suspicious_symbol_run", "flattened_display_math"}):
        flags.append("math_corruption_suspected")
    if "math_corruption_suspected" in flags or ("diagram_text_mixed_with_body" in flags and "heavy_math_density" in flags):
        flags.append("likely_needs_visual_review")
    return sorted(set(flags))


def _unmatched_parentheses(text: str) -> bool:
    opens = text.count("(") + text.count("[") + text.count("{")
    closes = text.count(")") + text.count("]") + text.count("}")
    return opens != closes


def _quality_score(flags: list[str]) -> float:
    score = 1.0
    penalties = {
        "weak_text_structure": 0.18,
        "flattened_display_math": 0.14,
        "diagram_text_mixed_with_body": 0.12,
        "broken_superscript_or_power": 0.14,
        "broken_fraction_structure": 0.14,
        "suspicious_symbol_run": 0.18,
        "heavy_math_density": 0.08,
        "math_corruption_suspected": 0.12,
        "likely_needs_visual_review": 0.08,
    }
    for flag in flags:
        score -= penalties.get(flag, 0.0)
    return max(0.05, min(1.0, score))


def _part_texts(body_text_raw: str) -> list[dict[str, object]]:
    lines = body_text_raw.splitlines()
    if not any(_PART_LINE_RE.match(line) for line in lines):
        return []

    parts: list[dict[str, object]] = []
    current_label = ""
    current_lines: list[str] = []
    for line in lines:
        match = _PART_LINE_RE.match(line)
        if match:
            if current_label and current_lines:
                raw = "\n".join(current_lines).strip()
                parts.append(
                    {
                        "part_label": current_label,
                        "raw_text": raw,
                        "normalized_text": _normalize_preserving_structure(raw),
                        "math_lines": _extract_math_lines(raw),
                    }
                )
            current_label = match.group("label").lower()
            current_lines = [line]
        elif current_label:
            current_lines.append(line)
    if current_label and current_lines:
        raw = "\n".join(current_lines).strip()
        parts.append(
            {
                "part_label": current_label,
                "raw_text": raw,
                "normalized_text": _normalize_preserving_structure(raw),
                "math_lines": _extract_math_lines(raw),
            }
        )
    return parts


def _layout_by_number(layouts: list[PageLayout], page_number: int) -> PageLayout:
    for layout in layouts:
        if layout.page_number == page_number:
            return layout
    raise KeyError(f"Missing layout for page {page_number}")


def _distance_to_box(a: BoundingBox, b: BoundingBox) -> float:
    dx = max(b.x0 - a.x1, a.x0 - b.x1, 0)
    dy = max(b.y0 - a.y1, a.y0 - b.y1, 0)
    return max(dx, dy)
