from pathlib import Path

import pytest

from exam_bank.config import AppConfig
from exam_bank.topic_pdfs import (
    DIFFICULTY_SECTIONS,
    _group_by_topic,
    _sorted_questions,
    _valid_questions,
    build_topic_pdfs,
)


def test_topic_pdf_validation_groups_and_sorts_records(tmp_path: Path) -> None:
    image_a = tmp_path / "a.png"
    image_b = tmp_path / "b.png"
    markscheme_a = tmp_path / "ms_a.png"
    image_a.write_bytes(b"not checked here")
    image_b.write_bytes(b"not checked here")
    markscheme_a.write_bytes(b"not checked here")
    records = [
        {
            "topic": "calculus",
            "subtopic": "integration",
            "difficulty": "average",
            "screenshot_path": str(image_b),
            "markscheme_image": str(markscheme_a),
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
    assert sorted_questions[1].markscheme_image_path == markscheme_a


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


def test_topic_pdf_validation_excludes_manual_unusable_records(tmp_path: Path) -> None:
    image = tmp_path / "q.png"
    image.write_bytes(b"not checked here")
    records = [
        {
            "topic": "calculus",
            "difficulty": "easy",
            "question_image": str(image),
            "paper_name": "paper_a",
            "question_number": "1",
            "student_usable": False,
        },
        {
            "topic": "calculus",
            "difficulty": "easy",
            "question_image": str(image),
            "paper_name": "paper_a",
            "question_number": "2",
            "crop_status": "bad",
        },
    ]

    valid, review_items = _valid_questions(records)

    assert not valid
    assert [item.issue_type for item in review_items] == [
        "topic_pdf_manual_excluded",
        "topic_pdf_manual_excluded",
    ]


def test_topic_pdf_embeds_mark_scheme_pages_and_internal_links(tmp_path: Path) -> None:
    pil_image = pytest.importorskip("PIL.Image")
    pytest.importorskip("reportlab")
    fitz = pytest.importorskip("fitz")

    question_a = tmp_path / "q_a.png"
    question_b = tmp_path / "q_b.png"
    markscheme_a = tmp_path / "markscheme_a.png"
    for path in [question_a, question_b, markscheme_a]:
        image = pil_image.new("RGB", (200, 80), "white")
        image.save(path)

    config = AppConfig()
    config.topic_pdfs.topic_pdf_output_dir = tmp_path / "topic_pdfs"
    config.topic_pdfs.embed_mark_schemes = True
    records = [
        {
            "topic": "calculus",
            "difficulty": "easy",
            "question_image": str(question_a),
            "markscheme_image": str(markscheme_a),
            "paper_name": "paper_a",
            "question_number": "1",
        },
        {
            "topic": "calculus",
            "difficulty": "easy",
            "question_image": str(question_b),
            "paper_name": "paper_a",
            "question_number": "2",
        },
    ]

    result = build_topic_pdfs(records, config)

    assert len(result.pdf_paths) == 1
    assert result.pdf_paths[0].exists()
    assert result.mark_scheme_link_count == 1
    assert result.missing_mark_scheme_link_count == 1

    with fitz.open(result.pdf_paths[0]) as pdf:
        assert pdf.page_count == 3
        links = []
        for page in pdf:
            links.extend(page.get_links())
        assert links
        assert all(link.get("kind") != fitz.LINK_URI for link in links)
        assert all("uri" not in link for link in links)
        text = "\n".join(page.get_text() for page in pdf)
    assert "Go to mark scheme" in text
    assert "Back to question" in text
    assert "Mark scheme image unavailable" in text
