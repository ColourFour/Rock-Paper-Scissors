# Automated Exam PDF Question Bank Pipeline

This project turns folders of maths exam PDFs into a reusable question bank with:

- one grouped clean question image per top-level question
- extracted question text
- matched mark scheme answer text where available
- topic and difficulty labels
- JSON, CSV, and manual review exports

The first version is tuned for Cambridge-style A Level maths papers with question labels such as `1`, `1(a)`, `2(a)(i)`, and grouped top-level questions.

Segmentation is layout-first: the pipeline scores visible number anchors and page coordinates before extracting text from the accepted local question regions. Native PDF spans are flattened and rebuilt into visual lines by y-position, then x-position, with a same-line tolerance so mathematical notation is read spatially rather than in raw PDF stream order.

## Folder Structure

```text
config.yaml
requirements.txt
src/exam_bank/
tests/
input/
  question_papers/
  mark_schemes/
  mappings/
output/
  images/
  json/
  csv/
  review/
  debug/
```

Put question papers in `input/question_papers/` and mark schemes in `input/mark_schemes/`.

## Setup

Create a virtual environment and install the project:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

For the test harness as well, install the dev extra:

```bash
pip install -e ".[dev]"
```

OCR fallback requires the Tesseract command-line app. On macOS:

```bash
brew install tesseract
```

Check the environment:

```bash
python -m exam_bank.cli preflight
```

## Run One Sample PDF

```bash
python -m exam_bank.cli sample \
  --question-pdf "/Users/sbrooker/Favorite/Former Classes/RCF 2024-2025/AS Maths/00 General/Math A Level Exams All/March 2019_qp_32.pdf" \
  --mark-scheme "/Users/sbrooker/Favorite/Former Classes/RCF 2024-2025/AS Maths/00 General/Math A Level Exams All/March 2019_ms_32.pdf"
```

Outputs will be written to:

```text
output/images/
output/json/
output/csv/
output/review/
output/debug/   # only populated when debug.enabled is true
```

## Run a Batch

Copy PDFs into the input folders:

```text
input/question_papers/
input/mark_schemes/
```

Then run:

```bash
python -m exam_bank.cli process --config config.yaml
```

The pipeline auto-pairs files like:

```text
March 2019_qp_32.pdf -> March 2019_ms_32.pdf
```

For exceptions, add a CSV file under `input/mappings/`, for example `input/mappings/pairs.csv`:

```csv
question_pdf,mark_scheme_pdf
March 2019_qp_32.pdf,March 2019_ms_32.pdf
```

## Output Schema

JSON keeps the full machine-readable record, including extracted question text:

```text
source_pdf
paper_name
question_number
full_question_label
screenshot_path
combined_question_text
answer_text
paper_family
question_level_paper_family
question_level_topic
question_level_subtopic
part_level_topics
topic
subtopic
topic_confidence
topic_evidence
secondary_topics
topic_uncertain
topic_alternatives
difficulty
marks
marks_if_available
page_numbers
review_flags
confidence
crop_uncertain
crop_debug_paths
```

`marks` and `marks_if_available` intentionally contain the same value.

CSV is the human review view. It is image-first and does not export `combined_question_text`. It includes `question_image`, `question_image_link`, `screenshot_path`, answer/classification metadata, part-level topic metadata as a JSON string, marks, pages, review flags, `crop_uncertain`, crop debug paths, and confidence. CSV cannot truly embed PNG pixels, so `question_image` points to the generated image and `question_image_link` provides a spreadsheet-friendly hyperlink.

## Configuration

Edit `config.yaml` to tune:

- input and output folders
- Cambridge 9709 paper-family taxonomy and method/object/keyword classification hints
- question detection thresholds
- crop margins and screenshot DPI
- prompt-only PDF crops versus whole-span PDF crops
- OCR fallback
- file naming
- optional OpenAI classification
- debug crop overlays

The only valid difficulty labels are:

```text
easy
average
difficult
```

Topic classification is a controlled Cambridge International AS & A Level Mathematics 9709 taxonomy problem. The classifier first infers `paper_family` from the mathematics required, then assigns topic and subtopic. Allowed paper families are:

```text
P1
P3
P4
P5
P6
mixed_or_uncertain
```

Each paper family has configured topic/subtopic paths in `config.yaml`, such as:

```text
P1 / algebra: quadratics, polynomials, partial_fractions, modulus, inequalities, surds
P1 / series: binomial_expansion_positive_integer, binomial_expansion_fractional_negative
P3 / calculus: integration_by_parts, integration_by_substitution, implicit_differentiation
P3 / complex_numbers: argand_diagrams, modulus_argument, roots_of_complex_numbers
P4 / dynamics: newtons_laws, connected_particles, pulleys
P5 / normal_distribution: standardisation, inverse_normal
P6 / hypothesis_testing: binomial, poisson, normal
```

The classifier scores configured method hints, mathematical object hints, and keyword hints, then applies explicit rule boosts for common exam tasks. It records `paper_family`, `topic_evidence`, `topic_confidence`, `secondary_topics`, and `topic_uncertain` instead of inventing open-ended labels.

For grouped multi-part questions, the default exported `topic` and `subtopic` remain aliases for the grouped question label. The explicit fields `question_level_paper_family`, `question_level_topic`, and `question_level_subtopic` store the same overall label, while `part_level_topics` stores any detectable subpart labels. For example, a grouped question can export `question_level_topic: algebra`, `question_level_subtopic: partial_fractions`, and `part_level_topics` with `9(a)` as partial fractions and `9(b)` as `series / binomial_expansion_fractional_negative`. In that case `secondary_topics` stores the other main topics, such as `series`.

By default, `detection.output_mode` is `prompt_only`. This renders the original PDF page, detects the prompt text/mark bounds, crops the rendered PDF pixels, and stitches only prompt regions together. It does not OCR-typeset or reconstruct the question image.

Use `detection.output_mode: full_region` only if you want the whole exam question area for debugging. That mode can include answer space and page furniture.

To inspect crop decisions, set:

```yaml
debug:
  enabled: true
```

Debug files are written to `output/debug/`:

- original rendered page images
- page images with detected text boxes
- page images with candidate question anchors
- page images with proposed question bounding boxes
- page images with final crop boxes
- crop box metadata JSON

## Optional OpenAI Classification

Local heuristic classification is the default. To enable the optional OpenAI classifier:

1. Set `classification.enable_openai: true` in `config.yaml`.
2. Export an API key:

```bash
export OPENAI_API_KEY="your-key"
```

The pipeline still falls back to local heuristics if OpenAI is disabled, unavailable, or returns an error.

## Review Workflow

The pipeline writes `output/review/review_items.csv` for anything uncertain, including:

- OCR fallback text
- missing mark schemes
- unmatched answer sections
- short detected question text
- low-confidence topic or difficulty labels
- uncertain paper family labels
- question sequence gaps
- uncertain question-start anchors
- possible next-question contamination
- header/footer contamination
- answer-space-heavy regions
- uncertain crop boxes

This file is designed for manual correction and later improvement of the heuristics.

Each processed PDF also writes `output/review/<paper_name>_diagnostics.json` with detected question count, candidate anchor count, uncertain split count, OCR fallback pages, footer/header contamination count, crop uncertainty count, and review flag counts.

Topic classification debugging is written to `output/review/<paper_name>_topic_debug.json`. It includes a text snippet, grouped topic and subtopic, part-level topics, confidence, evidence, secondary topics, and alternative candidates for low or medium confidence choices.

## Likely Failure Cases

- Scanned PDFs can work through OCR, but maths notation may be imperfect.
- Very unusual page layouts may need `question_start_max_x`, margins, or OCR thresholds adjusted.
- Mark schemes with complex tables may attach broad answer sections rather than precise subpart answers.
- Prompt crops are based on detected text/mark boxes plus nearby non-answer graphics. Very unusual diagrams or tables may still need review; uncertain crops are marked with `crop_uncertain`.
- Topic classification is intentionally conservative and flags uncertain items rather than hiding them.

## Tests

Run:

```bash
pytest
```

The lightweight unit tests cover question parsing, grouping, mark scheme pairing, and export schema. The sample integration test runs only when the March 2019 sample PDFs and PDF dependencies are available.
