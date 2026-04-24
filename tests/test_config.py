from pathlib import Path

import pytest

from exam_bank.config import AppConfig, load_config
from exam_bank.document_registry import build_document_registry_from_paths


def touch_pdf(path: Path) -> Path:
    path.write_bytes(b"%PDF-1.4\n")
    return path


def test_runtime_profile_populates_default_taxonomy() -> None:
    config = AppConfig()

    assert config.runtime.taxonomy == "paper_only"
    assert config.runtime.input_document_types == ["question_paper", "mark_scheme"]
    assert config.runtime.output_layout == "paper_first"
    assert config.runtime.topic_mode == "metadata_only"
    assert "topic_pdfs" in config.runtime.archived_runtime_surfaces
    assert "series_and_sequences" in config.paper_family_taxonomy["P1"]
    assert "complex_numbers" in config.paper_family_taxonomy["P3"]
    assert "advanced algebra" not in config.topic_taxonomy


def test_load_config_rejects_deprecated_runtime_taxonomy_overrides(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "paper_family_taxonomy:\n"
        "  P1:\n"
        "    algebra: [general]\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="runtime_profile.json"):
        load_config(config_path)


def test_load_config_rejects_archived_runtime_surface_sections(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "topic_pdfs:\n"
        "  enable_topic_pdfs: true\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="archived"):
        load_config(config_path)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("output:\n  images_dir: output/images\n", "output.images_dir"),
        ("output:\n  csv_dir: output/csv\n", "output.csv_dir"),
        ("output:\n  review_dir: output/review\n", "output.review_dir"),
        ("naming:\n  image_template: legacy.png\n", "naming.image_template"),
        ("naming:\n  csv_name: question_bank.csv\n", "naming.csv_name"),
        ("naming:\n  review_name: review_items.csv\n", "naming.review_name"),
    ],
)
def test_load_config_rejects_removed_legacy_output_and_naming_keys(tmp_path: Path, body: str, message: str) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(body, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_config(config_path)


def test_document_registry_can_filter_archived_document_types(tmp_path: Path) -> None:
    qp = touch_pdf(tmp_path / "9709 Mathematics November 2025 Question Paper 12.pdf")
    ms = touch_pdf(tmp_path / "9709 Mathematics November 2025 Mark Scheme 12.pdf")
    touch_pdf(tmp_path / "9709 Mathematics November 2025 Examiner Report.pdf")

    registry = build_document_registry_from_paths(
        [tmp_path],
        allowed_document_types={"question_paper", "mark_scheme"},
    )

    entry = registry.entries["9709_2025_November_12"]
    assert entry.question_paper == qp
    assert entry.mark_scheme == ms
    assert entry.examiner_reports == []
    assert registry.session_reports == {}


def test_checked_in_config_yaml_loads_with_current_schema() -> None:
    config = load_config(Path("config.yaml"))

    assert config.classification.enable_openai is False
    assert config.classification.openai_model == "gpt-5-mini"
    assert config.classification.openai_timeout_seconds == 30
