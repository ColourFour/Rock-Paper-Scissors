from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from exam_bank import deepseek_enrich


def _record(
    question_id: str = "12spring24_q01",
    paper_family: str = "p1",
    *,
    local_topic: str = "binomial_expansion",
    local_difficulty: str | None = None,
    scope_quality_status: str = "clean",
    text_fidelity_status: str = "clean",
    topic_trust_status: str = "normal",
    validation_status: str = "pass",
) -> dict:
    notes = {
        "scope_quality_status": scope_quality_status,
        "text_fidelity_status": text_fidelity_status,
        "topic_trust_status": topic_trust_status,
        "validation_status": validation_status,
    }
    if local_difficulty is not None:
        notes["difficulty"] = local_difficulty
    return {
        "question_id": question_id,
        "paper": "12spring24",
        "paper_family": paper_family,
        "question_number": "1",
        "question_text": "Find x.",
        "mark_scheme_text": "x = 2",
        "question_solution_marks": 3,
        "topic": local_topic,
        "notes": notes,
    }


def _chat_response(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=content,
                )
            )
        ]
    )


def test_missing_api_key_fails_clearly(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    input_path = tmp_path / "question_bank.json"
    output_path = tmp_path / "question_bank.deepseek.json"
    input_path.write_text(json.dumps([_record()]), encoding="utf-8")

    with pytest.raises(deepseek_enrich.StartupConfigurationError, match="DEEPSEEK_API_KEY is required"):
        deepseek_enrich.run(["--input", str(input_path), "--output", str(output_path)])

    assert not output_path.exists()


def test_client_creation_uses_configured_base_url_and_env_key(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    class FakeOpenAI:
        def __init__(self, *, api_key: str, base_url: str) -> None:
            captured["api_key"] = api_key
            captured["base_url"] = base_url

    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-key")
    monkeypatch.setattr(deepseek_enrich, "OpenAI", FakeOpenAI)

    deepseek_enrich.create_client(base_url="https://example.deepseek.local")

    assert captured == {
        "api_key": "secret-key",
        "base_url": "https://example.deepseek.local",
    }


def test_valid_json_response_parses_into_sidecar_schema() -> None:
    raw = json.dumps(
        {
            "topic": "trigonometry",
            "subtopic": "identities",
            "difficulty": "medium",
            "confidence": "high",
            "rationale": "Uses a standard identity and one algebraic simplification.",
            "review_required": False,
        }
    )

    parsed = deepseek_enrich.parse_model_json(raw)
    sidecar = deepseek_enrich.build_sidecar_success(
        _record(local_topic="trigonometry", local_difficulty="average"),
        parsed,
        model="deepseek-chat",
        run_timestamp="2026-04-23T00:00:00+00:00",
    )

    assert sidecar["deepseek_topic_raw"] == "trigonometry"
    assert sidecar["deepseek_subtopic_raw"] == "identities"
    assert sidecar["deepseek_difficulty_raw"] == "medium"
    assert sidecar["deepseek_confidence_raw"] == "high"
    assert sidecar["deepseek_confidence_normalized"] == "high"
    assert sidecar["deepseek_rationale_raw"] == "Uses a standard identity and one algebraic simplification."
    assert sidecar["deepseek_review_required_raw"] is False
    assert sidecar["deepseek_topic_normalized"] == "trigonometry"
    assert sidecar["deepseek_difficulty_normalized"] == "average"
    assert sidecar["local_topic"] == "trigonometry"
    assert sidecar["local_difficulty"] == "average"
    assert sidecar["topic_reconciliation_status"] == "match"
    assert sidecar["difficulty_reconciliation_status"] == "match"
    assert sidecar["final_review_required"] is False
    assert sidecar["final_review_reasons"] == []
    assert sidecar["llm_provider"] == "deepseek"
    assert sidecar["llm_model"] == "deepseek-chat"
    assert sidecar["llm_prompt_version"] == "v2"
    assert sidecar["llm_run_timestamp"] == "2026-04-23T00:00:00+00:00"


def test_known_raw_topic_label_normalizes_to_internal_canonical_label() -> None:
    assert deepseek_enrich.normalize_topic_label("Trigonometry", paper_family="p3") == "trigonometry"
    assert (
        deepseek_enrich.normalize_topic_label(
            "Mechanics",
            paper_family="p4",
            raw_subtopic="Connected Particles",
        )
        == "connected_particles"
    )


def test_known_raw_difficulty_label_normalizes_to_internal_canonical_label() -> None:
    assert deepseek_enrich.normalize_difficulty_label("Medium") == "average"
    assert deepseek_enrich.normalize_difficulty_label("Hard") == "difficult"


def test_known_numeric_and_string_confidence_values_normalize_to_internal_buckets() -> None:
    assert deepseek_enrich.normalize_confidence_value(0.91) == "high"
    assert deepseek_enrich.normalize_confidence_value(0.60) == "medium"
    assert deepseek_enrich.normalize_confidence_value(0.20) == "low"
    assert deepseek_enrich.normalize_confidence_value("82%") == "high"
    assert deepseek_enrich.normalize_confidence_value("0.55") == "medium"


def test_unmapped_labels_are_preserved_and_marked_unmapped() -> None:
    sidecar = deepseek_enrich.build_sidecar_success(
        _record(local_topic="trigonometry", local_difficulty="average", paper_family="p1"),
        {
            "topic": "Mechanics",
            "subtopic": "",
            "difficulty": "Medium",
            "confidence": "high",
            "rationale": "Raw external label does not belong to P1 taxonomy.",
            "review_required": False,
        },
        model="deepseek-chat",
        run_timestamp="2026-04-23T00:00:00+00:00",
    )

    assert sidecar["deepseek_topic_raw"] == "Mechanics"
    assert sidecar["deepseek_topic_normalized"] is None
    assert sidecar["topic_reconciliation_status"] == "unmapped_label"
    assert sidecar["final_review_required"] is True
    assert "topic_reconciliation_status:unmapped_label" in sidecar["final_review_reasons"]


def test_degraded_text_forces_final_review_even_when_deepseek_matches() -> None:
    sidecar = deepseek_enrich.build_sidecar_success(
        _record(local_topic="trigonometry", text_fidelity_status="degraded"),
        {
            "topic": "Trigonometry",
            "subtopic": "general",
            "difficulty": "easy",
            "confidence": "high",
            "rationale": "Clean conceptual match.",
            "review_required": False,
        },
        model="deepseek-chat",
        run_timestamp="2026-04-23T00:00:00+00:00",
    )

    assert sidecar["topic_reconciliation_status"] == "match"
    assert sidecar["final_review_required"] is True
    assert "text_fidelity_status:degraded" in sidecar["final_review_reasons"]


def test_scope_fail_forces_final_review_semantics() -> None:
    sidecar = deepseek_enrich.build_sidecar_success(
        _record(local_topic="connected_particles", paper_family="p4", scope_quality_status="fail"),
        {
            "topic": "Mechanics",
            "subtopic": "Connected Particles",
            "difficulty": "Medium",
            "confidence": "high",
            "rationale": "Broad label but clear subtopic.",
            "review_required": False,
        },
        model="deepseek-chat",
        run_timestamp="2026-04-23T00:00:00+00:00",
    )

    assert sidecar["deepseek_topic_normalized"] == "connected_particles"
    assert sidecar["topic_reconciliation_status"] == "match"
    assert sidecar["final_review_required"] is True
    assert "scope_quality_status:fail" in sidecar["final_review_reasons"]


def test_local_vs_deepseek_match_is_recorded_explicitly() -> None:
    sidecar = deepseek_enrich.build_sidecar_success(
        _record(local_topic="connected_particles", paper_family="p4"),
        {
            "topic": "Mechanics",
            "subtopic": "Connected Particles",
            "difficulty": "Medium",
            "confidence": "high",
            "rationale": "Topic and subtopic align.",
            "review_required": False,
        },
        model="deepseek-chat",
        run_timestamp="2026-04-23T00:00:00+00:00",
    )

    assert sidecar["topic_reconciliation_status"] == "match"
    assert sidecar["final_review_required"] is False


def test_local_vs_deepseek_mismatch_is_recorded_explicitly() -> None:
    sidecar = deepseek_enrich.build_sidecar_success(
        _record(local_topic="trigonometry", paper_family="p1"),
        {
            "topic": "Integration",
            "subtopic": "Definite Integrals",
            "difficulty": "easy",
            "confidence": "high",
            "rationale": "Different topic from the local label.",
            "review_required": False,
        },
        model="deepseek-chat",
        run_timestamp="2026-04-23T00:00:00+00:00",
    )

    assert sidecar["deepseek_topic_normalized"] == "integration"
    assert sidecar["topic_reconciliation_status"] == "mismatch"
    assert sidecar["final_review_required"] is True
    assert "topic_reconciliation_status:mismatch" in sidecar["final_review_reasons"]


def test_malformed_model_output_becomes_per_record_error() -> None:
    class FakeClient:
        class _Chat:
            class _Completions:
                @staticmethod
                def create(**_: object) -> SimpleNamespace:
                    return _chat_response("not valid json")

            completions = _Completions()

        chat = _Chat()

    sidecar = deepseek_enrich.enrich_records([_record()], client=FakeClient(), model="deepseek-chat")
    record = sidecar["12spring24_q01"]

    assert record["error"]["type"] == "parse_error"
    assert "valid JSON" in record["error"]["message"]
    assert record["error"]["raw_provider_output"] == "not valid json"
    assert record["llm_provider"] == "deepseek"
    assert record["llm_model"] == "deepseek-chat"


def test_numeric_confidence_output_is_accepted_and_bucketed() -> None:
    raw = json.dumps(
        {
            "topic": "trigonometry",
            "subtopic": "general",
            "difficulty": "easy",
            "confidence": 0.91,
            "rationale": "Direct trig identity.",
            "review_required": False,
        }
    )

    parsed = deepseek_enrich.parse_model_json(raw)
    sidecar = deepseek_enrich.build_sidecar_success(
        _record(local_topic="trigonometry"),
        parsed,
        model="deepseek-chat",
        run_timestamp="2026-04-24T00:00:00+00:00",
    )

    assert parsed["confidence"] == 0.91
    assert sidecar["deepseek_confidence_raw"] == 0.91
    assert sidecar["deepseek_confidence_normalized"] == "high"


def test_provider_exception_becomes_per_record_error_without_aborting_batch() -> None:
    responses = iter(
        [
            RuntimeError("temporary provider issue"),
            _chat_response(
                json.dumps(
                    {
                        "topic": "series_and_sequences",
                        "subtopic": "general",
                        "difficulty": "hard",
                        "confidence": "medium",
                        "rationale": "Requires linking AP and GP conditions before solving.",
                        "review_required": True,
                    }
                )
            ),
        ]
    )

    class FakeClient:
        class _Chat:
            class _Completions:
                @staticmethod
                def create(**_: object) -> SimpleNamespace:
                    result = next(responses)
                    if isinstance(result, Exception):
                        raise result
                    return result

            completions = _Completions()

        chat = _Chat()

    sidecar = deepseek_enrich.enrich_records(
        [_record("12spring24_q01"), _record("12spring24_q02")],
        client=FakeClient(),
        model="deepseek-chat",
    )

    assert sidecar["12spring24_q01"]["error"]["type"] == "provider_error"
    assert "temporary provider issue" in sidecar["12spring24_q01"]["error"]["message"]
    assert sidecar["12spring24_q02"]["deepseek_topic"] == "series_and_sequences"
    assert sidecar["12spring24_q02"]["llm_provider"] == "deepseek"


def test_quoted_review_required_is_rejected_as_parse_error_and_logged(tmp_path: Path) -> None:
    failure_log_path = tmp_path / "deepseek.failures.jsonl"

    class FakeClient:
        class _Chat:
            class _Completions:
                @staticmethod
                def create(**_: object) -> SimpleNamespace:
                    return _chat_response(
                        json.dumps(
                            {
                                "topic": "binomial_expansion",
                                "subtopic": "general",
                                "difficulty": "easy",
                                "confidence": "medium",
                                "rationale": "Looks straightforward.",
                                "review_required": "false",
                            }
                        )
                    )

            completions = _Completions()

        chat = _Chat()

    sidecar = deepseek_enrich.enrich_records(
        [_record()],
        client=FakeClient(),
        model="deepseek-chat",
        failure_log_path=failure_log_path,
    )

    record = sidecar["12spring24_q01"]
    assert record["error"]["type"] == "parse_error"
    assert "review_required must be a boolean" in record["error"]["message"]
    assert '"review_required": "false"' in record["error"]["raw_provider_output"]

    lines = failure_log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    failure_entry = json.loads(lines[0])
    assert failure_entry["question_id"] == "12spring24_q01"
    assert failure_entry["error_type"] == "parse_error"
    assert '"review_required": "false"' in failure_entry["raw_provider_output"]


def test_duplicate_json_keys_are_rejected() -> None:
    raw = (
        '{"topic":"binomial_expansion","topic":"trigonometry","subtopic":"general",'
        '"difficulty":"easy","confidence":"high","rationale":"dup","review_required":false}'
    )

    with pytest.raises(ValueError, match="duplicate key"):
        deepseek_enrich.parse_model_json(raw)


def test_sidecar_file_is_keyed_by_question_id_and_original_input_is_untouched(tmp_path: Path) -> None:
    input_payload = [_record("12spring24_q01"), _record("12spring24_q02")]
    input_path = tmp_path / "question_bank.json"
    output_path = tmp_path / "question_bank.deepseek.json"
    input_path.write_text(json.dumps(input_payload, indent=2), encoding="utf-8")

    class FakeClient:
        class _Chat:
            class _Completions:
                @staticmethod
                def create(**_: object) -> SimpleNamespace:
                    return _chat_response(
                        json.dumps(
                            {
                                "topic": "binomial_expansion",
                                "subtopic": "general",
                                "difficulty": "easy",
                                "confidence": "high",
                                "rationale": "Direct expansion with a standard coefficient read-off.",
                                "review_required": False,
                            }
                        )
                    )

            completions = _Completions()

        chat = _Chat()

    records = deepseek_enrich.load_question_bank(input_path)
    selected = deepseek_enrich.select_records(records, limit=1)
    sidecar = deepseek_enrich.enrich_records(selected, client=FakeClient(), model="deepseek-chat")
    deepseek_enrich.write_sidecar(sidecar, output_path)

    written_sidecar = json.loads(output_path.read_text(encoding="utf-8"))
    original_after = json.loads(input_path.read_text(encoding="utf-8"))

    assert list(written_sidecar) == ["12spring24_q01"]
    assert written_sidecar["12spring24_q01"]["llm_provider"] == "deepseek"
    assert written_sidecar["12spring24_q01"]["llm_model"] == "deepseek-chat"
    assert written_sidecar["12spring24_q01"]["llm_prompt_version"] == "v2"
    assert "llm_run_timestamp" in written_sidecar["12spring24_q01"]
    assert written_sidecar["12spring24_q01"]["deepseek_topic_raw"] == "binomial_expansion"
    assert written_sidecar["12spring24_q01"]["deepseek_topic_normalized"] == "binomial_expansion"
    assert written_sidecar["12spring24_q01"]["deepseek_difficulty_raw"] == "easy"
    assert written_sidecar["12spring24_q01"]["deepseek_difficulty_normalized"] == "easy"
    assert written_sidecar["12spring24_q01"]["deepseek_confidence_raw"] == "high"
    assert written_sidecar["12spring24_q01"]["deepseek_confidence_normalized"] == "high"
    assert written_sidecar["12spring24_q01"]["topic_reconciliation_status"] == "match"
    assert written_sidecar["12spring24_q01"]["difficulty_reconciliation_status"] == "no_local_label"
    assert "final_review_required" in written_sidecar["12spring24_q01"]
    assert "final_review_reasons" in written_sidecar["12spring24_q01"]
    assert original_after == input_payload


def test_dry_run_skips_external_calls_and_output_write(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    input_path = tmp_path / "question_bank.json"
    output_path = tmp_path / "question_bank.deepseek.json"
    input_path.write_text(json.dumps([_record("12spring24_q01"), _record("12spring24_q02")]), encoding="utf-8")

    exit_code = deepseek_enrich.run(
        ["--input", str(input_path), "--output", str(output_path), "--limit", "1", "--dry-run"]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "12spring24_q01" in captured.out
    assert not output_path.exists()
