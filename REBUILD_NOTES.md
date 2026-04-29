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
data/json/question_bank.json
data/json/question_bank.deepseek.full.json
data/json/image_availability.json
data/images/p1/
data/images/p3/
data/images/p4/
data/images/p5/
```

The future P1, P3, P4, and P5 pages should load only from `data/json` and `data/images`.

`data/json/image_availability.json` may be regenerated during deployment prep from the copied PNG files. Do not edit `question_bank.json` to remove records just because an image is missing.

They should not depend on the old `practice/`, `output/`, or `site-data/` structure.
