from pathlib import Path

from exam_bank.config import AppConfig
from exam_bank.image_rendering import (
    CropRegion,
    _dedupe_crop_regions,
    _graphics_for_segment,
    _same_page_diagram_union_regions,
    _single_page_union_regions,
)
from exam_bank.models import BoundingBox, PageLayout, QuestionSpan, TextBlock


def text_block(text: str, y: float, x: float = 50, width: float = 450) -> TextBlock:
    return TextBlock(page_number=1, text=text, bbox=BoundingBox(x, y, x + width, y + 14))


def span() -> QuestionSpan:
    return QuestionSpan(
        source_pdf=Path("9709_m24_qp_12.pdf"),
        paper_name="9709_m24_qp_12",
        question_number="10",
        start_page=1,
        start_y=60,
        end_page=1,
        end_y=500,
        page_numbers=[1],
        blocks=[],
        full_question_label="10",
    )


def test_formula_rule_graphics_do_not_create_diagram_regions() -> None:
    config = AppConfig()
    text_box = BoundingBox(50, 280, 545, 315)
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[],
        graphics=[
            BoundingBox(150, 300, 235, 300.5),
            BoundingBox(250, 330, 350, 440),
            BoundingBox(145, 80, 230, 80.5),
        ],
    )

    graphics, excluded = _graphics_for_segment(text_box, layout, config)

    assert BoundingBox(150, 300, 235, 300.5) not in graphics
    assert BoundingBox(250, 330, 350, 440) in graphics
    assert {"label": "barcode", "bbox": {"x0": 145, "y0": 80, "x1": 230, "y1": 80.5}} in excluded


def test_page_diagram_union_does_not_cross_large_answer_gap() -> None:
    config = AppConfig()
    layout = PageLayout(page_number=1, width=595, height=842, blocks=[])
    regions = [
        CropRegion(page_number=1, bbox=BoundingBox(40, 55, 300, 90), text_blocks=[text_block("10", 65)], region_kind="text"),
        CropRegion(
            page_number=1,
            bbox=BoundingBox(80, 90, 360, 250),
            graphics=[BoundingBox(100, 100, 340, 230)],
            region_kind="figure",
        ),
        CropRegion(page_number=1, bbox=BoundingBox(70, 255, 555, 360), text_blocks=[text_block("(a) Find the tangent. [3]", 265)], region_kind="text"),
        CropRegion(page_number=1, bbox=BoundingBox(70, 560, 555, 600), text_blocks=[text_block("(b) Find the circle. [2]", 570)], region_kind="text"),
    ]

    merged, flags = _same_page_diagram_union_regions(regions, span(), [layout], config)

    assert [region.region_kind for region in merged] == ["page_diagram_union", "text"]
    assert merged[0].bbox.y1 < 380
    assert merged[1].bbox.y0 == 560
    assert "page_diagram_union_used" in flags


def test_crop_region_dedupe_removes_stale_duplicate_fragment() -> None:
    regions = [
        CropRegion(
            page_number=1,
            bbox=BoundingBox(60, 120, 520, 360),
            text_blocks=[text_block("10 (a) Full prompt", 130), text_block("(b) Continuation", 310)],
            region_kind="page_diagram_union",
        ),
        CropRegion(
            page_number=1,
            bbox=BoundingBox(65, 125, 500, 210),
            text_blocks=[text_block("10 (a) Full prompt", 130)],
            region_kind="text",
        ),
    ]

    deduped, flags = _dedupe_crop_regions(regions)

    assert len(deduped) == 1
    assert deduped[0].region_kind == "page_diagram_union"
    assert "stale_crop_fragment_removed" in flags


def test_single_page_union_skips_disjoint_text_tail_and_allows_page_union() -> None:
    config = AppConfig()
    layout = PageLayout(page_number=1, width=595, height=842, blocks=[])
    regions = [
        CropRegion(page_number=1, bbox=BoundingBox(40, 55, 300, 90), text_blocks=[text_block("2", 65)], region_kind="text"),
        CropRegion(
            page_number=1,
            bbox=BoundingBox(80, 90, 520, 250),
            graphics=[BoundingBox(100, 100, 500, 230)],
            text_blocks=[text_block("axis", 95)],
            region_kind="figure",
            excluded_regions=[
                {"label": "barcode", "bbox": {"x0": 140, "y0": 80, "x1": 200, "y1": 110}},
                {"label": "barcode", "bbox": {"x0": 140, "y0": 80, "x1": 200, "y1": 110}},
            ],
        ),
        CropRegion(page_number=1, bbox=BoundingBox(60, 260, 555, 360), text_blocks=[text_block("(a) Describe the graph. [4]", 270)], region_kind="text"),
        CropRegion(page_number=1, bbox=BoundingBox(60, 550, 555, 585), text_blocks=[text_block("(b) Find f(x). [2]", 560)], region_kind="text"),
    ]

    union_regions, union_flags = _single_page_union_regions(regions, span(), [layout], config)
    page_regions, page_flags = _same_page_diagram_union_regions(regions, span(), [layout], config)

    assert union_regions is None
    assert "single_page_union_skipped_disjoint_tail" in union_flags
    assert [region.region_kind for region in page_regions] == ["page_diagram_union", "text"]
    assert page_regions[0].bbox.y1 < 400
    assert page_regions[1].bbox.y0 == 550
    assert len(page_regions[0].excluded_regions) == 1
    assert "page_diagram_union_used" in page_flags
