from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
QUESTION_BANK = ROOT / "output" / "json" / "question_bank.json"
OUTPUT_ROOT = ROOT / "output"
PRACTICE_DIR = ROOT / "practice"
MANIFEST_PATH = PRACTICE_DIR / "manifest.json"


PAPER_LABELS = {
    "p1": "Pure Mathematics 1",
    "p3": "Pure Mathematics 3",
    "p4": "Mechanics",
    "p5": "Probability & Statistics",
}


def main() -> None:
    records = json.loads(QUESTION_BANK.read_text(encoding="utf-8"))
    manifest_records: list[dict[str, Any]] = []
    skipped = 0

    for record in records:
        question_paths = record.get("question_image_paths") or []
        mark_scheme_paths = record.get("mark_scheme_image_paths") or []
        if not question_paths or not mark_scheme_paths:
            skipped += 1
            continue

        question_path = str(question_paths[0])
        mark_scheme_path = str(mark_scheme_paths[0])
        if not (OUTPUT_ROOT / question_path).exists() or not (OUTPUT_ROOT / mark_scheme_path).exists():
            skipped += 1
            continue

        family = str(record.get("paper_family", "")).lower()
        manifest_records.append(
            {
                "id": record.get("question_id"),
                "paper": record.get("paper"),
                "paperFamily": family,
                "paperLabel": PAPER_LABELS.get(family, family.upper()),
                "questionNumber": record.get("question_number"),
                "topic": record.get("topic") or "unknown",
                "marks": record.get("question_solution_marks"),
                "questionImage": f"../output/{question_path}",
                "markSchemeImage": f"../output/{mark_scheme_path}",
            }
        )

    manifest_records.sort(key=lambda item: (item["paperFamily"], str(item["paper"]), int(item["questionNumber"] or 0)))
    payload = {
        "generatedFrom": "output/json/question_bank.json",
        "count": len(manifest_records),
        "skippedMissingImages": skipped,
        "papers": PAPER_LABELS,
        "questions": manifest_records,
    }

    PRACTICE_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(manifest_records)} practice questions to {MANIFEST_PATH}")
    if skipped:
        print(f"Skipped {skipped} records with missing question or mark-scheme images")


if __name__ == "__main__":
    main()
