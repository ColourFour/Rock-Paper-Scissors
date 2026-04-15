import json
from pathlib import Path

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
    assert "source_pdf" not in html
    assert "../images/question.png" in html
    assert "../images/markscheme.png" in html
    assert "Give me a question" in html
    assert "Show mark scheme" in html


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
