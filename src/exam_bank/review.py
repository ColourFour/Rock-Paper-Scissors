from __future__ import annotations

import csv
from pathlib import Path

from .config import AppConfig
from .models import QuestionRecord, ReviewItem


def review_items_from_records(records: list[QuestionRecord]) -> list[ReviewItem]:
    items: list[ReviewItem] = []
    for record in records:
        for flag in record.review_flags:
            items.append(
                ReviewItem(
                    paper_name=record.paper_name,
                    question_number=record.question_number,
                    issue_type=flag,
                    message=_message_for_flag(flag),
                    source_pdf=record.source_pdf,
                    page_numbers=record.page_numbers,
                    crop_uncertain=record.crop_uncertain or flag == "crop_uncertain",
                    crop_debug_paths=record.crop_debug_paths,
                )
            )
    return items


def write_review_file(records: list[QuestionRecord], config: AppConfig, basename: str | None = None) -> Path:
    config.ensure_output_dirs()
    review_name = f"{basename}_review.csv" if basename else config.naming.review_name
    output_path = config.output.review_dir / review_name
    items = review_items_from_records(records)
    rows = [item.to_dict() for item in items]
    if not rows:
        rows = [
            {
                "paper_name": "",
                "question_number": "",
                "issue_type": "",
                "message": "",
                "source_pdf": "",
                "page_numbers": "",
                "crop_uncertain": "",
                "crop_debug_paths": "",
            }
        ]

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return output_path


def append_review_items(items: list[ReviewItem], config: AppConfig, basename: str | None = None) -> Path:
    config.ensure_output_dirs()
    review_name = f"{basename}_review.csv" if basename else config.naming.review_name
    output_path = config.output.review_dir / review_name
    fieldnames = [
        "paper_name",
        "question_number",
        "issue_type",
        "message",
        "source_pdf",
        "page_numbers",
        "crop_uncertain",
        "crop_debug_paths",
    ]
    file_has_rows = output_path.exists() and output_path.stat().st_size > 0
    with output_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if not file_has_rows:
            writer.writeheader()
        writer.writerows(item.to_dict() for item in items)
    return output_path


def _message_for_flag(flag: str) -> str:
    messages = {
        "unmatched_mark_scheme": "No matching mark scheme PDF was found.",
        "unmatched_answer": "A matching mark scheme was found, but no answer block matched this question number.",
        "no_question_boundaries_detected": "Question boundaries could not be detected; all extracted text was kept as one review item.",
        "short_question_text": "Detected question text is unusually short.",
        "topic_uncertain": "Topic label should be checked before trusting the exported metadata.",
        "topic_uncertain_low_quality_text": "Topic classification used weak, short, or OCR-contaminated extracted text.",
        "topic_uncertain_mixed_major_topics": "Multiple major topics were plausible for this grouped question.",
        "topic_uncertain_no_rule_match": "No configured method/object rule matched the extracted question text.",
        "paper_family_uncertain": "The mathematics does not uniquely identify one Cambridge 9709 paper family.",
        "part_topic_uncertain": "At least one detected subpart has a low-confidence topic label.",
        "uncertain_topic_no_keyword_match": "Local topic classifier did not find a strong keyword match.",
        "uncertain_topic_tie": "Local topic classifier found multiple topics with the same score.",
        "marks_missing_for_difficulty": "Difficulty was inferred without an extracted marks value.",
        "low_classification_confidence": "Local classification confidence is below the configured threshold.",
        "ocr_question_text": "Question text came from OCR fallback and may need checking.",
        "question_sequence_gap": "Detected question numbers skipped at least one expected number.",
        "question_start_uncertain": "The layout anchor for this question had a lower confidence score.",
        "question_start_mismatch": "The first accepted block does not match the chosen question anchor.",
        "possible_next_question_contamination": "Accepted text appears to include a later top-level question anchor.",
        "header_footer_contamination": "Accepted text appears to include page header or footer content.",
        "answer_space_heavy": "The region may contain too much answer-space artifact relative to prompt text.",
        "crop_uncertain": "The automatic crop was produced, but the crop boundary should be inspected.",
        "crop_fallback_used": "The renderer could not find a strong prompt region and used a fallback crop.",
        "crop_reaches_page_margin": "The crop reaches close to the page margin and may include extra material.",
        "crop_split_prompt_regions": "The renderer split this question into separate prompt regions to avoid answer space.",
        "topic_pdf_missing_image": "Topic PDF export skipped this record because the question image path was missing or unreadable.",
        "topic_pdf_missing_topic": "Topic PDF export skipped this record because the topic label was missing.",
        "topic_pdf_missing_difficulty": "Topic PDF export skipped this record because the difficulty label was missing or unsupported.",
        "topic_pdf_bad_image": "Topic PDF export skipped this record because the image could not be opened.",
    }
    return messages.get(flag, "Review this item before trusting the exported metadata.")
