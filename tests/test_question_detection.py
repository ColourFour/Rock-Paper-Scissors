from pathlib import Path

from exam_bank.config import AppConfig
from exam_bank.exporters import write_json
from exam_bank.identifiers import normalize_question_id
from exam_bank.image_rendering import _detect_prompt_regions
from exam_bank.mark_schemes import (
    MarkSchemeAnchor,
    MarkSchemeTable,
    MarkSchemeWord,
    _blocks_for_table_anchor_bounds,
    _detect_mark_scheme_tables,
    _detect_table_question_anchors,
    _detect_table_question_anchors_from_words,
    _detected_subparts_for_question,
    _mark_total_for_question_block,
    _marks_from_marks_cell,
    _next_boundary_anchor,
    _parse_mark_scheme_question_cell,
    _table_regions_for_anchor,
    _validate_mark_scheme_mapping,
    find_mark_scheme,
)
from exam_bank.models import BoundingBox, PageLayout, QuestionRecord, TextBlock
from exam_bank.pipeline import _question_subparts_from_span, _question_subparts_from_text
from exam_bank.question_detection import detect_question_spans, extract_marks_from_text, extract_question_total_from_text, parse_question_start


def block(page: int, text: str, y: float, x: float = 50) -> TextBlock:
    return TextBlock(page_number=page, text=text, bbox=BoundingBox(x, y, x + 300, y + 12))


def cell(page: int, text: str, y: float, x: float, width: float = 45) -> TextBlock:
    return TextBlock(page_number=page, text=text, bbox=BoundingBox(x, y, x + width, y + 12))


def hline(y: float, x0: float = 40, x1: float = 560) -> BoundingBox:
    return BoundingBox(x0, y, x1, y + 1)


def ms_word(page: int, text: str, x: float, y: float, width: float = 32) -> MarkSchemeWord:
    return MarkSchemeWord(page_number=page, text=text, bbox=BoundingBox(x, y, x + width, y + 12))


def vline(x: float, y0: float = 95, y1: float = 230) -> BoundingBox:
    return BoundingBox(x, y0, x + 1, y1)


def test_parse_question_start_accepts_top_level_and_subpart_label() -> None:
    config = AppConfig()
    assert parse_question_start("1 Solve the equation", config) == ("1", "1")
    assert parse_question_start("2(a)(i) Find x", config) == ("2", "2(a)(i)")
    assert parse_question_start("9709/32/M/J/19", config) is None


def test_detect_question_spans_groups_subparts_under_top_level_question() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[
            block(1, "1 Solve the equation [3]", 100),
            block(1, "(a) First part", 125, x=72),
            block(1, "........................................", 145, x=72),
            block(1, "(b) Second part", 155, x=72),
            block(1, "2 Differentiate y = x^2 [2]", 220),
        ],
    )

    spans = detect_question_spans([layout], Path("paper_qp.pdf"), config)

    assert len(spans) == 2
    assert spans[0].question_number == "1"
    assert spans[0].full_question_label == "1(a)-(b)"
    assert "(b) Second part" in spans[0].combined_text
    assert "........................" not in spans[0].combined_text
    assert "2 Differentiate" not in spans[0].combined_text


def test_detect_question_spans_splits_same_page_secondary_question_anchor() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[
            block(1, "2 Differentiate y = x^3. [3]", 100),
            block(1, "Find the gradient when x = 2.", 132, x=72),
            block(1, "3 Solve the equation x^2 - 5x + 6 = 0. [4]", 430),
        ],
    )

    spans = detect_question_spans([layout], Path("paper_qp.pdf"), config)

    assert [span.question_number for span in spans] == ["2", "3"]
    assert "3 Solve the equation" not in spans[0].combined_text
    assert "same_page_secondary_anchor_detected" in spans[0].review_flags
    assert "same_page_split_performed" in spans[0].review_flags


def test_detect_question_spans_splits_after_large_answer_space_before_new_question() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[
            block(1, "4 State the value of k. [2]", 95),
            block(1, "........................................", 150, x=72),
            block(1, "........................................", 178, x=72),
            block(1, "........................................", 206, x=72),
            block(1, "........................................", 234, x=72),
            block(1, "5 Sketch the graph of y = sin x for 0 <= x <= 2pi. [3]", 470),
        ],
    )

    spans = detect_question_spans([layout], Path("paper_qp.pdf"), config)

    assert [span.question_number for span in spans] == ["4", "5"]
    assert "5 Sketch the graph" not in spans[0].combined_text


def test_detect_question_spans_does_not_false_split_single_question_spanning_page() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[
            block(1, "6 The curve C has equation y = x^3 - 3x + 1.", 100),
            block(1, "Find the coordinates of the stationary points of C.", 165, x=72),
            block(1, "Hence determine the nature of each stationary point. [5]", 430, x=72),
        ],
    )

    spans = detect_question_spans([layout], Path("paper_qp.pdf"), config)

    assert len(spans) == 1
    assert spans[0].question_number == "6"
    assert "Hence determine the nature" in spans[0].combined_text


def test_detect_question_spans_preserves_lower_same_page_multipart_continuation() -> None:
    config = AppConfig()
    layouts = [
        PageLayout(
            page_number=1,
            width=595,
            height=842,
            blocks=[
                block(1, "5 (a) Find the exact value of cos 60°. [1]", 100),
                block(1, "........................................", 160, x=72),
                block(1, "........................................", 188, x=72),
                block(1, "........................................", 216, x=72),
                block(1, "(b) Hence find the exact value of sin 30°. [1]", 450, x=72),
            ],
        ),
        PageLayout(
            page_number=2,
            width=595,
            height=842,
            blocks=[
                block(2, "6 Next question. [3]", 100),
            ],
        ),
    ]

    spans = detect_question_spans(layouts, Path("paper_qp.pdf"), config)

    assert [span.question_number for span in spans] == ["5", "6"]
    assert spans[0].structure_detected["subparts"] == ["a", "b"]
    assert "6 Next question" not in spans[0].combined_text


def test_detect_question_spans_rescue_subpart_from_mixed_page_furniture_on_continuation_page() -> None:
    config = AppConfig()
    layouts = [
        PageLayout(
            page_number=1,
            width=595,
            height=842,
            blocks=[
                block(1, "6 (a) Solve the equation. [3]", 100),
                block(1, "........................................", 150, x=72),
            ],
        ),
        PageLayout(
            page_number=2,
            width=595,
            height=842,
            blocks=[
                block(2, "© UCLES 2025(b) Hence find the second value. [2]", 32),
                block(2, "7 Start of next question. [4]", 220),
            ],
        ),
    ]

    spans = detect_question_spans(layouts, Path("paper_qp.pdf"), config)

    assert len(spans) == 2
    assert spans[0].question_number == "6"
    assert spans[0].full_question_label == "6(a)-(b)"
    assert "(b) Hence find the second value. [2]" in spans[0].combined_text
    assert "7 Start of next question" not in spans[0].combined_text


def test_detect_question_spans_flags_gap_when_middle_subpart_is_missing() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[
            block(1, "7 (a) First part. [2]", 100),
            block(1, "(c) Third part. [4]", 180, x=72),
            block(1, "8 Next question. [3]", 260),
        ],
    )

    span = detect_question_spans([layout], Path("paper_qp.pdf"), config)[0]

    assert span.full_question_label == "7(a),(c)"
    assert "question_subpart_sequence_gap" in span.review_flags
    assert "question_scope_incomplete" in span.review_flags
    assert "impossible_subpart_sequence_detected" in span.review_flags
    assert "question_subparts_incomplete" in span.validation_flags
    assert span.structure_detected["missing_internal_subparts"] == ["b"]
    assert span.structure_detected["impossible_subpart_sequence_detected"] is True


def test_detect_question_spans_flags_roman_gap_when_middle_subpart_is_missing() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[
            block(1, "8 (i) First part. [2]", 100),
            block(1, "(iii) Third part. [4]", 180, x=72),
            block(1, "9 Next question. [3]", 260),
        ],
    )

    span = detect_question_spans([layout], Path("paper_qp.pdf"), config)[0]

    assert "question_subpart_sequence_gap" in span.review_flags
    assert "impossible_subpart_sequence_detected" in span.review_flags
    assert "question_subparts_incomplete" in span.validation_flags
    assert span.structure_detected["missing_internal_subparts"] == ["ii"]
    assert span.structure_detected["impossible_subpart_sequence_detected"] is True


def test_detect_question_spans_flags_single_first_subpart_without_end_evidence() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[
            block(1, "4 (a) State the value of k.", 100),
            block(1, "5 Next question. [3]", 220),
        ],
    )

    span = detect_question_spans([layout], Path("paper_qp.pdf"), config)[0]

    assert "question_subparts_incomplete" in span.validation_flags
    assert "missing_terminal_mark_total" in span.validation_flags


def test_detect_question_spans_does_not_false_positive_genuine_single_part_question() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[
            block(1, "4 (a) State the value of k. [2]", 100),
            block(1, "5 Next question. [3]", 220),
        ],
    )

    span = detect_question_spans([layout], Path("paper_qp.pdf"), config)[0]

    assert "question_subparts_incomplete" not in span.validation_flags
    assert "missing_terminal_mark_total" not in span.validation_flags


def test_detect_question_spans_flags_roman_singleton_without_ii() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[
            block(1, "8 (i) Show that the gradient is 3.", 100),
            block(1, "9 Next question. [4]", 220),
        ],
    )

    span = detect_question_spans([layout], Path("paper_qp.pdf"), config)[0]

    assert "question_subparts_incomplete" in span.validation_flags


def test_detect_question_spans_flags_weak_nearly_empty_anchor() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[
            block(1, "6", 100),
            block(1, "7 Next question. [4]", 220),
        ],
    )

    span = detect_question_spans([layout], Path("paper_qp.pdf"), config)[0]

    assert "weak_question_anchor" in span.validation_flags
    assert "likely_truncated_question_crop" in span.validation_flags


def test_detect_question_spans_recovers_nearby_missing_continuation_block() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[
            block(1, "3 (a) Solve the equation.", 100),
            block(1, "© UCLES 2025 (b) Hence find the other root. [2]", 145),
            block(1, "4 Next question. [3]", 250),
        ],
    )

    span = detect_question_spans([layout], Path("9709 Mathematics June 2025 Question paper  12.pdf"), config)[0]

    assert "(b) Hence find the other root. [2]" in span.combined_text
    assert "question_subparts_incomplete" not in span.validation_flags
    assert span.recovery_result in {"improved", "not_needed"}


def test_detect_question_spans_newer_format_stops_before_foreign_top_continuation() -> None:
    config = AppConfig()
    layouts = [
        PageLayout(
            page_number=1,
            width=595,
            height=842,
            blocks=[
                block(1, "2 A fair six-sided dice is thrown repeatedly until a 6 is obtained.", 90),
                block(1, "(a) Find the probability that a 6 is obtained on the 8th throw. [1]", 120, x=72),
                block(1, "(b) Find the probability that a 6 is obtained for the third time on the 7th throw. [3]", 155, x=72),
            ],
        ),
        PageLayout(
            page_number=2,
            width=595,
            height=842,
            blocks=[
                block(2, "(b) Find the mean annual salary of these employees. ....................................................................", 32, x=72),
                block(2, "3 Next question. [4]", 220),
            ],
        ),
    ]

    span = detect_question_spans(layouts, Path("9709 Mathematics November 2025 Question Paper  51.pdf"), config)[0]

    assert "annual salary" not in span.combined_text
    assert "newer_format_scope_stop_before_foreign_continuation" in span.review_flags
    assert "question_scope_contaminated" not in span.validation_flags


def test_detect_question_spans_stops_before_next_anchor_after_complete_question() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[
            block(1, "3 Kai has a spinner with four sides labelled 1, 2, 3, 4.", 90),
            block(1, "(a) Find Var(X). [4]", 120, x=72),
            block(1, "(b) Find the probability that a score of 2 is obtained fewer than 8 times. [3]", 160, x=72),
            block(1, "4 Priti has two bags of discs. [2]", 250),
        ],
    )

    span = detect_question_spans([layout], Path("9709 Mathematics November 2025 Question Paper  55.pdf"), config)[0]

    assert "Priti has two bags of discs" not in span.combined_text
    assert span.question_total_detected == 7


def test_detect_question_spans_keeps_valid_top_continuation_with_same_topic() -> None:
    config = AppConfig()
    layouts = [
        PageLayout(
            page_number=1,
            width=595,
            height=842,
            blocks=[
                block(1, "4 The heights of players from Pelicans and Swans are given in the table.", 90),
                block(1, "(a) Draw a back-to-back stem-and-leaf diagram for Pelicans and Swans. [4]", 140, x=72),
            ],
        ),
        PageLayout(
            page_number=2,
            width=595,
            height=842,
            blocks=[
                block(2, "(d) Make one comparison between the heights of the Pelicans players and the heights of the Swans players. ....................................................................", 32, x=72),
                block(2, "(b) Find the median and the interquartile range of the heights of the Pelicans. [3]", 90, x=72),
                block(2, "(c) Represent the data by a pair of box-and-whisker plots. [3]", 150, x=72),
                block(2, "5 Next question. [2]", 250),
            ],
        ),
    ]

    span = detect_question_spans(layouts, Path("9709 Mathematics November 2025 Question Paper  55.pdf"), config)[0]

    assert "comparison between the heights" in span.combined_text
    assert "(b) Find the median" in span.combined_text
    assert "question_scope_contaminated" not in span.validation_flags


def test_detect_question_spans_flags_mixed_question_scope_contamination() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[
            block(1, "2 A fair six-sided dice is thrown repeatedly until a 6 is obtained.", 90),
            block(1, "(a) Find the probability that a 6 is obtained on the 8th throw. [1]", 120, x=72),
            block(1, "(b) Find the probability that a 6 is obtained for the third time on the 7th throw. [3]", 155, x=72),
            block(1, "(b) Find the mean and standard deviation of the annual salaries of these 54 employees.", 205, x=72),
            block(1, "....................................................................................................", 235, x=72),
            block(1, "3 Next question. [4]", 300),
        ],
    )

    span = detect_question_spans([layout], Path("9709 Mathematics November 2025 Question Paper  51.pdf"), config)[0]

    assert "question_scope_contaminated" in span.validation_flags
    assert span.structure_detected["contamination_detected"] is True


def test_detect_question_spans_flags_answer_space_contamination() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[
            block(1, "4 Complete the tree diagram for the bag experiment.", 90),
            block(1, "(a) Complete the tree diagram below by entering all the remaining outcomes and probabilities. [3]", 120, x=72),
            block(1, "(b) Find the mean annual salary of these employees. DO NOT WRITE IN THIS MARGIN ....................................................................................................", 190, x=72),
            block(1, "5 Next question. [2]", 300),
        ],
    )

    span = detect_question_spans([layout], Path("9709 Mathematics November 2025 Question Paper  51.pdf"), config)[0]

    assert "question_scope_contaminated" in span.validation_flags
    assert span.structure_detected["contamination_indicators"]["filler_line_count"] >= 1


def test_detect_question_spans_does_not_false_flag_valid_long_multipart_question_as_contaminated() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[
            block(1, "3 Priti has two bags of discs, X and Y.", 90),
            block(1, "Bag X contains 8 red discs and 7 blue discs.", 120, x=72),
            block(1, "Bag Y contains 6 red discs and 9 blue discs.", 145, x=72),
            block(1, "(a) Draw a tree diagram to represent this information. [2]", 180, x=72),
            block(1, "(b) Find the probability that the two discs chosen are blue. [2]", 215, x=72),
            block(1, "(c) Find the conditional probability that at least one disc is red. [4]", 250, x=72),
            block(1, "4 Next question. [3]", 330),
        ],
    )

    span = detect_question_spans([layout], Path("9709 Mathematics November 2025 Question Paper  55.pdf"), config)[0]

    assert "question_scope_contaminated" not in span.validation_flags


def test_detect_question_spans_excludes_previous_tail_and_centered_page_number_from_new_question() -> None:
    config = AppConfig()
    layouts = [
        PageLayout(
            page_number=1,
            width=595,
            height=842,
            blocks=[
                block(1, "2 (a) Earlier question. [3]", 100),
                block(1, "(b) Earlier continuation. [2]", 180, x=72),
            ],
        ),
        PageLayout(
            page_number=2,
            width=595,
            height=842,
            blocks=[
                block(2, "(b) ............................................................................................", 42, x=8),
                block(2, "5", 48, x=292),
                block(2, "3", 73, x=50),
                block(2, "The real start of question 3. [4]", 241, x=72),
                block(2, "(a) First part. [2]", 293, x=72),
                block(2, "4 Next question. [3]", 420, x=50),
            ],
        ),
    ]

    spans = detect_question_spans(layouts, Path("paper_qp.pdf"), config)
    q3 = next(span for span in spans if span.question_number == "3")

    assert "(b) ................................................................" not in q3.combined_text
    assert "\n5\n" not in f"\n{q3.combined_text}\n"
    assert "The real start of question 3." in q3.combined_text


def test_detect_question_spans_keeps_later_subpart_below_answer_lines() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[
            block(1, "3 (a) Find x. [4]", 90),
            block(1, "(b) Hence find y. [2]", 520, x=72),
            block(1, "4 Next question. [3]", 700, x=50),
        ],
        graphics=[hline(y, x0=95, x1=555) for y in range(180, 421, 26)],
    )

    spans = detect_question_spans([layout], Path("paper_qp.pdf"), config)
    q3 = next(span for span in spans if span.question_number == "3")

    assert q3.full_question_label == "3(a)-(b)"
    assert "(b) Hence find y. [2]" in q3.combined_text


def test_detect_question_spans_preserves_top_continuation_on_continuation_page() -> None:
    config = AppConfig()
    layouts = [
        PageLayout(
            page_number=1,
            width=595,
            height=842,
            blocks=[
                block(1, "3 Intro part. [3]", 90),
                block(1, "(a) First part. [3]", 260, x=72),
            ],
        ),
        PageLayout(
            page_number=2,
            width=595,
            height=842,
            blocks=[
                block(2, "© UCLES 2025(b) Wrong rescued continuation. [2]", 32, x=50),
                block(2, "4 Next question. [4]", 63, x=50),
            ],
        ),
    ]

    spans = detect_question_spans(layouts, Path("paper_qp.pdf"), config)
    q3 = next(span for span in spans if span.question_number == "3")

    assert "Wrong rescued continuation" in q3.combined_text


def test_detect_question_spans_preserves_out_of_order_top_continuation_on_continuation_page() -> None:
    config = AppConfig()
    layouts = [
        PageLayout(
            page_number=1,
            width=595,
            height=842,
            blocks=[
                block(1, "6 Question intro. [1]", 90),
                block(1, "(a) First part. [4]", 180, x=72),
            ],
        ),
        PageLayout(
            page_number=2,
            width=595,
            height=842,
            blocks=[
                block(2, "DO NOT WRITE IN THIS MARGIN (d) Wrong top continuation. [1]", 32, x=6),
                block(2, "(c) Real later part. [3]", 63, x=72),
            ],
        ),
    ]

    spans = detect_question_spans(layouts, Path("paper_qp.pdf"), config)
    q6 = next(span for span in spans if span.question_number == "6")

    assert "Wrong top continuation" in q6.combined_text
    assert "(c) Real later part. [3]" in q6.combined_text


def test_extract_marks_sums_bracketed_marks() -> None:
    assert extract_marks_from_text("Find x. [2]\nHence find y. [3]") == 5
    assert extract_marks_from_text("No mark shown") is None
    assert extract_question_total_from_text("Find x. [2]\nHence find y. [3]\n[5]") == 5


def test_question_subparts_from_span_preserves_multiline_middle_parts() -> None:
    span = detect_question_spans(
        [
            PageLayout(
                page_number=1,
                width=595,
                height=842,
                blocks=[
                    block(1, "7 (a) First part. [2]\n(b) Second part. [3]\n(c) Third part. [1]", 100),
                    block(1, "8 Next question. [4]", 260),
                ],
            )
        ],
        Path("paper_qp.pdf"),
        AppConfig(),
    )[0]

    assert _question_subparts_from_text(span.combined_text) == ["a"]
    assert _question_subparts_from_span(span) == ["a", "b", "c"]


def test_mark_scheme_auto_pairing(tmp_path: Path) -> None:
    qp = tmp_path / "March 2019_qp_32.pdf"
    ms_dir = tmp_path / "mark_schemes"
    ms_dir.mkdir()
    qp.write_text("fake", encoding="utf-8")
    ms = ms_dir / "March 2019_ms_32.pdf"
    ms.write_text("fake", encoding="utf-8")

    assert find_mark_scheme(qp, ms_dir) == ms


def test_mark_scheme_table_mapping_merges_blank_question_number_continuation_rows() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=6,
        width=595,
        height=842,
        blocks=[
            cell(6, "Question", 100, x=45, width=55),
            cell(6, "Answer", 100, x=130, width=50),
            cell(6, "Marks", 100, x=390, width=45),
            cell(6, "Guidance", 100, x=455, width=65),
            cell(6, "1", 135, x=50, width=10),
            cell(6, "x = 2", 135, x=130),
            cell(6, "M1", 135, x=390, width=25),
            cell(6, "Allow equivalent", 135, x=455, width=120),
            cell(6, "continued working", 165, x=130, width=120),
            cell(6, "A1", 165, x=390, width=25),
            cell(6, "further guidance for same question", 195, x=455, width=120),
            cell(6, "2", 220, x=50, width=10),
            cell(6, "Differentiate", 220, x=130, width=100),
        ],
    )

    tables = _detect_mark_scheme_tables([layout], config)
    anchors = _detect_table_question_anchors([layout], tables, config, ["1", "2"])
    regions, flags = _table_regions_for_anchor([layout], tables, anchors[0], anchors[1], config)

    assert tables[6].question_col_right < 130
    assert [anchor.question_number for anchor in anchors] == ["1", "2"]
    assert not flags
    assert len(regions) == 1
    assert anchors[0].y0 - config.detection.crop_padding <= regions[0].bbox.y0 <= anchors[0].y0
    assert regions[0].bbox.y1 > 195
    assert regions[0].bbox.y1 < 220
    assert regions[0].bbox.x0 <= tables[6].bbox.x0
    assert regions[0].bbox.x1 >= tables[6].bbox.x1
    assert regions[0].continuation_rows_included


def test_mark_scheme_answer_table_may_start_on_page_5_when_header_is_valid() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=5,
        width=595,
        height=842,
        blocks=[
            cell(5, "Question", 100, x=45, width=55),
            cell(5, "Answer", 100, x=130, width=50),
            cell(5, "Marks", 100, x=390, width=45),
            cell(5, "Guidance", 100, x=455, width=65),
            cell(5, "1", 135, x=50, width=10),
            cell(5, "x = 2", 135, x=130),
        ],
    )

    assert list(_detect_mark_scheme_tables([layout], config)) == [5]


def test_question_id_normalization_preserves_subparts() -> None:
    assert normalize_question_id("3 a") == "3(a)"
    assert normalize_question_id("3(a)") == "3(a)"
    assert normalize_question_id("3a") == "3(a)"
    assert normalize_question_id("Question 3(a)") == "3(a)"
    assert normalize_question_id("8(iv)") == "8(iv)"
    assert _parse_mark_scheme_question_cell("3(b)", {"3(b)"}) == "3(b)"
    assert _parse_mark_scheme_question_cell("8x4", {"8"}) is None
    assert _parse_mark_scheme_question_cell("2(x2", {"2"}) is None
    assert _parse_mark_scheme_question_cell("(5", {"5"}) is None
    assert _parse_mark_scheme_question_cell("4tan", {"4"}) is None


def test_mark_scheme_table_detection_requires_answer_table_headers() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=6,
        width=595,
        height=842,
        blocks=[
            cell(6, "Question", 100, x=45, width=55),
            cell(6, "Mark Scheme", 100, x=130, width=80),
            cell(6, "Rules", 100, x=390, width=45),
            cell(6, "1", 135, x=50, width=10),
            cell(6, "General rubric", 135, x=130, width=120),
        ],
    )

    assert _detect_mark_scheme_tables([layout], config) == {}


def test_mark_scheme_header_requires_exact_marks_column() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=6,
        width=595,
        height=842,
        blocks=[
            cell(6, "Question", 100, x=45, width=55),
            cell(6, "Answer", 100, x=130, width=50),
            cell(6, "Mark", 100, x=390, width=45),
            cell(6, "Guidance", 100, x=455, width=65),
            cell(6, "1", 135, x=50, width=10),
            cell(6, "x = 2", 135, x=130),
        ],
    )

    assert _detect_mark_scheme_tables([layout], config) == {}


def test_mark_scheme_subpart_matching_keeps_3a_and_3b_separate() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=6,
        width=595,
        height=842,
        blocks=[
            cell(6, "Question", 100, x=45, width=55),
            cell(6, "Answer", 100, x=130, width=50),
            cell(6, "Marks", 100, x=390, width=45),
            cell(6, "Guidance", 100, x=455, width=65),
            cell(6, "3(a)", 135, x=50, width=35),
            cell(6, "Part a answer", 135, x=130, width=100),
            cell(6, "B1", 135, x=390, width=25),
            cell(6, "3(b)", 170, x=50, width=35),
            cell(6, "Part b answer", 170, x=130, width=100),
            cell(6, "M1", 170, x=390, width=25),
            cell(6, "4", 210, x=50, width=10),
            cell(6, "Next question", 210, x=130, width=100),
        ],
    )

    tables = _detect_mark_scheme_tables([layout], config)
    anchors = _detect_table_question_anchors([layout], tables, config, ["3(a)", "3(b)", "4"])
    region_a, flags_a = _table_regions_for_anchor([layout], tables, anchors[0], anchors[1], config)
    region_b, flags_b = _table_regions_for_anchor([layout], tables, anchors[1], anchors[2], config)

    assert [anchor.question_number for anchor in anchors] == ["3(a)", "3(b)", "4"]
    assert not flags_a
    assert not flags_b
    assert region_a[0].bbox.y1 <= anchors[1].y0
    assert region_b[0].bbox.y0 < anchors[1].y0
    assert region_b[0].bbox.y1 <= anchors[2].y0


def test_mark_scheme_full_parent_block_includes_all_subparts_and_marks() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=6,
        width=595,
        height=842,
        blocks=[
            cell(6, "Question", 100, x=45, width=55),
            cell(6, "Answer", 100, x=130, width=50),
            cell(6, "Marks", 100, x=390, width=45),
            cell(6, "Guidance", 100, x=455, width=65),
            cell(6, "5(a)", 135, x=50, width=35),
            cell(6, "Part a answer", 135, x=130, width=100),
            cell(6, "B1", 135, x=390, width=25),
            cell(6, "5(b)", 170, x=50, width=35),
            cell(6, "Part b answer", 170, x=130, width=100),
            cell(6, "M1 A1", 170, x=390, width=45),
            cell(6, "5(c)", 205, x=50, width=35),
            cell(6, "Part c answer", 205, x=130, width=100),
            cell(6, "B2", 205, x=390, width=25),
            cell(6, "6", 250, x=50, width=10),
            cell(6, "Next question", 250, x=130, width=100),
        ],
    )

    tables = _detect_mark_scheme_tables([layout], config)
    anchors = _detect_table_question_anchors([layout], tables, config, ["5", "6"])
    regions, flags = _table_regions_for_anchor([layout], tables, anchors[0], anchors[-1], config)
    mark_total = _mark_total_for_question_block([layout], anchors[0], anchors[-1], tables)
    validation_flags, reason = _validate_mark_scheme_mapping(
        "5",
        ["a", "b", "c"],
        ["a", "b", "c"],
        5,
        mark_total,
        anchors[0],
        anchors[-1],
        regions,
        flags,
    )

    assert mark_total == 5
    assert not validation_flags
    assert reason == ""
    assert regions[0].bbox.y1 <= anchors[-1].y0


def test_mark_scheme_whole_question_group_includes_roman_subparts_and_excludes_next_parent() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=6,
        width=595,
        height=842,
        blocks=[
            cell(6, "Question", 100, x=45, width=55),
            cell(6, "Answer", 100, x=130, width=50),
            cell(6, "Marks", 100, x=390, width=45),
            cell(6, "Guidance", 100, x=455, width=65),
            cell(6, "8(i)", 135, x=50, width=35),
            cell(6, "Part i answer", 135, x=130, width=100),
            cell(6, "B2", 135, x=390, width=25),
            cell(6, "8(ii)", 170, x=50, width=35),
            cell(6, "Part ii answer", 170, x=130, width=100),
            cell(6, "B1", 170, x=390, width=25),
            cell(6, "8(iii)", 205, x=50, width=42),
            cell(6, "Part iii answer", 205, x=130, width=100),
            cell(6, "M1 A1 A1", 205, x=390, width=55),
            cell(6, "8(iv)", 240, x=50, width=42),
            cell(6, "Part iv answer", 240, x=130, width=100),
            cell(6, "M1 A1 M1 A1", 240, x=390, width=75),
            cell(6, "9(i)", 295, x=50, width=35),
            cell(6, "Next question", 295, x=130, width=100),
        ],
    )

    tables = _detect_mark_scheme_tables([layout], config)
    anchors = _detect_table_question_anchors([layout], tables, config, ["8", "9"])
    regions, flags = _table_regions_for_anchor([layout], tables, anchors[0], anchors[-1], config)
    mark_total = _mark_total_for_question_block([layout], anchors[0], anchors[-1], tables)
    detected_subparts = _detected_subparts_for_question(anchors, 0, "8")
    validation_flags, reason = _validate_mark_scheme_mapping(
        "8",
        ["i", "ii", "iii", "iv"],
        detected_subparts,
        10,
        mark_total,
        anchors[0],
        anchors[-1],
        regions,
        flags,
    )

    assert [anchor.question_number for anchor in anchors] == ["8(i)", "8(ii)", "8(iii)", "8(iv)", "9(i)"]
    assert detected_subparts == ["i", "ii", "iii", "iv"]
    assert mark_total == 10
    assert not validation_flags
    assert reason == ""
    assert regions[0].bbox.y1 <= anchors[-1].y0


def test_mark_scheme_parent_boundary_prefers_first_child_anchor_over_stray_parent_number() -> None:
    table = MarkSchemeTable(
        page_number=1,
        bbox=BoundingBox(40, 50, 540, 430),
        question_col_right=120,
        marks_col_left=350,
        marks_col_right=420,
        header_bottom=70,
        confidence="high",
        header_detected=["Question", "Answer", "Marks", "Guidance"],
    )
    anchors = [
        MarkSchemeAnchor("9(a)", 1, 90, 102, 60, "9(a)", table),
        MarkSchemeAnchor("10", 1, 220, 232, 60, "10", table),
        MarkSchemeAnchor("10(a)", 2, 90, 102, 60, "10(a)", table),
        MarkSchemeAnchor("10(b)", 3, 90, 102, 60, "10(b)", table),
        MarkSchemeAnchor("11", 4, 90, 102, 60, "11", table),
    ]

    assert _next_boundary_anchor(anchors, 0, "9") == anchors[2]


def test_mark_scheme_mapping_rejects_missing_subpart_and_marks_mismatch() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=6,
        width=595,
        height=842,
        blocks=[
            cell(6, "Question", 100, x=45, width=55),
            cell(6, "Answer", 100, x=130, width=50),
            cell(6, "Marks", 100, x=390, width=45),
            cell(6, "Guidance", 100, x=455, width=65),
            cell(6, "5(a)", 135, x=50, width=35),
            cell(6, "Part a answer", 135, x=130, width=100),
            cell(6, "B1", 135, x=390, width=25),
            cell(6, "5(b)", 170, x=50, width=35),
            cell(6, "Part b answer", 170, x=130, width=100),
            cell(6, "M1", 170, x=390, width=25),
            cell(6, "6", 220, x=50, width=10),
            cell(6, "Next question", 220, x=130, width=100),
        ],
    )

    tables = _detect_mark_scheme_tables([layout], config)
    anchors = _detect_table_question_anchors([layout], tables, config, ["5", "6"])
    regions, flags = _table_regions_for_anchor([layout], tables, anchors[0], anchors[-1], config)
    mark_total = _mark_total_for_question_block([layout], anchors[0], anchors[-1], tables)

    validation_flags, reason = _validate_mark_scheme_mapping(
        "5",
        ["a", "b", "c"],
        ["a", "b"],
        5,
        mark_total,
        anchors[0],
        anchors[-1],
        regions,
        flags,
    )

    assert mark_total == 2
    assert validation_flags == ["mark_scheme_part_structure_mismatch"]
    assert reason == "mark_scheme_part_structure_mismatch"

    validation_flags, reason = _validate_mark_scheme_mapping(
        "5",
        ["a", "b"],
        ["a", "b"],
        5,
        mark_total,
        anchors[0],
        anchors[-1],
        regions,
        flags,
    )

    assert validation_flags == ["question_mark_total_mismatch"]
    assert reason == "question_mark_total_mismatch"


def test_mark_scheme_mapping_rejects_question_scope_smaller_than_markscheme_scope() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=6,
        width=595,
        height=842,
        blocks=[
            cell(6, "Question", 100, x=45, width=55),
            cell(6, "Answer", 100, x=130, width=50),
            cell(6, "Marks", 100, x=390, width=45),
            cell(6, "Guidance", 100, x=455, width=65),
            cell(6, "7(a)", 135, x=50, width=35),
            cell(6, "Part a answer", 135, x=130, width=100),
            cell(6, "B1", 135, x=390, width=25),
            cell(6, "7(b)", 170, x=50, width=35),
            cell(6, "Part b answer", 170, x=130, width=100),
            cell(6, "M1", 170, x=390, width=25),
            cell(6, "8", 220, x=50, width=10),
            cell(6, "Next question", 220, x=130, width=100),
        ],
    )

    tables = _detect_mark_scheme_tables([layout], config)
    anchors = _detect_table_question_anchors([layout], tables, config, ["7", "8"])
    regions, flags = _table_regions_for_anchor([layout], tables, anchors[0], anchors[-1], config)

    validation_flags, reason = _validate_mark_scheme_mapping(
        "7",
        ["a"],
        ["a", "b"],
        1,
        2,
        anchors[0],
        anchors[-1],
        regions,
        flags,
    )

    assert validation_flags == ["question_subparts_incomplete"]
    assert reason == "question_subparts_incomplete"


def test_mark_scheme_mapping_prioritizes_subparts_mismatch_over_weak_anchor() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=6,
        width=595,
        height=842,
        blocks=[
            cell(6, "Question", 100, x=45, width=55),
            cell(6, "Answer", 100, x=130, width=50),
            cell(6, "Marks", 100, x=390, width=45),
            cell(6, "Guidance", 100, x=455, width=65),
            cell(6, "5(a)", 135, x=50, width=35),
            cell(6, "Part a answer", 135, x=130, width=100),
            cell(6, "B1", 135, x=390, width=25),
            cell(6, "5(b)", 170, x=50, width=35),
            cell(6, "Part b answer", 170, x=130, width=100),
            cell(6, "M1", 170, x=390, width=25),
            cell(6, "5(c)", 205, x=50, width=35),
            cell(6, "Part c answer", 205, x=130, width=100),
            cell(6, "A1", 205, x=390, width=25),
            cell(6, "6", 250, x=50, width=10),
            cell(6, "Next question", 250, x=130, width=100),
        ],
    )

    tables = _detect_mark_scheme_tables([layout], config)
    anchors = _detect_table_question_anchors([layout], tables, config, ["5", "6"])
    regions, flags = _table_regions_for_anchor([layout], tables, anchors[0], anchors[-1], config)

    validation_flags, reason = _validate_mark_scheme_mapping(
        "5",
        ["a"],
        ["a", "b", "c"],
        3,
        6,
        anchors[0],
        anchors[-1],
        regions,
        flags,
        question_validation_flags=["weak_question_anchor"],
    )

    assert validation_flags == ["question_subparts_incomplete"]
    assert reason == "question_subparts_incomplete"


def test_mark_scheme_mapping_prioritizes_total_mismatch_over_weak_anchor() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=6,
        width=595,
        height=842,
        blocks=[
            cell(6, "Question", 100, x=45, width=55),
            cell(6, "Answer", 100, x=130, width=50),
            cell(6, "Marks", 100, x=390, width=45),
            cell(6, "Guidance", 100, x=455, width=65),
            cell(6, "3(a)", 135, x=50, width=35),
            cell(6, "Part a answer", 135, x=130, width=100),
            cell(6, "B1", 135, x=390, width=25),
            cell(6, "3(b)", 170, x=50, width=35),
            cell(6, "Part b answer", 170, x=130, width=100),
            cell(6, "M1 A1", 170, x=390, width=45),
            cell(6, "4", 220, x=50, width=10),
            cell(6, "Next question", 220, x=130, width=100),
        ],
    )

    tables = _detect_mark_scheme_tables([layout], config)
    anchors = _detect_table_question_anchors([layout], tables, config, ["3", "4"])
    regions, flags = _table_regions_for_anchor([layout], tables, anchors[0], anchors[-1], config)

    validation_flags, reason = _validate_mark_scheme_mapping(
        "3",
        ["a", "b"],
        ["a", "b"],
        2,
        3,
        anchors[0],
        anchors[-1],
        regions,
        flags,
        question_validation_flags=["weak_question_anchor"],
    )

    assert validation_flags == ["question_mark_total_mismatch"]
    assert reason == "question_mark_total_mismatch"


def test_mark_scheme_mapping_keeps_weak_anchor_when_no_stronger_structure_mismatch_exists() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=6,
        width=595,
        height=842,
        blocks=[
            cell(6, "Question", 100, x=45, width=55),
            cell(6, "Answer", 100, x=130, width=50),
            cell(6, "Marks", 100, x=390, width=45),
            cell(6, "Guidance", 100, x=455, width=65),
            cell(6, "9(a)", 135, x=50, width=35),
            cell(6, "Part a answer", 135, x=130, width=100),
            cell(6, "B1", 135, x=390, width=25),
            cell(6, "9(b)", 170, x=50, width=35),
            cell(6, "Part b answer", 170, x=130, width=100),
            cell(6, "M1", 170, x=390, width=25),
            cell(6, "10", 220, x=50, width=10),
            cell(6, "Next question", 220, x=130, width=100),
        ],
    )

    tables = _detect_mark_scheme_tables([layout], config)
    anchors = _detect_table_question_anchors([layout], tables, config, ["9", "10"])
    regions, flags = _table_regions_for_anchor([layout], tables, anchors[0], anchors[-1], config)

    validation_flags, reason = _validate_mark_scheme_mapping(
        "9",
        ["a", "b"],
        ["a", "b"],
        2,
        2,
        anchors[0],
        anchors[-1],
        regions,
        flags,
        question_validation_flags=["weak_question_anchor"],
    )

    assert validation_flags == ["weak_question_anchor"]
    assert reason == "weak_question_anchor"


def test_mark_scheme_mapping_rejects_missing_terminal_total_when_question_validation_flags_it() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=6,
        width=595,
        height=842,
        blocks=[
            cell(6, "Question", 100, x=45, width=55),
            cell(6, "Answer", 100, x=130, width=50),
            cell(6, "Marks", 100, x=390, width=45),
            cell(6, "Guidance", 100, x=455, width=65),
            cell(6, "7(a)", 135, x=50, width=35),
            cell(6, "Part a answer", 135, x=130, width=100),
            cell(6, "B1", 135, x=390, width=25),
            cell(6, "7(b)", 170, x=50, width=35),
            cell(6, "Part b answer", 170, x=130, width=100),
            cell(6, "M1", 170, x=390, width=25),
            cell(6, "8", 220, x=50, width=10),
            cell(6, "Next question", 220, x=130, width=100),
        ],
    )

    tables = _detect_mark_scheme_tables([layout], config)
    anchors = _detect_table_question_anchors([layout], tables, config, ["7", "8"])
    regions, flags = _table_regions_for_anchor([layout], tables, anchors[0], anchors[-1], config)

    validation_flags, reason = _validate_mark_scheme_mapping(
        "7",
        ["a", "b"],
        ["a", "b"],
        2,
        2,
        anchors[0],
        anchors[-1],
        regions,
        flags,
        question_validation_flags=["missing_terminal_mark_total"],
    )

    assert validation_flags == ["missing_terminal_mark_total"]
    assert reason == "missing_terminal_mark_total"


def test_mark_scheme_mark_total_sums_standalone_subpart_totals_after_alternatives() -> None:
    table = MarkSchemeTable(
        page_number=6,
        bbox=BoundingBox(40, 50, 540, 430),
        question_col_right=120,
        marks_col_left=350,
        marks_col_right=420,
        header_bottom=70,
        confidence="high",
        header_detected=["Question", "Answer", "Marks", "Guidance"],
    )
    layout = PageLayout(page_number=6, width=595, height=842, blocks=[])
    words_by_page = {
        6: [
            ms_word(6, "8(a)", 60, 90),
            ms_word(6, "M1", 360, 90),
            ms_word(6, "A1", 360, 110),
            ms_word(6, "A1", 360, 130),
            ms_word(6, "3", 360, 150),
            ms_word(6, "8(b)", 60, 175),
            ms_word(6, "B1", 360, 175),
            ms_word(6, "B1", 360, 195),
            ms_word(6, "2", 360, 215),
            ms_word(6, "8(c)", 60, 240),
            ms_word(6, "B1", 360, 240),
            ms_word(6, "B1", 360, 260),
            ms_word(6, "2", 360, 280),
            ms_word(6, "8(d)", 60, 305),
            ms_word(6, "M1", 360, 305),
            ms_word(6, "A1", 360, 325),
            ms_word(6, "Alternative", 180, 345),
            ms_word(6, "method", 245, 345),
            ms_word(6, "M1", 360, 365),
            ms_word(6, "A1", 360, 385),
            ms_word(6, "2", 360, 405),
        ]
    }
    anchor = MarkSchemeAnchor("8(a)", 6, 90, 102, 60, "8(a)", table)

    mark_total = _mark_total_for_question_block([layout], anchor, None, {6: table}, words_by_page)

    assert mark_total == 9


def test_mark_scheme_marks_cell_prefers_mark_codes_over_answer_digits() -> None:
    assert _marks_from_marks_cell("8x2 ± 2x M1") == [1]
    assert _marks_from_marks_cell("Page 10 of 21") == []
    assert _marks_from_marks_cell("8") == []


def test_mark_scheme_mark_total_ignores_answer_digits_spilling_into_marks_column() -> None:
    table = MarkSchemeTable(
        page_number=6,
        bbox=BoundingBox(40, 50, 540, 430),
        question_col_right=120,
        marks_col_left=350,
        marks_col_right=420,
        header_bottom=70,
        confidence="high",
        header_detected=["Question", "Answer", "Marks", "Guidance"],
    )
    layout = PageLayout(page_number=6, width=595, height=842, blocks=[])
    words_by_page = {
        6: [
            ms_word(6, "6", 60, 90),
            ms_word(6, "B1", 360, 90),
            ms_word(6, "B1", 360, 110),
            ms_word(6, "B1", 360, 130),
            ms_word(6, "B1", 360, 150),
            ms_word(6, "M1", 360, 170),
            ms_word(6, "A1", 360, 190),
            ms_word(6, "continued", 180, 210),
            ms_word(6, "8", 360, 210),
        ]
    }
    anchor = MarkSchemeAnchor("6", 6, 90, 102, 60, "6", table)

    mark_total = _mark_total_for_question_block([layout], anchor, None, {6: table}, words_by_page)

    assert mark_total == 6


def test_mark_scheme_mark_total_treats_alternative_methods_as_parallel_branches() -> None:
    table = MarkSchemeTable(
        page_number=6,
        bbox=BoundingBox(40, 50, 540, 430),
        question_col_right=120,
        marks_col_left=350,
        marks_col_right=420,
        header_bottom=70,
        confidence="high",
        header_detected=["Question", "Answer", "Marks", "Guidance"],
    )
    layout = PageLayout(page_number=6, width=595, height=842, blocks=[])
    words_by_page = {
        6: [
            ms_word(6, "9(a)", 60, 90),
            ms_word(6, "B1", 360, 90),
            ms_word(6, "M1", 360, 110),
            ms_word(6, "A1", 360, 130),
            ms_word(6, "9(a)", 60, 160),
            ms_word(6, "Alternative", 150, 160, width=60),
            ms_word(6, "Method", 220, 160, width=50),
            ms_word(6, "B1", 360, 185),
            ms_word(6, "M1", 360, 205),
            ms_word(6, "A1", 360, 225),
            ms_word(6, "3", 360, 255),
        ]
    }
    anchor = MarkSchemeAnchor("9(a)", 6, 90, 102, 60, "9(a)", table)

    mark_total = _mark_total_for_question_block([layout], anchor, None, {6: table}, words_by_page)

    assert mark_total == 3


def test_mark_scheme_alternative_form_explanatory_text_does_not_start_new_branch() -> None:
    table = MarkSchemeTable(
        page_number=6,
        bbox=BoundingBox(40, 50, 540, 430),
        question_col_right=120,
        marks_col_left=350,
        marks_col_right=420,
        header_bottom=70,
        confidence="high",
        header_detected=["Question", "Answer", "Marks", "Guidance"],
    )
    layout = PageLayout(page_number=6, width=595, height=842, blocks=[])
    words_by_page = {
        6: [
            ms_word(6, "10(a)", 60, 90),
            ms_word(6, "B1", 360, 90),
            ms_word(6, "Alternative", 170, 115, width=70),
            ms_word(6, "form:", 250, 115, width=45),
            ms_word(6, "M1", 360, 135),
            ms_word(6, "A1", 360, 155),
            ms_word(6, "A1", 360, 175),
            ms_word(6, "A1", 360, 195),
            ms_word(6, "A1", 360, 215),
        ]
    }
    anchor = MarkSchemeAnchor("10(a)", 6, 90, 102, 60, "10(a)", table)

    mark_total = _mark_total_for_question_block([layout], anchor, None, {6: table}, words_by_page)

    assert mark_total == 5


def test_mark_scheme_method2_heading_starts_parallel_branch_not_additive_total() -> None:
    table = MarkSchemeTable(
        page_number=6,
        bbox=BoundingBox(40, 50, 540, 430),
        question_col_right=120,
        marks_col_left=350,
        marks_col_right=420,
        header_bottom=70,
        confidence="high",
        header_detected=["Question", "Answer", "Marks", "Guidance"],
    )
    layout = PageLayout(page_number=6, width=595, height=842, blocks=[])
    words_by_page = {
        6: [
            ms_word(6, "5(a)", 60, 90),
            ms_word(6, "B1", 360, 90),
            ms_word(6, "M1", 360, 110),
            ms_word(6, "Method", 150, 140, width=55),
            ms_word(6, "2", 210, 140, width=10),
            ms_word(6, "B1", 360, 165),
            ms_word(6, "M1", 360, 185),
            ms_word(6, "2", 360, 215),
        ]
    }
    anchor = MarkSchemeAnchor("5(a)", 6, 90, 102, 60, "5(a)", table)

    mark_total = _mark_total_for_question_block([layout], anchor, None, {6: table}, words_by_page)

    assert mark_total == 2


def test_mark_scheme_mark_total_sums_subpart_caps_instead_of_additive_paths() -> None:
    table = MarkSchemeTable(
        page_number=6,
        bbox=BoundingBox(40, 50, 540, 430),
        question_col_right=120,
        marks_col_left=350,
        marks_col_right=420,
        header_bottom=70,
        confidence="high",
        header_detected=["Question", "Answer", "Marks", "Guidance"],
    )
    layout = PageLayout(page_number=6, width=595, height=842, blocks=[])
    words_by_page = {
        6: [
            ms_word(6, "8(a)", 60, 90),
            ms_word(6, "B1", 360, 90),
            ms_word(6, "M1", 360, 110),
            ms_word(6, "A1", 360, 130),
            ms_word(6, "3", 360, 150),
            ms_word(6, "8(b)", 60, 190),
            ms_word(6, "B1", 360, 190),
            ms_word(6, "M1", 360, 210),
            ms_word(6, "2", 360, 230),
        ]
    }
    anchor = MarkSchemeAnchor("8(a)", 6, 90, 102, 60, "8(a)", table)
    next_anchor = MarkSchemeAnchor("9(a)", 6, 270, 282, 60, "9(a)", table)

    mark_total = _mark_total_for_question_block([layout], anchor, next_anchor, {6: table}, words_by_page)

    assert mark_total == 5


def test_mark_scheme_table_detection_ignores_earlier_non_answer_table() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=6,
        width=595,
        height=842,
        blocks=[
            cell(6, "Question", 80, x=45, width=55),
            cell(6, "Mark Scheme", 80, x=130, width=80),
            cell(6, "Rules", 80, x=390, width=45),
            cell(6, "1", 110, x=50, width=10),
            cell(6, "General rubric", 110, x=130, width=120),
            cell(6, "Question", 210, x=45, width=55),
            cell(6, "Answer", 210, x=130, width=50),
            cell(6, "Marks", 210, x=390, width=45),
            cell(6, "Guidance", 210, x=455, width=65),
            cell(6, "1", 245, x=50, width=10),
            cell(6, "x = 2", 245, x=130),
            cell(6, "B1", 245, x=390, width=25),
        ],
    )

    tables = _detect_mark_scheme_tables([layout], config)
    anchors = _detect_table_question_anchors([layout], tables, config, ["1"])

    assert list(tables) == [6]
    assert tables[6].header_detected == ["Question", "Answer", "Marks", "Guidance"]
    assert tables[6].header_bottom > 210
    assert [anchor.question_number for anchor in anchors] == ["1"]
    assert anchors[0].y0 == 245


def test_mark_scheme_table_crop_starts_at_target_row_and_keeps_full_width() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=6,
        width=595,
        height=842,
        blocks=[
            cell(6, "Question", 100, x=45, width=55),
            cell(6, "Answer", 100, x=130, width=50),
            cell(6, "Marks", 100, x=390, width=45),
            cell(6, "Guidance", 100, x=455, width=65),
            cell(6, "1", 140, x=50, width=10),
            cell(6, "Solution line", 140, x=130, width=120),
            cell(6, "M1", 140, x=390, width=25),
            cell(6, "Total", 172, x=130, width=45),
            cell(6, "5", 172, x=390, width=10),
            cell(6, "2", 210, x=50, width=10),
            cell(6, "Next question", 210, x=130, width=100),
        ],
    )

    tables = _detect_mark_scheme_tables([layout], config)
    anchors = _detect_table_question_anchors([layout], tables, config, ["1", "2"])
    regions, flags = _table_regions_for_anchor([layout], tables, anchors[0], anchors[1], config)

    assert not flags
    assert len(regions) == 1
    assert regions[0].bbox.x0 == tables[6].bbox.x0
    assert regions[0].bbox.x1 == tables[6].bbox.x1
    assert anchors[0].y0 - config.detection.crop_padding <= regions[0].bbox.y0 <= anchors[0].y0
    assert regions[0].bbox.y1 > 172
    assert regions[0].bbox.y1 < anchors[1].y0


def test_mark_scheme_table_crop_prefers_visible_ruling_lines() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=6,
        width=595,
        height=842,
        blocks=[
            cell(6, "Question", 100, x=45, width=55),
            cell(6, "Answer", 100, x=130, width=50),
            cell(6, "Marks", 100, x=390, width=45),
            cell(6, "Guidance", 100, x=455, width=65),
            cell(6, "1", 140, x=50, width=10),
            cell(6, "Solution line", 140, x=130, width=120),
            cell(6, "Total", 172, x=130, width=45),
            cell(6, "5", 172, x=390, width=10),
            cell(6, "2", 212, x=50, width=10),
            cell(6, "Next question", 212, x=130, width=100),
        ],
        graphics=[
            hline(95),
            hline(122),
            hline(162),
            hline(202),
            hline(230),
            vline(40),
            vline(120),
            vline(380),
            vline(445),
            vline(560),
        ],
    )

    tables = _detect_mark_scheme_tables([layout], config)
    anchors = _detect_table_question_anchors([layout], tables, config, ["1", "2"])
    regions, flags = _table_regions_for_anchor([layout], tables, anchors[0], anchors[1], config)

    assert not flags
    assert len(regions) == 1
    assert regions[0].bbox.x0 == 40
    assert regions[0].bbox.x1 == 560
    assert regions[0].bbox.y0 == 95
    assert regions[0].bbox.y1 == 202


def test_mark_scheme_crop_hard_stops_before_next_question_anchor() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=6,
        width=595,
        height=842,
        blocks=[
            cell(6, "Question", 100, x=45, width=55),
            cell(6, "Answer", 100, x=130, width=50),
            cell(6, "Marks", 100, x=390, width=45),
            cell(6, "Guidance", 100, x=455, width=65),
            cell(6, "1", 140, x=50, width=10),
            cell(6, "Solution line", 140, x=130, width=120),
            cell(6, "M1", 140, x=390, width=25),
            cell(6, "2", 210, x=50, width=10),
            cell(6, "Next question", 210, x=130, width=100),
        ],
    )

    tables = _detect_mark_scheme_tables([layout], config)
    anchors = _detect_table_question_anchors([layout], tables, config, ["1", "2"])
    regions, flags = _table_regions_for_anchor([layout], tables, anchors[0], anchors[1], config)

    assert not flags
    assert len(regions) == 1
    assert regions[0].bbox.y1 <= anchors[1].y0


def test_mark_scheme_text_uses_same_anchor_bounds_as_image_crop() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=6,
        width=595,
        height=842,
        blocks=[
            cell(6, "Question", 100, x=45, width=55),
            cell(6, "Answer", 100, x=130, width=50),
            cell(6, "Marks", 100, x=390, width=45),
            cell(6, "Guidance", 100, x=455, width=65),
            cell(6, "1", 135, x=50, width=10),
            cell(6, "Previous answer tail", 135, x=130, width=120),
            cell(6, "2", 210, x=50, width=10),
            cell(6, "Target first row", 210, x=130, width=120),
            cell(6, "Target continuation", 240, x=130, width=120),
            cell(6, "3", 300, x=50, width=10),
            cell(6, "Next answer row", 300, x=130, width=120),
        ],
    )

    tables = _detect_mark_scheme_tables([layout], config)
    anchors = _detect_table_question_anchors([layout], tables, config, ["1", "2", "3"])
    regions, flags = _table_regions_for_anchor([layout], tables, anchors[1], anchors[2], config)
    text_blocks = _blocks_for_table_anchor_bounds([layout], tables, anchors[1], anchors[2], config)
    text = "\n".join(block.text for block in text_blocks)

    assert not flags
    assert regions[0].bbox.y0 <= anchors[1].y0
    assert regions[0].bbox.y1 <= anchors[2].y0
    assert "Target first row" in text
    assert "Target continuation" in text
    assert "Previous answer tail" not in text
    assert "Next answer row" not in text


def test_mark_scheme_text_excludes_repeated_table_header_rows() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=6,
        width=595,
        height=842,
        blocks=[
            cell(6, "Question", 100, x=45, width=55),
            cell(6, "Answer", 100, x=130, width=50),
            cell(6, "Marks", 100, x=390, width=45),
            cell(6, "Guidance", 100, x=455, width=65),
            cell(6, "1", 135, x=50, width=10),
            cell(6, "Target answer", 135, x=130, width=120),
            cell(6, "B1", 135, x=390, width=25),
            cell(6, "Question  Answer  Marks  Guidance", 170, x=45, width=260),
            cell(6, "2", 230, x=50, width=10),
            cell(6, "Next answer", 230, x=130, width=120),
        ],
    )

    tables = _detect_mark_scheme_tables([layout], config)
    anchors = _detect_table_question_anchors([layout], tables, config, ["1", "2"])
    text_blocks = _blocks_for_table_anchor_bounds([layout], tables, anchors[0], anchors[1], config)
    text = "\n".join(block.text for block in text_blocks)

    assert "Target answer" in text
    assert "Question  Answer  Marks  Guidance" not in text


def test_question_subparts_preserve_roman_and_alpha_labels() -> None:
    text = "8 (i) First. [2]\n(ii) Second. [1]\n(iii) Third. [3]\n(iv) Fourth. [4]"

    assert _question_subparts_from_text(text) == ["i", "ii", "iii", "iv"]
    assert _question_subparts_from_text("7 (a) First. [5]\n(b) Second. [3]") == ["a", "b"]
    assert _question_subparts_from_text("9 (a)(i) Show that ... [3]\n(ii) Hence ... [2]\n(b) Final part. [4]") == ["a", "b"]
    assert _question_subparts_from_text("Find P(X = i) and compare with (ii) from the formula sheet.") == []


def test_mark_scheme_word_anchor_detection_rejects_far_right_false_boundary_row() -> None:
    table = MarkSchemeTable(
        page_number=6,
        bbox=BoundingBox(64, 50, 784, 530),
        question_col_right=140,
        marks_col_left=424,
        marks_col_right=528,
        header_bottom=70,
        confidence="high",
        header_detected=["Question", "Answer", "Marks", "Guidance"],
    )

    words = [
        ms_word(6, "1", 92, 80, width=8),
        ms_word(6, "B1", 500, 80, width=18),
        ms_word(6, "1", 127, 121, width=8),
        ms_word(6, "M1", 498, 121, width=18),
        ms_word(6, "2", 127, 137, width=8),
        ms_word(6, "5", 319, 137, width=8),
        ms_word(6, "2", 92, 301, width=8),
        ms_word(6, "B1", 500, 301, width=18),
    ]

    anchors = _detect_table_question_anchors_from_words(words, table, {"1", "2"}, {"1", "2"})

    assert [(anchor.question_number, round(anchor.y0)) for anchor in anchors] == [("1", 80), ("2", 301)]


def test_record_json_schema_matches_paper_first_output_contract(tmp_path: Path) -> None:
    record = QuestionRecord(
        source_pdf="paper.pdf",
        paper_name="paper",
        question_number="1",
        full_question_label="1(a)-(b)",
        screenshot_path="output/p1/12spring21/questions/q01.png",
        combined_question_text="Find x.",
        body_text_raw="Find x.",
        body_text_normalized="Find x.",
        math_lines=[],
        diagram_text=[],
        extraction_quality_score=0.95,
        extraction_quality_flags=[],
        part_texts=[],
        answer_text="x = 2",
        paper_family="P1",
        source_paper_family="P1",
        inferred_paper_family="P1",
        paper_family_confidence="high",
        topic="quadratics",
        subtopic="solving",
        topic_confidence="medium",
        topic_evidence="test fixture",
        secondary_topics=[],
        topic_uncertain=False,
        difficulty="easy",
        difficulty_confidence="high",
        difficulty_evidence="direct routine method",
        difficulty_uncertain=False,
        marks=3,
        marks_if_available=3,
        page_numbers=[1],
        review_flags=[],
        confidence=0.8,
        session="March",
        year="2021",
        component="12",
        source_paper_code="12",
        markscheme_image="output/p1/12spring21/mark_scheme/q01.png",
        markscheme_pages=[5],
        markscheme_marks_total=3,
        question_marks_total=3,
        question_subparts=["a", "b"],
        mark_scheme_source_pdf="paper_ms.pdf",
    )
    output = write_json([record], tmp_path / "records.json", output_root="output")
    data = output.read_text(encoding="utf-8")

    for key in [
        "question_id",
        "paper",
        "paper_family",
        "question_number",
        "question_text",
        "mark_scheme_text",
        "question_solution_marks",
        "subparts",
        "subparts_solution_marks",
        "question_image_paths",
        "mark_scheme_image_paths",
        "page_refs",
        "topic",
        "notes",
    ]:
        assert f'"{key}"' in data

    assert '"paper": "12spring21"' in data
    assert '"question_id": "12spring21_q01"' in data
    assert '"question_image_paths": [' in data
    assert '"p1/12spring21/questions/q01.png"' in data
    assert '"p1/12spring21/mark_scheme/q01.png"' in data


def test_prompt_crop_regions_split_large_answer_space_and_skip_next_question() -> None:
    config = AppConfig()
    config.detection.prompt_region_max_gap = 60
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[
            block(1, "1 Find the exact value of x. [3]", 100),
            block(1, "(b) Hence find y. [2]", 260, x=72),
            block(1, "2 Start of the next question [4]", 340),
            block(1, "Turn over", 790, x=260),
        ],
    )
    span = detect_question_spans([layout], Path("paper_qp.pdf"), config)[0]

    regions, flags = _detect_prompt_regions(span, [layout], config)

    assert len(regions) == 2
    assert "crop_split_prompt_regions" in flags
    rendered_text = "\n".join(block.text for region in regions for block in region.text_blocks)
    assert "Start of the next question" not in rendered_text
    assert "Turn over" not in rendered_text


def test_question_span_stops_before_additional_page_boilerplate() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[
            block(1, "1 Solve the equation. [3]", 100),
            block(1, "Show your working clearly.", 130),
            block(1, "Additional Page", 300),
            block(1, "If you use the following lined page to complete the answer, write the question number.", 330),
            block(1, "Unrelated lower-page content", 380),
        ],
    )

    span = detect_question_spans([layout], Path("paper_qp.pdf"), config)[0]

    assert "Additional Page" not in span.combined_text
    assert "Unrelated lower-page content" not in span.combined_text
    assert "excluded_boilerplate_additional_page" in span.review_flags


def test_question_starts_reject_impossible_component_question_numbers() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[
            block(1, "1 Start of mechanics paper. [3]", 100),
            block(1, "30 This is a footer or total mark artefact", 620),
        ],
    )

    spans = detect_question_spans([layout], Path("9709 Mathematics June 2025 Question Paper  41.pdf"), config)

    assert len(spans) == 1
    assert spans[0].question_number == "1"
    assert "30 This is a footer" not in spans[0].combined_text


def test_question_starts_ignore_cover_page_number_before_question_one() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[
            block(1, "9", 100),
            block(1, "You will need: List of formulae (MF19)", 125),
            block(1, "1 Solve the equation. [3]", 300),
            block(1, "2 Differentiate x^2. [2]", 430),
        ],
    )

    spans = detect_question_spans([layout], Path("9709 Mathematics November 2025 Question Paper  12.pdf"), config)

    assert [span.question_number for span in spans] == ["1", "2"]
    assert "You will need" not in spans[0].combined_text


def test_question_detection_skips_cover_instruction_page_anchors() -> None:
    config = AppConfig()
    cover = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[
            block(1, "7", 100),
            block(1, "* You will need: List of formulae (MF19)", 125),
            block(1, "INSTRUCTIONS", 180),
            block(1, "Answer all questions.", 205),
            block(1, "INFORMATION", 260),
            block(1, "The total mark for this paper is 50.", 285),
        ],
    )
    question_page = PageLayout(
        page_number=2,
        width=595,
        height=842,
        blocks=[
            block(2, "1 Find the probability. [3]", 100),
            block(2, "2 Find the mean. [4]", 240),
        ],
    )

    spans = detect_question_spans([cover, question_page], Path("9709 Mathematics November 2025 Question Paper  55.pdf"), config)

    assert [span.question_number for span in spans] == ["1", "2"]
    assert "INSTRUCTIONS" not in spans[0].combined_text


def test_question_span_excludes_lined_answer_page_region() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[
            block(1, "1 Find the value of k. [4]", 100),
            block(1, "Use exact values.", 130),
            block(1, "This text after the answer lines is boilerplate.", 360),
        ],
        graphics=[
            BoundingBox(45, 210, 545, 211),
            BoundingBox(45, 235, 545, 236),
            BoundingBox(45, 260, 545, 261),
            BoundingBox(45, 285, 545, 286),
            BoundingBox(45, 310, 545, 311),
        ],
    )

    span = detect_question_spans([layout], Path("paper_qp.pdf"), config)[0]

    assert "answer_line_space_excluded" in span.review_flags
    assert "This text after the answer lines" not in span.combined_text


def test_prompt_crop_deduplicates_overlapping_visual_regions() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[
            block(1, "1 The diagram shows a curve. [3]", 100),
            block(1, "Find the area under the curve.", 170),
        ],
        graphics=[
            BoundingBox(100, 120, 320, 250),
            BoundingBox(101, 121, 321, 251),
            BoundingBox(102, 122, 319, 249),
        ],
    )
    span = detect_question_spans([layout], Path("paper_qp.pdf"), config)[0]

    regions, flags = _detect_prompt_regions(span, [layout], config)

    assert "duplicate_visual_regions_removed" in flags
    assert sum(len(region.graphics) for region in regions) == 1
    assert sum(region.duplicate_graphics_removed for region in regions) == 2


def test_prompt_crop_excludes_page_furniture_graphics_and_trims_edges() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[
            block(1, "1 The diagram shows a curve. [3]", 110),
            block(1, "Find the gradient at A.", 150),
        ],
        graphics=[
            BoundingBox(500, 22, 570, 55),  # barcode-like top strip
            BoundingBox(0, 90, 24, 730),  # side margin panel
            BoundingBox(45, 230, 545, 231),  # answer line
            BoundingBox(120, 175, 340, 270),  # actual diagram
        ],
    )
    span = detect_question_spans([layout], Path("paper_qp.pdf"), config)[0]

    regions, flags = _detect_prompt_regions(span, [layout], config)

    assert {"barcode_excluded", "side_panel_excluded", "answer_lines_excluded"} <= set(flags)
    assert len(regions) == 2
    assert [region.region_kind for region in regions] == ["text", "figure"]
    assert regions[0].bbox.y1 <= regions[1].bbox.y0
    assert regions[0].text_trimmed_for_figure
    assert regions[0].bbox.x0 >= config.detection.crop_left_margin
    assert regions[0].bbox.x1 <= layout.width - config.detection.crop_right_margin
    assert [item["label"] for item in regions[0].excluded_regions] == ["barcode", "side_panel", "answer_lines"]


def test_prompt_crop_separates_text_and_figure_without_overlap() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[
            block(1, "1 The figure shows a graph. [4]", 100),
            block(1, "Find the gradient of the tangent.", 150),
            block(1, "State the intercept.", 305),
        ],
        graphics=[
            BoundingBox(120, 180, 360, 285),
            BoundingBox(121, 181, 361, 286),
        ],
    )
    span = detect_question_spans([layout], Path("paper_qp.pdf"), config)[0]

    regions, flags = _detect_prompt_regions(span, [layout], config)

    assert "figure_region_separated" in flags
    assert "text_figure_overlap_trimmed" in flags
    assert "duplicate_visual_regions_removed" in flags
    assert [region.region_kind for region in regions] == ["text", "figure", "text"]
    assert regions[0].bbox.y1 <= regions[1].bbox.y0
    assert regions[1].bbox.y1 <= regions[2].bbox.y0
    assert regions[1].graphics
    assert sum(region.duplicate_graphics_removed for region in regions) == 1


def test_question_span_excludes_margin_text_and_control_artifacts() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[
            block(1, "1 Find x. [2]", 100),
            TextBlock(
                page_number=1,
                text="DO NOT WRITE IN THIS MARGIN",
                bbox=BoundingBox(4, 120, 34, 520),
            ),
            block(1, ",\x01\x01\x01\x01", 180),
            block(1, "2 Next question. [3]", 260),
        ],
    )

    span = detect_question_spans([layout], Path("paper_qp.pdf"), config)[0]

    assert "DO NOT WRITE" not in span.combined_text
    assert "\x01" not in span.combined_text


def test_question_start_keeps_meaningful_text_with_pdf_control_chars() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[
            block(1, "1 (a) Find the first three terms of \x001 + x\x01^{5}. [1]", 100),
            block(1, "2 Next question. [3]", 260),
        ],
    )

    spans = detect_question_spans([layout], Path("9709_s21_qp_12.pdf"), config)

    assert [span.question_number for span in spans] == ["1", "2"]
    assert "\x01" not in spans[0].combined_text
    assert "1 + x" in spans[0].combined_text


def test_question_starts_skip_large_jump_when_next_expected_question_exists() -> None:
    config = AppConfig()
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[
            block(1, "1 First question. [2]", 80),
            block(1, "2 Second question asks about", 170),
            block(1, "8 letters in the word COCOONED. [1]", 195, x=96),
            block(1, "3 Third question. [4]", 300),
        ],
    )

    spans = detect_question_spans([layout], Path("9709_s23_qp_51.pdf"), config)

    assert [span.question_number for span in spans] == ["1", "2", "3"]
