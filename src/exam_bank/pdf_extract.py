from __future__ import annotations

from collections import defaultdict
from io import BytesIO
from pathlib import Path
from typing import Any

from .config import AppConfig
from .models import BoundingBox, PageLayout, TextBlock


def extract_pdf_layout(pdf_path: str | Path, config: AppConfig, use_ocr: bool | None = None) -> list[PageLayout]:
    """Extract ordered text lines and graphic/image boxes from a PDF.

    PyMuPDF is intentionally imported lazily so preflight can report missing
    dependencies without the entire package failing to import.
    """

    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required for PDF extraction. Install requirements.txt first.") from exc

    pdf_path = Path(pdf_path)
    layouts: list[PageLayout] = []
    ocr_enabled = config.ocr.enabled if use_ocr is None else use_ocr

    with fitz.open(pdf_path) as doc:
        for page_index, page in enumerate(doc):
            page_number = page_index + 1
            blocks = _extract_text_blocks(page, page_number, config)
            graphics = _extract_graphics(page)
            text_len = len(" ".join(block.text for block in blocks).strip())
            warning: str | None = None
            source = "pdf"

            if text_len < config.detection.min_text_chars_per_page:
                if ocr_enabled:
                    try:
                        ocr_blocks = _ocr_page(page, page_number, config)
                    except Exception as exc:  # pragma: no cover - depends on local OCR install
                        ocr_blocks = []
                        warning = f"ocr_failed:{exc.__class__.__name__}"
                    if ocr_blocks:
                        blocks = ocr_blocks
                        source = "ocr"
                        warning = "ocr_used_low_pdf_text"
                    elif warning is None:
                        warning = "weak_text_no_ocr_words"
                else:
                    warning = "weak_text_ocr_disabled"

            layouts.append(
                PageLayout(
                    page_number=page_number,
                    width=float(page.rect.width),
                    height=float(page.rect.height),
                    blocks=sorted(blocks, key=lambda block: (block.bbox.y0, block.bbox.x0)),
                    graphics=graphics,
                    text_source=source,
                    extraction_warning=warning,
                )
            )

    return layouts


def _extract_text_blocks(page: Any, page_number: int, config: AppConfig) -> list[TextBlock]:
    text_dict = page.get_text("dict")
    spans: list[dict[str, Any]] = []
    for raw_block in text_dict.get("blocks", []):
        if raw_block.get("type") != 0:
            continue
        for raw_line in raw_block.get("lines", []):
            for span in raw_line.get("spans", []):
                if str(span.get("text", "")).strip():
                    spans.append(span)

    visual_lines = _group_spans_into_visual_lines(spans, config.detection.span_line_y_tolerance)
    blocks: list[TextBlock] = []
    for line_spans in visual_lines:
        sorted_spans = sorted(line_spans, key=lambda span: (float(span.get("bbox", [0, 0, 0, 0])[0]), float(span.get("bbox", [0, 0, 0, 0])[1])))
        text = _line_text_from_spans(sorted_spans).strip()
        if not text:
            continue
        x0, y0, x1, y1 = _line_bbox_from_spans(sorted_spans)
        font_sizes = [float(span.get("size", 0)) for span in sorted_spans if span.get("text", "").strip()]
        font_names = [str(span.get("font", "")) for span in sorted_spans if span.get("text", "").strip()]
        font_size = sum(font_sizes) / len(font_sizes) if font_sizes else None
        font_name = font_names[0] if font_names else None
        blocks.append(
            TextBlock(
                page_number=page_number,
                text=text,
                bbox=BoundingBox(float(x0), float(y0), float(x1), float(y1)),
                source="pdf",
                font_size=font_size,
                font_name=font_name,
                is_bold=any("bold" in font.lower() for font in font_names),
            )
        )
    return blocks


def _group_spans_into_visual_lines(spans: list[dict[str, Any]], y_tolerance: float) -> list[list[dict[str, Any]]]:
    """Rebuild visual text lines from span boxes using spatial order.

    PDF content streams are often not ordered the way a student reads the page,
    especially around formulas. This function ignores raw parser order: it sorts
    all spans by y/x, groups nearby y positions into a visual line, and lets the
    caller sort within each line by x.
    """

    sorted_spans = sorted(
        [span for span in spans if str(span.get("text", "")).strip()],
        key=lambda span: (_span_center_y(span), _span_x0(span)),
    )
    lines: list[list[dict[str, Any]]] = []
    for span in sorted_spans:
        target_index = _matching_line_index(span, lines, y_tolerance)
        if target_index is None:
            lines.append([span])
        else:
            lines[target_index].append(span)

    return sorted(lines, key=lambda line: (_line_center_y(line), min(_span_x0(span) for span in line)))


def _matching_line_index(span: dict[str, Any], lines: list[list[dict[str, Any]]], y_tolerance: float) -> int | None:
    best_index: int | None = None
    best_distance: float | None = None
    for index, line in enumerate(lines):
        line_center = _line_center_y(line)
        distance = abs(_span_center_y(span) - line_center)
        tolerance = max(y_tolerance, _line_median_font_size(line) * 0.65, float(span.get("size", 0)) * 0.65)
        if distance <= tolerance or _vertical_overlap_ratio(span, line) >= 0.28:
            if best_distance is None or distance < best_distance:
                best_index = index
                best_distance = distance
    return best_index


def _line_text_from_spans(spans: list[dict[str, Any]]) -> str:
    if not spans:
        return ""
    spans = sorted(spans, key=lambda span: (float(span.get("bbox", [0, 0, 0, 0])[0]), float(span.get("bbox", [0, 0, 0, 0])[1])))
    font_sizes = [float(span.get("size", 0)) for span in spans if span.get("text", "").strip()]
    max_size = max(font_sizes) if font_sizes else 0
    line_bbox = _line_bbox_from_spans(spans)
    line_mid = (line_bbox[1] + line_bbox[3]) / 2
    pieces: list[str] = []
    previous_x1: float | None = None
    previous_text = ""

    for span in spans:
        text = str(span.get("text", ""))
        if not text:
            continue
        x0, y0, x1, y1 = [float(value) for value in span.get("bbox", [0, 0, 0, 0])]
        gap = x0 - previous_x1 if previous_x1 is not None else 0
        operator_gap = _needs_operator_spacing(previous_text, text) and gap > 0.5
        if previous_x1 is not None and (operator_gap or gap > max(2.0, float(span.get("size", max_size)) * 0.35)):
            pieces.append(" ")
        previous_x1 = x1
        previous_text = text

        size = float(span.get("size", max_size))
        span_mid = (y0 + y1) / 2
        if max_size and size <= max_size * 0.82 and text.strip():
            if span_mid < line_mid - 1:
                pieces.append(f"^{{{text}}}")
                continue
            if span_mid > line_mid + 1:
                pieces.append(f"_{{{text}}}")
                continue
        pieces.append(text)

    return "".join(pieces)


def _needs_operator_spacing(previous_text: str, text: str) -> bool:
    operators = {"+", "-", "=", "<", ">", "≤", "≥", "±"}
    return previous_text.strip() in operators or text.strip() in operators


def _line_bbox_from_spans(spans: list[dict[str, Any]]) -> tuple[float, float, float, float]:
    bboxes = [span.get("bbox", [0, 0, 0, 0]) for span in spans if span.get("text", "").strip()]
    if not bboxes:
        return (0, 0, 0, 0)
    return (
        min(float(bbox[0]) for bbox in bboxes),
        min(float(bbox[1]) for bbox in bboxes),
        max(float(bbox[2]) for bbox in bboxes),
        max(float(bbox[3]) for bbox in bboxes),
    )


def _span_x0(span: dict[str, Any]) -> float:
    return float(span.get("bbox", [0, 0, 0, 0])[0])


def _span_center_y(span: dict[str, Any]) -> float:
    bbox = span.get("bbox", [0, 0, 0, 0])
    return (float(bbox[1]) + float(bbox[3])) / 2


def _line_center_y(line: list[dict[str, Any]]) -> float:
    sizes = [max(0.1, float(span.get("size", 0))) for span in line]
    weighted = sum(_span_center_y(span) * size for span, size in zip(line, sizes))
    return weighted / sum(sizes)


def _line_median_font_size(line: list[dict[str, Any]]) -> float:
    sizes = sorted(float(span.get("size", 0)) for span in line if float(span.get("size", 0)) > 0)
    if not sizes:
        return 0.0
    middle = len(sizes) // 2
    if len(sizes) % 2:
        return sizes[middle]
    return (sizes[middle - 1] + sizes[middle]) / 2


def _vertical_overlap_ratio(span: dict[str, Any], line: list[dict[str, Any]]) -> float:
    bbox = span.get("bbox", [0, 0, 0, 0])
    span_top = float(bbox[1])
    span_bottom = float(bbox[3])
    line_top = min(float(item.get("bbox", [0, 0, 0, 0])[1]) for item in line)
    line_bottom = max(float(item.get("bbox", [0, 0, 0, 0])[3]) for item in line)
    overlap = max(0.0, min(span_bottom, line_bottom) - max(span_top, line_top))
    span_height = max(0.1, span_bottom - span_top)
    return overlap / span_height


def _extract_graphics(page: Any) -> list[BoundingBox]:
    boxes: list[BoundingBox] = []
    for drawing in page.get_drawings():
        rect = drawing.get("rect")
        if rect and rect.is_valid and not rect.is_empty:
            boxes.append(BoundingBox(float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)))

    try:
        image_infos = page.get_image_info(xrefs=True)
    except Exception:
        image_infos = []
    for image_info in image_infos:
        bbox = image_info.get("bbox")
        if bbox:
            x0, y0, x1, y1 = bbox
            boxes.append(BoundingBox(float(x0), float(y0), float(x1), float(y1)))
    return boxes


def _ocr_page(page: Any, page_number: int, config: AppConfig) -> list[TextBlock]:
    try:
        import fitz
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("pytesseract and Pillow are required for OCR fallback.") from exc

    zoom = config.ocr.dpi / 72
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix, alpha=False)
    image = Image.open(BytesIO(pix.tobytes("png"))).convert("RGB")
    data = pytesseract.image_to_data(
        image,
        lang=config.ocr.language,
        output_type=pytesseract.Output.DICT,
    )

    grouped: dict[tuple[int, int, int], list[tuple[str, int, int, int, int, float]]] = defaultdict(list)
    for index, word in enumerate(data.get("text", [])):
        word = word.strip()
        if not word:
            continue
        try:
            confidence = float(data["conf"][index])
        except (ValueError, TypeError):
            confidence = -1
        if confidence >= 0 and confidence < config.ocr.min_confidence:
            continue
        key = (int(data["block_num"][index]), int(data["par_num"][index]), int(data["line_num"][index]))
        grouped[key].append(
            (
                word,
                int(data["left"][index]),
                int(data["top"][index]),
                int(data["width"][index]),
                int(data["height"][index]),
                confidence,
            )
        )

    scale_x = float(page.rect.width) / image.width
    scale_y = float(page.rect.height) / image.height
    blocks: list[TextBlock] = []
    for words in grouped.values():
        words.sort(key=lambda item: item[1])
        text = " ".join(item[0] for item in words)
        left = min(item[1] for item in words)
        top = min(item[2] for item in words)
        right = max(item[1] + item[3] for item in words)
        bottom = max(item[2] + item[4] for item in words)
        confidences = [item[5] for item in words if item[5] >= 0]
        avg_confidence = sum(confidences) / len(confidences) if confidences else None
        blocks.append(
            TextBlock(
                page_number=page_number,
                text=text,
                bbox=BoundingBox(left * scale_x, top * scale_y, right * scale_x, bottom * scale_y),
                source="ocr",
                confidence=avg_confidence,
            )
        )

    if blocks:
        return sorted(blocks, key=lambda block: (block.bbox.y0, block.bbox.x0))

    text = pytesseract.image_to_string(image, lang=config.ocr.language).strip()
    if not text:
        return []
    return [
        TextBlock(
            page_number=page_number,
            text=text,
            bbox=BoundingBox(0, 0, float(page.rect.width), float(page.rect.height)),
            source="ocr",
            confidence=None,
        )
    ]
