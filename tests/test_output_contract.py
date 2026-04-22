from pathlib import Path
import json

from exam_bank.config import AppConfig
from exam_bank.exporters import export_records
from exam_bank.models import QuestionRecord
from exam_bank.output_layout import mark_scheme_image_output_path, paper_instance_id, question_image_output_path


def _record() -> QuestionRecord:
    return QuestionRecord(
        source_pdf="input/question_papers/9709 Mathematics March 2021 Question paper  12.pdf",
        paper_name="9709_Mathematics_March_2021_Question_paper_12",
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
        topic="binomial_expansion",
        subtopic="general",
        topic_confidence="high",
        topic_evidence="fixture",
        secondary_topics=[],
        topic_uncertain=False,
        difficulty="easy",
        difficulty_confidence="high",
        difficulty_evidence="fixture",
        difficulty_uncertain=False,
        marks=3,
        marks_if_available=3,
        page_numbers=[3, 4],
        review_flags=["markscheme_parent_label_match"],
        confidence=0.8,
        session="March",
        year="2021",
        component="12",
        source_paper_code="12",
        markscheme_image="output/p1/12spring21/mark_scheme/q01.png",
        markscheme_pages=[6],
        markscheme_mapping_status="pass",
        question_marks_total=3,
        markscheme_marks_total=3,
        question_subparts=["a", "b"],
        mark_scheme_source_pdf="input/mark_schemes/9709 Mathematics March 2021 Mark Scheme  12.pdf",
    )


def test_paper_first_image_paths_follow_family_paper_questions_and_mark_scheme_layout(tmp_path: Path) -> None:
    config = AppConfig()
    config.output.apply_root(tmp_path / "output")

    qp_path = question_image_output_path(
        "input/question_papers/9709 Mathematics March 2021 Question paper  12.pdf",
        "1",
        config,
    )
    ms_path = mark_scheme_image_output_path(
        "input/mark_schemes/9709 Mathematics March 2021 Mark Scheme  12.pdf",
        "1",
        config,
    )

    assert paper_instance_id("12", "March", "2021") == "12spring21"
    assert qp_path == tmp_path / "output" / "p1" / "12spring21" / "questions" / "q01.png"
    assert ms_path == tmp_path / "output" / "p1" / "12spring21" / "mark_scheme" / "q01.png"


def test_export_records_writes_json_under_output_json_only(tmp_path: Path) -> None:
    config = AppConfig()
    config.output.apply_root(tmp_path / "output")
    record = _record()
    record.screenshot_path = str(tmp_path / "output" / "p1" / "12spring21" / "questions" / "q01.png")
    record.markscheme_image = str(tmp_path / "output" / "p1" / "12spring21" / "mark_scheme" / "q01.png")

    json_path = export_records([record], config)
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert json_path == tmp_path / "output" / "json" / "question_bank.json"
    assert json_path.exists()
    assert payload[0]["question_image_paths"] == ["p1/12spring21/questions/q01.png"]
    assert payload[0]["mark_scheme_image_paths"] == ["p1/12spring21/mark_scheme/q01.png"]
    assert not (tmp_path / "output" / "csv").exists()
    assert not (tmp_path / "output" / "review").exists()
