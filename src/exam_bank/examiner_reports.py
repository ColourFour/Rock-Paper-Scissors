from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .classification import infer_source_paper_code
from .document_metadata import companion_candidates, parse_filename_metadata
from .identifiers import normalize_question_id, parent_question_id


def examiner_report_evidence(source_pdf: str | Path, reports_dir: str | Path, question_id: str) -> str:
    reports_dir = Path(reports_dir)
    if not reports_dir.exists():
        return ""
    source_pdf = Path(source_pdf)
    metadata = parse_filename_metadata(source_pdf)
    if metadata.canonical_key:
        for path in companion_candidates(metadata, reports_dir, "ER"):
            evidence = _json_report_evidence(path, normalize_question_id(question_id), parent_question_id(question_id)) if path.suffix.lower() == ".json" else _text_report_evidence(path, normalize_question_id(question_id), parent_question_id(question_id))
            if evidence:
                return evidence
    paper_code, _confidence = infer_source_paper_code(source_pdf.name)
    keys = _candidate_keys(source_pdf, paper_code)
    wanted = normalize_question_id(question_id)
    parent = parent_question_id(wanted)

    for path in _candidate_report_paths(reports_dir, keys):
        if path.suffix.lower() == ".json":
            evidence = _json_report_evidence(path, wanted, parent)
        else:
            evidence = _text_report_evidence(path, wanted, parent)
        if evidence:
            return evidence
    return ""


def _candidate_keys(source_pdf: Path, paper_code: str) -> list[str]:
    stem = source_pdf.stem.lower()
    keys = [stem.replace("_qp_", "_er_"), stem.replace("_qp_", "_gt_"), stem]
    if paper_code:
        keys.append(paper_code)
    return list(dict.fromkeys(key for key in keys if key))


def _candidate_report_paths(reports_dir: Path, keys: list[str]) -> list[Path]:
    candidates: list[Path] = []
    for path in sorted(reports_dir.glob("*")):
        if path.suffix.lower() not in {".txt", ".json"}:
            continue
        lowered = path.stem.lower()
        if any(key in lowered for key in keys):
            candidates.append(path)
    return candidates


def _json_report_evidence(path: Path, wanted: str, parent: str) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if isinstance(data, dict):
        for key in [wanted, parent]:
            value = data.get(key)
            if isinstance(value, str):
                return value.strip()
            if isinstance(value, dict):
                text = value.get("text") or value.get("comment") or value.get("evidence")
                if isinstance(text, str):
                    return text.strip()
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            item_id = normalize_question_id(item.get("question_id") or item.get("question") or item.get("label"))
            if item_id in {wanted, parent}:
                text = item.get("text") or item.get("comment") or item.get("evidence")
                if isinstance(text, str):
                    return text.strip()
    return ""


def _text_report_evidence(path: Path, wanted: str, parent: str) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    sections = _split_text_sections(text)
    for key in [wanted, parent]:
        if key in sections:
            return sections[key].strip()
    return ""


def _split_text_sections(text: str) -> dict[str, str]:
    import re

    marker = re.compile(r"(?im)^\s*(?:question\s*)?(\d{1,2}\s*(?:\(?\s*[a-h]\s*\)?)?)\s*[:.\-–]\s*")
    matches = list(marker.finditer(text))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        key = normalize_question_id(match.group(1))
        sections[key] = text[start:end].strip()
    return sections
