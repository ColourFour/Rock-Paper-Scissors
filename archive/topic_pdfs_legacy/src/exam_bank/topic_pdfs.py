from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
import logging
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from .config import AppConfig
from .models import QuestionRecord, ReviewItem
from .review import append_review_items


DIFFICULTY_SECTIONS = {
    "easy": "Easy",
    "average": "Medium",
    "difficult": "Hard",
}
SECTION_ORDER = ["easy", "average", "difficult"]
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class TopicPDFResult:
    pdf_paths: list[Path]
    skipped_count: int
    review_path: Path | None = None
    mark_scheme_link_count: int = 0
    missing_mark_scheme_link_count: int = 0


@dataclass(frozen=True)
class TopicPDFWriteResult:
    wrote_pdf: bool
    mark_scheme_link_count: int = 0
    missing_mark_scheme_link_count: int = 0


@dataclass(frozen=True)
class TopicPDFQuestion:
    topic: str
    subtopic: str
    difficulty: str
    screenshot_path: Path
    paper_name: str
    question_number: str
    marks_if_available: int | None
    source_pdf: str = ""
    page_numbers: list[int] | None = None
    markscheme_image_path: Path | None = None
    markscheme_image_raw: str = ""


def build_topic_pdfs_from_records(records: Iterable[QuestionRecord | Mapping[str, Any]], config: AppConfig) -> TopicPDFResult:
    record_dicts = [record.to_dict() if isinstance(record, QuestionRecord) else dict(record) for record in records]
    return build_topic_pdfs(record_dicts, config)


def build_topic_pdfs_from_json(json_path: str | Path, config: AppConfig) -> TopicPDFResult:
    json_path = Path(json_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Question bank JSON must contain a list of records: {json_path}")
    return build_topic_pdfs([dict(item) for item in data if isinstance(item, dict)], config)


def build_topic_pdfs(records: list[Mapping[str, Any]], config: AppConfig) -> TopicPDFResult:
    valid_questions, review_items = _valid_questions(records)
    grouped = _group_by_topic(valid_questions)
    output_dir = config.topic_pdfs.topic_pdf_output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_paths: list[Path] = []
    mark_scheme_link_count = 0
    missing_mark_scheme_link_count = 0
    for topic, questions in sorted(grouped.items()):
        pdf_path = output_dir / f"{_safe_filename(topic)}.pdf"
        write_result = _write_topic_pdf(topic, questions, pdf_path, config, review_items)
        mark_scheme_link_count += write_result.mark_scheme_link_count
        missing_mark_scheme_link_count += write_result.missing_mark_scheme_link_count
        if write_result.wrote_pdf:
            pdf_paths.append(pdf_path)

    review_path = append_review_items(review_items, config) if review_items else None
    if config.topic_pdfs.embed_mark_schemes:
        LOGGER.info(
            "Topic PDF embedded mark schemes: embedded=%s missing_or_unreadable=%s",
            mark_scheme_link_count,
            missing_mark_scheme_link_count,
        )
    return TopicPDFResult(
        pdf_paths=pdf_paths,
        skipped_count=len(review_items),
        review_path=review_path,
        mark_scheme_link_count=mark_scheme_link_count,
        missing_mark_scheme_link_count=missing_mark_scheme_link_count,
    )


def _valid_questions(records: list[Mapping[str, Any]]) -> tuple[list[TopicPDFQuestion], list[ReviewItem]]:
    valid: list[TopicPDFQuestion] = []
    review_items: list[ReviewItem] = []
    for record in records:
        if not _student_usable(record):
            review_items.append(_review_item(record, "topic_pdf_manual_excluded"))
            continue
        topic = str(record.get("topic") or record.get("question_level_topic") or "").strip()
        difficulty = str(record.get("difficulty") or "").strip().lower()
        screenshot_raw = str(record.get("question_image") or record.get("screenshot_path") or "").strip()
        paper_name = str(record.get("paper_name") or "").strip()
        question_number = str(record.get("question_number") or "").strip()

        if not topic:
            review_items.append(_review_item(record, "topic_pdf_missing_topic"))
            continue
        if difficulty not in DIFFICULTY_SECTIONS:
            review_items.append(_review_item(record, "topic_pdf_missing_difficulty"))
            continue
        if not screenshot_raw:
            review_items.append(_review_item(record, "topic_pdf_missing_image"))
            continue

        screenshot_path = _resolve_path(screenshot_raw)
        if not screenshot_path.exists():
            review_items.append(_review_item(record, "topic_pdf_missing_image"))
            continue
        markscheme_image_raw = str(record.get("markscheme_image") or "").strip()
        markscheme_image_path = _resolve_path(markscheme_image_raw) if markscheme_image_raw else None

        valid.append(
            TopicPDFQuestion(
                topic=topic,
                subtopic=str(record.get("subtopic") or record.get("question_level_subtopic") or "").strip(),
                difficulty=difficulty,
                screenshot_path=screenshot_path,
                paper_name=paper_name,
                question_number=question_number,
                marks_if_available=_optional_int(record.get("marks_if_available") or record.get("marks")),
                source_pdf=str(record.get("source_pdf") or ""),
                page_numbers=_page_numbers(record.get("page_numbers")),
                markscheme_image_path=markscheme_image_path,
                markscheme_image_raw=markscheme_image_raw,
            )
        )
    return valid, review_items


def _student_usable(record: Mapping[str, Any]) -> bool:
    if record.get("student_usable") is False:
        return False
    if record.get("usable") is False:
        return False
    if str(record.get("crop_status") or "").strip().lower() == "bad":
        return False
    return True


def _group_by_topic(questions: list[TopicPDFQuestion]) -> dict[str, list[TopicPDFQuestion]]:
    grouped: dict[str, list[TopicPDFQuestion]] = defaultdict(list)
    for question in questions:
        grouped[question.topic].append(question)
    return dict(grouped)


def _write_topic_pdf(
    topic: str,
    questions: list[TopicPDFQuestion],
    pdf_path: Path,
    config: AppConfig,
    review_items: list[ReviewItem],
) -> TopicPDFWriteResult:
    try:
        from PIL import Image as PILImage
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.pdfbase.pdfmetrics import stringWidth
        from reportlab.platypus import Flowable, Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer
    except ImportError as exc:
        raise RuntimeError("ReportLab and Pillow are required for topic PDF exports. Run `pip install -r requirements.txt`.") from exc

    class Bookmark(Flowable):
        def __init__(self, name: str) -> None:
            super().__init__()
            self.name = name

        def wrap(self, availWidth: float, availHeight: float) -> tuple[float, float]:
            return (0, 0)

        def draw(self) -> None:
            self.canv.bookmarkPage(self.name)

    class InternalLink(Flowable):
        def __init__(self, text: str, destination: str, style: ParagraphStyle) -> None:
            super().__init__()
            self.text = text
            self.destination = destination
            self.style = style
            self.width = 0
            self.height = style.leading

        def wrap(self, availWidth: float, availHeight: float) -> tuple[float, float]:
            self.width = min(availWidth, stringWidth(self.text, self.style.fontName, self.style.fontSize) + 2)
            self.height = self.style.leading
            return (self.width, self.height)

        def draw(self) -> None:
            color = self.style.textColor or colors.HexColor("#1F3A5F")
            self.canv.setFillColor(color)
            self.canv.setFont(self.style.fontName, self.style.fontSize)
            self.canv.drawString(0, 1, self.text)
            self.canv.line(0, 0, self.width, 0)
            self.canv.linkRect(
                "",
                self.destination,
                Rect=(0, -2, self.width, self.height),
                relative=1,
                thickness=0,
            )

    page_size = A4 if config.topic_pdfs.page_size.upper() == "A4" else letter
    margin = config.topic_pdfs.margin
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=page_size,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
        title=f"{_topic_title(topic)} Questions",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TopicTitle",
        parent=styles["Title"],
        fontSize=config.topic_pdfs.topic_title_font_size,
        leading=config.topic_pdfs.topic_title_font_size + 5,
        spaceAfter=18,
    )
    section_style = ParagraphStyle(
        "TopicSection",
        parent=styles["Heading2"],
        fontSize=config.topic_pdfs.section_heading_font_size,
        leading=config.topic_pdfs.section_heading_font_size + 4,
        textColor=colors.HexColor("#1F3A5F"),
        spaceBefore=10,
        spaceAfter=8,
    )
    caption_style = ParagraphStyle(
        "QuestionCaption",
        parent=styles["Normal"],
        fontSize=config.topic_pdfs.caption_font_size,
        leading=config.topic_pdfs.caption_font_size + 3,
        textColor=colors.HexColor("#333333"),
        spaceAfter=4,
    )
    link_style = ParagraphStyle(
        "MarkSchemeLink",
        parent=styles["Normal"],
        fontSize=config.topic_pdfs.caption_font_size,
        leading=config.topic_pdfs.caption_font_size + 3,
        textColor=colors.HexColor("#1F3A5F"),
        spaceBefore=3,
        spaceAfter=5,
    )
    path_style = ParagraphStyle(
        "MarkSchemePath",
        parent=styles["Normal"],
        fontSize=max(6, config.topic_pdfs.caption_font_size - 1),
        leading=max(8, config.topic_pdfs.caption_font_size + 2),
        textColor=colors.HexColor("#666666"),
        spaceAfter=4,
    )

    story: list[Any] = [Paragraph(_topic_title(topic), title_style)]
    usable_width = min(doc.width, config.topic_pdfs.image_max_width)
    usable_height = max(72, doc.height - 120)
    included = 0
    mark_scheme_link_count = 0
    missing_mark_scheme_link_count = 0

    for difficulty in SECTION_ORDER:
        section_questions = _sorted_questions(question for question in questions if question.difficulty == difficulty)
        if not section_questions:
            continue
        for question in section_questions:
            try:
                with PILImage.open(question.screenshot_path) as image:
                    width_px, height_px = image.size
            except Exception:
                review_items.append(_review_item_from_question(question, "topic_pdf_bad_image"))
                continue
            if width_px <= 0 or height_px <= 0:
                review_items.append(_review_item_from_question(question, "topic_pdf_bad_image"))
                continue
            scale = min(usable_width / width_px, usable_height / height_px, 1.0)
            draw_width = width_px * scale
            draw_height = height_px * scale
            caption = _caption(question)
            question_anchor = _pdf_anchor_name("question", topic, difficulty, question, included)
            mark_scheme_anchor = _pdf_anchor_name("markscheme", topic, difficulty, question, included)
            if included:
                story.append(PageBreak())
            story.extend(
                [
                    Bookmark(question_anchor),
                    Paragraph(DIFFICULTY_SECTIONS[difficulty], section_style),
                ]
            )
            story.extend([
                Paragraph(caption, caption_style),
                Image(str(question.screenshot_path), width=draw_width, height=draw_height),
            ])
            if config.topic_pdfs.embed_mark_schemes:
                mark_scheme_size = _image_size(question.markscheme_image_path, PILImage) if question.markscheme_image_path else None
                if mark_scheme_size:
                    story.extend(
                        [
                            Spacer(1, 8),
                            InternalLink("Go to mark scheme", mark_scheme_anchor, link_style),
                        ]
                    )
                    story.append(PageBreak())
                    mark_width_px, mark_height_px = mark_scheme_size
                    mark_scale = min(doc.width / mark_width_px, max(72, doc.height - 96) / mark_height_px, 1.0)
                    story.extend(
                        [
                            Bookmark(mark_scheme_anchor),
                            Paragraph(f"Mark scheme | {caption}", caption_style),
                            InternalLink("Back to question", question_anchor, link_style),
                            Spacer(1, 8),
                            Image(
                                str(question.markscheme_image_path),
                                width=mark_width_px * mark_scale,
                                height=mark_height_px * mark_scale,
                            ),
                            Spacer(1, 12),
                        ]
                    )
                    mark_scheme_link_count += 1
                else:
                    story.append(Paragraph("Mark scheme image unavailable", path_style))
                    missing_mark_scheme_link_count += 1
                    if question.markscheme_image_raw:
                        review_items.append(_review_item_from_question(question, "topic_pdf_bad_markscheme_image"))
            story.append(Spacer(1, 12))
            included += 1

    if included == 0:
        return TopicPDFWriteResult(
            wrote_pdf=False,
            mark_scheme_link_count=mark_scheme_link_count,
            missing_mark_scheme_link_count=missing_mark_scheme_link_count,
        )
    doc.build(story)
    return TopicPDFWriteResult(
        wrote_pdf=True,
        mark_scheme_link_count=mark_scheme_link_count,
        missing_mark_scheme_link_count=missing_mark_scheme_link_count,
    )


def _sorted_questions(questions: Iterable[TopicPDFQuestion]) -> list[TopicPDFQuestion]:
    return sorted(
        questions,
        key=lambda question: (
            question.subtopic,
            question.paper_name,
            _question_sort_key(question.question_number),
        ),
    )


def _caption(question: TopicPDFQuestion) -> str:
    pieces = [
        question.paper_name or "unknown paper",
        f"Q{question.question_number}" if question.question_number else "unknown question",
    ]
    if question.subtopic:
        pieces.append(question.subtopic)
    if question.marks_if_available is not None:
        pieces.append(f"{question.marks_if_available} marks")
    return " | ".join(_escape_xml(piece) for piece in pieces)


def _question_sort_key(question_number: str) -> tuple[int, str]:
    match = re.search(r"\d+", question_number)
    if not match:
        return (9999, question_number)
    return (int(match.group(0)), question_number)


def _review_item(record: Mapping[str, Any], issue_type: str) -> ReviewItem:
    return ReviewItem(
        paper_name=str(record.get("paper_name") or ""),
        question_number=str(record.get("question_number") or ""),
        issue_type=issue_type,
        message=_review_message(issue_type),
        source_pdf=str(record.get("source_pdf") or ""),
        page_numbers=_page_numbers(record.get("page_numbers")) or [],
    )


def _review_item_from_question(question: TopicPDFQuestion, issue_type: str) -> ReviewItem:
    return ReviewItem(
        paper_name=question.paper_name,
        question_number=question.question_number,
        issue_type=issue_type,
        message=_review_message(issue_type),
        source_pdf=question.source_pdf,
        page_numbers=question.page_numbers or [],
    )


def _review_message(issue_type: str) -> str:
    messages = {
        "topic_pdf_missing_image": "Topic PDF export skipped this record because the question image path was missing or unreadable.",
        "topic_pdf_missing_topic": "Topic PDF export skipped this record because the topic label was missing.",
        "topic_pdf_missing_difficulty": "Topic PDF export skipped this record because the difficulty label was missing or unsupported.",
        "topic_pdf_manual_excluded": "Topic PDF export skipped this record because manual review marked it unusable or the crop as bad.",
        "topic_pdf_bad_image": "Topic PDF export skipped this record because the image could not be opened.",
        "topic_pdf_bad_markscheme_image": "Topic PDF export embedded the question but could not open the mark scheme image.",
    }
    return messages.get(issue_type, "Topic PDF export skipped this record.")


def _resolve_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return Path.cwd() / path


def _image_size(path: Path | None, pil_image_module: Any) -> tuple[int, int] | None:
    if path is None or not path.exists():
        return None
    try:
        with pil_image_module.open(path) as image:
            width_px, height_px = image.size
    except Exception:
        return None
    if width_px <= 0 or height_px <= 0:
        return None
    return (width_px, height_px)


def _pdf_anchor_name(prefix: str, topic: str, difficulty: str, question: TopicPDFQuestion, index: int) -> str:
    raw = "|".join(
        [
            prefix,
            topic,
            difficulty,
            question.paper_name,
            question.question_number,
            str(index),
        ]
    )
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", raw).strip("_") or f"{prefix}_{index}"


def _optional_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _page_numbers(value: Any) -> list[int]:
    if isinstance(value, list):
        numbers: list[int] = []
        for item in value:
            number = _optional_int(item)
            if number is not None:
                numbers.append(number)
        return numbers
    if isinstance(value, str):
        numbers = []
        for item in value.split(","):
            number = _optional_int(item.strip())
            if number is not None:
                numbers.append(number)
        return numbers
    return []


def _safe_filename(topic: str) -> str:
    filename = re.sub(r"[^A-Za-z0-9._-]+", "_", topic.strip().lower()).strip("_")
    return filename or "uncategorised"


def _topic_title(topic: str) -> str:
    return topic.replace("_", " ").title()


def _escape_xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
