from exam_bank.classification import classify_question, classify_question_parts
from exam_bank.config import AppConfig


def test_default_topic_taxonomy_uses_controlled_labels() -> None:
    config = AppConfig()

    assert config.paper_families == ["P1", "P3", "P4", "P5", "P6", "mixed_or_uncertain"]
    assert config.paper_family_taxonomy["P1"]["algebra"] == [
        "quadratics",
        "polynomials",
        "partial_fractions",
        "modulus",
        "inequalities",
        "surds",
    ]
    assert "advanced algebra" not in config.topic_taxonomy
    assert "algebra" in config.topic_taxonomy
    assert config.difficulty_labels == ["easy", "average", "difficult"]


def test_classifies_partial_fractions_as_controlled_algebra_label() -> None:
    result = classify_question(
        "1 Express (3x + 1)/((x + 1)(2x - 3)) in partial fractions. [4]",
        marks=4,
        config=AppConfig(),
    )

    assert result.paper_family == "mixed_or_uncertain"
    assert result.topic == "algebra"
    assert result.subtopic == "partial_fractions"
    assert result.topic_confidence == "medium"
    assert "partial fractions" in result.topic_evidence


def test_classifies_product_integral_as_integration_by_parts() -> None:
    result = classify_question(
        "2 Integrate x sec^2 x with respect to x. [5]",
        marks=5,
        config=AppConfig(),
    )

    assert result.paper_family == "P3"
    assert result.topic == "calculus"
    assert result.subtopic == "integration_by_parts"
    assert result.topic_confidence in {"medium", "high"}
    assert "integration by parts" in result.topic_evidence


def test_classifies_argand_question_as_complex_numbers() -> None:
    result = classify_question(
        "3 Sketch on an Argand diagram the locus of the complex number z such that |z - 2i| = 3. [4]",
        marks=4,
        config=AppConfig(),
    )

    assert result.paper_family == "P3"
    assert result.topic == "complex_numbers"
    assert result.subtopic == "argand_diagrams"
    assert "Argand" in result.topic_evidence


def test_records_secondary_topic_for_mixed_grouped_question() -> None:
    result = classify_question(
        (
            "4 Express the rational function in partial fractions. "
            "Hence expand the result in ascending powers of x, stating the range of validity. [8]"
        ),
        marks=8,
        config=AppConfig(),
    )

    assert result.topic == "algebra"
    assert result.subtopic == "partial_fractions"
    assert "series" in result.secondary_topics
    assert result.topic_uncertain


def test_classifies_detected_parts_separately() -> None:
    parts = classify_question_parts(
        (
            "9(a) Express the rational function in partial fractions. [4]\n"
            "(b) Hence expand the expression with a negative power in ascending powers of x. [4]"
        ),
        question_number="9",
        config=AppConfig(),
    )

    assert [part["part_label"] for part in parts] == ["9(a)", "9(b)"]
    assert parts[0]["paper_family"] == "mixed_or_uncertain"
    assert parts[0]["topic"] == "algebra"
    assert parts[0]["subtopic"] == "partial_fractions"
    assert parts[1]["paper_family"] == "mixed_or_uncertain"
    assert parts[1]["topic"] == "series"
    assert parts[1]["subtopic"] == "binomial_expansion_fractional_negative"
