from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import json
import re
from pathlib import Path
from typing import Any

from .classification import _score_topic_candidates_from_sources, infer_source_paper_code
from .config import AppConfig
from .document_metadata import companion_candidates, parse_filename_metadata
from .identifiers import normalize_question_id, parent_question_id
from .mupdf_tools import quiet_mupdf


MATH_CUE_PATTERNS = {
    "discriminant": r"\bdiscriminant\b|equal roots|repeated roots|nature of roots",
    "chain rule": r"\bchain rule\b",
    "translation": r"\btranslation\b|transform(?:ation|ed)|stretch|reflection",
    "tangent": r"\btangent\b|normal\b|gradient",
    "circle": r"\bcircle\b|radius|centre|diameter",
    "AP/GP": r"\bAP\b|\bGP\b|arithmetic progression|geometric progression",
    "integration by parts": r"integration by parts|integrat(?:e|ing).*by parts",
    "partial fractions": r"partial fractions?",
    "force diagram": r"force diagram|free-body diagram|resolve forces?|equilibrium|tension|friction",
    "hypothesis test": r"hypothesis test|significance level|critical region|null hypothesis|alternative hypothesis",
    "quadratic": r"\bquadratic\b|complete the square",
    "common denominator": r"common denominator",
    "trig identity": r"trig(?:onometric)? identity|\bsin\b|\bcos\b|\btan\b",
    "constant of integration": r"constant of integration",
    "required term": r"required term|coefficient of",
    "vectors": r"\bvector\b|scalar product|position vector",
    "complex numbers": r"argand|complex number|modulus|argument",
    "probability distribution": r"binomial distribution|poisson|normal distribution|random variable",
    "correlation/regression": r"correlation|regression|pmcc|least squares",
    "kinematics": r"velocity|acceleration|displacement|constant acceleration",
    "momentum/impulse": r"momentum|impulse|collision|coefficient of restitution",
    "work/energy/power": r"work energy|kinetic energy|potential energy|power",
}

METHOD_PATTERNS = {
    "solve": r"\bsolve\b|solving",
    "differentiate": r"differentiat(?:e|ing|ion)|dy\s*/\s*dx",
    "integrate": r"integrat(?:e|ing|ion|al)",
    "set up integral": r"set up (?:a )?correct integral",
    "substitute": r"substitut(?:e|ed|ing)",
    "eliminate": r"eliminat(?:e|ed|ion)",
    "expand": r"\bexpand(?:ed|ing)?\b|ascending powers",
    "sketch": r"\bsketch(?:ed|ing)?\b|draw(?:n|ing)?",
    "resolve forces": r"resolv(?:e|ed|ing) forces?",
    "standardise": r"standardi[sz](?:e|ed|ing)",
    "test hypothesis": r"test(?:ed|ing)?|hypothesis",
}

LINKED_HINT_PATTERNS = {
    "use result from part": r"use (?:the )?(?:result|answer).{0,40}part\s*\([a-h]\)|from part\s*\([a-h]\)",
    "hence": r"\bhence\b",
    "using previous answer": r"using (?:their|the|your) (?:previous )?answer|using (?:their|the|your) result",
}


@dataclass(frozen=True)
class ExaminerReportEvidence:
    paper_code: str
    question_number: str
    subpart: str = ""
    canonical_topic: str = ""
    topic_confidence: str = "low"
    methods_skills: list[str] = field(default_factory=list)
    common_errors: list[str] = field(default_factory=list)
    linked_question_hints: list[str] = field(default_factory=list)
    mathematical_cues: list[str] = field(default_factory=list)

    @property
    def classification_text(self) -> str:
        pieces = [
            f"canonical topic {self.canonical_topic}" if self.canonical_topic else "",
            "methods " + " ".join(self.methods_skills) if self.methods_skills else "",
            "linked hints " + " ".join(self.linked_question_hints) if self.linked_question_hints else "",
            "mathematical cues " + " ".join(self.mathematical_cues) if self.mathematical_cues else "",
        ]
        return ". ".join(piece for piece in pieces if piece)

    def to_dict(self) -> dict[str, object]:
        return {
            "paper_code": self.paper_code,
            "question_number": self.question_number,
            "subpart": self.subpart,
            "canonical_topic": self.canonical_topic,
            "topic_confidence": self.topic_confidence,
            "methods_skills": self.methods_skills,
            "common_errors": self.common_errors,
            "linked_question_hints": self.linked_question_hints,
            "mathematical_cues": self.mathematical_cues,
        }


def examiner_report_evidence(
    source_pdf: str | Path,
    reports_dir: str | Path,
    question_id: str,
    report_paths: list[Path] | None = None,
) -> str:
    reports_dir = Path(reports_dir)
    source_pdf = Path(source_pdf)
    metadata = parse_filename_metadata(source_pdf)
    paper_code, _confidence = infer_source_paper_code(source_pdf.name)
    wanted = normalize_question_id(question_id)
    parent = parent_question_id(wanted)

    for path in _explicit_report_paths(report_paths or []):
        evidence = _report_evidence(path, wanted, parent, paper_code)
        if evidence:
            return evidence

    if not reports_dir.exists():
        return ""
    if metadata.canonical_key:
        for path in companion_candidates(metadata, reports_dir, "ER"):
            evidence = _report_evidence(path, wanted, parent, paper_code)
            if evidence:
                return evidence
    for path in _session_report_paths(reports_dir, metadata.session_key):
        evidence = _report_evidence(path, wanted, parent, paper_code)
        if evidence:
            return evidence
    keys = _candidate_keys(source_pdf, paper_code)

    for path in _candidate_report_paths(reports_dir, keys):
        evidence = _report_evidence(path, wanted, parent, paper_code)
        if evidence:
            return evidence
    return ""


def examiner_report_topic_evidence(
    source_pdf: str | Path,
    reports_dir: str | Path,
    question_id: str,
    config: AppConfig,
    report_paths: list[Path] | None = None,
) -> ExaminerReportEvidence | None:
    paper_code, _confidence = infer_source_paper_code(Path(source_pdf).name)
    if not paper_code:
        return None
    block_text = examiner_report_evidence(source_pdf, reports_dir, question_id, report_paths=report_paths)
    if not block_text:
        return None
    question_number = normalize_question_id(question_id)
    evidence = _extract_examiner_report_evidence(block_text, paper_code, question_number)
    topic, confidence = _map_examiner_evidence_to_topic(evidence, config)
    return ExaminerReportEvidence(
        paper_code=evidence.paper_code,
        question_number=evidence.question_number,
        subpart=evidence.subpart,
        canonical_topic=topic,
        topic_confidence=confidence,
        methods_skills=evidence.methods_skills,
        common_errors=evidence.common_errors,
        linked_question_hints=evidence.linked_question_hints,
        mathematical_cues=evidence.mathematical_cues,
    )


def _explicit_report_paths(paths: list[Path]) -> list[Path]:
    return [path for path in paths if path.suffix.lower() in {".txt", ".json", ".pdf"} and path.exists()]


def _report_evidence(path: Path, wanted: str, parent: str, paper_code: str) -> str:
    if path.suffix.lower() == ".json":
        return _json_report_evidence(path, wanted, parent, paper_code)
    return _text_report_evidence(path, wanted, parent, paper_code)


def _candidate_keys(source_pdf: Path, paper_code: str) -> list[str]:
    stem = source_pdf.stem.lower()
    keys = [stem.replace("_qp_", "_er_"), stem.replace("_qp_", "_gt_"), stem]
    if paper_code:
        keys.append(paper_code)
    return list(dict.fromkeys(key for key in keys if key))


def _candidate_report_paths(reports_dir: Path, keys: list[str]) -> list[Path]:
    candidates: list[Path] = []
    for path in sorted(reports_dir.glob("*")):
        if path.suffix.lower() not in {".txt", ".json", ".pdf"}:
            continue
        lowered = path.stem.lower()
        if any(key in lowered for key in keys):
            candidates.append(path)
    return candidates


def _session_report_paths(reports_dir: Path, session_key: str) -> list[Path]:
    if not session_key:
        return []
    candidates: list[Path] = []
    for path in sorted(reports_dir.glob("*")):
        if path.suffix.lower() not in {".txt", ".json", ".pdf"}:
            continue
        metadata = parse_filename_metadata(path)
        if metadata.document_type == "examiner_report" and metadata.session_key == session_key:
            candidates.append(path)
    return candidates


def _json_report_evidence(path: Path, wanted: str, parent: str, paper_code: str = "") -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    scoped_data = False
    if isinstance(data, dict):
        scoped = _json_paper_scope(data, paper_code)
        if scoped is None:
            return ""
        data = scoped
        scoped_data = True
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
            if paper_code and not scoped_data and not _json_item_matches_paper(item, paper_code):
                continue
            item_id = normalize_question_id(item.get("question_id") or item.get("question") or item.get("label"))
            if item_id in {wanted, parent}:
                text = item.get("text") or item.get("comment") or item.get("evidence")
                if isinstance(text, str):
                    return text.strip()
    return ""


def _json_paper_scope(data: dict[str, Any], paper_code: str) -> dict[str, Any] | list[Any] | None:
    if not paper_code:
        return None
    paper_keys = [
        paper_code,
        f"9709/{paper_code}",
        f"Paper 9709/{paper_code}",
        f"paper 9709/{paper_code}",
    ]
    for key in paper_keys:
        value = data.get(key)
        if isinstance(value, (dict, list)):
            return value
    if _json_item_matches_paper(data, paper_code):
        questions = data.get("questions") or data.get("comments") or data.get("items")
        if isinstance(questions, (dict, list)):
            return questions
    return None


def _json_item_matches_paper(item: dict[str, Any], paper_code: str) -> bool:
    candidates = [
        item.get("paper"),
        item.get("paper_code"),
        item.get("component"),
        item.get("component_code"),
        item.get("paper_component"),
    ]
    normalized = {str(candidate).strip().lower() for candidate in candidates if candidate is not None}
    wanted = {paper_code.lower(), f"9709/{paper_code}".lower(), f"paper 9709/{paper_code}".lower()}
    return bool(normalized & wanted)


def _extract_examiner_report_evidence(text: str, paper_code: str, question_number: str) -> ExaminerReportEvidence:
    sentences = _sentences(text)
    return ExaminerReportEvidence(
        paper_code=paper_code,
        question_number=question_number,
        subpart=_subpart_from_question_id(question_number),
        methods_skills=_pattern_labels(text, METHOD_PATTERNS),
        common_errors=_common_error_sentences(sentences),
        linked_question_hints=_linked_question_hints(text, sentences),
        mathematical_cues=_pattern_labels(text, MATH_CUE_PATTERNS),
    )


def _map_examiner_evidence_to_topic(evidence: ExaminerReportEvidence, config: AppConfig) -> tuple[str, str]:
    family = f"P{evidence.paper_code[0]}" if evidence.paper_code else "unknown"
    allowed_topics = config.paper_family_taxonomy.get(family, {})
    if not allowed_topics:
        return "", "low"
    classification_text = evidence.classification_text
    candidates = _score_topic_candidates_from_sources({"examiner_report": classification_text}, config, [family])
    candidates = [candidate for candidate in candidates if candidate.topic in allowed_topics]
    candidates.sort(key=lambda candidate: candidate.score, reverse=True)
    if not candidates:
        return next(iter(allowed_topics)), "low"
    top = candidates[0]
    if top.score <= 0:
        return top.topic, "low"
    second = candidates[1].score if len(candidates) > 1 else 0.0
    confidence = "high" if top.score >= 8 and top.score - second >= 3 else "medium"
    return top.topic, confidence


def _pattern_labels(text: str, patterns: dict[str, str]) -> list[str]:
    return [label for label, pattern in patterns.items() if re.search(pattern, text, re.IGNORECASE)]


def _sentences(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return []
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", compact) if sentence.strip()]


def _common_error_sentences(sentences: list[str]) -> list[str]:
    error_pattern = re.compile(r"\berror|mistake|incorrect|wrong|failed|unable|omitted|confus(?:e|ed|ion)|did not|rarely|weak\b", re.IGNORECASE)
    return [_shorten(sentence) for sentence in sentences if error_pattern.search(sentence)]


def _linked_question_hints(text: str, sentences: list[str]) -> list[str]:
    hints = _pattern_labels(text, LINKED_HINT_PATTERNS)
    for sentence in sentences:
        if re.search(r"\bhence\b|part\s*\([a-h]\)|previous answer|previous result", sentence, re.IGNORECASE):
            shortened = _shorten(sentence)
            if shortened not in hints:
                hints.append(shortened)
    return hints


def _subpart_from_question_id(question_number: str) -> str:
    match = re.search(r"\(([a-h])\)", question_number, re.IGNORECASE)
    return match.group(1).lower() if match else ""


def _shorten(value: str, limit: int = 180) -> str:
    value = value.strip()
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _text_report_evidence(path: Path, wanted: str, parent: str, paper_code: str = "") -> str:
    text = _report_text(path)
    if not text:
        return ""
    return _text_report_evidence_from_text(text, wanted, parent, paper_code)


@lru_cache(maxsize=48)
def _report_text_cached(path_value: str) -> str:
    path = Path(path_value)
    if path.suffix.lower() == ".pdf":
        return _pdf_report_text(path)
    return path.read_text(encoding="utf-8", errors="ignore")


def _report_text(path: Path) -> str:
    try:
        return _report_text_cached(str(path.resolve()))
    except Exception:
        return ""


def _pdf_report_text(path: Path) -> str:
    try:
        import fitz
    except ImportError:
        return ""
    quiet_mupdf(fitz)

    pages: list[str] = []
    with fitz.open(path) as doc:
        for page in doc:
            pages.append(page.get_text("text"))
    return "\n".join(pages)


def _text_report_evidence_from_text(text: str, wanted: str, parent: str, paper_code: str = "") -> str:
    text = _paper_section_text(text, paper_code)
    text = _comments_on_specific_questions_text(text)
    if not text:
        return ""
    sections = _split_text_sections(text)
    for key in [wanted, parent]:
        if key in sections:
            return sections[key].strip()
    return ""


def _paper_section_text(text: str, paper_code: str) -> str:
    if not paper_code:
        return ""
    import re

    marker = re.compile(r"(?im)^\s*paper\s+9709\s*/\s*([1-6][0-9])\b.*$")
    matches = list(marker.finditer(text))
    if not matches:
        return ""
    for index, match in enumerate(matches):
        if match.group(1) != paper_code:
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        return text[start:end]
    return ""


def _comments_on_specific_questions_text(text: str) -> str:
    import re

    marker = re.search(r"(?im)^\s*comments\s+on\s+specific\s+questions\s*$", text)
    if not marker:
        return ""
    return text[marker.end() :]


def _split_text_sections(text: str) -> dict[str, str]:
    import re

    marker = re.compile(r"(?im)^\s*question\s+(\d{1,2}\s*(?:\(?\s*[a-h]\s*\)?)?)\s*[:.\-–]?\s*(.*)$")
    matches = list(marker.finditer(text))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.start(2)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        key = normalize_question_id(match.group(1))
        sections[key] = text[start:end].strip()
    return sections
