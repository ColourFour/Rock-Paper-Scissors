from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from openai import OpenAI
from .runtime_profile import DIFFICULTY_LABELS, PAPER_FAMILY_TAXONOMY

DEFAULT_INPUT_PATH = Path("output/json/question_bank.json")
DEFAULT_OUTPUT_PATH = Path("output/json/question_bank.deepseek.json")
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
PROMPT_VERSION = "v2"
LLM_PROVIDER = "deepseek"


class StartupConfigurationError(RuntimeError):
    """Raised when the enrichment run is misconfigured before processing starts."""


class ModelResponseError(ValueError):
    """Raised when provider output is present but cannot be accepted."""

    def __init__(self, message: str, *, raw_provider_output: str | None = None) -> None:
        super().__init__(message)
        self.raw_provider_output = raw_provider_output


_UNIQUE_TOPIC_ALIASES: dict[str, str] = {}
_TOPIC_ALIASES_BY_FAMILY: dict[str, dict[str, str]] = {}
for family_name, topics in PAPER_FAMILY_TAXONOMY.items():
    if family_name == "unknown":
        continue
    family_aliases: dict[str, str] = {}
    for canonical_topic in topics:
        alias = canonical_topic.replace("_", " ").strip().lower()
        family_aliases[alias] = canonical_topic
        _UNIQUE_TOPIC_ALIASES.setdefault(alias, canonical_topic)
        if _UNIQUE_TOPIC_ALIASES.get(alias) != canonical_topic:
            _UNIQUE_TOPIC_ALIASES.pop(alias, None)
    _TOPIC_ALIASES_BY_FAMILY[family_name] = family_aliases

_DIFFICULTY_ALIASES = {
    "easy": "easy",
    "simple": "easy",
    "basic": "easy",
    "routine": "easy",
    "average": "average",
    "medium": "average",
    "moderate": "average",
    "intermediate": "average",
    "difficult": "difficult",
    "hard": "difficult",
    "challenging": "difficult",
}

_CONFIDENCE_ALIASES = {
    "high": "high",
    "medium": "medium",
    "med": "medium",
    "moderate": "medium",
    "low": "low",
}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a narrow DeepSeek enrichment pass over exported question bank JSON.",
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH, help="Path to question_bank.json.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="Path to write the DeepSeek sidecar JSON.")
    parser.add_argument("--limit", type=int, default=25, help="Maximum number of selected records to enrich.")
    parser.add_argument(
        "--question-ids",
        nargs="*",
        default=None,
        help="Optional question IDs to enrich. Accepts space- or comma-separated values.",
    )
    parser.add_argument("--paper-family", default=None, help="Optional paper family filter, for example P1 or p1.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="OpenAI-compatible API base URL.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="DeepSeek model name.")
    parser.add_argument(
        "--failure-log",
        type=Path,
        default=None,
        help="Optional JSONL path for raw provider failure logging. Defaults next to the output sidecar.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print which records would be sent without making external API calls or writing an output file.",
    )
    args = parser.parse_args(argv)
    if args.limit < 0:
        parser.error("--limit must be zero or greater.")
    args.question_ids = _parse_question_ids(args.question_ids)
    return args


def _parse_question_ids(raw_values: Sequence[str] | None) -> list[str] | None:
    if not raw_values:
        return None
    question_ids: list[str] = []
    for value in raw_values:
        for part in value.split(","):
            cleaned = part.strip()
            if cleaned:
                question_ids.append(cleaned)
    return question_ids or None


def _normalize_free_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower().replace("_", " ")
    normalized = "".join(char if char.isalnum() or char.isspace() else " " for char in text)
    return " ".join(normalized.split())


def _canonical_paper_family(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in PAPER_FAMILY_TAXONOMY:
        return text
    return "unknown"


def normalize_topic_label(raw_topic: Any, *, paper_family: Any, raw_subtopic: Any = None) -> str | None:
    family = _canonical_paper_family(paper_family)
    family_aliases = _TOPIC_ALIASES_BY_FAMILY.get(family, {})
    for candidate in (raw_topic, raw_subtopic):
        normalized_candidate = _normalize_free_text(candidate)
        if not normalized_candidate:
            continue
        if normalized_candidate in family_aliases:
            return family_aliases[normalized_candidate]
        if normalized_candidate in _UNIQUE_TOPIC_ALIASES:
            return _UNIQUE_TOPIC_ALIASES[normalized_candidate]
    return None


def normalize_difficulty_label(raw_difficulty: Any) -> str | None:
    normalized = _normalize_free_text(raw_difficulty)
    if not normalized:
        return None
    if normalized in _DIFFICULTY_ALIASES:
        return _DIFFICULTY_ALIASES[normalized]
    if normalized in DIFFICULTY_LABELS:
        return normalized
    return None


def normalize_confidence_value(raw_confidence: Any) -> str | None:
    if isinstance(raw_confidence, bool) or raw_confidence is None:
        return None
    if isinstance(raw_confidence, (int, float)):
        return _numeric_confidence_bucket(float(raw_confidence))

    raw_text = str(raw_confidence).strip()
    if not raw_text:
        return None
    normalized = _normalize_free_text(raw_text)
    if normalized in _CONFIDENCE_ALIASES:
        return _CONFIDENCE_ALIASES[normalized]
    try:
        numeric_text = raw_text.rstrip("%").strip()
        numeric = float(numeric_text)
    except ValueError:
        return None
    return _numeric_confidence_bucket(numeric, had_percent=raw_text.endswith("%"))


def _numeric_confidence_bucket(value: float, *, had_percent: bool = False) -> str | None:
    if value < 0:
        return None
    scaled = value
    if had_percent or value > 1:
        if value > 100:
            return None
        scaled = value / 100.0
    if scaled >= 0.75:
        return "high"
    if scaled >= 0.45:
        return "medium"
    return "low"


def require_api_key(env: dict[str, str] | None = None) -> str:
    source = env if env is not None else os.environ
    api_key = source.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise StartupConfigurationError(
            "DEEPSEEK_API_KEY is required in the environment before running DeepSeek enrichment."
        )
    return api_key


def create_client(*, base_url: str = DEFAULT_BASE_URL, api_key: str | None = None) -> OpenAI:
    resolved_api_key = api_key if api_key is not None else require_api_key()
    return OpenAI(api_key=resolved_api_key, base_url=base_url)


def load_question_bank(path: str | Path) -> list[dict[str, Any]]:
    input_path = Path(path)
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StartupConfigurationError(f"Input question bank not found: {input_path}") from exc
    except json.JSONDecodeError as exc:
        raise StartupConfigurationError(f"Input question bank is not valid JSON: {input_path}") from exc

    if not isinstance(payload, list):
        raise StartupConfigurationError("Input question bank must be a JSON array of records.")

    records: list[dict[str, Any]] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise StartupConfigurationError(f"Question bank record at index {index} is not a JSON object.")
        question_id = str(item.get("question_id", "")).strip()
        if not question_id:
            raise StartupConfigurationError(f"Question bank record at index {index} is missing question_id.")
        records.append(item)
    return records


def select_records(
    records: Sequence[dict[str, Any]],
    *,
    limit: int,
    question_ids: Sequence[str] | None = None,
    paper_family: str | None = None,
) -> list[dict[str, Any]]:
    selected = list(records)
    if question_ids:
        wanted = {value.strip() for value in question_ids if value.strip()}
        selected = [record for record in selected if str(record.get("question_id", "")).strip() in wanted]
    if paper_family:
        wanted_family = paper_family.strip().lower()
        selected = [record for record in selected if str(record.get("paper_family", "")).strip().lower() == wanted_family]
    if limit >= 0:
        selected = selected[:limit]
    return selected


def build_enrichment_payload(record: dict[str, Any]) -> dict[str, Any]:
    notes = record.get("notes")
    note_map = notes if isinstance(notes, dict) else {}
    payload: dict[str, Any] = {
        "question_id": str(record["question_id"]),
        "paper_family": record.get("paper_family"),
        "question_number": record.get("question_number"),
        "question_text": record.get("question_text"),
    }
    optional_fields = {
        "mark_scheme_text": record.get("mark_scheme_text"),
        "question_solution_marks": record.get("question_solution_marks"),
        "scope_quality_status": note_map.get("scope_quality_status"),
        "text_fidelity_status": note_map.get("text_fidelity_status"),
        "topic_trust_status": note_map.get("topic_trust_status"),
        "current_local_topic": record.get("topic"),
    }
    for key, value in optional_fields.items():
        if value not in (None, "", []):
            payload[key] = value
    return payload


def _raw_or_none(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    return value


def _reconciliation_status(*, raw_value: Any, normalized_value: str | None, local_value: str | None) -> str:
    if _raw_or_none(raw_value) in (None, ""):
        return "no_deepseek_label"
    if normalized_value is None:
        return "unmapped_label"
    if local_value is None:
        return "no_local_label"
    if normalized_value == local_value:
        return "match"
    return "mismatch"


def _append_reason(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _final_review_reasons(
    *,
    model_review_required: bool,
    validation_status: str | None,
    scope_quality_status: str | None,
    text_fidelity_status: str | None,
    topic_trust_status: str | None,
    topic_reconciliation_status: str,
    difficulty_reconciliation_status: str,
    local_difficulty_present: bool,
) -> list[str]:
    reasons: list[str] = []
    if model_review_required:
        _append_reason(reasons, "llm_review_required")
    if validation_status and validation_status != "pass":
        _append_reason(reasons, f"validation_status:{validation_status}")
    if scope_quality_status and scope_quality_status != "clean":
        _append_reason(reasons, f"scope_quality_status:{scope_quality_status}")
    if text_fidelity_status == "degraded":
        _append_reason(reasons, "text_fidelity_status:degraded")
    elif text_fidelity_status == "unusable":
        _append_reason(reasons, "text_fidelity_status:unusable")
    if topic_trust_status and topic_trust_status != "normal":
        _append_reason(reasons, f"topic_trust_status:{topic_trust_status}")
    if topic_reconciliation_status in {"mismatch", "unmapped_label", "no_deepseek_label"}:
        _append_reason(reasons, f"topic_reconciliation_status:{topic_reconciliation_status}")
    if local_difficulty_present and difficulty_reconciliation_status in {"mismatch", "unmapped_label", "no_deepseek_label"}:
        _append_reason(reasons, f"difficulty_reconciliation_status:{difficulty_reconciliation_status}")
    return reasons


def build_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    instructions = (
        "You are reviewing a CAIE 9709 maths question record for suggestion-only enrichment. "
        "Return one strict JSON object only, with no markdown, no prose, no code fences, and no extra keys. "
        "The object must contain exactly these keys: "
        "topic, subtopic, difficulty, confidence, rationale, review_required. "
        "Use an empty string for subtopic when unavailable. "
        "Keep rationale short and concrete. "
        "review_required must be a literal JSON boolean: true or false. "
        "Do not quote the boolean."
    )
    return [
        {"role": "system", "content": instructions},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def request_suggestion(client: OpenAI, *, model: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.chat.completions.create(
        model=model,
        messages=build_messages(payload),
        response_format={"type": "json_object"},
        temperature=0,
    )
    raw_text = response_text(response)
    try:
        return parse_model_json(raw_text)
    except ValueError as exc:
        raise ModelResponseError(str(exc), raw_provider_output=raw_text) from exc


def response_text(response: Any) -> str:
    choices = getattr(response, "choices", None)
    if choices:
        first_choice = choices[0]
        message = getattr(first_choice, "message", None)
        content = getattr(message, "content", None)
        if isinstance(content, str) and content.strip():
            return content
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text
    raise ModelResponseError(
        "Provider response did not contain text content.",
        raw_provider_output=_response_snapshot(response),
    )


def parse_model_json(raw_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_text, object_pairs_hook=_strict_json_object)
    except json.JSONDecodeError as exc:
        raise ValueError("Model output was not valid JSON.") from exc

    if not isinstance(payload, dict):
        raise ValueError("Model output must be a JSON object.")

    expected_keys = {"topic", "subtopic", "difficulty", "confidence", "rationale", "review_required"}
    actual_keys = set(payload)
    if actual_keys != expected_keys:
        raise ValueError(
            f"Model output keys did not match the required schema. Expected {sorted(expected_keys)}, got {sorted(actual_keys)}."
        )

    topic = _require_non_empty_string(payload["topic"], "topic")
    difficulty = _require_non_empty_string(payload["difficulty"], "difficulty")
    confidence = _require_confidence_value(payload["confidence"])
    rationale = _require_non_empty_string(payload["rationale"], "rationale")

    subtopic_value = payload["subtopic"]
    if subtopic_value is None:
        subtopic = ""
    elif isinstance(subtopic_value, str):
        subtopic = subtopic_value.strip()
    else:
        raise ValueError("subtopic must be a string or null.")

    review_required = payload["review_required"]
    if not isinstance(review_required, bool):
        raise ValueError("review_required must be a boolean.")

    return {
        "topic": topic,
        "subtopic": subtopic,
        "difficulty": difficulty,
        "confidence": confidence,
        "rationale": rationale,
        "review_required": review_required,
    }


def _require_non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")
    return value.strip()


def _require_confidence_value(value: Any) -> str | int | float:
    if isinstance(value, bool):
        raise ValueError("confidence must be a non-empty string or numeric value.")
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValueError("confidence must be a non-empty string or numeric value.")


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError(f"Model output contained a duplicate key: {key}.")
        payload[key] = value
    return payload


def _response_snapshot(response: Any) -> str:
    model_dump_json = getattr(response, "model_dump_json", None)
    if callable(model_dump_json):
        try:
            return str(model_dump_json(indent=2))
        except TypeError:
            return str(model_dump_json())
    model_dump = getattr(response, "model_dump", None)
    if callable(model_dump):
        try:
            return json.dumps(model_dump(), ensure_ascii=False, indent=2)
        except TypeError:
            return json.dumps(model_dump(), ensure_ascii=False)
    return repr(response)


def build_sidecar_success(
    record: dict[str, Any],
    suggestion: dict[str, Any],
    *,
    model: str,
    run_timestamp: str,
) -> dict[str, Any]:
    notes = record.get("notes")
    note_map = notes if isinstance(notes, dict) else {}

    raw_topic = _raw_or_none(suggestion.get("topic"))
    raw_subtopic = _raw_or_none(suggestion.get("subtopic"))
    raw_difficulty = _raw_or_none(suggestion.get("difficulty"))
    raw_confidence = _raw_or_none(suggestion.get("confidence"))
    normalized_confidence = normalize_confidence_value(raw_confidence)
    raw_rationale = _raw_or_none(suggestion.get("rationale"))
    raw_review_required = bool(suggestion.get("review_required"))

    local_topic = _raw_or_none(record.get("topic"))
    local_difficulty = _raw_or_none(record.get("difficulty")) or _raw_or_none(note_map.get("difficulty"))

    normalized_topic = normalize_topic_label(
        raw_topic,
        paper_family=record.get("paper_family"),
        raw_subtopic=raw_subtopic,
    )
    normalized_difficulty = normalize_difficulty_label(raw_difficulty)

    local_topic_normalized = normalize_topic_label(
        local_topic,
        paper_family=record.get("paper_family"),
        raw_subtopic=note_map.get("subtopic"),
    ) if local_topic else None
    local_difficulty_normalized = normalize_difficulty_label(local_difficulty) if local_difficulty else None

    topic_reconciliation_status = _reconciliation_status(
        raw_value=raw_topic,
        normalized_value=normalized_topic,
        local_value=local_topic_normalized,
    )
    difficulty_reconciliation_status = _reconciliation_status(
        raw_value=raw_difficulty,
        normalized_value=normalized_difficulty,
        local_value=local_difficulty_normalized,
    )

    final_review_reasons = _final_review_reasons(
        model_review_required=raw_review_required,
        validation_status=_raw_or_none(note_map.get("validation_status")),
        scope_quality_status=_raw_or_none(note_map.get("scope_quality_status")),
        text_fidelity_status=_raw_or_none(note_map.get("text_fidelity_status")),
        topic_trust_status=_raw_or_none(note_map.get("topic_trust_status")),
        topic_reconciliation_status=topic_reconciliation_status,
        difficulty_reconciliation_status=difficulty_reconciliation_status,
        local_difficulty_present=local_difficulty_normalized is not None,
    )

    return {
        "deepseek_topic": raw_topic,
        "deepseek_subtopic": raw_subtopic,
        "deepseek_difficulty": raw_difficulty,
        "deepseek_confidence": raw_confidence,
        "deepseek_confidence_normalized": normalized_confidence,
        "deepseek_rationale": raw_rationale,
        "deepseek_review_required": raw_review_required,
        "deepseek_topic_raw": raw_topic,
        "deepseek_subtopic_raw": raw_subtopic,
        "deepseek_difficulty_raw": raw_difficulty,
        "deepseek_confidence_raw": raw_confidence,
        "deepseek_rationale_raw": raw_rationale,
        "deepseek_review_required_raw": raw_review_required,
        "deepseek_topic_normalized": normalized_topic,
        "deepseek_difficulty_normalized": normalized_difficulty,
        "local_topic": local_topic_normalized or local_topic,
        "local_difficulty": local_difficulty_normalized or local_difficulty,
        "topic_reconciliation_status": topic_reconciliation_status,
        "difficulty_reconciliation_status": difficulty_reconciliation_status,
        "final_review_required": bool(final_review_reasons),
        "final_review_reasons": final_review_reasons,
        "llm_provider": LLM_PROVIDER,
        "llm_model": model,
        "llm_prompt_version": PROMPT_VERSION,
        "llm_run_timestamp": run_timestamp,
    }


def build_sidecar_error(
    *,
    error_type: str,
    message: str,
    model: str,
    run_timestamp: str,
    raw_provider_output: str | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {
        "type": error_type,
        "message": message,
    }
    if raw_provider_output:
        error["raw_provider_output"] = raw_provider_output
    return {
        "error": error,
        "llm_provider": LLM_PROVIDER,
        "llm_model": model,
        "llm_prompt_version": PROMPT_VERSION,
        "llm_run_timestamp": run_timestamp,
    }


def enrich_records(
    records: Sequence[dict[str, Any]],
    *,
    client: OpenAI,
    model: str,
    failure_log_path: str | Path | None = None,
) -> dict[str, dict[str, Any]]:
    run_timestamp = datetime.now(timezone.utc).isoformat()
    sidecar: dict[str, dict[str, Any]] = {}
    for record in records:
        question_id = str(record["question_id"])
        payload = build_enrichment_payload(record)
        try:
            suggestion = request_suggestion(client, model=model, payload=payload)
        except ModelResponseError as exc:
            error_record = build_sidecar_error(
                error_type="parse_error",
                message=str(exc),
                model=model,
                run_timestamp=run_timestamp,
                raw_provider_output=exc.raw_provider_output,
            )
            sidecar[question_id] = error_record
            _append_failure_log(
                failure_log_path,
                question_id=question_id,
                error_type="parse_error",
                error_message=str(exc),
                model=model,
                run_timestamp=run_timestamp,
                raw_provider_output=exc.raw_provider_output,
                request_payload=payload,
            )
            continue
        except ValueError as exc:
            error_record = build_sidecar_error(
                error_type="parse_error",
                message=str(exc),
                model=model,
                run_timestamp=run_timestamp,
            )
            sidecar[question_id] = error_record
            _append_failure_log(
                failure_log_path,
                question_id=question_id,
                error_type="parse_error",
                error_message=str(exc),
                model=model,
                run_timestamp=run_timestamp,
                raw_provider_output=None,
                request_payload=payload,
            )
            continue
        except Exception as exc:
            error_record = build_sidecar_error(
                error_type="provider_error",
                message=f"{exc.__class__.__name__}: {exc}",
                model=model,
                run_timestamp=run_timestamp,
            )
            sidecar[question_id] = error_record
            _append_failure_log(
                failure_log_path,
                question_id=question_id,
                error_type="provider_error",
                error_message=f"{exc.__class__.__name__}: {exc}",
                model=model,
                run_timestamp=run_timestamp,
                raw_provider_output=None,
                request_payload=payload,
            )
            continue

        sidecar[question_id] = build_sidecar_success(
            record,
            suggestion,
            model=model,
            run_timestamp=run_timestamp,
        )
    return sidecar


def write_sidecar(payload: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def default_failure_log_path(output_path: str | Path) -> Path:
    output = Path(output_path)
    if output.suffix == ".json":
        return output.with_suffix(".failures.jsonl")
    return output.parent / f"{output.name}.failures.jsonl"


def _append_failure_log(
    failure_log_path: str | Path | None,
    *,
    question_id: str,
    error_type: str,
    error_message: str,
    model: str,
    run_timestamp: str,
    raw_provider_output: str | None,
    request_payload: dict[str, Any],
) -> None:
    if failure_log_path is None:
        return
    path = Path(failure_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "question_id": question_id,
        "error_type": error_type,
        "error_message": error_message,
        "llm_provider": LLM_PROVIDER,
        "llm_model": model,
        "llm_prompt_version": PROMPT_VERSION,
        "llm_run_timestamp": run_timestamp,
        "raw_provider_output": raw_provider_output,
        "request_payload": request_payload,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def validate_paths(*, input_path: Path, output_path: Path) -> None:
    if input_path.resolve() == output_path.resolve():
        raise StartupConfigurationError("Output path must be different from the input question bank path.")


def run(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    validate_paths(input_path=args.input, output_path=args.output)
    failure_log_path = args.failure_log or default_failure_log_path(args.output)
    records = load_question_bank(args.input)
    selected = select_records(
        records,
        limit=args.limit,
        question_ids=args.question_ids,
        paper_family=args.paper_family,
    )

    if args.dry_run:
        summary = {
            "input": str(args.input),
            "output": str(args.output),
            "failure_log": str(failure_log_path),
            "selected_count": len(selected),
            "question_ids": [record["question_id"] for record in selected],
        }
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    client = create_client(base_url=args.base_url)
    sidecar = enrich_records(selected, client=client, model=args.model, failure_log_path=failure_log_path)
    write_sidecar(sidecar, args.output)
    print(f"Wrote {len(sidecar)} DeepSeek enrichment records to {args.output}")
    failure_count = sum(1 for value in sidecar.values() if "error" in value)
    if failure_count:
        print(f"Logged {failure_count} provider failures to {failure_log_path}")
    return 0


def main() -> None:
    try:
        raise SystemExit(run())
    except StartupConfigurationError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
