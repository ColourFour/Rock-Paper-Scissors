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
        return "\n".join(block.text.strip() for block in self.blocks if block.text.strip()).strip()


@dataclass
class ClassificationResult:
    paper_family: str
    topic: str
    subtopic: str
    difficulty: str
    confidence: float
    review_flags: list[str] = field(default_factory=list)
    topic_confidence: str = "low"
    topic_evidence: str = ""
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


@dataclass
class QuestionRecord:
    source_pdf: str
    paper_name: str
    question_number: str
    full_question_label: str
    screenshot_path: str
    combined_question_text: str
    answer_text: str
    paper_family: str
    topic: str
    subtopic: str
    topic_confidence: str
    topic_evidence: str
    secondary_topics: list[str]
    topic_uncertain: bool
    difficulty: str
    marks: int | None
    marks_if_available: int | None
    page_numbers: list[int]
    review_flags: list[str]
    confidence: float
    crop_uncertain: bool = False
    crop_debug_paths: list[str] = field(default_factory=list)
    topic_alternatives: list[str] = field(default_factory=list)
    question_level_paper_family: str = ""
    question_level_topic: str = ""
    question_level_subtopic: str = ""
    part_level_topics: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        question_level_paper_family = self.question_level_paper_family or self.paper_family
        question_level_topic = self.question_level_topic or self.topic
        question_level_subtopic = self.question_level_subtopic or self.subtopic
        return {
            "source_pdf": self.source_pdf,
            "paper_name": self.paper_name,
            "question_number": self.question_number,
            "full_question_label": self.full_question_label,
            "screenshot_path": self.screenshot_path,
            "combined_question_text": self.combined_question_text,
            "answer_text": self.answer_text,
            "paper_family": question_level_paper_family,
            "question_level_paper_family": question_level_paper_family,
            "question_level_topic": question_level_topic,
            "question_level_subtopic": question_level_subtopic,
            "part_level_topics": self.part_level_topics,
            "topic": question_level_topic,
            "subtopic": question_level_subtopic,
            "topic_confidence": self.topic_confidence,
            "topic_evidence": self.topic_evidence,
            "secondary_topics": self.secondary_topics,
            "topic_uncertain": self.topic_uncertain,
            "difficulty": self.difficulty,
            "marks": self.marks,
            "marks_if_available": self.marks_if_available,
            "page_numbers": self.page_numbers,
            "review_flags": self.review_flags,
            "confidence": round(self.confidence, 3),
            "crop_uncertain": self.crop_uncertain,
            "crop_debug_paths": self.crop_debug_paths,
            "topic_alternatives": self.topic_alternatives,
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
        }
