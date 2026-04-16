import json
from pathlib import Path

from exam_bank.config import AppConfig
from exam_bank.manual_review import apply_manual_review, build_manual_review_page


def test_manual_review_page_embeds_records_topics_and_relative_images(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    images_dir = tmp_path / "output" / "images"
    images_dir.mkdir(parents=True)
    (images_dir / "question.png").write_bytes(b"question")
    (images_dir / "markscheme.png").write_bytes(b"markscheme")
    question_bank = tmp_path / "output" / "json" / "question_bank.json"
    question_bank.parent.mkdir(parents=True)
    question_bank.write_text(
        json.dumps(
            [
                {
                    "question_id": "p1-q1",
                    "source_pdf": "input/question_papers/9709_s21_qp_12.pdf",
                    "paper_family": "P1",
                    "topic": "quadratics",
                    "difficulty": "average",
                    "question_number": "1",
                    "marks_if_available": 4,
                    "question_image": "output/images/question.png",
                    "markscheme_image": "output/images/markscheme.png",
                }
            ]
        ),
        encoding="utf-8",
    )
    config = AppConfig()

    result = build_manual_review_page(question_bank, tmp_path / "output" / "manual_review", config)
    html = result.html_path.read_text(encoding="utf-8")

    assert result.record_count == 1
    assert "window.MANUAL_REVIEW_RECORDS =" in html
    assert "window.TOPICS_BY_PAPER =" in html
    assert "fetch(" not in html
    assert "../images/question.png" in html
    assert "../images/markscheme.png" in html
    assert "Manual topic" in html
    assert "Manual difficulty" in html
    assert "Flag unusable" in html
    assert "Export review JSON" in html
    assert "examBankManualReview:v1" in html


def test_apply_manual_review_overrides_topic_difficulty_and_student_usability(tmp_path: Path) -> None:
    question_bank = tmp_path / "question_bank.json"
    question_bank.write_text(
        json.dumps(
            [
                {
                    "question_id": "p1-q1",
                    "paper_family": "P1",
                    "topic": "functions",
                    "question_level_topic": "functions",
                    "difficulty": "easy",
                    "question_number": "1",
                    "question_image": "output/images/question.png",
                    "markscheme_image": "output/images/markscheme.png",
                    "review_flags": [],
                }
            ]
        ),
        encoding="utf-8",
    )
    review_json = tmp_path / "manual_review.json"
    review_json.write_text(
        json.dumps(
            {
                "version": 1,
                "reviews": {
                    "p1-q1": {
                        "manual_topic": "quadratics",
                        "manual_difficulty": "medium",
                        "usable": False,
                        "crop_status": "bad",
                        "notes": "Repeated diagram.",
                        "reviewed_at": "2026-04-16T00:00:00.000Z",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = apply_manual_review(question_bank, review_json, tmp_path / "question_bank_reviewed.json")
    merged = json.loads(result.output_json_path.read_text(encoding="utf-8"))

    assert result.matched_reviews == 1
    assert result.unmatched_reviews == 0
    assert merged[0]["auto_topic"] == "functions"
    assert merged[0]["topic"] == "quadratics"
    assert merged[0]["question_level_topic"] == "quadratics"
    assert merged[0]["manual_difficulty"] == "medium"
    assert merged[0]["difficulty"] == "average"
    assert merged[0]["usable"] is False
    assert merged[0]["student_usable"] is False
    assert merged[0]["crop_status"] == "bad"
    assert merged[0]["manual_notes"] == "Repeated diagram."
    assert "manual_review_applied" in merged[0]["review_flags"]
    assert "manual_excluded_from_student_practice" in merged[0]["review_flags"]
