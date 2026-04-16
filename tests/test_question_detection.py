from pathlib import Path

from exam_bank.config import AppConfig
from exam_bank.exporters import write_csv, write_json
from exam_bank.identifiers import normalize_question_id
from exam_bank.image_rendering import _detect_prompt_regions
from exam_bank.mark_schemes import (
    _detect_mark_scheme_tables,
    _detect_table_question_anchors,
    _mark_total_for_question_block,
    _parse_mark_scheme_question_cell,
    _table_regions_for_anchor,
    _validate_mark_scheme_mapping,
    find_mark_scheme,
)
from exam_bank.models import BoundingBox, PageLayout, QuestionRecord, TextBlock
from exam_bank.question_detection import detect_question_spans, extract_marks_from_text, parse_question_start


def block(page: int, text: str, y: float, x: float = 50) -> TextBlock:
    return TextBlock(page_number=page, text=text, bbox=BoundingBox(x, y, x + 300, y + 12))


def cell(page: int, text: str, y: float, x: float, width: float = 45) -> TextBlock:
    return TextBlock(page_number=page, text=text, bbox=BoundingBox(x, y, x + width, y + 12))


def hline(y: float, x0: float = 40, x1: float = 560) -> BoundingBox:
    return BoundingBox(x0, y, x1, y + 1)


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


def test_extract_marks_sums_bracketed_marks() -> None:
    assert extract_marks_from_text("Find x. [2]\nHence find y. [3]") == 5
    assert extract_marks_from_text("No mark shown") is None


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
    assert regions[0].bbox.y0 < 105
    assert regions[0].bbox.y1 > 195
    assert regions[0].bbox.y1 < 220
    assert regions[0].bbox.x0 <= tables[6].bbox.x0
    assert regions[0].bbox.x1 >= tables[6].bbox.x1
    assert regions[0].continuation_rows_included


def test_mark_scheme_answer_table_before_page_6_is_rejected() -> None:
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

    assert _detect_mark_scheme_tables([layout], config) == {}


def test_question_id_normalization_preserves_subparts() -> None:
    assert normalize_question_id("3 a") == "3(a)"
    assert normalize_question_id("3(a)") == "3(a)"
    assert normalize_question_id("3a") == "3(a)"
    assert normalize_question_id("Question 3(a)") == "3(a)"
    assert _parse_mark_scheme_question_cell("3(b)", {"3(b)"}) == "3(b)"


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
    assert validation_flags == ["missing_subparts"]
    assert reason == "missing_subparts"

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

    assert validation_flags == ["marks_total_mismatch"]
    assert reason == "marks_total_mismatch"


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


def test_mark_scheme_table_crop_includes_header_row_and_full_width() -> None:
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
    assert regions[0].bbox.y0 <= tables[6].bbox.y0
    assert regions[0].bbox.y0 < anchors[0].y0
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


def test_record_json_schema_contains_required_fields(tmp_path: Path) -> None:
    record = QuestionRecord(
        source_pdf="paper.pdf",
        paper_name="paper",
        question_number="1",
        full_question_label="1(a)-(b)",
        screenshot_path="output/images/paper_q01.png",
        combined_question_text="Find x.",
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
    )
    output = write_json([record], tmp_path / "records.json")
    data = output.read_text(encoding="utf-8")

    for key in [
        "source_pdf",
        "paper_name",
        "question_number",
        "full_question_label",
        "question_image",
        "question_pages",
        "question_crop_confidence",
        "screenshot_path",
        "combined_question_text",
        "answer_text",
        "paper_family",
        "source_paper_code",
        "source_paper_family",
        "inferred_paper_family",
        "paper_family_confidence",
        "question_level_paper_family",
        "question_level_topic",
        "question_level_subtopic",
        "part_level_topics",
        "topic",
        "subtopic",
        "topic_confidence",
        "topic_confidence_score",
        "topic_evidence",
        "topic_evidence_details",
        "secondary_topics",
        "topic_uncertain",
        "topic_alternatives",
        "difficulty",
        "difficulty_confidence",
        "difficulty_evidence",
        "difficulty_uncertain",
        "marks",
        "marks_if_available",
        "page_numbers",
        "review_flags",
        "confidence",
        "markscheme_text",
        "markscheme_image",
        "markscheme_pages",
        "markscheme_question_number",
        "markscheme_crop_confidence",
        "markscheme_mapping_method",
        "markscheme_table_detected",
        "markscheme_table_header_detected",
        "markscheme_nearby_anchors",
        "markscheme_debug_paths",
        "markscheme_table_header_ok",
        "mark_scheme",
        "qa",
    ]:
        assert f'"{key}"' in data


def test_csv_is_image_first_and_omits_question_text(tmp_path: Path) -> None:
    record = QuestionRecord(
        source_pdf="paper.pdf",
        paper_name="paper",
        question_number="1",
        full_question_label="1(a)-(b)",
        screenshot_path="output/images/paper_q01.png",
        combined_question_text="This should stay out of the CSV.",
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
    )

    output = write_csv([record], tmp_path / "records.csv")
    data = output.read_text(encoding="utf-8")

    assert "question_image" in data
    assert "question_image_link" in data
    assert "paper_family" in data
    assert "source_paper_code" in data
    assert "source_paper_family" in data
    assert "question_pages" in data
    assert "question_crop_confidence" in data
    assert "difficulty_confidence" in data
    assert "markscheme_image" in data
    assert "markscheme_table_header_detected" in data
    assert "question_level_paper_family" in data
    assert "question_level_topic" in data
    assert "part_level_topics" in data
    assert "output/images/paper_q01.png" in data
    assert "combined_question_text" not in data
    assert "This should stay out of the CSV." not in data


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
    assert len(regions) == 1
    assert regions[0].bbox.x0 >= config.detection.crop_left_margin
    assert regions[0].bbox.x1 <= layout.width - config.detection.crop_right_margin
    assert [item["label"] for item in regions[0].excluded_regions] == ["barcode", "side_panel", "answer_lines"]


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
