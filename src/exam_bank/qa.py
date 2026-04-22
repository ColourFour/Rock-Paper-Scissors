from __future__ import annotations

from collections import Counter
import csv
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any
import warnings

from .image_limits import SAFE_PROBE_PIXELS


TARGET_PAPER_FAMILIES = ("P1", "P3", "P4", "P5")
IGNORED_PAPER_FAMILIES = ("P2", "P6")

ALLOWED_TOPICS_BY_PAPER: dict[str, tuple[str, ...]] = {
    "P1": (
        "algebra",
        "quadratics",
        "functions",
        "coordinate_geometry",
        "circular_measure",
        "trigonometry",
        "series_and_sequences",
        "binomial_expansion",
        "differentiation",
        "integration",
    ),
    "P3": (
        "algebra",
        "modulus",
        "logarithms_and_exponentials",
        "trigonometry",
        "functions",
        "numerical_methods",
        "differentiation",
        "integration",
        "differential_equations",
        "binomial_expansion",
        "implicit_differentiation",
        "partial_fractions",
        "vectors",
        "complex_numbers",
        "polynomials",
        "parametric_equations",
    ),
    "P4": (
        "kinematics_constant_acceleration",
        "kinematics_graphs",
        "kinematics_variable_functions",
        "forces_newtons_second_law",
        "equilibrium_coplanar_forces",
        "equilibrium_particle",
        "friction_rough_plane",
        "connected_particles",
        "momentum_impulse",
        "work_energy_power",
        "connected_particles_energy",
        "rough_plane_energy",
        "power_and_resistance",
    ),
    "P5": (
        "data_representation",
        "measures_of_central_tendency_and_dispersion",
        "permutations_and_combinations",
        "probability",
        "probability_distributions",
        "geometric_distribution",
        "binomial_distribution",
        "normal_distribution",
    ),
}

EXPECTED_MARKSCHEME_HEADER = ("question", "answer", "marks", "guidance")

CSV_FIELDS = [
    "record_index",
    "source_pdf",
    "paper_name",
    "question_number",
    "paper_family",
    "topic",
    "question_image",
    "markscheme_image",
    "qa_status",
    "qa_flags",
    "qa_notes",
    "question_crop_confidence",
    "markscheme_crop_confidence",
    "markscheme_mapping_method",
    "review_flags",
]

FAIL_FLAGS = {
    "record_incomplete",
    "missing_source_pdf",
    "empty_source_pdf",
    "missing_question_number",
    "missing_paper_family",
    "invalid_paper_family",
    "missing_topic",
    "invalid_topic_for_paper",
    "multiple_final_topics",
    "missing_question_image",
    "question_image_unreadable",
    "question_crop_blank",
    "question_crop_too_small",
    "missing_markscheme_image",
    "markscheme_image_unreadable",
    "markscheme_crop_blank",
    "markscheme_crop_too_small",
    "markscheme_question_number_mismatch",
    "paper_family_source_mismatch",
    "markscheme_page_before_6",
    "markscheme_header_not_ok",
    "markscheme_label_missing",
    "invalid_table_header",
    "missing_subparts",
    "marks_total_mismatch",
    "partial_question_block",
    "adjacent_question_block_selected",
}
FLAG_PRIORITY = [
    "record_incomplete",
    "missing_source_pdf",
    "empty_source_pdf",
    "missing_question_number",
    "missing_paper_family",
    "invalid_paper_family",
    "missing_topic",
    "invalid_topic_for_paper",
    "multiple_final_topics",
    "missing_question_image",
    "missing_markscheme_image",
]

LOW_CONFIDENCE_VALUES = {"low", "uncertain"}


@dataclass(frozen=True)
class QAResult:
    records: list[dict[str, Any]]
    skipped_records: list[dict[str, Any]]
    summary: dict[str, Any]
    json_path: Path
    csv_path: Path
    review_path: Path


def run_qa(
    question_bank_path: str | Path,
    output_dir: str | Path,
    *,
    only_failed: bool = False,
) -> QAResult:
    question_bank_path = Path(question_bank_path)
    output_dir = Path(output_dir)
    raw_records = _load_question_bank(question_bank_path)

    qa_records: list[dict[str, Any]] = []
    skipped_records: list[dict[str, Any]] = []
    for index, record in enumerate(raw_records):
        paper_family = _text(record.get("paper_family"))
        if paper_family in IGNORED_PAPER_FAMILIES:
            skipped_records.append(
                {
                    "record_index": index,
                    "paper_family": paper_family,
                    "question_number": _text(record.get("question_number")),
                    "source_pdf": _text(record.get("source_pdf")),
                    "reason": "ignored_paper_family",
                }
            )
            continue
        qa_records.append(validate_record(record, index, question_bank_path))

    all_status_counts = _status_counts(qa_records)
    written_records = [record for record in qa_records if not only_failed or record["qa_status"] == "fail"]
    summary = {
        "question_bank": str(question_bank_path),
        "record_count": len(raw_records),
        "validated_record_count": len(qa_records),
        "written_record_count": len(written_records),
        "skipped_record_count": len(skipped_records),
        "skipped_paper_families": list(IGNORED_PAPER_FAMILIES),
        "target_paper_families": list(TARGET_PAPER_FAMILIES),
        "only_failed": only_failed,
        "status_counts": all_status_counts,
        "written_status_counts": _status_counts(written_records),
        "flag_counts": _flag_counts(qa_records),
        "warning_flag_counts": _flag_counts([record for record in qa_records if record["qa_status"] == "warning"]),
        "fail_flag_counts": _flag_counts([record for record in qa_records if record["qa_status"] == "fail"], only_flags=FAIL_FLAGS),
        "top_warning_reason": _top_flag([record for record in qa_records if record["qa_status"] == "warning"]),
        "top_fail_reason": _top_flag([record for record in qa_records if record["qa_status"] == "fail"], only_flags=FAIL_FLAGS),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "qa_report.json"
    csv_path = output_dir / "qa_report.csv"
    review_path = output_dir / "review.html"

    payload = {
        "summary": summary,
        "records": written_records,
        "skipped_records": skipped_records,
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_csv(written_records, csv_path)
    _write_review_html(review_path, payload)
    return QAResult(
        records=written_records,
        skipped_records=skipped_records,
        summary=summary,
        json_path=json_path,
        csv_path=csv_path,
        review_path=review_path,
    )


def validate_record(record: dict[str, Any], record_index: int, question_bank_path: Path) -> dict[str, Any]:
    flags: list[str] = []
    notes: list[str] = []

    source_pdf = _text(record.get("source_pdf"))
    paper_name = _text(record.get("paper_name"))
    question_number = _text(record.get("question_number"))
    paper_family = _text(record.get("paper_family"))
    topic = _raw_topic(record.get("topic"))
    question_image = _text(record.get("question_image") or record.get("screenshot_path"))
    markscheme_image = _text(record.get("markscheme_image"))
    review_flags = _list_text(record.get("review_flags"))

    if not source_pdf:
        _add(flags, "missing_source_pdf")
    else:
        source_path = _resolve_path(source_pdf, question_bank_path.parent)
        if not source_path.exists():
            _add(flags, "missing_source_pdf")
            notes.append(f"source_pdf not found: {source_pdf}")
        elif source_path.stat().st_size <= 0:
            _add(flags, "empty_source_pdf")
            notes.append(f"source_pdf is empty: {source_pdf}")

    if not question_number:
        _add(flags, "missing_question_number")
    if not paper_family:
        _add(flags, "missing_paper_family")
    elif paper_family not in TARGET_PAPER_FAMILIES:
        _add(flags, "invalid_paper_family")
        notes.append(f"paper_family must be one of {', '.join(TARGET_PAPER_FAMILIES)}")

    topic_values = _topic_values(record.get("topic"))
    if not topic_values:
        _add(flags, "missing_topic")
    elif len(topic_values) != 1:
        _add(flags, "multiple_final_topics")
        notes.append("topic must contain exactly one final topic")
    elif paper_family in ALLOWED_TOPICS_BY_PAPER and topic_values[0] not in ALLOWED_TOPICS_BY_PAPER[paper_family]:
        _add(flags, "invalid_topic_for_paper")
        notes.append(f"{topic_values[0]} is not valid for {paper_family}")

    if not source_pdf or not question_number or not paper_family or not topic_values:
        _add(flags, "record_incomplete")

    _check_question_image(record, question_image, question_bank_path, flags, notes)
    _check_markscheme_image(record, markscheme_image, question_bank_path, flags, notes)
    _check_markscheme_header(record, flags, notes)
    _check_mapping_consistency(record, flags, notes)
    _check_existing_review_flags(review_flags, flags, notes)
    question_resolved = _resolve_path(question_image, question_bank_path.parent) if question_image else None
    markscheme_resolved = _resolve_path(markscheme_image, question_bank_path.parent) if markscheme_image else None

    status = _status_for_flags(flags)
    return {
        "record_index": record_index,
        "source_pdf": source_pdf,
        "paper_name": paper_name,
        "question_number": question_number,
        "paper_family": paper_family,
        "topic": topic,
        "question_image": question_image,
        "markscheme_image": markscheme_image,
        "question_image_exists": bool(question_resolved and question_resolved.exists()),
        "question_image_resolved_path": str(question_resolved) if question_resolved else "",
        "markscheme_image_exists": bool(markscheme_resolved and markscheme_resolved.exists()),
        "markscheme_image_resolved_path": str(markscheme_resolved) if markscheme_resolved else "",
        "qa_status": status,
        "qa_flags": sorted(flags),
        "qa_notes": _dedupe(notes),
        "question_crop_confidence": _text(record.get("question_crop_confidence")),
        "markscheme_crop_confidence": _text(record.get("markscheme_crop_confidence")),
        "markscheme_mapping_method": _text(record.get("markscheme_mapping_method")),
        "markscheme_table_detected": bool(record.get("markscheme_table_detected")),
        "markscheme_table_header_detected": _list_text(record.get("markscheme_table_header_detected")),
        "review_flags": review_flags,
    }


def _load_question_bank(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Question bank JSON must be a list of records.")
    records: list[dict[str, Any]] = []
    for item in data:
        records.append(item if isinstance(item, dict) else {"value": item})
    return records


def _check_question_image(
    record: dict[str, Any],
    image_value: str,
    question_bank_path: Path,
    flags: list[str],
    notes: list[str],
) -> None:
    if not image_value:
        _add(flags, "missing_question_image")
        return

    image_path = _resolve_path(image_value, question_bank_path.parent)
    metrics = _probe_image(image_path)
    _apply_image_metrics("question", metrics, flags, notes)

    crop_confidence = _text(record.get("question_crop_confidence")).lower()
    if bool(record.get("crop_uncertain")) or crop_confidence in LOW_CONFIDENCE_VALUES:
        _add(flags, "question_crop_low_confidence")
        notes.append("question crop confidence is not high")

    question_text = _text(record.get("combined_question_text")).lower()
    if "turn over" in question_text or "header_footer_contamination" in _list_text(record.get("review_flags")):
        _add(flags, "possible_footer_in_question_crop")
        notes.append("question text metadata contains likely footer/header text")
    if "do not write in this margin" in question_text:
        _add(flags, "possible_margin_text_in_question_crop")
        notes.append("question text metadata contains vertical margin text")
    if "additional page" in question_text:
        _add(flags, "possible_additional_page_in_question_crop")
        notes.append("question text contains likely Additional Page boilerplate")
    if "© ucles" in question_text:
        _add(flags, "possible_copyright_in_question_crop")
        notes.append("question text contains likely copyright/footer text")


def _check_markscheme_image(
    record: dict[str, Any],
    image_value: str,
    question_bank_path: Path,
    flags: list[str],
    notes: list[str],
) -> None:
    if not image_value:
        _add(flags, "missing_markscheme_image")
        return

    image_path = _resolve_path(image_value, question_bank_path.parent)
    metrics = _probe_image(image_path)
    _apply_image_metrics("markscheme", metrics, flags, notes)

    crop_confidence = _text(record.get("markscheme_crop_confidence")).lower()
    if crop_confidence in LOW_CONFIDENCE_VALUES:
        _add(flags, "markscheme_crop_low_confidence")
        notes.append("mark scheme crop confidence is not high")


def _check_markscheme_header(record: dict[str, Any], flags: list[str], notes: list[str]) -> None:
    header = _normalize_header(record.get("markscheme_table_header_detected"))
    table_detected = bool(record.get("markscheme_table_detected"))
    table_header_ok = bool(record.get("markscheme_table_header_ok"))
    markscheme_text = _text(record.get("markscheme_text") or record.get("answer_text"))
    review_flags = set(_list_text(record.get("review_flags")))

    if table_header_ok:
        return
    if header:
        if tuple(header) != EXPECTED_MARKSCHEME_HEADER:
            _add(flags, "markscheme_header_not_found")
            _add(flags, "possible_nonstandard_markscheme_table")
            notes.append("mark scheme table header metadata does not match Question | Answer | Marks | Guidance")
        return

    text_has_expected_header = _text_has_expected_markscheme_header(markscheme_text)
    if not table_detected and not text_has_expected_header:
        _add(flags, "markscheme_header_not_found")
        notes.append("expected mark scheme table header was not found in metadata")

    if (
        not table_detected
        or "markscheme_answer_table_header_missing" in review_flags
        or "markscheme_table_detection_failed" in review_flags
        or _looks_like_rubric_table(markscheme_text)
    ):
        _add(flags, "possible_nonstandard_markscheme_table")
        notes.append("mark scheme metadata suggests a fallback or nonstandard table")


def _check_mapping_consistency(record: dict[str, Any], flags: list[str], notes: list[str]) -> None:
    question_number = _text(record.get("question_number"))
    markscheme_question_number = _text(record.get("markscheme_question_number"))
    if markscheme_question_number and question_number and _normalize_question_number(markscheme_question_number) != _normalize_question_number(question_number):
        _add(flags, "markscheme_question_number_mismatch")
        notes.append(f"mark scheme question number is {markscheme_question_number}, expected {question_number}")
    if record.get("markscheme_image") and record.get("markscheme_table_header_ok") is False and not bool(record.get("markscheme_table_detected")):
        _add(flags, "markscheme_header_not_ok")
        notes.append("mark scheme crop is not linked to the expected answer-table header")
    if record.get("markscheme_image") and not markscheme_question_number:
        _add(flags, "markscheme_label_missing")
        notes.append("mark scheme crop does not include a matched label in metadata")
    if _text(record.get("markscheme_mapping_status")) == "fail":
        reason = _text(record.get("markscheme_failure_reason"))
        if reason in {"invalid_table_header", "missing_subparts", "marks_total_mismatch", "partial_question_block", "adjacent_question_block_selected"}:
            _add(flags, reason)
            notes.append(f"mark scheme mapping failed: {reason}")

    paper_family = _text(record.get("paper_family"))
    source_paper_family = _text(record.get("source_paper_family"))
    inferred_paper_family = _text(record.get("inferred_paper_family"))
    if source_paper_family in TARGET_PAPER_FAMILIES and paper_family in TARGET_PAPER_FAMILIES and source_paper_family != paper_family:
        _add(flags, "paper_family_source_mismatch")
        notes.append(f"source paper family is {source_paper_family}, final paper_family is {paper_family}")
    if inferred_paper_family in TARGET_PAPER_FAMILIES and paper_family in TARGET_PAPER_FAMILIES and inferred_paper_family != paper_family:
        _add(flags, "paper_family_source_mismatch")
        notes.append(f"inferred paper family is {inferred_paper_family}, final paper_family is {paper_family}")

    nearby_anchors = _list_text(record.get("markscheme_nearby_anchors"))
    if question_number and nearby_anchors and _normalize_question_number(question_number) not in {_normalize_question_number(anchor) for anchor in nearby_anchors}:
        _add(flags, "markscheme_crop_suspicious")
        notes.append("question number was not present in nearby mark scheme anchors")


def _check_existing_review_flags(review_flags: list[str], flags: list[str], notes: list[str]) -> None:
    review_flag_set = set(review_flags)
    if {"low_confidence_question_crop", "crop_uncertain", "crop_fallback_used"} & review_flag_set:
        _add(flags, "question_crop_low_confidence")
    if {"crop_reaches_page_margin", "answer_space_heavy", "possible_next_question_contamination"} & review_flag_set:
        _add(flags, "question_crop_suspicious")
    if {"header_footer_contamination"} & review_flag_set:
        _add(flags, "possible_footer_in_question_crop")
    if {"text_figure_overlap_trimmed", "question_text_figure_overlap_prevented"} & review_flag_set:
        _add(flags, "question_text_figure_overlap_trimmed")
        notes.append("question text crop overlapped a detected figure and was trimmed before rendering")
    if {"text_figure_overlap_unresolved"} & review_flag_set:
        _add(flags, "text_figure_overlap_in_question_crop")
        _add(flags, "possible_duplicate_figure_content")
        _add(flags, "question_crop_suspicious")
        notes.append("question crop still has unresolved text/figure overlap")
    if {"duplicate_visual_fragment_excluded"} & review_flag_set:
        _add(flags, "duplicate_visual_regions_detected")
        notes.append("duplicate or overlapping visual figure sources were detected during crop selection")
    cleanup_flags = sorted(
        flag
        for flag in review_flag_set
        if flag.endswith("_excluded")
        or flag.startswith("excluded_boilerplate_")
        or flag
        in {
            "duplicate_visual_regions_removed",
            "figure_region_separated",
            "text_figure_overlap_trimmed",
            "question_text_figure_overlap_prevented",
            "overlapping_crop_region_trimmed",
        }
    )
    if cleanup_flags:
        notes.append(f"crop cleanup applied: {', '.join(cleanup_flags)}")
    if {"impossible_question_number_anchor_excluded"} & review_flag_set:
        _add(flags, "question_crop_suspicious")
        notes.append("an impossible question-number anchor was excluded from the crop span")
    if {"markscheme_image_uncertain", "markscheme_table_continuation_inferred"} & review_flag_set:
        _add(flags, "markscheme_crop_low_confidence")
    if {"markscheme_image_no_boundaries", "markscheme_no_row_for_question"} & review_flag_set:
        _add(flags, "markscheme_crop_suspicious")
    if {"markscheme_answer_table_header_missing", "markscheme_table_detection_failed"} & review_flag_set:
        _add(flags, "markscheme_header_not_found")
        _add(flags, "possible_nonstandard_markscheme_table")
    for reason in ["invalid_table_header", "missing_subparts", "marks_total_mismatch", "partial_question_block", "adjacent_question_block_selected"]:
        if reason in review_flag_set:
            _add(flags, reason)
    if review_flags:
        notes.append(f"source review flags: {', '.join(review_flags)}")


def _probe_image(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path)}
    try:
        from PIL import Image as PILImage
        from PIL import ImageStat
        from PIL.Image import DecompressionBombWarning
    except ImportError:
        return {"exists": True, "readable": False, "path": str(path), "error": "Pillow is not installed"}
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DecompressionBombWarning)
            with PILImage.open(path) as image:
                width, height = image.size
                sample = image.convert("RGB")
                sample.thumbnail((1000, 1000))
                gray = sample.convert("L")
                histogram = gray.histogram()
                total = sum(histogram) or 1
                nonwhite = sum(count for value, count in enumerate(histogram) if value < 245)
                stat = ImageStat.Stat(gray)
            bomb_warnings = [warning for warning in caught if issubclass(warning.category, DecompressionBombWarning)]
            return {
                "exists": True,
                "readable": True,
                "path": str(path),
                "width": width,
                "height": height,
                "pixels": width * height,
                "nonwhite_ratio": nonwhite / total,
                "stddev": float(stat.stddev[0]),
                "decompression_bomb_warning": bool(bomb_warnings) or (width * height > SAFE_PROBE_PIXELS),
            }
    except Exception as exc:
        return {"exists": True, "readable": False, "path": str(path), "error": exc.__class__.__name__}


def _apply_image_metrics(kind: str, metrics: dict[str, Any], flags: list[str], notes: list[str]) -> None:
    prefix = "question" if kind == "question" else "markscheme"
    display = "question" if kind == "question" else "mark scheme"
    if not metrics.get("exists"):
        _add(flags, f"missing_{prefix}_image")
        notes.append(f"{display} image not found: {metrics.get('path')}")
        return
    if not metrics.get("readable"):
        _add(flags, f"{prefix}_image_unreadable")
        notes.append(f"{display} image could not be opened: {metrics.get('error', 'unknown error')}")
        return

    width = int(metrics["width"])
    height = int(metrics["height"])
    pixels = int(metrics["pixels"])
    nonwhite_ratio = float(metrics["nonwhite_ratio"])
    stddev = float(metrics["stddev"])
    notes.append(f"{display} image {width}x{height}, nonwhite={nonwhite_ratio:.4f}, stddev={stddev:.2f}")
    if metrics.get("decompression_bomb_warning"):
        notes.append(f"{display} image is very large; opened deliberately for QA probing")

    if width < 120 or height < 60 or pixels < 10000:
        _add(flags, f"{prefix}_crop_too_small")
    elif width < 300 or height < 100:
        _add(flags, f"{prefix}_crop_suspicious")

    if stddev < 1.5 or nonwhite_ratio < 0.001:
        _add(flags, f"{prefix}_crop_blank")
    elif stddev < 5.0 or nonwhite_ratio < 0.004:
        _add(flags, f"{prefix}_crop_suspicious")

    if height > 1000 and height / max(width, 1) > 4.5:
        _add(flags, f"{prefix}_crop_suspicious")
        notes.append(f"{display} image is suspiciously tall")


def _write_csv(records: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow({field: _csv_value(record.get(field)) for field in CSV_FIELDS})


def _write_review_html(output_path: Path, payload: dict[str, Any]) -> None:
    output_path.write_text(_review_html(payload), encoding="utf-8")


def _review_html(payload: dict[str, Any]) -> str:
    embedded_payload = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>QA Review</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #172018;
      --muted: #5e665f;
      --line: #cbd5cc;
      --panel: #f5f7f2;
      --pass: #1f7a45;
      --warning: #956800;
      --fail: #b42318;
      --surface: #ffffff;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      color: var(--ink);
      background: #fbfbf8;
      font-family: Arial, Helvetica, sans-serif;
      line-height: 1.45;
    }

    header,
    main {
      width: min(1180px, calc(100% - 32px));
      margin: 0 auto;
    }

    header {
      padding: 28px 0 18px;
    }

    h1 {
      margin: 0 0 8px;
      font-size: 30px;
      letter-spacing: 0;
    }

    .summary {
      color: var(--muted);
      margin: 0;
    }

    .controls {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: end;
      padding: 16px 0 20px;
      border-top: 1px solid var(--line);
      border-bottom: 1px solid var(--line);
    }

    label {
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 13px;
    }

    select,
    input[type="file"] {
      min-width: 190px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 10px;
      background: var(--surface);
      color: var(--ink);
      font: inherit;
    }

    .record {
      padding: 22px 0;
      border-bottom: 1px solid var(--line);
    }

    .record-header {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;
    }

    .identity {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      font-weight: 700;
    }

    .badge {
      display: inline-flex;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 3px 8px;
      background: var(--surface);
      font-size: 13px;
    }

    .status-pass {
      color: var(--pass);
      border-color: #84c49a;
    }

    .status-warning {
      color: var(--warning);
      border-color: #d4b35f;
    }

    .status-fail {
      color: var(--fail);
      border-color: #dc8b84;
    }

    .flags {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin: 8px 0 14px;
    }

    .flag {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 3px 7px;
      background: var(--panel);
      color: var(--ink);
      font-size: 12px;
      overflow-wrap: anywhere;
    }

    .images {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }

    figure {
      margin: 0;
    }

    figcaption {
      margin-bottom: 6px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
    }

    img {
      display: block;
      width: 100%;
      max-height: 760px;
      object-fit: contain;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--surface);
    }

    .notes {
      margin: 12px 0 0;
      color: var(--muted);
      font-size: 13px;
      overflow-wrap: anywhere;
    }

    .asset-debug {
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }

    .empty {
      padding: 34px 0;
      color: var(--muted);
    }

    @media (max-width: 760px) {
      header,
      main {
        width: min(100% - 20px, 1180px);
      }

      .images {
        grid-template-columns: 1fr;
      }

      h1 {
        font-size: 24px;
      }
    }
  </style>
</head>
<body>
  <header>
    <h1>QA Review</h1>
    <p class="summary" id="summary">Loading QA report.</p>
  </header>
  <main>
    <section class="controls" aria-label="Filters">
      <label>Status
        <select id="statusFilter">
          <option value="">All statuses</option>
          <option value="fail">Fail</option>
          <option value="warning">Warning</option>
          <option value="pass">Pass</option>
        </select>
      </label>
      <label>Flag
        <select id="flagFilter">
          <option value="">All flags</option>
        </select>
      </label>
      <label>QA JSON
        <input id="jsonFile" type="file" accept="application/json">
      </label>
    </section>
    <section id="records" aria-live="polite"></section>
  </main>
  <script id="qaPayload" type="application/json">__QA_PAYLOAD__</script>
  <script>
    const state = { records: [], summary: {} };
    const statusFilter = document.querySelector("#statusFilter");
    const flagFilter = document.querySelector("#flagFilter");
    const jsonFile = document.querySelector("#jsonFile");
    const summary = document.querySelector("#summary");
    const records = document.querySelector("#records");

    function imagePath(path) {
      if (!path) return "";
      if (/^(https?:)?\\/\\//.test(path) || path.startsWith("data:") || path.startsWith("/") || path.startsWith("../")) return path;
      if (path.startsWith("./")) return path;
      return `../../${path}`;
    }

    function setReport(payload) {
      state.records = Array.isArray(payload) ? payload : payload.records || [];
      state.summary = Array.isArray(payload) ? {} : payload.summary || {};
      updateFlagOptions();
      render();
    }

    function updateFlagOptions() {
      const flags = [...new Set(state.records.flatMap((record) => record.qa_flags || []))].sort();
      flagFilter.innerHTML = '<option value="">All flags</option>';
      for (const flag of flags) {
        const option = document.createElement("option");
        option.value = flag;
        option.textContent = flag;
        flagFilter.appendChild(option);
      }
    }

    function filteredRecords() {
      const status = statusFilter.value;
      const flag = flagFilter.value;
      return state.records.filter((record) => {
        if (status && record.qa_status !== status) return false;
        if (flag && !(record.qa_flags || []).includes(flag)) return false;
        return true;
      });
    }

    function render() {
      const visible = filteredRecords();
      const counts = state.summary.status_counts || {};
      summary.textContent = `${visible.length} shown. Pass ${counts.pass || 0}, warning ${counts.warning || 0}, fail ${counts.fail || 0}.`;
      records.innerHTML = "";
      if (!visible.length) {
        records.innerHTML = '<p class="empty">No records match these filters.</p>';
        return;
      }
      for (const record of visible) {
        const article = document.createElement("article");
        article.className = "record";
        const flags = (record.qa_flags || []).map((flag) => `<span class="flag">${escapeHtml(flag)}</span>`).join("");
        const notes = (record.qa_notes || []).map(escapeHtml).join(" · ");
        article.innerHTML = `
          <div class="record-header">
            <div class="identity">
              <span>${escapeHtml(record.paper_family || "unknown")}</span>
              <span>${escapeHtml(record.topic || "missing topic")}</span>
              <span>Question ${escapeHtml(record.question_number || "missing")}</span>
            </div>
            <span class="badge status-${escapeHtml(record.qa_status)}">${escapeHtml(record.qa_status)}</span>
          </div>
          <div class="flags">${flags || '<span class="flag">no flags</span>'}</div>
          <div class="images">
            <figure>
              <figcaption>Question</figcaption>
              ${record.question_image ? `<img loading="lazy" data-kind="question" src="${escapeAttribute(imagePath(record.question_image))}" alt="Question ${escapeAttribute(record.question_number || "")}">` : '<p class="empty">Missing question image.</p>'}
              ${assetDebug(record, "question")}
            </figure>
            <figure>
              <figcaption>Mark Scheme</figcaption>
              ${record.markscheme_image ? `<img loading="lazy" data-kind="markscheme" src="${escapeAttribute(imagePath(record.markscheme_image))}" alt="Mark scheme ${escapeAttribute(record.question_number || "")}">` : '<p class="empty">Missing mark scheme image.</p>'}
              ${assetDebug(record, "markscheme")}
            </figure>
          </div>
          ${notes ? `<p class="notes">${notes}</p>` : ""}
        `;
        records.appendChild(article);
      }
      article.querySelectorAll("img").forEach((image) => {
        image.addEventListener("error", () => {
          const kind = image.dataset.kind || "image";
          console.warn("QA image failed to load", {
            record_id: `${record.paper_family || "unknown"}:${record.topic || "unknown"}:${record.question_number || "missing"}`,
            kind,
            image_src: image.getAttribute("src"),
            expected_image_path: kind === "question" ? record.question_image : record.markscheme_image,
            resolved_path: kind === "question" ? record.question_image_resolved_path : record.markscheme_image_resolved_path,
            exists_at_generation: kind === "question" ? record.question_image_exists : record.markscheme_image_exists,
          });
        });
      });
    }

    function assetDebug(record, kind) {
      const key = kind === "question" ? "question_image" : "markscheme_image";
      const resolvedKey = kind === "question" ? "question_image_resolved_path" : "markscheme_image_resolved_path";
      const existsKey = kind === "question" ? "question_image_exists" : "markscheme_image_exists";
      const value = record[key] || "";
      if (!value) return "";
      return `<p class="asset-debug">image src: ${escapeHtml(imagePath(value))} | source: ${escapeHtml(value)} | resolved: ${escapeHtml(record[resolvedKey] || "")} | exists at generation: ${escapeHtml(record[existsKey])}</p>`;
    }

    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;",
      }[char]));
    }

    function escapeAttribute(value) {
      return escapeHtml(value).replace(/`/g, "&#096;");
    }

    async function loadDefaultReport() {
      const embedded = document.querySelector("#qaPayload");
      if (embedded && embedded.textContent.trim()) {
        setReport(JSON.parse(embedded.textContent));
        return;
      }
      try {
        const response = await fetch("qa_report.json", { cache: "no-store" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        setReport(await response.json());
      } catch (error) {
        summary.textContent = "Choose qa_report.json to begin.";
      }
    }

    statusFilter.addEventListener("change", render);
    flagFilter.addEventListener("change", render);
    jsonFile.addEventListener("change", async (event) => {
      const file = event.target.files && event.target.files[0];
      if (!file) return;
      setReport(JSON.parse(await file.text()));
    });

    loadDefaultReport();
  </script>
</body>
</html>
"""
    return html.replace("__QA_PAYLOAD__", embedded_payload)


def _status_for_flags(flags: list[str]) -> str:
    if any(flag in FAIL_FLAGS for flag in flags):
        return "fail"
    if flags:
        return "warning"
    return "pass"


def _status_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"pass": 0, "warning": 0, "fail": 0}
    for record in records:
        status = str(record.get("qa_status", ""))
        if status in counts:
            counts[status] += 1
    return counts


def _flag_counts(records: list[dict[str, Any]], only_flags: set[str] | None = None) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for record in records:
        counts.update(str(flag) for flag in record.get("qa_flags", []) if only_flags is None or str(flag) in only_flags)
    priority = {flag: index for index, flag in enumerate(FLAG_PRIORITY)}
    return dict(sorted(counts.items(), key=lambda item: (-item[1], priority.get(item[0], len(priority)), item[0])))


def _top_flag(records: list[dict[str, Any]], only_flags: set[str] | None = None) -> dict[str, Any] | None:
    counts = _flag_counts(records, only_flags=only_flags)
    if not counts:
        return None
    flag, count = next(iter(counts.items()))
    return {"flag": flag, "count": count}


def _resolve_path(value: str, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    candidates = [
        Path.cwd() / path,
        base_dir / path,
        base_dir.parent / path,
        base_dir.parent.parent / path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _normalize_header(value: Any) -> list[str]:
    return [_normalize_header_cell(item) for item in _list_text(value) if _normalize_header_cell(item)]


def _normalize_header_cell(value: str) -> str:
    cleaned = re.sub(r"[^a-z]+", " ", value.lower()).strip()
    if cleaned in {"mark", "marks"}:
        return "marks"
    return cleaned


def _text_has_expected_markscheme_header(text: str) -> bool:
    cleaned = re.sub(r"[^a-z]+", " ", text.lower())
    position = 0
    for term in EXPECTED_MARKSCHEME_HEADER:
        next_position = cleaned.find(term, position)
        if next_position < 0:
            return False
        position = next_position + len(term)
    return True


def _looks_like_rubric_table(text: str) -> bool:
    cleaned = text.lower()
    rubric_terms = [
        "generic marking principles",
        "marking principles",
        "abbreviations",
        "cao",
        "isw",
        "m marks",
        "a marks",
        "b marks",
        "ft marks",
    ]
    return any(term in cleaned for term in rubric_terms)


def _topic_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    text = _text(value)
    if not text:
        return []
    if re.search(r"[,;|]", text):
        return [item.strip() for item in re.split(r"[,;|]", text) if item.strip()]
    return [text]


def _raw_topic(value: Any) -> str:
    if isinstance(value, list):
        return ";".join(_text(item) for item in value if _text(item))
    return _text(value)


def _normalize_question_number(value: str) -> str:
    cleaned = value.strip().lower()
    match = re.search(r"\d+", cleaned)
    return (match.group(0).lstrip("0") or "0") if match else cleaned


def _csv_value(value: Any) -> str:
    if isinstance(value, list):
        return ";".join(str(item) for item in value)
    if value is None:
        return ""
    return str(value)


def _list_text(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    if isinstance(value, tuple):
        return [_text(item) for item in value if _text(item)]
    if isinstance(value, str):
        if not value.strip():
            return []
        return [item.strip() for item in re.split(r"[;,]", value) if item.strip()]
    return [_text(value)] if _text(value) else []


def _list_int(value: Any) -> list[int]:
    numbers: list[int] = []
    for item in _list_text(value):
        try:
            numbers.append(int(item))
        except ValueError:
            continue
    return numbers


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _add(flags: list[str], flag: str) -> None:
    if flag not in flags:
        flags.append(flag)


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return deduped
