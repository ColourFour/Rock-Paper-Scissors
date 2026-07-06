# P5 Statistics Mark Scheme Audit - 2026-07-06

Scope: local `data/step-3/question_bank.json` and `data/step-3/p5/**` image assets. P5 is the statistics family in this static bank.

## Summary

- P5/statistics renderable records checked: 740.
- Missing referenced question or mark-scheme images: 0 found in this audit pass.
- Duplicate `mark_scheme_image_path`: 0.
- Duplicate `mark_scheme_block_ids`: 0.
- Duplicate mark-scheme image hashes: 24 two-record groups.
- Structural mark-scheme suspects reviewed visually: 16.
- Additional explicit table-header candidates reviewed visually: 3.
- Verified mark-scheme content issues: 7.

No visually confirmed P5 case was found where the mark scheme belongs to a different question. The confirmed issues are incomplete crops or extra crop content.

## Metadata Counts

| Field | Counts |
|---|---|
| `mapping_status` | `pass`: 728, `fail`: 12 |
| `scope_quality_status` | `clean`: 645, `review`: 93, `fail`: 2 |
| `validation_status` | `pass`: 610, `review`: 87, `fail`: 43 |
| `mark_scheme_crop_confidence` | `high`: 609, `medium`: 131 |

The 2025 `scope_quality_status=review` records are mostly driven by low question-crop confidence and cross-page question scope; their mark-scheme crops are high/medium confidence and paper totals match.

## Verified Mark-Scheme Issues

| Question | Type | Finding |
|---|---|---|
| `51summer20_q05` | extra mark-scheme boilerplate | Mark-scheme image contains the complete `q05` scheme, then includes an extra table header row (`Question / Answer / Marks`) from the following section. |
| `53summer20_q02` | extra mark-scheme boilerplate | Mark-scheme image contains the complete `q02` scheme, then includes an extra table header row from the following section. |
| `53summer20_q06` | extra mark-scheme boilerplate | Mark-scheme image contains the complete `q06` scheme, then includes an extra table header row from the following section. |
| `61autumn18_q06` | incomplete mark scheme | Question has parts (i)-(iii), 6 marks total. The mark-scheme image contains only `6(iii)`, 6 marks; parts (i)-(ii) are missing from the crop. The crop also includes an extra table header below the answer. |
| `61summer16_q06` | incomplete mark scheme | Question has `6(a)(i)`, `6(a)(ii)`, and `6(b)`, 11 marks total. The mark-scheme image contains `6(a)(i)` and starts `6(a)(ii)`, then stops; the rest of `6(a)(ii)` and `6(b)` are missing. |
| `63autumn19_q06` | extra following-question information | Mark-scheme image contains the complete `q06` scheme, then continues into the start of `q07(i)(a)`. |
| `63autumn19_q07` | incomplete mark scheme | Question has `q07(i)(a)`, `q07(i)(b)`, and `q07(ii)`. The mark-scheme image contains only `q07(ii)`, so `q07(i)(a)` and `q07(i)(b)` are missing. |

## Metadata Suspects Cleared By Visual Review

These records were flagged by mapping status, scope status, or duplicate-image metadata, but the question and mark scheme matched on visual inspection:

`06summer09_q01`, `53spring23_q04`, `53summer23_q04`, `61summer16_q03`, `61summer16_q05`, `61summer16_q07`, `61summer17_q01`, `62autumn18_q01`, `62autumn18_q07`, `62spring17_q02`, `63summer14_q07`, `63summer18_q07`.

Notes:

- `53spring23_q04` and `53summer23_q04` share the same mark-scheme image hash, but visual review shows the same underlying question and matching scheme. The question-image hashes differ because the question renderings differ.
- `06summer09_q01` and `63summer14_q07` were scope failures in metadata, but the mark schemes themselves match their questions.

## Duplicate Mark-Scheme Image Hashes

All duplicate hash groups below contain two records. Most are duplicate spring/summer records with the same underlying question and mark scheme. No duplicate `mark_scheme_image_path` or duplicate `mark_scheme_block_ids` were found.

| Hash prefix | Records | Note |
|---|---|---|
| `02c404ff132f` | `52spring22_q03`, `52summer22_q03` | same question-image hash |
| `0c96bc4101d9` | `52spring21_q04`, `52summer21_q04` | same question-image hash |
| `119ce6e43a87` | `51spring21_q01`, `51summer21_q01` | same question-image hash |
| `1d4d45e07bb6` | `52spring22_q01`, `52summer22_q01` | same question-image hash |
| `341a2837e4dc` | `53spring22_q05`, `53summer22_q05` | same question-image hash |
| `3b7664c136ab` | `51spring22_q02`, `51summer22_q02` | same question-image hash |
| `4e080cc175db` | `51spring23_q02`, `51summer23_q02` | same question-image hash |
| `50047d7a76fd` | `52spring22_q04`, `52summer22_q04` | same question-image hash |
| `54e4d8a13d5e` | `53spring23_q04`, `53summer23_q04` | different question-image hash; visually same underlying question |
| `59aa0dd07641` | `51spring21_q02`, `51summer21_q02` | same question-image hash |
| `61096c0ac2d5` | `53spring21_q04`, `53summer21_q04` | same question-image hash |
| `73e15853937d` | `53spring23_q03`, `53summer23_q03` | same question-image hash |
| `7c19e39a71d0` | `51spring23_q01`, `51summer23_q01` | same question-image hash |
| `929ef893cc5f` | `51spring22_q01`, `51summer22_q01` | same question-image hash |
| `a5f1e9c07e00` | `51spring23_q03`, `51summer23_q03` | same question-image hash |
| `b004ea144d04` | `53spring21_q02`, `53summer21_q02` | same question-image hash |
| `b82aa2aa8d78` | `52spring22_q05`, `52summer22_q05` | same question-image hash |
| `cf1ebc8be520` | `52spring21_q02`, `52summer21_q02` | same question-image hash |
| `d71dd67d1d19` | `53spring21_q05`, `53summer21_q05` | same question-image hash |
| `d9134228a4cb` | `51spring23_q04`, `51summer23_q04` | same question-image hash |
| `dcdbea451450` | `53spring23_q02`, `53summer23_q02` | same question-image hash |
| `ed7f5d443d4c` | `53spring23_q01`, `53summer23_q01` | same question-image hash |
| `f0ddae0cb86b` | `52spring21_q01`, `52summer21_q01` | same question-image hash |
| `fd62094e6975` | `53spring22_q02`, `53summer22_q02` | same question-image hash |

## Validation

`python3 scripts/ingest_exam_bank_static.py --validate-only` passed:

```json
{
  "missing_referenced_image_examples": [],
  "missing_referenced_images": 0,
  "validated_renderable_by_family": {
    "p1": 1190,
    "p3": 1184,
    "p4": 770,
    "p5": 740
  },
  "validated_renderable_records": 3884
}
```
