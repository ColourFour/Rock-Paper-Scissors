from pathlib import Path

from exam_bank.config import AppConfig
from exam_bank.exporters import write_csv, write_json
from exam_bank.identifiers import normalize_question_id
from exam_bank.image_rendering import _detect_prompt_regions
from exam_bank.mark_schemes import _detect_mark_scheme_tables, _detect_table_question_anchors, _parse_mark_scheme_question_cell, _table_regions_for_anchor, find_mark_scheme
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
