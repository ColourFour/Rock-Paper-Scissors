from pathlib import Path

from exam_bank.config import AppConfig
from exam_bank.exporters import write_csv, write_json
from exam_bank.image_rendering import _detect_prompt_regions
from exam_bank.mark_schemes import find_mark_scheme
from exam_bank.models import BoundingBox, PageLayout, QuestionRecord, TextBlock
from exam_bank.question_detection import detect_question_spans, extract_marks_from_text, parse_question_start


def block(page: int, text: str, y: float, x: float = 50) -> TextBlock:
    return TextBlock(page_number=page, text=text, bbox=BoundingBox(x, y, x + 300, y + 12))


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
        topic="algebra",
        subtopic="quadratics",
        topic_confidence="medium",
        topic_evidence="test fixture",
        secondary_topics=[],
        topic_uncertain=False,
        difficulty="easy",
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
        "screenshot_path",
        "combined_question_text",
        "answer_text",
        "paper_family",
        "question_level_paper_family",
        "question_level_topic",
        "question_level_subtopic",
        "part_level_topics",
        "topic",
        "subtopic",
        "topic_confidence",
        "topic_evidence",
        "secondary_topics",
        "topic_uncertain",
        "topic_alternatives",
        "difficulty",
        "marks",
        "marks_if_available",
        "page_numbers",
        "review_flags",
        "confidence",
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
        topic="algebra",
        subtopic="quadratics",
        topic_confidence="medium",
        topic_evidence="test fixture",
        secondary_topics=[],
        topic_uncertain=False,
        difficulty="easy",
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
