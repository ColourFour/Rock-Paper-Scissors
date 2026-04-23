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
    validation_status: str = "pass"
    validation_flags: list[str] = field(default_factory=list)
    recovery_attempted: bool = False
    recovery_result: str = ""
    structure_detected: dict[str, Any] = field(default_factory=dict)
    question_total_detected: int | None = None
    format_profile: str = "legacy"

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
    mark_scheme_source_pdf: str = ""
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
    validation_status: str = ""
    validation_flags: list[str] = field(default_factory=list)
    scope_quality_status: str = ""
    text_source_profile: str = ""
    text_fidelity_status: str = ""
    text_fidelity_flags: list[str] = field(default_factory=list)
    topic_trust_status: str = ""
    recovery_attempted: bool = False
    recovery_result: str = ""
    question_structure_detected: dict[str, Any] = field(default_factory=dict)
    mark_scheme_structure_detected: dict[str, Any] = field(default_factory=dict)
    question_total_detected: int | None = None
    mark_scheme_total_detected: int | None = None
    question_format_profile: str = ""
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
    paper_total_expected: int | None = None
    paper_total_detected: int | None = None
    paper_total_status: str = ""
    rescan_triggered: bool = False
    rescan_result: str = ""
    paper_total_before_rescan: int | None = None
    paper_total_after_rescan: int | None = None
    paper_total_focus_questions: list[str] = field(default_factory=list)
    paper_total_focus_pages: list[int] = field(default_factory=list)
    paper_total_focus_reason: str = ""


def _clean_model_text(text: str) -> str:
    stripped_controls = "".join(char if ord(char) >= 32 or char in "\n\t\r" else " " for char in text)
    return " ".join(stripped_controls.replace("\u00a0", " ").split())
