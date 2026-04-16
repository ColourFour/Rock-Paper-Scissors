# Automated Exam PDF Question Bank Pipeline

This project turns folders of maths exam PDFs into a reusable question bank with:

- one grouped clean question image per top-level question
- extracted question text
- matched mark scheme answer text and cropped mark scheme images where available
- CAIE-paper-aware topic and difficulty labels
- JSON, CSV, topic PDF packs, and manual review exports

The first version is tuned for Cambridge-style A Level maths papers with question labels such as `1`, `1(a)`, `2(a)(i)`, and grouped top-level questions.

Segmentation is layout-first: the pipeline scores visible number anchors and page coordinates before extracting text from the accepted local question regions. Native PDF spans are flattened and rebuilt into visual lines by y-position, then x-position, with a same-line tolerance so mathematical notation is read spatially rather than in raw PDF stream order.

## Folder Structure

```text
config.yaml
requirements.txt
src/exam_bank/
tests/
index.html
practice/       # generated GitHub Pages export
input/
  question_papers/
  mark_schemes/
  mappings/
  examiner_reports/
output/
  images/
  json/
  csv/
  review/
  qa/
  practice/
  topic_pdfs/
  debug/
```

Put question papers in `input/question_papers/` and mark schemes in `input/mark_schemes/`.
Optional examiner report text or JSON files can go in `input/examiner_reports/`; when present, the classifier uses matching paper/question comments as strong topic evidence.

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
output/qa/
output/practice/
output/topic_pdfs/
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

The batch command now builds a filename metadata registry before opening PDFs. Files are routed by document type from the filename, so question papers enter question extraction, mark schemes enter mark-scheme extraction only as paired companions, and examiner reports are attached as session-level evidence where available.

To build topic PDF packs as part of the batch:

```bash
python -m exam_bank.cli process --config config.yaml --build-topic-pdfs
```

You can also enable this permanently in `config.yaml` with:

```yaml
topic_pdfs:
  enable_topic_pdfs: true
  include_mark_scheme_link: true
```

When `include_mark_scheme_link` is enabled, each question in a topic PDF includes an
`Open mark scheme image` link plus the visible relative image path as a fallback.
Keep `output/topic_pdfs/` and the image folders together so links like
`../images/...png` or `../markschemes/...png` continue to resolve when shared.

The pipeline auto-pairs files like:

```text
March 2019_qp_32.pdf -> March 2019_ms_32.pdf
```

It also understands full Cambridge-style names such as:

```text
9709 Mathematics November 2025 Question Paper 12.pdf
9709 Mathematics November 2025 Mark Scheme 12.pdf
9709 Mathematics November 2025 Examiner Report.pdf
```

For a single uploaded folder containing mixed QP/MS/ER PDFs, use:

```bash
python -m exam_bank.cli process-folder --config config.yaml --input-folder path/to/pdf-folder
```

The registry key is `{syllabus}_{year}_{session}_{component}`, for example `9709_2025_November_12`. Examiner reports without a component number are treated as session-level files and attached to matching components from the same syllabus, year, and session.

For exceptions, add a CSV file under `input/mappings/`, for example `input/mappings/pairs.csv`:

```csv
question_pdf,mark_scheme_pdf
March 2019_qp_32.pdf,March 2019_ms_32.pdf
```

## Topic PDF Packs

After JSON has been generated, build topic-based PDF packs with:

```bash
python -m exam_bank.cli topic-pdfs --config config.yaml
```

By default this reads `output/json/question_bank.json` and writes one PDF per topic to:

```text
output/topic_pdfs/
```

Each topic PDF is organized into difficulty sections:

```text
Easy    -> difficulty: easy
Medium  -> difficulty: average
Hard    -> difficulty: difficult
```

Questions are sorted inside each section by `subtopic`, then `paper_name`, then `question_number`. Each entry uses the existing cropped PNG and a small caption with paper name, question number, subtopic, and marks when available. Records with missing topic, difficulty, or image paths are skipped and logged in `output/review/review_items.csv`.

## QA Review

After `output/json/question_bank.json` exists, run deterministic QA checks against the existing JSON and image files:

```bash
python -m exam_bank.cli qa --config config.yaml
```

To point QA at another export:

```bash
python -m exam_bank.cli qa --config config.yaml --question-bank output/json/question_bank.json
```

To write only failing records:

```bash
python -m exam_bank.cli qa --config config.yaml --only-failed
```

QA focuses on P1, P3, P4, and P5. P2 and P6 records are skipped and counted in the JSON summary. The reports are written to:

```text
output/qa/qa_report.json
output/qa/qa_report.csv
output/qa/review.html
```

The review page is fully static and embeds the QA report payload, so no local server is needed. On macOS, open it with:

```bash
python -m exam_bank.cli open-qa --config config.yaml
```

or:

```bash
open output/qa/review.html
```

Do not type `output/qa/review.html` directly into zsh; that asks the shell to execute the file and will usually produce `permission denied`.

If you intentionally start a local server for another reason and port 8000 is busy, use a different port:

```bash
python3 -m http.server 8001
```

QA JSON summaries include `flag_counts`, `warning_flag_counts`, `fail_flag_counts`, `top_warning_reason`, and `top_fail_reason` so the most common problems are visible without hand-counting records.

## Open Review Output

To open the main review CSV:

```bash
python -m exam_bank.cli open-review --config config.yaml
```

## Student Practice Page

After generating `output/json/question_bank.json`, build a browser-only practice page:

```bash
python -m exam_bank.cli practice-page --config config.yaml
```

To point it at another export:

```bash
python -m exam_bank.cli practice-page --config config.yaml --question-bank output/json/question_bank.json
```

This writes a local test page and a publishable GitHub Pages copy:

```text
output/practice/index.html
practice/index.html
practice/assets/
```

Open the local file directly from Finder or your browser:

```bash
open output/practice/index.html
```

It does not fetch local JSON and does not need a local server. The generated HTML embeds a small usable record set with these fields:

```text
source_pdf
paper_family
topic
question_number
marks_if_available
question_image
markscheme_image
full_question_label / question_label
session
year
component
source page number
mark scheme page number
qa status / warnings
```

The page lets a student choose a paper family and topic, get a random matching question image, and reveal the mapped mark scheme image.

The publishable copy in `practice/` also copies the referenced question and mark scheme images into `practice/assets/`, so the page works from GitHub Pages instead of depending on ignored `output/` files.

### GitHub Pages Sharing

`output/practice/index.html` is ignored by git and is not published. The shareable page is exported to:

```text
practice/index.html
```

The repository root page links to `practice/`, and the GitHub Pages workflow deploys `index.html` plus the generated `practice/` directory. After running the generator, commit and push the updated `practice/` folder:

```bash
python -m exam_bank.cli practice-page --config config.yaml
git add index.html practice .github/workflows/pages.yml .nojekyll
git commit -m "Publish practice page"
git push
```

For this repository, the colleague-facing URL is:

```text
https://colourfour.github.io/Rock-Paper-Scissors/practice/
```

The root project page is:

```text
https://colourfour.github.io/Rock-Paper-Scissors/
```

If GitHub Pages is not enabled yet, enable it in the repository settings using GitHub Actions as the source. The included workflow deploys on pushes to `main`.

### Sharing and Bug Reports

The practice page can collect lightweight structured feedback without a backend. It uses an external form as the primary path and a clipboard template as the fallback path:

- `Report a problem` opens your configured form in a new tab and appends the current question metadata as query parameters.
- `Copy bug report` copies a clean template that colleagues can paste into email, Slack, Teams, or a form.

Configure this in `config.yaml`:

```yaml
practice_page:
  publish_enabled: true
  publish_dir: practice
  publish_assets: true
  publish_asset_dir: assets
  github_pages_url: "https://colourfour.github.io/Rock-Paper-Scissors/"
  bug_report:
    enabled: true
    form_url: "https://forms.example.com/your-form"
    open_in_new_tab: true
    enable_copy_button: true
    form_field_names:
      paper: paper
      topic: topic
      question_number: question_number
      marks: marks
      source_pdf: source_pdf
      question_image: question_image
      markscheme_image: markscheme_image
      report_text: report_text
```

If `form_url` is blank, the page hides `Report a problem` and still shows `Copy bug report` when `enable_copy_button` is true.

The copied report includes:

```text
Issue type
Description
Expected result
Actual result
Paper
Topic
Question number
Marks
Source PDF
Question image path
Mark scheme image path
Question label
Question id
Session/year
Component
Source page number
Mark scheme page number
QA status / warnings
Topic assigned by pipeline
```

For Google Forms, create a prefilled link and copy the `entry.xxxxx` field names into `form_field_names`. For Microsoft Forms or another form tool, use the query parameter names that tool expects. If the form ignores query parameters, the form still opens and colleagues can use `Copy bug report` to paste the metadata manually.

## Output Schema

JSON keeps the full machine-readable record, including extracted question text:

```text
source_pdf
paper_name
question_number
full_question_label
question_image
screenshot_path
combined_question_text
answer_text
paper_family
source_paper_code
source_paper_family
inferred_paper_family
paper_family_confidence
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
difficulty_confidence
difficulty_evidence
difficulty_uncertain
marks
marks_if_available
question_pages
question_crop_confidence
page_numbers
review_flags
confidence
crop_uncertain
crop_debug_paths
markscheme_text
markscheme_image
markscheme_pages
markscheme_question_number
markscheme_crop_confidence
markscheme_mapping_method
markscheme_table_detected
markscheme_table_header_detected
markscheme_nearby_anchors
markscheme_debug_paths
```

`marks` and `marks_if_available` intentionally contain the same value.

CSV is the human review view. It is image-first and does not export `combined_question_text`. It includes `question_image`, `question_image_link`, `screenshot_path`, `markscheme_image`, answer/classification metadata, part-level topic metadata as a JSON string, marks, pages, review flags, `crop_uncertain`, crop debug paths, and confidence. CSV cannot truly embed PNG pixels, so image fields point to generated files and `question_image_link` provides a spreadsheet-friendly hyperlink.

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
- topic PDF export layout
- static practice page bug-report buttons
- debug crop overlays

The only valid difficulty labels are:

```text
easy
average
difficult
```

Topic classification is a controlled Cambridge International AS & A Level Mathematics 9709 taxonomy problem. The classifier first identifies the paper family from the source filename when it can, otherwise from the mathematics required, then restricts topic/subtopic scoring to that paper's topic bank. The exported fields include `source_paper_family`, `inferred_paper_family`, and `paper_family_confidence`. Allowed paper families are:

```text
P1
P2
P3
P4
P5
P6
unknown
```

Each paper family has one strict allowed topic list in `config.yaml`, such as:

```text
P1: quadratics, polynomials, partial_fractions, modulus, inequalities, functions, coordinate_geometry, circular_measure, trigonometry, binomial_expansion, differentiation, integration, numerical_methods
P2: logarithmic_and_exponential_functions, trigonometry, differentiation, integration
P3: logarithmic_and_exponential_functions, trigonometry, integration, differentiation, differential_equations, vectors, complex_numbers, series, parametric_equations
P4: kinematics, forces_and_equilibrium, connected_particles, momentum_and_impulse, work_energy_power, circular_motion
P5: permutations_and_combinations, probability, discrete_random_variables, binomial_distribution, poisson_distribution, normal_distribution, correlation_and_regression
P6: probability, continuous_random_variables, normal_distribution, central_limit_theorem, confidence_intervals, hypothesis_testing
```

The classifier first chooses the paper family, restricts candidates to that paper's allowed list, scores each topic, and then forces exactly one final `topic`. Confidence is diagnostic only; it never suppresses the final assignment. `secondary_topics` is intentionally left empty in this strict baseline.

For grouped multi-part questions, the default exported `topic` is the single final grouped topic used by the student page. `part_level_topics` may still be written for diagnostics, but it does not change the forced one-topic output.

Difficulty is also paper-aware. It combines marks, number of linked parts, symbolic density, routine versus disguised wording, cross-topic mixing, and the selected paper family's difficulty heuristics. The output includes `difficulty`, `difficulty_confidence`, `difficulty_evidence`, and `difficulty_uncertain`.

Mark scheme images are cropped from the rendered mark scheme PDF using the CAIE answer table only. A table is accepted only when the header row contains all four headers: `Question`, `Answer`, `Marks`, and `Guidance`. Rubric, rules, notes tables, and nonstandard tables are rejected. The mapper finds the matching question number in the Question column, crops the full table row block until the next visible question number, includes same-question subparts and continuation rows, and requires the mark-scheme total to match the question-paper marks exactly. If the strict checks fail, the record is flagged and no mark scheme image is exposed to the student page.

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
- rendered mark scheme pages, detected table bounds, detected question-number anchors, and chosen mark scheme crop boxes

Topic PDF layout can be tuned in `config.yaml`:

```yaml
topic_pdfs:
  enable_topic_pdfs: false
  topic_pdf_output_dir: output/topic_pdfs
  include_mark_scheme_link: true
  page_size: A4
  margin: 42
  image_max_width: 500
  caption_font_size: 8
  section_heading_font_size: 15
  topic_title_font_size: 22
```

Practice page publishing and reporting can be tuned in `config.yaml`:

```yaml
practice_page:
  publish_enabled: true
  publish_dir: practice
  publish_assets: true
  publish_asset_dir: assets
  github_pages_url: "https://colourfour.github.io/Rock-Paper-Scissors/"
  bug_report:
    enabled: true
    form_url: ""
    open_in_new_tab: true
    enable_copy_button: true
    form_field_names:
      paper: paper
      topic: topic
      question_number: question_number
      marks: marks
      source_pdf: source_pdf
      question_image: question_image
      markscheme_image: markscheme_image
      report_text: report_text
```

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
- missing or uncertain mark scheme image crops
- missing Question/Answer/Marks/Guidance answer-table headers
- fallback mark scheme table mappings
- mark scheme rows not found for a question number
- short detected question text
- low-confidence topic or difficulty labels
- uncertain paper family labels
- topic PDF records skipped for missing metadata or unreadable images
- question sequence gaps
- uncertain question-start anchors
- possible next-question contamination
- header/footer contamination
- answer-space-heavy regions
- uncertain crop boxes

This file is designed for manual correction and later improvement of the heuristics.

Each processed PDF also writes `output/review/<paper_name>_diagnostics.json` with detected question count, candidate anchor count, uncertain split count, OCR fallback pages, footer/header contamination count, crop uncertainty count, mark scheme image counts, review flag counts, and topic/difficulty counts by paper family. Batch runs also write `output/review/batch_diagnostics.json`.

Topic classification debugging is written to `output/review/<paper_name>_topic_debug.json`. It includes a text snippet, source and inferred paper family, final grouped topic, confidence, evidence, alternative paper-valid candidates for low or medium confidence choices, difficulty evidence, and mark scheme image status. Review rows for uncertain mark scheme mappings include the mapping method, crop confidence, detected mark scheme pages, detected answer-table headers, whether a table was detected, and nearby question-number anchors.

## Likely Failure Cases

- Scanned PDFs can work through OCR, but maths notation may be imperfect.
- Very unusual page layouts may need `question_start_max_x`, margins, or OCR thresholds adjusted.
- Mark schemes with complex tables may attach broad answer sections rather than precise subpart answers.
- Prompt crops are based on detected text/mark boxes plus nearby non-answer graphics. Very unusual diagrams or tables may still need review; uncertain crops are marked with `crop_uncertain`.
- Topic classification is intentionally conservative and flags uncertain items rather than hiding them.
- Topic PDF export uses the already-cropped PNGs. If an image path is stale or unreadable, that record is skipped and logged instead of stopping the pack build.

## Tests

Run:

```bash
pytest
```

The lightweight unit tests cover question parsing, grouping, mark scheme pairing, topic PDF grouping, and export schema. The sample integration test runs only when the March 2019 sample PDFs and PDF dependencies are available.
