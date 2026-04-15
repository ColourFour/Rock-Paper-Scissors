from exam_bank.classification import classify_question, classify_question_parts, infer_source_paper_code, infer_source_paper_family
from exam_bank.config import AppConfig


def test_default_topic_taxonomy_uses_controlled_labels() -> None:
    config = AppConfig()

    assert config.paper_families == ["P1", "P2", "P3", "P4", "P5", "P6", "unknown"]
    assert "partial_fractions" in config.paper_family_taxonomy["P1"]
    assert "complex_numbers" in config.paper_family_taxonomy["P3"]
    assert "connected_particles" in config.paper_family_taxonomy["P4"]
    assert "surds" not in config.paper_family_taxonomy["P1"]
    assert "hypothesis_testing" not in config.paper_family_taxonomy["P1"]
    assert "advanced algebra" not in config.topic_taxonomy
    assert "partial_fractions" in config.topic_taxonomy
    assert config.difficulty_labels == ["easy", "average", "difficult"]


def test_classifies_partial_fractions_inside_p1_topic_bank() -> None:
    result = classify_question(
        "1 Express (3x + 1)/((x + 1)(2x - 3)) in partial fractions. [4]",
        marks=4,
        config=AppConfig(),
        source_name="9709_s21_qp_12.pdf",
    )

    assert result.source_paper_family == "P1"
    assert result.source_paper_code == "12"
    assert result.inferred_paper_family == "P1"
    assert result.paper_family_confidence == "high"
    assert result.paper_family == "P1"
    assert result.topic == "partial_fractions"
    assert result.subtopic == "general"
    assert result.topic_confidence == "high"
    assert "partial fractions" in result.topic_evidence


def test_source_paper_code_and_family_are_inferred_from_filename() -> None:
    assert infer_source_paper_code("9709_s21_qp_12.pdf") == ("12", "high")
    assert infer_source_paper_family("March 2019_qp_32.pdf") == ("P3", "high")


def test_classifies_product_integral_as_integration_by_parts() -> None:
    result = classify_question(
        "2 Integrate x sec^2 x with respect to x. [5]",
        marks=5,
        config=AppConfig(),
        source_name="9709_s21_qp_32.pdf",
    )

    assert result.paper_family == "P3"
    assert result.topic == "integration"
    assert result.subtopic == "general"
    assert result.topic_confidence in {"medium", "high"}
    assert "integration" in result.topic_evidence


def test_classifies_argand_question_as_complex_numbers() -> None:
    result = classify_question(
        "3 Sketch on an Argand diagram the locus of the complex number z such that |z - 2i| = 3. [4]",
        marks=4,
        config=AppConfig(),
        source_name="9709_s21_qp_32.pdf",
    )

    assert result.paper_family == "P3"
    assert result.topic == "complex_numbers"
    assert result.subtopic == "general"
    assert "Argand" in result.topic_evidence


def test_forces_one_topic_for_mixed_grouped_question() -> None:
    result = classify_question(
        (
            "4 Express the rational function in partial fractions. "
            "Hence expand the result in ascending powers of x, stating the range of validity. [8]"
        ),
        marks=8,
        config=AppConfig(),
        source_name="9709_s21_qp_12.pdf",
    )

    assert result.topic == "partial_fractions"
    assert result.subtopic == "general"
    assert result.secondary_topics == []
    assert result.topic_confidence in {"high", "medium"}


def test_classifies_detected_parts_separately() -> None:
    parts = classify_question_parts(
        (
            "9(a) Express the rational function in partial fractions. [4]\n"
            "(b) Hence expand the expression with a negative power in ascending powers of x. [4]"
        ),
        question_number="9",
        config=AppConfig(),
        source_name="9709_s21_qp_12.pdf",
    )

    assert [part["part_label"] for part in parts] == ["9(a)", "9(b)"]
    assert parts[0]["paper_family"] == "P1"
    assert parts[0]["topic"] == "partial_fractions"
    assert parts[0]["subtopic"] == "general"
    assert parts[1]["paper_family"] == "P1"
    assert parts[1]["topic"] == "binomial_expansion"
    assert parts[1]["subtopic"] == "general"


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


def test_missing_examiner_report_still_forces_valid_topic_from_fallback_rules() -> None:
    result = classify_question(
        "Use the common denominator and simplify the identity involving sin x and cos x. [4]",
        marks=4,
        config=AppConfig(),
        source_name="9709_s21_qp_12.pdf",
    )

    assert result.paper_family == "P1"
    assert result.topic == "trigonometry"
    assert result.topic in AppConfig().paper_family_taxonomy["P1"]
