from exam_bank.pdf_extract import _group_spans_into_visual_lines, _line_text_from_spans


def span(text: str, x0: float, y0: float, x1: float, y1: float, size: float = 10) -> dict:
    return {
        "text": text,
        "bbox": [x0, y0, x1, y1],
        "size": size,
        "font": "TestFont",
    }


def test_spans_are_grouped_by_visual_y_then_x_not_raw_order() -> None:
    raw_order = [
        span("second", 50, 40, 85, 50),
        span("[3]", 120, 10, 135, 20),
        span("Find", 50, 10, 72, 20),
        span("x", 76, 10, 82, 20),
        span("2", 83, 5, 88, 12, size=7),
        span(".", 89, 10, 92, 20),
    ]

    lines = _group_spans_into_visual_lines(raw_order, y_tolerance=6)
    text_lines = [_line_text_from_spans(line) for line in lines]

    assert text_lines == ["Find x^{2}. [3]", "second"]


def test_nearby_y_offsets_stay_on_same_visual_line() -> None:
    raw_order = [
        span("+", 84, 11, 90, 21),
        span("1", 94, 13, 100, 23),
        span("x", 76, 9, 82, 19),
    ]

    lines = _group_spans_into_visual_lines(raw_order, y_tolerance=6)

    assert len(lines) == 1
    assert _line_text_from_spans(lines[0]) == "x + 1"

