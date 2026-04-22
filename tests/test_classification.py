from exam_bank.classification import classify_question, classify_question_parts, infer_source_paper_code, infer_source_paper_family
from exam_bank.config import AppConfig


def test_default_topic_taxonomy_uses_controlled_labels() -> None:
    config = AppConfig()

    assert config.paper_families == ["P1", "P2", "P3", "P4", "P5", "P6", "unknown"]
    assert "algebra" in config.paper_family_taxonomy["P1"]
    assert "series_and_sequences" in config.paper_family_taxonomy["P1"]
    assert "complex_numbers" in config.paper_family_taxonomy["P3"]
    assert "kinematics_graphs" in config.paper_family_taxonomy["P4"]
    assert "measures_of_central_tendency_and_dispersion" in config.paper_family_taxonomy["P5"]
    assert "partial_fractions" not in config.paper_family_taxonomy["P1"]
    assert "poisson_distribution" not in config.paper_family_taxonomy["P5"]
    assert "advanced algebra" not in config.topic_taxonomy
    assert config.difficulty_labels == ["easy", "average", "difficult"]


def test_source_paper_code_and_family_are_inferred_from_filename() -> None:
    assert infer_source_paper_code("9709_s21_qp_12.pdf") == ("12", "high")
    assert infer_source_paper_family("March 2019_qp_32.pdf") == ("P3", "high")


def test_classifies_binomial_coefficient_as_binomial_expansion() -> None:
    result = classify_question(
        "Find the coefficient of x^2 in the expansion of (1 + 2x)^6. [3]",
        marks=3,
        config=AppConfig(),
        source_name="9709_s21_qp_12.pdf",
    )

    assert result.paper_family == "P1"
    assert result.topic == "binomial_expansion"
    assert result.subtopic == "general"
    assert result.topic_confidence in {"medium", "high"}


def test_classifies_ap_question_as_series_and_sequences() -> None:
    result = classify_question(
        "An arithmetic progression has first term 3 and common difference 5. Find the sum of the first 20 terms. [4]",
        marks=4,
        config=AppConfig(),
        source_name="9709_s21_qp_12.pdf",
    )

    assert result.paper_family == "P1"
    assert result.topic == "series_and_sequences"


def test_classifies_product_integral_as_integration() -> None:
    result = classify_question(
        "Integrate x sec^2 x with respect to x. [5]",
        marks=5,
        config=AppConfig(),
        source_name="9709_s21_qp_32.pdf",
    )

    assert result.paper_family == "P3"
    assert result.topic == "integration"
    assert result.subtopic == "general"
    assert result.topic_confidence in {"medium", "high"}


def test_classifies_argand_question_as_complex_numbers() -> None:
    result = classify_question(
        "Sketch on an Argand diagram the locus of the complex number z such that |z - 2i| = 3. [4]",
        marks=4,
        config=AppConfig(),
        source_name="9709_s21_qp_32.pdf",
    )

    assert result.paper_family == "P3"
    assert result.topic == "complex_numbers"
    assert result.subtopic == "general"
    assert "complex-number objects" in result.topic_evidence


def test_marks_mixed_topic_question_with_secondary_topic() -> None:
    result = classify_question(
        (
            "Express the rational function in partial fractions. "
            "Hence integrate the result with respect to x. [8]"
        ),
        marks=8,
        config=AppConfig(),
        source_name="9709_s21_qp_32.pdf",
    )

    assert result.paper_family == "P3"
    assert result.topic == "partial_fractions"
    assert "integration" in result.secondary_topics
    assert "mixed_topic_possible" in result.review_flags


def test_classifies_detected_parts_separately() -> None:
    parts = classify_question_parts(
        (
            "9(a) Express the rational function in partial fractions. [4]\n"
            "(b) Hence expand the expression with a negative power in ascending powers of x. [4]"
        ),
        question_number="9",
        config=AppConfig(),
        source_name="9709_s21_qp_32.pdf",
    )

    assert [part["part_label"] for part in parts] == ["9(a)", "9(b)"]
    assert parts[0]["paper_family"] == "P3"
    assert parts[0]["topic"] == "partial_fractions"
    assert parts[1]["paper_family"] == "P3"
    assert parts[1]["topic"] == "binomial_expansion"


def test_hence_part_continuity_keeps_same_topic_when_signal_is_weak() -> None:
    parts = classify_question_parts(
        (
            "5(a) Expand (1 + x)^5. [2]\n"
            "(b) Hence find the coefficient of x^2 in a related expression. [2]"
        ),
        question_number="5",
        config=AppConfig(),
        source_name="9709_s21_qp_12.pdf",
    )

    assert parts[0]["topic"] == "binomial_expansion"
    assert parts[1]["topic"] == "binomial_expansion"
    assert "part_topic_continuity_applied" in parts[1]["review_flags"] or parts[1]["topic_confidence"] in {"medium", "high"}


def test_source_filename_restricts_topic_bank() -> None:
    result = classify_question(
        "A particle moves with constant acceleration. Find the tension in the string over a pulley. [6]",
        marks=6,
        config=AppConfig(),
        source_name="9709_s21_qp_42.pdf",
    )

    assert result.source_paper_family == "P4"
    assert result.paper_family == "P4"
    assert result.topic == "connected_particles"


def test_final_topic_candidates_are_restricted_before_scoring() -> None:
    result = classify_question(
        "Differentiate y = x^2 and find dy/dx. [3]",
        marks=3,
        config=AppConfig(),
        source_name="9709_s21_qp_42.pdf",
    )

    assert result.paper_family == "P4"
    assert result.topic in AppConfig().paper_family_taxonomy["P4"]
    assert result.topic != "differentiation"
    assert all(candidate.startswith("P4:") for candidate in result.alternative_topics)


def test_p4_graph_motion_prefers_kinematics_graphs() -> None:
    result = classify_question(
        "The velocity-time graph of a particle is shown. Find the displacement during the first 12 seconds. [4]",
        marks=4,
        config=AppConfig(),
        source_name="9709_s21_qp_42.pdf",
    )

    assert result.paper_family == "P4"
    assert result.topic == "kinematics_graphs"


def test_routine_trig_question_is_not_marked_mixed_or_too_hard() -> None:
    result = classify_question(
        "Solve the equation 4 sin x + tan x = 0 for 0 < x < 180. [3]",
        marks=3,
        config=AppConfig(),
        source_name="9709_s21_qp_12.pdf",
    )

    assert result.paper_family == "P1"
    assert result.topic == "trigonometry"
    assert "mixed_topic_possible" not in result.review_flags
    assert result.difficulty == "easy"


def test_forces_low_confidence_topic_within_known_paper_bank() -> None:
    result = classify_question(
        "A strangely worded task with little mathematical context. [2]",
        marks=2,
        config=AppConfig(),
        source_name="9709_s21_qp_52.pdf",
    )

    assert result.paper_family == "P5"
    assert result.topic in AppConfig().paper_family_taxonomy["P5"]
    assert result.topic_confidence == "low"
    assert "topic_forced_low_confidence" in result.review_flags


def test_examiner_report_method_evidence_overrides_noisy_question_text() -> None:
    result = classify_question(
        "A vector is translated in a diagram and a line is drawn. [5]",
        marks=5,
        config=AppConfig(),
        source_name="9709_s21_qp_12.pdf",
        examiner_report_text="Most candidates used elimination leading to a quadratic and then considered the discriminant.",
    )

    assert result.paper_family == "P1"
    assert result.topic == "quadratics"
    assert result.topic in AppConfig().paper_family_taxonomy["P1"]
    assert "examiner_report" in result.topic_evidence_details


def test_p5_summary_statistics_not_forced_to_normal_distribution() -> None:
    result = classify_question(
        "Find the mean and standard deviation of the distribution, using coding if appropriate. [5]",
        marks=5,
        config=AppConfig(),
        source_name="9709_s21_qp_52.pdf",
    )

    assert result.paper_family == "P5"
    assert result.topic == "measures_of_central_tendency_and_dispersion"


def test_topic_candidates_are_short_and_plausible() -> None:
    result = classify_question(
        "Find the equation of the tangent to the curve y = x^3 at the point where x = 2. [4]",
        marks=4,
        config=AppConfig(),
        source_name="9709_s21_qp_12.pdf",
    )

    assert result.topic == "differentiation"
    assert len(result.alternative_topics) <= 2


def test_missing_markscheme_and_weak_text_trigger_uncertainty_flags() -> None:
    result = classify_question(
        "weird cropped text ??? [2]",
        marks=2,
        config=AppConfig(),
        source_name="9709_s21_qp_12.pdf",
        question_ocr_text="weird cropped text ???",
    )

    assert result.topic_confidence == "low"
    assert result.topic_uncertain is True
    assert "weak_question_text" in result.review_flags
    assert "weak_markscheme_signal" in result.review_flags


def test_object_cues_keep_p1_ap_gp_question_in_series_and_sequences() -> None:
    result = classify_question(
        "Find p. [6]",
        marks=6,
        config=AppConfig(),
        source_name="9709_s21_qp_12.pdf",
        mark_scheme_text=(
            "Using the AP and GP conditions gives a quadratic equation in p. "
            "Solve the quadratic using the discriminant, then factorise and take the repeated root if valid."
        ),
        body_text_normalized=(
            "An arithmetic progression has common difference p.\n"
            "A related geometric progression has common ratio p.\n"
            "Find the value of p and the sum to infinity."
        ),
        part_texts=[
            {
                "part_label": "(a)",
                "normalized_text": "arithmetic progression common difference p",
                "raw_text": "arithmetic progression common difference p",
                "math_lines": [],
            }
        ],
        body_text_raw=(
            "An arithmetic progression has common difference p.\n"
            "A related geometric progression has common ratio p.\n"
            "Find the value of p and the sum to infinity."
        ),
    )

    assert result.paper_family == "P1"
    assert result.topic == "series_and_sequences"
    assert result.topic_evidence_details["object_cue_primary_topic"] == "series_and_sequences"
    assert "arithmetic progression" in result.topic_evidence_details["detected_object_cues"]
    assert result.topic_evidence_details["source_method_stage_top_topic"] == "quadratics"
    assert result.topic_evidence_details["object_cue_resisted_override"] is True
    assert result.topic_evidence_details["object_cue_protection_applied"] is True
    assert "quadratics" in result.topic_evidence_details["object_cue_protection_topics"]
    assert result.topic_evidence_details["topic_score_breakdown"]["series_and_sequences"]["final_score"] > result.topic_evidence_details["topic_score_breakdown"]["quadratics"]["final_score"]


def test_object_cues_keep_binomial_continuation_in_binomial_expansion() -> None:
    parts = classify_question_parts(
        "7(a) Find the expansion of (1 + 2x)^5 in ascending powers of x. [3]\n(b) Hence find the coefficient of x^2 in (1 + 2x)^5(1 - x). [2]",
        question_number="7",
        config=AppConfig(),
        source_name="9709_s21_qp_12.pdf",
        structured_part_texts=[
            {
                "part_label": "(a)",
                "normalized_text": "find the expansion of (1 + 2x)^5 in ascending powers of x",
                "raw_text": "find the expansion of (1 + 2x)^5 in ascending powers of x",
                "math_lines": ["(1 + 2x)^5"],
            },
            {
                "part_label": "(b)",
                "normalized_text": "hence find the coefficient of x^2 in (1 + 2x)^5(1 - x)",
                "raw_text": "hence find the coefficient of x^2 in (1 + 2x)^5(1 - x)",
                "math_lines": ["coefficient of x^2"],
            },
        ],
    )

    assert parts[0]["topic"] == "binomial_expansion"
    assert parts[1]["topic"] == "binomial_expansion"
    assert parts[1]["object_cue_primary_topic"] == "binomial_expansion"


def test_object_cues_keep_circular_measure_despite_trig_in_markscheme() -> None:
    result = classify_question(
        "Find x. [5]",
        marks=5,
        config=AppConfig(),
        source_name="9709_s21_qp_12.pdf",
        body_text_normalized="The diagram shows a sector with arc AB. Find the perimeter of the shaded segment in radians.",
        body_text_raw="The diagram shows a sector with arc AB. Find the perimeter of the shaded segment in radians.",
        mark_scheme_text="Use the sine rule and then simplify the trig expression to obtain the final answer.",
    )

    assert result.topic == "circular_measure"
    assert result.topic_evidence_details["object_cue_primary_topic"] == "circular_measure"


def test_object_cues_keep_tangent_question_in_differentiation() -> None:
    result = classify_question(
        "Find the equation of the tangent to the curve y = x^3 - 3x at x = 2. [4]",
        marks=4,
        config=AppConfig(),
        source_name="9709_s21_qp_12.pdf",
        mark_scheme_text="An alternative method substitutes a line into the curve and forms a quadratic with equal roots.",
        body_text_normalized="Find the equation of the tangent to the curve y = x^3 - 3x at x = 2.",
        body_text_raw="Find the equation of the tangent to the curve y = x^3 - 3x at x = 2.",
    )

    assert result.topic == "differentiation"
    assert result.topic_evidence_details["object_cue_primary_topic"] == "differentiation"


def test_object_cues_classify_p5_distribution_table_as_probability_distributions() -> None:
    result = classify_question(
        "A random variable X takes values 0, 1, 2, 3 with probabilities shown in the table. [5]",
        marks=5,
        config=AppConfig(),
        source_name="9709_s21_qp_52.pdf",
        body_text_normalized="The random variable X takes values 0, 1, 2, 3. The probability distribution table is given.",
        body_text_raw="The random variable X takes values 0, 1, 2, 3. The probability distribution table is given.",
    )

    assert result.paper_family == "P5"
    assert result.topic == "probability_distributions"
    assert result.topic_evidence_details["object_cue_primary_topic"] == "probability_distributions"


def test_object_cues_classify_p3_argand_question_as_complex_numbers() -> None:
    result = classify_question(
        "On an Argand diagram, sketch the locus of z such that |z - 1| = 2. [4]",
        marks=4,
        config=AppConfig(),
        source_name="9709_s21_qp_32.pdf",
        body_text_normalized="On an Argand diagram, sketch the locus of z such that |z - 1| = 2.",
        body_text_raw="On an Argand diagram, sketch the locus of z such that |z - 1| = 2.",
    )

    assert result.paper_family == "P3"
    assert result.topic == "complex_numbers"
    assert result.topic_evidence_details["object_cue_primary_topic"] == "complex_numbers"
