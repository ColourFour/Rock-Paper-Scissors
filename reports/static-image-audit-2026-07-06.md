# Static Image Audit - 2026-07-06

Scope: published GitHub Pages data at `https://colourfour.github.io/Rock-Paper-Scissors/`, cross-checked against local `data/step-3`. The published `question_bank.json` byte length matched the local file.

## Summary

- total_records: 4113
- renderable_records: 3884
- renderable_by_family: {'p1': 1190, 'p3': 1184, 'p4': 770, 'p5': 740}
- ingested_renderable_records: 3256
- retained_renderable_records: 628
- missing_referenced_images: 0
- source_pairs_checked: 3256
- source_pairs_ok: 3256
- mark_scheme_block_id_checked: 3256
- mark_scheme_block_id_ok: 3256
- confirmed_question_count: 4
- risk_question_count: 1595

## Confirmed Findings

| Question | Type | Details | Visual observation |
|---|---|---|---|
| `13autumn19_q10` | `route_topic_family_mismatch` | primary_topic_id 9709_p3_topic_vectors does not match family p1 |  |
| `31autumn15_q02` | `question_image_cropped_too_short` | Question image size (1578, 75); mark scheme size (1541, 251) | Question image stops after "correct to"; mark scheme matches the visible question start. |
| `32autumn15_q02` | `question_image_cropped_too_short` | Question image size (1578, 75); mark scheme size (1541, 251) | Question image stops after "correct to"; same crop defect as 31autumn15_q02. |
| `62autumn14_q05` | `question_image_cropped_too_short` | Question image size (1578, 70); mark scheme size (1556, 725) | Question image stops after "normal distribution with mean"; mark scheme is for q05. |

## Risk Buckets

- pipeline_image_review_flags: 1594
- validation_status_review_with_image_flags: 686
- mark_scheme_crop_confidence_review: 601
- validation_status_fail: 125
- mapping_status_not_pass: 30

Full row-level details are in the CSV and JSON reports beside this file.
