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
data/step-3/question_bank.json
data/step-3/question_bank.topic_routing.v1.json
data/step-3/p1/
data/step-3/p3/
data/step-3/p4/
data/step-3/p5/
```

The future P1, P3, P4, and P5 pages should load from `data/step-3`.

`data/step-3/question_bank.topic_routing.v1.json` is a sidecar keyed by `question_id`; do not treat it as an array. Records without a routed topic should fall back to the `topic` field in `question_bank.json`.

The static page should display only the fixed syllabus-level topic buckets for each paper family and force every record into one of those buckets at render time. Difficulty should remain absent from the webpage until there is a reliable metric.

Do not edit `question_bank.json` to remove records just because an image or mark-scheme path is missing. The static page should skip records that cannot render both required PNGs.

They should not depend on the old `practice/`, `output/`, or `site-data/` structure.
