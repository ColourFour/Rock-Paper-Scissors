# P1 Mark Scheme Audit - 2026-07-06

Scope: local `data/step-3/question_bank.json` and `data/step-3/p1/**` image assets.

## Summary

- P1 renderable records checked: 1190.
- Missing referenced question or mark-scheme images: 0 found in this audit pass.
- Duplicate `mark_scheme_image_path`: 0.
- Duplicate `mark_scheme_block_ids`: 0.
- Duplicate mark-scheme image hashes: 34 two-record groups.
- Structural suspects reviewed visually: 23.
- Verified mark-scheme content issues: 5.

## Verified Mark-Scheme Issues

| Question | Type | Finding |
|---|---|---|
| `01autumn08_q09` | incomplete mark scheme | The question has parts (i)-(iii), 12 marks total. The mark-scheme image contains only parts (i)-(ii), 8 marks total; part (iii) is missing. |
| `01autumn08_q10` | extra previous-question information | The mark-scheme image starts with the tail of `q09` part (iii), then continues into `q10`. The `q10` mark scheme itself appears present, but the crop includes extra `q09` material. |
| `11autumn18_q10` | incomplete mark scheme | The question has part (i)(a), part (i)(b), and part (ii), 10 marks total. The mark-scheme image contains only `10(ii)`, 2 marks total; part (i) is missing. |
| `12autumn18_q07` | extra following-question information | The mark-scheme image includes `q07`, then continues with material for later questions (`q08`, `q09`, `q10`, and `q11`). |
| `13summer20_q06` | extra mark-scheme boilerplate | The mark-scheme image contains the complete `q06` scheme, then includes an extra table header row (`Question / Answer / Marks`) from the following section. No next-question answer content was visible. |

## Metadata Suspects Cleared By Visual Review

These records were flagged by metadata totals or mapping status, but the question and mark scheme matched on visual inspection:

`01summer09_q09`, `11autumn14_q11`, `11autumn15_q04`, `11autumn15_q11`, `11autumn17_q03`, `11autumn18_q09`, `11summer25_q01`, `12autumn16_q03`, `12autumn17_q05`, `12spring17_q05`, `12summer13_q08`, `13autumn15_q03`, `13summer14_q09`, `13summer16_q05`, `13summer17_q10`, `13summer25_q05`.

Notes:

- `11autumn17_q03` is a label-style mismatch only: question uses `(a)/(b)` and the mark scheme uses `3(i)/3(ii)`, but the content and marks match.
- `13summer17_q10` is a label/structure detection issue only; the visible mark scheme covers the question.

## Incidental Question-Crop Issues

These are not mark-scheme mismatches, but were visible while reviewing suspects:

| Question | Finding |
|---|---|
| `11summer14_q04` | Question image includes the start of `q05` below `q04`. |
| `12autumn14_q05` | Question image contains duplicated/overlapping question text. |
| `13summer16_q05` | Question image includes footer/junk text after the prompt. |

## Duplicate Mark-Scheme Image Hashes

All duplicate hash groups below contain two records. In every checked case, the associated question content also appears to be the same underlying question, often with minor crop/glyph differences. These look like duplicate session records rather than a reused mark scheme attached to a different question.

| Hash prefix | Records |
|---|---|
| `a985ae985291` | `11spring21_q01`, `11summer21_q01` |
| `5e8d302f3347` | `11spring21_q02`, `11summer21_q02` |
| `b1a6d1b2a663` | `11spring21_q05`, `11summer21_q05` |
| `7c7cbd6e3269` | `11spring21_q07`, `11summer21_q07` |
| `2fff1e4459cb` | `11spring22_q01`, `11summer22_q01` |
| `042e852b5477` | `11spring22_q02`, `11summer22_q02` |
| `cb318fdc3a67` | `11spring22_q03`, `11summer22_q03` |
| `4b544fbf0c4c` | `11spring22_q08`, `11summer22_q08` |
| `fcbda56cce98` | `11spring22_q09`, `11summer22_q09` |
| `05a5923c4148` | `11spring23_q01`, `11summer23_q01` |
| `364ae2f8dd2e` | `11spring23_q02`, `11summer23_q02` |
| `5c1f4f0f54bb` | `12spring21_q02`, `12summer21_q02` |
| `d1a1a46c8e60` | `12spring21_q03`, `12summer21_q03` |
| `a62e8a4c9321` | `12spring21_q04`, `12summer21_q04` |
| `c4222e877159` | `12spring22_q03`, `12summer22_q03` |
| `7f418a22fef9` | `12spring22_q09`, `12summer22_q09` |
| `9736184b95e2` | `12spring23_q01`, `12summer23_q01` |
| `b8cc71ec1afb` | `12spring23_q02`, `12summer23_q02` |
| `cd1bedfeb99a` | `12spring23_q04`, `12summer23_q04` |
| `cccdd8652c7a` | `12spring23_q06`, `12summer23_q06` |
| `7395f48fc84b` | `13spring21_q01`, `13summer21_q01` |
| `ed3148afead8` | `13spring21_q02`, `13summer21_q02` |
| `86179650a2c9` | `13spring21_q03`, `13summer21_q03` |
| `8493dfca9e94` | `13spring21_q04`, `13summer21_q04` |
| `0f0ca429de8d` | `13spring22_q01`, `13summer22_q01` |
| `816051def24c` | `13spring22_q02`, `13summer22_q02` |
| `02d546ae983d` | `13spring22_q03`, `13summer22_q03` |
| `b3c5ba2a9597` | `13spring22_q05`, `13summer22_q05` |
| `ed1b734ebe00` | `13spring23_q02`, `13summer23_q02` |
| `2a12b1c6312c` | `13spring23_q06`, `13summer23_q06` |
| `765651091052` | `13spring23_q07`, `13summer23_q07` |
| `46ea0869f8f9` | `13spring23_q08`, `13summer23_q08` |
| `43e3030a3114` | `13spring23_q09`, `13summer23_q09` |
| `97fce7dd0c41` | `13spring24_q01`, `13summer24_q01` |

