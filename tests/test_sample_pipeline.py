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
