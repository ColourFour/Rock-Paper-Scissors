from exam_bank.image_limits import SAFE_RENDER_PIXELS, _safe_zoom, cap_image_pixels


def test_safe_zoom_keeps_normal_a4_render_dpi() -> None:
    requested_zoom = 220 / 72

    assert _safe_zoom(595, 842, requested_zoom, SAFE_RENDER_PIXELS) == requested_zoom


def test_safe_zoom_caps_oversized_page_render() -> None:
    requested_zoom = 220 / 72
    zoom = _safe_zoom(4000, 4000, requested_zoom, SAFE_RENDER_PIXELS)

    assert zoom < requested_zoom
    assert int(4000 * zoom) * int(4000 * zoom) <= SAFE_RENDER_PIXELS


def test_cap_image_pixels_downscales_large_output() -> None:
    from PIL import Image

    image = Image.new("RGB", (4000, 4000), "white")
    capped = cap_image_pixels(image, source_file="paper.pdf", context="test", max_pixels=4_000_000)

    assert capped.width * capped.height <= 4_000_000
