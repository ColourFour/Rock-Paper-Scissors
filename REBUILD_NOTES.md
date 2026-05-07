# Rebuild Notes

This repo is the static GitHub Pages deployment target. The future rebuild should copy in a clean static export from the newer exam-bank project.

Intended structure:

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

The future P1, P3, P4, and P5 pages should load only from `data/step-2/json` and `data/step-2`.

`data/step-2/json/image_availability.json` may be regenerated during deployment prep from the copied PNG files. Do not edit `question_bank.json` to remove records just because an image is missing.

They should not depend on the old `practice/`, `output/`, or `site-data/` structure.
