from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import re

from .config import AppConfig
from .image_limits import cap_image_pixels, render_pdf_area
from .models import BoundingBox, PageLayout, QuestionSpan, RenderResult, TextBlock
from .mupdf_tools import quiet_mupdf
from .question_detection import detect_question_anchor_candidates, extract_text_from_blocks, parse_question_start


@dataclass
class CropRegion:
    page_number: int
    bbox: BoundingBox
    text_blocks: list[TextBlock] = field(default_factory=list)
    graphics: list[BoundingBox] = field(default_factory=list)
    duplicate_graphics_removed: int = 0
    original_bbox: BoundingBox | None = None
    excluded_regions: list[dict[str, object]] = field(default_factory=list)


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
    quiet_mupdf(fitz)

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

    crops = []
    debug_paths: list[str] = []

    with fitz.open(pdf_path) as doc:
        rendered_pages = {}
        for region in regions:
            page = doc[region.page_number - 1]
            rect = fitz.Rect(region.bbox.x0, region.bbox.y0, region.bbox.x1, region.bbox.y1)
            crop, used_zoom = render_pdf_area(
                page,
                fitz,
                dpi=config.detection.render_dpi,
                source_file=pdf_path,
                page_number=region.page_number,
                context=f"question_crop:{span.question_number}",
                clip=rect,
            )
            crops.append(crop)

            if config.debug.enabled and region.page_number not in rendered_pages:
                page_image, page_zoom = render_pdf_area(
                    page,
                    fitz,
                    dpi=config.detection.render_dpi,
                    source_file=pdf_path,
                    page_number=region.page_number,
                    context=f"question_debug_page:{span.question_number}",
                )
                rendered_pages[region.page_number] = (page_image, page_zoom)
                if config.debug.save_rendered_pages:
                    debug_paths.append(_save_debug_image(page_image, span, region.page_number, "rendered", config))

            layout = _layout_by_number(layouts, region.page_number)
            if _box_height(region.bbox) > layout.height * config.detection.max_crop_height_ratio:
                flags.extend(["crop_reaches_page_margin", "crop_uncertain"])
                crop_uncertain = True

            if used_zoom * 72 < config.detection.render_dpi * 0.8:
                flags.append("render_dpi_capped")

        if config.debug.enabled:
            debug_paths.extend(_write_debug_overlays(rendered_pages, span, layouts, regions, config))

    if not crops:
        raise RuntimeError(f"No crops could be rendered for {span.paper_name} question {span.question_number}.")

    stitched = cap_image_pixels(
        _stitch_images(crops, config.detection.stitch_gap_px),
        source_file=pdf_path,
        context=f"question_output:{span.question_number}",
    )
    stitched.save(output_path)

    if config.debug.enabled:
        debug_paths.append(_write_crop_metadata(span, regions, flags, config))

    crop_uncertain = crop_uncertain or "crop_uncertain" in flags
    extracted_text = _text_from_regions(regions) or span.combined_text
    flags = sorted(set(flags))
    crop_diagnostics = _crop_diagnostics(pdf_path, span, regions, flags)
    return RenderResult(
        screenshot_path=output_path,
        review_flags=flags,
        crop_uncertain=crop_uncertain,
        debug_paths=debug_paths,
        extracted_text=extracted_text,
        crop_diagnostics=crop_diagnostics,
    )


def _detect_prompt_regions(
    span: QuestionSpan,
    layouts: list[PageLayout],
    config: AppConfig,
) -> tuple[list[CropRegion], list[str]]:
    regions: list[CropRegion] = []
    flags: list[str] = []
    seen_graphics: dict[int, list[BoundingBox]] = {}

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
            raw_graphics, excluded_regions = _graphics_for_segment(text_box, layout, config)
            for excluded in excluded_regions:
                reason = str(excluded.get("label") or "")
                if reason:
                    flags.append(f"{reason}_excluded")
            graphics, duplicate_count = _dedupe_graphics(raw_graphics, seen_graphics.setdefault(page_number, []))
            if duplicate_count:
                flags.append("duplicate_visual_regions_removed")
                flags.append("duplicate_visual_fragment_excluded")
            boxes = [text_box] + graphics
            original_box = _union_boxes(boxes).padded(config.detection.crop_padding, layout.width, layout.height)
            crop_box = _clamp_crop_to_prompt_area(original_box, layout, config)
            crop_box = _trim_crop_furniture_edges(crop_box, layout, config)
            if _box_height(crop_box) < config.detection.min_crop_height:
                flags.append("crop_uncertain")
            regions.append(
                CropRegion(
                    page_number=page_number,
                    bbox=crop_box,
                    text_blocks=segment,
                    graphics=graphics,
                    duplicate_graphics_removed=duplicate_count,
                    original_bbox=original_box,
                    excluded_regions=excluded_regions,
                )
            )

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


def _graphics_for_segment(text_box: BoundingBox, layout: PageLayout, config: AppConfig) -> tuple[list[BoundingBox], list[dict[str, object]]]:
    graphics: list[BoundingBox] = []
    excluded_regions: list[dict[str, object]] = []
    top = text_box.y0 - config.detection.prompt_graphic_overlap_padding
    bottom = text_box.y1 + config.detection.prompt_graphic_lookahead
    answer_rule_bands = _answer_rule_y_bands(layout)
    for graphic in layout.graphics:
        furniture_label = _page_furniture_box_label(graphic, layout, config, answer_rule_bands)
        if furniture_label:
            excluded_regions.append(_excluded_region(furniture_label, graphic))
            continue
        overlaps_vertically = graphic.y1 >= top and graphic.y0 <= bottom
        overlaps_horizontally = graphic.x1 >= text_box.x0 - 30 and graphic.x0 <= text_box.x1 + 30
        graphic_width = graphic.x1 - graphic.x0
        graphic_height = graphic.y1 - graphic.y0
        significant_nearby_graphic = graphic_width >= 20 and graphic_height >= 20
        if overlaps_vertically and (overlaps_horizontally or significant_nearby_graphic):
            graphics.append(graphic)
    return graphics, excluded_regions


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
    if _is_margin_furniture_text(block, layout, config):
        return False
    if _is_control_artifact_text(text):
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
    quiet_mupdf(fitz)

    output_path = _image_output_path(span, config)
    output_path.parent.mkdir(parents=True, exist_ok=True)
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
            rect = fitz.Rect(crop.x0, crop.y0, crop.x1, crop.y1)
            image, used_zoom = render_pdf_area(
                page,
                fitz,
                dpi=config.detection.render_dpi,
                source_file=pdf_path,
                page_number=page_number,
                context=f"question_full_region:{span.question_number}",
                clip=rect,
            )
            images.append(image)
            if config.debug.enabled and page_number not in rendered_pages:
                page_image, page_zoom = render_pdf_area(
                    page,
                    fitz,
                    dpi=config.detection.render_dpi,
                    source_file=pdf_path,
                    page_number=page_number,
                    context=f"question_debug_page:{span.question_number}",
                )
                rendered_pages[page_number] = (page_image, page_zoom)
                if config.debug.save_rendered_pages:
                    debug_paths.append(_save_debug_image(page_image, span, page_number, "rendered", config))

        if config.debug.enabled:
            debug_paths.extend(_write_debug_overlays(rendered_pages, span, layouts, regions, config))

    if not images:
        return RenderResult(output_path, ["crop_fallback_failed", "crop_uncertain"], crop_uncertain=True)

    stitched = cap_image_pixels(
        _stitch_images(images, config.detection.stitch_gap_px),
        source_file=pdf_path,
        context=f"question_full_region_output:{span.question_number}",
    )
    stitched.save(output_path)
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
    rendered_pages: dict[int, tuple["Image.Image", float]],
    span: QuestionSpan,
    layouts: list[PageLayout],
    regions: list[CropRegion],
    config: AppConfig,
) -> list[str]:
    from PIL import ImageDraw

    paths: list[str] = []
    for page_number, (page_image, zoom) in rendered_pages.items():
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
                "original_bbox_pdf_points": _box_payload(region.original_bbox or region.bbox),
                "text_blocks": [block.text for block in region.text_blocks],
                "merged_blocks": len(region.text_blocks),
                "graphics_count": len(region.graphics),
                "duplicate_graphics_removed": region.duplicate_graphics_removed,
                "excluded_regions": region.excluded_regions,
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


def _trim_crop_furniture_edges(box: BoundingBox, layout: PageLayout, config: AppConfig) -> BoundingBox:
    return BoundingBox(
        max(box.x0, config.detection.crop_left_margin),
        box.y0,
        min(box.x1, layout.width - config.detection.crop_right_margin),
        box.y1,
    )


def _union_boxes(boxes: list[BoundingBox]) -> BoundingBox:
    return BoundingBox(
        min(box.x0 for box in boxes),
        min(box.y0 for box in boxes),
        max(box.x1 for box in boxes),
        max(box.y1 for box in boxes),
    )


def _dedupe_graphics(boxes: list[BoundingBox], seen: list[BoundingBox]) -> tuple[list[BoundingBox], int]:
    kept: list[BoundingBox] = []
    removed = 0
    for box in sorted(boxes, key=lambda item: (_box_area(item), item.y0, item.x0), reverse=True):
        if any(_boxes_duplicate(box, other) for other in kept) or any(_boxes_duplicate(box, other) for other in seen):
            removed += 1
            continue
        kept.append(box)
        seen.append(box)
    return sorted(kept, key=lambda item: (item.y0, item.x0)), removed


def _boxes_duplicate(a: BoundingBox, b: BoundingBox) -> bool:
    if _intersection_area(a, b) / max(1.0, min(_box_area(a), _box_area(b))) >= 0.88:
        return True
    smaller = min(_box_area(a), _box_area(b))
    larger = max(_box_area(a), _box_area(b))
    if smaller > 0 and smaller <= larger * 0.35 and _intersection_area(a, b) / smaller >= 0.65:
        return True
    return (
        abs(a.x0 - b.x0) <= 3
        and abs(a.y0 - b.y0) <= 3
        and abs(a.x1 - b.x1) <= 3
        and abs(a.y1 - b.y1) <= 3
    )


def _intersection_area(a: BoundingBox, b: BoundingBox) -> float:
    width = max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))
    height = max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))
    return width * height


def _box_area(box: BoundingBox) -> float:
    return max(0.0, box.x1 - box.x0) * max(0.0, box.y1 - box.y0)


def _is_footer_or_header_box(box: BoundingBox, layout: PageLayout, config: AppConfig) -> bool:
    return box.y1 < config.detection.crop_top_margin or box.y0 > layout.height - config.detection.bottom_margin


def _page_furniture_box_label(
    box: BoundingBox,
    layout: PageLayout,
    config: AppConfig,
    answer_rule_bands: list[float],
) -> str | None:
    if _is_footer_or_header_box(box, layout, config):
        return "header_footer"
    if _is_answer_rule_like(box, layout) or _is_in_answer_rule_band(box, answer_rule_bands):
        return "answer_lines"
    if _is_side_panel_box(box, layout, config):
        return "side_panel"
    if _is_barcode_like_box(box, layout, config):
        return "barcode"
    if _is_scan_edge_box(box, layout):
        return "scan_edge"
    return None


def _is_side_panel_box(box: BoundingBox, layout: PageLayout, config: AppConfig) -> bool:
    width = max(0.0, box.x1 - box.x0)
    height = max(0.0, box.y1 - box.y0)
    near_left = box.x0 <= config.detection.crop_left_margin * 0.8
    near_right = box.x1 >= layout.width - config.detection.crop_right_margin * 0.8
    return width <= 55 and height >= layout.height * 0.16 and (near_left or near_right)


def _is_barcode_like_box(box: BoundingBox, layout: PageLayout, config: AppConfig) -> bool:
    width = max(0.0, box.x1 - box.x0)
    height = max(0.0, box.y1 - box.y0)
    return box.y0 <= config.detection.crop_top_margin + 70 and height <= 90 and 20 <= width <= layout.width * 0.45


def _is_scan_edge_box(box: BoundingBox, layout: PageLayout) -> bool:
    width = max(0.0, box.x1 - box.x0)
    height = max(0.0, box.y1 - box.y0)
    near_edge = box.x0 <= 4 or box.x1 >= layout.width - 4 or box.y0 <= 4 or box.y1 >= layout.height - 4
    return near_edge and (width <= 8 or height <= 8)


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
        r"^Additional Page\b",
        r"If you use the following lined page",
        r"write the question number",
        r"^©\s*UCLES\b",
        r"^UCLES\b",
        r"^\d{4}/\d{2}/[A-Z]/[A-Z]/\d{2}$",
        r"^9709[/_ -]",
        r"^Cambridge International",
        r"DO NOT WRITE IN THIS MARGIN",
        r"^This document consists of",
        r"^BLANK PAGE$",
        r"^Question Paper$",
        r"^Mark Scheme$",
        r"^Turn over$",
    ]
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _is_margin_furniture_text(block: TextBlock, layout: PageLayout, config: AppConfig) -> bool:
    text = _clean_text_line(block.text)
    if re.search(r"DO NOT WRITE IN THIS MARGIN", text, re.IGNORECASE):
        return True
    narrow_edge = (block.bbox.x1 - block.bbox.x0) <= 70 and (
        block.bbox.x0 <= config.detection.crop_left_margin or block.bbox.x1 >= layout.width - config.detection.crop_right_margin
    )
    tall = (block.bbox.y1 - block.bbox.y0) >= 80
    return narrow_edge and tall


def _is_control_artifact_text(text: str) -> bool:
    if not text:
        return False
    control_count = sum(1 for char in text if ord(char) < 32 and char not in "\n\t\r")
    return control_count >= 2 or (control_count >= 1 and len(text.strip()) <= 6)


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


def _crop_diagnostics(
    pdf_path: str | Path,
    span: QuestionSpan,
    regions: list[CropRegion],
    flags: list[str],
) -> dict[str, object]:
    return {
        "source_file": str(pdf_path),
        "question_id": span.question_number,
        "flags": sorted(set(flags)),
        "merged_blocks": sum(len(region.text_blocks) for region in regions),
        "duplicate_visual_blocks_removed": sum(region.duplicate_graphics_removed for region in regions),
        "excluded_boilerplate_reasons": sorted(flag.replace("excluded_boilerplate_", "") for flag in flags if flag.startswith("excluded_boilerplate_")),
        "regions": [
            {
                "page_number": region.page_number,
                "original_crop_bbox": _box_payload(region.original_bbox or region.bbox),
                "final_crop_bbox": {
                    "x0": round(region.bbox.x0, 2),
                    "y0": round(region.bbox.y0, 2),
                    "x1": round(region.bbox.x1, 2),
                    "y1": round(region.bbox.y1, 2),
                },
                "merged_blocks": len(region.text_blocks),
                "graphics_count": len(region.graphics),
                "duplicate_visual_blocks_removed": region.duplicate_graphics_removed,
                "excluded_regions": region.excluded_regions,
            }
            for region in regions
        ],
    }


def _excluded_region(label: str, box: BoundingBox) -> dict[str, object]:
    return {"label": label, "bbox": _box_payload(box)}


def _box_payload(box: BoundingBox) -> dict[str, float]:
    return {
        "x0": round(box.x0, 2),
        "y0": round(box.y0, 2),
        "x1": round(box.x1, 2),
        "y1": round(box.y1, 2),
    }


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
