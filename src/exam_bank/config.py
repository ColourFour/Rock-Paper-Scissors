from __future__ import annotations

from dataclasses import dataclass, field, is_dataclass
from pathlib import Path
from typing import Any

from .runtime_profile import (
    ACTIVE_INPUT_DOCUMENT_TYPES,
    ACTIVE_OUTPUTS,
    ARCHIVED_INPUT_DOCUMENT_TYPES,
    ARCHIVED_RUNTIME_SURFACES,
    CLASSIFICATION_HINT_OVERRIDES,
    DIFFICULTY_HEURISTICS,
    DIFFICULTY_LABELS,
    OUTPUT_LAYOUT,
    PAPER_FAMILIES,
    PAPER_FAMILY_TAXONOMY,
    RUNTIME_PROFILE_PATH,
    RUNTIME_TAXONOMY,
    TOPIC_MODE,
)


def _phrase(label: str) -> str:
    return label.replace("_", " ")


def _flatten_topic_taxonomy(taxonomy: dict[str, dict[str, list[str]]]) -> dict[str, list[str]]:
    flattened: dict[str, list[str]] = {}
    for family, topics in taxonomy.items():
        if family == "unknown":
            continue
        for topic, subtopics in topics.items():
            flattened.setdefault(topic, [])
            for subtopic in subtopics:
                if subtopic not in flattened[topic]:
                    flattened[topic].append(subtopic)
    return flattened


def _auto_classification_hints(
    taxonomy: dict[str, dict[str, list[str]]],
) -> dict[str, dict[str, dict[str, dict[str, list[str]]]]]:
    hints: dict[str, dict[str, dict[str, dict[str, list[str]]]]] = {}
    for family, topics in taxonomy.items():
        if family == "unknown":
            continue
        hints[family] = {}
        for topic, subtopics in topics.items():
            hints[family][topic] = {}
            topic_phrase = _phrase(topic)
            for subtopic in subtopics:
                subtopic_phrase = _phrase(subtopic)
                tokens = [token for token in subtopic.split("_") if len(token) >= 4]
                hints[family][topic][subtopic] = {
                    "methods": [],
                    "objects": [subtopic_phrase, topic_phrase],
                    "keywords": tokens,
                }
    return hints


def _deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _copied_paper_family_taxonomy() -> dict[str, dict[str, list[str]]]:
    return {
        family: {topic: list(subtopics) for topic, subtopics in topics.items()}
        for family, topics in PAPER_FAMILY_TAXONOMY.items()
    }


def _copied_classification_hints() -> dict[str, dict[str, dict[str, dict[str, list[str]]]]]:
    merged = _deep_merge_dicts(_auto_classification_hints(_copied_paper_family_taxonomy()), CLASSIFICATION_HINT_OVERRIDES)
    return {
        family: {
            topic: {subtopic: {kind: list(values) for kind, values in hints.items()} for subtopic, hints in subtopics.items()}
            for topic, subtopics in topics.items()
        }
        for family, topics in merged.items()
    }


def _copied_difficulty_heuristics() -> dict[str, dict[str, list[str]]]:
    return {family: {key: list(values) for key, values in data.items()} for family, data in DIFFICULTY_HEURISTICS.items()}


def _copied_topic_taxonomy() -> dict[str, list[str]]:
    return {key: list(value) for key, value in _flatten_topic_taxonomy(_copied_paper_family_taxonomy()).items()}


@dataclass(frozen=True)
class RuntimeConfig:
    taxonomy_source: Path = field(default_factory=lambda: RUNTIME_PROFILE_PATH)
    taxonomy: str = RUNTIME_TAXONOMY
    input_document_types: list[str] = field(default_factory=lambda: list(ACTIVE_INPUT_DOCUMENT_TYPES))
    archived_input_document_types: list[str] = field(default_factory=lambda: list(ARCHIVED_INPUT_DOCUMENT_TYPES))
    output_layout: str = OUTPUT_LAYOUT
    topic_mode: str = TOPIC_MODE
    active_outputs: list[str] = field(default_factory=lambda: list(ACTIVE_OUTPUTS))
    archived_runtime_surfaces: list[str] = field(default_factory=lambda: list(ARCHIVED_RUNTIME_SURFACES))

    def supports_input_document_type(self, document_type: str) -> bool:
        return document_type in self.input_document_types


@dataclass
class InputConfig:
    question_papers_dir: Path = Path("input/question_papers")
    mark_schemes_dir: Path = Path("input/mark_schemes")
    mappings_dir: Path = Path("input/mappings")
    examiner_reports_dir: Path = Path("input/examiner_reports")


@dataclass
class OutputConfig:
    json_dir: Path = Path("output/json")
    debug_dir: Path = Path("output/debug")

    def root_dir(self) -> Path:
        return self.json_dir.parent

    def apply_root(self, root: str | Path) -> None:
        root = Path(root)
        self.json_dir = root / "json"
        self.debug_dir = root / "debug"


@dataclass
class DetectionConfig:
    max_question_number: int = 30
    question_start_max_x: float = 115
    min_question_start_y: float = 65
    bottom_margin: float = 45
    crop_left_margin: float = 35
    crop_right_margin: float = 35
    crop_top_margin: float = 45
    crop_bottom_margin: float = 40
    crop_padding: float = 10
    min_text_chars_per_page: int = 25
    min_question_chars: int = 20
    render_dpi: int = 220
    stitch_gap_px: int = 18
    output_mode: str = "prompt_only"
    image_mode: str | None = None
    anchor_min_confidence: float = 0.58
    anchor_left_tolerance: float = 12
    anchor_font_size_ratio: float = 0.85
    anchor_y_tolerance: float = 8
    span_line_y_tolerance: float = 6
    continuation_min_text_chars: int = 8
    prompt_region_max_gap: float = 60
    prompt_graphic_lookahead: float = 180
    prompt_graphic_overlap_padding: float = 24
    min_crop_height: float = 24
    max_crop_height_ratio: float = 0.82


@dataclass
class OCRConfig:
    enabled: bool = True
    language: str = "eng"
    dpi: int = 220
    min_confidence: int = 45


@dataclass
class NamingConfig:
    json_name: str = "question_bank.json"


@dataclass
class ClassificationConfig:
    enable_openai: bool = False
    openai_model: str = "gpt-5-mini"
    openai_timeout_seconds: int = 30
    uncertainty_threshold: float = 0.55


@dataclass
class DebugConfig:
    enabled: bool = False
    save_rendered_pages: bool = True
    save_text_boxes: bool = True
    save_anchor_candidates: bool = True
    save_proposed_boxes: bool = True
    save_crop_boxes: bool = True


@dataclass
class AppConfig:
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    input: InputConfig = field(default_factory=InputConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    paper_families: list[str] = field(default_factory=lambda: list(PAPER_FAMILIES))
    paper_family_taxonomy: dict[str, dict[str, list[str]]] = field(default_factory=_copied_paper_family_taxonomy)
    topics: list[str] = field(default_factory=lambda: list(_copied_topic_taxonomy()))
    topic_taxonomy: dict[str, list[str]] = field(default_factory=_copied_topic_taxonomy)
    classification_hints: dict[str, dict[str, dict[str, dict[str, list[str]]]]] = field(default_factory=_copied_classification_hints)
    difficulty_heuristics: dict[str, dict[str, list[str]]] = field(default_factory=_copied_difficulty_heuristics)
    difficulty_labels: list[str] = field(default_factory=lambda: list(DIFFICULTY_LABELS))
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    ocr: OCRConfig = field(default_factory=OCRConfig)
    naming: NamingConfig = field(default_factory=NamingConfig)
    classification: ClassificationConfig = field(default_factory=ClassificationConfig)
    debug: DebugConfig = field(default_factory=DebugConfig)

    def ensure_output_dirs(self) -> None:
        self.output.root_dir().mkdir(parents=True, exist_ok=True)
        self.output.json_dir.mkdir(parents=True, exist_ok=True)
        if self.debug.enabled:
            self.output.debug_dir.mkdir(parents=True, exist_ok=True)


def load_config(path: str | Path | None = None) -> AppConfig:
    config = AppConfig()
    validate_config(config)
    config_path = Path(path) if path else Path("config.yaml")
    if not config_path.exists():
        return config

    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to read config.yaml. Install the project dependencies first.") from exc

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Config file must contain a YAML mapping: {config_path}")

    _apply_mapping(config, raw)
    validate_config(config)
    return config


def validate_config(config: AppConfig) -> None:
    if config.paper_families != list(PAPER_FAMILIES):
        raise ValueError(f"Paper families must be exactly {list(PAPER_FAMILIES)}.")
    config.topic_taxonomy = _flatten_topic_taxonomy(config.paper_family_taxonomy)
    config.topics = list(config.topic_taxonomy)

    if config.difficulty_labels != list(DIFFICULTY_LABELS):
        raise ValueError(f"Difficulty labels must be exactly {list(DIFFICULTY_LABELS)}.")
    if not isinstance(config.difficulty_heuristics, dict):
        raise ValueError("difficulty_heuristics must be a mapping.")
    if not 0 <= config.classification.uncertainty_threshold <= 1:
        raise ValueError("classification.uncertainty_threshold must be between 0 and 1.")
    if config.detection.output_mode not in {"prompt_only", "full_region"}:
        raise ValueError("detection.output_mode must be `prompt_only` or `full_region`.")
    if config.detection.image_mode not in {None, "prompt_crop", "pdf_crop"}:
        raise ValueError("detection.image_mode must be `prompt_crop`, `pdf_crop`, or unset.")
    if config.detection.image_mode == "pdf_crop":
        config.detection.output_mode = "full_region"
    elif config.detection.image_mode == "prompt_crop":
        config.detection.output_mode = "prompt_only"
    if not 0 < config.detection.max_crop_height_ratio <= 1:
        raise ValueError("detection.max_crop_height_ratio must be between 0 and 1.")

def _deprecated_runtime_key_error(key: str) -> ValueError:
    return ValueError(
        f"Config key `{key}` is deprecated. Runtime taxonomy now comes from `{RUNTIME_PROFILE_PATH.name}`; "
        "keep YAML overrides for operational settings only."
    )


def _archived_surface_key_error(key: str) -> ValueError:
    return ValueError(
        f"Config section `{key}` is archived and not part of the active extraction pipeline. "
        "The supported workflow is question-paper and mark-scheme extraction only."
    )


def _removed_output_key_error(key: str) -> ValueError:
    return ValueError(
        f"Config key `output.{key}` is no longer supported. Output now uses the paper-first root plus "
        "`output.json_dir` and optional `output.debug_dir`."
    )


def _removed_naming_key_error(key: str) -> ValueError:
    return ValueError(
        f"Config key `naming.{key}` is no longer supported. The active pipeline names images by paper and "
        "question automatically and only keeps `naming.json_name` configurable."
    )


def _apply_mapping(config: AppConfig, raw: dict[str, Any]) -> None:
    for key, value in raw.items():
        if key in {"runtime", "paper_families", "paper_family_taxonomy", "classification_hints", "difficulty_heuristics", "difficulty_labels", "topics", "topic_taxonomy"}:
            raise _deprecated_runtime_key_error(key)
        if key in {"topic_pdfs", "practice_page", "manual_review"}:
            raise _archived_surface_key_error(key)
        if key in {"input", "output", "detection", "ocr", "naming", "classification", "debug"}:
            target = getattr(config, key)
            if not isinstance(value, dict):
                raise ValueError(f"Config section `{key}` must be a mapping.")
            _set_dataclass_fields(target, value, path_fields=key in {"input", "output"})
        else:
            raise ValueError(f"Unknown config key `{key}`.")


def _set_dataclass_fields(target: object, values: dict[str, Any], path_fields: bool = False) -> None:
    valid = set(target.__dataclass_fields__)  # type: ignore[attr-defined]
    for key, value in values.items():
        if key not in valid:
            if isinstance(target, OutputConfig) and key in {"images_dir", "csv_dir", "review_dir"}:
                raise _removed_output_key_error(key)
            if isinstance(target, NamingConfig) and key in {"image_template", "csv_name", "review_name"}:
                raise _removed_naming_key_error(key)
            raise ValueError(f"Unknown config key `{key}` in {target.__class__.__name__}.")
        current = getattr(target, key)
        if is_dataclass(current) and isinstance(value, dict):
            _set_dataclass_fields(current, value, path_fields=False)
            continue
        if isinstance(current, Path):
            setattr(target, key, Path(value))
            continue
        if path_fields:
            value = Path(value)
        setattr(target, key, value)
