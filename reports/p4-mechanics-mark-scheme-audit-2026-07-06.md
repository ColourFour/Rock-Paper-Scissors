# P4 Mechanics Mark Scheme Audit - 2026-07-06

Scope: local `data/step-3/question_bank.json` and `data/step-3/p4/**` image assets. P4 is the mechanics family in this static bank.

## Summary

- P4/mechanics renderable records checked: 770.
- Missing referenced question or mark-scheme images: 0 found in this audit pass.
- Duplicate `mark_scheme_image_path`: 0.
- Duplicate `mark_scheme_block_ids`: 0.
- Duplicate mark-scheme image hashes: 24 two-record groups.
- Structural mark-scheme suspects reviewed visually: 24.
- Additional explicit table-header candidates reviewed visually: 5 unique records outside the structural-suspect set.
- Verified mark-scheme content issues: 10.

No visually confirmed P4 case was found where the mark scheme belongs to a different question or where required parts of the mark scheme are missing. The confirmed issues are extra crop content.

## Metadata Counts

| Field | Counts |
|---|---|
| `mapping_status` | `pass`: 768, `fail`: 2 |
| `scope_quality_status` | `clean`: 653, `review`: 111, `fail`: 6 |
| `validation_status` | `pass`: 542, `review`: 212, `fail`: 16 |
| `mark_scheme_crop_confidence` | `high`: 649, `medium`: 121 |

The 2024/2025 `scope_quality_status=review` records are mostly driven by low question-crop confidence and cross-page question scope; their mark-scheme crops are high/medium confidence and paper totals match.

## Verified Mark-Scheme Issues

| Question | Type | Finding |
|---|---|---|
| `41summer19_q01` | extra mark-scheme boilerplate | Mark-scheme image contains the complete `q01` scheme, then includes an extra table header row (`Question / Answer / Mark / Guidance`) from the following section. |
| `41summer20_q01` | extra mark-scheme boilerplate | Mark-scheme image contains the complete `q01` scheme, then includes an extra table header row (`Question / Answer / Marks`) from the following section. |
| `41autumn20_q06` | extra mark-scheme boilerplate | Mark-scheme image contains the complete `q06` scheme, then includes an extra table header row from the following section. |
| `42summer11_q07` | extra previous-question information | Mark-scheme image starts with the tail of an alternative method for `q06`, then continues into the complete `q07` scheme. |
| `43summer20_q01` | extra mark-scheme boilerplate | Mark-scheme image contains the complete `q01` scheme, then includes an extra table header row from the following section. |
| `43summer20_q03` | extra mark-scheme boilerplate | Mark-scheme image contains the complete `q03` scheme, then includes an extra table header row from the following section. |
| `43spring21_q03` | extra mark-scheme boilerplate | Mark-scheme image contains the complete `q03` scheme, then includes an extra table header row (`Question / Answer / Marks / Guidance`) from the following section. |
| `43summer21_q03` | extra mark-scheme boilerplate | Same crop pattern as `43spring21_q03`: complete `q03` scheme plus an extra table header row. |
| `43spring22_q03` | extra mark-scheme boilerplate | Mark-scheme image contains the complete `q03` scheme, then includes an extra table header row from the following section. |
| `43summer22_q03` | extra mark-scheme boilerplate | Same crop pattern as `43spring22_q03`: complete `q03` scheme plus an extra table header row. |

## Metadata Suspects Cleared By Visual Review

These records were flagged by mapping status, scope status, or duplicate-image metadata, but the question and mark scheme matched on visual inspection:

`41spring21_q06`, `41spring23_q05`, `41summer12_q04`, `41summer16_q07`, `41summer18_q02`, `41summer21_q06`, `41summer23_q05`, `42autumn11_q07`, `42spring22_q05`, `42summer11_q01`, `42summer22_q05`, `43autumn10_q05`, `43autumn12_q01`, `43autumn16_q03`, `43spring22_q06`, `43summer13_q03`, `43summer15_q04`, `43summer17_q02`, `43summer22_q06`.

Notes:

- `41spring23_q05` and `41summer23_q05` share the same mark-scheme image hash, but visual review shows the same underlying question and matching scheme. The question-image hashes differ because the question renderings differ.
- `41spring21_q06`/`41summer21_q06`, `42spring22_q05`/`42summer22_q05`, and `43spring22_q06`/`43summer22_q06` also have duplicate mark-scheme hashes with different question-image hashes, but the visible questions and schemes match.
- The mapping failures `41summer18_q02` and `43summer17_q02` were not mark-scheme mismatches on visual review.

## Incidental Question-Crop Issues

These are not mark-scheme mismatches, but were visible while reviewing suspects:

| Question | Finding |
|---|---|
| `41summer18_q02` | Question image is bottom-truncated; the mark scheme itself matches `q02`. |
| `41summer23_q05` | Question image includes a duplicated diagram fragment below the intended question crop. |
| `43summer15_q04` | Question image starts with the tail of previous-question text before `q04`; the mark scheme itself matches `q04`. |

## Duplicate Mark-Scheme Image Hashes

All duplicate hash groups below contain two records. Most are duplicate spring/summer records with the same underlying question and mark scheme. No duplicate `mark_scheme_image_path` or duplicate `mark_scheme_block_ids` were found.

| Hash prefix | Records | Note |
|---|---|---|
| `00aa4bb8c687` | `43spring23_q02`, `43summer23_q02` | same question-image hash |
| `07858d027f16` | `43spring22_q01`, `43summer22_q01` | same question-image hash |
| `0798751e7f3a` | `43spring22_q05`, `43summer22_q05` | same question-image hash |
| `0935e9acf9cc` | `41spring23_q05`, `41summer23_q05` | different question-image hash; visually same underlying question |
| `177b1b51f949` | `41spring21_q05`, `41summer21_q05` | same question-image hash |
| `2acf8e5d3225` | `41spring21_q06`, `41summer21_q06` | different question-image hash; visually same underlying question |
| `2d1104d31d39` | `42spring21_q01`, `42summer21_q01` | same question-image hash |
| `3313b3795bec` | `42spring22_q01`, `42summer22_q01` | same question-image hash |
| `3fbc9cc05660` | `41spring21_q01`, `41summer21_q01` | same question-image hash |
| `4304785260ab` | `41spring21_q03`, `41summer21_q03` | same question-image hash |
| `65f895b1b97c` | `41spring22_q03`, `41summer22_q03` | same question-image hash |
| `71648d756990` | `43spring22_q02`, `43summer22_q02` | same question-image hash |
| `72bde75d3574` | `41spring23_q01`, `41summer23_q01` | same question-image hash |
| `7a22e9c4502c` | `43spring21_q02`, `43summer21_q02` | same question-image hash |
| `8c5e260bd123` | `43spring22_q06`, `43summer22_q06` | different question-image hash; visually same underlying question |
| `a26b02644e11` | `43spring23_q01`, `43summer23_q01` | same question-image hash |
| `ac40ab8ad7ae` | `41spring22_q02`, `41summer22_q02` | same question-image hash |
| `b498432b4324` | `42spring22_q05`, `42summer22_q05` | different question-image hash; visually same underlying question |
| `b6b82d395ea0` | `43spring21_q01`, `43summer21_q01` | same question-image hash |
| `c6296fc5e29b` | `41spring22_q07`, `41summer22_q07` | same question-image hash |
| `cd01f40ff311` | `42spring23_q01`, `42summer23_q01` | same question-image hash |
| `d087535111a3` | `43spring22_q03`, `43summer22_q03` | different question-image hash; visually same underlying question, same extra table-header crop |
| `e8f9a76306b1` | `43spring21_q03`, `43summer21_q03` | different question-image hash; visually same underlying question, same extra table-header crop |
| `ff3b2fb0a3c1` | `43spring21_q06`, `43summer21_q06` | same question-image hash |

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
