from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from .classification import classify_question, classify_question_parts, infer_source_paper_code, _explicit_primary_topic_from_text
from .config import AppConfig
from .document_metadata import DocumentMetadata, parse_filename_metadata, parse_internal_document_metadata, reconcile_document_metadata
from .document_registry import DocumentRegistry, build_document_registry, build_document_registry_from_paths
from .examiner_reports import examiner_report_topic_evidence
from .exporters import export_records
from .extraction_structure import build_structured_question_text
from .image_rendering import render_question_image
from .mark_schemes import MarkSchemeImageResult, extract_mark_scheme_answers, find_mark_scheme, render_mark_scheme_images
from .models import ClassificationResult, PageLayout, QuestionRecord, QuestionSpan
from .pdf_extract import extract_pdf_layout
from .question_detection import detect_question_anchor_candidates, detect_question_spans, extract_marks_from_text, extract_question_total_from_text


@dataclass(frozen=True)
class PipelineResult:
    records: list[QuestionRecord]
    json_path: Path
    output_root: Path


def process_inputs(input_path: str | Path, config: AppConfig) -> PipelineResult:
    config.ensure_output_dirs()
    registry = build_document_registry(input_path, allowed_document_types=set(config.runtime.input_document_types))
    return _process_registry_entries(registry, config)


def process_batch(config: AppConfig) -> PipelineResult:
    config.ensure_output_dirs()
    active_document_types = set(config.runtime.input_document_types)
    source_paths: list[Path] = []
    if config.runtime.supports_input_document_type("question_paper"):
        source_paths.append(config.input.question_papers_dir)
    if config.runtime.supports_input_document_type("mark_scheme"):
        source_paths.append(config.input.mark_schemes_dir)
    registry = build_document_registry_from_paths(
        source_paths,
        allowed_document_types=active_document_types,
    )
    return _process_registry_entries(registry, config)


def process_folder(folder: str | Path, config: AppConfig) -> PipelineResult:
    config.ensure_output_dirs()
    registry = build_document_registry(folder, allowed_document_types=set(config.runtime.input_document_types))
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
    json_path = export_records(records, config)
    if config.debug.enabled:
        _write_batch_diagnostic(records, config)
    return PipelineResult(records, json_path, config.output.root_dir())


def process_sample(question_pdf: str | Path, config: AppConfig, mark_scheme_pdf: str | Path | None = None) -> PipelineResult:
    config.ensure_output_dirs()
    records = build_records_for_pdf(question_pdf, config, mark_scheme_pdf=mark_scheme_pdf)
    basename = _safe_basename(Path(question_pdf).stem)
    json_path = export_records(records, config, basename=f"{basename}_sample")
    if config.debug.enabled:
        _write_batch_diagnostic(records, config, basename=f"{basename}_sample")
    return PipelineResult(records, json_path, config.output.root_dir())


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
    initial_spans = detect_question_spans(layouts, question_pdf, config)
    source_paper_code, _source_paper_code_confidence = infer_source_paper_code(question_pdf.name)
    source_paper_code = document_metadata.component or source_paper_code

    initial_records = _build_records_from_spans(
        question_pdf=question_pdf,
        layouts=layouts,
        spans=initial_spans,
        config=config,
        mark_scheme_pdf=mark_scheme_pdf,
        examiner_report_paths=examiner_report_paths,
        document_metadata=document_metadata,
        registry_warnings=registry_warnings or [],
        source_paper_code=source_paper_code,
    )
    initial_total_check = _paper_total_check(
        initial_records,
        component=document_metadata.component or source_paper_code,
        paper_family=initial_records[0].paper_family if initial_records else "",
    )

    final_spans = initial_spans
    final_records = initial_records
    final_total_check = initial_total_check
    final_layouts = layouts
    rescan_triggered = False
    rescan_result = "not_triggered"

    if _should_trigger_paper_total_rescan(initial_total_check):
        rescan_triggered = True
        broader_config = _broadened_detection_config(config)
        rescanned_layouts = extract_pdf_layout(question_pdf, broader_config)
        rescanned_spans = detect_question_spans(rescanned_layouts, question_pdf, broader_config)
        rescanned_records = _build_records_from_spans(
            question_pdf=question_pdf,
            layouts=rescanned_layouts,
            spans=rescanned_spans,
            config=config,
            mark_scheme_pdf=mark_scheme_pdf,
            examiner_report_paths=examiner_report_paths,
            document_metadata=document_metadata,
            registry_warnings=registry_warnings or [],
            source_paper_code=source_paper_code,
        )
        rescanned_total_check = _paper_total_check(
            rescanned_records,
            component=document_metadata.component or source_paper_code,
            paper_family=rescanned_records[0].paper_family if rescanned_records else "",
        )
        (
            final_spans,
            final_records,
            final_total_check,
            rescan_result,
        ) = _select_preferred_detection_pass(
            initial_spans=initial_spans,
            initial_records=initial_records,
            initial_total_check=initial_total_check,
            rescanned_spans=rescanned_spans,
            rescanned_records=rescanned_records,
            rescanned_total_check=rescanned_total_check,
        )
        if final_spans is rescanned_spans:
            final_layouts = rescanned_layouts

    _reconcile_paper_topics(final_records, config)
    _apply_paper_total_metadata(
        final_records,
        initial_total_check=initial_total_check,
        total_check=final_total_check,
        rescan_triggered=rescan_triggered,
        rescan_result=rescan_result,
        focus=_paper_total_focus(final_records),
    )
    if config.debug.enabled:
        _write_pdf_diagnostic(question_pdf, final_layouts, final_spans, final_records, config)
    return final_records


def _build_records_from_spans(
    *,
    question_pdf: Path,
    layouts: list[PageLayout],
    spans: list[QuestionSpan],
    config: AppConfig,
    mark_scheme_pdf: str | Path | None,
    examiner_report_paths: list[Path] | None,
    document_metadata: DocumentMetadata,
    registry_warnings: list[str],
    source_paper_code: str,
) -> list[QuestionRecord]:
    expected_numbers = [span.question_number for span in spans if span.question_number.isdigit()]
    expected_marks = {
        span.question_number: span.question_total_detected if span.question_total_detected is not None else extract_question_total_from_text(span.combined_text)
        for span in spans
        if span.question_number.isdigit()
    }
    expected_subparts = {span.question_number: _question_subparts_from_span(span) for span in spans if span.question_number.isdigit()}
    expected_validation_flags = {span.question_number: list(span.validation_flags) for span in spans if span.question_number.isdigit()}

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
                question_validation_flags=expected_validation_flags,
            )
        except Exception as exc:
            mark_scheme_flags.append(f"markscheme_image_export_failed:{exc.__class__.__name__}")
    else:
        mark_scheme_flags.append("unmatched_mark_scheme")

    records: list[QuestionRecord] = []
    for span in spans:
        question_subparts = _question_subparts_from_span(span)
        render_result = render_question_image(question_pdf, span, layouts, config)
        structured_text = build_structured_question_text(span, layouts, config)
        question_text = structured_text.combined_question_text or render_result.extracted_text or span.combined_text
        marks = span.question_total_detected if span.question_total_detected is not None else extract_question_total_from_text(question_text)
        answer_text = answers.get(span.question_number, "")
        mark_scheme_image = mark_scheme_images.get(span.question_number)
        examiner_evidence = None
        if config.runtime.supports_input_document_type("examiner_report"):
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
                structured_text=structured_text,
                question_subparts=question_subparts,
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
    return records


def _build_question_record(
    *,
    question_pdf: Path,
    span: QuestionSpan,
    question_text: str,
    marks: int | None,
    answer_text: str,
    render_result,
    structured_text,
    question_subparts: list[str],
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
            context_flags=flags + list(structured_text.extraction_quality_flags),
            source_name=question_pdf.name,
            examiner_report_text=examiner_text,
            mark_scheme_text=answer_text,
            question_ocr_text=question_text if "ocr_question_text" in flags else "",
            body_text_normalized=structured_text.body_text_normalized,
            part_texts=structured_text.part_texts,
            body_text_raw=structured_text.body_text_raw,
            math_lines=structured_text.math_lines,
        )
        part_level_topics = classify_question_parts(
            question_text,
            span.question_number,
            config,
            context_flags=flags + list(structured_text.extraction_quality_flags),
            source_name=question_pdf.name,
            examiner_report_text=examiner_text,
            mark_scheme_text=answer_text,
            question_ocr_text=question_text if "ocr_question_text" in flags else "",
            structured_part_texts=structured_text.part_texts,
        )
        question_topic = _question_topic_from_parts(classification, part_level_topics)
        flags.extend(question_topic["review_flags"])
        flags.extend(render_result.review_flags)
        confidence = _record_confidence(float(question_topic["confidence"]), flags)
        validation_status, validation_flags = _refine_validation_status(
            base_status=span.validation_status,
            base_validation_flags=span.validation_flags,
            mapping_status=mark_scheme_image.mapping_status if mark_scheme_image else "fail",
            mapping_failure_reason=mark_scheme_image.failure_reason if mark_scheme_image else "",
            crop_uncertain=render_result.crop_uncertain,
            extraction_quality_flags=structured_text.extraction_quality_flags,
            review_flags=flags,
            question_structure_detected=span.structure_detected,
        )
        scope_quality_status = _derive_scope_quality_status(
            validation_flags=validation_flags,
            review_flags=flags,
            question_structure_detected=span.structure_detected,
        )
        text_source_profile = _text_source_profile(flags)
        text_fidelity_status, text_fidelity_flags = _assess_text_fidelity(
            question_text=question_text,
            extraction_quality_flags=structured_text.extraction_quality_flags,
            review_flags=flags,
            validation_flags=validation_flags,
            question_structure_detected=span.structure_detected,
            mapping_failure_reason=mark_scheme_image.failure_reason if mark_scheme_image else "",
            text_source_profile=text_source_profile,
        )
        topic_trust_status = _derive_topic_trust_status(
            topic_confidence=str(question_topic["topic_confidence"]),
            topic_uncertain=bool(question_topic["topic_uncertain"]),
            text_fidelity_status=text_fidelity_status,
            validation_status=validation_status,
            scope_quality_status=scope_quality_status,
        )

        return QuestionRecord(
                source_pdf=_display_path(question_pdf),
                paper_name=span.paper_name,
                question_number=span.question_number,
                full_question_label=span.full_question_label,
                screenshot_path=_display_path(render_result.screenshot_path),
                combined_question_text=question_text,
                body_text_raw=structured_text.body_text_raw,
                body_text_normalized=structured_text.body_text_normalized,
                math_lines=structured_text.math_lines,
                diagram_text=structured_text.diagram_text,
                extraction_quality_score=structured_text.extraction_quality_score,
                extraction_quality_flags=structured_text.extraction_quality_flags,
                part_texts=structured_text.part_texts,
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
                mark_scheme_source_pdf=_display_path(matched_mark_scheme) if matched_mark_scheme else "",
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
                question_subparts=question_subparts,
                markscheme_subparts=mark_scheme_image.markscheme_subparts if mark_scheme_image else [],
                question_marks_total=mark_scheme_image.question_marks_total if mark_scheme_image else marks,
                markscheme_marks_total=mark_scheme_image.markscheme_marks_total if mark_scheme_image else None,
                markscheme_mapping_status=mark_scheme_image.mapping_status if mark_scheme_image else "fail",
                markscheme_failure_reason=mark_scheme_image.failure_reason if mark_scheme_image else "partial_question_block",
                validation_status=validation_status,
                validation_flags=validation_flags,
                scope_quality_status=scope_quality_status,
                text_source_profile=text_source_profile,
                text_fidelity_status=text_fidelity_status,
                text_fidelity_flags=text_fidelity_flags,
                topic_trust_status=topic_trust_status,
                recovery_attempted=span.recovery_attempted,
                recovery_result=span.recovery_result,
                question_structure_detected=span.structure_detected,
                mark_scheme_structure_detected={
                    "subparts": mark_scheme_image.markscheme_subparts if mark_scheme_image else [],
                    "question_subparts": mark_scheme_image.question_subparts if mark_scheme_image else [],
                    "question_total_detected": mark_scheme_image.question_marks_total if mark_scheme_image else None,
                    "mark_scheme_total_detected": mark_scheme_image.markscheme_marks_total if mark_scheme_image else None,
                },
                question_total_detected=span.question_total_detected,
                mark_scheme_total_detected=mark_scheme_image.markscheme_marks_total if mark_scheme_image else None,
                question_format_profile=span.format_profile,
            )


_QUESTION_SUBPART_LABEL_RE = re.compile(
    r"^\s*(?:\d+\s*)?(?P<labels>(?:\((?:a|b|c|d|e|f|g|h|viii|vii|vi|iv|ix|iii|ii|i|v|x)\))+)",
    re.IGNORECASE,
)


def _question_subparts_from_text(text: str) -> list[str]:
    subparts: list[str] = []
    for line in text.splitlines():
        match = _QUESTION_SUBPART_LABEL_RE.match(line.strip())
        if not match:
            continue
        for label in re.findall(r"\((a|b|c|d|e|f|g|h|viii|vii|vi|iv|ix|iii|ii|i|v|x)\)", match.group("labels"), re.IGNORECASE):
            normalized = label.lower()
            if normalized not in subparts:
                subparts.append(normalized)
    alpha_labels = ["a", "b", "c", "d", "e", "f", "g", "h"]
    roman_labels = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"]
    if any(label in alpha_labels for label in subparts):
        return sorted({label for label in subparts if label in alpha_labels}, key=alpha_labels.index)
    if any(label in roman_labels for label in subparts):
        return sorted({label for label in subparts if label in roman_labels}, key=roman_labels.index)
    return subparts


def _question_subparts_from_span(span: QuestionSpan) -> list[str]:
    lines: list[str] = []
    for block in span.blocks:
        control_stripped = "".join(char if ord(char) >= 32 or char in "\n\t\r" else " " for char in block.text)
        for raw_line in control_stripped.replace("\u00a0", " ").splitlines():
            normalized_line = " ".join(raw_line.split())
            if normalized_line:
                lines.append(normalized_line)
    return _question_subparts_from_text("\n".join(lines))


def _broadened_detection_config(config: AppConfig) -> AppConfig:
    broader = deepcopy(config)
    broader.detection.anchor_min_confidence = max(0.45, config.detection.anchor_min_confidence - 0.08)
    broader.detection.anchor_y_tolerance = config.detection.anchor_y_tolerance + 8
    broader.detection.prompt_region_max_gap = config.detection.prompt_region_max_gap + 30
    broader.detection.crop_padding = config.detection.crop_padding + 8
    broader.detection.crop_bottom_margin = max(18, config.detection.crop_bottom_margin - 12)
    return broader


def _record_solution_marks(record: QuestionRecord) -> int | None:
    for value in [record.markscheme_marks_total, record.question_marks_total, record.marks_if_available, record.marks]:
        if value is not None:
            return int(value)
    return None


def _derive_scope_quality_status(
    *,
    validation_flags: list[str],
    review_flags: list[str],
    question_structure_detected: dict[str, Any],
) -> str:
    if (
        question_structure_detected.get("contamination_detected")
        or any(
            flag in validation_flags or flag in review_flags
            for flag in {
                "question_scope_contaminated",
                "question_start_mismatch",
                "possible_next_question_contamination",
                "likely_truncated_question_crop",
            }
        )
    ):
        return "fail"
    if any(
        flag in validation_flags or flag in review_flags
        for flag in {
            "weak_question_anchor",
            "question_start_uncertain",
            "question_sequence_gap",
            "paper_total_focus_candidate",
        }
    ):
        return "review"
    return "clean"


def _text_source_profile(review_flags: list[str]) -> str:
    if any(flag.startswith("ocr_merged") for flag in review_flags):
        return "hybrid"
    if "ocr_question_text" in review_flags:
        return "ocr"
    return "native_pdf"


def _assess_text_fidelity(
    *,
    question_text: str,
    extraction_quality_flags: list[str],
    review_flags: list[str],
    validation_flags: list[str],
    question_structure_detected: dict[str, Any],
    mapping_failure_reason: str,
    text_source_profile: str,
) -> tuple[str, list[str]]:
    flags: set[str] = set()
    strong_corruption_flags = {
        "likely_needs_visual_review",
        "math_corruption_suspected",
        "broken_fraction_structure",
        "broken_superscript_or_power",
        "suspicious_symbol_run",
        "flattened_display_math",
        "diagram_text_mixed_with_body",
    }
    if any(flag in extraction_quality_flags for flag in strong_corruption_flags):
        flags.add("math_text_corruption_detected")
    if _text_has_suspicious_ocr_noise(question_text):
        flags.add("ocr_noise_fragment_present")
    if _text_has_corrupted_math_notation(question_text):
        flags.add("ocr_math_notation_degraded")
    if (
        mapping_failure_reason == "question_subparts_incomplete"
        or "question_subparts_incomplete" in validation_flags
        or bool(question_structure_detected.get("missing_internal_subparts"))
        or bool(question_structure_detected.get("impossible_subpart_sequence_detected"))
    ):
        flags.add("missing_visible_structure_in_text")
    if (
        text_source_profile != "native_pdf"
        and "heavy_math_density" in extraction_quality_flags
        and ("ocr_noise_fragment_present" in flags or "ocr_math_notation_degraded" in flags)
    ):
        flags.add("hybrid_math_text_requires_review")
    if "weak_question_text" in review_flags and flags:
        flags.add("weak_extracted_text")

    status = "clean"
    if "missing_visible_structure_in_text" in flags:
        status = "unusable"
    elif flags:
        status = "degraded"
    return status, sorted(flags)


def _text_has_suspicious_ocr_noise(text: str) -> bool:
    normalized_lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    for line in normalized_lines:
        lowered = line.lower()
        if lowered in {"anne", "fy"} or any(token in lowered for token in {"| anne", "| fy", "¢"}):
            return True
        if re.fullmatch(r"[|¦Il1]\s*[A-Za-z]{2,6}", line):
            return True
        if re.fullmatch(r"[A-Za-z]{2,6}[!?]", line):
            return True
        if re.search(r"\b[A-Za-z]{3,}[!?]\b", line):
            return True
    return False


def _text_has_corrupted_math_notation(text: str) -> bool:
    normalized = str(text)
    patterns = [
        r"(?:sin|cos|tan|sec|cot){2,}",
        r"\b[a-z]*(?:sin|cos|tan|sec|cot){2,}[a-z]*\b",
        r"\^\{[^}]{1,4}\}_\{[^}]{1,4}\}r",
        r"[A-Za-z]{1,3},,",
    ]
    return any(re.search(pattern, normalized, re.IGNORECASE) for pattern in patterns)


def _derive_topic_trust_status(
    *,
    topic_confidence: str,
    topic_uncertain: bool,
    text_fidelity_status: str,
    validation_status: str,
    scope_quality_status: str,
) -> str:
    if validation_status == "fail" or scope_quality_status == "fail":
        return "review_required"
    if text_fidelity_status != "clean":
        return "degraded_text"
    if topic_uncertain or topic_confidence == "low":
        return "review_required"
    return "normal"


def _expected_paper_total(component: str, paper_family: str = "") -> int | None:
    family = (paper_family or "").strip().upper()
    if family in {"P1", "P3", "P4", "P5"}:
        return {"P1": 75, "P3": 75, "P4": 50, "P5": 50}[family]

    digits = "".join(char for char in str(component) if char.isdigit())
    if digits:
        return {"1": 75, "3": 75, "4": 50, "5": 50}.get(digits[0])
    return None


def _paper_total_check(
    records: list[QuestionRecord],
    *,
    component: str,
    paper_family: str,
) -> dict[str, int | str | bool | None]:
    expected_total = _expected_paper_total(component, paper_family)
    detected_total = sum(mark for record in records if (mark := _record_solution_marks(record)) is not None)
    status = "unknown_expected_total"
    if expected_total is not None:
        status = "matched" if detected_total == expected_total else "mismatch"
    return {
        "expected_total": expected_total,
        "detected_total": detected_total,
        "status": status,
        "difference": None if expected_total is None else detected_total - expected_total,
    }


def _should_trigger_paper_total_rescan(total_check: dict[str, int | str | bool | None]) -> bool:
    return total_check.get("expected_total") is not None and total_check.get("status") == "mismatch"


def _structural_failure_count(records: list[QuestionRecord]) -> int:
    structural_flags = {
        "question_subparts_incomplete",
        "question_scope_contaminated",
        "missing_terminal_mark_total",
        "question_mark_total_mismatch",
        "question_mark_total_missing",
        "likely_truncated_question_crop",
    }
    count = 0
    for record in records:
        if any(flag in structural_flags for flag in record.validation_flags):
            count += 1
            continue
        if record.markscheme_failure_reason in structural_flags:
            count += 1
    return count


def _paper_total_preference_key(
    total_check: dict[str, int | str | bool | None],
    records: list[QuestionRecord],
) -> tuple[int, int, int]:
    expected_total = total_check.get("expected_total")
    detected_total = int(total_check.get("detected_total") or 0)
    if expected_total is None:
        distance = 10**6
    else:
        distance = abs(detected_total - int(expected_total))
    return (-distance, -_structural_failure_count(records), len(records))


def _select_preferred_detection_pass(
    *,
    initial_spans: list[QuestionSpan],
    initial_records: list[QuestionRecord],
    initial_total_check: dict[str, int | str | bool | None],
    rescanned_spans: list[QuestionSpan],
    rescanned_records: list[QuestionRecord],
    rescanned_total_check: dict[str, int | str | bool | None],
) -> tuple[
    list[QuestionSpan],
    list[QuestionRecord],
    dict[str, int | str | bool | None],
    str,
]:
    if rescanned_total_check.get("status") == "matched" and initial_total_check.get("status") != "matched":
        return rescanned_spans, rescanned_records, rescanned_total_check, "recovered_exact_total"

    if _paper_total_preference_key(rescanned_total_check, rescanned_records) > _paper_total_preference_key(initial_total_check, initial_records):
        result = "improved_but_still_mismatch"
        if rescanned_total_check.get("status") == "matched":
            result = "recovered_exact_total"
        return rescanned_spans, rescanned_records, rescanned_total_check, result

    return initial_spans, initial_records, initial_total_check, "no_improvement"


def _apply_paper_total_metadata(
    records: list[QuestionRecord],
    *,
    initial_total_check: dict[str, int | str | bool | None],
    total_check: dict[str, int | str | bool | None],
    rescan_triggered: bool,
    rescan_result: str,
    focus: dict[str, object],
) -> None:
    before_total = initial_total_check.get("detected_total")
    expected_total = total_check.get("expected_total")
    detected_total = total_check.get("detected_total")
    status = str(total_check.get("status") or "")
    focus_questions = [str(question) for question in focus.get("question_numbers", [])]
    focus_pages = [int(page) for page in focus.get("pages", [])]
    reasons_by_question = dict(focus.get("reasons_by_question", {}))
    if status == "matched" and rescan_triggered:
        status = "recovered_after_rescan" if rescan_result == "recovered_exact_total" else "matched"
    elif status == "mismatch" and rescan_triggered:
        status = "mismatch_after_rescan"

    for record in records:
        record.paper_total_expected = int(expected_total) if expected_total is not None else None
        record.paper_total_detected = int(detected_total) if detected_total is not None else None
        record.paper_total_status = status
        record.rescan_triggered = rescan_triggered
        record.rescan_result = rescan_result
        record.paper_total_before_rescan = int(before_total) if before_total is not None else None
        record.paper_total_after_rescan = int(detected_total) if detected_total is not None else None
        record.paper_total_focus_questions = list(focus_questions)
        record.paper_total_focus_pages = list(focus_pages)
        record.paper_total_focus_reason = str(reasons_by_question.get(record.question_number, ""))

        review_flags = set(record.review_flags)
        if rescan_triggered:
            review_flags.add("paper_total_rescan_triggered")
        if rescan_result == "recovered_exact_total":
            review_flags.add("paper_total_rescan_recovered")
        if record.question_number in focus_questions:
            review_flags.add("paper_total_focus_candidate")
        if status == "mismatch_after_rescan":
            review_flags.add("paper_total_mismatch")
        record.review_flags = sorted(review_flags)

        validation_flags = set(record.validation_flags)
        if status == "mismatch_after_rescan":
            validation_flags.add("paper_total_mismatch")
            record.validation_status = "fail"
        record.validation_flags = sorted(validation_flags)


def _paper_total_focus(records: list[QuestionRecord]) -> dict[str, object]:
    scored: list[tuple[int, str, list[int], list[str]]] = []
    for record in records:
        reasons: list[str] = []
        structural_reason = record.markscheme_failure_reason
        if structural_reason in {
            "question_scope_contaminated",
            "question_subparts_incomplete",
            "question_mark_total_mismatch",
            "question_mark_total_missing",
        }:
            reasons.append(structural_reason)
        if "weak_question_anchor" in record.validation_flags or "question_start_uncertain" in record.review_flags:
            reasons.append("anchor_or_boundary")
        if "possible_next_question_contamination" in record.review_flags:
            reasons.append("adjacent_boundary_contamination")
        if record.recovery_attempted and record.recovery_result == "no_change":
            reasons.append("recovery_stalled")
        if len(record.page_numbers) > 1:
            reasons.append("cross_page_scope")
        if not reasons:
            continue
        score = 0
        priority = {
            "question_scope_contaminated": 5,
            "question_subparts_incomplete": 5,
            "question_mark_total_mismatch": 4,
            "question_mark_total_missing": 4,
            "anchor_or_boundary": 3,
            "adjacent_boundary_contamination": 3,
            "recovery_stalled": 2,
            "cross_page_scope": 1,
        }
        for reason in reasons:
            score += priority.get(reason, 1)
        scored.append((score, record.question_number, list(record.page_numbers), reasons))

    scored.sort(key=lambda item: (-item[0], int(item[1]) if item[1].isdigit() else 999, item[1]))
    top = scored[:3]
    pages: list[int] = []
    question_numbers: list[str] = []
    reasons_by_question: dict[str, str] = {}
    for _score, question_number, record_pages, reasons in top:
        question_numbers.append(question_number)
        for page in record_pages:
            if page not in pages:
                pages.append(page)
        reasons_by_question[question_number] = ", ".join(reasons)
    return {
        "question_numbers": question_numbers,
        "pages": pages,
        "reasons_by_question": reasons_by_question,
    }


def _record_confidence(classification_confidence: float, flags: list[str]) -> float:
    penalty = min(0.45, len(set(flags)) * 0.04)
    return max(0.05, min(0.98, classification_confidence - penalty))


def _refine_validation_status(
    *,
    base_status: str,
    base_validation_flags: list[str],
    mapping_status: str,
    mapping_failure_reason: str,
    crop_uncertain: bool,
    extraction_quality_flags: list[str],
    review_flags: list[str],
    question_structure_detected: dict[str, Any],
) -> tuple[str, list[str]]:
    validation_flags = list(base_validation_flags)
    status = base_status

    structural_mapping_failures = {
        "question_subparts_incomplete",
        "question_scope_contaminated",
        "missing_terminal_mark_total",
        "question_mark_total_mismatch",
        "question_mark_total_missing",
        "likely_truncated_question_crop",
    }
    if mapping_failure_reason in structural_mapping_failures:
        status = "fail"
        if mapping_failure_reason not in validation_flags:
            validation_flags.append(mapping_failure_reason)

    support_groups = _polluted_pass_signal_groups(
        crop_uncertain=crop_uncertain,
        base_validation_flags=base_validation_flags,
        extraction_quality_flags=extraction_quality_flags,
        review_flags=review_flags,
        question_structure_detected=question_structure_detected,
    )
    if mapping_status == "pass" and len(support_groups) >= 2:
        status = "fail"
        if "polluted_pass_requires_review" not in validation_flags:
            validation_flags.append("polluted_pass_requires_review")

    return status, sorted(set(validation_flags))


def _polluted_pass_signal_groups(
    *,
    crop_uncertain: bool,
    base_validation_flags: list[str],
    extraction_quality_flags: list[str],
    review_flags: list[str],
    question_structure_detected: dict[str, Any],
) -> set[str]:
    if not crop_uncertain:
        return set()

    groups: set[str] = set()
    if any(
        flag in extraction_quality_flags
        for flag in {"likely_needs_visual_review", "math_corruption_suspected", "broken_fraction_structure", "suspicious_symbol_run"}
    ):
        groups.add("low_quality_text")
    if any(
        flag in review_flags
        for flag in {"low_confidence_question_crop", "crop_reaches_page_margin", "weak_question_text"}
    ):
        groups.add("crop_risk")
    if any(
        flag in base_validation_flags
        for flag in {"weak_question_anchor", "likely_truncated_question_crop", "missing_terminal_mark_total"}
    ):
        groups.add("question_validation_risk")
    contamination_indicators = question_structure_detected.get("contamination_indicators") or {}
    contamination_signal_score = int(contamination_indicators.get("signal_score", 0))
    if question_structure_detected.get("contamination_detected") or contamination_signal_score >= 2:
        groups.add("pollution_signals")
    return groups


def _question_topic_from_parts(
    classification: ClassificationResult,
    part_level_topics: list[dict[str, object]],
) -> dict[str, object]:
    review_flags = list(classification.review_flags)
    part_topics = []
    for part in part_level_topics:
        part_topic = str(part.get("topic", ""))
        if not part_topic or part_topic == classification.topic:
            continue
        if bool(part.get("topic_uncertain")) or str(part.get("topic_confidence", "")) == "low":
            continue
        part_topics.append(part_topic)
    secondary_topics = []
    for topic in part_topics:
        if topic not in secondary_topics:
            secondary_topics.append(topic)
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
    if secondary_topics:
        review_flags.append("mixed_topic_possible")
    if len(secondary_topics) >= 2 and classification.topic_confidence != "high":
        review_flags.append("topic_uncertain_mixed_major_topics")
        topic_uncertain = True

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


def _reconcile_paper_topics(records: list[QuestionRecord], config: AppConfig) -> None:
    if not records:
        return
    paper_family = records[0].paper_family
    if paper_family not in {"P1", "P3", "P4", "P5"}:
        return

    allowed_topics = set(config.paper_family_taxonomy.get(paper_family, {}))
    coverage = _paper_topic_coverage_summary(records, allowed_topics)
    missing_topics = sorted(topic for topic, counts in coverage.items() if counts["high"] == 0 and counts["medium"] == 0)

    for record in records:
        candidate_topics = _candidate_topics_for_reconciliation(record, allowed_topics)
        if not _record_is_reconciliation_candidate(record, candidate_topics):
            record.paper_repair_considered = False
            record.paper_repair_changed_topic = False
            record.paper_repair_candidates = []
            record.paper_repair_missing_topics = missing_topics
            record.paper_repair_reason = ""
            record.paper_repair_note = _paper_repair_note(missing_topics, changed=False, considered=False)
            record.paper_repair_supporting_evidence = {}
            continue

        record.paper_repair_considered = True
        record.paper_repair_candidates = candidate_topics
        record.paper_repair_missing_topics = missing_topics
        if len(candidate_topics) <= 1:
            record.paper_repair_changed_topic = False
            record.paper_repair_reason = ""
            record.paper_repair_note = _paper_repair_note(missing_topics, changed=False, considered=True)
            record.paper_repair_supporting_evidence = {
                "paper_family": paper_family,
                "coverage_summary": coverage,
                "eligible_for_repair": True,
                "candidate_topics": candidate_topics,
                "decision": "insufficient_local_alternatives",
            }
            continue

        current_scores = _reconciliation_topic_scores(record, record.topic, paper_family, missing_topics, coverage)
        best_topic = record.topic
        best_scores = current_scores
        all_scores = [current_scores]
        for topic in candidate_topics:
            scores = _reconciliation_topic_scores(record, topic, paper_family, missing_topics, coverage)
            all_scores.append(scores)
            if _is_better_reconciliation_candidate(scores, best_scores):
                best_topic = topic
                best_scores = scores

        record.paper_repair_supporting_evidence = {
            "paper_family": paper_family,
            "coverage_summary": coverage,
            "missing_topics": missing_topics,
            "eligible_for_repair": True,
            "candidate_topics": candidate_topics,
            "current_topic_scores": current_scores,
            "repair_candidate_scores": {item["topic"]: item for item in all_scores},
            "selected_topic": best_topic,
        }

        if best_topic == record.topic:
            record.reconciliation_changed_topic = False
            record.reconciliation_reason = ""
            record.reconciliation_note = _reconciliation_note(record, missing_topics, changed=False)
            record.paper_repair_changed_topic = False
            record.paper_repair_reason = ""
            record.paper_repair_note = _paper_repair_note(missing_topics, changed=False, considered=True)
            record.paper_repair_from_topic = record.topic
            record.paper_repair_to_topic = record.topic
            continue

        previous_topic = record.topic
        record.topic = best_topic
        record.question_level_topic = best_topic
        record.subtopic = "general"
        record.question_level_subtopic = "general"
        record.topic_confidence = "medium" if best_scores["local_support"] >= 3 else "low"
        record.topic_uncertain = record.topic_confidence == "low"
        record.confidence = min(0.72, max(record.confidence, 0.58)) if record.topic_confidence == "medium" else min(record.confidence, 0.5)
        record.review_flags = _update_reconciliation_flags(record.review_flags, record.topic_uncertain)
        record.topic_alternatives = [f"{paper_family}:{previous_topic}:general"] if previous_topic != best_topic else record.topic_alternatives[:1]
        record.secondary_topics = [previous_topic] if previous_topic != best_topic and previous_topic in allowed_topics else []
        record.reconciliation_changed_topic = True
        record.reconciliation_reason = (
            f"paper-level reconciliation reranked `{previous_topic}` to `{best_topic}` because `{best_topic}` "
            f"had genuine local support and better fit missing paper coverage"
        )
        record.reconciliation_note = _reconciliation_note(record, missing_topics, changed=True)
        record.paper_repair_changed_topic = True
        record.paper_repair_reason = (
            f"paper-level fallback repair reranked `{previous_topic}` to `{best_topic}` because the local label was weak "
            f"and `{best_topic}` had stronger local plausibility plus better missing-topic fit"
        )
        record.paper_repair_note = _paper_repair_note(missing_topics, changed=True, considered=True)
        record.paper_repair_from_topic = previous_topic
        record.paper_repair_to_topic = best_topic


def _record_is_reconciliation_candidate(record: QuestionRecord, candidate_topics: list[str]) -> bool:
    trigger_flags = {
        "low_classification_confidence",
        "topic_forced_no_rule_match",
        "topic_forced_low_confidence",
        "mixed_topic_possible",
        "weak_question_text",
        "weak_markscheme_signal",
        "likely_needs_visual_review",
        "part_topic_continuity_applied",
        "object_cue_conflict_with_method_scoring",
    }
    details = record.topic_evidence_details or {}
    score_breakdown = details.get("topic_score_breakdown", {})
    current_breakdown = score_breakdown.get(record.topic, {})
    clear_local_win = _score_gap_is_clear_winner(record.topic, score_breakdown)
    extraction_weak = record.extraction_quality_score < 0.68 or "likely_needs_visual_review" in record.extraction_quality_flags
    meaningful_alternatives = [topic for topic in candidate_topics if topic and topic != record.topic]
    has_meaningful_alternative = bool(meaningful_alternatives)
    weak_signal = bool(
        record.topic_confidence != "high"
        or record.topic_uncertain
        or any(flag in trigger_flags for flag in record.review_flags)
        or any("uncertain" in flag for flag in record.review_flags)
        or bool(details.get("object_cue_conflict_with_method_scoring"))
        or bool(current_breakdown.get("object_protection_penalty"))
        or (
            extraction_weak
            and (
                record.topic_confidence != "high"
                or record.topic_uncertain
                or bool(details.get("object_cue_conflict_with_method_scoring"))
                or len(meaningful_alternatives) > 0
                or bool(record.secondary_topics)
                or _has_meaningful_part_tension(record)
                or _score_breakdown_is_close(record.topic, score_breakdown)
            )
        )
    )

    if _is_protected_local_win(record, candidate_topics):
        return False

    if not weak_signal:
        return False
    if not has_meaningful_alternative:
        return False
    return True


def _candidate_topics_for_reconciliation(record: QuestionRecord, allowed_topics: set[str]) -> list[str]:
    candidates: list[str] = []
    if record.topic in allowed_topics:
        candidates.append(record.topic)
    for topic in _topics_from_alternatives(record.topic_alternatives):
        if topic in allowed_topics and topic not in candidates:
            candidates.append(topic)
    for part in record.part_level_topics:
        topic = str(part.get("topic", ""))
        if topic in allowed_topics and str(part.get("topic_confidence", "")) in {"medium", "high"} and topic not in candidates:
            candidates.append(topic)
    details = record.topic_evidence_details or {}
    object_topic = str(details.get("object_cue_primary_topic", ""))
    if object_topic in allowed_topics and object_topic not in candidates:
        candidates.append(object_topic)
    for topic in record.secondary_topics:
        if topic in allowed_topics and topic not in candidates:
            candidates.append(topic)
    for topic in _close_runner_up_topics(details.get("topic_score_breakdown", {}), record.topic):
        if topic in allowed_topics and topic not in candidates:
            candidates.append(topic)
    return candidates[:5]


def _topics_from_alternatives(alternatives: list[str]) -> list[str]:
    topics: list[str] = []
    for label in alternatives:
        parts = str(label).split(":")
        if len(parts) >= 2 and parts[1] and parts[1] not in topics:
            topics.append(parts[1])
    return topics


def _reconciliation_topic_scores(
    record: QuestionRecord,
    topic: str,
    paper_family: str,
    missing_topics: list[str],
    coverage: dict[str, dict[str, int]],
) -> dict[str, float]:
    question_text = (record.body_text_normalized or record.combined_question_text).lower()
    markscheme_text = record.answer_text.lower()
    details = record.topic_evidence_details or {}
    object_scores = details.get("object_cue_topic_scores", {})
    object_primary = str(details.get("object_cue_primary_topic", ""))
    score_breakdown = details.get("topic_score_breakdown", {})
    current_breakdown = score_breakdown.get(record.topic, {})
    candidate_breakdown = score_breakdown.get(topic, {})
    explicit_question = 1.0 if _explicit_primary_topic_from_text(question_text, paper_family) == topic else 0.0
    explicit_markscheme = 1.0 if markscheme_text and _explicit_primary_topic_from_text(markscheme_text, paper_family) == topic else 0.0
    part_support = sum(
        1.0
        for part in record.part_level_topics
        if str(part.get("topic", "")) == topic and str(part.get("topic_confidence", "")) in {"medium", "high"}
    )
    alternative_support = 1.0 if topic in _topics_from_alternatives(record.topic_alternatives) else 0.0
    current_bonus = 0.8 if topic == record.topic else 0.0
    object_support = min(3.0, float(object_scores.get(topic, 0.0)) / 6.0)
    object_alignment = 1.5 if object_primary == topic and topic != record.topic else 0.0
    secondary_support = 0.8 if topic in record.secondary_topics else 0.0
    close_runner_bonus = _close_score_bonus(current_breakdown, candidate_breakdown, topic != record.topic)
    extraction_bonus = 1.2 if (record.extraction_quality_score < 0.68 or "likely_needs_visual_review" in record.extraction_quality_flags) else 0.0
    drift_bonus = 1.2 if _looks_like_incidental_algebra_drift(record, topic) else 0.0
    paper_fit = _paper_repair_bonus(topic, missing_topics, coverage)
    local_support = (
        explicit_question * 3.0
        + explicit_markscheme * 1.8
        + part_support * 1.4
        + alternative_support
        + current_bonus
        + object_support
        + object_alignment
        + secondary_support
        + close_runner_bonus
    )
    repair_bonus = paper_fit + extraction_bonus + drift_bonus
    return {
        "topic": topic,
        "local_support": local_support,
        "paper_fit": paper_fit,
        "repair_bonus": repair_bonus,
        "total": local_support + repair_bonus,
        "explicit_question": explicit_question,
        "explicit_markscheme": explicit_markscheme,
        "object_support": object_support,
        "object_alignment": object_alignment,
        "close_runner_bonus": close_runner_bonus,
        "extraction_bonus": extraction_bonus,
        "drift_bonus": drift_bonus,
        "current_final_score": float(current_breakdown.get("final_score", 0.0)),
        "candidate_final_score": float(candidate_breakdown.get("final_score", 0.0)),
    }


def _is_better_reconciliation_candidate(candidate: dict[str, float], current: dict[str, float]) -> bool:
    if candidate["topic"] == current["topic"]:
        return False
    if candidate["local_support"] < 2.6:
        return False
    if candidate["repair_bonus"] < 0.9:
        return False
    if candidate["total"] < current["total"] + 1.25:
        return False
    if candidate["local_support"] + 0.5 < current["local_support"]:
        return False
    return True


def _update_reconciliation_flags(flags: list[str], topic_uncertain: bool) -> list[str]:
    cleaned = [
        flag
        for flag in flags
        if flag not in {"mixed_topic_possible", "topic_forced_no_rule_match", "topic_forced_low_confidence"}
    ]
    cleaned.append("paper_level_topic_reconciled")
    if not topic_uncertain:
        cleaned = [flag for flag in cleaned if flag != "low_classification_confidence"]
    return sorted(set(cleaned))


def _reconciliation_note(record: QuestionRecord, missing_topics: list[str], changed: bool) -> str:
    if changed:
        return f"soft paper-level coverage prior considered missing topics {missing_topics} and reranked this weak label"
    if missing_topics:
        return f"soft paper-level coverage prior considered missing topics {missing_topics} but local evidence remained stronger"
    return "soft paper-level coverage prior found no meaningful missing-topic repair"


def _paper_repair_note(missing_topics: list[str], changed: bool, considered: bool) -> str:
    if not considered:
        return "paper-level fallback repair did not consider this question because the local label was protected"
    if changed:
        return f"paper-level fallback repair used missing-topic pressure from {missing_topics} to rerank a weak label"
    if missing_topics:
        return f"paper-level fallback repair considered missing topics {missing_topics} but did not find enough local support"
    return "paper-level fallback repair found no underrepresented topics worth using"


def _paper_topic_coverage_summary(records: list[QuestionRecord], allowed_topics: set[str]) -> dict[str, dict[str, int]]:
    coverage = {topic: {"high": 0, "medium": 0, "weak": 0} for topic in sorted(allowed_topics)}
    for record in records:
        topic = record.topic
        if topic not in coverage:
            continue
        bucket = "weak"
        if record.topic_confidence == "high" and not record.topic_uncertain:
            bucket = "high"
        elif record.topic_confidence == "medium" and not record.topic_uncertain:
            bucket = "medium"
        coverage[topic][bucket] += 1
    return coverage


def _close_runner_up_topics(score_breakdown: dict[str, dict[str, Any]], current_topic: str) -> list[str]:
    current_score = float(score_breakdown.get(current_topic, {}).get("final_score", 0.0))
    close_topics: list[str] = []
    for topic, details in sorted(score_breakdown.items(), key=lambda item: float(item[1].get("final_score", 0.0)), reverse=True):
        if topic == current_topic:
            continue
        score = float(details.get("final_score", 0.0))
        if current_score and current_score - score > 6.5:
            continue
        if score <= 0:
            continue
        close_topics.append(topic)
        if len(close_topics) >= 2:
            break
    return close_topics


def _score_gap_is_clear_winner(current_topic: str, score_breakdown: dict[str, dict[str, Any]]) -> bool:
    if current_topic not in score_breakdown:
        return False
    ordered = sorted((float(details.get("final_score", 0.0)), topic) for topic, details in score_breakdown.items())
    if len(ordered) < 2:
        return True
    top_score, top_topic = ordered[-1]
    runner_up_score = ordered[-2][0]
    return top_topic == current_topic and top_score - runner_up_score >= 8.0


def _score_breakdown_is_close(current_topic: str, score_breakdown: dict[str, dict[str, Any]]) -> bool:
    if current_topic not in score_breakdown or len(score_breakdown) < 2:
        return False
    ordered = sorted((float(details.get("final_score", 0.0)), topic) for topic, details in score_breakdown.items())
    top_score, top_topic = ordered[-1]
    runner_up_score = ordered[-2][0]
    return top_topic == current_topic and top_score - runner_up_score <= 6.5


def _has_meaningful_part_tension(record: QuestionRecord) -> bool:
    for part in record.part_level_topics:
        part_topic = str(part.get("topic", ""))
        if not part_topic or part_topic == record.topic:
            continue
        if str(part.get("topic_confidence", "")) in {"medium", "high"} and not bool(part.get("topic_uncertain")):
            return True
    return False


def _is_protected_local_win(record: QuestionRecord, candidate_topics: list[str]) -> bool:
    details = record.topic_evidence_details or {}
    score_breakdown = details.get("topic_score_breakdown", {})
    object_primary = str(details.get("object_cue_primary_topic", ""))
    object_scores = details.get("object_cue_topic_scores", {})
    has_object_conflict = bool(details.get("object_cue_conflict_with_method_scoring"))
    meaningful_alternatives = [topic for topic in candidate_topics if topic and topic != record.topic]
    strong_object_anchor = object_primary == record.topic and float(object_scores.get(record.topic, 0.0)) >= 8.0
    clear_local_win = _score_gap_is_clear_winner(record.topic, score_breakdown)
    no_part_tension = not _has_meaningful_part_tension(record)
    return bool(
        record.topic_confidence == "high"
        and not record.topic_uncertain
        and strong_object_anchor
        and clear_local_win
        and not has_object_conflict
        and not meaningful_alternatives
        and no_part_tension
    )


def _close_score_bonus(
    current_breakdown: dict[str, Any],
    candidate_breakdown: dict[str, Any],
    is_alternative: bool,
) -> float:
    if not is_alternative:
        return 0.0
    current_score = float(current_breakdown.get("final_score", 0.0))
    candidate_score = float(candidate_breakdown.get("final_score", 0.0))
    if candidate_score <= 0:
        return 0.0
    gap = current_score - candidate_score
    if gap <= 3.0:
        return 1.4
    if gap <= 7.0:
        return 0.8
    return 0.0


def _paper_repair_bonus(topic: str, missing_topics: list[str], coverage: dict[str, dict[str, int]]) -> float:
    if topic in missing_topics:
        return 1.5
    counts = coverage.get(topic, {})
    if counts and counts.get("high", 0) == 0 and counts.get("medium", 0) == 0 and counts.get("weak", 0) > 0:
        return 0.7
    return 0.0


def _looks_like_incidental_algebra_drift(record: QuestionRecord, alternative_topic: str) -> bool:
    details = record.topic_evidence_details or {}
    object_primary = str(details.get("object_cue_primary_topic", ""))
    if record.topic not in {"algebra", "quadratics", "polynomials"}:
        return False
    if alternative_topic != object_primary:
        return False
    return float(details.get("object_cue_topic_scores", {}).get(alternative_topic, 0.0)) >= 6.0


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
    path = config.output.debug_dir / f"{paper_name}_diagnostics.json"
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
    path = config.output.debug_dir / name
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
    allowed_topics = set(config.paper_family_taxonomy.get(records[0].paper_family, {})) if records else set()
    payload = {
        "source_pdf": _display_path(question_pdf),
        "paper_name": paper_name,
        "paper_repair_summary": _paper_repair_debug_summary(records, allowed_topics),
        "questions": [
            {
                "question_number": record.question_number,
                "text_snippet": record.combined_question_text[:500],
                "body_text_raw": record.body_text_raw[:500],
                "body_text_normalized": record.body_text_normalized[:500],
                "math_lines": record.math_lines,
                "diagram_text": record.diagram_text,
                "extraction_quality_score": record.extraction_quality_score,
                "extraction_quality_flags": record.extraction_quality_flags,
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
                "detected_object_cues": record.topic_evidence_details.get("detected_object_cues", []),
                "object_cue_topic_scores": record.topic_evidence_details.get("object_cue_topic_scores", {}),
                "object_cue_source_topic_scores": record.topic_evidence_details.get("object_cue_source_topic_scores", {}),
                "object_cue_primary_topic": record.topic_evidence_details.get("object_cue_primary_topic", ""),
                "object_cue_conflict_with_method_scoring": record.topic_evidence_details.get(
                    "object_cue_conflict_with_method_scoring", False
                ),
                "object_cue_protection_applied": record.topic_evidence_details.get("object_cue_protection_applied", False),
                "object_cue_protection_topics": record.topic_evidence_details.get("object_cue_protection_topics", []),
                "object_cue_resisted_override": record.topic_evidence_details.get("object_cue_resisted_override", False),
                "source_method_stage_top_topic": record.topic_evidence_details.get("source_method_stage_top_topic", ""),
                "source_method_stage_top_score": record.topic_evidence_details.get("source_method_stage_top_score", 0),
                "object_cue_override_stage": record.topic_evidence_details.get("object_cue_override_stage", ""),
                "object_cue_override_topic": record.topic_evidence_details.get("object_cue_override_topic", ""),
                "topic_score_breakdown": record.topic_evidence_details.get("topic_score_breakdown", {}),
                "secondary_topics": record.secondary_topics,
                "part_level_topics": record.part_level_topics,
                "alternative_candidate_topics": record.topic_alternatives if record.topic_confidence != "high" else [],
                "difficulty": record.difficulty,
                "difficulty_confidence": record.difficulty_confidence,
                "difficulty_evidence": record.difficulty_evidence,
                "difficulty_uncertain": record.difficulty_uncertain,
                "reconciliation_changed_topic": record.reconciliation_changed_topic,
                "reconciliation_reason": record.reconciliation_reason,
                "reconciliation_note": record.reconciliation_note,
                "paper_repair_considered": record.paper_repair_considered,
                "paper_repair_changed_topic": record.paper_repair_changed_topic,
                "paper_repair_reason": record.paper_repair_reason,
                "paper_repair_note": record.paper_repair_note,
                "paper_repair_from_topic": record.paper_repair_from_topic,
                "paper_repair_to_topic": record.paper_repair_to_topic,
                "paper_repair_candidates": record.paper_repair_candidates,
                "paper_repair_missing_topics": record.paper_repair_missing_topics,
                "paper_repair_supporting_evidence": record.paper_repair_supporting_evidence,
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
    path = config.output.debug_dir / f"{paper_name}_topic_debug.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _paper_repair_debug_summary(records: list[QuestionRecord], allowed_topics: set[str]) -> dict[str, Any]:
    if not records:
        return {}
    coverage = _paper_topic_coverage_summary(records, allowed_topics)
    missing_topics = sorted(topic for topic, counts in coverage.items() if counts["high"] == 0 and counts["medium"] == 0)
    eligible_questions = [record.question_number for record in records if record.paper_repair_considered]
    changed_questions = [record.question_number for record in records if record.paper_repair_changed_topic]
    return {
        "paper_family": records[0].paper_family,
        "topic_coverage_summary": coverage,
        "missing_or_underrepresented_topics": missing_topics,
        "repair_eligible_questions": eligible_questions,
        "repair_changed_questions": changed_questions,
    }
