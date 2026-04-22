from exam_bank.config import AppConfig
from exam_bank.models import QuestionRecord
from exam_bank.pipeline import _reconcile_paper_topics


def _record(
    *,
    question_number: str,
    paper_family: str,
    topic: str,
    topic_confidence: str,
    combined_question_text: str,
    topic_uncertain: bool = False,
    topic_alternatives: list[str] | None = None,
    review_flags: list[str] | None = None,
    confidence: float = 0.42,
    body_text_normalized: str | None = None,
    extraction_quality_score: float = 0.9,
    extraction_quality_flags: list[str] | None = None,
    topic_evidence_details: dict | None = None,
    secondary_topics: list[str] | None = None,
) -> QuestionRecord:
    return QuestionRecord(
        source_pdf="input/question_papers/test.pdf",
        paper_name="test_paper",
        question_number=question_number,
        full_question_label=question_number,
        screenshot_path="output/images/test.png",
        combined_question_text=combined_question_text,
        body_text_raw=combined_question_text,
        body_text_normalized=body_text_normalized or combined_question_text,
        math_lines=[],
        diagram_text=[],
        extraction_quality_score=extraction_quality_score,
        extraction_quality_flags=extraction_quality_flags or [],
        part_texts=[],
        answer_text="",
        paper_family=paper_family,
        source_paper_family=paper_family,
        inferred_paper_family=paper_family,
        paper_family_confidence="high",
        topic=topic,
        subtopic="general",
        topic_confidence=topic_confidence,
        topic_evidence="",
        secondary_topics=secondary_topics or [],
        topic_uncertain=topic_uncertain,
        difficulty="average",
        difficulty_confidence="medium",
        difficulty_evidence="",
        difficulty_uncertain=False,
        marks=4,
        marks_if_available=4,
        page_numbers=[1],
        review_flags=review_flags or [],
        confidence=confidence,
        topic_alternatives=topic_alternatives or [],
        topic_evidence_details=topic_evidence_details or {},
        question_level_paper_family=paper_family,
        question_level_topic=topic,
        question_level_subtopic="general",
        part_level_topics=[],
    )


def test_reconciliation_reranks_weak_label_to_missing_supported_topic() -> None:
    records = [
        _record(
            question_number="1",
            paper_family="P1",
            topic="binomial_expansion",
            topic_confidence="high",
            combined_question_text="Expand (1 + x)^5. [3]",
            confidence=0.88,
        ),
        _record(
            question_number="2",
            paper_family="P1",
            topic="trigonometry",
            topic_confidence="high",
            combined_question_text="Solve the equation sin x = 1/2. [3]",
            confidence=0.88,
        ),
        _record(
            question_number="3",
            paper_family="P1",
            topic="algebra",
            topic_confidence="low",
            topic_uncertain=True,
            combined_question_text="An arithmetic progression has first term 3 and common difference 5. Find the sum of the first 20 terms. [4]",
            topic_alternatives=["P1:series_and_sequences:general"],
            review_flags=["low_classification_confidence", "weak_markscheme_signal"],
            confidence=0.35,
        ),
    ]

    _reconcile_paper_topics(records, AppConfig())

    assert records[2].topic == "series_and_sequences"
    assert records[2].question_level_topic == "series_and_sequences"
    assert records[2].reconciliation_changed_topic is True
    assert "paper_level_topic_reconciled" in records[2].review_flags


def test_reconciliation_does_not_override_high_confidence_local_label() -> None:
    records = [
        _record(
            question_number="1",
            paper_family="P1",
            topic="binomial_expansion",
            topic_confidence="high",
            combined_question_text="Find the coefficient of x^2 in the expansion of (1 + 2x)^6. [3]",
            topic_alternatives=["P1:series_and_sequences:general"],
            review_flags=[],
            confidence=0.88,
        ),
        _record(
            question_number="2",
            paper_family="P1",
            topic="trigonometry",
            topic_confidence="high",
            combined_question_text="Solve tan x = 1 for 0 < x < 180. [2]",
            confidence=0.88,
        ),
    ]

    _reconcile_paper_topics(records, AppConfig())

    assert records[0].topic == "binomial_expansion"
    assert records[0].reconciliation_changed_topic is False


def test_paper_repair_missing_topic_pressure_repairs_weak_sequence_label() -> None:
    records = [
        _record(
            question_number="1",
            paper_family="P1",
            topic="trigonometry",
            topic_confidence="high",
            combined_question_text="Solve sin x = 1/2. [3]",
            confidence=0.88,
        ),
        _record(
            question_number="2",
            paper_family="P1",
            topic="binomial_expansion",
            topic_confidence="high",
            combined_question_text="Find the coefficient of x^2. [3]",
            confidence=0.88,
        ),
        _record(
            question_number="3",
            paper_family="P1",
            topic="quadratics",
            topic_confidence="low",
            topic_uncertain=True,
            combined_question_text="Find p. [5]",
            body_text_normalized="An arithmetic progression has common difference p. A geometric progression has common ratio p. Find the sum to infinity.",
            topic_alternatives=["P1:series_and_sequences:general"],
            review_flags=["low_classification_confidence", "object_cue_conflict_with_method_scoring"],
            topic_evidence_details={
                "object_cue_primary_topic": "series_and_sequences",
                "object_cue_topic_scores": {"series_and_sequences": 18.0},
                "topic_score_breakdown": {
                    "quadratics": {"final_score": 11.0, "object_protection_penalty": -6.5},
                    "series_and_sequences": {"final_score": 8.5},
                },
            },
        ),
    ]

    _reconcile_paper_topics(records, AppConfig())

    assert records[2].topic == "series_and_sequences"
    assert records[2].paper_repair_changed_topic is True
    assert records[2].paper_repair_to_topic == "series_and_sequences"
    assert "series_and_sequences" in records[2].paper_repair_missing_topics


def test_paper_repair_does_not_override_strong_local_label() -> None:
    records = [
        _record(
            question_number="1",
            paper_family="P1",
            topic="trigonometry",
            topic_confidence="high",
            combined_question_text="Solve tan x = 1 for 0 < x < 180. [2]",
            body_text_normalized="Solve tan x = 1 for 0 < x < 180.",
            confidence=0.91,
            topic_evidence_details={
                "object_cue_primary_topic": "trigonometry",
                "object_cue_topic_scores": {"trigonometry": 12.0},
                "topic_score_breakdown": {
                    "trigonometry": {"final_score": 22.0},
                    "series_and_sequences": {"final_score": 4.0},
                },
            },
        ),
        _record(
            question_number="2",
            paper_family="P1",
            topic="functions",
            topic_confidence="high",
            combined_question_text="Find the inverse function. [4]",
            confidence=0.9,
        ),
    ]

    _reconcile_paper_topics(records, AppConfig())

    assert records[0].topic == "trigonometry"
    assert records[0].paper_repair_considered is False
    assert records[0].paper_repair_changed_topic is False


def test_strong_local_win_with_weak_extraction_is_not_considered() -> None:
    records = [
        _record(
            question_number="1",
            paper_family="P1",
            topic="binomial_expansion",
            topic_confidence="high",
            combined_question_text="Find the coefficient of x^2 in the expansion of (1 + 2x)^6. [3]",
            extraction_quality_score=0.42,
            extraction_quality_flags=["likely_needs_visual_review"],
            review_flags=["likely_needs_visual_review"],
            confidence=0.9,
            topic_evidence_details={
                "object_cue_primary_topic": "binomial_expansion",
                "object_cue_topic_scores": {"binomial_expansion": 14.0},
                "topic_score_breakdown": {
                    "binomial_expansion": {"final_score": 24.0},
                    "quadratics": {"final_score": 5.0},
                },
            },
        )
    ]

    _reconcile_paper_topics(records, AppConfig())

    assert records[0].paper_repair_considered is False
    assert records[0].paper_repair_changed_topic is False


def test_weak_extraction_alone_is_insufficient_for_consideration() -> None:
    records = [
        _record(
            question_number="1",
            paper_family="P1",
            topic="trigonometry",
            topic_confidence="high",
            combined_question_text="Solve tan x = 1 for 0 < x < 180. [2]",
            extraction_quality_score=0.5,
            extraction_quality_flags=["likely_needs_visual_review"],
            review_flags=["likely_needs_visual_review"],
            confidence=0.9,
            topic_evidence_details={
                "object_cue_primary_topic": "trigonometry",
                "object_cue_topic_scores": {"trigonometry": 11.0},
                "topic_score_breakdown": {
                    "trigonometry": {"final_score": 21.0},
                    "functions": {"final_score": 3.0},
                },
            },
        )
    ]

    _reconcile_paper_topics(records, AppConfig())

    assert records[0].paper_repair_considered is False


def test_weak_with_meaningful_alternative_is_considered() -> None:
    records = [
        _record(
            question_number="1",
            paper_family="P1",
            topic="quadratics",
            topic_confidence="low",
            topic_uncertain=True,
            combined_question_text="Find p. [4]",
            body_text_normalized="An arithmetic progression has common difference p and the sum to infinity is required from a geometric progression.",
            topic_alternatives=["P1:series_and_sequences:general"],
            review_flags=["low_classification_confidence"],
            topic_evidence_details={
                "object_cue_primary_topic": "series_and_sequences",
                "object_cue_topic_scores": {"series_and_sequences": 15.0},
                "topic_score_breakdown": {
                    "quadratics": {"final_score": 9.0},
                    "series_and_sequences": {"final_score": 7.8},
                },
            },
        )
    ]

    _reconcile_paper_topics(records, AppConfig())

    assert records[0].paper_repair_considered is True


def test_object_cue_conflict_still_qualifies_for_consideration() -> None:
    records = [
        _record(
            question_number="1",
            paper_family="P5",
            topic="probability",
            topic_confidence="medium",
            combined_question_text="Let X be a random variable. [4]",
            topic_alternatives=["P5:probability_distributions:general"],
            review_flags=["object_cue_conflict_with_method_scoring"],
            topic_evidence_details={
                "object_cue_primary_topic": "probability_distributions",
                "object_cue_topic_scores": {"probability_distributions": 12.0, "probability": 4.0},
                "object_cue_conflict_with_method_scoring": True,
                "topic_score_breakdown": {
                    "probability": {"final_score": 8.0},
                    "probability_distributions": {"final_score": 7.1},
                },
            },
        )
    ]

    _reconcile_paper_topics(records, AppConfig())

    assert records[0].paper_repair_considered is True


def test_only_current_topic_candidate_is_not_considered() -> None:
    records = [
        _record(
            question_number="1",
            paper_family="P1",
            topic="algebra",
            topic_confidence="low",
            topic_uncertain=True,
            combined_question_text="Simplify the expression. [2]",
            review_flags=["low_classification_confidence", "weak_question_text"],
            topic_evidence_details={
                "topic_score_breakdown": {
                    "algebra": {"final_score": 3.0},
                }
            },
        )
    ]

    _reconcile_paper_topics(records, AppConfig())

    assert records[0].paper_repair_considered is False
    assert records[0].paper_repair_candidates == []


def test_missing_topic_pressure_alone_is_insufficient() -> None:
    records = [
        _record(
            question_number="1",
            paper_family="P1",
            topic="trigonometry",
            topic_confidence="high",
            combined_question_text="Solve cos x = 0. [2]",
            confidence=0.88,
        ),
        _record(
            question_number="2",
            paper_family="P1",
            topic="algebra",
            topic_confidence="low",
            topic_uncertain=True,
            combined_question_text="Simplify the expression. [2]",
            review_flags=["low_classification_confidence", "weak_question_text"],
            topic_evidence_details={"topic_score_breakdown": {"algebra": {"final_score": 3.0}}},
        ),
    ]

    _reconcile_paper_topics(records, AppConfig())

    assert records[1].topic == "algebra"
    assert records[1].paper_repair_changed_topic is False


def test_object_cue_supported_alternative_is_repaired_when_missing() -> None:
    records = [
        _record(
            question_number="1",
            paper_family="P5",
            topic="probability",
            topic_confidence="low",
            topic_uncertain=True,
            combined_question_text="Let X be a random variable. [4]",
            body_text_normalized="A random variable X takes values 0, 1, 2, 3 with probabilities shown in the table.",
            topic_alternatives=["P5:probability_distributions:general"],
            review_flags=["low_classification_confidence", "object_cue_conflict_with_method_scoring"],
            topic_evidence_details={
                "object_cue_primary_topic": "probability_distributions",
                "object_cue_topic_scores": {"probability_distributions": 16.0, "probability": 3.0},
                "topic_score_breakdown": {
                    "probability": {"final_score": 7.0},
                    "probability_distributions": {"final_score": 6.4},
                },
            },
        ),
        _record(
            question_number="2",
            paper_family="P5",
            topic="normal_distribution",
            topic_confidence="high",
            combined_question_text="The variable is normally distributed. [4]",
            confidence=0.9,
        ),
    ]

    _reconcile_paper_topics(records, AppConfig())

    assert records[0].topic == "probability_distributions"
    assert records[0].paper_repair_changed_topic is True


def test_corrupted_text_needs_local_support_for_repair() -> None:
    records = [
        _record(
            question_number="1",
            paper_family="P1",
            topic="algebra",
            topic_confidence="low",
            topic_uncertain=True,
            combined_question_text="bad ??? cropped text [2]",
            extraction_quality_score=0.42,
            extraction_quality_flags=["likely_needs_visual_review"],
            review_flags=["low_classification_confidence", "weak_question_text", "likely_needs_visual_review"],
            topic_evidence_details={
                "topic_score_breakdown": {
                    "algebra": {"final_score": 2.0},
                }
            },
        ),
        _record(
            question_number="2",
            paper_family="P1",
            topic="trigonometry",
            topic_confidence="high",
            combined_question_text="Solve tan x = 1. [2]",
            confidence=0.88,
        ),
    ]

    _reconcile_paper_topics(records, AppConfig())

    assert records[0].topic == "algebra"
    assert records[0].paper_repair_considered is False
    assert records[0].paper_repair_changed_topic is False
