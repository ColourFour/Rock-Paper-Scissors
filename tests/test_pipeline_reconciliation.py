from exam_bank.config import AppConfig
from exam_bank.models import QuestionRecord
from exam_bank.pipeline import (
    _assess_text_fidelity,
    _derive_scope_quality_status,
    _derive_topic_trust_status,
    _paper_total_check,
    _polluted_pass_signal_groups,
    _reconcile_paper_topics,
    _refine_validation_status,
    _should_trigger_paper_total_rescan,
)


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


def test_refine_validation_status_escalates_low_confidence_polluted_pass() -> None:
    status, flags = _refine_validation_status(
        base_status="review",
        base_validation_flags=[],
        mapping_status="pass",
        mapping_failure_reason="",
        crop_uncertain=True,
        extraction_quality_flags=["likely_needs_visual_review", "broken_fraction_structure"],
        review_flags=["low_confidence_question_crop", "weak_question_text"],
        question_structure_detected={"contamination_indicators": {"signal_score": 2}},
    )

    assert status == "fail"
    assert "polluted_pass_requires_review" in flags


def test_refine_validation_status_keeps_clean_high_confidence_pass_stable() -> None:
    status, flags = _refine_validation_status(
        base_status="review",
        base_validation_flags=[],
        mapping_status="pass",
        mapping_failure_reason="",
        crop_uncertain=False,
        extraction_quality_flags=[],
        review_flags=["question_start_uncertain"],
        question_structure_detected={"contamination_indicators": {"signal_score": 0}},
    )

    assert status == "review"
    assert flags == []


def test_refine_validation_status_does_not_blur_true_fail_into_polluted_pass_logic() -> None:
    status, flags = _refine_validation_status(
        base_status="fail",
        base_validation_flags=["question_scope_contaminated"],
        mapping_status="fail",
        mapping_failure_reason="question_scope_contaminated",
        crop_uncertain=True,
        extraction_quality_flags=["likely_needs_visual_review"],
        review_flags=["low_confidence_question_crop", "question_scope_contaminated"],
        question_structure_detected={"contamination_indicators": {"signal_score": 7}},
    )

    assert status == "fail"
    assert "question_scope_contaminated" in flags
    assert "polluted_pass_requires_review" not in flags


def test_refine_validation_status_escalates_structural_mapping_failures() -> None:
    status, flags = _refine_validation_status(
        base_status="review",
        base_validation_flags=[],
        mapping_status="fail",
        mapping_failure_reason="question_subparts_incomplete",
        crop_uncertain=False,
        extraction_quality_flags=[],
        review_flags=[],
        question_structure_detected={"contamination_indicators": {"signal_score": 0}},
    )

    assert status == "fail"
    assert "question_subparts_incomplete" in flags


def test_assess_text_fidelity_marks_degraded_math_text_even_when_mapping_can_pass() -> None:
    status, flags = _assess_text_fidelity(
        question_text=(
            "5 (a) The complex number u is given by\n"
            "u = (coscos^{1}_{7}_{1}_{7}rr+-isinisin^{1}_{7}_{1}_{7}rr)^{4}.\n"
            "(b) Describe the transformation. [2]"
        ),
        extraction_quality_flags=["heavy_math_density"],
        review_flags=["ocr_merged_sparse_lower_region", "weak_question_text"],
        validation_flags=[],
        question_structure_detected={"missing_internal_subparts": [], "impossible_subpart_sequence_detected": False},
        mapping_failure_reason="",
        text_source_profile="hybrid",
    )

    assert status == "degraded"
    assert "ocr_math_notation_degraded" in flags


def test_assess_text_fidelity_marks_missing_visible_structure_as_unusable() -> None:
    status, flags = _assess_text_fidelity(
        question_text="1 ... (a) ... [3]",
        extraction_quality_flags=[],
        review_flags=[],
        validation_flags=["question_subparts_incomplete"],
        question_structure_detected={"missing_internal_subparts": [], "impossible_subpart_sequence_detected": False},
        mapping_failure_reason="question_subparts_incomplete",
        text_source_profile="native_pdf",
    )

    assert status == "unusable"
    assert "missing_visible_structure_in_text" in flags


def test_assess_text_fidelity_keeps_clean_text_clean() -> None:
    status, flags = _assess_text_fidelity(
        question_text="2 Find the coordinates of A. [1]\n(b) Find the equation of the new curve. [3]",
        extraction_quality_flags=[],
        review_flags=[],
        validation_flags=[],
        question_structure_detected={"missing_internal_subparts": [], "impossible_subpart_sequence_detected": False},
        mapping_failure_reason="",
        text_source_profile="native_pdf",
    )

    assert status == "clean"
    assert flags == []


def test_topic_trust_downgrades_when_text_is_degraded_even_if_otherwise_usable() -> None:
    status = _derive_topic_trust_status(
        topic_confidence="high",
        topic_uncertain=False,
        text_fidelity_status="degraded",
        validation_status="review",
        scope_quality_status="clean",
    )

    assert status == "degraded_text"


def test_scope_quality_stays_failed_for_true_contamination_case() -> None:
    status = _derive_scope_quality_status(
        validation_flags=["question_scope_contaminated"],
        review_flags=["possible_next_question_contamination"],
        question_structure_detected={"contamination_detected": True},
    )

    assert status == "fail"


def test_polluted_pass_signal_groups_collapse_overlap_into_named_clusters() -> None:
    groups = _polluted_pass_signal_groups(
        crop_uncertain=True,
        base_validation_flags=["weak_question_anchor", "likely_truncated_question_crop"],
        extraction_quality_flags=["likely_needs_visual_review", "broken_fraction_structure"],
        review_flags=["low_confidence_question_crop", "crop_reaches_page_margin", "weak_question_text"],
        question_structure_detected={"contamination_detected": False, "contamination_indicators": {"signal_score": 2}},
    )

    assert groups == {
        "crop_risk",
        "low_quality_text",
        "pollution_signals",
        "question_validation_risk",
    }


def test_paper_total_mismatch_triggers_rescan() -> None:
    records = [
        _record(question_number="1", paper_family="P1", topic="algebra", topic_confidence="high", combined_question_text="Q1"),
        _record(question_number="2", paper_family="P1", topic="algebra", topic_confidence="high", combined_question_text="Q2"),
    ]
    records[0].question_marks_total = 30
    records[1].question_marks_total = 40

    total_check = _paper_total_check(records, component="12", paper_family="P1")

    assert total_check["expected_total"] == 75
    assert total_check["detected_total"] == 70
    assert total_check["status"] == "mismatch"
    assert _should_trigger_paper_total_rescan(total_check) is True


def test_paper_total_match_does_not_trigger_rescan() -> None:
    records = [
        _record(question_number="1", paper_family="P5", topic="statistics", topic_confidence="high", combined_question_text="Q1"),
        _record(question_number="2", paper_family="P5", topic="statistics", topic_confidence="high", combined_question_text="Q2"),
    ]
    records[0].question_marks_total = 20
    records[1].question_marks_total = 30

    total_check = _paper_total_check(records, component="53", paper_family="P5")

    assert total_check["expected_total"] == 50
    assert total_check["detected_total"] == 50
    assert total_check["status"] == "matched"
    assert _should_trigger_paper_total_rescan(total_check) is False
