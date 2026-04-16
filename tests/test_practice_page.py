import json
from pathlib import Path

from exam_bank.config import PracticePageConfig
from exam_bank.practice_page import build_practice_page


def test_practice_page_embeds_data_and_uses_relative_image_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    images_dir = tmp_path / "output" / "images"
    images_dir.mkdir(parents=True)
    question_image = images_dir / "question.png"
    markscheme_image = images_dir / "markscheme.png"
    question_image.write_bytes(b"question")
    markscheme_image.write_bytes(b"markscheme")

    json_dir = tmp_path / "output" / "json"
    json_dir.mkdir(parents=True)
    question_bank = json_dir / "question_bank.json"
    question_bank.write_text(
        json.dumps(
            [
                {
                    "source_pdf": "input/question_papers/9709_s21_qp_12.pdf",
                    "paper_family": "P1",
                    "topic": "quadratics",
                    "question_number": "1",
                    "marks_if_available": 4,
                    "question_image": "output/images/question.png",
                    "markscheme_image": "output/images/markscheme.png",
                }
            ]
        ),
        encoding="utf-8",
    )

    result = build_practice_page(question_bank, tmp_path / "output" / "practice")
    html = result.html_path.read_text(encoding="utf-8")

    assert result.usable_records == 1
    assert result.skipped_records == 0
    assert "window.QUESTION_BANK =" in html
    assert "fetch(" not in html
    assert "source_pdf" in html
    assert "../images/question.png" in html
    assert "../images/markscheme.png" in html
    assert "Give me a question" in html
    assert "Show mark scheme" in html
    assert "Copy bug report" in html
    assert "Reset progress" in html
    assert "Seen 0 / 0" in html
    assert "examBankPracticeProgress:v2" in html
    assert "remaining = choices.filter" in html
    assert "You've completed all available questions in this set" in html


def test_practice_page_embeds_missing_asset_debug_for_broken_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    images_dir = tmp_path / "output" / "images"
    images_dir.mkdir(parents=True)
    question_image = images_dir / "question.png"
    question_image.write_bytes(b"question")

    question_bank = tmp_path / "question_bank.json"
    question_bank.write_text(
        json.dumps(
            [
                {
                    "source_pdf": "input/question_papers/9709_s21_qp_12.pdf",
                    "paper_family": "P1",
                    "topic": "quadratics",
                    "question_number": "1",
                    "question_image": "output/images/question.png",
                    "markscheme_image": "",
                },
                {
                    "source_pdf": "input/question_papers/9709_s21_qp_32.pdf",
                    "paper_family": "P3",
                    "topic": "vectors",
                    "question_number": "2",
                    "question_image": "output/images/question.png",
                    "markscheme_image": "output/images/missing.png",
                },
            ]
        ),
        encoding="utf-8",
    )

    result = build_practice_page(question_bank, tmp_path / "output" / "practice")
    html = result.html_path.read_text(encoding="utf-8")

    assert result.usable_records == 1
    assert result.skipped_records == 1
    assert "../images/missing.png" in html
    assert '"markscheme_image_exists":false' in html
    assert "Practice image failed to load" in html


def test_practice_page_bug_report_form_config_is_embedded(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    images_dir = tmp_path / "output" / "images"
    images_dir.mkdir(parents=True)
    question_image = images_dir / "question.png"
    markscheme_image = images_dir / "markscheme.png"
    question_image.write_bytes(b"question")
    markscheme_image.write_bytes(b"markscheme")

    question_bank = tmp_path / "question_bank.json"
    question_bank.write_text(
        json.dumps(
            [
                {
                    "source_pdf": "input/question_papers/9709_s21_qp_12.pdf",
                    "paper_name": "9709_s21_qp_12",
                    "paper_family": "P1",
                    "topic": "quadratics",
                    "question_number": "1",
                    "full_question_label": "1(a)-1(b)",
                    "marks_if_available": 4,
                    "question_image": "output/images/question.png",
                    "markscheme_image": "output/images/markscheme.png",
                    "page_numbers": [2],
                    "markscheme_pages": [6],
                    "qa": {"status": "warning", "flags": ["question_crop_suspicious"]},
                }
            ]
        ),
        encoding="utf-8",
    )
    config = PracticePageConfig()
    config.bug_report.form_url = "https://example.com/report"
    config.bug_report.form_field_names = {
        "paper": "entry.1",
        "topic": "entry.2",
        "report_text": "entry.3",
    }

    result = build_practice_page(question_bank, tmp_path / "output" / "practice", config)
    html = result.html_path.read_text(encoding="utf-8")

    assert "Report a problem" in html
    assert "https://example.com/report" in html
    assert '"paper":"entry.1"' in html
    assert '"report_text":"entry.3"' in html
    assert "Issue type:" in html
    assert "Source page number:" in html


def test_practice_page_publish_copy_uses_local_asset_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    images_dir = tmp_path / "output" / "images"
    images_dir.mkdir(parents=True)
    question_image = images_dir / "question.png"
    markscheme_image = images_dir / "markscheme.png"
    question_image.write_bytes(b"question")
    markscheme_image.write_bytes(b"markscheme")

    question_bank = tmp_path / "question_bank.json"
    question_bank.write_text(
        json.dumps(
            [
                {
                    "source_pdf": "input/question_papers/9709_s21_qp_12.pdf",
                    "paper_family": "P1",
                    "topic": "quadratics",
                    "question_number": "1",
                    "question_image": "output/images/question.png",
                    "markscheme_image": "output/images/markscheme.png",
                }
            ]
        ),
        encoding="utf-8",
    )

    result = build_practice_page(
        question_bank,
        tmp_path / "practice",
        copy_assets=True,
        asset_dir_name="assets",
    )
    html = result.html_path.read_text(encoding="utf-8")

    assert result.usable_records == 1
    assert result.copied_assets == 2
    assert result.missing_assets == 0
    assert "assets/output/images/question.png" in html
    assert "assets/output/images/markscheme.png" in html
    assert (tmp_path / "practice" / "assets" / "output" / "images" / "question.png").read_bytes() == b"question"
    assert (tmp_path / "practice" / "assets" / "output" / "images" / "markscheme.png").read_bytes() == b"markscheme"


def test_practice_page_progress_logic_is_filter_aware_and_persistent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    images_dir = tmp_path / "output" / "images"
    images_dir.mkdir(parents=True)
    for name in ["q1.png", "q2.png", "ms1.png", "ms2.png"]:
        (images_dir / name).write_bytes(name.encode("utf-8"))

    question_bank = tmp_path / "question_bank.json"
    question_bank.write_text(
        json.dumps(
            [
                {
                    "paper_family": "P1",
                    "topic": "quadratics",
                    "question_number": "1",
                    "question_id": "p1-q1",
                    "question_image": "output/images/q1.png",
                    "markscheme_image": "output/images/ms1.png",
                },
                {
                    "paper_family": "P1",
                    "topic": "quadratics",
                    "question_number": "2",
                    "question_id": "p1-q2",
                    "question_image": "output/images/q2.png",
                    "markscheme_image": "output/images/ms2.png",
                },
            ]
        ),
        encoding="utf-8",
    )

    result = build_practice_page(question_bank, tmp_path / "output" / "practice")
    html = result.html_path.read_text(encoding="utf-8")

    assert "localStorage.getItem(STORAGE_KEY)" in html
    assert "localStorage.setItem(STORAGE_KEY" in html
    assert "function poolKey" in html
    assert "function validSeenSetForCurrentPool" in html
    assert "function resetProgress" in html
    assert "questionButton.disabled = total === 0 || seen.size >= total" in html


def test_practice_page_uses_manual_topic_and_excludes_manual_bad_records(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    images_dir = tmp_path / "output" / "images"
    images_dir.mkdir(parents=True)
    for name in ["q1.png", "q2.png", "ms1.png", "ms2.png"]:
        (images_dir / name).write_bytes(name.encode("utf-8"))

    question_bank = tmp_path / "question_bank.json"
    question_bank.write_text(
        json.dumps(
            [
                {
                    "paper_family": "P1",
                    "topic": "functions",
                    "manual_topic": "quadratics",
                    "question_number": "1",
                    "question_id": "p1-q1",
                    "question_image": "output/images/q1.png",
                    "markscheme_image": "output/images/ms1.png",
                    "usable": True,
                    "crop_status": "ok",
                },
                {
                    "paper_family": "P1",
                    "topic": "functions",
                    "manual_topic": "polynomials",
                    "question_number": "2",
                    "question_id": "p1-q2",
                    "question_image": "output/images/q2.png",
                    "markscheme_image": "output/images/ms2.png",
                    "usable": False,
                    "crop_status": "bad",
                },
            ]
        ),
        encoding="utf-8",
    )

    result = build_practice_page(question_bank, tmp_path / "output" / "practice")
    html = result.html_path.read_text(encoding="utf-8")

    assert result.usable_records == 1
    assert result.skipped_records == 1
    assert '"topic":"quadratics"' in html
    assert '"pipeline_topic":"functions"' in html
    assert "p1-q2" not in html
