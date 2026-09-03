# CAIE 9709 Practice Page

This repository is only the GitHub Pages deployment repo for:

```text
https://colourfour.github.io/Rock-Paper-Scissors/
```

The root landing page is preserved in `index.html`. The old extraction pipeline, generated practice app, and generated image exports have been removed from this repo.

The extraction pipeline now lives in the newer `exam-bank` project. Future updates should be copied into this repo from that project's clean static export, not generated here.

## Current State

- `index.html` is the public landing page.
- `assets/` contains the artwork directly used by the landing page.
- `p1/`, `p3/`, `p4/`, and `p5/` are static practice pages.
- `proof-court/` contains the Court of Proof introductory proof game.
- `data/step-3/question_bank.json` contains exported question metadata copied from the newer exam-bank project.
- `data/step-3/question_bank.topic_routing.v1.json` contains the current keyed topic-routing sidecar.
- `data/step-3/p1/`, `data/step-3/p3/`, `data/step-3/p4/`, and `data/step-3/p5/` contain exported question and mark-scheme PNGs.
- `.github/workflows/pages.yml` deploys the static site to GitHub Pages.

## Export Shape

The practice pages use this structure:

```text
index.html
assets/
p1/index.html
p3/index.html
p4/index.html
p5/index.html
proof-court/index.html
data/step-3/question_bank.json
data/step-3/question_bank.topic_routing.v1.json
data/step-3/p1/
data/step-3/p3/
data/step-3/p4/
data/step-3/p5/
```

The practice pages render question and mark-scheme PNGs from `data/step-3`. They do not render OCR question text or mark-scheme text as the main content.

Question records without both question and mark-scheme image paths are skipped by the static page. Difficulty is intentionally not shown because the current export does not provide a reliable metric for students.

The topic filter uses a fixed syllabus-level taxonomy for each paper family. `question_bank.topic_routing.v1.json` is preferred when a routed topic is available; otherwise the page falls back to `question_bank.json` and forces the record into the nearest displayed topic bucket at render time.

See `REBUILD_NOTES.md` before copying in a future export.
