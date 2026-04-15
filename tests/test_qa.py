import json
from pathlib import Path

import pytest

from exam_bank.qa import run_qa


def _write_image(path: Path, *, blank: bool = False) -> None:
    pytest.importorskip("PIL")
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (640, 240), "white")
    if not blank:
        draw = ImageDraw.Draw(image)
        draw.rectangle((24, 24, 616, 216), outline="black", width=3)
        draw.line((48, 82, 592, 82), fill="black", width=2)
        draw.line((48, 142, 592, 142), fill="black", width=2)
        draw.text((54, 48), "Question | Answer | Marks | Guidance", fill="black")
        draw.text((54, 110), "1 Find x. [2]", fill="black")
    image.save(path)


def test_qa_passes_clean_p1_record(tmp_path: Path) -> None:
    source_pdf = tmp_path / "9709_s21_qp_12.pdf"
    source_pdf.write_bytes(b"%PDF-1.4\n")
    question_image = tmp_path / "question.png"
    markscheme_image = tmp_path / "markscheme.png"
    _write_image(question_image)
    _write_image(markscheme_image)

    question_bank = tmp_path / "question_bank.json"
    question_bank.write_text(
        json.dumps(
            [
                {
                    "source_pdf": str(source_pdf),
                    "paper_name": "9709_s21_qp_12",
                    "question_number": "1",
                    "paper_family": "P1",
                    "source_paper_family": "P1",
                    "inferred_paper_family": "P1",
                    "topic": "quadratics",
                    "question_image": str(question_image),
                    "markscheme_image": str(markscheme_image),
                    "question_crop_confidence": "high",
                    "markscheme_crop_confidence": "high",
                    "markscheme_table_detected": True,
                    "markscheme_table_header_detected": ["Question", "Answer", "Marks", "Guidance"],
                    "markscheme_question_number": "1",
                    "markscheme_nearby_anchors": ["1", "2"],
                    "combined_question_text": "1 Solve the quadratic equation. [2]",
                    "markscheme_text": "Question Answer Marks Guidance",
                    "review_flags": [],
                }
            ]
        ),
        encoding="utf-8",
    )

    result = run_qa(question_bank, tmp_path / "qa")

    assert result.records[0]["qa_status"] == "pass"
    assert result.records[0]["qa_flags"] == []
    assert result.json_path.exists()
    assert result.csv_path.exists()
    assert result.review_path.exists()


def test_qa_flags_bad_record_and_skips_p2(tmp_path: Path) -> None:
    source_pdf = tmp_path / "9709_s21_qp_12.pdf"
    source_pdf.write_bytes(b"%PDF-1.4\n")
    blank_question = tmp_path / "blank_question.png"
    _write_image(blank_question, blank=True)

    question_bank = tmp_path / "question_bank.json"
    question_bank.write_text(
        json.dumps(
            [
                {
                    "source_pdf": str(source_pdf),
                    "paper_name": "9709_s21_qp_12",
                    "question_number": "",
                    "paper_family": "P1",
                    "source_paper_family": "P1",
                    "topic": "vectors",
                    "question_image": str(blank_question),
                    "markscheme_image": "",
                    "question_crop_confidence": "low",
                    "combined_question_text": "Turn over",
                    "review_flags": ["header_footer_contamination"],
                },
                {
                    "source_pdf": str(source_pdf),
                    "question_number": "2",
                    "paper_family": "P2",
                    "topic": "integration",
                },
            ]
        ),
        encoding="utf-8",
    )

    result = run_qa(question_bank, tmp_path / "qa")

    assert len(result.records) == 1
    record = result.records[0]
    assert record["qa_status"] == "fail"
    assert "missing_question_number" in record["qa_flags"]
    assert "invalid_topic_for_paper" in record["qa_flags"]
    assert "question_crop_blank" in record["qa_flags"]
    assert "missing_markscheme_image" in record["qa_flags"]
    assert "possible_footer_in_question_crop" in record["qa_flags"]
    assert result.summary["skipped_record_count"] == 1
    assert result.skipped_records[0]["paper_family"] == "P2"


def test_qa_only_failed_filters_written_records(tmp_path: Path) -> None:
    source_pdf = tmp_path / "9709_s21_qp_12.pdf"
    source_pdf.write_bytes(b"%PDF-1.4\n")
    question_image = tmp_path / "question.png"
    markscheme_image = tmp_path / "markscheme.png"
    _write_image(question_image)
    _write_image(markscheme_image)

    question_bank = tmp_path / "question_bank.json"
    question_bank.write_text(
        json.dumps(
            [
                {
                    "source_pdf": str(source_pdf),
                    "question_number": "1",
                    "paper_family": "P1",
                    "source_paper_family": "P1",
                    "topic": "quadratics",
                    "question_image": str(question_image),
                    "markscheme_image": str(markscheme_image),
                    "question_crop_confidence": "high",
                    "markscheme_crop_confidence": "high",
                    "markscheme_table_detected": True,
                    "markscheme_table_header_detected": ["Question", "Answer", "Marks", "Guidance"],
                    "markscheme_question_number": "1",
                    "markscheme_nearby_anchors": ["1"],
                },
                {
                    "source_pdf": "",
                    "question_number": "2",
                    "paper_family": "P1",
                    "topic": "quadratics",
                    "question_image": str(question_image),
                    "markscheme_image": str(markscheme_image),
                    "question_crop_confidence": "high",
                    "markscheme_crop_confidence": "high",
                },
            ]
        ),
        encoding="utf-8",
    )

    result = run_qa(question_bank, tmp_path / "qa", only_failed=True)
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))

    assert result.summary["validated_record_count"] == 2
    assert result.summary["written_record_count"] == 1
    assert len(payload["records"]) == 1
    assert payload["records"][0]["qa_status"] == "fail"
