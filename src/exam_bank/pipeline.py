from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

from .classification import classify_question, classify_question_parts, infer_source_paper_code
from .config import AppConfig
from .document_metadata import DocumentMetadata, parse_filename_metadata, parse_internal_document_metadata, reconcile_document_metadata
from .document_registry import DocumentRegistry, build_document_registry, build_document_registry_from_paths
from .examiner_reports import examiner_report_topic_evidence
from .exporters import export_records
from .image_rendering import render_question_image
from .mark_schemes import MarkSchemeImageResult, extract_mark_scheme_answers, find_mark_scheme, render_mark_scheme_images
from .models import ClassificationResult, PageLayout, QuestionRecord, QuestionSpan
from .pdf_extract import extract_pdf_layout
from .question_detection import detect_question_anchor_candidates, detect_question_spans, extract_marks_from_text
from .review import write_review_file


@dataclass(frozen=True)
class PipelineResult:
    records: list[QuestionRecord]
    json_path: Path
    csv_path: Path
    review_path: Path


def process_batch(config: AppConfig) -> PipelineResult:
    config.ensure_output_dirs()
    registry = build_document_registry_from_paths(
        [
            config.input.question_papers_dir,
            config.input.mark_schemes_dir,
            config.input.examiner_reports_dir,
        ]
    )
    return _process_registry_entries(registry, config)


def process_folder(folder: str | Path, config: AppConfig) -> PipelineResult:
    config.ensure_output_dirs()
    registry = build_document_registry(folder)
    return _process_registry_entries(registry, config)


def _process_registry_entries(registry: DocumentRegistry, config: AppConfig) -> PipelineResult:
    records: list[QuestionRecord] = []
    for entry in registry.question_paper_entries():
        assert entry.question_paper is not None
        question_metadata = entry.metadata_by_path.get(str(entry.question_paper))
        records.extend(
            build_records_for_pdf(
                entry.question_paper,
                config,
                mark_scheme_pdf=entry.mark_scheme,
                examiner_report_paths=entry.examiner_reports,
                filename_metadata=question_metadata,
                registry_warnings=entry.warnings,
            )
        )
    json_path, csv_path = export_records(records, config)
    review_path = write_review_file(records, config)
    _write_batch_diagnostic(records, config)
    return PipelineResult(records, json_path, csv_path, review_path)


def process_sample(question_pdf: str | Path, config: AppConfig, mark_scheme_pdf: str | Path | None = None) -> PipelineResult:
    config.ensure_output_dirs()
    records = build_records_for_pdf(question_pdf, config, mark_scheme_pdf=mark_scheme_pdf)
    basename = _safe_basename(Path(question_pdf).stem)
    json_path, csv_path = export_records(records, config, basename=f"{basename}_sample")
    review_path = write_review_file(records, config, basename=f"{basename}_sample")
    _write_batch_diagnostic(records, config, basename=f"{basename}_sample")
    return PipelineResult(records, json_path, csv_path, review_path)


def build_records_for_pdf(
    question_pdf: str | Path,
    config: AppConfig,
    mark_scheme_pdf: str | Path | None = None,
    examiner_report_paths: list[Path] | None = None,
    filename_metadata: DocumentMetadata | None = None,
    registry_warnings: list[str] | None = None,
) -> list[QuestionRecord]:
    question_pdf = Path(question_pdf)
    layouts = extract_pdf_layout(question_pdf, config)
    parsed_filename_metadata = filename_metadata or parse_filename_metadata(question_pdf)
    internal_metadata = parse_internal_document_metadata(layouts)
    document_metadata = reconcile_document_metadata(parsed_filename_metadata, internal_metadata)
    spans = detect_question_spans(layouts, question_pdf, config)
    expected_numbers = [span.question_number for span in spans if span.question_number.isdigit()]
    expected_marks = {span.question_number: extract_marks_from_text(span.combined_text) for span in spans if span.question_number.isdigit()}
    expected_subparts = {span.question_number: _question_subparts_from_text(span.combined_text) for span in spans if span.question_number.isdigit()}

    matched_mark_scheme = Path(mark_scheme_pdf) if mark_scheme_pdf else find_mark_scheme(
        question_pdf,
        config.input.mark_schemes_dir,
        config.input.mappings_dir,
    )
    answers: dict[str, str] = {}
    mark_scheme_images: dict[str, MarkSchemeImageResult] = {}
    mark_scheme_flags: list[str] = []
    if matched_mark_scheme and matched_mark_scheme.exists():
        try:
            answers = extract_mark_scheme_answers(matched_mark_scheme, config, expected_numbers)
        except Exception as exc:
            mark_scheme_flags.append(f"mark_scheme_extract_failed:{exc.__class__.__name__}")
        try:
            mark_scheme_images = render_mark_scheme_images(
                matched_mark_scheme,
                config,
                expected_numbers,
                question_marks=expected_marks,
                question_subparts=expected_subparts,
            )
        except Exception as exc:
            mark_scheme_flags.append(f"markscheme_image_export_failed:{exc.__class__.__name__}")
    else:
        mark_scheme_flags.append("unmatched_mark_scheme")

    records: list[QuestionRecord] = []
    source_paper_code, _source_paper_code_confidence = infer_source_paper_code(question_pdf.name)
    source_paper_code = document_metadata.component or source_paper_code
    for span in spans:
        render_result = render_question_image(question_pdf, span, layouts, config)
        question_text = render_result.extracted_text or span.combined_text
        marks = extract_marks_from_text(question_text)
        answer_text = answers.get(span.question_number, "")
        mark_scheme_image = mark_scheme_images.get(span.question_number)
        examiner_evidence = examiner_report_topic_evidence(
            question_pdf,
            config.input.examiner_reports_dir,
            span.question_number,
            config,
            report_paths=examiner_report_paths,
        )
        examiner_text = examiner_evidence.classification_text if examiner_evidence else ""
        records.append(
            _build_question_record(
                question_pdf=question_pdf,
                span=span,
                question_text=question_text,
                marks=marks,
                answer_text=answer_text,
                render_result=render_result,
                mark_scheme_image=mark_scheme_image,
                mark_scheme_flags=mark_scheme_flags,
                matched_mark_scheme=matched_mark_scheme,
                document_metadata=document_metadata,
                registry_warnings=registry_warnings or [],
                config=config,
                source_paper_code=source_paper_code,
                examiner_evidence=examiner_evidence,
                examiner_text=examiner_text,
            )
        )
    _write_pdf_diagnostic(question_pdf, layouts, spans, records, config)
    _write_topic_debug_report(question_pdf, records, config)
    return records


def _build_question_record(
    *,
    question_pdf: Path,
    span: QuestionSpan,
    question_text: str,
    marks: int | None,
    answer_text: str,
    render_result,
    mark_scheme_image: MarkSchemeImageResult | None,
    mark_scheme_flags: list[str],
    matched_mark_scheme: Path | None,
    document_metadata: DocumentMetadata,
    registry_warnings: list[str],
    config: AppConfig,
    source_paper_code: str,
    examiner_evidence,
    examiner_text: str,
) -> QuestionRecord:
        flags = list(span.review_flags)
        flags.extend(mark_scheme_flags)
        flags.extend(document_metadata.warnings)
        flags.extend(registry_warnings)
        if matched_mark_scheme and matched_mark_scheme.exists() and not answer_text:
            flags.append("unmatched_answer")
        if matched_mark_scheme and matched_mark_scheme.exists():
            if mark_scheme_image is None or not mark_scheme_image.image_path:
                flags.append("markscheme_image_missing")
            elif mark_scheme_image.crop_confidence != "high":
                flags.append("markscheme_image_uncertain")
        if mark_scheme_image:
            flags.extend(mark_scheme_image.review_flags)

        if not render_result.screenshot_path:
            flags.append("missing_question_image")
        if render_result.crop_uncertain:
            flags.append("low_confidence_question_crop")
        classification = classify_question(
            question_text,
            marks,
            config,
            context_flags=flags,
            source_name=question_pdf.name,
            examiner_report_text=examiner_text,
            mark_scheme_text=answer_text,
            question_ocr_text=question_text if "ocr_question_text" in flags else "",
        )
        part_level_topics = classify_question_parts(
            question_text,
            span.question_number,
            config,
            context_flags=flags,
            source_name=question_pdf.name,
            examiner_report_text=examiner_text,
            mark_scheme_text=answer_text,
            question_ocr_text=question_text if "ocr_question_text" in flags else "",
        )
        question_topic = _question_topic_from_parts(classification, part_level_topics)
        qa_flags = _record_qa_flags(str(question_topic["paper_family"]), str(question_topic["topic"]), config, mark_scheme_image)
        flags.extend(question_topic["review_flags"])
        flags.extend(qa_flags)
        flags.extend(render_result.review_flags)
        confidence = _record_confidence(float(question_topic["confidence"]), flags)

        return QuestionRecord(
                source_pdf=_display_path(question_pdf),
                paper_name=span.paper_name,
                question_number=span.question_number,
                full_question_label=span.full_question_label,
                screenshot_path=_display_path(render_result.screenshot_path),
                combined_question_text=question_text,
                answer_text=answer_text,
                paper_family=str(question_topic["paper_family"]),
                source_paper_code=source_paper_code,
                syllabus_code=document_metadata.syllabus,
                session=document_metadata.session,
                year=document_metadata.year,
                document_type=document_metadata.document_type or "question_paper",
                component=document_metadata.component,
                document_key=document_metadata.canonical_key,
                metadata_source=document_metadata.source,
                source_paper_family=classification.source_paper_family,
                inferred_paper_family=classification.inferred_paper_family,
                paper_family_confidence=classification.paper_family_confidence,
                question_level_paper_family=str(question_topic["paper_family"]),
                question_level_topic=str(question_topic["topic"]),
                question_level_subtopic=str(question_topic["subtopic"]),
                part_level_topics=part_level_topics,
                topic=str(question_topic["topic"]),
                subtopic=str(question_topic["subtopic"]),
                topic_confidence=str(question_topic["topic_confidence"]),
                topic_evidence=classification.topic_evidence,
                topic_evidence_details={
                    **classification.topic_evidence_details,
                    **({"examiner_report_structured": examiner_evidence.to_dict()} if examiner_evidence else {}),
                },
                examiner_report_evidence=examiner_evidence.to_dict() if examiner_evidence else {},
                secondary_topics=list(question_topic["secondary_topics"]),
                topic_uncertain=bool(question_topic["topic_uncertain"]),
                difficulty=classification.difficulty,
                difficulty_confidence=classification.difficulty_confidence,
                difficulty_evidence=classification.difficulty_evidence,
                difficulty_uncertain=classification.difficulty_uncertain,
                marks=marks,
                marks_if_available=marks,
                page_numbers=span.page_numbers,
                review_flags=sorted(set(flags)),
                confidence=confidence,
                crop_uncertain=render_result.crop_uncertain,
                question_crop_confidence="low" if render_result.crop_uncertain else "high",
                crop_debug_paths=render_result.debug_paths,
                question_crop_diagnostics=render_result.crop_diagnostics,
                topic_alternatives=classification.alternative_topics,
                markscheme_image=_display_path(mark_scheme_image.image_path) if mark_scheme_image and mark_scheme_image.image_path else "",
                markscheme_pages=mark_scheme_image.page_numbers if mark_scheme_image else [],
                markscheme_question_number=mark_scheme_image.markscheme_question_number if mark_scheme_image else "",
                markscheme_crop_confidence=mark_scheme_image.crop_confidence if mark_scheme_image else "",
                markscheme_mapping_method=mark_scheme_image.mapping_method if mark_scheme_image else "",
                markscheme_table_detected=mark_scheme_image.table_detected if mark_scheme_image else False,
                markscheme_table_header_detected=mark_scheme_image.table_header_detected if mark_scheme_image else [],
                markscheme_nearby_anchors=mark_scheme_image.nearby_anchors if mark_scheme_image else [],
                markscheme_debug_paths=mark_scheme_image.debug_paths if mark_scheme_image else [],
                markscheme_table_header_ok=mark_scheme_image.table_header_ok if mark_scheme_image else False,
                markscheme_continuation_rows_included=mark_scheme_image.continuation_rows_included if mark_scheme_image else False,
                question_subparts=mark_scheme_image.question_subparts if mark_scheme_image else [],
                markscheme_subparts=mark_scheme_image.markscheme_subparts if mark_scheme_image else [],
                question_marks_total=mark_scheme_image.question_marks_total if mark_scheme_image else marks,
                markscheme_marks_total=mark_scheme_image.markscheme_marks_total if mark_scheme_image else None,
                markscheme_mapping_status=mark_scheme_image.mapping_status if mark_scheme_image else "fail",
                markscheme_failure_reason=mark_scheme_image.failure_reason if mark_scheme_image else "partial_question_block",
                qa_status="fail" if any(flag.startswith("qa_fail_") for flag in qa_flags) else ("warning" if qa_flags else "pass"),
                qa_flags=qa_flags,
            )


def _record_qa_flags(
    paper_family: str,
    topic: str,
    config: AppConfig,
    mark_scheme_image: MarkSchemeImageResult | None,
) -> list[str]:
    flags: list[str] = []
    allowed_topics = set(config.paper_family_taxonomy.get(paper_family, {}))
    if paper_family in config.paper_family_taxonomy and topic not in allowed_topics:
        flags.append("qa_fail_invalid_topic_for_paper")
    if mark_scheme_image:
        if any(page < 6 for page in mark_scheme_image.page_numbers):
            flags.append("qa_fail_markscheme_page_before_6")
        if mark_scheme_image.image_path and not mark_scheme_image.table_header_ok:
            flags.append("qa_fail_markscheme_header_not_ok")
        if mark_scheme_image.image_path and not mark_scheme_image.markscheme_question_number:
            flags.append("qa_fail_markscheme_label_missing")
        if "markscheme_continuation_maybe_truncated" in mark_scheme_image.review_flags:
            flags.append("qa_warn_markscheme_continuation_maybe_truncated")
        if "markscheme_parent_label_match" in mark_scheme_image.review_flags:
            flags.append("qa_warn_markscheme_parent_label_match")
        if mark_scheme_image.mapping_status == "fail":
            flags.append(f"qa_fail_markscheme_{mark_scheme_image.failure_reason or 'mapping_failed'}")
    return sorted(set(flags))


_QUESTION_SUBPART_LABEL_RE = re.compile(
    r"(?<![A-Za-z0-9])\((?P<label>a|b|c|d|e|f|g|h|viii|vii|vi|iv|ix|iii|ii|i|v|x)\)",
    re.IGNORECASE,
)


def _question_subparts_from_text(text: str) -> list[str]:
    subparts: list[str] = []
    for match in _QUESTION_SUBPART_LABEL_RE.finditer(text):
        label = match.group("label").lower()
        if label not in subparts:
            subparts.append(label)
    return subparts


def _record_confidence(classification_confidence: float, flags: list[str]) -> float:
    penalty = min(0.45, len(set(flags)) * 0.04)
    return max(0.05, min(0.98, classification_confidence - penalty))


def _question_topic_from_parts(
    classification: ClassificationResult,
    part_level_topics: list[dict[str, object]],
) -> dict[str, object]:
    review_flags = list(classification.review_flags)
    secondary_topics: list[str] = []
    topic_confidence = classification.topic_confidence
    topic_uncertain = classification.topic_uncertain
    confidence = classification.confidence
    paper_family = classification.paper_family

    part_families = sorted(
        {
            str(part.get("paper_family", ""))
            for part in part_level_topics
            if part.get("paper_family") and part.get("paper_family") != "unknown"
        }
    )

    if len(part_families) == 1 and paper_family == "unknown":
        paper_family = part_families[0]
    elif len(part_families) > 1:
        paper_family = "unknown"
        review_flags.append("paper_family_uncertain")
    elif paper_family == "unknown":
        review_flags.append("paper_family_uncertain")

    if any(part.get("topic_uncertain") or part.get("topic_confidence") == "low" for part in part_level_topics):
        review_flags.append("part_topic_uncertain")

    return {
        "paper_family": paper_family,
        "topic": classification.topic,
        "subtopic": classification.subtopic,
        "topic_confidence": topic_confidence,
        "topic_uncertain": topic_uncertain,
        "secondary_topics": secondary_topics,
        "review_flags": sorted(set(review_flags)),
        "confidence": confidence,
    }


def _secondary_main_topics(labels: list[str], primary_topic: str) -> list[str]:
    topics: list[str] = []
    for label in labels:
        topic = str(label).split(":", 1)[0]
        if topic and topic != primary_topic and topic not in topics:
            topics.append(topic)
    return topics


def _clear_resolved_mixed_topic_flags(flags: list[str]) -> list[str]:
    cleaned = [flag for flag in flags if flag != "topic_uncertain_mixed_major_topics"]
    remaining_topic_uncertainty = any(flag.startswith("topic_uncertain_") for flag in cleaned)
    if not remaining_topic_uncertainty:
        cleaned = [flag for flag in cleaned if flag != "topic_uncertain"]
    return cleaned


def _topic_uncertain_from_flags(flags: list[str]) -> bool:
    return "topic_uncertain" in flags or any(flag.startswith("topic_uncertain_") for flag in flags)


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def _safe_basename(stem: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in stem).strip("_") or "paper"


def _write_pdf_diagnostic(
    question_pdf: Path,
    layouts: list[PageLayout],
    spans: list[QuestionSpan],
    records: list[QuestionRecord],
    config: AppConfig,
) -> Path:
    config.ensure_output_dirs()
    paper_name = _safe_basename(question_pdf.stem)
    anchors = detect_question_anchor_candidates(layouts, config)
    uncertain_records = [
        record
        for record in records
        if record.crop_uncertain
        or any("uncertain" in flag or "contamination" in flag or "sequence_gap" in flag for flag in record.review_flags)
    ]
    ocr_pages = [
        layout.page_number
        for layout in layouts
        if layout.text_source == "ocr" or str(layout.extraction_warning or "").startswith("ocr")
    ]
    footer_contamination = [
        record.question_number
        for record in records
        if any("header_footer_contamination" in flag or "crop_reaches_page_margin" in flag for flag in record.review_flags)
    ]
    payload = {
        "source_pdf": _display_path(question_pdf),
        "paper_name": paper_name,
        "detected_top_level_questions": len(records),
        "detected_question_numbers": [record.question_number for record in records],
        "candidate_question_anchors": len(anchors),
        "accepted_question_anchors": len(spans),
        "uncertain_splits": len(uncertain_records),
        "ocr_fallback_pages": len(ocr_pages),
        "ocr_page_numbers": ocr_pages,
        "footer_header_contamination_count": len(footer_contamination),
        "footer_header_contamination_questions": footer_contamination,
        "crop_uncertain_count": sum(1 for record in records if record.crop_uncertain),
        "topic_counts_by_paper_family": _topic_counts_by_paper_family(records),
        "difficulty_counts_by_paper_family": _difficulty_counts_by_paper_family(records),
        "markscheme_image_count": sum(1 for record in records if record.markscheme_image),
        "markscheme_image_missing_count": sum(1 for record in records if "markscheme_image_missing" in record.review_flags),
        "review_flag_counts": _flag_counts(records),
    }
    path = config.output.review_dir / f"{paper_name}_diagnostics.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _write_batch_diagnostic(records: list[QuestionRecord], config: AppConfig, basename: str | None = None) -> Path:
    config.ensure_output_dirs()
    name = f"{basename}_diagnostics.json" if basename else "batch_diagnostics.json"
    payload = {
        "record_count": len(records),
        "paper_family_counts": _paper_family_counts(records),
        "topic_counts_by_paper_family": _topic_counts_by_paper_family(records),
        "difficulty_counts_by_paper_family": _difficulty_counts_by_paper_family(records),
        "markscheme_image_count": sum(1 for record in records if record.markscheme_image),
        "markscheme_image_missing_count": sum(1 for record in records if "markscheme_image_missing" in record.review_flags),
        "review_flag_counts": _flag_counts(records),
    }
    path = config.output.review_dir / name
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _paper_family_counts(records: list[QuestionRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        family = record.paper_family or "unknown"
        counts[family] = counts.get(family, 0) + 1
    return dict(sorted(counts.items()))


def _topic_counts_by_paper_family(records: list[QuestionRecord]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for record in records:
        family = record.paper_family or "unknown"
        topic = record.question_level_topic or record.topic or "unknown"
        family_counts = counts.setdefault(family, {})
        family_counts[topic] = family_counts.get(topic, 0) + 1
    return {family: dict(sorted(topic_counts.items())) for family, topic_counts in sorted(counts.items())}


def _difficulty_counts_by_paper_family(records: list[QuestionRecord]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for record in records:
        family = record.paper_family or "unknown"
        difficulty = record.difficulty or "unknown"
        family_counts = counts.setdefault(family, {})
        family_counts[difficulty] = family_counts.get(difficulty, 0) + 1
    return {family: dict(sorted(difficulty_counts.items())) for family, difficulty_counts in sorted(counts.items())}


def _flag_counts(records: list[QuestionRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        for flag in record.review_flags:
            counts[flag] = counts.get(flag, 0) + 1
    return dict(sorted(counts.items()))


def _write_topic_debug_report(question_pdf: Path, records: list[QuestionRecord], config: AppConfig) -> Path:
    config.ensure_output_dirs()
    paper_name = _safe_basename(question_pdf.stem)
    payload = {
        "source_pdf": _display_path(question_pdf),
        "paper_name": paper_name,
        "questions": [
            {
                "question_number": record.question_number,
                "text_snippet": record.combined_question_text[:500],
                "paper_family": record.paper_family,
                "source_paper_family": record.source_paper_family,
                "inferred_paper_family": record.inferred_paper_family,
                "paper_family_confidence": record.paper_family_confidence,
                "question_level_paper_family": record.question_level_paper_family or record.paper_family,
                "question_level_topic": record.question_level_topic or record.topic,
                "question_level_subtopic": record.question_level_subtopic or record.subtopic,
                "topic": record.topic,
                "subtopic": record.subtopic,
                "topic_confidence": record.topic_confidence,
                "record_confidence": record.confidence,
                "topic_uncertain": record.topic_uncertain,
                "topic_evidence": record.topic_evidence,
                "secondary_topics": record.secondary_topics,
                "part_level_topics": record.part_level_topics,
                "alternative_candidate_topics": record.topic_alternatives if record.topic_confidence != "high" else [],
                "difficulty": record.difficulty,
                "difficulty_confidence": record.difficulty_confidence,
                "difficulty_evidence": record.difficulty_evidence,
                "difficulty_uncertain": record.difficulty_uncertain,
                "markscheme_image_found": bool(record.markscheme_image),
                "markscheme_question_number": record.markscheme_question_number,
                "markscheme_crop_confidence": record.markscheme_crop_confidence,
                "markscheme_mapping_method": record.markscheme_mapping_method,
                "markscheme_table_detected": record.markscheme_table_detected,
                "classification_restricted_by_paper_family": record.paper_family not in {"", "unknown"},
            }
            for record in records
        ],
    }
    path = config.output.review_dir / f"{paper_name}_topic_debug.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
