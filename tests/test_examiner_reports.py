from pathlib import Path

import pytest

from exam_bank.config import AppConfig
from exam_bank.examiner_reports import examiner_report_evidence, examiner_report_topic_evidence


def test_examiner_report_evidence_is_restricted_to_target_paper_section(tmp_path: Path) -> None:
    report = tmp_path / "9709 Mathematics November 2025 Examiner Report.txt"
    report.write_text(
        """
Paper 9709/12

Comments on specific questions

Question 1
Used the discriminant of a quadratic.

Paper 9709/32

Comments on specific questions

Question 1
Used integration by parts.
""",
        encoding="utf-8",
    )

    evidence = examiner_report_evidence(
        "9709 Mathematics November 2025 Question Paper 32.pdf",
        tmp_path / "missing",
        "1",
        report_paths=[report],
    )

    assert "integration by parts" in evidence
    assert "discriminant" not in evidence


def test_examiner_report_evidence_reads_session_level_pdf(tmp_path: Path) -> None:
    fitz = pytest.importorskip("fitz")
    report = tmp_path / "9709 Mathematics November 2025 Examiner Report.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        """
Paper 9709/12

Comments on specific questions

Question 1
Used the discriminant of a quadratic.

Paper 9709/32

Comments on specific questions

Question 1
Used integration by parts.
""",
    )
    doc.save(report)
    doc.close()

    evidence = examiner_report_evidence(
        "9709 Mathematics November 2025 Question Paper 32.pdf",
        tmp_path,
        "1",
    )

    assert "integration by parts" in evidence
    assert "discriminant" not in evidence


def test_examiner_report_evidence_requires_comments_on_specific_questions(tmp_path: Path) -> None:
    report = tmp_path / "9709 Mathematics November 2025 Examiner Report.txt"
    report.write_text(
        """
Paper 9709/12

General comments

Question 1
This should not be used as question-level evidence.
""",
        encoding="utf-8",
    )

    evidence = examiner_report_evidence(
        "9709 Mathematics November 2025 Question Paper 12.pdf",
        tmp_path / "missing",
        "1",
        report_paths=[report],
    )

    assert evidence == ""


def test_examiner_report_subpart_match_does_not_cross_to_other_subpart(tmp_path: Path) -> None:
    report = tmp_path / "9709 Mathematics November 2025 Examiner Report.txt"
    report.write_text(
        """
Paper 9709/12

Comments on specific questions

Question 3(a)
Candidates substituted the line into the circle.

Question 3(b)
Candidates used a sequence of transformations.
""",
        encoding="utf-8",
    )

    evidence = examiner_report_evidence(
        "9709 Mathematics November 2025 Question Paper 12.pdf",
        tmp_path / "missing",
        "3(b)",
        report_paths=[report],
    )

    assert "sequence of transformations" in evidence
    assert "circle" not in evidence


def test_examiner_report_json_requires_paper_scope(tmp_path: Path) -> None:
    report = tmp_path / "9709 Mathematics November 2025 Examiner Report.json"
    report.write_text(
        """
{
  "Paper 9709/12": {
    "1": {"text": "Used the discriminant of a quadratic."}
  },
  "Paper 9709/32": {
    "1": {"text": "Used integration by parts."}
  }
}
""",
        encoding="utf-8",
    )

    evidence = examiner_report_evidence(
        "9709 Mathematics November 2025 Question Paper 32.pdf",
        tmp_path / "missing",
        "1",
        report_paths=[report],
    )

    assert "integration by parts" in evidence
    assert "discriminant" not in evidence


def test_examiner_report_topic_evidence_extracts_cues_and_canonical_topic(tmp_path: Path) -> None:
    report = tmp_path / "9709 Mathematics November 2025 Examiner Report.txt"
    report.write_text(
        """
Paper 9709/12

Comments on specific questions

Question 1
Most candidates used elimination leading to a quadratic and then considered the discriminant.
Some candidates made the common error of using the wrong sign.
""",
        encoding="utf-8",
    )

    evidence = examiner_report_topic_evidence(
        "9709 Mathematics November 2025 Question Paper 12.pdf",
        tmp_path / "missing",
        "1",
        AppConfig(),
        report_paths=[report],
    )

    assert evidence is not None
    assert evidence.paper_code == "12"
    assert evidence.question_number == "1"
    assert evidence.canonical_topic == "quadratics"
    assert "discriminant" in evidence.mathematical_cues
    assert "eliminate" in evidence.methods_skills
    assert evidence.common_errors
    assert "quadratic" in evidence.classification_text


def test_examiner_report_topic_evidence_keeps_subpart_and_linked_hints(tmp_path: Path) -> None:
    report = tmp_path / "9709 Mathematics November 2025 Examiner Report.txt"
    report.write_text(
        """
Paper 9709/12

Comments on specific questions

Question 4(a)
Candidates needed to substitute the line into the circle and find the tangent.

Question 4(b)
The word Hence was important; candidates needed to use the result from part (a).
""",
        encoding="utf-8",
    )

    evidence = examiner_report_topic_evidence(
        "9709 Mathematics November 2025 Question Paper 12.pdf",
        tmp_path / "missing",
        "4(b)",
        AppConfig(),
        report_paths=[report],
    )

    assert evidence is not None
    assert evidence.subpart == "b"
    assert evidence.canonical_topic in AppConfig().paper_family_taxonomy["P1"]
    assert evidence.linked_question_hints
