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

