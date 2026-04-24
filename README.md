# CAIE 9709 Extraction Pipeline

This project now does one job:

- ingest question paper PDFs and mark scheme PDFs
- detect paper type from filenames
- extract top-level questions
- extract matching mark scheme regions
- map each question to its mark scheme
- write paper-first image exports and JSON metadata

Archived and not part of the supported runtime:

- QA dashboards
- practice pages
- manual review pages
- topic-PDF generation

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

OCR fallback requires Tesseract:

```bash
brew install tesseract
```

## Run

The supported extraction front door is:

```bash
python -m exam_bank.cli process --input input --output output
```

`--input` is scanned recursively, so either of these work:

```text
input/
  question_papers/
  mark_schemes/
  mappings/        # optional mapping files if you use them
```

or a single mixed folder containing question paper PDFs and mark scheme PDFs.

The active runtime does not support legacy QA, review, practice, or topic-PDF commands.

Optional DeepSeek enrichment is a separate sidecar step. It does not change extraction and it does not mutate `question_bank.json`.

Set the API key in your environment:

```bash
export DEEPSEEK_API_KEY=...
```

Then run the enrichment pass against the exported bank:

```bash
python -m exam_bank.deepseek_enrich \
  --input output/json/question_bank.json \
  --output output/json/question_bank.deepseek.json \
  --limit 25
```

Useful options:

- `--question-ids 12spring24_q01 12spring24_q06`
- `--paper-family p1`
- `--dry-run`
- `--failure-log output/json/question_bank.deepseek.failures.jsonl`

The DeepSeek sidecar keeps the raw model suggestion and adds Stage 2 reconciliation fields such as normalized topic/difficulty labels, local-vs-DeepSeek match status, and final review gating:

```text
output/json/question_bank.deepseek.json
output/json/question_bank.deepseek.failures.jsonl   # only when failures occur
```

## Output

The pipeline writes a paper-first tree:

```text
output/
  p1/
    12spring21/
      questions/
        q01.png
      mark_scheme/
        q01.png
  p3/
  p4/
  p5/
  json/
    question_bank.json
  debug/              # only when debug.enabled is true
```

Paper instance folders use:

```text
{component}{season}{yy}
```

Examples:

- `12spring21`
- `33summer24`
- `53autumn25`

## JSON Contract

`output/json/question_bank.json` contains one object per extracted question.

Core fields:

- `question_id`
- `paper`
- `paper_family`
- `question_number`
- `question_text`
- `mark_scheme_text`
- `question_solution_marks`
- `subparts`
- `subparts_solution_marks`
- `question_image_paths`
- `mark_scheme_image_paths`
- `page_refs`
- `topic`
- `notes`

`notes` keeps traceable extraction metadata such as:

- source PDF paths
- crop confidence
- mapping status and failure reason
- review flags
- extraction quality score and flags

Archived topic-PDF code is kept for reference under `archive/topic_pdfs_legacy/`. It is not part of the supported package runtime.

## Tests

Run the test suite with:

```bash
pytest
```

The regression set covers:

- paper-type recognition
- question-to-mark-scheme mapping
- interior subpart continuity
- paper-first output paths
- JSON schema shape
