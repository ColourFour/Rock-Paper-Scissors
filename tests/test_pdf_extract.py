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


def test_question_number_stem_and_mark_stay_on_one_visual_line() -> None:
    raw_order = [
        span("The coefficient", 32, 10, 112, 20),
        span("1", 10, 10, 16, 20),
        span("[3]", 220, 10, 235, 20),
        span("of", 116, 10, 126, 20),
        span("x", 130, 10, 136, 20),
        span("3", 137, 5, 142, 12, size=7),
        span(".", 143, 10, 146, 20),
    ]

    lines = _group_spans_into_visual_lines(raw_order, y_tolerance=6)

    assert len(lines) == 1
    assert _line_text_from_spans(lines[0]) == "1 The coefficient of x^{3}. [3]"


def test_mark_token_is_not_treated_as_script() -> None:
    raw_order = [
        span("Find", 50, 10, 72, 20),
        span("x", 76, 10, 82, 20),
        span("[3]", 120, 6, 135, 18, size=7),
    ]

    lines = _group_spans_into_visual_lines(raw_order, y_tolerance=6)

    assert len(lines) == 1
    assert _line_text_from_spans(lines[0]) == "Find x [3]"


def test_question_number_is_not_treated_as_subscript_or_split_line() -> None:
    raw_order = [
        span("8", 10, 11, 16, 21, size=7),
        span("Express", 32, 10, 72, 20),
        span("x", 78, 10, 84, 20),
        span("2", 85, 5, 90, 12, size=7),
    ]

    lines = _group_spans_into_visual_lines(raw_order, y_tolerance=6)

    assert len(lines) == 1
    assert _line_text_from_spans(lines[0]) == "8 Express x^{2}"