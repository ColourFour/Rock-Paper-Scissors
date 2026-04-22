# Repo Review Pass - 2026-04-22

This is a repo-wide review of the maintained project files, with a focus on architecture, maintainability, correctness risk, and fit for the current CAIE 9709 direction.

Score guide:
- `5/5`: strong, clear, low-risk, good fit for current direction
- `4/5`: good and dependable, with normal cleanup opportunities
- `3/5`: workable and valuable, but carrying clear maintenance debt
- `2/5`: materially drifted, awkward, or risky
- `1/5`: actively misleading, stale, or in need of replacement

Scope notes:
- I reviewed source, tests, docs, config, and committed frontend/publish files.
- I did not score generated outputs under `output/`.
- `practice/index.html` is included because it is committed and effectively acts like a publish artifact.

## Executive View

Top findings:
1. The Python core is in good shape functionally, but too much complexity is concentrated in `classification.py`, `pipeline.py`, `question_detection.py`, `mark_schemes.py`, and `image_rendering.py`.
2. Runtime-facing taxonomy/config surfaces have drifted from the current CAIE 9709 direction. The biggest offenders are `config.yaml`, `app/student_practice/app.js`, and the committed `practice/index.html` artifact.
3. The test suite is one of the strongest parts of the repo. It gives real confidence in detection, reconciliation, and sample-pipeline behavior.
4. The current data model is powerful but increasingly wide. `QuestionRecord` is becoming the place where every new idea lands.
5. The project is past the “prove it works” stage and entering the “make it sustainable” stage. The next big wins are refactoring boundaries, unifying taxonomy/config, and retiring stale frontend surfaces.

Recommended next path:
1. Unify runtime taxonomy in exactly one maintained source of truth, then make config/frontend consumers derive from it.
2. Split the large heuristic modules by responsibility before adding much more logic.
3. Keep leaning on the existing regression style: small synthetic tests plus repo-sample tests.
4. Decide whether `app/student_practice/*` is legacy or intended product. Right now it looks legacy and confusing.

## Source Files

### `src/exam_bank/__init__.py` - 4/5
- Does: package version and minimal package surface.
- Good: clean and harmless.
- Bad: very little value beyond version metadata.
- Improve next: keep it minimal; no action needed unless package metadata expands.

### `src/exam_bank/classification.py` - 3/5
- Does: local topic classification, part classification, object-cue handling, continuity, difficulty, and OpenAI fallback plumbing.
- Good: the logic is clearly battle-tested, recent CAIE-specific refinements are visible, and the debug surface is much better than average for a rules engine.
- Bad: it is too large and too central. Topic scoring, object cues, difficulty, family inference, continuity, and debugging all live together, which raises change risk.
- Improve next: split into submodules such as `paper_family`, `object_cues`, `topic_scoring`, `difficulty`, and `debug_payloads`. Keep the same behavior, just reduce blast radius.

### `src/exam_bank/cli.py` - 4/5
- Does: command-line entrypoint for preflight, sample runs, batch runs, QA, practice page, manual review, and topic PDF builds.
- Good: broad coverage, clear user messages, sensible command structure.
- Bad: CLI behavior depends heavily on runtime config quality, so stale config can make the CLI look worse than the code actually is.
- Improve next: add one lightweight “config sanity” command that explicitly checks taxonomy alignment and warns on known stale labels.

### `src/exam_bank/config.py` - 2/5
- Does: dataclass config model, default taxonomy, classification hints, validation, and config loading.
- Good: strong validation scaffolding and a useful typed config model.
- Bad: it is doing too much, and it still contains legacy taxonomy/hint material that does not cleanly match the current CAIE 9709 direction. This is one of the main drift points in the repo.
- Improve next: separate “app config schema” from “taxonomy/hints knowledge base”, then enforce one canonical vocabulary source.

### `src/exam_bank/document_metadata.py` - 4/5
- Does: filename/internal metadata parsing and reconciliation for syllabus, session, component, and document type.
- Good: focused, readable, and appropriately defensive about real-world filename mess.
- Bad: synonym growth can make it slowly accrete edge-case logic.
- Improve next: keep adding regression tests for newly observed filename formats, but resist letting this file absorb registry logic.

### `src/exam_bank/document_registry.py` - 4/5
- Does: scans files, classifies document roles, pairs QP/MS/ER files, and tracks warnings/unclassified files.
- Good: clear responsibility and good separation from extraction/classification.
- Bad: a few more reporting utilities would make it easier to inspect pairing decisions in isolation.
- Improve next: consider a small registry diagnostic export so pairing problems can be debugged before running the full pipeline.

### `src/exam_bank/examiner_reports.py` - 4/5
- Does: finds examiner report evidence, scopes it to the right paper/question, extracts cues, and maps them into topic evidence.
- Good: useful augmentation layer, scoped carefully enough to avoid obvious cross-paper contamination.
- Bad: it reaches into classification scoring helpers, which creates some coupling.
- Improve next: move shared topic-scoring interfaces behind a smaller public helper so this file is less dependent on classifier internals.

### `src/exam_bank/exporters.py` - 4/5
- Does: JSON and CSV export for records, including compatibility handling and image-first CSV choices.
- Good: pragmatic, stable, and intentionally keeps CSV readable instead of dumping everything.
- Bad: field mapping is long and will keep growing as `QuestionRecord` grows.
- Improve next: centralize export field definitions so schema evolution is easier to track and test.

### `src/exam_bank/extraction_structure.py` - 4/5
- Does: builds structured text representations like `body_text_raw`, `body_text_normalized`, `math_lines`, `diagram_text`, part text, and extraction quality flags.
- Good: this is exactly the kind of structural layer the project needed. It improves downstream reasoning without overpromising symbolic reconstruction.
- Bad: the heuristics are still fairly shallow, so hard layout cases will continue to leak through.
- Improve next: keep it incremental. Add more layout-aware heuristics, but do not let it turn into a full symbolic parser.

### `src/exam_bank/identifiers.py` - 5/5
- Does: normalizes question IDs and parent question IDs.
- Good: tiny, clear, and high leverage.
- Bad: none that matter.
- Improve next: keep it small and well-tested.

### `src/exam_bank/image_limits.py` - 5/5
- Does: safe render caps and image downscaling to prevent oversized raster work.
- Good: focused, important, and easy to trust.
- Bad: none of consequence.
- Improve next: keep this file narrowly scoped; it is a good example for the rest of the codebase.

### `src/exam_bank/image_rendering.py` - 3/5
- Does: prompt-region detection, text/figure separation, crop unioning, dedupe, debug overlays, and final question image rendering.
- Good: sophisticated and clearly shaped by real exam-page failure cases. It is one of the reasons the pipeline works as well as it does.
- Bad: very large, heavily heuristic, and hard to reason about end to end. This is a future maintenance hotspot.
- Improve next: split into region detection, figure handling, overlap/dedupe, and debug-output helpers. Keep the tests exactly as aggressive as they are now.

### `src/exam_bank/manual_review.py` - 4/5
- Does: builds a local manual review page and merges reviewed outputs back into JSON.
- Good: practical, understandable, and directly useful for a human-in-the-loop workflow.
- Bad: HTML generation embedded in Python can get unwieldy over time.
- Improve next: keep the data contract stable, but consider moving the HTML template into a separate file if the UI grows.

### `src/exam_bank/mark_schemes.py` - 3/5
- Does: mark scheme pairing, answer extraction, table detection, anchor finding, crop rendering, and mark total validation.
- Good: serious amount of real-world logic here, and the validation work is stronger than most one-off PDF pipelines.
- Bad: this is one of the hardest files in the repo to safely modify. It mixes table geometry, OCR-like word handling, crop logic, and validation in one place.
- Improve next: split table detection, anchor detection, crop generation, and mark-total reasoning into separate units with explicit intermediate structures.

### `src/exam_bank/models.py` - 3/5
- Does: core dataclasses for layout objects, classification results, render results, and the exported `QuestionRecord`.
- Good: clear types and an easy-to-understand central schema.
- Bad: `QuestionRecord` is becoming a dumping ground for every pipeline concern: extraction, classification, QA, reconciliation, repair, and manual review metadata.
- Improve next: separate “core record fields” from optional debug/audit metadata, or introduce nested dataclasses for extraction/classification/QA payloads.

### `src/exam_bank/mupdf_tools.py` - 5/5
- Does: quiets noisy MuPDF stderr behavior.
- Good: tiny, useful, and isolated.
- Bad: none.
- Improve next: keep it exactly this boring.

### `src/exam_bank/pdf_extract.py` - 4/5
- Does: PDF text/graphics extraction, OCR merge, and visual-line reconstruction for math-heavy content.
- Good: good architectural instinct here. Reconstructing visual lines before later processing is one of the strongest choices in the pipeline.
- Bad: extraction heuristics will always have edge cases, and this file is already accumulating some subtle notation behavior.
- Improve next: keep tests focused on visual-order and notation integrity; avoid letting unrelated downstream logic creep in.

### `src/exam_bank/pipeline.py` - 3/5
- Does: end-to-end orchestration from PDF to records, including extraction, rendering, mark schemes, classification, reconciliation, QA flags, and debug reporting.
- Good: powerful and clearly the operational heart of the project. It also contains useful paper-level debug/reporting hooks.
- Bad: orchestration and policy are too intertwined. This file now owns too many cross-cutting decisions.
- Improve next: peel off reconciliation/repair and debug-report writing into separate modules, leaving `pipeline.py` as a thinner conductor.

### `src/exam_bank/practice_page.py` - 4/5
- Does: builds the static student practice page from the question bank and manages asset resolution.
- Good: pragmatic, easy to use, and apparently the maintained frontend path.
- Bad: still uses large inline HTML/CSS/JS strings, which becomes awkward to maintain once the UI expands.
- Improve next: if this page keeps growing, move template assets out of Python. If it stays modest, current structure is acceptable.

### `src/exam_bank/qa.py` - 4/5
- Does: deterministic QA against existing exports, including topic validation, image checks, mark scheme checks, and static HTML review output.
- Good: this is a strong safety net and a major project asset. The QA layer creates a lot of trust in outputs.
- Bad: it duplicates some taxonomy knowledge and can drift if the source of truth is not unified.
- Improve next: drive allowed-topic validation from one canonical taxonomy source shared with config/classification.

### `src/exam_bank/question_detection.py` - 3/5
- Does: detects question anchors and spans, filters page furniture, rescues continuation blocks, tracks subparts, and extracts marks.
- Good: deeply informed by real paper layouts. This is a serious heuristic engine, not a toy.
- Bad: long, stateful, and brittle to modify. It is hard to tell which heuristics are foundational versus opportunistic.
- Improve next: split anchor scoring, span boundary logic, continuation rescue, and furniture filtering into smaller units with explicit intermediate tests.

### `src/exam_bank/review.py` - 4/5
- Does: turns record review flags into CSV review items and messages.
- Good: focused and useful; good separation from pipeline logic.
- Bad: flag-message mapping will get long as the system grows.
- Improve next: consider centralizing review-flag metadata if the flag vocabulary keeps expanding.

### `src/exam_bank/topic_pdfs.py` - 4/5
- Does: validates records for topic-pack export and builds topic-grouped PDFs with optional embedded mark schemes.
- Good: practical output layer, sensible validation, and a nice self-contained sharing artifact.
- Bad: some PDF-building complexity is unavoidable and makes the file a bit dense.
- Improve next: keep the validation separate from document rendering; that boundary is already helping.

## Frontend, Docs, and Config Files

### `README.md` - 3/5
- Does: setup, commands, folder structure, QA flow, practice page flow, manual review flow, and project usage guidance.
- Good: very thorough and clearly written by someone who uses the repo for real work.
- Bad: it is getting long enough to drift, and some parts are likely to lag current runtime behavior.
- Improve next: split into “quick start”, “operator guide”, and “architecture notes” so it stays trustworthy.

### `config.yaml` - 1/5
- Does: runtime config used by the CLI.
- Good: central place for operator-facing defaults.
- Bad: this is the biggest runtime drift risk in the repo. The taxonomy in this file still reflects older labels and families, so it can undermine the much better Python-side logic.
- Improve next: either regenerate this from the canonical taxonomy or drastically shrink it so operators only override true runtime knobs, not topic vocabulary.

### `pyproject.toml` - 4/5
- Does: packaging metadata, dependencies, and pytest config.
- Good: clean and modern enough for this project.
- Bad: minimal packaging metadata only; not a real problem.
- Improve next: keep dev/test extras clean and avoid duplicating dependency intent elsewhere.

### `requirements.txt` - 3/5
- Does: flat dependency list.
- Good: straightforward and easy for quick local setup.
- Bad: includes `pytest`, which is really a dev dependency, and duplicates the dependency story already present in `pyproject.toml`.
- Improve next: decide whether `requirements.txt` is a runtime install file or a convenience file, then align it with that purpose.

### `index.html` - 4/5
- Does: simple landing page that points users to the published practice page.
- Good: clean, small, and fit for purpose.
- Bad: visually basic and not especially extensible.
- Improve next: keep it simple unless you want the repo root to become a fuller project site.

### `practice/index.html` - 2/5
- Does: committed generated static practice page with embedded question-bank payload.
- Good: useful as a publish artifact and easy to host.
- Bad: very large, generated, and currently stale relative to the latest classification/taxonomy direction. This is not a good hand-maintained artifact.
- Improve next: treat it explicitly as a generated artifact. Rebuild it from current data or keep it out of review-oriented source discussions.

### `app/student_practice/index.html` - 2/5
- Does: legacy standalone student practice page shell.
- Good: simple structure.
- Bad: looks superseded by `practice_page.py` output and creates product confusion.
- Improve next: retire it, or explicitly mark it as legacy. Maintaining two frontend paths is not helping.

### `app/student_practice/app.js` - 1/5
- Does: legacy client-side practice logic and topic filtering.
- Good: the basic interaction model is understandable.
- Bad: taxonomy is materially stale and mismatched with the current CAIE 9709 pipeline. This file can actively mislead users about supported topics and output meaning.
- Improve next: either delete/retire it or rebuild it from the same canonical taxonomy and JSON schema used by the maintained pipeline.

### `app/student_practice/styles.css` - 3/5
- Does: styles for the legacy student practice UI.
- Good: readable and serviceable.
- Bad: it styles a frontend that looks no longer canonical.
- Improve next: only keep this if the legacy app remains supported; otherwise remove it with the old frontend.

## Test Files

### `tests/test_classification.py` - 5/5
- Does: regression tests for classification taxonomy, object cues, continuity, and uncertainty behavior.
- Good: this is one of the strongest tests in the repo because it encodes exactly the failure modes that matter.
- Bad: file size will keep growing as classification rules grow.
- Improve next: if it becomes unwieldy, split by theme rather than reducing coverage.

### `tests/test_document_registry.py` - 5/5
- Does: tests metadata parsing, pairing, session-level examiner reports, and registry routing.
- Good: focused, readable, and high value.
- Bad: none that matter.
- Improve next: keep adding cases when new filename weirdness shows up.

### `tests/test_examiner_reports.py` - 4/5
- Does: tests examiner report scoping and topic evidence extraction.
- Good: covers the main contamination risks well.
- Bad: could grow more examples over time as examiner report formats vary.
- Improve next: add a few more “false match should not happen” cases as the evidence layer expands.

### `tests/test_extraction_structure.py` - 5/5
- Does: tests structured extraction fields, math-line preservation, diagram separation, part boundaries, and corruption flags.
- Good: exactly the right kind of tests for the new extraction layer.
- Bad: none significant.
- Improve next: keep extending it whenever a new extraction artifact is discovered.

### `tests/test_image_limits.py` - 5/5
- Does: tests render caps and large-image downscaling.
- Good: tight, focused, and confidence-building.
- Bad: none.
- Improve next: keep it small and fast.

### `tests/test_image_rendering.py` - 4/5
- Does: targeted rendering-region heuristics tests.
- Good: good guardrails around a risky heuristic area.
- Bad: only a slice of the rendering complexity is unit-tested here.
- Improve next: add more cases when image-rendering bugs appear, but keep them narrow and synthetic.

### `tests/test_manual_review.py` - 4/5
- Does: tests manual review page generation and merge-back behavior.
- Good: useful coverage for a workflow that is easy to break accidentally.
- Bad: could use one or two more cases around partial/manual review payloads.
- Improve next: add edge cases for unmatched review records and malformed review payloads.

### `tests/test_pdf_extract.py` - 3/5
- Does: tests visual-line grouping and script reconstruction behavior.
- Good: covers an important foundational behavior.
- Bad: this file currently contains duplicated imports, duplicated helper definitions, and duplicated test definitions. That is noise at best and a blind-spot risk at worst.
- Improve next: clean the duplication first. This is a good example of a test file that needs maintenance even though the logic it tests is good.

### `tests/test_pipeline_reconciliation.py` - 5/5
- Does: tests paper-level reconciliation and repair gating behavior.
- Good: high-value tests for a subtle layer that could easily become noisy or too aggressive.
- Bad: none significant.
- Improve next: keep it focused on eligibility and reranking logic, not generic classification behavior.

### `tests/test_practice_page.py` - 5/5
- Does: tests the maintained practice page generation, asset handling, bug report config, progress logic, and manual-topic use.
- Good: very strong coverage for a user-facing artifact.
- Bad: none significant.
- Improve next: this file is already doing the right job; keep it aligned with whichever frontend is actually canonical.

### `tests/test_qa.py` - 5/5
- Does: tests deterministic QA, fail/warn behavior, summaries, and static review page embedding.
- Good: clean, practical, and high confidence.
- Bad: none significant.
- Improve next: keep it tightly aligned with QA policy changes.

### `tests/test_question_detection.py` - 5/5
- Does: large regression suite for question detection, mark scheme mapping, prompt crops, subparts, totals, and schema/export expectations.
- Good: this is one of the backbone files of the repo. It covers exactly the kinds of regressions this project tends to suffer.
- Bad: long and intimidating, though that is mostly a cost of the domain.
- Improve next: if it becomes too hard to navigate, split by subsystem, but do not reduce the sample quality.

### `tests/test_sample_pipeline.py` - 4/5
- Does: end-to-end sample pipeline checks using real repo or local PDFs.
- Good: extremely valuable reality check against actual papers.
- Bad: environment- and fixture-dependent, so some cases naturally skip. That makes it less universally reliable than the synthetic suites.
- Improve next: keep it as a smoke/regression layer, and consider a smaller stable fixture subset if you want less skip behavior.

### `tests/test_topic_pdfs.py` - 4/5
- Does: tests topic-PDF validation, grouping, usability filtering, and embedded mark scheme links.
- Good: good coverage for a downstream export path.
- Bad: probably less business-critical than detection/classification, so it should stay secondary in maintenance effort.
- Improve next: keep the tests around the validation boundary, where most real failures will show up.

## Overall Direction

Where the project is strongest:
- detection and mark scheme regression culture
- structured extraction improvements
- local classification debugability
- QA/reporting discipline
- practical operator workflows

Where the project is weakest:
- taxonomy/config consistency across code, config, and frontend
- module size and cohesion in the heuristic core
- schema sprawl in `QuestionRecord`
- stale legacy frontend artifacts

If I were planning the next serious development phase, I would prioritize:
1. taxonomy/config unification
2. modular refactor of `classification.py`, `pipeline.py`, `question_detection.py`, `mark_schemes.py`, and `image_rendering.py`
3. deciding and documenting the single supported student frontend
4. slimming or structuring the exported/debug schema so it stays explainable
