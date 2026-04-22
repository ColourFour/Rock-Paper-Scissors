from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BoundingBox:
    """PDF-space rectangle in points."""

    x0: float
    y0: float
    x1: float
    y1: float

    def padded(self, amount: float, width: float, height: float) -> "BoundingBox":
        return BoundingBox(
            max(0, self.x0 - amount),
            max(0, self.y0 - amount),
            min(width, self.x1 + amount),
            min(height, self.y1 + amount),
        )


@dataclass(frozen=True)
class TextBlock:
    page_number: int
    text: str
    bbox: BoundingBox
    source: str = "pdf"
    confidence: float | None = None
    font_size: float | None = None
    font_name: str | None = None
    is_bold: bool = False

    @property
    def first_line(self) -> str:
        for line in self.text.splitlines():
            stripped = line.strip()
            if stripped:
                return stripped
        return ""


@dataclass(frozen=True)
class PageLayout:
    page_number: int
    width: float
    height: float
    blocks: list[TextBlock]
    graphics: list[BoundingBox] = field(default_factory=list)
    text_source: str = "pdf"
    extraction_warning: str | None = None

    @property
    def text(self) -> str:
        return "\n".join(block.text for block in self.blocks if block.text.strip())


@dataclass(frozen=True)
class QuestionStart:
    question_number: str
    page_number: int
    y0: float
    x0: float
    label: str
    block_index: int
    bbox: BoundingBox | None = None
    font_size: float | None = None
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)


@dataclass
class QuestionSpan:
    source_pdf: Path
    paper_name: str
    question_number: str
    start_page: int
    start_y: float
    end_page: int
    end_y: float
    page_numbers: list[int]
    blocks: list[TextBlock]
    full_question_label: str
    review_flags: list[str] = field(default_factory=list)
    anchor: QuestionStart | None = None

    @property
    def combined_text(self) -> str:
        return "\n".join(_clean_model_text(block.text) for block in self.blocks if _clean_model_text(block.text)).strip()


@dataclass
class ClassificationResult:
    paper_family: str
    source_paper_code: str
    source_paper_family: str
    inferred_paper_family: str
    paper_family_confidence: str
    topic: str
    subtopic: str
    difficulty: str
    difficulty_confidence: str
    difficulty_evidence: str
    difficulty_uncertain: bool
    confidence: float
    review_flags: list[str] = field(default_factory=list)
    topic_confidence: str = "low"
    topic_evidence: str = ""
    topic_evidence_details: dict[str, Any] = field(default_factory=dict)
    secondary_topics: list[str] = field(default_factory=list)
    topic_uncertain: bool = False
    alternative_topics: list[str] = field(default_factory=list)


@dataclass
class RenderResult:
    screenshot_path: Path
    review_flags: list[str] = field(default_factory=list)
    crop_uncertain: bool = False
    debug_paths: list[str] = field(default_factory=list)
    extracted_text: str = ""
    crop_diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass
class QuestionRecord:
    source_pdf: str
    paper_name: str
    question_number: str
    full_question_label: str
    screenshot_path: str
    combined_question_text: str
    body_text_raw: str
    body_text_normalized: str
    math_lines: list[str]
    diagram_text: list[str]
    extraction_quality_score: float
    extraction_quality_flags: list[str]
    part_texts: list[dict[str, Any]]
    answer_text: str
    paper_family: str
    source_paper_family: str
    inferred_paper_family: str
    paper_family_confidence: str
    topic: str
    subtopic: str
    topic_confidence: str
    topic_evidence: str
    secondary_topics: list[str]
    topic_uncertain: bool
    difficulty: str
    difficulty_confidence: str
    difficulty_evidence: str
    difficulty_uncertain: bool
    marks: int | None
    marks_if_available: int | None
    page_numbers: list[int]
    review_flags: list[str]
    confidence: float
    source_paper_code: str = ""
    syllabus_code: str = ""
    session: str = ""
    year: str = ""
    document_type: str = ""
    component: str = ""
    document_key: str = ""
    metadata_source: str = ""
    crop_uncertain: bool = False
    question_crop_confidence: str = ""
    crop_debug_paths: list[str] = field(default_factory=list)
    question_crop_diagnostics: dict[str, Any] = field(default_factory=dict)
    topic_alternatives: list[str] = field(default_factory=list)
    topic_evidence_details: dict[str, Any] = field(default_factory=dict)
    examiner_report_evidence: dict[str, Any] = field(default_factory=dict)
    question_level_paper_family: str = ""
    question_level_topic: str = ""
    question_level_subtopic: str = ""
    part_level_topics: list[dict[str, Any]] = field(default_factory=list)
    markscheme_image: str = ""
    markscheme_pages: list[int] = field(default_factory=list)
    markscheme_question_number: str = ""
    markscheme_crop_confidence: str = ""
    markscheme_mapping_method: str = ""
    markscheme_table_detected: bool = False
    markscheme_table_header_detected: list[str] = field(default_factory=list)
    markscheme_nearby_anchors: list[str] = field(default_factory=list)
    markscheme_debug_paths: list[str] = field(default_factory=list)
    markscheme_table_header_ok: bool = False
    markscheme_continuation_rows_included: bool = False
    question_subparts: list[str] = field(default_factory=list)
    markscheme_subparts: list[str] = field(default_factory=list)
    question_marks_total: int | None = None
    markscheme_marks_total: int | None = None
    markscheme_mapping_status: str = ""
    markscheme_failure_reason: str = ""
    qa_status: str = "pass"
    qa_flags: list[str] = field(default_factory=list)
    reconciliation_changed_topic: bool = False
    reconciliation_reason: str = ""
    reconciliation_note: str = ""
    paper_repair_considered: bool = False
    paper_repair_changed_topic: bool = False
    paper_repair_reason: str = ""
    paper_repair_note: str = ""
    paper_repair_from_topic: str = ""
    paper_repair_to_topic: str = ""
    paper_repair_candidates: list[str] = field(default_factory=list)
    paper_repair_missing_topics: list[str] = field(default_factory=list)
    paper_repair_supporting_evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        question_level_paper_family = self.question_level_paper_family or self.paper_family
        question_level_topic = self.question_level_topic or self.topic
        question_level_subtopic = self.question_level_subtopic or self.subtopic
        return {
            "source_pdf": self.source_pdf,
            "paper_name": self.paper_name,
            "question_number": self.question_number,
            "full_question_label": self.full_question_label,
            "question_image": self.screenshot_path,
            "question_pages": self.page_numbers,
            "question_crop_confidence": self.question_crop_confidence or ("low" if self.crop_uncertain else "high"),
            "screenshot_path": self.screenshot_path,
            "combined_question_text": self.combined_question_text,
            "body_text_raw": self.body_text_raw,
            "body_text_normalized": self.body_text_normalized,
            "math_lines": self.math_lines,
            "diagram_text": self.diagram_text,
            "extraction_quality_score": round(self.extraction_quality_score, 3),
            "extraction_quality_flags": self.extraction_quality_flags,
            "part_texts": self.part_texts,
            "answer_text": self.answer_text,
            "paper_family": question_level_paper_family,
            "source_paper_code": self.source_paper_code,
            "syllabus_code": self.syllabus_code,
            "session": self.session,
            "year": self.year,
            "document_type": self.document_type,
            "component": self.component,
            "document_key": self.document_key,
            "metadata_source": self.metadata_source,
            "source_paper_family": self.source_paper_family,
            "inferred_paper_family": self.inferred_paper_family,
            "paper_family_confidence": self.paper_family_confidence,
            "question_level_paper_family": question_level_paper_family,
            "question_level_topic": question_level_topic,
            "question_level_subtopic": question_level_subtopic,
            "part_level_topics": self.part_level_topics,
            "topic": question_level_topic,
            "subtopic": question_level_subtopic,
            "topic_confidence": self.topic_confidence,
            "topic_confidence_score": _confidence_score(self.topic_confidence),
            "topic_evidence": self.topic_evidence,
            "topic_evidence_details": self.topic_evidence_details,
            "examiner_report_evidence": self.examiner_report_evidence,
            "secondary_topics": self.secondary_topics,
            "topic_uncertain": self.topic_uncertain,
            "difficulty": self.difficulty,
            "difficulty_confidence": self.difficulty_confidence,
            "difficulty_evidence": self.difficulty_evidence,
            "difficulty_uncertain": self.difficulty_uncertain,
            "reconciliation_changed_topic": self.reconciliation_changed_topic,
            "reconciliation_reason": self.reconciliation_reason,
            "reconciliation_note": self.reconciliation_note,
            "paper_repair_considered": self.paper_repair_considered,
            "paper_repair_changed_topic": self.paper_repair_changed_topic,
            "paper_repair_reason": self.paper_repair_reason,
            "paper_repair_note": self.paper_repair_note,
            "paper_repair_from_topic": self.paper_repair_from_topic,
            "paper_repair_to_topic": self.paper_repair_to_topic,
            "paper_repair_candidates": self.paper_repair_candidates,
            "paper_repair_missing_topics": self.paper_repair_missing_topics,
            "paper_repair_supporting_evidence": self.paper_repair_supporting_evidence,
            "marks": self.marks,
            "marks_if_available": self.marks_if_available,
            "page_numbers": self.page_numbers,
            "review_flags": self.review_flags,
            "confidence": round(self.confidence, 3),
            "crop_uncertain": self.crop_uncertain,
            "crop_debug_paths": self.crop_debug_paths,
            "question_crop_diagnostics": self.question_crop_diagnostics,
            "topic_alternatives": self.topic_alternatives,
            "markscheme_text": self.answer_text,
            "markscheme_image": self.markscheme_image,
            "markscheme_pages": self.markscheme_pages,
            "markscheme_question_number": self.markscheme_question_number,
            "markscheme_crop_confidence": self.markscheme_crop_confidence,
            "markscheme_mapping_method": self.markscheme_mapping_method,
            "markscheme_table_detected": self.markscheme_table_detected,
            "markscheme_table_header_detected": self.markscheme_table_header_detected,
            "markscheme_nearby_anchors": self.markscheme_nearby_anchors,
            "markscheme_debug_paths": self.markscheme_debug_paths,
            "markscheme_table_header_ok": self.markscheme_table_header_ok,
            "question_subparts": self.question_subparts,
            "markscheme_subparts": self.markscheme_subparts,
            "question_marks_total": self.question_marks_total,
            "markscheme_marks_total": self.markscheme_marks_total,
            "markscheme_mapping_status": self.markscheme_mapping_status,
            "markscheme_failure_reason": self.markscheme_failure_reason,
            "mark_scheme": {
                "page": self.markscheme_pages[0] if self.markscheme_pages else None,
                "table_header_ok": self.markscheme_table_header_ok,
                "label_matched": self.markscheme_question_number,
                "continuation_rows_included": self.markscheme_continuation_rows_included,
                "crop_method": self.markscheme_mapping_method,
                "detected_subparts_from_question_paper": self.question_subparts,
                "detected_subparts_from_mark_scheme": self.markscheme_subparts,
                "question_paper_total_marks": self.question_marks_total,
                "mark_scheme_total_marks": self.markscheme_marks_total,
                "mapping_status": self.markscheme_mapping_status,
                "failure_reason": self.markscheme_failure_reason,
            },
            "qa": {
                "status": self.qa_status,
                "flags": self.qa_flags,
            },
        }


@dataclass(frozen=True)
class ReviewItem:
    paper_name: str
    question_number: str
    issue_type: str
    message: str
    source_pdf: str
    page_numbers: list[int] = field(default_factory=list)
    crop_uncertain: bool = False
    crop_debug_paths: list[str] = field(default_factory=list)
    paper_family: str = ""
    topic_candidates: list[str] = field(default_factory=list)
    chosen_topic: str = ""
    chosen_difficulty: str = ""
    evidence: str = ""
    markscheme_image_found: bool | None = None
    markscheme_pages: list[int] = field(default_factory=list)
    markscheme_crop_confidence: str = ""
    markscheme_mapping_method: str = ""
    markscheme_table_detected: bool | None = None
    markscheme_table_header_detected: list[str] = field(default_factory=list)
    markscheme_nearby_anchors: list[str] = field(default_factory=list)
    classification_restricted_by_paper_family: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "paper_name": self.paper_name,
            "question_number": self.question_number,
            "issue_type": self.issue_type,
            "message": self.message,
            "source_pdf": self.source_pdf,
            "page_numbers": ",".join(str(page) for page in self.page_numbers),
            "crop_uncertain": "true" if self.crop_uncertain else "false",
            "crop_debug_paths": ",".join(self.crop_debug_paths),
            "paper_family": self.paper_family,
            "topic_candidates": ";".join(self.topic_candidates),
            "chosen_topic": self.chosen_topic,
            "chosen_difficulty": self.chosen_difficulty,
            "evidence": self.evidence,
            "markscheme_image_found": "" if self.markscheme_image_found is None else ("true" if self.markscheme_image_found else "false"),
            "markscheme_pages": ",".join(str(page) for page in self.markscheme_pages),
            "markscheme_crop_confidence": self.markscheme_crop_confidence,
            "markscheme_mapping_method": self.markscheme_mapping_method,
            "markscheme_table_detected": "" if self.markscheme_table_detected is None else ("true" if self.markscheme_table_detected else "false"),
            "markscheme_table_header_detected": ",".join(self.markscheme_table_header_detected),
            "markscheme_nearby_anchors": ";".join(self.markscheme_nearby_anchors),
            "classification_restricted_by_paper_family": ""
            if self.classification_restricted_by_paper_family is None
            else ("true" if self.classification_restricted_by_paper_family else "false"),
        }


def _confidence_score(label: str) -> float:
    return {
        "high": 0.91,
        "medium": 0.66,
        "low": 0.35,
    }.get(label, 0.0)


def _clean_model_text(text: str) -> str:
    stripped_controls = "".join(char if ord(char) >= 32 or char in "\n\t\r" else " " for char in text)
    return " ".join(stripped_controls.replace("\u00a0", " ").split())
