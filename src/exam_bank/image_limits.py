from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any


SAFE_RENDER_PIXELS = 40_000_000
SAFE_PROBE_PIXELS = 80_000_000


def render_pdf_area(
    page: Any,
    fitz: Any,
    *,
    dpi: int,
    source_file: str | Path,
    page_number: int,
    context: str,
    clip: Any | None = None,
    max_pixels: int = SAFE_RENDER_PIXELS,
) -> tuple[Any, float]:
    """Render a PDF page or clip while capping oversized rasters."""

    rect = clip if clip is not None else page.rect
    width_pt = max(1.0, float(rect.width))
    height_pt = max(1.0, float(rect.height))
    requested_zoom = dpi / 72
    zoom = _safe_zoom(width_pt, height_pt, requested_zoom, max_pixels)
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix, clip=clip, alpha=False)
    rendered_pixels = int(pix.width) * int(pix.height)
    if zoom < requested_zoom or rendered_pixels > max_pixels:
        logging.warning(
            "large_render_capped source=%s page=%s context=%s rendered=%sx%s requested_dpi=%s used_dpi=%.1f",
            source_file,
            page_number,
            context,
            pix.width,
            pix.height,
            dpi,
            zoom * 72,
        )
    return pixmap_to_image(pix), zoom


def pixmap_to_image(pix: Any) -> Any:
    """Convert a PyMuPDF pixmap without round-tripping through PNG decoding."""

    from PIL import Image

    size = (int(pix.width), int(pix.height))
    if pix.alpha:
        return Image.frombytes("RGBA", size, pix.samples).convert("RGB")
    if pix.n == 1:
        return Image.frombytes("L", size, pix.samples).convert("RGB")
    if pix.n == 3:
        return Image.frombytes("RGB", size, pix.samples)
    if pix.n == 4:
        return Image.frombytes("CMYK", size, pix.samples).convert("RGB")
    return Image.frombytes("RGB", size, pix.samples)


def cap_image_pixels(
    image: Any,
    *,
    source_file: str | Path,
    context: str,
    max_pixels: int = SAFE_RENDER_PIXELS,
) -> Any:
    pixels = int(image.width) * int(image.height)
    if pixels <= max_pixels:
        return image
    scale = math.sqrt(max_pixels / pixels)
    new_size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
    logging.warning(
        "large_output_image_downscaled source=%s context=%s original=%sx%s output=%sx%s",
        source_file,
        context,
        image.width,
        image.height,
        new_size[0],
        new_size[1],
    )
    from PIL import Image

    return image.resize(new_size, Image.Resampling.LANCZOS)


def _safe_zoom(width_pt: float, height_pt: float, requested_zoom: float, max_pixels: int) -> float:
    requested_pixels = width_pt * requested_zoom * height_pt * requested_zoom
    if requested_pixels <= max_pixels:
        return requested_zoom
    return max(0.1, math.sqrt(max_pixels / (width_pt * height_pt)))
