#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import filecmp
import json
import re
import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATIC_FAMILIES = {"p1", "p3", "p4", "p5"}
PIPELINE_FAMILY_ALIASES = {
    "pm1": "p1",
    "pm3": "p3",
    "p1": "p1",
    "p3": "p3",
    "p4": "p4",
    "p5": "p5",
}
COURSE_BY_FAMILY = {
    "p1": ("p1", "Pure Mathematics 1"),
    "p3": ("p3", "Pure Mathematics 3"),
    "p4": ("m1", "Mechanics 1"),
    "p5": ("s1", "Probability & Statistics 1"),
}
SESSION_BY_CODE = {
    "m": "spring",
    "s": "summer",
    "w": "autumn",
}
SEASON_ORDER = {
    "spring": 1,
    "summer": 2,
    "autumn": 3,
    "winter": 3,
}
IMAGE_PATH_RE = re.compile(
    r"(?:^|/)[^/]+_(?P<year>\d{4})_(?P<session>[msw])(?P<year2>\d{2})_"
    r"(?P<component>\d{1,2})_(?:qp|ms)_q(?P<question>\d+)_"
)
PAPER_RE = re.compile(r"^(?P<component>\d+)(?P<season>spring|summer|autumn|winter)(?P<year>\d+)$")
QUESTION_ID_RE = re.compile(r"_q(?P<question>\d+)$")


@dataclass
class PreparedRecord:
    key: str
    record: dict[str, Any]
    route: dict[str, Any] | None
    source: str
    renderable: bool
    question_source: Path | None = None
    mark_scheme_source: Path | None = None
    question_dest: Path | None = None
    mark_scheme_dest: Path | None = None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Adapt exam-bank-pipeline output into this static GitHub Pages repo."
    )
    parser.add_argument(
        "--pipeline-root",
        type=Path,
        default=Path("../exam-bank-pipeline"),
        help="Path to the sibling exam-bank-pipeline repo.",
    )
    parser.add_argument(
        "--site-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Path to this static site repo.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing files.")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate the current data/step-3 image references.",
    )
    args = parser.parse_args()

    site_root = args.site_root.resolve()
    data_root = site_root / "data" / "step-3"
    if args.validate_only:
        question_bank = read_json(data_root / "question_bank.json")
        summary = validate_site_bank(question_bank, data_root)
        print_summary(summary)
        return 0 if summary["missing_referenced_images"] == 0 else 1

    pipeline_root = args.pipeline_root.resolve()
    summary = ingest(pipeline_root=pipeline_root, site_root=site_root, dry_run=args.dry_run)
    print_summary(summary)
    return 0 if summary["missing_referenced_images"] == 0 else 1


def ingest(*, pipeline_root: Path, site_root: Path, dry_run: bool) -> dict[str, Any]:
    data_root = site_root / "data" / "step-3"
    pipeline_output = pipeline_root / "output"
    pipeline_bank_path = pipeline_root / "output" / "json" / "question_bank.json"
    pipeline_routes_path = pipeline_root / "data" / "topic_routing" / "question_bank.topic_routing.v1.json"
    current_bank_path = data_root / "question_bank.json"
    current_routes_path = data_root / "question_bank.topic_routing.v1.json"

    pipeline_bank = read_json(pipeline_bank_path)
    pipeline_routes_payload = read_json(pipeline_routes_path)
    current_bank = read_json(current_bank_path)
    current_routes_payload = read_json(current_routes_path)

    pipeline_routes = records_dict(pipeline_routes_payload)
    current_routes = records_dict(current_routes_payload)

    pipeline_prepared, duplicate_keys = prepare_pipeline_records(
        pipeline_bank.get("questions", []),
        pipeline_routes,
        pipeline_output=pipeline_output,
        data_root=data_root,
    )
    current_prepared = prepare_current_records(
        current_bank.get("questions", []),
        current_routes,
        data_root=data_root,
    )

    final_records: dict[str, PreparedRecord] = {}
    pipeline_renderable_by_key: set[str] = set()
    pipeline_nonrenderable_by_key: set[str] = set()

    for key, prepared in sorted(pipeline_prepared.items(), key=lambda item: sort_key_for_record(item[1].record)):
        final_records[key] = prepared
        if prepared.renderable:
            pipeline_renderable_by_key.add(key)
        else:
            pipeline_nonrenderable_by_key.add(key)

    retained_current = 0
    replaced_nonrenderable = 0
    for key, prepared in sorted(current_prepared.items(), key=lambda item: sort_key_for_record(item[1].record)):
        if key in pipeline_renderable_by_key:
            continue
        if key in pipeline_nonrenderable_by_key:
            replaced_nonrenderable += 1
        if key not in final_records or key in pipeline_nonrenderable_by_key:
            final_records[key] = prepared
            retained_current += 1

    ordered = [prepared for _, prepared in sorted(final_records.items(), key=lambda item: sort_key_for_record(item[1].record))]
    final_questions = [prepared.record for prepared in ordered]
    final_routes = {
        prepared.key: prepared.route
        for prepared in ordered
        if prepared.route is not None
    }

    output_bank = copy.deepcopy(pipeline_bank)
    output_bank["questions"] = final_questions
    output_bank["record_count"] = len(final_questions)
    output_bank.setdefault("metadata", {})
    if isinstance(output_bank["metadata"], dict):
        output_bank["metadata"]["static_ingest"] = ingest_metadata(
            pipeline_root=pipeline_root,
            pipeline_record_count=len(pipeline_bank.get("questions", [])),
            pipeline_renderable_count=len(pipeline_renderable_by_key),
            retained_current_count=retained_current,
            final_renderable_count=sum(1 for prepared in ordered if has_both_static_paths(prepared.record)),
            dry_run=dry_run,
        )

    output_routes = copy.deepcopy(pipeline_routes_payload)
    output_routes["records"] = final_routes
    output_routes.setdefault("metadata", {})
    if isinstance(output_routes["metadata"], dict):
        output_routes["metadata"]["question_bank_record_count"] = len(final_questions)
        output_routes["metadata"]["sidecar_entry_count"] = len(final_routes)
        output_routes["metadata"]["static_ingest"] = ingest_metadata(
            pipeline_root=pipeline_root,
            pipeline_record_count=len(pipeline_bank.get("questions", [])),
            pipeline_renderable_count=len(pipeline_renderable_by_key),
            retained_current_count=retained_current,
            final_renderable_count=sum(1 for prepared in ordered if has_both_static_paths(prepared.record)),
            dry_run=dry_run,
        )

    copy_summary = copy_pipeline_images(ordered, dry_run=dry_run)
    validation_summary = (
        validate_prepared_records(ordered)
        if dry_run
        else validate_records(final_questions, data_root)
    )

    if not dry_run:
        write_json(current_bank_path, output_bank)
        write_json(current_routes_path, output_routes)

    by_source = Counter(prepared.source for prepared in ordered if has_both_static_paths(prepared.record))
    by_family = Counter(
        prepared.record.get("paper_family")
        for prepared in ordered
        if has_both_static_paths(prepared.record)
    )
    return {
        "mode": "dry-run" if dry_run else "apply",
        "pipeline_records_read": len(pipeline_bank.get("questions", [])),
        "pipeline_renderable_records": len(pipeline_renderable_by_key),
        "pipeline_nonrenderable_records": len(pipeline_prepared) - len(pipeline_renderable_by_key),
        "current_renderable_records": sum(1 for prepared in current_prepared.values() if prepared.renderable),
        "retained_existing_renderable_records": retained_current,
        "replaced_nonrenderable_pipeline_records": replaced_nonrenderable,
        "final_metadata_records": len(final_questions),
        "final_renderable_records": sum(1 for prepared in ordered if has_both_static_paths(prepared.record)),
        "final_renderable_by_family": dict(sorted(by_family.items())),
        "final_renderable_by_source": dict(sorted(by_source.items())),
        "duplicate_pipeline_static_ids": duplicate_keys,
        "image_copy": copy_summary,
        **validation_summary,
    }


def prepare_pipeline_records(
    records: list[dict[str, Any]],
    routes: dict[str, dict[str, Any]],
    *,
    pipeline_output: Path,
    data_root: Path,
) -> tuple[dict[str, PreparedRecord], list[str]]:
    prepared_by_key: dict[str, PreparedRecord] = {}
    duplicate_keys: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        route = routes.get(str(record.get("question_id") or ""))
        static_family = static_family_for(record, route)
        if static_family not in STATIC_FAMILIES:
            continue
        static_paper = static_paper_for(record)
        question_label = static_question_label_for(record)
        static_id = f"{static_paper}_{question_label}"

        q_rel_source = text(record.get("question_image_path"))
        ms_rel_source = text(record.get("mark_scheme_image_path"))
        q_source = safe_join(pipeline_output, q_rel_source) if q_rel_source else None
        ms_source = safe_join(pipeline_output, ms_rel_source) if ms_rel_source else None
        q_exists = q_source is not None and q_source.is_file()
        ms_exists = ms_source is not None and ms_source.is_file()
        renderable = q_exists and ms_exists

        q_rel_dest = f"{static_family}/{static_paper}/questions/{question_label}.png" if renderable else ""
        ms_rel_dest = f"{static_family}/{static_paper}/mark_scheme/{question_label}.png" if renderable else ""

        normalized = copy.deepcopy(record)
        normalized["question_id"] = static_id
        normalized["paper"] = static_paper
        normalized["paper_family"] = static_family
        normalized["question_number"] = question_number_value(record, question_label)
        normalized["question_image_path"] = q_rel_dest
        normalized["mark_scheme_image_path"] = ms_rel_dest
        normalized["canonical_question_artifact"] = q_rel_dest
        normalized["canonical_mark_scheme_artifact"] = ms_rel_dest
        normalized["question_image_paths"] = [q_rel_dest] if q_rel_dest else []
        normalized["mark_scheme_image_paths"] = [ms_rel_dest] if ms_rel_dest else []
        normalized.setdefault("notes", {})
        if isinstance(normalized["notes"], dict):
            normalized["notes"]["static_ingest_source_question_id"] = record.get("question_id")
            normalized["notes"]["static_ingest_source_paper"] = record.get("paper")
            normalized["notes"]["static_ingest_source_question_image_path"] = q_rel_source
            normalized["notes"]["static_ingest_source_mark_scheme_image_path"] = ms_rel_source

        normalized_route = normalize_route(route, static_id, static_paper, static_family, normalized)
        prepared = PreparedRecord(
            key=static_id,
            record=normalized,
            route=normalized_route,
            source="pipeline",
            renderable=renderable,
            question_source=q_source if renderable else None,
            mark_scheme_source=ms_source if renderable else None,
            question_dest=data_root / q_rel_dest if q_rel_dest else None,
            mark_scheme_dest=data_root / ms_rel_dest if ms_rel_dest else None,
        )

        existing = prepared_by_key.get(static_id)
        if existing is not None:
            duplicate_keys.append(static_id)
            if existing.renderable and not prepared.renderable:
                continue
            if prepared.renderable and not existing.renderable:
                prepared_by_key[static_id] = prepared
                continue
        prepared_by_key[static_id] = prepared
    return prepared_by_key, sorted(set(duplicate_keys))


def prepare_current_records(
    records: list[dict[str, Any]],
    routes: dict[str, dict[str, Any]],
    *,
    data_root: Path,
) -> dict[str, PreparedRecord]:
    prepared: dict[str, PreparedRecord] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        key = text(record.get("question_id"))
        if not key:
            continue
        q_rel = text(record.get("question_image_path"))
        ms_rel = text(record.get("mark_scheme_image_path"))
        q_path = safe_join(data_root, q_rel) if q_rel else None
        ms_path = safe_join(data_root, ms_rel) if ms_rel else None
        renderable = bool(q_path and q_path.is_file() and ms_path and ms_path.is_file())
        if not renderable:
            continue
        current = copy.deepcopy(record)
        current["paper"] = text(current.get("paper")).replace("winter", "autumn")
        current["question_id"] = key.replace("winter", "autumn")
        current["paper_family"] = static_family_for_current(current)
        route = normalize_route(routes.get(key), current["question_id"], current["paper"], current["paper_family"], current)
        prepared[current["question_id"]] = PreparedRecord(
            key=current["question_id"],
            record=current,
            route=route,
            source="current_retained",
            renderable=True,
        )
    return prepared


def static_family_for(record: dict[str, Any], route: dict[str, Any] | None) -> str:
    route_family = text((route or {}).get("paper_family")).lower()
    if route_family in STATIC_FAMILIES:
        return route_family
    source_family = text(record.get("paper_family")).lower()
    if source_family in PIPELINE_FAMILY_ALIASES:
        return PIPELINE_FAMILY_ALIASES[source_family]
    component = component_for(record)
    if component in {"01", "11", "12", "13", "15"}:
        return "p1"
    if component in {"03", "31", "32", "33", "35"}:
        return "p3"
    if component in {"04", "41", "42", "43", "45"}:
        return "p4"
    if component in {"06", "51", "52", "53", "55", "61", "62", "63"}:
        return "p5"
    return source_family


def static_family_for_current(record: dict[str, Any]) -> str:
    family = text(record.get("paper_family")).lower()
    if family in STATIC_FAMILIES:
        return family
    return static_family_for(record, None)


def static_paper_for(record: dict[str, Any]) -> str:
    parsed = parse_image_path(text(record.get("question_image_path"))) or parse_image_path(
        text(record.get("canonical_question_artifact"))
    )
    if parsed:
        return f"{parsed['component']}{SESSION_BY_CODE[parsed['session']]}{parsed['year2']}"
    return text(record.get("paper")).replace("winter", "autumn")


def static_question_label_for(record: dict[str, Any]) -> str:
    parsed = parse_image_path(text(record.get("question_image_path"))) or parse_image_path(
        text(record.get("canonical_question_artifact"))
    )
    if parsed:
        return f"q{int(parsed['question']):02d}"
    match = QUESTION_ID_RE.search(text(record.get("question_id")))
    if match:
        return f"q{int(match.group('question')):02d}"
    value = text(record.get("question_number"))
    number_match = re.search(r"\d+", value)
    if number_match:
        return f"q{int(number_match.group()):02d}"
    return "q00"


def component_for(record: dict[str, Any]) -> str:
    parsed = parse_image_path(text(record.get("question_image_path"))) or parse_image_path(
        text(record.get("canonical_question_artifact"))
    )
    if parsed:
        return parsed["component"]
    paper = text(record.get("paper"))
    match = re.match(r"^(\d+)", paper)
    return match.group(1) if match else ""


def parse_image_path(path: str) -> dict[str, str] | None:
    match = IMAGE_PATH_RE.search(path)
    if not match:
        return None
    parsed = match.groupdict()
    parsed["component"] = parsed["component"].zfill(2)
    return parsed


def question_number_value(record: dict[str, Any], question_label: str) -> Any:
    existing = record.get("question_number")
    if existing not in (None, ""):
        return existing
    return int(question_label[1:]) if question_label.startswith("q") and question_label[1:].isdigit() else question_label


def normalize_route(
    route: dict[str, Any] | None,
    static_id: str,
    static_paper: str,
    static_family: str,
    record: dict[str, Any],
) -> dict[str, Any] | None:
    if route is None:
        return None
    normalized = copy.deepcopy(route)
    normalized["paper"] = static_paper
    normalized["paper_family"] = static_family
    normalized["packet_family"] = static_family
    normalized["question_number"] = str(record.get("question_number") or "")
    course_id, component_name = COURSE_BY_FAMILY.get(static_family, ("", ""))
    if course_id:
        normalized["course_id"] = course_id
    if component_name:
        normalized["component_name"] = component_name
    normalized["static_question_id"] = static_id
    return normalized


def copy_pipeline_images(records: list[PreparedRecord], *, dry_run: bool) -> dict[str, int]:
    summary = Counter()
    for prepared in records:
        if not prepared.renderable:
            continue
        for source, dest in (
            (prepared.question_source, prepared.question_dest),
            (prepared.mark_scheme_source, prepared.mark_scheme_dest),
        ):
            if source is None or dest is None:
                continue
            summary["referenced_pipeline_images"] += 1
            if dest.exists() and filecmp.cmp(source, dest, shallow=False):
                summary["unchanged"] += 1
                continue
            if dry_run:
                summary["would_copy"] += 1
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            summary["copied"] += 1
    return dict(summary)


def validate_prepared_records(records: list[PreparedRecord]) -> dict[str, Any]:
    missing: list[str] = []
    renderable = 0
    by_family: Counter[str] = Counter()
    for prepared in records:
        record = prepared.record
        if not has_both_static_paths(record):
            continue
        if prepared.source == "pipeline":
            q_exists = prepared.question_source is not None and prepared.question_source.is_file()
            ms_exists = prepared.mark_scheme_source is not None and prepared.mark_scheme_source.is_file()
            if not q_exists:
                missing.append(text(record.get("question_image_path")))
            if not ms_exists:
                missing.append(text(record.get("mark_scheme_image_path")))
            if not (q_exists and ms_exists):
                continue
        elif not prepared.renderable:
            missing.append(text(record.get("question_id")))
            continue
        renderable += 1
        by_family[text(record.get("paper_family"))] += 1
    return {
        "validated_renderable_records": renderable,
        "validated_renderable_by_family": dict(sorted(by_family.items())),
        "missing_referenced_images": len(missing),
        "missing_referenced_image_examples": missing[:20],
    }


def validate_site_bank(question_bank: dict[str, Any], data_root: Path) -> dict[str, Any]:
    return validate_records(question_bank.get("questions", []), data_root)


def validate_records(records: list[dict[str, Any]], data_root: Path) -> dict[str, Any]:
    missing: list[str] = []
    renderable = 0
    by_family: Counter[str] = Counter()
    for record in records:
        if not isinstance(record, dict):
            continue
        q_rel = text(record.get("question_image_path"))
        ms_rel = text(record.get("mark_scheme_image_path"))
        if not q_rel or not ms_rel:
            continue
        q_path = safe_join(data_root, q_rel)
        ms_path = safe_join(data_root, ms_rel)
        q_exists = q_path.is_file()
        ms_exists = ms_path.is_file()
        if q_exists and ms_exists:
            renderable += 1
            by_family[text(record.get("paper_family"))] += 1
            continue
        if not q_exists:
            missing.append(q_rel)
        if not ms_exists:
            missing.append(ms_rel)
    return {
        "validated_renderable_records": renderable,
        "validated_renderable_by_family": dict(sorted(by_family.items())),
        "missing_referenced_images": len(missing),
        "missing_referenced_image_examples": missing[:20],
    }


def has_both_static_paths(record: dict[str, Any]) -> bool:
    return bool(record.get("question_image_path") and record.get("mark_scheme_image_path"))


def ingest_metadata(
    *,
    pipeline_root: Path,
    pipeline_record_count: int,
    pipeline_renderable_count: int,
    retained_current_count: int,
    final_renderable_count: int,
    dry_run: bool,
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "dry-run" if dry_run else "apply",
        "pipeline_root": str(pipeline_root),
        "pipeline_question_bank_path": "output/json/question_bank.json",
        "pipeline_topic_routing_path": "data/topic_routing/question_bank.topic_routing.v1.json",
        "pipeline_record_count": pipeline_record_count,
        "pipeline_renderable_count": pipeline_renderable_count,
        "retained_existing_renderable_count": retained_current_count,
        "final_renderable_count": final_renderable_count,
    }


def sort_key_for_record(record: dict[str, Any]) -> tuple[int, int, int, str, int, str]:
    paper = text(record.get("paper"))
    match = PAPER_RE.match(paper)
    if match:
        component = int(match.group("component"))
        year = int(match.group("year"))
        season = SEASON_ORDER.get(match.group("season"), 999)
    else:
        component = 999
        year = 999
        season = 999
    question_label = static_question_label_for(record)
    question_number = int(question_label[1:]) if question_label.startswith("q") and question_label[1:].isdigit() else 999
    return (component, year, season, paper, question_number, text(record.get("question_id")))


def records_dict(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records = payload.get("records")
    if isinstance(records, dict):
        return {str(key): value for key, value in records.items() if isinstance(value, dict)}
    return {}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required JSON file: {path}")
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected top-level JSON object in {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temp_path.replace(path)


def safe_join(root: Path, relative_path: str) -> Path:
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Unsafe relative path: {relative_path}")
    return root / relative


def text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def print_summary(summary: dict[str, Any]) -> None:
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
