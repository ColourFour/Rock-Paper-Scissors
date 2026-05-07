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
- `data/step-2/json/` contains exported metadata copied from the newer exam-bank project.
- `data/step-2/p1/`, `data/step-2/p3/`, `data/step-2/p4/`, and `data/step-2/p5/` contain exported question and mark-scheme PNGs.
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
data/step-2/json/question_bank.json
data/step-2/json/question_bank.deepseek.json
data/step-2/json/image_availability.json
data/step-2/p1/
data/step-2/p3/
data/step-2/p4/
data/step-2/p5/
```

The practice pages render question and mark-scheme PNGs from `data/step-2`. They do not render OCR question text or mark-scheme text as the main content.

`image_availability.json` is a deployment helper generated from the copied image files. It lets the static pages skip records whose PNGs are not present without mutating the exported question bank.

See `REBUILD_NOTES.md` before copying in a future export.
