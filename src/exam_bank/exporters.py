from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import AppConfig
from .models import QuestionRecord
from .output_layout import component_code_from_values, paper_family_dir_name, paper_instance_id, question_id


def export_records(records: list[QuestionRecord], config: AppConfig, basename: str | None = None) -> Path:
    config.ensure_output_dirs()
    json_name = f"{basename}.json" if basename else config.naming.json_name
    json_path = config.output.json_dir / json_name
    write_json(records, json_path, output_root=config.output.root_dir())
    return json_path


def write_json(records: list[QuestionRecord], output_path: str | Path, *, output_root: str | Path | None = None) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    root = Path(output_root) if output_root is not None else None
    output_path.write_text(
        json.dumps([_record_to_output_dict(record, root) for record in records], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return output_path


def _record_to_output_dict(record: QuestionRecord, output_root: Path | None) -> dict[str, Any]:
    paper = paper_instance_id(
        record.component or record.source_paper_code,
        record.session,
        record.year,
    )
    family = paper_family_dir_name(record.paper_family or record.question_level_paper_family)
    subparts = list(record.question_subparts or record.markscheme_subparts)
    question_image_paths = _path_list(record.screenshot_path, output_root)
    mark_scheme_image_paths = _path_list(record.markscheme_image, output_root)
    question_solution_marks = _question_solution_marks(record)

    return {
        "question_id": question_id(paper, record.question_number),
        "paper": paper,
        "paper_family": family,
        "question_number": record.question_number,
        "question_text": record.combined_question_text,
        "mark_scheme_text": record.answer_text,
        "question_solution_marks": question_solution_marks,
        "subparts": subparts,
        "subparts_solution_marks": {label: None for label in subparts},
        "question_image_paths": question_image_paths,
        "mark_scheme_image_paths": mark_scheme_image_paths,
        "page_refs": {
            "question": list(record.page_numbers),
            "mark_scheme": list(record.markscheme_pages),
        },
        "topic": record.question_level_topic or record.topic,
        "notes": {
            "subtopic": record.question_level_subtopic or record.subtopic,
            "source_pdf": record.source_pdf,
            "mark_scheme_source_pdf": record.mark_scheme_source_pdf,
            "source_paper_code": component_code_from_values(record.component, record.source_paper_code),
            "full_question_label": record.full_question_label,
            "mapping_status": record.markscheme_mapping_status,
            "mapping_failure_reason": record.markscheme_failure_reason,
            "question_crop_confidence": record.question_crop_confidence or ("low" if record.crop_uncertain else "high"),
            "mark_scheme_crop_confidence": record.markscheme_crop_confidence,
            "review_flags": list(record.review_flags),
            "extraction_quality_score": round(record.extraction_quality_score, 3),
            "extraction_quality_flags": list(record.extraction_quality_flags),
        },
    }


def _question_solution_marks(record: QuestionRecord) -> int | None:
    for value in [record.markscheme_marks_total, record.question_marks_total, record.marks_if_available, record.marks]:
        if value is not None:
            return int(value)
    return None


def _path_list(path_value: str, output_root: Path | None) -> list[str]:
    if not path_value:
        return []
    return [_relative_output_path(path_value, output_root)]


def _relative_output_path(path_value: str, output_root: Path | None) -> str:
    path = Path(path_value)
    if output_root is None:
        return str(path)
    try:
        return str(path.relative_to(output_root))
    except ValueError:
        return str(path)
