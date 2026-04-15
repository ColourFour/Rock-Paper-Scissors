from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import re
from pathlib import Path
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

    @property
    def label(self) -> str:
        return f"{self.paper_family}:{self.topic}:{self.subtopic}"

    @property
    def topic_label(self) -> str:
        return f"{self.topic}:{self.subtopic}"

    @property
    def has_method_and_object(self) -> bool:
        return bool(self.methods and self.objects)


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


def classify_question(
    text: str,
    marks: int | None,
    config: AppConfig,
    context_flags: list[str] | None = None,
    source_name: str | None = None,
    forced_paper_family: str | None = None,
) -> ClassificationResult:
    local = _local_classify(
        text,
        marks,
        config,
        context_flags=context_flags or [],
        source_name=source_name,
        forced_paper_family=forced_paper_family,
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
) -> list[dict[str, Any]]:
    segments = split_question_parts(text, question_number)
    part_topics: list[dict[str, Any]] = []
    for segment in segments:
        marks = _extract_marks(segment.text)
        result = _local_classify(
            segment.classification_text,
            marks,
            config,
            context_flags=context_flags or [],
            source_name=source_name,
            forced_paper_family=forced_paper_family,
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
                "text_snippet": _compact_snippet(segment.text),
            }
        )
    return part_topics


def split_question_parts(text: str, question_number: str) -> list[QuestionPartSegment]:
    cleaned = text.strip()
    if not cleaned:
        return []

    alpha_segments = _segments_from_anchors(cleaned, question_number, _ALPHA_PART_ANCHOR_RE)
    if alpha_segments:
        return alpha_segments
    return _segments_from_anchors(cleaned, question_number, _ROMAN_PART_ANCHOR_RE)


def infer_source_paper_family(source_name: str | None) -> tuple[str, str]:
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
) -> ClassificationResult:
    normalized = _normalize_math_text(text)

    # Paper family is the first-stage decision. Final topic scoring must happen
    # only inside this restricted syllabus bank, not against a generic pool of
    # mathematical topics.
    family_decision = _decide_paper_family(normalized, config, source_name, forced_paper_family)
    candidates = _score_topic_candidates(normalized, config, family_decision.allowed_families)
    candidates.sort(key=lambda item: item.score, reverse=True)

    flags: list[str] = list(family_decision.review_flags)
    if _text_quality_is_low(normalized) or any(flag.startswith("ocr") or "short_question_text" in flag for flag in context_flags):
        flags.append("topic_uncertain_low_quality_text")

    if candidates:
        top = candidates[0]
        alternatives = [candidate for candidate in candidates[1:8] if candidate.score > 0]
        topic_confidence, topic_uncertain, topic_numeric_confidence = _topic_confidence(top, alternatives, flags)
        secondary_topics: list[str] = []
        evidence = _evidence_string(top, alternatives)
        if top.score <= 0:
            topic_confidence = "low"
            topic_uncertain = True
            topic_numeric_confidence = 0.35
            evidence = f"No strong rule matched; forced to {top.paper_family} allowed topic `{top.topic}`."
            flags.extend(["topic_forced_no_rule_match", "topic_forced_low_confidence"])
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
        flags.extend(["topic_uncertain", "topic_uncertain_no_rule_match"])

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
        secondary_topics=secondary_topics,
        topic_uncertain=topic_uncertain,
        alternative_topics=[candidate.label for candidate in alternatives[:6]],
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
    if candidate.topic == "quadratics" and re.search(r"quadratic|discriminant|complete the square|root", text):
        candidate.score += 5.0
    if candidate.topic == "polynomials" and re.search(r"polynomial|factor theorem|remainder theorem|divided by|remainder|factorise", text):
        candidate.score += 5.0
    if candidate.topic == "partial_fractions" and re.search(r"partial fractions", text):
        candidate.score += 9.0
        candidate.methods.append("partial fractions")
    if candidate.topic == "modulus" and re.search(r"modulus|absolute value|\|[a-z0-9]", text):
        candidate.score += 5.0
    if candidate.topic == "inequalities" and re.search(r"inequalit|≤|≥|<|>", text):
        candidate.score += 4.0
    if candidate.topic == "functions" and re.search(r"function|domain|range|inverse|composite|f\s*\(|g\s*\(|transformation", text):
        candidate.score += 5.0
    if candidate.topic == "coordinate_geometry" and re.search(r"straight line|circle|coordinate|gradient|equation of.*line|tangent|normal", text):
        candidate.score += 5.0
    if candidate.topic == "circular_measure" and re.search(r"radian|arc length|sector|area of sector", text):
        candidate.score += 6.0
    if candidate.topic == "binomial_expansion" and ("expand" in detected_verbs or "ascending powers" in text):
        candidate.score += 4.0
        if re.search(r"negative power|fractional power|valid for", text) and candidate.subtopic == "fractional_negative":
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
        if re.search(r"implicit", text):
            candidate.objects.append("implicit differentiation")
    if candidate.topic == "integration_by_parts" and "integrate" in detected_verbs and re.search(r"\bx\s*(?:sec|sin|cos|e\^|ln)", text):
        candidate.score += 6.0
        candidate.methods.append("integrate")
        candidate.objects.append("product requiring integration by parts")
    if candidate.topic == "integration_by_substitution" and re.search(r"substitution|using\s+u\s*=", text):
        candidate.score += 5.0
    if candidate.topic == "complex_numbers" and re.search(r"\bargand\b|complex (?:number|root)|\barg\s*\(?z|\|z\|", text):
        candidate.score += 9.0
    if candidate.topic == "vectors" and re.search(r"\bvector\b|scalar product|position vector|line", text):
        candidate.score += 4.0
    if candidate.topic == "differential_equations" and re.search(r"differential equation|dy\s*/\s*dx|rate of change", text):
        candidate.score += 5.0
    if candidate.topic == "logarithmic_and_exponential_functions" and re.search(r"\blog\b|\bln\b|exponential|e\^|e\(", text):
        candidate.score += 6.0
    if candidate.topic == "trigonometry" and re.search(r"\bsin\b|\bcos\b|\btan\b|sec|cosec|cot|radian|trig", text):
        candidate.score += 5.0
    if candidate.topic == "series" and re.search(r"maclaurin|series|ascending powers|binomial", text):
        candidate.score += 6.0
    if candidate.topic == "parametric_equations" and re.search(r"parametric|parameter|x\s*=.*t|y\s*=.*t", text):
        candidate.score += 6.0
    if candidate.paper_family == "P4":
        if candidate.topic == "connected_particles" and re.search(r"connected particles|pulley|tension|string", text):
            candidate.score += 8.0
            if re.search(r"pulley", text) and re.search(r"tension|string", text):
                candidate.score += 2.0
        if candidate.topic == "forces_and_equilibrium" and re.search(r"resolve|equilibrium|force|limiting", text):
            candidate.score += 4.0
        if candidate.topic == "forces_and_equilibrium" and re.search(r"friction|coefficient of friction", text):
            candidate.score += 6.0
        if candidate.topic == "momentum_and_impulse" and re.search(r"momentum|impulse|collision|coefficient of restitution", text):
            candidate.score += 7.0
        if candidate.topic == "work_energy_power" and re.search(r"work|energy|power|kinetic|potential", text):
            candidate.score += 7.0
        if candidate.topic == "circular_motion" and re.search(r"circular motion|centripetal|circle", text):
            candidate.score += 7.0
        if candidate.topic == "kinematics" and re.search(r"pulley|tension|string|force|friction", text):
            candidate.score -= 2.0
    if candidate.paper_family in {"P5", "P6"}:
        if candidate.topic == "hypothesis_testing" and re.search(r"hypothesis|significance|critical region", text):
            candidate.score += 7.0
        if candidate.topic == "normal_distribution" and re.search(r"normal distribution|standard deviation|standardise", text):
            candidate.score += 5.0
        if candidate.topic == "poisson_distribution" and re.search(r"poisson", text):
            candidate.score += 6.0
        if candidate.topic == "binomial_distribution" and re.search(r"binomial|X\s*~\s*B", text):
            candidate.score += 6.0


def _family_context_boost(family: str, text: str) -> float:
    patterns = {
        "P3": r"complex|argand|vector|implicit|parametric|differential equation|integration by parts|maclaurin",
        "P4": r"force|particle|tension|friction|pulley|acceleration|velocity|momentum|impulse|energy|power|equilibrium|collision",
        "P5": r"histogram|box plot|correlation|regression|permutation|combination|poisson|normal distribution|binomial distribution",
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
    low_quality = any(flag.startswith("topic_uncertain_low_quality") for flag in existing_flags)

    if top.score >= 9 and gap >= 2.5 and not low_quality:
        return "high", False, 0.88
    if top.score >= 4.5 and gap >= 1.2 and not low_quality:
        return "medium", False, 0.66
    return "low", True, 0.42


def _secondary_topics(top: TopicCandidate, alternatives: list[TopicCandidate]) -> list[str]:
    secondary: list[str] = []
    for candidate in alternatives:
        if candidate.topic == top.topic:
            continue
        if candidate.score >= max(4.5, top.score * 0.45) and candidate.topic not in secondary:
            secondary.append(candidate.topic)
    return secondary[:3]


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
    if top.topic == "partial_fractions":
        return "asks to express a rational function in partial fractions"
    if top.topic == "binomial_expansion":
        return "requires expansion in ascending powers using binomial series"
    if top.topic == "integration":
        return "requires integration within the selected paper's syllabus"
    if top.topic == "differentiation":
        return "requires differentiation within the selected paper's syllabus"
    if top.paper_family == "P4" and top.topic in {"connected_particles", "forces_and_equilibrium"}:
        return "uses forces, connected particles, and Newton's second law"
    if top.topic == "complex_numbers":
        return "uses complex-number objects such as Argand diagrams, modulus, argument, or roots"
    if top.topic == "hypothesis_testing":
        return "uses a hypothesis test with a probability distribution"
    return ""


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
    score = 1.0
    evidence: list[str] = []
    flags: list[str] = []
    heuristics = config.difficulty_heuristics.get(paper_family, config.difficulty_heuristics.get("unknown", {}))

    if marks is None:
        flags.append("marks_missing_for_difficulty")
        evidence.append("marks unavailable")
    elif marks <= 3:
        score -= 0.5
        evidence.append("low mark allocation")
    elif marks >= 10:
        score += 1.5
        evidence.append("very high mark allocation")
    elif marks >= 7:
        score += 1.0
        evidence.append("higher mark allocation")

    part_count = len(re.findall(r"^\s*(?:\d+\s*)?\([a-z]\)", text, flags=re.MULTILINE))
    if part_count >= 2:
        score += 0.8
        evidence.append("multiple linked parts")
    if part_count >= 4:
        score += 0.8

    if any(keyword in text for keyword in heuristics.get("linked_keywords", [])):
        score += 0.7
        evidence.append("chains results across parts")
    if any(keyword in text for keyword in heuristics.get("disguised_keywords", [])):
        score += 0.7
        evidence.append("less direct exam-style wording")

    algebraic_density = len(re.findall(r"[=+\-*/^√∫]|\\frac|\\sqrt|\b(?:sin|cos|tan|ln|e\^|arg)\b", text))
    if algebraic_density >= 18:
        score += 0.8
        evidence.append("high algebraic or symbolic density")
    if len(secondary_topics) >= 1:
        score += 0.8
        evidence.append("mixes multiple syllabus ideas")

    if topic in heuristics.get("difficult_topics", []):
        score += 1.0
        evidence.append(f"{paper_family} topic is often later-paper difficulty")
    if topic in heuristics.get("routine_easy_topics", []):
        score -= 0.4
        evidence.append("routine topic for this paper")

    if _looks_like_direct_routine_application(text, paper_family, topic):
        score -= 0.8
        evidence.append("direct routine method")

    if score <= 1.0:
        label = "easy"
    elif score >= 3.2:
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
    if paper_family == "P4" and topic == "kinematics" and "constant acceleration" in text:
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
