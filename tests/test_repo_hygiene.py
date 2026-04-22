from pathlib import Path


README_PATH = Path("README.md")
CONFIG_PATH = Path("config.yaml")
PYPROJECT_PATH = Path("pyproject.toml")


def test_readme_centers_supported_process_command() -> None:
    readme = README_PATH.read_text(encoding="utf-8")

    assert "python -m exam_bank.cli process --input input --output output" in readme
    assert "process-folder" not in readme
    assert "topic-pdfs" not in readme
    assert "practice-page" not in readme
    assert "manual-review" not in readme
    assert "open-qa" not in readme


def test_config_yaml_only_advertises_active_operational_sections() -> None:
    config_yaml = CONFIG_PATH.read_text(encoding="utf-8")

    for section in ["topic_pdfs:", "practice_page:", "manual_review:", "images_dir:", "csv_dir:", "review_dir:"]:
        assert section not in config_yaml


def test_package_metadata_matches_extraction_only_runtime() -> None:
    pyproject = PYPROJECT_PATH.read_text(encoding="utf-8")

    assert 'description = "CAIE 9709 question-paper and mark-scheme extraction pipeline."' in pyproject
    assert '"pandas>=2.0.0"' not in pyproject
    assert '"reportlab>=4.0.0"' not in pyproject
