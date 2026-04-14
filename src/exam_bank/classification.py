from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import re
from typing import Any

from .config import AppConfig
from .models import ClassificationResult


TASK_VERB_PATTERNS = {
    "solve": r"\bsolve\b",
    "differentiate": r"\bdifferentiat(?:e|ion)\b|\bfind\s+dy\s*/\s*dx\b",
    "integrate": r"\bintegrat(?:e|ion|al)\b|∫",
    "show": r"\bshow that\b|\bdeduce\b|\bhence\b",
    "express": r"\bexpress\b|\bwrite\b",
    "expand": r"\bexpand\b|\bascending powers\b",
    "prove": r"\bprove\b",
    "find_equation": r"\bfind the equation of\b",
    "iterate": r"\biterat(?:e|ion|ive)\b",
    "newton_raphson": r"\bnewton[- ]raphson\b",
    "sketch": r"\bsketch\b|\bdraw\b",
    "calculate": r"\bcalculate\b|\bfind\b|\bdetermine\b",
}

_ALPHA_PART_ANCHOR_RE = re.compile(
    r"(?m)^(?P<prefix>\s*(?:(?P<question>\d{1,2})\s*)?\((?P<label>[a-h])\)(?:\s*\([ivx]+\))?\s*)",
    re.IGNORECASE,
)
_ROMAN_PART_ANCHOR_RE = re.compile(
    r"(?m)^(?P<prefix>\s*(?:(?P<question>\d{1,2})\s*)?\((?P<label>i{1,3}|iv|v|vi{0,3}|ix|x)\)\s*)",
    re.IGNORECASE,
)
_MARK_RE = re.compile(r"\[(\d{1,2})\]")


@dataclass
class TopicCandidate:
    paper_family: str
    topic: str
    subtopic: str
    score: float = 0.0
    methods: list[str] = field(default_factory=list)
    objects: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.paper_family}:{self.topic}:{self.subtopic}"

    @property
    def has_method_and_object(self) -> bool:
        return bool(self.methods and self.objects)


@dataclass(frozen=True)
class QuestionPartSegment:
    part_label: str
    text: str
    classification_text: str


def classify_question(
    text: str,
    marks: int | None,
    config: AppConfig,
    context_flags: list[str] | None = None,
) -> ClassificationResult:
    local = _local_classify(text, marks, config, context_flags=context_flags or [])
    if not config.classification.enable_openai:
        return local

    if not os.environ.get("OPENAI_API_KEY"):
        local.review_flags.append("openai_enabled_but_api_key_missing")
        return local

    try:
        ai_result = _classify_with_openai(text, marks, config)
    except Exception as exc:  # pragma: no cover - depends on network/API
        local.review_flags.append(f"openai_classification_failed:{exc.__class__.__name__}")
        return local

    merged_flags = sorted(set(local.review_flags + ai_result.review_flags))
    ai_result.review_flags = merged_flags
    return ai_result


def classify_question_parts(
    text: str,
    question_number: str,
    config: AppConfig,
    context_flags: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Classify detectable subparts without changing the grouped question label."""

    segments = split_question_parts(text, question_number)
    part_topics: list[dict[str, Any]] = []
    for segment in segments:
        marks = _extract_marks(segment.text)
        result = _local_classify(segment.classification_text, marks, config, context_flags=context_flags or [])
        part_topics.append(
            {
                "part_label": segment.part_label,
                "paper_family": result.paper_family,
                "topic": result.topic,
                "subtopic": result.subtopic,
                "topic_confidence": result.topic_confidence,
                "topic_evidence": result.topic_evidence,
                "secondary_topics": result.secondary_topics,
                "topic_uncertain": result.topic_uncertain,
                "confidence": round(result.confidence, 3),
                "marks": marks,
                "review_flags": result.review_flags,
                "text_snippet": _compact_snippet(segment.text),
            }
        )
    return part_topics


def split_question_parts(text: str, question_number: str) -> list[QuestionPartSegment]:
    """Split grouped question text into top-level subparts when labels are visible."""

    cleaned = text.strip()
    if not cleaned:
        return []

    alpha_segments = _segments_from_anchors(cleaned, question_number, _ALPHA_PART_ANCHOR_RE)
    if alpha_segments:
        return alpha_segments
    return _segments_from_anchors(cleaned, question_number, _ROMAN_PART_ANCHOR_RE)


def _segments_from_anchors(text: str, question_number: str, pattern: re.Pattern[str]) -> list[QuestionPartSegment]:
    matches = list(pattern.finditer(text))
    if not matches:
        return []

    preamble = text[: matches[0].start()].strip()
    segments: list[QuestionPartSegment] = []
    for index, match in enumerate(matches):
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        part_text = text[match.start() : next_start].strip()
        if len(part_text) < 12:
            continue

        label = match.group("label").lower()
        part_label = f"{question_number}({label})" if question_number else f"({label})"
        classification_text = f"{preamble}\n{part_text}".strip() if preamble else part_text
        segments.append(QuestionPartSegment(part_label=part_label, text=part_text, classification_text=classification_text))
    return segments


def _local_classify(
    text: str,
    marks: int | None,
    config: AppConfig,
    context_flags: list[str],
) -> ClassificationResult:
    normalized = _normalize_math_text(text)
    candidates = _score_topic_candidates(normalized, config)
    candidates.sort(key=lambda item: item.score, reverse=True)

    flags: list[str] = []
    if _text_quality_is_low(normalized) or any(flag.startswith("ocr") or "short_question_text" in flag for flag in context_flags):
        flags.append("topic_uncertain_low_quality_text")

    if candidates and candidates[0].score > 0:
        top = candidates[0]
        alternatives = [candidate for candidate in candidates[1:6] if candidate.score > 0]
        paper_family = _paper_family_for_top_candidate(top, alternatives)
        topic_confidence, topic_uncertain, confidence_value = _topic_confidence(top, alternatives, flags)
        secondary_topics = _secondary_topics(top, alternatives)
        mixed_topic_candidates = [
            candidate
            for candidate in alternatives[:5]
            if candidate.topic != top.topic and candidate.score >= max(5.0, top.score * 0.35)
        ]
        if mixed_topic_candidates:
            flags.append("topic_uncertain_mixed_major_topics")
            topic_uncertain = True
            if topic_confidence == "high":
                topic_confidence = "medium"
                confidence_value = min(confidence_value, 0.68)
        if paper_family == "mixed_or_uncertain":
            flags.append("paper_family_uncertain")
            if topic_confidence == "high":
                topic_confidence = "medium"
                confidence_value = min(confidence_value, 0.68)
        evidence = _evidence_string(top, alternatives)
        review_flags = list(flags)
        if topic_uncertain:
            review_flags.append("topic_uncertain")
    else:
        fallback_family, fallback_topic, fallback_subtopic = _fallback_taxonomy_label(config)
        top = TopicCandidate(fallback_family, fallback_topic, fallback_subtopic)
        alternatives = []
        paper_family = "mixed_or_uncertain"
        topic_confidence = "low"
        topic_uncertain = True
        confidence_value = 0.35
        secondary_topics = []
        evidence = "No configured method/object rule matched; defaulted to the first safe taxonomy label."
        review_flags = sorted(set(flags + ["topic_uncertain", "topic_uncertain_no_rule_match"]))

    difficulty, difficulty_confidence, difficulty_flags = _infer_difficulty(normalized, marks)
    review_flags.extend(difficulty_flags)
    confidence_value = min(confidence_value, difficulty_confidence)
    if confidence_value < config.classification.uncertainty_threshold:
        review_flags.append("low_classification_confidence")

    return ClassificationResult(
        paper_family=paper_family,
        topic=top.topic,
        subtopic=top.subtopic,
        difficulty=difficulty,
        confidence=confidence_value,
        review_flags=sorted(set(review_flags)),
        topic_confidence=topic_confidence,
        topic_evidence=evidence,
        secondary_topics=secondary_topics,
        topic_uncertain=topic_uncertain,
        alternative_topics=[candidate.label for candidate in alternatives[:5]],
    )


def _score_topic_candidates(text: str, config: AppConfig) -> list[TopicCandidate]:
    candidates: list[TopicCandidate] = []
    for family, topics in config.paper_family_taxonomy.items():
        if family == "mixed_or_uncertain":
            continue
        family_hints = config.classification_hints.get(family, {})
        for topic, subtopics in topics.items():
            topic_hints = family_hints.get(topic, {})
            for subtopic in subtopics:
                hints = topic_hints.get(subtopic, {})
                candidate = TopicCandidate(paper_family=family, topic=topic, subtopic=subtopic)
                _apply_hint_group(candidate, text, hints.get("methods", []), "methods", weight=4.0)
                _apply_hint_group(candidate, text, hints.get("objects", []), "objects", weight=3.0)
                _apply_hint_group(candidate, text, hints.get("keywords", []), "keywords", weight=1.2)
                if candidate.has_method_and_object:
                    candidate.score += 2.0
                _apply_family_rule_boosts(candidate, text)
                _apply_specific_rule_boosts(candidate, text)
                candidates.append(candidate)
    return candidates


def _apply_hint_group(candidate: TopicCandidate, text: str, patterns: list[str], attr: str, weight: float) -> None:
    matched: list[str] = []
    for pattern in patterns:
        if _pattern_matches(pattern, text):
            matched.append(pattern)
    if not matched:
        return
    setattr(candidate, attr, matched)
    candidate.score += len(matched) * weight


def _apply_family_rule_boosts(candidate: TopicCandidate, text: str) -> None:
    if candidate.paper_family == "P4" and re.search(
        r"force|particle|tension|friction|pulley|acceleration|velocity|momentum|impulse|energy|power|equilibrium",
        text,
    ):
        candidate.score += 1.8
    if candidate.paper_family in {"P5", "P6"} and re.search(
        r"probability|distribution|normal|poisson|binomial|hypothesis|sample|confidence interval|correlation|regression|variance|expected",
        text,
    ):
        candidate.score += 1.5
    if candidate.paper_family == "P6" and re.search(
        r"confidence interval|hypothesis|central limit|density function|continuous random variable|bayes|population mean",
        text,
    ):
        candidate.score += 2.8
    if candidate.paper_family == "P3" and re.search(
        r"complex|argand|vector|implicit|parametric|differential equation|integration by parts|substitution|maclaurin",
        text,
    ):
        candidate.score += 2.0


def _apply_specific_rule_boosts(candidate: TopicCandidate, text: str) -> None:
    detected_verbs = _detected_task_verbs(text)
    if candidate.paper_family == "P3" and candidate.topic == "calculus" and candidate.subtopic == "integration_by_parts":
        if "integrate" in detected_verbs and re.search(r"\bx\s*(?:sec|sin|cos|e\^|ln)", text):
            candidate.score += 4.0
            candidate.methods.append("integrate")
            candidate.objects.append("product requiring parts")
    if candidate.topic == "series" and "binomial_expansion" in candidate.subtopic:
        if "expand" in detected_verbs and re.search(r"ascending powers|valid for|approx", text):
            candidate.score += 3.0
    if candidate.topic == "algebra" and candidate.subtopic == "partial_fractions":
        if re.search(r"partial fractions", text):
            candidate.score += 4.0
    if candidate.topic == "complex_numbers":
        if re.search(r"\bargand\b|complex (?:number|root)|\barg\s*\(?z|\|z\|", text):
            candidate.score += 3.0
    if candidate.topic == "differential_equations" or candidate.subtopic == "differential_equations":
        if re.search(r"differential equation|dy\s*/\s*dx", text) and "solve" in detected_verbs:
            candidate.score += 3.0
    if candidate.paper_family == "P4" and candidate.topic == "dynamics":
        if re.search(r"newton'?s second law|f\s*=\s*ma|connected particles|pulley", text):
            candidate.score += 4.0
    if candidate.paper_family == "P6" and candidate.topic == "hypothesis_testing":
        if re.search(r"hypothesis|significance|critical region", text):
            candidate.score += 4.0


def _topic_confidence(
    top: TopicCandidate,
    alternatives: list[TopicCandidate],
    existing_flags: list[str],
) -> tuple[str, bool, float]:
    second = next(
        (
            candidate
            for candidate in alternatives
            if not (candidate.topic == top.topic and candidate.subtopic == top.subtopic)
        ),
        None,
    )
    gap = top.score - (second.score if second else 0)
    low_quality = any(flag.startswith("topic_uncertain_low_quality") for flag in existing_flags)

    if top.score >= 8 and gap >= 3 and top.has_method_and_object and not low_quality:
        return "high", False, 0.88
    if top.score >= 4 and gap >= 1.8 and not low_quality:
        return "medium", False, 0.66
    return "low", True, 0.42


def _paper_family_for_top_candidate(top: TopicCandidate, alternatives: list[TopicCandidate]) -> str:
    close_same_label = [
        candidate
        for candidate in alternatives
        if candidate.topic == top.topic
        and candidate.subtopic == top.subtopic
        and candidate.paper_family != top.paper_family
        and candidate.score >= top.score - 1.5
    ]
    if close_same_label:
        return "mixed_or_uncertain"
    close_families = {
        candidate.paper_family
        for candidate in [top] + alternatives[:4]
        if candidate.score >= max(5.0, top.score * 0.65)
    }
    if len(close_families) > 1 and top.score < 10:
        return "mixed_or_uncertain"
    return top.paper_family


def _fallback_taxonomy_label(config: AppConfig) -> tuple[str, str, str]:
    for family in config.paper_families:
        topics = config.paper_family_taxonomy.get(family, {})
        if topics:
            topic = next(iter(topics))
            return family, topic, topics[topic][0]
    return "mixed_or_uncertain", "uncertain", "uncertain"


def _secondary_topics(top: TopicCandidate, alternatives: list[TopicCandidate]) -> list[str]:
    secondary: list[str] = []
    for candidate in alternatives:
        if candidate.topic == top.topic:
            continue
        if candidate.score >= max(5.0, top.score * 0.35):
            if candidate.topic not in secondary:
                secondary.append(candidate.topic)
    return secondary[:3]


def _evidence_string(top: TopicCandidate, alternatives: list[TopicCandidate]) -> str:
    specific = _specific_evidence(top)
    if specific:
        return specific
    pieces = [f"matched {top.topic}/{top.subtopic}"]
    if top.methods:
        pieces.append("method cues: " + ", ".join(_clean_pattern(pattern) for pattern in top.methods[:2]))
    if top.objects:
        pieces.append("objects: " + ", ".join(_clean_pattern(pattern) for pattern in top.objects[:2]))
    if top.keywords:
        pieces.append("keywords: " + ", ".join(_clean_pattern(pattern) for pattern in top.keywords[:3]))
    close = [candidate.label for candidate in alternatives[:3] if candidate.score > 0]
    if close:
        pieces.append("alternatives: " + ", ".join(close))
    return "; ".join(pieces)


def _specific_evidence(top: TopicCandidate) -> str:
    if top.topic == "algebra" and top.subtopic == "partial_fractions":
        return "asks to express a rational function in partial fractions"
    if top.topic == "series" and top.subtopic == "binomial_expansion_fractional_negative":
        return "requires expansion in ascending powers using binomial series"
    if top.paper_family == "P3" and top.topic == "calculus" and top.subtopic == "integration_by_parts":
        return "finds an integral of a product, so integration by parts"
    if top.paper_family == "P4" and top.topic == "dynamics" and top.subtopic in {"newtons_laws", "connected_particles", "pulleys"}:
        return "uses forces, connected particles, and Newton's second law"
    if top.topic == "complex_numbers" and top.subtopic == "argand_diagrams":
        return "uses an Argand diagram representation of complex numbers"
    if top.topic == "hypothesis_testing":
        return f"uses a hypothesis test with the {top.subtopic.replace('_', ' ')} model"
    return ""


def _detected_task_verbs(text: str) -> set[str]:
    return {name for name, pattern in TASK_VERB_PATTERNS.items() if re.search(pattern, text, re.IGNORECASE)}


def _pattern_matches(pattern: str, text: str) -> bool:
    if pattern.startswith("regex:"):
        try:
            return re.search(pattern.removeprefix("regex:"), text, re.IGNORECASE) is not None
        except re.error:
            return False

    regex = _literal_hint_regex(pattern)
    try:
        return re.search(regex, text, re.IGNORECASE) is not None
    except re.error:
        return re.search(re.escape(pattern), text, re.IGNORECASE) is not None


def _literal_hint_regex(pattern: str) -> str:
    if ".*" in pattern:
        regex = ".*".join(re.escape(part).replace(r"\ ", r"\s+") for part in pattern.split(".*"))
    else:
        regex = re.escape(pattern).replace(r"\ ", r"\s+")
    if pattern and pattern[0].isalnum():
        regex = r"(?<![A-Za-z0-9_])" + regex
    if pattern and pattern[-1].isalnum():
        regex += r"(?![A-Za-z0-9_])"
    return regex


def _clean_pattern(pattern: str) -> str:
    return pattern.replace(".*", " ... ").replace("\\b", "").replace("\\", "")


def _normalize_math_text(text: str) -> str:
    normalized = text.replace("\u00a0", " ")
    normalized = normalized.replace("−", "-").replace("–", "-").replace("—", "-")
    normalized = normalized.replace("²", "^2").replace("³", "^3")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip().lower()


def _extract_marks(text: str) -> int | None:
    marks = [int(match.group(1)) for match in _MARK_RE.finditer(text)]
    return sum(marks) if marks else None


def _compact_snippet(text: str, limit: int = 220) -> str:
    snippet = re.sub(r"\s+", " ", text).strip()
    if len(snippet) <= limit:
        return snippet
    return snippet[: limit - 3].rstrip() + "..."


def _text_quality_is_low(text: str) -> bool:
    if len(text) < 40:
        return True
    alpha_numeric = sum(char.isalnum() for char in text)
    if alpha_numeric / max(1, len(text)) < 0.35:
        return True
    replacement_markers = text.count("?") + text.count("\ufffd")
    return replacement_markers >= 4


def _infer_difficulty(text: str, marks: int | None) -> tuple[str, float, list[str]]:
    score = 1
    flags: list[str] = []

    if marks is None:
        flags.append("marks_missing_for_difficulty")
        confidence = 0.55
    else:
        confidence = 0.68
        if marks <= 3:
            score -= 1
        elif marks >= 8:
            score += 1
        if marks >= 11:
            score += 1

    subpart_count = len(re.findall(r"^\s*\([a-z]\)", text, flags=re.MULTILINE))
    if subpart_count >= 3:
        score += 1
    if subpart_count >= 5:
        score += 1

    if any(phrase in text for phrase in ["show that", "prove", "hence", "deduce", "given that"]):
        score += 1
    if any(phrase in text for phrase in ["differential equation", "complex", "vector", "iteration"]):
        score += 1

    algebra_density = len(re.findall(r"[=+\-*/^√∫]|\\frac|\\sqrt", text))
    if algebra_density >= 20:
        score += 1
    if len(text) > 1200:
        score += 1

    if score <= 0:
        return "easy", min(0.85, confidence + 0.1), flags
    if score >= 3:
        return "difficult", min(0.86, confidence + 0.08), flags
    return "average", confidence, flags


def _classify_with_openai(text: str, marks: int | None, config: AppConfig) -> ClassificationResult:
    from openai import OpenAI

    subtopic_enum = sorted({subtopic for subtopics in config.topic_taxonomy.values() for subtopic in subtopics})
    schema = {
        "type": "object",
        "properties": {
            "paper_family": {"type": "string", "enum": config.paper_families},
            "topic": {"type": "string", "enum": list(config.topic_taxonomy)},
            "subtopic": {"type": "string", "enum": subtopic_enum},
            "topic_confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "topic_evidence": {"type": "string"},
            "secondary_topics": {"type": "array", "items": {"type": "string"}},
            "topic_uncertain": {"type": "boolean"},
            "difficulty": {"type": "string", "enum": config.difficulty_labels},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "review_flags": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "paper_family",
            "topic",
            "subtopic",
            "topic_confidence",
            "topic_evidence",
            "secondary_topics",
            "topic_uncertain",
            "difficulty",
            "confidence",
            "review_flags",
        ],
        "additionalProperties": False,
    }

    client = OpenAI(timeout=config.classification.openai_timeout_seconds)
    prompt = (
        "Classify this A Level mathematics exam question using the fixed taxonomy. "
        "First infer the Cambridge 9709 paper_family from the mathematics required, not from the filename. "
        "Then choose the dominant topic/subtopic required to solve the grouped question. "
        "Use a valid paper_family/topic/subtopic path only. Provide short evidence based on task verbs and mathematical objects.\n\n"
        f"Taxonomy:\n{json.dumps(config.topic_taxonomy, indent=2)}\n\n"
        f"Family taxonomy:\n{json.dumps(config.paper_family_taxonomy, indent=2)}\n\n"
        f"Marks: {marks if marks is not None else 'unknown'}\n\n"
        f"Question:\n{text[:6000]}"
    )
    response = client.responses.create(
        model=config.classification.openai_model,
        input=prompt,
        text={
            "format": {
                "type": "json_schema",
                "name": "exam_question_classification",
                "schema": schema,
                "strict": True,
            }
        },
    )
    raw = _response_text(response)
    data = json.loads(raw)
    return _classification_from_mapping(data, config)


def _response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text

    output = getattr(response, "output", None)
    if output:
        chunks: list[str] = []
        for item in output:
            for content in getattr(item, "content", []) or []:
                text = getattr(content, "text", None)
                if text:
                    chunks.append(text)
        if chunks:
            return "\n".join(chunks)
    raise ValueError("OpenAI response did not contain output text.")


def _classification_from_mapping(data: dict[str, Any], config: AppConfig) -> ClassificationResult:
    paper_family = str(data["paper_family"])
    topic = str(data["topic"])
    subtopic = str(data["subtopic"])
    difficulty = str(data["difficulty"])
    if paper_family not in config.paper_families:
        raise ValueError(f"OpenAI returned unknown paper family: {paper_family}")
    if paper_family != "mixed_or_uncertain" and topic not in config.paper_family_taxonomy[paper_family]:
        raise ValueError(f"OpenAI returned invalid topic `{topic}` for paper family `{paper_family}`.")
    if topic not in config.topic_taxonomy:
        raise ValueError(f"OpenAI returned unknown topic: {topic}")
    if paper_family != "mixed_or_uncertain" and subtopic not in config.paper_family_taxonomy[paper_family][topic]:
        raise ValueError(f"OpenAI returned invalid subtopic `{subtopic}` for {paper_family}.{topic}.")
    if subtopic not in config.topic_taxonomy[topic]:
        raise ValueError(f"OpenAI returned invalid subtopic `{subtopic}` for topic `{topic}`.")
    if difficulty not in config.difficulty_labels:
        raise ValueError(f"OpenAI returned unknown difficulty: {difficulty}")
    topic_confidence = str(data.get("topic_confidence", "low"))
    if topic_confidence not in {"high", "medium", "low"}:
        topic_confidence = "low"
    confidence = float(data.get("confidence", 0.5))
    flags = [str(flag) for flag in data.get("review_flags", [])]
    topic_uncertain = bool(data.get("topic_uncertain", topic_confidence == "low"))
    if topic_uncertain:
        flags.append("topic_uncertain")
    return ClassificationResult(
        paper_family=paper_family,
        topic=topic,
        subtopic=subtopic,
        difficulty=difficulty,
        confidence=max(0, min(1, confidence)),
        review_flags=sorted(set(flags)),
        topic_confidence=topic_confidence,
        topic_evidence=str(data.get("topic_evidence") or ""),
        secondary_topics=[str(item) for item in data.get("secondary_topics", [])],
        topic_uncertain=topic_uncertain,
        alternative_topics=[str(item) for item in data.get("secondary_topics", [])],
    )
