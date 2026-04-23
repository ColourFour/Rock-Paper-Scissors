from pathlib import Path
import json

import pytest

from exam_bank.config import AppConfig
from exam_bank.pdf_extract import extract_pdf_layout
from exam_bank.pipeline import process_sample
from exam_bank.question_detection import detect_question_starts


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
REPO_N24_P12_QP = Path("input/question_papers/9709 Mathematics November 2024 Question paper  12.pdf")
REPO_N24_P12_MS = Path("input/mark_schemes/9709 Mathematics November 2024 Mark Scheme  12.pdf")
REPO_M24_P12_QP = Path("input/question_papers/9709 Mathematics March 2024 Question paper  12.pdf")
REPO_M24_P12_MS = Path("input/mark_schemes/9709 Mathematics March 2024 Mark Scheme  12.pdf")
REPO_M24_P32_QP = Path("input/question_papers/9709 Mathematics March 2024 Question paper  32.pdf")
REPO_M24_P32_MS = Path("input/mark_schemes/9709 Mathematics March 2024 Mark Scheme  32.pdf")
REPO_N24_P32_QP = Path("input/question_papers/9709 Mathematics November 2024 Question paper  32.pdf")
REPO_N24_P32_MS = Path("input/mark_schemes/9709 Mathematics November 2024 Mark Scheme  32.pdf")
REPO_M24_P42_QP = Path("input/question_papers/9709 Mathematics March 2024 Question paper  42.pdf")
REPO_M24_P42_MS = Path("input/mark_schemes/9709 Mathematics March 2024 Mark Scheme  42.pdf")


def _paper_total(result) -> int:
    return sum(
        int(mark)
        for record in result.records
        if (mark := record.markscheme_marks_total or record.question_marks_total or record.marks_if_available or record.marks) is not None
    )


def _configure_test_output(config: AppConfig, tmp_path: Path) -> None:
    config.output.apply_root(tmp_path / "output")


def test_sample_pipeline_on_march_2019_pdf(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")

    if not SAMPLE_QP.exists() or not SAMPLE_MS.exists():
        pytest.skip("March 2019 sample PDFs are not available on this machine.")

    config = AppConfig()
    _configure_test_output(config, tmp_path)
    config.ocr.enabled = False

    result = process_sample(SAMPLE_QP, config, mark_scheme_pdf=SAMPLE_MS)

    assert result.records
    assert result.json_path.exists()
    assert result.output_root == tmp_path / "output"
    assert any(
        Path(record.screenshot_path).exists() or ((tmp_path / "output") / Path(record.screenshot_path)).exists()
        for record in result.records
    )
    assert all(record.combined_question_text for record in result.records)


def test_repo_march_2019_pipeline_exports_whole_questions_with_matched_mark_schemes(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")

    if not REPO_SAMPLE_QP.exists() or not REPO_SAMPLE_MS.exists():
        pytest.skip("Repo March 2019 sample PDFs are not available.")

    config = AppConfig()
    _configure_test_output(config, tmp_path)
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
    _configure_test_output(config, tmp_path)
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
    _configure_test_output(config, tmp_path)
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
    _configure_test_output(config, tmp_path)
    config.ocr.enabled = False

    result = process_sample(REPO_N25_P5_QP, config, mark_scheme_pdf=REPO_N25_P5_MS)

    q3 = next(record for record in result.records if record.question_number == "3")
    q6 = next(record for record in result.records if record.question_number == "6")
    q7 = next(record for record in result.records if record.question_number == "7")

    assert q3.question_subparts == ["a"]
    assert q3.markscheme_mapping_status == "fail"
    assert q3.markscheme_failure_reason == "question_subparts_incomplete"
    assert q3.validation_status == "fail"
    assert q6.question_subparts == ["a", "c", "d"]
    assert q6.markscheme_subparts == ["a", "b", "c", "d"]
    assert q6.markscheme_mapping_status == "fail"
    assert q6.markscheme_failure_reason == "question_subparts_incomplete"
    assert q6.validation_status == "fail"
    assert q6.question_structure_detected.get("impossible_subpart_sequence_detected") is True
    assert q6.question_structure_detected.get("missing_internal_subparts") == ["b"]
    assert q7.question_subparts == ["a", "c"]
    assert q7.markscheme_mapping_status == "fail"
    assert q7.markscheme_failure_reason == "question_subparts_incomplete"
    assert q7.validation_status == "fail"
    assert q7.question_structure_detected.get("impossible_subpart_sequence_detected") is True
    assert q7.question_structure_detected.get("missing_internal_subparts") == ["b"]


def test_repo_n23_p41_q1_keeps_full_mark_scheme_block_and_total(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")

    if not REPO_N23_P41_QP.exists() or not REPO_N23_P41_MS.exists():
        pytest.skip("Repo November 2023 P41 sample PDFs are not available.")

    config = AppConfig()
    _configure_test_output(config, tmp_path)
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
    _configure_test_output(config, tmp_path)
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


def test_repo_m24_p1_diagram_sensitive_controls_do_not_fail_on_weak_anchor_only(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")

    if not REPO_M24_P12_QP.exists() or not REPO_M24_P12_MS.exists():
        pytest.skip("Repo March 2024 P12 sample PDFs are not available.")

    config = AppConfig()
    _configure_test_output(config, tmp_path)
    config.ocr.enabled = False

    result = process_sample(REPO_M24_P12_QP, config, mark_scheme_pdf=REPO_M24_P12_MS)

    for question_number in ["2", "10", "11"]:
        record = next(record for record in result.records if record.question_number == question_number)
        assert record.markscheme_mapping_status == "pass"
        assert record.validation_status == "pass"
        assert record.scope_quality_status == "clean"
        assert record.text_fidelity_status == "clean"
        assert record.topic_trust_status == "normal"
        assert "weak_question_anchor" not in record.validation_flags


def test_repo_m24_p32_control_stays_clean_without_unnecessary_rescan(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")

    if not REPO_M24_P32_QP.exists() or not REPO_M24_P32_MS.exists():
        pytest.skip("Repo March 2024 P32 sample PDFs are not available.")

    config = AppConfig()
    _configure_test_output(config, tmp_path)
    config.ocr.enabled = False

    result = process_sample(REPO_M24_P32_QP, config, mark_scheme_pdf=REPO_M24_P32_MS)

    q7 = next(record for record in result.records if record.question_number == "7")

    assert result.records[0].paper_total_status == "matched"
    assert result.records[0].rescan_triggered is False
    assert q7.markscheme_mapping_status == "pass"
    assert q7.validation_status == "pass"
    assert "weak_question_anchor" not in q7.validation_flags


def test_repo_n24_p32_same_page_lower_blocks_are_recovered_from_sparse_lower_region_ocr(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")
    pytest.importorskip("pytesseract")

    if not REPO_N24_P32_QP.exists() or not REPO_N24_P32_MS.exists():
        pytest.skip("Repo November 2024 P32 sample PDFs are not available.")

    config_off = AppConfig()
    _configure_test_output(config_off, tmp_path / "without_ocr")
    config_off.ocr.enabled = False
    without_ocr = process_sample(REPO_N24_P32_QP, config_off, mark_scheme_pdf=REPO_N24_P32_MS)

    config_on = AppConfig()
    _configure_test_output(config_on, tmp_path / "with_ocr")
    config_on.ocr.enabled = True
    with_ocr = process_sample(REPO_N24_P32_QP, config_on, mark_scheme_pdf=REPO_N24_P32_MS)
    layouts = extract_pdf_layout(REPO_N24_P32_QP, config_on)

    q2_before = next(record for record in without_ocr.records if record.question_number == "2")
    q5_before = next(record for record in without_ocr.records if record.question_number == "5")
    q2_after = next(record for record in with_ocr.records if record.question_number == "2")
    q5_after = next(record for record in with_ocr.records if record.question_number == "5")
    page3 = layouts[2]
    page6 = layouts[5]

    assert q2_before.question_subparts == ["a"]
    assert q5_before.question_subparts == ["a"]
    assert q2_after.question_subparts == ["a", "b"]
    assert q5_after.question_subparts == ["a", "b"]
    assert q2_after.markscheme_mapping_status == "pass"
    assert q5_after.markscheme_mapping_status == "pass"
    assert page3.extraction_warning == "ocr_merged_sparse_lower_region"
    assert page6.extraction_warning == "ocr_merged_sparse_lower_region"
    assert any(block.text.startswith("(b)") and block.bbox.y0 > 350 for block in page3.blocks)
    assert any(block.text.startswith("(b)") and block.bbox.y0 > 350 for block in page6.blocks)


def test_repo_n24_p32_degraded_math_text_exports_degraded_text_fidelity_and_topic_trust(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")
    pytest.importorskip("pytesseract")

    if not REPO_N24_P32_QP.exists() or not REPO_N24_P32_MS.exists():
        pytest.skip("Repo November 2024 P32 sample PDFs are not available.")

    config = AppConfig()
    _configure_test_output(config, tmp_path)

    result = process_sample(REPO_N24_P32_QP, config, mark_scheme_pdf=REPO_N24_P32_MS)
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    q2 = next(record for record in result.records if record.question_number == "2")
    q2_json = next(item for item in payload if item["question_number"] == "2")

    assert q2.markscheme_mapping_status == "pass"
    assert q2.text_fidelity_status == "degraded"
    assert "ocr_math_notation_degraded" in q2.text_fidelity_flags
    assert q2.topic_trust_status == "degraded_text"
    assert q2.scope_quality_status == "review"
    assert q2_json["notes"]["mapping_status"] == "pass"
    assert q2_json["notes"]["text_source_profile"] == "hybrid"
    assert q2_json["notes"]["text_fidelity_status"] == "degraded"
    assert q2_json["notes"]["topic_trust_status"] == "degraded_text"


def test_repo_n24_p32_same_page_continuation_pages_do_not_false_split_on_lower_recovery(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")
    pytest.importorskip("pytesseract")

    if not REPO_N24_P32_QP.exists():
        pytest.skip("Repo November 2024 P32 sample PDF is not available.")

    config = AppConfig()
    _configure_test_output(config, tmp_path)
    config.ocr.enabled = True

    layouts = extract_pdf_layout(REPO_N24_P32_QP, config)
    page3_starts = detect_question_starts([layouts[2]], config, source_pdf=REPO_N24_P32_QP)
    page6_starts = detect_question_starts([layouts[5]], config, source_pdf=REPO_N24_P32_QP)

    assert [start.question_number for start in page3_starts] == ["2"]
    assert [start.question_number for start in page6_starts] == ["5"]


def test_repo_m24_p32_clean_single_question_page_remains_single_with_ocr_enabled(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")
    pytest.importorskip("pytesseract")

    if not REPO_M24_P32_QP.exists():
        pytest.skip("Repo March 2024 P32 sample PDF is not available.")

    config = AppConfig()
    _configure_test_output(config, tmp_path)
    config.ocr.enabled = True

    layouts = extract_pdf_layout(REPO_M24_P32_QP, config)
    page10_starts = detect_question_starts([layouts[9]], config, source_pdf=REPO_M24_P32_QP)

    assert [start.question_number for start in page10_starts] == ["7"]


def test_repo_newer_format_scope_cleanup_tightens_p51_scopes_upstream(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")

    if not all(path.exists() for path in [REPO_N25_P51_QP, REPO_N25_P51_MS, REPO_N25_P5_QP, REPO_N25_P5_MS]):
        pytest.skip("Repo November 2025 sample PDFs are not available.")

    config = AppConfig()
    _configure_test_output(config, tmp_path)

    p51 = process_sample(REPO_N25_P51_QP, config, mark_scheme_pdf=REPO_N25_P51_MS)
    p53 = process_sample(REPO_N25_P5_QP, config, mark_scheme_pdf=REPO_N25_P5_MS)

    q2 = next(record for record in p51.records if record.question_number == "2")
    q3 = next(record for record in p51.records if record.question_number == "3")
    q4 = next(record for record in p51.records if record.question_number == "4")
    q6 = next(record for record in p53.records if record.question_number == "6")

    assert q2.markscheme_mapping_status == "pass"
    assert "annual salaries" not in q2.combined_question_text
    assert q2.question_structure_detected.get("contamination_detected") is not True
    assert q3.question_subparts == ["a", "b"]
    assert q3.markscheme_subparts == ["a", "b"]
    assert q3.markscheme_mapping_status == "pass"
    assert q3.validation_status == "review"
    assert "marbles chosen" not in q3.combined_question_text
    assert q3.question_structure_detected.get("contamination_detected") is not True
    assert q4.question_subparts == ["a", "b"]
    assert q4.markscheme_subparts == ["a", "b"]
    assert q4.markscheme_failure_reason == "question_scope_contaminated"
    assert "question_scope_contaminated" in q4.validation_flags
    assert q6.markscheme_subparts == ["a", "b", "c", "d"]
    assert q6.question_subparts in (["a", "c", "d"], ["a", "b", "c", "d"])
    if q6.markscheme_mapping_status == "fail":
        assert q6.markscheme_failure_reason == "question_subparts_incomplete"
    else:
        assert q6.markscheme_mapping_status == "pass"
    assert q3.markscheme_image
    assert q4.markscheme_image
    assert q6.markscheme_image


def test_repo_n25_p51_missing_visible_part_exports_unusable_text_semantics(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")

    if not REPO_N25_P51_QP.exists() or not REPO_N25_P51_MS.exists():
        pytest.skip("Repo November 2025 P51 sample PDFs are not available.")

    config = AppConfig()
    _configure_test_output(config, tmp_path)

    result = process_sample(REPO_N25_P51_QP, config, mark_scheme_pdf=REPO_N25_P51_MS)
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    q1 = next(record for record in result.records if record.question_number == "1")
    q1_json = next(item for item in payload if item["question_number"] == "1")

    assert q1.markscheme_failure_reason == "question_subparts_incomplete"
    assert q1.scope_quality_status in {"clean", "review"}
    assert q1.text_fidelity_status == "unusable"
    assert "missing_visible_structure_in_text" in q1.text_fidelity_flags
    assert q1.topic_trust_status == "review_required"
    assert q1_json["notes"]["scope_quality_status"] in {"clean", "review"}
    assert q1_json["notes"]["text_fidelity_status"] == "unusable"
    assert "missing_visible_structure_in_text" in q1_json["notes"]["text_fidelity_flags"]


def test_repo_n25_p51_structure_mismatch_reasons_beat_weak_anchor(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")

    if not REPO_N25_P51_QP.exists() or not REPO_N25_P51_MS.exists():
        pytest.skip("Repo November 2025 P51 sample PDFs are not available.")

    config = AppConfig()
    _configure_test_output(config, tmp_path)
    config.ocr.enabled = False

    result = process_sample(REPO_N25_P51_QP, config, mark_scheme_pdf=REPO_N25_P51_MS)

    q1 = next(record for record in result.records if record.question_number == "1")
    q3 = next(record for record in result.records if record.question_number == "3")

    assert q1.markscheme_failure_reason == "question_subparts_incomplete"
    assert "weak_question_anchor" not in {q1.markscheme_failure_reason}
    assert q1.question_subparts == ["a"]
    assert q1.markscheme_subparts == ["a", "b", "c"]

    assert q3.markscheme_failure_reason == "question_subparts_incomplete"
    assert "weak_question_anchor" not in {q3.markscheme_failure_reason}
    assert q3.question_subparts == ["a"]
    assert q3.markscheme_subparts == ["a", "b"]


def test_repo_n25_p51_scope_cleanup_changes_ugly_cases_measurably(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")

    if not REPO_N25_P51_QP.exists() or not REPO_N25_P51_MS.exists():
        pytest.skip("Repo November 2025 P51 sample PDFs are not available.")

    config = AppConfig()
    _configure_test_output(config, tmp_path)
    config.ocr.enabled = False

    result = process_sample(REPO_N25_P51_QP, config, mark_scheme_pdf=REPO_N25_P51_MS)

    q2 = next(item for item in result.records if item.question_number == "2")
    q3 = next(item for item in result.records if item.question_number == "3")
    q4 = next(item for item in result.records if item.question_number == "4")

    assert q2.markscheme_mapping_status == "pass"
    assert "question_scope_contaminated" not in q2.validation_flags
    assert q2.question_structure_detected.get("contamination_detected") is not True
    assert "annual salaries" not in q2.combined_question_text

    assert q3.markscheme_mapping_status == "fail"
    assert q3.markscheme_failure_reason == "question_subparts_incomplete"
    assert "question_scope_contaminated" not in q3.validation_flags
    assert q3.question_structure_detected.get("contamination_detected") is not True
    assert "marbles chosen" not in q3.combined_question_text

    assert q4.markscheme_mapping_status == "fail"
    assert q4.markscheme_failure_reason == "question_scope_contaminated"
    assert "question_scope_contaminated" in q4.validation_flags or q4.question_structure_detected.get("contamination_detected") is True


def test_repo_newer_format_clean_passes_remain_non_contaminated(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")

    if not all(path.exists() for path in [REPO_N25_P5_QP, REPO_N25_P5_MS, REPO_N25_P55_QP, REPO_N25_P55_MS]):
        pytest.skip("Repo November 2025 P53/P55 sample PDFs are not available.")

    config = AppConfig()
    _configure_test_output(config, tmp_path)
    config.ocr.enabled = False

    p53 = process_sample(REPO_N25_P5_QP, config, mark_scheme_pdf=REPO_N25_P5_MS)
    p55 = process_sample(REPO_N25_P55_QP, config, mark_scheme_pdf=REPO_N25_P55_MS)

    q1_p53 = next(record for record in p53.records if record.question_number == "1")
    q2_p55 = next(record for record in p55.records if record.question_number == "2")
    q3_p55 = next(record for record in p55.records if record.question_number == "3")

    for record in [q1_p53, q2_p55, q3_p55]:
        assert "question_scope_contaminated" not in record.validation_flags
        assert record.question_structure_detected.get("contamination_detected") is not True
        assert record.markscheme_mapping_status == "pass"


def test_repo_newer_format_shaky_pass_gets_stricter_validation_without_hurting_controls(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")

    required = [
        REPO_N25_P5_QP,
        REPO_N25_P5_MS,
        REPO_N25_P55_QP,
        REPO_N25_P55_MS,
        REPO_N25_P51_QP,
        REPO_N25_P51_MS,
    ]
    if not all(path.exists() for path in required):
        pytest.skip("Repo November 2025 sample PDFs are not available.")

    config = AppConfig()
    _configure_test_output(config, tmp_path)
    config.ocr.enabled = False

    p51 = process_sample(REPO_N25_P51_QP, config, mark_scheme_pdf=REPO_N25_P51_MS)
    p53 = process_sample(REPO_N25_P5_QP, config, mark_scheme_pdf=REPO_N25_P5_MS)
    p55 = process_sample(REPO_N25_P55_QP, config, mark_scheme_pdf=REPO_N25_P55_MS)

    q4_p53 = next(record for record in p53.records if record.question_number == "4")
    q1_p53 = next(record for record in p53.records if record.question_number == "1")
    q2_p55 = next(record for record in p55.records if record.question_number == "2")
    q3_p55 = next(record for record in p55.records if record.question_number == "3")
    q2_p51 = next(record for record in p51.records if record.question_number == "2")
    q3_p51 = next(record for record in p51.records if record.question_number == "3")
    q4_p51 = next(record for record in p51.records if record.question_number == "4")

    assert q4_p53.markscheme_mapping_status == "pass"
    assert q4_p53.validation_status == "fail"
    assert "polluted_pass_requires_review" in q4_p53.validation_flags
    assert q4_p53.question_crop_confidence == "low"
    assert q4_p53.question_structure_detected.get("contamination_detected") is not True

    for record in [q1_p53, q2_p55, q3_p55]:
        assert record.markscheme_mapping_status == "pass"
        assert record.validation_status == "review"
        assert "polluted_pass_requires_review" not in record.validation_flags
        assert record.question_crop_confidence == "high"

    assert q2_p51.markscheme_mapping_status == "pass"
    assert q2_p51.validation_status == "review"
    assert "polluted_pass_requires_review" not in q2_p51.validation_flags

    assert q3_p51.markscheme_mapping_status == "fail"
    assert q3_p51.validation_status == "fail"
    assert q3_p51.markscheme_failure_reason == "question_subparts_incomplete"
    assert "polluted_pass_requires_review" not in q3_p51.validation_flags

    assert q4_p51.markscheme_mapping_status == "fail"
    assert q4_p51.validation_status == "fail"
    assert q4_p51.markscheme_failure_reason == "question_scope_contaminated"
    assert "question_scope_contaminated" in q4_p51.validation_flags


def test_repo_j24_p13_q3_starts_at_real_prompt_not_answer_space_junk(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")

    if not REPO_J24_P13_QP.exists() or not REPO_J24_P13_MS.exists():
        pytest.skip("Repo June 2024 P13 sample PDFs are not available.")

    config = AppConfig()
    _configure_test_output(config, tmp_path)
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
    _configure_test_output(config, tmp_path)
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
    _configure_test_output(config, tmp_path)
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
    _configure_test_output(config, tmp_path)
    config.ocr.enabled = False

    result = process_sample(REPO_J21_P42_QP, config, mark_scheme_pdf=REPO_J21_P42_MS)

    q6 = next(record for record in result.records if record.question_number == "6")

    assert q6.question_subparts == []
    assert q6.markscheme_subparts == []
    assert q6.question_marks_total == 8
    assert q6.markscheme_marks_total == 8
    assert q6.markscheme_mapping_status == "pass"


@pytest.mark.parametrize(
    ("question_pdf", "mark_scheme_pdf", "paper_family", "expected_total"),
    [
        (REPO_N24_P12_QP, REPO_N24_P12_MS, "P1", 75),
        (REPO_M24_P12_QP, REPO_M24_P12_MS, "P1", 75),
        (REPO_M24_P32_QP, REPO_M24_P32_MS, "P3", 75),
        (REPO_N25_P51_QP, REPO_N25_P51_MS, "P5", 50),
        (REPO_N25_P5_QP, REPO_N25_P5_MS, "P5", 50),
    ],
)
def test_repo_2024_2025_papers_report_expected_totals_or_fail_clearly(
    tmp_path: Path,
    question_pdf: Path,
    mark_scheme_pdf: Path,
    paper_family: str,
    expected_total: int,
) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")

    if not question_pdf.exists() or not mark_scheme_pdf.exists():
        pytest.skip(f"Missing fixture pair for {question_pdf.name}.")

    config = AppConfig()
    _configure_test_output(config, tmp_path)
    config.ocr.enabled = False

    result = process_sample(question_pdf, config, mark_scheme_pdf=mark_scheme_pdf)

    assert result.records
    detected_total = _paper_total(result)
    record = result.records[0]

    assert record.paper_family == paper_family
    assert record.paper_total_expected == expected_total
    assert record.paper_total_detected == detected_total
    assert record.paper_total_before_rescan is not None
    assert record.paper_total_after_rescan is not None

    if detected_total == expected_total:
        assert record.paper_total_status in {"matched", "recovered_after_rescan"}
        assert record.paper_total_after_rescan == expected_total
    else:
        assert record.rescan_triggered is True
        assert record.paper_total_status == "mismatch_after_rescan"
        assert any(item.validation_status == "fail" for item in result.records)


def test_repo_n24_p12_mismatch_is_localized_after_rescan(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")

    if not REPO_N24_P12_QP.exists() or not REPO_N24_P12_MS.exists():
        pytest.skip("Repo November 2024 P12 sample PDFs are not available.")

    config = AppConfig()
    _configure_test_output(config, tmp_path)
    config.ocr.enabled = False

    result = process_sample(REPO_N24_P12_QP, config, mark_scheme_pdf=REPO_N24_P12_MS)

    first = result.records[0]
    focus_records = [record for record in result.records if "paper_total_focus_candidate" in record.review_flags]

    assert first.paper_total_expected == 75
    assert first.paper_total_before_rescan == 72
    assert first.paper_total_after_rescan == 72
    assert first.paper_total_status == "mismatch_after_rescan"
    assert first.rescan_triggered is True
    assert first.rescan_result == "no_improvement"
    assert set(first.paper_total_focus_questions) >= {"1", "5", "7"}
    assert 10 in first.paper_total_focus_pages
    assert focus_records
    assert any(record.question_number == "1" and "question_scope_contaminated" in record.paper_total_focus_reason for record in focus_records)
    assert any(record.question_number == "7" and "question_mark_total_mismatch" in record.paper_total_focus_reason for record in focus_records)


def test_repo_n25_p51_contamination_control_survives_without_rescan_regression(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")

    if not REPO_N25_P51_QP.exists() or not REPO_N25_P51_MS.exists():
        pytest.skip("Repo November 2025 P51 sample PDFs are not available.")

    config = AppConfig()
    _configure_test_output(config, tmp_path)
    config.ocr.enabled = False

    result = process_sample(REPO_N25_P51_QP, config, mark_scheme_pdf=REPO_N25_P51_MS)

    first = result.records[0]
    q4 = next(record for record in result.records if record.question_number == "4")
    q7 = next(record for record in result.records if record.question_number == "7")

    assert first.paper_total_expected == 50
    assert first.paper_total_before_rescan == 50
    assert first.paper_total_after_rescan == 50
    assert first.rescan_triggered is False
    assert q4.markscheme_failure_reason == "question_scope_contaminated"
    assert q4.validation_status == "fail"
    assert q4.scope_quality_status == "fail"
    assert q4.topic_trust_status == "review_required"
    assert "question_scope_contaminated" in q4.validation_flags
    assert q7.markscheme_failure_reason == "question_scope_contaminated"
    assert q7.validation_status == "fail"
