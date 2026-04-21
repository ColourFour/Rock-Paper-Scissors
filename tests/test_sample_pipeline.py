from pathlib import Path

import pytest

from exam_bank.config import AppConfig
from exam_bank.pipeline import process_sample


SAMPLE_QP = Path(
    "/Users/sbrooker/Favorite/Former Classes/RCF 2024-2025/AS Maths/00 General/Math A Level Exams All/March 2019_qp_32.pdf"
)
SAMPLE_MS = Path(
    "/Users/sbrooker/Favorite/Former Classes/RCF 2024-2025/AS Maths/00 General/Math A Level Exams All/March 2019_ms_32.pdf"
)
REPO_SAMPLE_QP = Path("input/question_papers/March 2019 Exam Paper P1 (2).pdf")
REPO_SAMPLE_MS = Path("input/mark_schemes/March 2019 Mark Scheme P1 (2).pdf")
REPO_S24_P3_QP = Path("input/question_papers/9709_s24_qp_33.pdf")
REPO_S24_P3_MS = Path("input/mark_schemes/9709_s24_ms_33.pdf")
REPO_N25_P5_QP = Path("input/question_papers/9709 Mathematics November 2025 Question Paper  53.pdf")
REPO_N25_P5_MS = Path("input/mark_schemes/9709 Mathematics November 2025 Mark Scheme  53.pdf")
REPO_N23_P41_QP = Path("input/question_papers/9709 Mathematics November 2023 Question paper  41.pdf")
REPO_N23_P41_MS = Path("input/mark_schemes/9709 Mathematics November 2023 Mark Scheme  41.pdf")
REPO_J24_P51_QP = Path("input/question_papers/9709 Mathematics June 2024 Question paper  51.pdf")
REPO_J24_P51_MS = Path("input/mark_schemes/9709 Mathematics June 2024 Mark Scheme  51.pdf")
REPO_J24_P52_QP = Path("input/question_papers/9709 Mathematics June 2024 Question paper  52.pdf")
REPO_J24_P52_MS = Path("input/mark_schemes/9709 Mathematics June 2024 Mark Scheme  52.pdf")
REPO_N25_P51_QP = Path("input/question_papers/9709 Mathematics November 2025 Question Paper  51.pdf")
REPO_N25_P51_MS = Path("input/mark_schemes/9709 Mathematics November 2025 Mark Scheme  51.pdf")
REPO_J24_P13_QP = Path("input/question_papers/9709 Mathematics June 2024 Question paper  13.pdf")
REPO_J24_P13_MS = Path("input/mark_schemes/9709 Mathematics June 2024 Mark Scheme  13.pdf")
REPO_N25_P55_QP = Path("input/question_papers/9709 Mathematics November 2025 Question Paper  55.pdf")
REPO_N25_P55_MS = Path("input/mark_schemes/9709 Mathematics November 2025 Mark Scheme  55.pdf")
REPO_J22_P52_QP = Path("input/question_papers/9709 Mathematics June 2022 Question paper  52.pdf")
REPO_J22_P52_MS = Path("input/mark_schemes/9709 Mathematics June 2022 Mark Scheme  52.pdf")
REPO_J21_P42_QP = Path("input/question_papers/9709 Mathematics June 2021 Question paper  42.pdf")
REPO_J21_P42_MS = Path("input/mark_schemes/9709 Mathematics June 2021 Mark Scheme  42.pdf")


def test_sample_pipeline_on_march_2019_pdf(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")

    if not SAMPLE_QP.exists() or not SAMPLE_MS.exists():
        pytest.skip("March 2019 sample PDFs are not available on this machine.")

    config = AppConfig()
    config.output.images_dir = tmp_path / "images"
    config.output.json_dir = tmp_path / "json"
    config.output.csv_dir = tmp_path / "csv"
    config.output.review_dir = tmp_path / "review"
    config.ocr.enabled = False

    result = process_sample(SAMPLE_QP, config, mark_scheme_pdf=SAMPLE_MS)

    assert result.records
    assert result.json_path.exists()
    assert result.csv_path.exists()
    assert result.review_path.exists()
    assert any(Path(record.screenshot_path).exists() or (tmp_path / Path(record.screenshot_path)).exists() for record in result.records)
    assert all(record.combined_question_text for record in result.records)


def test_repo_march_2019_pipeline_exports_whole_questions_with_matched_mark_schemes(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")

    if not REPO_SAMPLE_QP.exists() or not REPO_SAMPLE_MS.exists():
        pytest.skip("Repo March 2019 sample PDFs are not available.")

    config = AppConfig()
    config.output.images_dir = tmp_path / "images"
    config.output.json_dir = tmp_path / "json"
    config.output.csv_dir = tmp_path / "csv"
    config.output.review_dir = tmp_path / "review"
    config.ocr.enabled = False

    result = process_sample(REPO_SAMPLE_QP, config, mark_scheme_pdf=REPO_SAMPLE_MS)

    assert [record.question_number for record in result.records] == [str(number) for number in range(1, 11)]
    assert sum(1 for record in result.records if record.markscheme_image) == 10
    assert all(record.markscheme_mapping_status == "pass" for record in result.records)
    assert all(record.markscheme_failure_reason == "" for record in result.records)
    assert all("adjacent_question_block_selected" not in record.review_flags for record in result.records)
    assert next(record for record in result.records if record.question_number == "8").markscheme_subparts == ["i", "ii", "iii", "iv"]


def test_repo_pipeline_does_not_pass_scope_mismatches_on_newer_papers(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")

    if not all(path.exists() for path in [REPO_S24_P3_QP, REPO_S24_P3_MS, REPO_N25_P5_QP, REPO_N25_P5_MS]):
        pytest.skip("Repo newer-format sample PDFs are not available.")

    config = AppConfig()
    config.output.images_dir = tmp_path / "images"
    config.output.json_dir = tmp_path / "json"
    config.output.csv_dir = tmp_path / "csv"
    config.output.review_dir = tmp_path / "review"
    config.ocr.enabled = False

    s24 = process_sample(REPO_S24_P3_QP, config, mark_scheme_pdf=REPO_S24_P3_MS)
    p53 = process_sample(REPO_N25_P5_QP, config, mark_scheme_pdf=REPO_N25_P5_MS)

    for result in [s24, p53]:
        for record in result.records:
            if record.markscheme_mapping_status != "pass":
                continue
            assert sorted(record.question_subparts) == sorted(record.markscheme_subparts)
            assert record.question_marks_total == record.markscheme_marks_total


def test_repo_s24_p3_recovers_hidden_middle_parts_on_question_side(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")

    if not REPO_S24_P3_QP.exists() or not REPO_S24_P3_MS.exists():
        pytest.skip("Repo Spring 2024 P3 sample PDFs are not available.")

    config = AppConfig()
    config.output.images_dir = tmp_path / "images"
    config.output.json_dir = tmp_path / "json"
    config.output.csv_dir = tmp_path / "csv"
    config.output.review_dir = tmp_path / "review"
    config.ocr.enabled = False

    result = process_sample(REPO_S24_P3_QP, config, mark_scheme_pdf=REPO_S24_P3_MS)

    q6 = next(record for record in result.records if record.question_number == "6")
    q7 = next(record for record in result.records if record.question_number == "7")

    assert q6.question_subparts == ["a", "b"]
    assert q6.markscheme_mapping_status == "pass"
    assert q7.question_subparts == ["a", "b", "c"]
    assert q7.markscheme_mapping_status == "pass"


def test_repo_n25_p53_does_not_false_pass_incomplete_question_scope(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")

    if not REPO_N25_P5_QP.exists() or not REPO_N25_P5_MS.exists():
        pytest.skip("Repo November 2025 P53 sample PDFs are not available.")

    config = AppConfig()
    config.output.images_dir = tmp_path / "images"
    config.output.json_dir = tmp_path / "json"
    config.output.csv_dir = tmp_path / "csv"
    config.output.review_dir = tmp_path / "review"
    config.ocr.enabled = False

    result = process_sample(REPO_N25_P5_QP, config, mark_scheme_pdf=REPO_N25_P5_MS)

    q3 = next(record for record in result.records if record.question_number == "3")
    q6 = next(record for record in result.records if record.question_number == "6")
    q7 = next(record for record in result.records if record.question_number == "7")

    assert q3.question_subparts == ["a"]
    assert q3.markscheme_mapping_status == "fail"
    assert q3.markscheme_failure_reason == "question_subparts_incomplete"
    assert q6.question_subparts == ["a", "b", "c", "d"]
    assert q6.markscheme_subparts == ["a", "b", "c", "d"]
    assert q6.markscheme_mapping_status == "fail"
    assert q6.markscheme_failure_reason == "marks_total_mismatch"
    assert q7.question_subparts == ["a", "c"]
    assert q7.markscheme_mapping_status == "fail"
    assert q7.markscheme_failure_reason == "question_subparts_incomplete"


def test_repo_n23_p41_q1_keeps_full_mark_scheme_block_and_total(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")

    if not REPO_N23_P41_QP.exists() or not REPO_N23_P41_MS.exists():
        pytest.skip("Repo November 2023 P41 sample PDFs are not available.")

    config = AppConfig()
    config.output.images_dir = tmp_path / "images"
    config.output.json_dir = tmp_path / "json"
    config.output.csv_dir = tmp_path / "csv"
    config.output.review_dir = tmp_path / "review"
    config.ocr.enabled = False

    result = process_sample(REPO_N23_P41_QP, config, mark_scheme_pdf=REPO_N23_P41_MS)

    q1 = next(record for record in result.records if record.question_number == "1")

    assert q1.markscheme_mapping_status == "pass"
    assert q1.markscheme_image
    assert q1.question_marks_total == 3
    assert q1.markscheme_marks_total == 3


def test_repo_j24_p5_and_p6_q1_pick_up_page_5_mark_scheme_start(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")

    if not all(path.exists() for path in [REPO_J24_P51_QP, REPO_J24_P51_MS, REPO_J24_P52_QP, REPO_J24_P52_MS]):
        pytest.skip("Repo June 2024 P5/P6 sample PDFs are not available.")

    config = AppConfig()
    config.output.images_dir = tmp_path / "images"
    config.output.json_dir = tmp_path / "json"
    config.output.csv_dir = tmp_path / "csv"
    config.output.review_dir = tmp_path / "review"
    config.ocr.enabled = False

    p51 = process_sample(REPO_J24_P51_QP, config, mark_scheme_pdf=REPO_J24_P51_MS)
    p52 = process_sample(REPO_J24_P52_QP, config, mark_scheme_pdf=REPO_J24_P52_MS)

    q1_p51 = next(record for record in p51.records if record.question_number == "1")
    q1_p52 = next(record for record in p52.records if record.question_number == "1")

    assert q1_p51.markscheme_image
    assert q1_p51.markscheme_mapping_status == "pass"
    assert q1_p52.markscheme_failure_reason != "partial_question_block"
    assert q1_p52.markscheme_subparts == ["a", "b", "c"]
    assert q1_p52.answer_text


def test_repo_newer_format_scope_cleanup_recovers_question_side_parts_before_totals_review(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")

    if not all(path.exists() for path in [REPO_N25_P51_QP, REPO_N25_P51_MS, REPO_N25_P5_QP, REPO_N25_P5_MS]):
        pytest.skip("Repo November 2025 sample PDFs are not available.")

    config = AppConfig()
    config.output.images_dir = tmp_path / "images"
    config.output.json_dir = tmp_path / "json"
    config.output.csv_dir = tmp_path / "csv"
    config.output.review_dir = tmp_path / "review"

    p51 = process_sample(REPO_N25_P51_QP, config, mark_scheme_pdf=REPO_N25_P51_MS)
    p53 = process_sample(REPO_N25_P5_QP, config, mark_scheme_pdf=REPO_N25_P5_MS)

    q3 = next(record for record in p51.records if record.question_number == "3")
    q4 = next(record for record in p51.records if record.question_number == "4")
    q6 = next(record for record in p53.records if record.question_number == "6")

    assert q3.question_subparts == ["a", "b"]
    assert q3.markscheme_subparts == ["a", "b"]
    assert q3.markscheme_failure_reason == "marks_total_mismatch"
    assert q4.question_subparts == ["a", "b"]
    assert q4.markscheme_subparts == ["a", "b"]
    assert q4.markscheme_failure_reason == "marks_total_mismatch"
    assert q6.question_subparts == ["a", "b", "c", "d"]
    assert q6.markscheme_subparts == ["a", "b", "c", "d"]
    assert q6.markscheme_failure_reason == "marks_total_mismatch"
    assert q3.markscheme_image
    assert q4.markscheme_image
    assert q6.markscheme_image


def test_repo_j24_p13_q3_starts_at_real_prompt_not_answer_space_junk(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")

    if not REPO_J24_P13_QP.exists() or not REPO_J24_P13_MS.exists():
        pytest.skip("Repo June 2024 P13 sample PDFs are not available.")

    config = AppConfig()
    config.output.images_dir = tmp_path / "images"
    config.output.json_dir = tmp_path / "json"
    config.output.csv_dir = tmp_path / "csv"
    config.output.review_dir = tmp_path / "review"
    config.ocr.enabled = False

    result = process_sample(REPO_J24_P13_QP, config, mark_scheme_pdf=REPO_J24_P13_MS)

    q3 = next(record for record in result.records if record.question_number == "3")

    assert q3.combined_question_text.startswith("3")
    assert "The diagram shows a sector of a circle" in q3.combined_question_text
    assert "................................" not in q3.combined_question_text[:180]
    assert q3.markscheme_failure_reason == "question_subparts_incomplete"


def test_repo_n25_p55_q4_recovers_full_whole_question_scope(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")

    if not REPO_N25_P55_QP.exists() or not REPO_N25_P55_MS.exists():
        pytest.skip("Repo November 2025 P55 sample PDFs are not available.")

    config = AppConfig()
    config.output.images_dir = tmp_path / "images"
    config.output.json_dir = tmp_path / "json"
    config.output.csv_dir = tmp_path / "csv"
    config.output.review_dir = tmp_path / "review"
    config.ocr.enabled = False

    result = process_sample(REPO_N25_P55_QP, config, mark_scheme_pdf=REPO_N25_P55_MS)

    q4 = next(record for record in result.records if record.question_number == "4")

    assert q4.question_subparts == ["a", "b", "c", "d"]
    assert q4.markscheme_subparts == ["a", "b", "c", "d"]
    assert q4.markscheme_mapping_status == "pass"


def test_repo_mark_scheme_subpart_totals_fix_j22_p52_q6(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")

    if not REPO_J22_P52_QP.exists() or not REPO_J22_P52_MS.exists():
        pytest.skip("Repo June 2022 P52 sample PDFs are not available.")

    config = AppConfig()
    config.output.images_dir = tmp_path / "images"
    config.output.json_dir = tmp_path / "json"
    config.output.csv_dir = tmp_path / "csv"
    config.output.review_dir = tmp_path / "review"
    config.ocr.enabled = False

    result = process_sample(REPO_J22_P52_QP, config, mark_scheme_pdf=REPO_J22_P52_MS)

    q6 = next(record for record in result.records if record.question_number == "6")

    assert q6.question_subparts == ["a", "b", "c", "d"]
    assert q6.markscheme_subparts == ["a", "b", "c", "d"]
    assert q6.question_marks_total == 10
    assert q6.markscheme_marks_total == 10
    assert q6.markscheme_mapping_status == "pass"


def test_repo_mark_scheme_no_subparts_fix_j21_p42_q6(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")

    if not REPO_J21_P42_QP.exists() or not REPO_J21_P42_MS.exists():
        pytest.skip("Repo June 2021 P42 sample PDFs are not available.")

    config = AppConfig()
    config.output.images_dir = tmp_path / "images"
    config.output.json_dir = tmp_path / "json"
    config.output.csv_dir = tmp_path / "csv"
    config.output.review_dir = tmp_path / "review"
    config.ocr.enabled = False

    result = process_sample(REPO_J21_P42_QP, config, mark_scheme_pdf=REPO_J21_P42_MS)

    q6 = next(record for record in result.records if record.question_number == "6")

    assert q6.question_subparts == []
    assert q6.markscheme_subparts == []
    assert q6.question_marks_total == 8
    assert q6.markscheme_marks_total == 8
    assert q6.markscheme_mapping_status == "pass"
