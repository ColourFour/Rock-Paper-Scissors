from pathlib import Path

from exam_bank.config import AppConfig
from exam_bank.extraction_structure import build_structured_question_text
from exam_bank.models import BoundingBox, PageLayout, QuestionSpan, TextBlock


def _block(text: str, y: float, x: float = 60, width: float = 420, page: int = 1) -> TextBlock:
    return TextBlock(page_number=page, text=text, bbox=BoundingBox(x, y, x + width, y + 14))


def test_preserves_display_math_lines_in_body_and_math_lines() -> None:
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[],
    )
    span = QuestionSpan(
        source_pdf=Path("paper.pdf"),
        paper_name="paper",
        question_number="1",
        start_page=1,
        start_y=40,
        end_page=1,
        end_y=700,
        page_numbers=[1],
        blocks=[
            _block("1 Find the values of x for which", 80),
            _block("x^2 - 5x + 6 = 0", 110, x=110, width=220),
            _block("and state the interval 0 < x < 6. [4]", 145),
        ],
        full_question_label="1",
    )

    structured = build_structured_question_text(span, [layout], AppConfig())

    assert "x^2 - 5x + 6 = 0" in structured.body_text_raw
    assert "x^2 - 5x + 6 = 0" in structured.math_lines
    assert structured.body_text_raw.count("\n") >= 2


def test_separates_diagram_labels_from_body_text() -> None:
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[],
        graphics=[BoundingBox(320, 160, 540, 360)],
    )
    span = QuestionSpan(
        source_pdf=Path("paper.pdf"),
        paper_name="paper",
        question_number="3",
        start_page=1,
        start_y=40,
        end_page=1,
        end_y=700,
        page_numbers=[1],
        blocks=[
            _block("3 The diagram shows a sector ABC of a circle with centre O.", 80),
            _block("Find the perimeter of the shaded segment. [5]", 110),
            _block("A", 185, x=330, width=12),
            _block("B", 185, x=515, width=12),
            _block("O", 255, x=420, width=12),
            _block("8 cm", 300, x=360, width=35),
            _block("30°", 220, x=450, width=24),
        ],
        full_question_label="3",
    )

    structured = build_structured_question_text(span, [layout], AppConfig())

    assert "The diagram shows a sector ABC of a circle with centre O." in structured.body_text_normalized
    assert "A" in structured.diagram_text
    assert "8 cm" in structured.diagram_text
    assert "30°" in structured.diagram_text
    assert "8 cm" not in structured.combined_question_text


def test_preserves_part_boundaries_and_part_math_lines() -> None:
    layout = PageLayout(page_number=1, width=595, height=842, blocks=[])
    span = QuestionSpan(
        source_pdf=Path("paper.pdf"),
        paper_name="paper",
        question_number="5",
        start_page=1,
        start_y=40,
        end_page=1,
        end_y=700,
        page_numbers=[1],
        blocks=[
            _block("5(a) Expand (1 + 2x)^4. [2]", 80),
            _block("(b) Hence find the coefficient of x^2 in", 120),
            _block("(1 + 2x)^4 (1 - x). [2]", 150, x=100, width=240),
        ],
        full_question_label="5(a)-(b)",
    )

    structured = build_structured_question_text(span, [layout], AppConfig())

    assert len(structured.part_texts) == 2
    assert structured.part_texts[0]["part_label"] == "(a)"
    assert structured.part_texts[1]["part_label"] == "(b)"
    assert "(1 + 2x)^4 (1 - x). [2]" in structured.part_texts[1]["math_lines"]


def test_flags_malformed_power_or_symbol_runs() -> None:
    layout = PageLayout(page_number=1, width=595, height=842, blocks=[])
    span = QuestionSpan(
        source_pdf=Path("paper.pdf"),
        paper_name="paper",
        question_number="1",
        start_page=1,
        start_y=40,
        end_page=1,
        end_y=700,
        page_numbers=[1],
        blocks=[
            _block("1 Solve the equation 4 sin 1 + tan 1 = 0", 80),
            _block("for 0Å < 1 < 180Å. [3]", 110),
        ],
        full_question_label="1",
    )

    structured = build_structured_question_text(span, [layout], AppConfig())

    assert "broken_superscript_or_power" in structured.extraction_quality_flags
    assert "math_corruption_suspected" in structured.extraction_quality_flags
    assert structured.extraction_quality_score < 1.0


def test_combined_question_text_prefers_clean_body_without_diagram_pollution() -> None:
    layout = PageLayout(
        page_number=1,
        width=595,
        height=842,
        blocks=[],
        graphics=[BoundingBox(300, 180, 540, 340)],
    )
    span = QuestionSpan(
        source_pdf=Path("paper.pdf"),
        paper_name="paper",
        question_number="7",
        start_page=1,
        start_y=40,
        end_page=1,
        end_y=700,
        page_numbers=[1],
        blocks=[
            _block("7 The graph of y = f(x) is shown.", 80),
            _block("(a) Describe the transformation. [2]", 110),
            _block("x", 320, x=520, width=10),
            _block("y", 190, x=305, width=10),
        ],
        full_question_label="7(a)",
    )

    structured = build_structured_question_text(span, [layout], AppConfig())

    assert structured.combined_question_text == structured.body_text_normalized
    assert "x" in structured.diagram_text
    assert "y" in structured.diagram_text
    assert structured.combined_question_text.endswith("[2]")
