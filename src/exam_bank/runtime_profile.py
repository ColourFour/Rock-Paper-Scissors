from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


RUNTIME_PROFILE_PATH = Path(__file__).with_name("runtime_profile.json")


def _load_runtime_profile() -> dict[str, Any]:
    return json.loads(RUNTIME_PROFILE_PATH.read_text(encoding="utf-8"))


def runtime_profile() -> dict[str, Any]:
    return deepcopy(_RUNTIME_PROFILE)


_RUNTIME_PROFILE = _load_runtime_profile()
PRODUCT_DIRECTION = deepcopy(_RUNTIME_PROFILE["product_direction"])
RUNTIME_TAXONOMY = str(PRODUCT_DIRECTION["runtime_taxonomy"])
ACTIVE_INPUT_DOCUMENT_TYPES = tuple(PRODUCT_DIRECTION["active_input_document_types"])
ARCHIVED_INPUT_DOCUMENT_TYPES = tuple(PRODUCT_DIRECTION["archived_input_document_types"])
OUTPUT_LAYOUT = str(PRODUCT_DIRECTION["output_layout"])
TOPIC_MODE = str(PRODUCT_DIRECTION["topic_mode"])
ACTIVE_OUTPUTS = tuple(PRODUCT_DIRECTION["active_outputs"])
ARCHIVED_RUNTIME_SURFACES = tuple(PRODUCT_DIRECTION["archived_runtime_surfaces"])

PAPER_FAMILIES = tuple(_RUNTIME_PROFILE["paper_families"])
SESSION_ALIASES = deepcopy(_RUNTIME_PROFILE["session_aliases"])
DOCUMENT_TYPE_ALIASES = deepcopy(_RUNTIME_PROFILE["document_types"]["aliases"])
COMPACT_DOCUMENT_TYPES = deepcopy(_RUNTIME_PROFILE["document_types"]["compact_codes"])
PAPER_FAMILY_TAXONOMY = deepcopy(_RUNTIME_PROFILE["paper_family_taxonomy"])
CLASSIFICATION_HINT_OVERRIDES = deepcopy(_RUNTIME_PROFILE["classification_hints"])
DIFFICULTY_LABELS = tuple(_RUNTIME_PROFILE["difficulty_labels"])
DIFFICULTY_HEURISTICS = deepcopy(_RUNTIME_PROFILE["difficulty_heuristics"])
