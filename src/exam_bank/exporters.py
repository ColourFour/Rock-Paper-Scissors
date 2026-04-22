from __future__ import annotations

import csv
import json
from pathlib import Path

from .config import AppConfig
from .models import QuestionRecord


def export_records(records: list[QuestionRecord], config: AppConfig, basename: str | None = None) -> tuple[Path, Path]:
    config.ensure_output_dirs()
    json_name = f"{basename}.json" if basename else config.naming.json_name
    csv_name = f"{basename}.csv" if basename else config.naming.csv_name
    json_path = config.output.json_dir / json_name
    csv_path = config.output.csv_dir / csv_name
    write_json(records, json_path)
    write_csv(records, csv_path)
    return json_path, csv_path


def write_json(records: list[QuestionRecord], output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([record.to_dict() for record in records], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return output_path


def write_csv(records: list[QuestionRecord], output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [_record_to_csv_row(record) for record in records]
    if not rows:
        rows = [_empty_row()]

    try:
        import pandas as pd
    except ImportError:
        _write_csv_stdlib(rows, output_path)
    else:
        pd.DataFrame(rows).to_csv(output_path, index=False)
    return output_path


def _write_csv_stdlib(rows: list[dict[str, object]], output_path: Path) -> None:
    fieldnames = list(rows[0].keys())
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _empty_row() -> dict[str, object]:
    return {
        "source_pdf": "",
        "paper_name": "",
        "question_number": "",
        "full_question_label": "",
        "question_image": "",
        "question_image_link": "",
        "question_pages": "",
        "question_crop_confidence": "",
        "screenshot_path": "",
        "body_text_raw": "",
        "body_text_normalized": "",
        "math_lines": "",
        "diagram_text": "",
        "extraction_quality_score": "",
        "extraction_quality_flags": "",
        "part_texts": "",
        "answer_text": "",
        "markscheme_text": "",
        "markscheme_image": "",
        "markscheme_pages": "",
        "markscheme_question_number": "",
        "markscheme_crop_confidence": "",
        "markscheme_mapping_method": "",
        "markscheme_table_detected": "",
        "markscheme_table_header_detected": "",
        "markscheme_nearby_anchors": "",
        "markscheme_debug_paths": "",
        "question_subparts": "",
        "markscheme_subparts": "",
        "question_marks_total": "",
        "markscheme_marks_total": "",
        "markscheme_mapping_status": "",
        "markscheme_failure_reason": "",
        "paper_family": "",
        "source_paper_code": "",
        "syllabus_code": "",
        "session": "",
        "year": "",
        "document_type": "",
        "component": "",
        "document_key": "",
        "metadata_source": "",
        "source_paper_family": "",
        "inferred_paper_family": "",
        "paper_family_confidence": "",
        "question_level_paper_family": "",
        "question_level_topic": "",
        "question_level_subtopic": "",
        "part_level_topics": "",
        "topic": "",
        "subtopic": "",
        "topic_confidence": "",
        "topic_evidence": "",
        "examiner_report_evidence": "",
        "secondary_topics": "",
        "topic_uncertain": "",
        "topic_alternatives": "",
        "difficulty": "",
        "difficulty_confidence": "",
        "difficulty_evidence": "",
        "difficulty_uncertain": "",
        "reconciliation_changed_topic": "",
        "reconciliation_reason": "",
        "reconciliation_note": "",
        "paper_repair_considered": "",
        "paper_repair_changed_topic": "",
        "paper_repair_reason": "",
        "paper_repair_note": "",
        "paper_repair_from_topic": "",
        "paper_repair_to_topic": "",
        "paper_repair_candidates": "",
        "paper_repair_missing_topics": "",
        "paper_repair_supporting_evidence": "",
        "marks": "",
        "marks_if_available": "",
        "page_numbers": "",
        "review_flags": "",
        "confidence": "",
        "crop_uncertain": "",
        "crop_debug_paths": "",
    }


def _record_to_csv_row(record: QuestionRecord) -> dict[str, object]:
    data = record.to_dict()
    screenshot_path = str(data["screenshot_path"])
    return {
        "source_pdf": data["source_pdf"],
        "paper_name": data["paper_name"],
        "question_number": data["question_number"],
        "full_question_label": data["full_question_label"],
        "question_image": screenshot_path,
        "question_image_link": _hyperlink_formula(screenshot_path),
        "question_pages": ",".join(str(page) for page in data["question_pages"]),
        "question_crop_confidence": data["question_crop_confidence"],
        "screenshot_path": screenshot_path,
        # Preserve the richer extraction structure in JSON while keeping CSV
        # focused on image-first review and metadata.
        "body_text_raw": "",
        "body_text_normalized": "",
        "math_lines": "",
        "diagram_text": "",
        "extraction_quality_score": data["extraction_quality_score"],
        "extraction_quality_flags": ";".join(str(flag) for flag in data["extraction_quality_flags"]),
        "part_texts": "",
        "answer_text": data["answer_text"],
        "markscheme_text": data["markscheme_text"],
        "markscheme_image": data["markscheme_image"],
        "markscheme_pages": ",".join(str(page) for page in data["markscheme_pages"]),
        "markscheme_question_number": data["markscheme_question_number"],
        "markscheme_crop_confidence": data["markscheme_crop_confidence"],
        "markscheme_mapping_method": data["markscheme_mapping_method"],
        "markscheme_table_detected": "true" if data["markscheme_table_detected"] else "false",
        "markscheme_table_header_detected": ",".join(str(header) for header in data["markscheme_table_header_detected"]),
        "markscheme_nearby_anchors": ";".join(str(anchor) for anchor in data["markscheme_nearby_anchors"]),
        "markscheme_debug_paths": ",".join(str(path) for path in data["markscheme_debug_paths"]),
        "question_subparts": ";".join(str(part) for part in data["question_subparts"]),
        "markscheme_subparts": ";".join(str(part) for part in data["markscheme_subparts"]),
        "question_marks_total": data["question_marks_total"] if data["question_marks_total"] is not None else "",
        "markscheme_marks_total": data["markscheme_marks_total"] if data["markscheme_marks_total"] is not None else "",
        "markscheme_mapping_status": data["markscheme_mapping_status"],
        "markscheme_failure_reason": data["markscheme_failure_reason"],
        "paper_family": data["paper_family"],
        "source_paper_code": data["source_paper_code"],
        "syllabus_code": data["syllabus_code"],
        "session": data["session"],
        "year": data["year"],
        "document_type": data["document_type"],
        "component": data["component"],
        "document_key": data["document_key"],
        "metadata_source": data["metadata_source"],
        "source_paper_family": data["source_paper_family"],
        "inferred_paper_family": data["inferred_paper_family"],
        "paper_family_confidence": data["paper_family_confidence"],
        "question_level_paper_family": data["question_level_paper_family"],
        "question_level_topic": data["question_level_topic"],
        "question_level_subtopic": data["question_level_subtopic"],
        "part_level_topics": json.dumps(data["part_level_topics"], ensure_ascii=False),
        "topic": data["topic"],
        "subtopic": data["subtopic"],
        "topic_confidence": data["topic_confidence"],
        "topic_evidence": data["topic_evidence"],
        "examiner_report_evidence": json.dumps(data["examiner_report_evidence"], ensure_ascii=False),
        "secondary_topics": ";".join(str(topic) for topic in data["secondary_topics"]),
        "topic_uncertain": "true" if data["topic_uncertain"] else "false",
        "topic_alternatives": ";".join(str(topic) for topic in data["topic_alternatives"]),
        "difficulty": data["difficulty"],
        "difficulty_confidence": data["difficulty_confidence"],
        "difficulty_evidence": data["difficulty_evidence"],
        "difficulty_uncertain": "true" if data["difficulty_uncertain"] else "false",
        "reconciliation_changed_topic": "true" if data["reconciliation_changed_topic"] else "false",
        "reconciliation_reason": data["reconciliation_reason"],
        "reconciliation_note": data["reconciliation_note"],
        "paper_repair_considered": "true" if data["paper_repair_considered"] else "false",
        "paper_repair_changed_topic": "true" if data["paper_repair_changed_topic"] else "false",
        "paper_repair_reason": data["paper_repair_reason"],
        "paper_repair_note": data["paper_repair_note"],
        "paper_repair_from_topic": data["paper_repair_from_topic"],
        "paper_repair_to_topic": data["paper_repair_to_topic"],
        "paper_repair_candidates": ";".join(str(topic) for topic in data["paper_repair_candidates"]),
        "paper_repair_missing_topics": ";".join(str(topic) for topic in data["paper_repair_missing_topics"]),
        "paper_repair_supporting_evidence": json.dumps(data["paper_repair_supporting_evidence"], ensure_ascii=False),
        "marks": data["marks"],
        "marks_if_available": data["marks_if_available"],
        "page_numbers": ",".join(str(page) for page in data["page_numbers"]),
        "review_flags": ",".join(str(flag) for flag in data["review_flags"]),
        "confidence": data["confidence"],
        "crop_uncertain": "true" if data["crop_uncertain"] else "false",
        "crop_debug_paths": ",".join(str(path) for path in data["crop_debug_paths"]),
    }


def _hyperlink_formula(path: str) -> str:
    escaped_path = path.replace('"', '""')
    return f'=HYPERLINK("{escaped_path}","question image")'
