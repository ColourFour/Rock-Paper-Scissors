# P3 Mark Scheme Audit - 2026-07-06

Scope: local `data/step-3/question_bank.json` and `data/step-3/p3/**` image assets.

## Summary

- P3 renderable records checked: 1184.
- Missing referenced question or mark-scheme images: 0 found in this audit pass.
- Duplicate `mark_scheme_image_path`: 0.
- Duplicate `mark_scheme_block_ids`: 0.
- Duplicate mark-scheme image hashes: 100 two-record groups.
- Structural suspects reviewed visually: 41.
- Verified mark-scheme content issues: 20.
- No visually confirmed P3 case was found where the mark scheme is for the wrong question or where required parts of the mark scheme are missing. The confirmed issues are extra crop content.

## Verified Mark-Scheme Issues

| Question | Type | Finding |
|---|---|---|
| `03autumn08_q06` | extra previous-question information | Mark-scheme image starts with the tail of the previous question's answer/guidance, then continues into `q06`. |
| `31autumn10_q06` | extra previous-question information | Mark-scheme image starts with the tail of the previous question's answer, then continues into `q06`. |
| `31autumn13_q06` | extra previous-question information | Mark-scheme image starts with the tail of the previous question's part (ii), then continues into `q06`. |
| `31autumn13_q10` | extra previous-question information | Mark-scheme image starts with the tail of earlier mark-scheme material, then continues into `q10`. |
| `31summer10_q04` | extra previous-question information | Mark-scheme image starts with part (ii) from the previous question, then continues into `q04`. |
| `31summer11_q06` | extra previous-question information | Mark-scheme image starts with the previous question's final answer line, then continues into `q06`. |
| `31summer12_q04` | extra previous-question information | Mark-scheme image starts with the previous question's final line, then continues into `q04`. |
| `31summer14_q08` | extra previous-question information | Mark-scheme image starts with the tail of `q07(iii)`, then continues into `q08`. |
| `32autumn10_q06` | extra previous-question information | Same crop pattern as `31autumn10_q06`: previous-question tail before `q06`. |
| `32autumn13_q06` | extra previous-question information | Same crop pattern as `31autumn13_q06`: previous-question part (ii) tail before `q06`. |
| `32autumn14_q09` | extra previous-question information | Mark-scheme image starts with the tail of `q08(iii)`, then continues into `q09`. |
| `32summer12_q02` | extra previous-question information | Mark-scheme image starts with a previous-question final line, then continues into `q02`. |
| `32summer15_q05` | extra previous-question information | Mark-scheme image starts with a previous-question guidance line, then continues into `q05`. |
| `33autumn10_q04` | extra previous-question information | Mark-scheme image starts with part (ii) from the previous question, then continues into `q04`. |
| `33autumn14_q06` | extra previous-question information | Mark-scheme image starts with the tail of `q05(ii)`, then continues into `q06`. |
| `33autumn14_q09` | extra previous-question information | Mark-scheme image starts with the tail of the previous question, then continues into `q09`. |
| `33summer10_q08` | extra previous-question information | Mark-scheme image starts with the tail of a previous integration answer, then continues into `q08`. |
| `33summer16_q03` | extra previous-question fragment | Mark-scheme image starts with a leftover previous-question mark bracket (`[2]`), then continues into `q03`. |
| `33summer19_q04` | extra mark-scheme boilerplate | Mark-scheme image contains the complete `q04` scheme, then includes an extra table header row (`Question / Answer / Marks / Guidance`) from the following section. |
| `33summer25_q02` | extra mark-scheme boilerplate | Mark-scheme image contains the complete `q02` scheme, then includes an extra table header row from the following section. |

## Metadata Suspects Cleared By Visual Review

These records were flagged by metadata totals or mapping status, but the question and mark scheme matched on visual inspection:

`31autumn14_q08`, `31autumn15_q09`, `31autumn15_q10`, `31autumn18_q08`, `31summer13_q10`, `31summer14_q05`, `31summer14_q07`, `31summer14_q09`, `32autumn14_q08`, `32autumn15_q09`, `32autumn15_q10`, `32summer25_q04`, `33autumn11_q07`, `33autumn14_q05`, `33autumn18_q08`, `33autumn19_q09`, `33summer13_q04`, `35spring25_q07`, `35summer25_q02`, `35summer25_q07`.

Notes:

- `31autumn18_q08` and `33autumn18_q08` are label-style mismatches only: the question uses `(a)/(b)` and the mark scheme uses `8(i)/8(ii)`, but content and marks match.
- `33autumn19_q09` is marked as a partial block in metadata, but visually the scheme covers both parts.
- `35spring25_q07` and `35summer25_q07` are terminal-total detection issues only; the mark-scheme content is present.

## Incidental Question-Crop Issues

These are not mark-scheme mismatches, but were visible while reviewing suspects:

| Question | Finding |
|---|---|
| `31summer12_q04` | Question image includes the start of `q05` below `q04`. |
| `32autumn14_q02` | Question image includes additional following questions (`q03`, `q04`, and the start of `q05`) below `q02`. |

## Duplicate Mark-Scheme Image Hashes

All duplicate hash groups below contain two records. The groups are mostly duplicate component/session records or duplicate rendered crops across related variants. No duplicate `mark_scheme_image_path` or duplicate `mark_scheme_block_ids` were found.

| Hash prefix | Records |
|---|---|
| `07933212471d` | `31autumn10_q01`, `32autumn10_q01` |
| `efd439d6a14f` | `31autumn10_q02`, `32autumn10_q02` |
| `2654486e65f7` | `31autumn10_q03`, `32autumn10_q03` |
| `4ee39570742b` | `31autumn10_q04`, `32autumn10_q04` |
| `efb13baf2e0f` | `31autumn10_q05`, `32autumn10_q05` |
| `a4453f420665` | `31autumn10_q06`, `32autumn10_q06` |
| `9db4ec37f529` | `31autumn10_q07`, `32autumn10_q07` |
| `d5f66377afeb` | `31autumn10_q08`, `32autumn10_q08` |
| `a818e102e65e` | `31autumn10_q09`, `32autumn10_q09` |
| `0717da150fba` | `31autumn10_q10`, `32autumn10_q10` |
| `19c9838d6b7b` | `31autumn11_q01`, `32autumn11_q01` |
| `b63b251f4ff3` | `31autumn11_q02`, `32autumn11_q02` |
| `cec897c25b49` | `31autumn11_q03`, `32autumn11_q03` |
| `28c6fd800f4f` | `31autumn11_q04`, `32autumn11_q04` |
| `d80ab12c3ac3` | `31autumn11_q05`, `32autumn11_q05` |
| `ec652a320a17` | `31autumn11_q06`, `32autumn11_q06` |
| `26030a9375e1` | `31autumn11_q07`, `32autumn11_q07` |
| `306e1b5faa3e` | `31autumn11_q08`, `32autumn11_q08` |
| `4c14fb591128` | `31autumn11_q09`, `32autumn11_q09` |
| `78d87fae390f` | `31autumn11_q10`, `32autumn11_q10` |
| `d9099205b8d0` | `31autumn15_q01`, `32autumn15_q01` |
| `f5f46bc54c0f` | `31autumn15_q02`, `32autumn15_q02` |
| `40eba46900f8` | `31autumn15_q03`, `32autumn15_q03` |
| `85441eececbf` | `31autumn15_q04`, `32autumn15_q04` |
| `c93a334df7c8` | `31autumn15_q05`, `32autumn15_q05` |
| `1b8bb24fd670` | `31autumn15_q06`, `32autumn15_q06` |
| `b2cd42134582` | `31autumn15_q07`, `32autumn15_q07` |
| `2916a6f6fd5e` | `31autumn15_q08`, `32autumn15_q08` |
| `161998a7a697` | `31autumn15_q09`, `32autumn15_q09` |
| `8898850248e7` | `31autumn15_q10`, `32autumn15_q10` |
| `b9f4ef0d9484` | `31autumn16_q01`, `32autumn16_q01` |
| `2b467c701177` | `31autumn16_q02`, `32autumn16_q02` |
| `0cbfd115977e` | `31autumn16_q03`, `32autumn16_q03` |
| `d3d79bfae26c` | `31autumn16_q04`, `32autumn16_q04` |
| `69a4955936fe` | `31autumn16_q05`, `32autumn16_q05` |
| `473db975bdd5` | `31autumn16_q06`, `32autumn16_q06` |
| `760d24744727` | `31autumn16_q07`, `32autumn16_q07` |
| `f06879b2b304` | `31autumn16_q08`, `32autumn16_q08` |
| `0b1ac2fd9491` | `31autumn16_q09`, `32autumn16_q09` |
| `c11fbf407577` | `31autumn16_q10`, `32autumn16_q10` |
| `09bb54b37dd4` | `31autumn18_q02`, `33autumn18_q02` |
| `219c4310041e` | `31autumn18_q03`, `33autumn18_q03` |
| `d0b716c71c41` | `31autumn18_q04`, `33autumn18_q04` |
| `a8c61695d695` | `31autumn18_q06`, `33autumn18_q06` |
| `be762d62356e` | `31autumn18_q07`, `33autumn18_q07` |
| `7cacca97fff2` | `31autumn18_q10`, `33autumn18_q10` |
| `7f37b53f25ef` | `31autumn20_q01`, `33autumn20_q01` |
| `08c8491d8a40` | `31autumn20_q02`, `33autumn20_q02` |
| `0bd896bfe29d` | `31autumn20_q03`, `33autumn20_q03` |
| `c20440354f1c` | `31autumn20_q04`, `33autumn20_q04` |
| `6ab7714773cc` | `31autumn20_q06`, `33autumn20_q06` |
| `9dbaea1617b9` | `31autumn20_q07`, `33autumn20_q07` |
| `ad1af51882ae` | `31autumn20_q08`, `33autumn20_q08` |
| `35cae9beca25` | `31autumn20_q09`, `33autumn20_q09` |
| `b011630fc4e6` | `31autumn20_q10`, `33autumn20_q10` |
| `8904770a24c6` | `31autumn20_q11`, `33autumn20_q11` |
| `42f883be6fe6` | `31spring21_q01`, `31summer21_q01` |
| `b9cde340d186` | `31spring21_q02`, `31summer21_q02` |
| `efd808e0d710` | `31spring21_q03`, `31summer21_q03` |
| `c860ec01b27e` | `31spring22_q01`, `31summer22_q01` |
| `907e8c58d04b` | `31spring22_q02`, `31summer22_q02` |
| `a19f5be4f447` | `31spring22_q03`, `31summer22_q03` |
| `f9e44aef2ea6` | `31spring22_q04`, `31summer22_q04` |
| `e59ef359eeb8` | `31spring22_q06`, `31summer22_q06` |
| `d0117d21f836` | `31spring22_q07`, `31summer22_q07` |
| `5ede247a4b75` | `31spring22_q08`, `31summer22_q08` |
| `e538679e5234` | `31spring22_q09`, `31summer22_q09` |
| `d7f3063f645f` | `31spring23_q03`, `31summer23_q03` |
| `756b223ca04b` | `31spring23_q05`, `31summer23_q05` |
| `cafdded09b00` | `31spring23_q08`, `31summer23_q08` |
| `aa4a907060f4` | `31spring23_q09`, `31summer23_q09` |
| `6e8d66300a20` | `31spring24_q01`, `31summer24_q01` |
| `56ed72b3dd6e` | `31spring24_q03`, `31summer24_q03` |
| `fe5a012fca60` | `32spring21_q01`, `32summer21_q01` |
| `de5b8752b531` | `32spring21_q05`, `32summer21_q05` |
| `ff782fb9886b` | `32spring21_q07`, `32summer21_q07` |
| `88bf647d2026` | `32spring21_q08`, `32summer21_q08` |
| `e898f160e7df` | `32spring21_q09`, `32summer21_q09` |
| `f2dc04a1bec4` | `32spring22_q01`, `32summer22_q01` |
| `a9816c268ee6` | `32spring22_q02`, `32summer22_q02` |
| `462b0f6687e6` | `32spring22_q04`, `32summer22_q04` |
| `f709b99856d4` | `32spring22_q06`, `32summer22_q06` |
| `54aa0e1a5251` | `32spring22_q07`, `32summer22_q07` |
| `ff22c5535744` | `32spring22_q08`, `32summer22_q08` |
| `64b24067070d` | `32spring23_q01`, `32summer23_q01` |
| `9a526c149ef2` | `32spring23_q04`, `32summer23_q04` |
| `25d1eea073a9` | `32spring23_q05`, `32summer23_q05` |
| `ab851474db77` | `32spring23_q08`, `32summer23_q08` |
| `309016bb2897` | `33spring21_q01`, `33summer21_q01` |
| `a3736deb9422` | `33spring21_q02`, `33summer21_q02` |
| `ce68d59635fa` | `33spring21_q03`, `33summer21_q03` |
| `11e724401c0f` | `33spring21_q04`, `33summer21_q04` |
| `fc1422101657` | `33spring21_q07`, `33summer21_q07` |
| `21a9be6cf1af` | `33spring21_q08`, `33summer21_q08` |
| `61a8d33f1b70` | `33spring21_q10`, `33summer21_q10` |
| `6d5886d61bfb` | `33spring22_q01`, `33summer22_q01` |
| `8859d4d0447d` | `33spring22_q03`, `33summer22_q03` |
| `2996a9f2db72` | `33spring23_q02`, `33summer23_q02` |
| `c59ed425a940` | `33spring23_q04`, `33summer23_q04` |
| `0c5d61992f72` | `33spring23_q05`, `33summer23_q05` |

