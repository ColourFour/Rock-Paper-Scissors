from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
import json
import re

from .config import AppConfig
from .models import BoundingBox, PageLayout, QuestionSpan, RenderResult, TextBlock
from .question_detection import detect_question_anchor_candidates, extract_text_from_blocks, parse_question_start


@dataclass
class CropRegion:
    page_number: int
    bbox: BoundingBox
    text_blocks: list[TextBlock] = field(default_factory=list)
    graphics: list[BoundingBox] = field(default_factory=list)


def render_question_image(
    pdf_path: str | Path,
    span: QuestionSpan,
    layouts: list[PageLayout],
    config: AppConfig,
) -> RenderResult:
    """Render original PDF pixels cropped tightly to prompt content."""

    if config.detection.output_mode == "full_region":
        return _render_full_region_image(pdf_path, span, layouts, config)
    return _render_prompt_crop_image(pdf_path, span, layouts, config)


def _render_prompt_crop_image(
    pdf_path: str | Path,
    span: QuestionSpan,
    layouts: list[PageLayout],
    config: AppConfig,
) -> RenderResult:
    try:
        import fitz
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise RuntimeError("PyMuPDF and Pillow are required for rendering screenshots.") from exc

    output_path = _image_output_path(span, config)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    regions, flags = _detect_prompt_regions(span, layouts, config)
    crop_uncertain = False

    if not regions:
        regions = _fallback_regions(span, layouts, config)
        flags.extend(["crop_fallback_used", "crop_uncertain"])
        crop_uncertain = True

    if any(flag == "ocr_question_text" or flag.startswith("ocr_") for flag in span.review_flags):
        flags.append("crop_uncertain")
        crop_uncertain = True

    zoom = config.detection.render_dpi / 72
    matrix = fitz.Matrix(zoom, zoom)
    crops = []
    debug_paths: list[str] = []

    with fitz.open(pdf_path) as doc:
        rendered_pages = {}
        for region in regions:
            if region.page_number not in rendered_pages:
                page = doc[region.page_number - 1]
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                page_image = Image.open(BytesIO(pix.tobytes("png"))).convert("RGB")
                rendered_pages[region.page_number] = page_image

                if config.debug.enabled and config.debug.save_rendered_pages:
                    debug_paths.append(_save_debug_image(page_image, span, region.page_number, "rendered", config))

            layout = _layout_by_number(layouts, region.page_number)
            pixel_box = _pdf_box_to_pixel_box(region.bbox, zoom, rendered_pages[region.page_number].size)
            if _box_height(region.bbox) > layout.height * config.detection.max_crop_height_ratio:
                flags.extend(["crop_reaches_page_margin", "crop_uncertain"])
                crop_uncertain = True

            crop = rendered_pages[region.page_number].crop(pixel_box)
            crops.append(crop)

        if config.debug.enabled:
            debug_paths.extend(_write_debug_overlays(rendered_pages, span, layouts, regions, zoom, config))

    if not crops:
        raise RuntimeError(f"No crops could be rendered for {span.paper_name} question {span.question_number}.")

    stitched = _stitch_images(crops, config.detection.stitch_gap_px)
    stitched.save(output_path)

    if config.debug.enabled:
        debug_paths.append(_write_crop_metadata(span, regions, flags, config))

    crop_uncertain = crop_uncertain or "crop_uncertain" in flags
    extracted_text = _text_from_regions(regions) or span.combined_text
    flags = sorted(set(flags))
    return RenderResult(
        screenshot_path=output_path,
        review_flags=flags,
        crop_uncertain=crop_uncertain,
        debug_paths=debug_paths,
        extracted_text=extracted_text,
    )


def _detect_prompt_regions(
    span: QuestionSpan,
    layouts: list[PageLayout],
    config: AppConfig,
) -> tuple[list[CropRegion], list[str]]:
    regions: list[CropRegion] = []
    flags: list[str] = []

    for page_number in span.page_numbers:
        layout = _layout_by_number(layouts, page_number)
        blocks = [
            block
            for block in span.blocks
            if block.page_number == page_number and _is_prompt_text_block(block, span, layout, config)
        ]
        if not blocks:
            continue

        segments = _split_prompt_segments(blocks, config)
        if len(segments) > 1:
            flags.append("crop_split_prompt_regions")

        for segment in segments:
            text_box = _union_boxes([block.bbox for block in segment])
            graphics = _graphics_for_segment(text_box, layout, config)
            boxes = [text_box] + graphics
            crop_box = _union_boxes(boxes).padded(config.detection.crop_padding, layout.width, layout.height)
            crop_box = _clamp_crop_to_prompt_area(crop_box, layout, config)
            if _box_height(crop_box) < config.detection.min_crop_height:
                flags.append("crop_uncertain")
            regions.append(CropRegion(page_number=page_number, bbox=crop_box, text_blocks=segment, graphics=graphics))

    return regions, sorted(set(flags))


def _split_prompt_segments(blocks: list[TextBlock], config: AppConfig) -> list[list[TextBlock]]:
    sorted_blocks = sorted(blocks, key=lambda item: (item.bbox.y0, item.bbox.x0))
    if not sorted_blocks:
        return []

    segments: list[list[TextBlock]] = [[sorted_blocks[0]]]
    previous = sorted_blocks[0]
    for block in sorted_blocks[1:]:
        gap = block.bbox.y0 - previous.bbox.y1
        if gap > config.detection.prompt_region_max_gap:
            segments.append([block])
        else:
            segments[-1].append(block)
        previous = block
    return segments


def _graphics_for_segment(text_box: BoundingBox, layout: PageLayout, config: AppConfig) -> list[BoundingBox]:
    graphics: list[BoundingBox] = []
    top = text_box.y0 - config.detection.prompt_graphic_overlap_padding
    bottom = text_box.y1 + config.detection.prompt_graphic_lookahead
    answer_rule_bands = _answer_rule_y_bands(layout)
    for graphic in layout.graphics:
        if _is_footer_or_header_box(graphic, layout, config):
            continue
        if _is_answer_rule_like(graphic, layout) or _is_in_answer_rule_band(graphic, answer_rule_bands):
            continue
        overlaps_vertically = graphic.y1 >= top and graphic.y0 <= bottom
        overlaps_horizontally = graphic.x1 >= text_box.x0 - 30 and graphic.x0 <= text_box.x1 + 30
        graphic_width = graphic.x1 - graphic.x0
        graphic_height = graphic.y1 - graphic.y0
        significant_nearby_graphic = graphic_width >= 20 and graphic_height >= 20
        if overlaps_vertically and (overlaps_horizontally or significant_nearby_graphic):
            graphics.append(graphic)
    return graphics


def _is_prompt_text_block(block: TextBlock, span: QuestionSpan, layout: PageLayout, config: AppConfig) -> bool:
    text = _clean_text_line(block.text)
    if not text:
        return False
    if _is_footer_or_header_box(block.bbox, layout, config):
        return False
    if _is_boilerplate_text(text):
        return False
    if _is_answer_space_text(text):
        return False

    parsed = parse_question_start(text, config)
    if parsed and parsed[0] != span.question_number:
        return False

    # Lone page numbers and administrative codes should not set crop bounds.
    if text.isdigit() and (block.bbox.y0 < config.detection.crop_top_margin or block.bbox.y1 > layout.height - config.detection.bottom_margin):
        return False
    return True


def _fallback_regions(span: QuestionSpan, layouts: list[PageLayout], config: AppConfig) -> list[CropRegion]:
    regions: list[CropRegion] = []
    for page_number in span.page_numbers:
        layout = _layout_by_number(layouts, page_number)
        top = span.start_y if page_number == span.start_page else config.detection.crop_top_margin
        bottom = span.end_y if page_number == span.end_page else layout.height - config.detection.crop_bottom_margin
        bbox = BoundingBox(
            config.detection.crop_left_margin,
            max(config.detection.crop_top_margin, top),
            layout.width - config.detection.crop_right_margin,
            min(layout.height - config.detection.crop_bottom_margin, bottom),
        )
        if bbox.y1 > bbox.y0:
            regions.append(CropRegion(page_number=page_number, bbox=bbox))
    return regions


def _render_full_region_image(
    pdf_path: str | Path,
    span: QuestionSpan,
    layouts: list[PageLayout],
    config: AppConfig,
) -> RenderResult:
    """Render the full exam question region for debugging."""

    try:
        import fitz
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("PyMuPDF and Pillow are required for rendering screenshots.") from exc

    output_path = _image_output_path(span, config)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    zoom = config.detection.render_dpi / 72
    matrix = fitz.Matrix(zoom, zoom)
    images: list[Image.Image] = []
    regions: list[CropRegion] = []
    debug_paths: list[str] = []

    with fitz.open(pdf_path) as doc:
        rendered_pages = {}
        for page_number in span.page_numbers:
            layout = _layout_by_number(layouts, page_number)
            crop = _full_region_crop_for_page(layout, span, config)
            if crop is None:
                continue
            regions.append(CropRegion(page_number=page_number, bbox=crop, text_blocks=[block for block in span.blocks if block.page_number == page_number]))
            page = doc[page_number - 1]
            if page_number not in rendered_pages:
                pix_full = page.get_pixmap(matrix=matrix, alpha=False)
                rendered_pages[page_number] = Image.open(BytesIO(pix_full.tobytes("png"))).convert("RGB")
                if config.debug.enabled and config.debug.save_rendered_pages:
                    debug_paths.append(_save_debug_image(rendered_pages[page_number], span, page_number, "rendered", config))
            rect = fitz.Rect(crop.x0, crop.y0, crop.x1, crop.y1)
            pix = page.get_pixmap(matrix=matrix, clip=rect, alpha=False)
            images.append(Image.open(BytesIO(pix.tobytes("png"))).convert("RGB"))

        if config.debug.enabled:
            debug_paths.extend(_write_debug_overlays(rendered_pages, span, layouts, regions, zoom, config))

    if not images:
        return RenderResult(output_path, ["crop_fallback_failed", "crop_uncertain"], crop_uncertain=True)

    _stitch_images(images, config.detection.stitch_gap_px).save(output_path)
    if config.debug.enabled:
        debug_paths.append(_write_crop_metadata(span, regions, ["full_region_mode"], config))
    return RenderResult(output_path, debug_paths=debug_paths, extracted_text=span.combined_text)


def _full_region_crop_for_page(layout: PageLayout, span: QuestionSpan, config: AppConfig) -> BoundingBox | None:
    padding = config.detection.crop_padding
    top = span.start_y - padding if layout.page_number == span.start_page else config.detection.crop_top_margin
    bottom = span.end_y + padding if layout.page_number == span.end_page else layout.height - config.detection.crop_bottom_margin
    top = max(config.detection.crop_top_margin, top)
    bottom = min(layout.height - config.detection.crop_bottom_margin, bottom)
    if bottom <= top + 4:
        return None
    return BoundingBox(
        config.detection.crop_left_margin,
        top,
        max(config.detection.crop_left_margin + 20, layout.width - config.detection.crop_right_margin),
        bottom,
    )


def _write_debug_overlays(
    rendered_pages: dict[int, "Image.Image"],
    span: QuestionSpan,
    layouts: list[PageLayout],
    regions: list[CropRegion],
    zoom: float,
    config: AppConfig,
) -> list[str]:
    from PIL import ImageDraw

    paths: list[str] = []
    for page_number, page_image in rendered_pages.items():
        layout = _layout_by_number(layouts, page_number)
        anchors = [
            anchor
            for anchor in detect_question_anchor_candidates([layout], config)
            if anchor.bbox is not None
        ]
        proposed = _proposed_region_for_page(layout, span, config)

        if config.debug.save_anchor_candidates:
            image = page_image.copy()
            draw = ImageDraw.Draw(image)
            for anchor in anchors:
                draw.rectangle(_pdf_box_to_pixel_box(anchor.bbox, zoom, image.size), outline="orange", width=4)
            paths.append(_save_debug_image(image, span, page_number, "anchor_candidates", config))

        if config.debug.save_text_boxes:
            image = page_image.copy()
            draw = ImageDraw.Draw(image)
            included = {
                (block.page_number, round(block.bbox.x0, 2), round(block.bbox.y0, 2), round(block.bbox.x1, 2), round(block.bbox.y1, 2))
                for region in regions
                if region.page_number == page_number
                for block in region.text_blocks
            }
            for block in layout.blocks:
                key = (block.page_number, round(block.bbox.x0, 2), round(block.bbox.y0, 2), round(block.bbox.x1, 2), round(block.bbox.y1, 2))
                color = "lime" if key in included else "dodgerblue"
                draw.rectangle(_pdf_box_to_pixel_box(block.bbox, zoom, image.size), outline=color, width=3 if key in included else 1)
            for anchor in anchors:
                draw.rectangle(_pdf_box_to_pixel_box(anchor.bbox, zoom, image.size), outline="orange", width=4)
            paths.append(_save_debug_image(image, span, page_number, "text_boxes", config))

        if config.debug.save_proposed_boxes and proposed is not None:
            image = page_image.copy()
            draw = ImageDraw.Draw(image)
            draw.rectangle(_pdf_box_to_pixel_box(proposed, zoom, image.size), outline="cyan", width=5)
            for anchor in anchors:
                draw.rectangle(_pdf_box_to_pixel_box(anchor.bbox, zoom, image.size), outline="orange", width=4)
            paths.append(_save_debug_image(image, span, page_number, "proposed_boxes", config))

        if config.debug.save_crop_boxes:
            image = page_image.copy()
            draw = ImageDraw.Draw(image)
            for region in [region for region in regions if region.page_number == page_number]:
                draw.rectangle(_pdf_box_to_pixel_box(region.bbox, zoom, image.size), outline="magenta", width=5)
            for anchor in anchors:
                draw.rectangle(_pdf_box_to_pixel_box(anchor.bbox, zoom, image.size), outline="orange", width=4)
            paths.append(_save_debug_image(image, span, page_number, "crop_boxes", config))
    return paths


def _write_crop_metadata(span: QuestionSpan, regions: list[CropRegion], flags: list[str], config: AppConfig) -> str:
    path = _debug_path(span, "crop_boxes", config, suffix=".json")
    payload = {
        "paper_name": span.paper_name,
        "question_number": span.question_number,
        "flags": sorted(set(flags)),
        "regions": [
            {
                "page_number": region.page_number,
                "bbox_pdf_points": {
                    "x0": round(region.bbox.x0, 2),
                    "y0": round(region.bbox.y0, 2),
                    "x1": round(region.bbox.x1, 2),
                    "y1": round(region.bbox.y1, 2),
                },
                "text_blocks": [block.text for block in region.text_blocks],
                "graphics_count": len(region.graphics),
            }
            for region in regions
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return _display_path(path)


def _save_debug_image(image: "Image.Image", span: QuestionSpan, page_number: int, kind: str, config: AppConfig) -> str:
    path = _debug_path(span, f"p{page_number:02d}_{kind}", config)
    image.save(path)
    return _display_path(path)


def _debug_path(span: QuestionSpan, kind: str, config: AppConfig, suffix: str = ".png") -> Path:
    config.output.debug_dir.mkdir(parents=True, exist_ok=True)
    if span.question_number.isdigit():
        qid = f"q{int(span.question_number):02d}"
    else:
        qid = f"q{span.question_number}"
    return config.output.debug_dir / f"{span.paper_name}_{qid}_{kind}{suffix}"


def _proposed_region_for_page(layout: PageLayout, span: QuestionSpan, config: AppConfig) -> BoundingBox | None:
    if layout.page_number not in span.page_numbers:
        return None
    top = span.start_y if layout.page_number == span.start_page else config.detection.crop_top_margin
    bottom = span.end_y if layout.page_number == span.end_page else layout.height - config.detection.crop_bottom_margin
    if bottom <= top:
        return None
    return BoundingBox(
        config.detection.crop_left_margin,
        max(config.detection.crop_top_margin, top),
        layout.width - config.detection.crop_right_margin,
        min(layout.height - config.detection.bottom_margin, bottom),
    )


def _pdf_box_to_pixel_box(box: BoundingBox, zoom: float, image_size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = image_size
    left = max(0, min(width - 1, int(box.x0 * zoom)))
    top = max(0, min(height - 1, int(box.y0 * zoom)))
    right = max(left + 1, min(width, int(box.x1 * zoom)))
    bottom = max(top + 1, min(height, int(box.y1 * zoom)))
    return (left, top, right, bottom)


def _clamp_crop_to_prompt_area(box: BoundingBox, layout: PageLayout, config: AppConfig) -> BoundingBox:
    return BoundingBox(
        max(0, box.x0),
        max(config.detection.crop_top_margin, box.y0),
        min(layout.width, box.x1),
        min(layout.height - config.detection.bottom_margin, box.y1),
    )


def _union_boxes(boxes: list[BoundingBox]) -> BoundingBox:
    return BoundingBox(
        min(box.x0 for box in boxes),
        min(box.y0 for box in boxes),
        max(box.x1 for box in boxes),
        max(box.y1 for box in boxes),
    )


def _is_footer_or_header_box(box: BoundingBox, layout: PageLayout, config: AppConfig) -> bool:
    return box.y1 < config.detection.crop_top_margin or box.y0 > layout.height - config.detection.bottom_margin


def _is_answer_rule_like(box: BoundingBox, layout: PageLayout) -> bool:
    width = max(0.0, box.x1 - box.x0)
    height = max(0.0, box.y1 - box.y0)
    return height <= 2.5 and width >= layout.width * 0.28


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


def _is_in_answer_rule_band(box: BoundingBox, bands: list[float]) -> bool:
    if not bands:
        return False
    y_mid = (box.y0 + box.y1) / 2
    return any(abs(y_mid - band) <= 2.5 for band in bands)


def _is_boilerplate_text(text: str) -> bool:
    patterns = [
        r"^©\s*UCLES\b",
        r"^UCLES\b",
        r"^\d{4}/\d{2}/[A-Z]/[A-Z]/\d{2}$",
        r"^9709[/_ -]",
        r"^Cambridge International",
        r"^This document consists of",
        r"^BLANK PAGE$",
        r"^Question Paper$",
        r"^Mark Scheme$",
        r"^Turn over$",
    ]
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _is_answer_space_text(text: str) -> bool:
    if re.fullmatch(r"[._\-–—\s]{6,}", text):
        return True
    if re.fullmatch(r"(?:\.\s*){6,}", text):
        return True
    return bool(re.search(r"\bAnswer\b\s*[._\-–—]{6,}", text, re.IGNORECASE))


def _text_from_regions(regions: list[CropRegion]) -> str:
    blocks: list[TextBlock] = []
    for region in regions:
        blocks.extend(region.text_blocks)
    return extract_text_from_blocks(blocks)


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


def _image_output_path(span: QuestionSpan, config: AppConfig) -> Path:
    if span.question_number.isdigit():
        filename = config.naming.image_template.format(
            paper_name=span.paper_name,
            question_number=int(span.question_number),
            question_number_raw=span.question_number,
        )
    else:
        filename = f"{span.paper_name}_q{span.question_number}.png"
    return config.output.images_dir / filename


def _layout_by_number(layouts: list[PageLayout], page_number: int) -> PageLayout:
    for layout in layouts:
        if layout.page_number == page_number:
            return layout
    raise ValueError(f"No layout for page {page_number}")


def _box_height(box: BoundingBox) -> float:
    return max(0.0, box.y1 - box.y0)


def _clean_text_line(text: str) -> str:
    return " ".join(text.replace("\u00a0", " ").split())


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)
