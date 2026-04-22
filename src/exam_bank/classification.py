from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import re
from pathlib import Path
from typing import Any

from .config import AppConfig
from .document_metadata import parse_filename_metadata
from .models import ClassificationResult


TASK_VERB_PATTERNS = {
    "solve": r"\bsolve\b",
    "differentiate": r"\bdifferentiat(?:e|ion)\b|\bfind\s+dy\s*/\s*dx\b",
    "integrate": r"\bintegrat(?:e|ion|al)\b|∫",
    "show": r"\bshow that\b|\bdeduce\b|\bhence\b",
    "express": r"\bexpress\b|\bwrite\b",
    "expand": r"\bexpand\b|\bascending powers\b",
    "prove": r"\bprove\b",
    "estimate": r"\bestimat(?:e|ion)\b",
    "find_equation": r"\bfind the equation of\b",
    "iterate": r"\biterat(?:e|ion|ive)\b",
    "sketch": r"\bsketch\b|\bdraw\b",
    "test": r"\bhypothesis\b|\bsignificance\b|\btest\b",
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
_PAPER_CODE_RE = re.compile(r"(?:qp|ms|paper|p)[_\-\s]*(?P<code>[1-6][0-9])\b", re.IGNORECASE)
_PAPER_FAMILY_RE = re.compile(r"\bP(?P<family>[1-6])\b", re.IGNORECASE)


@dataclass
class TopicCandidate:
    paper_family: str
    topic: str
    subtopic: str
    score: float = 0.0
    methods: list[str] = field(default_factory=list)
    objects: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    boosts: list[str] = field(default_factory=list)
    source_scores: dict[str, float] = field(default_factory=dict)
    method_scores: dict[str, float] = field(default_factory=dict)
    object_cue_prior_score: float = 0.0
    object_anchor_bonus: float = 0.0
    object_protection_penalty: float = 0.0

    @property
    def label(self) -> str:
        return f"{self.paper_family}:{self.topic}:{self.subtopic}"

    @property
    def topic_label(self) -> str:
        return f"{self.topic}:{self.subtopic}"

    @property
    def has_method_and_object(self) -> bool:
        return bool(self.methods and self.objects)

    @property
    def source_method_total(self) -> float:
        return sum(self.source_scores.values()) + sum(self.method_scores.values())


@dataclass(frozen=True)
class QuestionPartSegment:
    part_label: str
    text: str
    classification_text: str


@dataclass(frozen=True)
class FamilyDecision:
    source_paper_family: str
    source_paper_code: str
    inferred_paper_family: str
    paper_family: str
    paper_family_confidence: str
    allowed_families: list[str]
    review_flags: list[str]


@dataclass(frozen=True)
class DifficultyDecision:
    difficulty: str
    confidence: str
    evidence: str
    uncertain: bool
    numeric_confidence: float
    review_flags: list[str]


@dataclass(frozen=True)
class ObjectCueDecision:
    detected_object_cues: list[str]
    topic_scores: dict[str, float]
    evidence: dict[str, list[str]]
    primary_topic: str
    flags: list[str]
    conflict_with_method_scoring: bool = False
    source_topic_scores: dict[str, dict[str, float]] = field(default_factory=dict)


def classify_question(
    text: str,
    marks: int | None,
    config: AppConfig,
    context_flags: list[str] | None = None,
    source_name: str | None = None,
    forced_paper_family: str | None = None,
    examiner_report_text: str = "",
    mark_scheme_text: str = "",
    question_ocr_text: str = "",
    body_text_normalized: str = "",
    part_texts: list[dict[str, Any]] | None = None,
    body_text_raw: str = "",
    math_lines: list[str] | None = None,
) -> ClassificationResult:
    local = _local_classify(
        text,
        marks,
        config,
        context_flags=context_flags or [],
        source_name=source_name,
        forced_paper_family=forced_paper_family,
        examiner_report_text=examiner_report_text,
        mark_scheme_text=mark_scheme_text,
        question_ocr_text=question_ocr_text,
        body_text_normalized=body_text_normalized,
        part_texts=part_texts or [],
        body_text_raw=body_text_raw,
        math_lines=math_lines or [],
    )
    if not config.classification.enable_openai:
        return local

    if not os.environ.get("OPENAI_API_KEY"):
        local.review_flags.append("openai_enabled_but_api_key_missing")
        return local

    try:
        ai_result = _classify_with_openai(text, marks, config, local)
    except Exception as exc:  # pragma: no cover - depends on network/API
        local.review_flags.append(f"openai_classification_failed:{exc.__class__.__name__}")
        return local

    ai_result.review_flags = sorted(set(local.review_flags + ai_result.review_flags))
    return ai_result


def classify_question_parts(
    text: str,
    question_number: str,
    config: AppConfig,
    context_flags: list[str] | None = None,
    source_name: str | None = None,
    forced_paper_family: str | None = None,
    examiner_report_text: str = "",
    mark_scheme_text: str = "",
    question_ocr_text: str = "",
    structured_part_texts: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    segments = split_question_parts(text, question_number)
    structured_parts = _index_structured_part_texts(structured_part_texts or [])
    part_topics: list[dict[str, Any]] = []
    for segment in segments:
        marks = _extract_marks(segment.text)
        structured_part = structured_parts.get(_normalize_part_key(segment.part_label), {})
        result = _local_classify(
            segment.classification_text,
            marks,
            config,
            context_flags=context_flags or [],
            source_name=source_name,
            forced_paper_family=forced_paper_family,
            examiner_report_text=examiner_report_text,
            mark_scheme_text=mark_scheme_text,
            question_ocr_text=question_ocr_text,
            body_text_normalized=str(structured_part.get("normalized_text", "")),
            part_texts=[],
            body_text_raw=str(structured_part.get("raw_text", "")),
            math_lines=list(structured_part.get("math_lines", [])) if isinstance(structured_part.get("math_lines", []), list) else [],
        )
        part_topics.append(
            {
                "part_label": segment.part_label,
                "paper_family": result.paper_family,
                "source_paper_code": result.source_paper_code,
                "source_paper_family": result.source_paper_family,
                "inferred_paper_family": result.inferred_paper_family,
                "paper_family_confidence": result.paper_family_confidence,
                "topic": result.topic,
                "subtopic": result.subtopic,
                "topic_confidence": result.topic_confidence,
                "topic_evidence": result.topic_evidence,
                "secondary_topics": result.secondary_topics,
                "topic_uncertain": result.topic_uncertain,
                "difficulty": result.difficulty,
                "difficulty_confidence": result.difficulty_confidence,
                "difficulty_evidence": result.difficulty_evidence,
                "difficulty_uncertain": result.difficulty_uncertain,
                "confidence": round(result.confidence, 3),
                "marks": marks,
                "review_flags": result.review_flags,
                "topic_candidates": result.alternative_topics,
                "detected_object_cues": result.topic_evidence_details.get("detected_object_cues", []),
                "object_cue_topic_scores": result.topic_evidence_details.get("object_cue_topic_scores", {}),
                "object_cue_evidence": result.topic_evidence_details.get("object_cue_evidence", {}),
                "object_cue_primary_topic": result.topic_evidence_details.get("object_cue_primary_topic", ""),
                "object_cue_conflict_with_method_scoring": result.topic_evidence_details.get(
                    "object_cue_conflict_with_method_scoring", False
                ),
                "object_cue_protection_applied": result.topic_evidence_details.get("object_cue_protection_applied", False),
                "object_cue_resisted_override": result.topic_evidence_details.get("object_cue_resisted_override", False),
                "source_method_stage_top_topic": result.topic_evidence_details.get("source_method_stage_top_topic", ""),
                "topic_score_breakdown": result.topic_evidence_details.get("topic_score_breakdown", {}),
                "text_snippet": _compact_snippet(segment.text),
            }
        )
    _apply_part_topic_continuity(part_topics, segments)
    return part_topics


def split_question_parts(text: str, question_number: str) -> list[QuestionPartSegment]:
    cleaned = text.strip()
    if not cleaned:
        return []

    alpha_segments = _segments_from_anchors(cleaned, question_number, _ALPHA_PART_ANCHOR_RE)
    if alpha_segments:
        return alpha_segments
    return _segments_from_anchors(cleaned, question_number, _ROMAN_PART_ANCHOR_RE)


def _apply_part_topic_continuity(
    part_topics: list[dict[str, Any]],
    segments: list[QuestionPartSegment],
) -> None:
    for index in range(1, min(len(part_topics), len(segments))):
        current = part_topics[index]
        previous = part_topics[index - 1]
        current_text = segments[index].text.lower()
        previous_topic = str(previous.get("topic", ""))
        current_topic = str(current.get("topic", ""))

        if not _is_continuity_dependent_part(current_text):
            continue
        if str(previous.get("topic_confidence", "low")) not in {"high", "medium"}:
            continue
        if current_topic == previous_topic:
            continue
        if str(previous.get("paper_family", "")) != str(current.get("paper_family", "")):
            continue
        if not (bool(current.get("topic_uncertain")) or str(current.get("topic_confidence", "")) == "low"):
            continue
        if _explicit_primary_topic_from_text(current_text, str(current.get("paper_family", ""))) not in {"", previous_topic}:
            continue

        old_topic = current_topic
        current["topic"] = previous_topic
        current["subtopic"] = "general"
        current["topic_confidence"] = "medium"
        current["topic_uncertain"] = False
        current["topic_evidence"] = f"continuity prior from earlier part; later part depends on the previous result within `{previous_topic}`"
        current["secondary_topics"] = [old_topic] if old_topic and old_topic != previous_topic else []
        current["topic_candidates"] = [f"{current['paper_family']}:{old_topic}:general"] if old_topic and old_topic != previous_topic else []
        flags = {
            flag
            for flag in list(current.get("review_flags", []))
            if flag
            not in {
                "topic_uncertain",
                "topic_forced_low_confidence",
                "topic_forced_no_rule_match",
                "topic_uncertain_no_rule_match",
                "mixed_topic_possible",
            }
            and not str(flag).startswith("topic_uncertain_")
        }
        flags.add("part_topic_continuity_applied")
        current["review_flags"] = sorted(flags)


def infer_source_paper_family(source_name: str | None) -> tuple[str, str]:
    metadata = parse_filename_metadata(source_name or "")
    if metadata.paper_family != "unknown":
        return metadata.paper_family, "high"
    code, confidence = infer_source_paper_code(source_name)
    if code:
        return f"P{code[0]}", confidence
    if not source_name:
        return "unknown", "low"
    name = Path(source_name).name
    direct = _PAPER_FAMILY_RE.search(name)
    if direct:
        return f"P{direct.group('family')}", "high"
    return "unknown", "low"


def infer_source_paper_code(source_name: str | None) -> tuple[str, str]:
    if not source_name:
        return "", "low"
    metadata = parse_filename_metadata(source_name)
    if metadata.component:
        return metadata.component, "high"
    name = Path(source_name).name
    match = _PAPER_CODE_RE.search(name)
    if match:
        return match.group("code"), "high"
    qp_match = re.search(r"(?:^|[_\-\s])(?:qp|ms)[_\-\s]*(?P<code>[1-6][0-9])(?:\D|$)", name, re.IGNORECASE)
    if qp_match:
        return qp_match.group("code"), "high"
    return "", "low"


def _local_classify(
    text: str,
    marks: int | None,
    config: AppConfig,
    context_flags: list[str],
    source_name: str | None,
    forced_paper_family: str | None = None,
    examiner_report_text: str = "",
    mark_scheme_text: str = "",
    question_ocr_text: str = "",
    body_text_normalized: str = "",
    part_texts: list[dict[str, Any]] | None = None,
    body_text_raw: str = "",
    math_lines: list[str] | None = None,
) -> ClassificationResult:
    normalized = _normalize_math_text(text)
    evidence_sources = {
        "examiner_report": _normalize_math_text(examiner_report_text),
        "mark_scheme": _normalize_math_text(mark_scheme_text),
        "question_text": normalized,
        "question_ocr": _normalize_math_text(question_ocr_text),
    }

    # Paper family is the first-stage decision. Final topic scoring must happen
    # only inside this restricted syllabus bank, not against a generic pool of
    # mathematical topics.
    family_decision = _decide_paper_family(normalized, config, source_name, forced_paper_family)
    object_cues = _detect_object_cues(
        family_decision.paper_family,
        body_text_normalized=body_text_normalized,
        part_texts=part_texts or [],
        body_text_raw=body_text_raw,
        math_lines=math_lines or [],
        combined_question_text=text,
        mark_scheme_text=mark_scheme_text,
    )
    candidates = _score_topic_candidates_from_sources(
        evidence_sources,
        config,
        family_decision.allowed_families,
        object_cues=object_cues,
    )
    candidates.sort(key=lambda item: item.score, reverse=True)

    flags: list[str] = list(family_decision.review_flags)
    if _text_quality_is_low(normalized) or any(flag.startswith("ocr") or "short_question_text" in flag for flag in context_flags):
        flags.append("topic_uncertain_low_quality_text")
        flags.append("weak_question_text")
    if mark_scheme_text and _text_quality_is_low(evidence_sources["mark_scheme"]):
        flags.append("weak_markscheme_signal")
    if not evidence_sources["mark_scheme"] and not evidence_sources["examiner_report"]:
        flags.append("weak_markscheme_signal")

    if candidates:
        top = candidates[0]
        alternatives = _plausible_alternatives(top, candidates[1:8])
        topic_confidence, topic_uncertain, topic_numeric_confidence = _topic_confidence(top, alternatives, flags)
        secondary_topics = _secondary_topics(top, alternatives)
        evidence = _evidence_string(top, alternatives)
        evidence_details = _topic_evidence_details(evidence_sources, object_cues)
        stage_summary = _score_stage_summary(candidates, top.paper_family, object_cues)
        evidence_details["topic_score_breakdown"] = _topic_score_breakdown(candidates, top.paper_family)
        evidence_details.update(stage_summary)
        if object_cues.primary_topic and object_cues.primary_topic != top.topic:
            evidence_details["object_cue_conflict_with_method_scoring"] = True
            flags.append("object_cue_conflict_with_method_scoring")
        elif stage_summary.get("object_cue_resisted_override"):
            flags.append("object_cue_resisted_override")
        if top.score <= 0:
            topic_confidence = "low"
            topic_uncertain = True
            topic_numeric_confidence = 0.35
            evidence = f"No strong rule matched; forced to {top.paper_family} allowed topic `{top.topic}`."
            flags.extend(["topic_forced_no_rule_match", "topic_forced_low_confidence"])
        if secondary_topics:
            flags.append("mixed_topic_possible")
        if len(secondary_topics) >= 2:
            flags.append("topic_uncertain_mixed_major_topics")
            topic_uncertain = True
            if topic_confidence == "high":
                topic_confidence = "medium"
                topic_numeric_confidence = min(topic_numeric_confidence, 0.66)
        if topic_uncertain:
            flags.append("topic_uncertain")
    else:
        fallback_family, fallback_topic, fallback_subtopic = _fallback_taxonomy_label(config, family_decision.paper_family)
        top = TopicCandidate(fallback_family, fallback_topic, fallback_subtopic)
        alternatives = []
        topic_confidence = "low"
        topic_uncertain = True
        topic_numeric_confidence = 0.35
        secondary_topics = []
        evidence = "No configured method or object rule matched this question."
        evidence_details = _topic_evidence_details(evidence_sources, object_cues)
        evidence_details["topic_score_breakdown"] = {}
        flags.extend(["topic_uncertain", "topic_uncertain_no_rule_match"])

    if not evidence_sources["examiner_report"] and not evidence_sources["mark_scheme"] and evidence_sources["question_ocr"]:
        flags.append("topic_ocr_only_evidence")
        topic_uncertain = True
    if alternatives and top.score - alternatives[0].score <= 1.5:
        flags.append("topic_close_score")

    difficulty = _infer_difficulty(
        normalized,
        marks,
        top.paper_family,
        top.topic,
        top.subtopic,
        secondary_topics,
        topic_confidence,
        config,
    )
    flags.extend(difficulty.review_flags)
    if difficulty.uncertain:
        flags.append("difficulty_uncertain")

    confidence_value = min(topic_numeric_confidence, difficulty.numeric_confidence)
    if confidence_value < config.classification.uncertainty_threshold:
        flags.append("low_classification_confidence")

    return ClassificationResult(
        paper_family=family_decision.paper_family,
        source_paper_code=family_decision.source_paper_code,
        source_paper_family=family_decision.source_paper_family,
        inferred_paper_family=family_decision.inferred_paper_family,
        paper_family_confidence=family_decision.paper_family_confidence,
        topic=top.topic,
        subtopic=top.subtopic,
        difficulty=difficulty.difficulty,
        difficulty_confidence=difficulty.confidence,
        difficulty_evidence=difficulty.evidence,
        difficulty_uncertain=difficulty.uncertain,
        confidence=confidence_value,
        review_flags=sorted(set(flags)),
        topic_confidence=topic_confidence,
        topic_evidence=evidence,
        topic_evidence_details=evidence_details,
        secondary_topics=secondary_topics,
        topic_uncertain=topic_uncertain,
        alternative_topics=[candidate.label for candidate in alternatives[:2]],
    )


def _decide_paper_family(
    text: str,
    config: AppConfig,
    source_name: str | None,
    forced_paper_family: str | None,
) -> FamilyDecision:
    valid_families = [family for family in config.paper_families if family != "unknown"]
    source_paper_code, _source_code_confidence = infer_source_paper_code(source_name)
    source_family, source_confidence = infer_source_paper_family(source_name)

    if forced_paper_family and forced_paper_family in valid_families:
        return FamilyDecision(
            source_family,
            source_paper_code,
            forced_paper_family,
            forced_paper_family,
            "high",
            [forced_paper_family],
            [],
        )

    if source_family in valid_families and source_confidence == "high":
        return FamilyDecision(source_family, source_paper_code, source_family, source_family, "high", [source_family], [])

    family_scores = _family_scores(text, config, valid_families)
    if not family_scores:
        return FamilyDecision(
            source_family,
            source_paper_code,
            "unknown",
            "unknown",
            "low",
            valid_families,
            ["paper_family_uncertain"],
        )

    top_family, top_score = family_scores[0]
    second_score = family_scores[1][1] if len(family_scores) > 1 else 0.0
    if top_score < 3.0:
        return FamilyDecision(
            source_family,
            source_paper_code,
            "unknown",
            "unknown",
            "low",
            valid_families,
            ["paper_family_uncertain"],
        )

    confidence = "medium" if top_score - second_score >= 2.0 else "low"
    flags = [] if confidence == "medium" else ["paper_family_uncertain"]
    return FamilyDecision(source_family, source_paper_code, top_family, top_family, confidence, [top_family], flags)


def _family_scores(text: str, config: AppConfig, families: list[str]) -> list[tuple[str, float]]:
    scores: list[tuple[str, float]] = []
    for family in families:
        candidates = _score_topic_candidates(text, config, [family])
        best = max((candidate.score for candidate in candidates), default=0.0)
        best += _family_context_boost(family, text)
        scores.append((family, best))
    return sorted(scores, key=lambda item: item[1], reverse=True)


def _score_topic_candidates(text: str, config: AppConfig, allowed_families: list[str]) -> list[TopicCandidate]:
    candidates: list[TopicCandidate] = []
    for family in allowed_families:
        topics = config.paper_family_taxonomy.get(family, {})
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
                _apply_specific_rule_boosts(candidate, text)
                candidates.append(candidate)
    return _best_candidate_per_topic(candidates)


def _score_topic_candidates_from_sources(
    evidence_sources: dict[str, str],
    config: AppConfig,
    allowed_families: list[str],
    object_cues: ObjectCueDecision | None = None,
) -> list[TopicCandidate]:
    source_weights = {
        "examiner_report": 1.6,
        "mark_scheme": 1.25,
        "question_text": 1.0,
        "question_ocr": 0.45,
    }
    direct_weights = {
        "examiner_report": 6.0,
        "mark_scheme": 4.0,
        "question_text": 3.0,
        "question_ocr": 1.0,
    }
    merged: dict[tuple[str, str], TopicCandidate] = {}
    for source, text in evidence_sources.items():
        if not text:
            continue
        for candidate in _score_topic_candidates(text, config, allowed_families):
            key = (candidate.paper_family, candidate.topic)
            target = merged.setdefault(
                key,
                TopicCandidate(candidate.paper_family, candidate.topic, candidate.subtopic),
            )
            source_contribution = candidate.score * source_weights.get(source, 1.0)
            target.score += source_contribution
            target.source_scores[source] = target.source_scores.get(source, 0.0) + source_contribution
            _extend_unique(target.methods, candidate.methods)
            _extend_unique(target.objects, candidate.objects)
            _extend_unique(target.keywords, candidate.keywords)
            if candidate.score > 0:
                target.boosts.append(f"{source}:{candidate.score:.1f}")
            method_boost = _method_first_topic_boost(target, text, source)
            if method_boost:
                method_contribution = method_boost * direct_weights.get(source, 1.0)
                target.score += method_contribution
                target.method_scores[source] = target.method_scores.get(source, 0.0) + method_contribution
                target.boosts.append(f"{source}:method_first:{method_boost:.1f}")
    for family in allowed_families:
        for topic, subtopics in config.paper_family_taxonomy.get(family, {}).items():
            merged.setdefault((family, topic), TopicCandidate(family, topic, subtopics[0] if subtopics else "general"))
    if object_cues:
        _apply_object_cue_priors(merged, allowed_families, object_cues)
    return sorted(merged.values(), key=lambda item: item.score, reverse=True)


def _extend_unique(target: list[str], values: list[str]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def _is_continuity_dependent_part(text: str) -> bool:
    return bool(re.search(r"\b(hence|deduce|using your answer|from part \(?[a-zivx]+\)?)\b", text, re.IGNORECASE))


def _index_structured_part_texts(part_texts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for index, part in enumerate(part_texts):
        label = _normalize_part_key(str(part.get("part_label", "")))
        if label:
            indexed[label] = part
        indexed[str(index)] = part
    return indexed


def _normalize_part_key(label: str) -> str:
    match = re.search(r"\((?P<label>[a-zivx]+)\)", label.lower())
    if match:
        return match.group("label")
    return label.strip().lower()


def _object_cue_map() -> dict[str, dict[str, list[tuple[str, str, float]]]]:
    return {
        "P1": {
            "series_and_sequences": [
                ("arithmetic progression", r"\barithmetic progression\b", 4.2),
                ("geometric progression", r"\bgeometric progression\b", 4.2),
                ("common difference", r"\bcommon difference\b", 3.8),
                ("common ratio", r"\bcommon ratio\b", 3.8),
                ("nth term", r"\bnth term\b", 3.6),
                ("sum to infinity", r"\bsum to infinity\b", 4.4),
                ("sum of", r"\bsum of\b", 2.0),
                ("AP", r"\bAP\b", 2.8),
                ("GP", r"\bGP\b", 2.8),
            ],
            "binomial_expansion": [
                ("expansion", r"\bexpand\b|\bexpansion\b", 3.4),
                ("ascending powers", r"\bascending powers\b", 4.2),
                ("coefficient of", r"\bcoefficient of\b", 4.0),
                ("binomial", r"\bbinomial\b", 3.6),
                ("first three terms", r"\bfirst three terms\b", 3.8),
            ],
            "functions": [
                ("transformation", r"\btransformation\b|\btransformations\b", 4.0),
                ("inverse function", r"\binverse function\b|\bf\^-?1\s*\(x\)|f\^{-1}\(x\)", 4.4),
                ("composite function", r"\bcomposite function\b|g\s*\(\s*f\s*\(x\)\s*\)|f\s*\(\s*g\s*\(x\)\s*\)", 4.4),
                ("domain", r"\bdomain\b", 3.8),
                ("range", r"\brange\b", 3.8),
                ("sketch the graph", r"\bsketch the graph\b", 2.8),
                ("y = f(x)", r"\by\s*=\s*f\s*\(x\)", 2.8),
            ],
            "circular_measure": [
                ("sector", r"\bsector\b", 4.4),
                ("arc", r"\barc\b|\barc length\b", 4.0),
                ("segment", r"\bsegment\b|\bperimeter of segment\b", 4.2),
                ("radians", r"\bradian(?:s)?\b", 3.8),
                ("area of sector", r"\barea of sector\b", 4.2),
            ],
            "trigonometry": [
                ("sin", r"\bsin\b", 2.2),
                ("cos", r"\bcos\b", 2.2),
                ("tan", r"\btan\b", 2.2),
                ("sec", r"\bsec\b", 2.0),
                ("cosec", r"\bcosec\b", 2.0),
                ("cot", r"\bcot\b", 2.0),
                ("trig equation", r"\btrig(?:onometric)? equation\b", 4.0),
                ("solve for theta interval", r"\bsolve\b.+\b0\s*<\s*[a-zθ]", 3.4),
                ("exact values", r"\bexact values?\b", 3.0),
                ("identities", r"\bidentit(?:y|ies)\b", 3.0),
            ],
            "quadratics": [
                ("discriminant", r"\bdiscriminant\b", 4.8),
                ("repeated root", r"\brepeated root\b|\bequal roots?\b", 4.6),
                ("two distinct roots", r"\btwo distinct roots?\b|\bdistinct intersections?\b", 4.4),
                ("solve the quadratic", r"\bsolve the quadratic\b|\bquadratic equation\b", 4.2),
                ("factorise", r"\bfactoris[ea]\b", 2.4),
            ],
            "coordinate_geometry": [
                ("gradient", r"\bgradient\b", 3.0),
                ("midpoint", r"\bmidpoint\b", 3.8),
                ("equation of line", r"\bequation of (?:the )?line\b|\bstraight line\b", 4.0),
                ("perpendicular bisector", r"\bperpendicular bisector\b", 4.2),
                ("circle with centre", r"\bcircle with centre\b|\bcentre\b", 3.6),
                ("distance between points", r"\bdistance between points\b", 3.8),
            ],
            "differentiation": [
                ("differentiate", r"\bdifferentiat(?:e|ion)\b", 4.2),
                ("derivative", r"\bderivative\b", 3.8),
                ("dy/dx", r"\bdy\s*/\s*dx\b", 4.2),
                ("stationary point", r"\bstationary point\b", 4.0),
                ("tangent", r"\btangent\b", 4.0),
                ("normal", r"\bnormal\b", 3.8),
                ("gradient of curve", r"\bgradient of (?:the )?curve\b", 4.0),
            ],
            "integration": [
                ("integrate", r"\bintegrat(?:e|ion)\b|∫", 4.4),
                ("area under the curve", r"\barea under the curve\b|\bfind the area under\b", 4.2),
                ("volume of revolution", r"\bvolume of revolution\b", 4.4),
            ],
        },
        "P3": {
            "logarithms_and_exponentials": [
                ("ln", r"\bln\b", 4.2),
                ("log", r"\blog\b", 3.6),
                ("exponential", r"\bexponential\b|e\^x|e\^\(", 4.2),
                ("straight line graph after logs", r"\bstraight line graph\b.+\blogs?\b|\btaking logs\b", 4.4),
                ("model of form", r"\bmodel of form\b", 3.2),
                ("linearise", r"\blinearise\b|\blinearize\b", 4.0),
            ],
            "modulus": [
                ("modulus", r"\bmodulus\b|\babsolute value\b", 4.4),
                ("|x|", r"\|x\|", 4.0),
                ("mod graph", r"\bmod graph\b", 3.8),
                ("modulus equation/inequality", r"\bmodulus\b.+\b(?:equation|inequalit)", 4.0),
            ],
            "complex_numbers": [
                ("complex number", r"\bcomplex number\b|\bcomplex roots?\b", 4.4),
                ("Argand diagram", r"\bargand(?: diagram)?\b", 5.0),
                ("locus in Argand diagram", r"\blocus of z\b|\blocus in argand\b", 4.8),
                ("modulus of z", r"\bmodulus of z\b|\|z\|", 4.6),
                ("argument of z", r"\bargument of z\b|\barg\s*\(?z\)?", 4.6),
                ("roots of complex equation", r"\broots? of complex equation\b", 4.4),
            ],
            "numerical_methods": [
                ("iteration", r"\biteration\b|\biterate\b", 4.6),
                ("fixed point", r"\bfixed point\b", 4.8),
                ("use the iterative formula", r"\biterative formula\b", 4.6),
                ("show root lies in", r"\bshow that the root lies in\b|\broot lies in\b", 4.4),
            ],
            "parametric_equations": [
                ("parametric", r"\bparametric\b", 4.8),
                ("parameter", r"\bparameter\b", 2.8),
                ("x(t), y(t)", r"\bx\s*=.+t|\by\s*=.+t", 3.8),
                ("dy/dx in terms of t", r"\bdy\s*/\s*dx\b.+\bin terms of t\b", 4.4),
            ],
            "implicit_differentiation": [
                ("implicitly", r"\bimplicitly\b", 4.8),
                ("relation between x and y", r"\brelation between x and y\b", 4.2),
                ("find dy/dx", r"\bfind\s+dy\s*/\s*dx\b", 3.8),
            ],
            "partial_fractions": [
                ("partial fractions", r"\bpartial fractions\b", 5.0),
                ("express in partial fractions", r"\bexpress\b.+\bpartial fractions\b", 4.8),
            ],
            "differential_equations": [
                ("differential equation", r"\bdifferential equation\b", 5.0),
                ("solve the differential equation", r"\bsolve the differential equation\b", 5.0),
                ("particular solution", r"\bparticular solution\b", 4.2),
            ],
            "vectors": [
                ("vector", r"\bvector\b|\bvectors\b", 4.2),
                ("position vector", r"\bposition vector\b", 4.4),
                ("line/plane vector form", r"\bvector equation\b|\bline\b.+\bvector\b|\bplane\b.+\bvector\b", 4.0),
            ],
            "polynomials": [
                ("remainder theorem", r"\bremainder theorem\b", 4.8),
                ("factor theorem", r"\bfactor theorem\b", 4.8),
                ("polynomial", r"\bpolynomial\b", 4.0),
                ("quotient", r"\bquotient\b", 3.4),
                ("root of polynomial", r"\broot of polynomial\b", 4.2),
            ],
        },
        "P4": {
            "momentum_impulse": [
                ("collision", r"\bcollision\b|\bcoalescence\b", 4.8),
                ("impulse", r"\bimpulse\b", 4.6),
                ("momentum", r"\bmomentum\b", 4.4),
                ("coefficient of restitution", r"\bcoefficient of restitution\b", 4.8),
                ("loss of kinetic energy in collision", r"\bloss of kinetic energy\b", 4.4),
            ],
            "kinematics_graphs": [
                ("velocity-time graph", r"\bvelocity-?time graph\b|\bv-?t graph\b", 5.0),
                ("displacement-time graph", r"\bdisplacement-?time graph\b|\bs-?t graph\b", 4.8),
                ("area under graph", r"\barea under (?:the )?graph\b", 4.0),
            ],
            "kinematics_constant_acceleration": [
                ("constant acceleration", r"\bconstant acceleration\b", 5.0),
                ("starts from rest", r"\bstarts from rest\b", 3.2),
                ("moves with acceleration", r"\bmoves with acceleration\b", 3.8),
                ("SUVAT-style motion", r"\bsuvat\b", 4.8),
            ],
            "kinematics_variable_functions": [
                ("v as a function of t", r"\bv\s+as a function of t\b|\bv\(t\)", 4.8),
                ("s as a function of t", r"\bs\s+as a function of t\b|\bs\(t\)", 4.8),
                ("a as a function of t", r"\ba\s+as a function of t\b|\ba\(t\)", 4.8),
            ],
            "equilibrium_coplanar_forces": [
                ("in equilibrium", r"\bin equilibrium\b", 3.8),
                ("coplanar forces", r"\bcoplanar forces\b", 5.0),
                ("force diagram", r"\bforce diagram\b", 3.6),
                ("tension and angle balance", r"\btension\b.+\bangle\b", 3.4),
            ],
            "equilibrium_particle": [
                ("in equilibrium", r"\bin equilibrium\b", 3.8),
                ("particle in equilibrium", r"\bparticle\b.+\bequilibrium\b", 4.8),
            ],
            "friction_rough_plane": [
                ("rough plane", r"\brough plane\b", 5.0),
                ("coefficient of friction", r"\bcoefficient of friction\b", 5.0),
                ("limiting equilibrium", r"\blimiting equilibrium\b", 4.8),
            ],
            "connected_particles": [
                ("two particles connected", r"\btwo particles connected\b|\bconnected particles\b", 5.0),
                ("light inextensible string", r"\blight inextensible string\b", 4.8),
                ("pulley", r"\bpulley\b", 4.6),
            ],
            "work_energy_power": [
                ("work done", r"\bwork done\b", 4.4),
                ("kinetic energy", r"\bkinetic energy\b", 4.4),
                ("potential energy", r"\bpotential energy\b", 4.4),
                ("power", r"\bpower\b", 4.2),
            ],
            "power_and_resistance": [
                ("resistance proportional to", r"\bresistance proportional to\b", 5.0),
                ("engine power", r"\bengine power\b", 5.0),
                ("power", r"\bpower\b", 4.0),
            ],
        },
        "P5": {
            "measures_of_central_tendency_and_dispersion": [
                ("mean", r"\bmean\b", 4.0),
                ("standard deviation", r"\bstandard deviation\b", 4.4),
                ("variance", r"\bvariance\b", 4.2),
                ("quartile", r"\bquartile\b", 4.0),
                ("interquartile range", r"\binterquartile range\b|\bIQR\b", 4.2),
                ("coding", r"\bcoding\b", 4.0),
                ("Σx", r"Σx|\bsigma x\b", 3.4),
                ("Σx^2", r"Σx\^?2|\bsigma x\^?2\b", 3.6),
            ],
            "data_representation": [
                ("histogram", r"\bhistogram\b", 5.0),
                ("cumulative frequency", r"\bcumulative frequency\b", 4.8),
                ("stem-and-leaf", r"\bstem-?and-?leaf\b", 4.8),
                ("back-to-back stem-and-leaf", r"\bback-?to-?back stem-?and-?leaf\b", 5.0),
                ("box-and-whisker", r"\bbox-?and-?whisker\b|\bbox plot\b", 4.8),
            ],
            "permutations_and_combinations": [
                ("number of ways", r"\bnumber of ways\b", 4.2),
                ("arrangements", r"\barrangements?\b", 4.4),
                ("committee", r"\bcommittee\b", 4.8),
                ("selection", r"\bselection\b|\bchoose from\b", 3.8),
                ("permutations", r"\bpermutations?\b", 4.4),
                ("combinations", r"\bcombinations?\b", 4.4),
            ],
            "probability_distributions": [
                ("probability distribution table", r"\bprobability distribution table\b", 5.0),
                ("random variable X takes values", r"\brandom variable\b.+\btakes values\b", 5.0),
                ("P(X = x)", r"\bP\s*\(\s*X\s*=\s*[a-z0-9]+\s*\)", 4.8),
            ],
            "geometric_distribution": [
                ("first success", r"\bfirst success\b", 5.0),
                ("repeated until", r"\brepeated until\b", 4.6),
                ("number of trials until", r"\bnumber of trials until\b", 4.8),
            ],
            "binomial_distribution": [
                ("sample of n", r"\bsample of\b", 3.4),
                ("number who", r"\bnumber who\b", 3.0),
                ("X ~ B(...)", r"\bX\s*~\s*B\b", 5.0),
            ],
            "normal_distribution": [
                ("normally distributed", r"\bnormally distributed\b", 5.0),
                ("normal distribution", r"\bnormal distribution\b", 5.0),
                ("z", r"\bz\b", 2.6),
                ("expected number with value above/below", r"\bexpected number\b.+\b(?:above|below)\b", 4.2),
                ("find mean/standard deviation from percentile information", r"\bpercentile\b|\bmedian\b.+\bnormal\b", 4.0),
            ],
            "probability": [
                ("conditional probability", r"\bconditional probability\b", 4.6),
                ("given that", r"\bgiven that\b", 3.8),
                ("probability tree", r"\btree diagram\b|\bprobability tree\b", 4.2),
                ("without replacement", r"\bwithout replacement\b|\bwith replacement\b", 3.6),
            ],
        },
    }


def _detect_object_cues(
    paper_family: str,
    *,
    body_text_normalized: str,
    part_texts: list[dict[str, Any]],
    body_text_raw: str,
    math_lines: list[str],
    combined_question_text: str,
    mark_scheme_text: str,
) -> ObjectCueDecision:
    cue_map = _object_cue_map().get(paper_family, {})
    if not cue_map:
        return ObjectCueDecision([], {}, {}, "", [])

    source_texts = [
        ("body_text_normalized", _normalize_math_text(body_text_normalized), 1.7),
        (
            "part_texts",
            " ".join(
                _normalize_math_text(str(part.get("normalized_text", "")))
                for part in part_texts
                if str(part.get("normalized_text", "")).strip()
            ),
            1.35,
        ),
        ("body_text_raw", _normalize_math_text(body_text_raw), 1.15),
        ("math_lines", _normalize_math_text(" ".join(math_lines)), 0.7),
        ("combined_question_text", _normalize_math_text(combined_question_text), 0.55),
        ("mark_scheme_text", _normalize_math_text(mark_scheme_text), 0.35),
    ]

    detected: list[str] = []
    topic_scores: dict[str, float] = {}
    evidence: dict[str, list[str]] = {}
    flags: list[str] = []
    source_topic_scores: dict[str, dict[str, float]] = {}

    for topic, cues in cue_map.items():
        for cue_name, pattern, base_weight in cues:
            matched_sources: list[str] = []
            score = 0.0
            matched_source_scores: dict[str, float] = {}
            for source_name, source_text, source_weight in source_texts:
                if not source_text or not re.search(pattern, source_text, re.IGNORECASE):
                    continue
                matched_sources.append(source_name)
                weighted = base_weight * source_weight
                matched_source_scores[source_name] = matched_source_scores.get(source_name, 0.0) + weighted
                score += weighted
            if not matched_sources:
                continue
            topic_scores[topic] = topic_scores.get(topic, 0.0) + score
            evidence.setdefault(topic, []).append(f"{cue_name} ({', '.join(matched_sources)})")
            topic_source_scores = source_topic_scores.setdefault(topic, {})
            for source_name, weighted in matched_source_scores.items():
                topic_source_scores[source_name] = topic_source_scores.get(source_name, 0.0) + weighted
            detected.append(cue_name)

    if len(topic_scores) >= 2:
        ranked = sorted(topic_scores.items(), key=lambda item: item[1], reverse=True)
        if ranked[0][1] - ranked[1][1] <= 2.0:
            flags.append("object_cue_competition")

    primary_topic = max(topic_scores.items(), key=lambda item: item[1])[0] if topic_scores else ""
    return ObjectCueDecision(
        detected_object_cues=sorted(set(detected)),
        topic_scores={topic: round(score, 3) for topic, score in sorted(topic_scores.items(), key=lambda item: item[1], reverse=True)},
        evidence={topic: cues for topic, cues in sorted(evidence.items())},
        primary_topic=primary_topic,
        flags=sorted(set(flags)),
        source_topic_scores={
            topic: {source: round(score, 3) for source, score in sorted(source_scores.items())}
            for topic, source_scores in sorted(source_topic_scores.items())
        },
    )


def _topic_signal_patterns() -> dict[str, dict[str, str]]:
    return {
        "P1": {
            "binomial_expansion": r"expan|ascending powers|coefficient of|required term",
            "series_and_sequences": r"\bAP\b|\bGP\b|arithmetic progression|geometric progression|common difference|common ratio|sum to infinity|nth term",
            "functions": r"transformation|inverse|composite|domain|range",
            "circular_measure": r"sector|arc|segment|radian|perimeter of segment|area of sector",
            "differentiation": r"tangent to (?:the )?curve|normal to (?:the )?curve|stationary point|dy\s*/\s*dx|differentiat",
            "quadratics": r"discriminant|repeated root|equal roots|quadratic equation|distinct intersections",
        },
        "P3": {
            "complex_numbers": r"argand|modulus|argument|locus of z|complex roots|\|z\|",
            "logarithms_and_exponentials": r"\bln\b|\blog\b|e\^x|exponential|taking logs|straight line graph",
            "numerical_methods": r"iterate|iteration|fixed point|show .* root lies|change of sign|newton",
            "parametric_equations": r"parametric|dx/dt|dy/dt|x\s*=.*t|y\s*=.*t",
            "implicit_differentiation": r"implicit|implicitly",
            "partial_fractions": r"partial fractions",
            "integration": r"integrat|definite integral|find the area",
            "binomial_expansion": r"expan|ascending powers|coefficient of|required term",
        },
        "P4": {
            "momentum_impulse": r"collision|coalescence|impulse|momentum|loss of kinetic energy|coefficient of restitution",
            "kinematics_graphs": r"velocity-?time graph|speed-?time graph|displacement-?time graph",
            "kinematics_constant_acceleration": r"constant acceleration|suvat",
            "friction_rough_plane": r"rough plane|coefficient of friction|limiting equilibrium",
            "work_energy_power": r"work done|kinetic energy|potential energy|\bpower\b",
            "power_and_resistance": r"engine power|resistance.*speed|driving force",
        },
        "P5": {
            "measures_of_central_tendency_and_dispersion": r"mean|standard deviation|variance|quartile|interquartile|IQR|coding|combined mean",
            "data_representation": r"stem-?and-?leaf|histogram|box plot|cumulative frequency",
            "permutations_and_combinations": r"committee|arrangement|restriction|different ways|choose",
            "geometric_distribution": r"first success|until the first|geometric distribution",
            "binomial_distribution": r"\bX\s*~\s*B|binomial distribution|fixed number of trials",
            "probability_distributions": r"probability distribution table|P\(X\s*=",
            "normal_distribution": r"normal distribution|z-?value|standardise|expected number",
        },
    }


def _apply_object_cue_priors(
    merged: dict[tuple[str, str], TopicCandidate],
    allowed_families: list[str],
    object_cues: ObjectCueDecision,
) -> None:
    if not object_cues.topic_scores:
        return

    protected_algebraic_topics = {"algebra", "quadratics", "polynomials"}
    primary_score = object_cues.topic_scores.get(object_cues.primary_topic, 0.0)
    primary_source_scores = object_cues.source_topic_scores.get(object_cues.primary_topic, {})
    stem_primary_score = sum(
        score
        for source, score in primary_source_scores.items()
        if source in {"body_text_normalized", "part_texts", "body_text_raw", "math_lines", "combined_question_text"}
    )
    for family in allowed_families:
        for topic, cue_score in object_cues.topic_scores.items():
            candidate = merged.get((family, topic))
            if candidate is None:
                continue
            candidate.score += cue_score
            candidate.object_cue_prior_score += cue_score
            _extend_unique(candidate.objects, object_cues.evidence.get(topic, []))
            candidate.boosts.append(f"object_cue:{cue_score:.1f}")
            if topic == object_cues.primary_topic and cue_score >= 9.0:
                anchor_bonus = 4.0 if stem_primary_score >= 12.0 else 2.5
                candidate.score += anchor_bonus
                candidate.object_anchor_bonus += anchor_bonus
                candidate.boosts.append(f"object_anchor:{anchor_bonus:.1f}")

        if object_cues.primary_topic and primary_score >= 9.0:
            protection_penalty = 6.5 if stem_primary_score >= 12.0 else 3.5
            for topic in protected_algebraic_topics:
                if topic == object_cues.primary_topic:
                    continue
                candidate = merged.get((family, topic))
                if candidate is None:
                    continue
                candidate.score -= protection_penalty
                candidate.object_protection_penalty -= protection_penalty
                candidate.boosts.append(f"object_protection:-{protection_penalty:.1f}->{object_cues.primary_topic}")


def _explicit_primary_topic_from_text(text: str, paper_family: str) -> str:
    for topic, pattern in _topic_signal_patterns().get(paper_family, {}).items():
        if re.search(pattern, text, re.IGNORECASE):
            return topic
    return ""


def _topic_has_explicit_signal(topic: str, text: str, paper_family: str) -> bool:
    pattern = _topic_signal_patterns().get(paper_family, {}).get(topic, "")
    return bool(pattern and re.search(pattern, text, re.IGNORECASE))


def _method_first_topic_boost(candidate: TopicCandidate, text: str, source: str) -> float:
    topic = candidate.topic
    patterns = {
        "algebra": [r"simplify|algebraic|rationali[sz]e|surd|rearrange"],
        "quadratics": [
            r"discriminant|repeated roots|equal roots|nature of roots",
            r"elimination leading to (?:a )?quadratic|leading to (?:a )?quadratic",
        ],
        "series_and_sequences": [r"\bAP\b|\bGP\b|arithmetic progression|geometric progression|sum to infinity|sequence|series"],
        "coordinate_geometry": [r"substitute (?:the )?line into (?:the )?circle|line (?:and|into) circle|coordinate geometry"],
        "trigonometry": [r"common denominator.*trig|trig(?:onometric)? identity|use (?:a )?trig(?:onometric)? identity"],
        "integration": [r"integrate f'?\\?'\(x\)|constant of integration|set up (?:a )?correct integral|definite integral|volume of revolution"],
        "binomial_expansion": [r"select the required term|required term|coefficient of|binomial expansion|ascending powers"],
        "functions": [r"sequence of transformations|composite function|composite.*identity|inverse function|domain|range"],
        "differentiation": [r"differentiat|stationary point|gradient function|tangent|normal"],
        "modulus": [r"modulus|absolute value|\|[a-z0-9]"],
        "logarithms_and_exponentials": [r"\blog\b|\bln\b|exponential|e\^|taking logs|straight line graph"],
        "numerical_methods": [r"iteration|iterative formula|newton|estimate.*root|change of sign|fixed point"],
        "implicit_differentiation": [r"implicitly|implicit relation"],
        "partial_fractions": [r"partial fractions"],
        "complex_numbers": [r"argand|complex number|modulus and argument|roots of.*complex"],
        "polynomials": [r"polynomial|factor theorem|remainder theorem|remainder|factorise"],
        "vectors": [r"position vector|scalar product|vector equation|vectors?"],
        "differential_equations": [r"differential equation|separate variables|rate of change"],
        "kinematics_constant_acceleration": [r"constant acceleration|suvat|\bu\b.*\bv\b.*\ba\b.*\bs\b.*\bt\b"],
        "kinematics_graphs": [r"velocity-?time graph|speed-?time graph|displacement-?time graph|area under.*graph"],
        "kinematics_variable_functions": [r"v\(t\)|a\(t\)|s\(t\)|velocity.*function of t|acceleration.*function of t"],
        "forces_newtons_second_law": [r"newton'?s second law|resultant force|ma\b"],
        "equilibrium_coplanar_forces": [r"coplanar forces|three forces|equilibrium"],
        "equilibrium_particle": [r"particle.*equilibrium|equilibrium of a particle"],
        "friction_rough_plane": [r"rough plane|coefficient of friction|limiting equilibrium|about to move"],
        "connected_particles": [r"connected particles|pulley|tension|string"],
        "momentum_impulse": [r"momentum|impulse|collision|coefficient of restitution"],
        "connected_particles_energy": [r"connected particles|pulley|tension|string|kinetic energy|potential energy"],
        "rough_plane_energy": [r"rough plane|friction|kinetic energy|potential energy|work done against friction"],
        "work_energy_power": [r"work energy|kinetic energy|potential energy|power"],
        "power_and_resistance": [r"power|engine|resistance.*speed|driving force"],
        "data_representation": [r"histogram|box plot|cumulative frequency|stem-?and-?leaf"],
        "measures_of_central_tendency_and_dispersion": [r"mean|variance|standard deviation|quartile|interquartile|IQR|coding"],
        "permutations_and_combinations": [r"permutation|combination|arrangement|selection|required ways"],
        "probability": [r"probability|conditional|independent events|tree diagram"],
        "probability_distributions": [r"probability distribution table|random variable|E\(X\)|Var\(X\)"],
        "geometric_distribution": [r"first success|until the first|geometric distribution"],
        "binomial_distribution": [r"binomial distribution|\bX\s*~\s*B"],
        "normal_distribution": [r"normal distribution|standardi[sz]e|standard deviation|z value"],
    }
    for pattern in patterns.get(topic, []):
        if re.search(pattern, text, re.IGNORECASE):
            return 1.0
    if source == "question_ocr":
        return 0.0
    return 0.0


def _best_candidate_per_topic(candidates: list[TopicCandidate]) -> list[TopicCandidate]:
    best: dict[tuple[str, str], TopicCandidate] = {}
    for candidate in candidates:
        key = (candidate.paper_family, candidate.topic)
        current = best.get(key)
        if current is None or candidate.score > current.score:
            best[key] = candidate
    return sorted(best.values(), key=lambda item: item.score, reverse=True)


def _apply_hint_group(candidate: TopicCandidate, text: str, patterns: list[str], attr: str, weight: float) -> None:
    matched: list[str] = []
    for pattern in patterns:
        if _pattern_matches(pattern, text):
            matched.append(pattern)
    if not matched:
        return
    setattr(candidate, attr, matched)
    candidate.score += len(matched) * weight


def _apply_specific_rule_boosts(candidate: TopicCandidate, text: str) -> None:
    detected_verbs = _detected_task_verbs(text)
    if candidate.topic == "algebra" and re.search(r"simplify|algebraic|rationali[sz]e|surd|rearrange", text):
        candidate.score += 4.0
    if candidate.topic == "quadratics" and re.search(r"quadratic|discriminant|complete the square|root", text):
        candidate.score += 5.0
        if re.search(r"expan|ascending powers|coefficient of|required term|arithmetic progression|geometric progression|sum to infinity|\blog\b|\bln\b|e\^|connected particles|pulley|tension", text):
            candidate.score -= 4.0
    if candidate.topic == "polynomials" and re.search(r"polynomial|factor theorem|remainder theorem|divided by|remainder|factorise", text):
        candidate.score += 5.0
    if candidate.topic == "partial_fractions" and re.search(r"partial fractions", text):
        candidate.score += 9.0
        candidate.methods.append("partial fractions")
    if candidate.topic == "modulus" and re.search(r"modulus|absolute value|\|[a-z0-9]", text):
        candidate.score += 5.0
    if candidate.topic == "functions" and re.search(r"function|domain|range|inverse|composite|f\s*\(|g\s*\(|transformation", text):
        candidate.score += 5.0
        if re.search(r"gradient of (?:the )?curve|stationary point|differentiat", text):
            candidate.score -= 2.0
    if candidate.topic == "coordinate_geometry" and re.search(r"straight line|circle|coordinate|gradient|equation of.*line|tangent|normal", text):
        candidate.score += 5.0
        if re.search(r"tangent to (?:the )?curve|normal to (?:the )?curve|dy\s*/\s*dx|differentiat", text):
            candidate.score -= 2.0
    if candidate.topic == "circular_measure" and re.search(r"radian|arc length|sector|area of sector", text):
        candidate.score += 6.0
    if candidate.topic == "series_and_sequences" and re.search(r"\bAP\b|\bGP\b|sequence|series|sum to infinity|arithmetic progression|geometric progression", text):
        candidate.score += 6.0
    if candidate.topic == "binomial_expansion" and ("expand" in detected_verbs or "ascending powers" in text):
        candidate.score += 4.0
        if re.search(r"negative power|fractional power|valid for|coefficient|required term", text):
            candidate.score += 3.0
    if candidate.topic == "numerical_methods" and re.search(r"iteration|iterative formula|newton|estimate.*root|change of sign", text):
        candidate.score += 6.0
    if candidate.topic == "integration" and "integrate" in detected_verbs:
        candidate.score += 8.0
        candidate.methods.append("integrate")
        if re.search(r"by parts|product|x\s*(?:sec|sin|cos|e\^|ln)", text):
            candidate.score += 3.0
            candidate.objects.append("product integral")
        if re.search(r"substitution|using\s+u\s*=", text):
            candidate.score += 3.0
            candidate.objects.append("substitution integral")
        if re.search(r"area|definite|limits", text):
            candidate.score += 2.0
    if candidate.topic == "differentiation" and re.search(r"differentiat|dy\s*/\s*dx|stationary|tangent|normal|implicit", text):
        candidate.score += 5.0
        candidate.methods.append("differentiate")
    if candidate.topic == "implicit_differentiation" and re.search(r"implicit|implicitly", text):
        candidate.score += 7.0
    if candidate.topic == "complex_numbers" and re.search(r"\bargand\b|complex (?:number|root)|\barg\s*\(?z|\|z\|", text):
        candidate.score += 9.0
    if candidate.topic == "vectors" and re.search(r"\bvector\b|scalar product|position vector|line", text):
        candidate.score += 4.0
    if candidate.topic == "differential_equations" and re.search(r"differential equation|dy\s*/\s*dx|rate of change", text):
        candidate.score += 5.0
    if candidate.topic == "logarithms_and_exponentials" and re.search(r"\blog\b|\bln\b|exponential|e\^|e\(", text):
        candidate.score += 6.0
        if re.search(r"taking logs|straight line graph|linearise", text):
            candidate.score += 3.0
    if candidate.topic == "trigonometry" and re.search(r"\bsin\b|\bcos\b|\btan\b|sec|cosec|cot|radian|trig", text):
        candidate.score += 5.0
    if candidate.topic == "parametric_equations" and re.search(r"parametric|parameter|x\s*=.*t|y\s*=.*t", text):
        candidate.score += 6.0
    if candidate.paper_family == "P4":
        if candidate.topic == "kinematics_constant_acceleration" and re.search(r"constant acceleration|suvat", text):
            candidate.score += 6.0
        if candidate.topic == "kinematics_graphs" and re.search(r"velocity-?time graph|speed-?time graph|displacement-?time graph|area under", text):
            candidate.score += 6.0
        if candidate.topic == "kinematics_variable_functions" and re.search(r"v\(t\)|a\(t\)|s\(t\)|differentiate.*velocity|integrate.*acceleration", text):
            candidate.score += 6.0
        if candidate.topic == "connected_particles" and re.search(r"connected particles|pulley|tension|string", text):
            candidate.score += 8.0
            if re.search(r"pulley", text) and re.search(r"tension|string", text):
                candidate.score += 2.0
        if candidate.topic == "forces_newtons_second_law" and re.search(r"newton|ma\b|resultant force|acceleration", text):
            candidate.score += 6.0
        if candidate.topic == "equilibrium_coplanar_forces" and re.search(r"coplanar|three forces|equilibrium", text):
            candidate.score += 6.0
        if candidate.topic == "equilibrium_particle" and re.search(r"equilibrium|particle", text):
            candidate.score += 4.0
        if candidate.topic == "friction_rough_plane" and re.search(r"friction|coefficient of friction|rough plane|limiting", text):
            candidate.score += 6.0
        if candidate.topic == "momentum_impulse" and re.search(r"momentum|impulse|collision|coefficient of restitution", text):
            candidate.score += 7.0
        if candidate.topic == "work_energy_power" and re.search(r"work|energy|power|kinetic|potential", text):
            candidate.score += 7.0
        if candidate.topic == "connected_particles_energy" and re.search(r"connected particles|pulley|tension|string", text) and re.search(r"energy|kinetic|potential", text):
            candidate.score += 8.0
        if candidate.topic == "rough_plane_energy" and re.search(r"rough plane|friction", text) and re.search(r"energy|kinetic|potential|work done", text):
            candidate.score += 8.0
        if candidate.topic == "power_and_resistance" and re.search(r"power|engine|resistance", text):
            candidate.score += 8.0
        if candidate.topic.startswith("kinematics_") and re.search(r"pulley|tension|string|force|friction", text):
            candidate.score -= 2.0
    if candidate.paper_family in {"P5", "P6"}:
        if candidate.topic == "hypothesis_testing" and re.search(r"hypothesis|significance|critical region", text):
            candidate.score += 7.0
        if candidate.topic == "data_representation" and re.search(r"histogram|box plot|stem|cumulative frequency", text):
            candidate.score += 7.0
        if candidate.topic == "measures_of_central_tendency_and_dispersion" and re.search(r"mean|variance|standard deviation|quartile|interquartile|IQR|coding", text):
            candidate.score += 7.0
        if candidate.topic == "probability_distributions" and re.search(r"probability distribution table|random variable|e\(x\)|var\(x\)", text):
            candidate.score += 7.0
        if candidate.topic == "geometric_distribution" and re.search(r"first success|until the first|geometric", text):
            candidate.score += 8.0
        if candidate.topic == "normal_distribution" and re.search(r"normal distribution|standard deviation|standardise", text):
            candidate.score += 5.0
        if candidate.topic == "binomial_distribution" and re.search(r"binomial|X\s*~\s*B", text):
            candidate.score += 6.0


def _family_context_boost(family: str, text: str) -> float:
    patterns = {
        "P3": r"complex|argand|vector|implicit|parametric|differential equation|partial fractions|log|ln|exponential",
        "P4": r"force|particle|tension|friction|pulley|acceleration|velocity|momentum|impulse|energy|power|equilibrium|collision",
        "P5": r"histogram|box plot|stem|cumulative frequency|permutation|combination|normal distribution|binomial distribution|geometric distribution|random variable",
        "P6": r"hypothesis|confidence interval|central limit|density function|continuous random variable|bayes|population mean",
    }
    pattern = patterns.get(family)
    if pattern and re.search(pattern, text):
        return 3.0
    return 0.0


def _topic_confidence(
    top: TopicCandidate,
    alternatives: list[TopicCandidate],
    existing_flags: list[str],
) -> tuple[str, bool, float]:
    second = next((candidate for candidate in alternatives if candidate.topic != top.topic), alternatives[0] if alternatives else None)
    gap = top.score - (second.score if second else 0.0)
    low_quality = any(flag.startswith("topic_uncertain_low_quality") or flag == "weak_question_text" for flag in existing_flags)
    weak_support = "weak_markscheme_signal" in existing_flags

    if top.score >= 10 and gap >= 3.0 and not low_quality and not weak_support:
        return "high", False, 0.88
    if top.score >= 5.0 and gap >= 1.4 and not low_quality:
        return "medium", False, 0.66
    return "low", True, 0.42


def _plausible_alternatives(top: TopicCandidate, candidates: list[TopicCandidate]) -> list[TopicCandidate]:
    plausible: list[TopicCandidate] = []
    for candidate in candidates:
        if candidate.score <= 0 or candidate.topic == top.topic:
            continue
        explicit_mixed = _mixed_topic_pair_is_meaningful(top.paper_family, top.topic, candidate.topic) and _topic_has_explicit_signal(
            candidate.topic, " ".join(candidate.methods + candidate.objects + candidate.keywords), top.paper_family
        )
        min_score = max(4.5, min(top.score * 0.45, 10.0)) if explicit_mixed else max(6.0, top.score * 0.72)
        max_gap = 24.0 if explicit_mixed else 2.2
        if candidate.score < min_score:
            continue
        if top.score - candidate.score > max_gap:
            continue
        if candidate.topic not in {item.topic for item in plausible}:
            plausible.append(candidate)
        if len(plausible) >= 2:
            break
    return plausible


def _secondary_topics(top: TopicCandidate, alternatives: list[TopicCandidate]) -> list[str]:
    secondary: list[str] = []
    for candidate in alternatives:
        if candidate.topic == top.topic:
            continue
        if not _mixed_topic_pair_is_meaningful(top.paper_family, top.topic, candidate.topic):
            continue
        if (
            candidate.score >= max(4.5, min(top.score * 0.45, 10.0))
            and (top.score - candidate.score <= 24.0)
            and candidate.topic not in secondary
        ):
            secondary.append(candidate.topic)
    return secondary[:2]


def _mixed_topic_pair_is_meaningful(paper_family: str, primary: str, secondary: str) -> bool:
    meaningful_pairs = {
        "P3": {
            ("partial_fractions", "integration"),
            ("integration", "partial_fractions"),
        },
        "P4": {
            ("connected_particles", "work_energy_power"),
            ("connected_particles", "connected_particles_energy"),
            ("friction_rough_plane", "rough_plane_energy"),
            ("work_energy_power", "power_and_resistance"),
        },
        "P5": {
            ("permutations_and_combinations", "probability"),
            ("probability", "permutations_and_combinations"),
            ("probability_distributions", "probability"),
        },
    }
    return (primary, secondary) in meaningful_pairs.get(paper_family, set())


def _fallback_taxonomy_label(config: AppConfig, paper_family: str) -> tuple[str, str, str]:
    families = [paper_family] if paper_family != "unknown" else [family for family in config.paper_families if family != "unknown"]
    for family in families:
        topics = config.paper_family_taxonomy.get(family, {})
        if topics:
            topic = next(iter(topics))
            return family, topic, topics[topic][0]
    return "unknown", "unknown", "unknown"


def _evidence_string(top: TopicCandidate, alternatives: list[TopicCandidate]) -> str:
    specific = _specific_evidence(top)
    if specific:
        return specific
    pieces = [f"matched {top.paper_family} {top.topic}/{top.subtopic}"]
    if top.boosts:
        pieces.append("source scores: " + ", ".join(top.boosts[:4]))
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


def _topic_score_breakdown(candidates: list[TopicCandidate], paper_family: str) -> dict[str, dict[str, Any]]:
    breakdown: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        if candidate.paper_family != paper_family:
            continue
        breakdown[candidate.topic] = {
            "source_scores": {source: round(score, 3) for source, score in sorted(candidate.source_scores.items())},
            "method_scores": {source: round(score, 3) for source, score in sorted(candidate.method_scores.items())},
            "source_method_total": round(candidate.source_method_total, 3),
            "object_cue_prior": round(candidate.object_cue_prior_score, 3),
            "object_anchor_bonus": round(candidate.object_anchor_bonus, 3),
            "object_protection_penalty": round(candidate.object_protection_penalty, 3),
            "final_score": round(candidate.score, 3),
        }
    return dict(sorted(breakdown.items(), key=lambda item: item[1]["final_score"], reverse=True))


def _score_stage_summary(
    candidates: list[TopicCandidate],
    paper_family: str,
    object_cues: ObjectCueDecision | None,
) -> dict[str, Any]:
    family_candidates = [candidate for candidate in candidates if candidate.paper_family == paper_family]
    if not family_candidates:
        return {}

    source_method_top = max(family_candidates, key=lambda candidate: candidate.source_method_total)
    final_top = max(family_candidates, key=lambda candidate: candidate.score)
    protection_topics = [
        candidate.topic
        for candidate in family_candidates
        if abs(candidate.object_protection_penalty) > 0.0
    ]
    primary_topic = object_cues.primary_topic if object_cues else ""
    return {
        "source_method_stage_top_topic": source_method_top.topic,
        "source_method_stage_top_score": round(source_method_top.source_method_total, 3),
        "object_cue_primary_topic": primary_topic,
        "object_cue_override_stage": "source_method_scoring" if primary_topic and primary_topic != final_top.topic else "",
        "object_cue_resisted_override": bool(primary_topic and primary_topic != source_method_top.topic and primary_topic == final_top.topic),
        "object_cue_override_topic": final_top.topic if primary_topic and primary_topic != final_top.topic else "",
        "object_cue_protection_applied": bool(protection_topics),
        "object_cue_protection_topics": protection_topics,
    }


def _specific_evidence(top: TopicCandidate) -> str:
    if top.topic == "partial_fractions":
        return "asks to express a rational function in partial fractions"
    if top.topic == "binomial_expansion":
        return "requires expansion or coefficient extraction using a binomial expansion"
    if top.topic == "functions":
        return "uses function methods such as inverse, composite, transformation, domain, or range"
    if top.topic == "integration":
        return "requires integration within the selected paper's syllabus"
    if top.topic == "differentiation":
        return "requires differentiation within the selected paper's syllabus"
    if top.paper_family == "P4" and top.topic in {"connected_particles", "forces_newtons_second_law", "connected_particles_energy"}:
        return "uses mechanics methods involving forces, tension systems, or Newton's second law"
    if top.topic == "complex_numbers":
        return "uses complex-number objects such as Argand diagrams, modulus, argument, or roots"
    if top.topic == "measures_of_central_tendency_and_dispersion":
        return "focuses on mean, variance, standard deviation, quartiles, or coding methods"
    return ""


def _topic_evidence_details(
    evidence_sources: dict[str, str],
    object_cues: ObjectCueDecision | None = None,
) -> dict[str, Any]:
    details: dict[str, Any] = {
        key: _compact_snippet(value, limit=260)
        for key, value in evidence_sources.items()
        if value
    }
    if object_cues:
        details["detected_object_cues"] = object_cues.detected_object_cues
        details["object_cue_topic_scores"] = object_cues.topic_scores
        details["object_cue_evidence"] = object_cues.evidence
        details["object_cue_primary_topic"] = object_cues.primary_topic
        details["object_cue_flags"] = object_cues.flags
        details["object_cue_source_topic_scores"] = object_cues.source_topic_scores
        details["object_cue_conflict_with_method_scoring"] = object_cues.conflict_with_method_scoring
    return details


def _infer_difficulty(
    text: str,
    marks: int | None,
    paper_family: str,
    topic: str,
    subtopic: str,
    secondary_topics: list[str],
    topic_confidence: str,
    config: AppConfig,
) -> DifficultyDecision:
    score = 0.7
    evidence: list[str] = []
    flags: list[str] = []
    heuristics = config.difficulty_heuristics.get(paper_family, config.difficulty_heuristics.get("unknown", {}))

    if marks is None:
        flags.append("marks_missing_for_difficulty")
        evidence.append("marks unavailable")
    elif marks <= 3:
        score -= 0.8
        evidence.append("low mark allocation")
    elif marks >= 10:
        score += 1.0
        evidence.append("very high mark allocation")
    elif marks >= 7:
        score += 0.6
        evidence.append("higher mark allocation")

    part_count = len(re.findall(r"^\s*(?:\d+\s*)?\([a-z]\)", text, flags=re.MULTILINE))
    if part_count >= 3:
        score += 0.5
        evidence.append("multiple linked parts")
    if part_count >= 4:
        score += 0.5

    if any(keyword in text for keyword in heuristics.get("linked_keywords", [])):
        score += 0.4
        evidence.append("chains results across parts")
    if any(keyword in text for keyword in heuristics.get("disguised_keywords", [])):
        score += 0.5
        evidence.append("less direct exam-style wording")

    algebraic_density = len(re.findall(r"[=+\-*/^√∫]|\\frac|\\sqrt|\b(?:sin|cos|tan|ln|e\^|arg)\b", text))
    if algebraic_density >= 22:
        score += 0.7
        evidence.append("high algebraic or symbolic density")
    if algebraic_density >= 32:
        score += 0.4
    if len(secondary_topics) >= 1 and topic_confidence != "low" and not _looks_like_direct_routine_application(text, paper_family, topic):
        score += 0.4
        evidence.append("mixes multiple syllabus ideas")

    if topic in heuristics.get("difficult_topics", []):
        score += 0.7
        evidence.append(f"{paper_family} topic is often later-paper difficulty")
    if topic in heuristics.get("routine_easy_topics", []):
        score -= 0.5
        evidence.append("routine topic for this paper")

    if _looks_like_direct_routine_application(text, paper_family, topic):
        score -= 1.0
        evidence.append("direct routine method")

    if marks is not None and marks <= 4 and _looks_like_direct_routine_application(text, paper_family, topic):
        label = "easy"
    elif score <= 1.2:
        label = "easy"
    elif score >= 3.4:
        label = "difficult"
    else:
        label = "average"

    confidence = "high"
    numeric_confidence = 0.82
    if marks is None or topic_confidence == "low":
        confidence = "medium"
        numeric_confidence = 0.62
    if _text_quality_is_low(text):
        confidence = "low"
        numeric_confidence = 0.42
    uncertain = confidence == "low"
    if uncertain:
        flags.append("difficulty_uncertain")

    if not evidence:
        evidence.append("routine-looking question with limited complexity signals")
    return DifficultyDecision(label, confidence, "; ".join(evidence[:5]), uncertain, numeric_confidence, flags)


def _looks_like_direct_routine_application(text: str, paper_family: str, topic: str) -> bool:
    direct_patterns = [
        r"^.*differentiate\b.*\[",
        r"^.*integrate\b.*\[",
        r"^.*solve\b.*quadratic.*\[",
        r"^.*find the gradient\b.*\[",
    ]
    if any(re.search(pattern, text) for pattern in direct_patterns) and "hence" not in text and "show that" not in text:
        return True
    if paper_family == "P4" and topic == "kinematics_constant_acceleration" and "constant acceleration" in text:
        return True
    return False


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
    if len(text) < 35:
        return True
    alpha_numeric = sum(char.isalnum() for char in text)
    if alpha_numeric / max(1, len(text)) < 0.32:
        return True
    replacement_markers = text.count("?") + text.count("\ufffd")
    return replacement_markers >= 4


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


def _classify_with_openai(text: str, marks: int | None, config: AppConfig, local: ClassificationResult) -> ClassificationResult:
    from openai import OpenAI

    family_taxonomy = config.paper_family_taxonomy.get(local.paper_family, {}) if local.paper_family != "unknown" else config.paper_family_taxonomy
    schema = {
        "type": "object",
        "properties": {
            "topic": {"type": "string"},
            "subtopic": {"type": "string"},
            "topic_confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "topic_evidence": {"type": "string"},
            "difficulty": {"type": "string", "enum": config.difficulty_labels},
            "difficulty_confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "difficulty_evidence": {"type": "string"},
        },
        "required": ["topic", "subtopic", "topic_confidence", "topic_evidence", "difficulty", "difficulty_confidence", "difficulty_evidence"],
        "additionalProperties": False,
    }
    client = OpenAI(timeout=config.classification.openai_timeout_seconds)
    prompt = (
        "Classify this CAIE 9709 maths question. Use only the supplied paper-family topic bank. "
        f"Paper family: {local.paper_family}. Topic bank:\n{json.dumps(family_taxonomy, indent=2)}\n\n"
        f"Marks: {marks if marks is not None else 'unknown'}\nQuestion:\n{text[:6000]}"
    )
    response = client.responses.create(
        model=config.classification.openai_model,
        input=prompt,
        text={"format": {"type": "json_schema", "name": "exam_question_classification", "schema": schema, "strict": True}},
    )
    data = json.loads(_response_text(response))
    if not _is_valid_topic_path(local.paper_family, str(data["topic"]), str(data["subtopic"]), config):
        return local
    local.topic = str(data["topic"])
    local.subtopic = str(data["subtopic"])
    local.topic_confidence = str(data["topic_confidence"])
    local.topic_evidence = str(data["topic_evidence"])
    local.difficulty = str(data["difficulty"])
    local.difficulty_confidence = str(data["difficulty_confidence"])
    local.difficulty_evidence = str(data["difficulty_evidence"])
    local.difficulty_uncertain = local.difficulty_confidence == "low"
    return local


def _is_valid_topic_path(paper_family: str, topic: str, subtopic: str, config: AppConfig) -> bool:
    if paper_family == "unknown":
        return any(subtopic in topics.get(topic, []) for family, topics in config.paper_family_taxonomy.items() if family != "unknown")
    return subtopic in config.paper_family_taxonomy.get(paper_family, {}).get(topic, [])


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
