from pathlib import Path

from exam_bank.topic_pdfs import DIFFICULTY_SECTIONS, _group_by_topic, _sorted_questions, _valid_questions


def test_topic_pdf_validation_groups_and_sorts_records(tmp_path: Path) -> None:
    image_a = tmp_path / "a.png"
    image_b = tmp_path / "b.png"
    image_a.write_bytes(b"not checked here")
    image_b.write_bytes(b"not checked here")
    records = [
        {
            "topic": "calculus",
            "subtopic": "integration",
            "difficulty": "average",
            "screenshot_path": str(image_b),
            "paper_name": "paper_b",
            "question_number": "10",
            "marks_if_available": 6,
        },
        {
            "topic": "calculus",
            "subtopic": "differentiation",
            "difficulty": "average",
            "screenshot_path": str(image_a),
            "paper_name": "paper_a",
            "question_number": "2",
            "marks_if_available": 4,
        },
    ]

    valid, review_items = _valid_questions(records)
    grouped = _group_by_topic(valid)
    sorted_questions = _sorted_questions(grouped["calculus"])

    assert not review_items
    assert DIFFICULTY_SECTIONS["average"] == "Medium"
    assert list(grouped) == ["calculus"]
    assert [question.question_number for question in sorted_questions] == ["2", "10"]


def test_topic_pdf_validation_flags_missing_metadata() -> None:
    records = [
        {"topic": "", "difficulty": "easy", "screenshot_path": "missing.png"},
        {"topic": "vectors", "difficulty": "", "screenshot_path": "missing.png"},
        {"topic": "vectors", "difficulty": "easy", "screenshot_path": ""},
    ]

    valid, review_items = _valid_questions(records)

    assert not valid
    assert [item.issue_type for item in review_items] == [
        "topic_pdf_missing_topic",
        "topic_pdf_missing_difficulty",
        "topic_pdf_missing_image",
    ]
