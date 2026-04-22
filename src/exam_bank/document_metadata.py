from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .models import PageLayout
from .runtime_profile import COMPACT_DOCUMENT_TYPES, DOCUMENT_TYPE_ALIASES, SESSION_ALIASES


@dataclass(frozen=True)
class DocumentMetadata:
    syllabus: str = ""
    subject: str = ""
    year: str = ""
    session: str = ""
    original_session_label: str = ""
    normalized_session_key: str = ""
    document_type: str = ""
    component: str = ""
    source: str = ""
    warnings: tuple[str, ...] = ()

    @property
    def paper_family(self) -> str:
        return f"P{self.component[0]}" if self.component and self.component[0].isdigit() else "unknown"

    @property
    def canonical_key(self) -> str:
        session = self.normalized_session_key or self.session
        if not (self.year and session and self.component):
            return ""
        syllabus = self.syllabus or "unknown"
        return f"{syllabus}_{self.year}_{session}_{self.component}"

    @property
    def session_key(self) -> str:
        session = self.normalized_session_key or self.session
        if not (self.year and session):
            return ""
        syllabus = self.syllabus or "unknown"
        return f"{syllabus}_{self.year}_{session}"

    @property
    def compact_document_type(self) -> str:
        return COMPACT_DOCUMENT_TYPES.get(self.document_type, self.document_type)

    def with_document_type(self, document_type: str) -> "DocumentMetadata":
        return DocumentMetadata(
            syllabus=self.syllabus,
            subject=self.subject,
            year=self.year,
            session=self.session,
            original_session_label=self.original_session_label,
            normalized_session_key=self.normalized_session_key,
            document_type=document_type,
            component=self.component,
            source=self.source,
            warnings=self.warnings,
        )


def parse_filename_metadata(path: str | Path) -> DocumentMetadata:
    name = Path(path).name
    stem = Path(path).stem
    normalized = _normalize_name(stem)
    tokens = [token for token in normalized.split("_") if token]

    syllabus = _first_match(tokens, r"^\d{4}$")
    document_type = _document_type_from_tokens(tokens)
    component = _component_from_tokens(tokens, document_type)
    session, year = _session_year_from_tokens(tokens)
    subject = _subject_from_tokens(tokens)

    if not year:
        year_match = re.search(r"\b(20\d{2}|\d{2})\b", stem)
        if year_match:
            year = _normalize_year(year_match.group(1))
    if not session:
        session = _session_from_text(stem)
    if syllabus and syllabus == year:
        syllabus = ""

    return DocumentMetadata(
        syllabus=syllabus,
        subject=subject,
        year=year,
        session=session,
        original_session_label=session,
        normalized_session_key=session,
        document_type=document_type,
        component=component,
        source="filename",
    )


def parse_internal_document_metadata(layouts: list[PageLayout]) -> DocumentMetadata:
    cover_text = "\n".join(layout.text for layout in layouts[:2])
    normalized = _normalize_name(cover_text)

    syllabus = ""
    syllabus_match = re.search(r"\b(9709)\b", cover_text)
    if syllabus_match:
        syllabus = syllabus_match.group(1)

    component = ""
    component_patterns = [
        r"\bpaper\s*(?P<component>[1-6][0-9])\b",
        r"\b9709\s*/\s*(?P<component>[1-6][0-9])\b",
        r"\bcomponent\s*(?P<component>[1-6][0-9])\b",
    ]
    for pattern in component_patterns:
        match = re.search(pattern, cover_text, re.IGNORECASE)
        if match:
            component = match.group("component")
            break

    document_type = ""
    if re.search(r"\bmark scheme\b", cover_text, re.IGNORECASE):
        document_type = "mark_scheme"
    elif re.search(r"\bexaminer(?:'s)? report\b|\bprincipal examiner\b", cover_text, re.IGNORECASE):
        document_type = "examiner_report"
    elif re.search(r"\bquestion paper\b", cover_text, re.IGNORECASE):
        document_type = "question_paper"

    session = _session_from_text(cover_text)
    year = ""
    year_match = re.search(r"\b(20\d{2})\b", cover_text)
    if year_match:
        year = year_match.group(1)
    else:
        compact_match = re.search(r"\b(?:m|s|w)(\d{2})\b", normalized)
        if compact_match:
            year = _normalize_year(compact_match.group(1))

    return DocumentMetadata(
        syllabus=syllabus,
        year=year,
        session=session,
        original_session_label=session,
        normalized_session_key=session,
        document_type=document_type,
        component=component,
        source="internal",
    )


def reconcile_document_metadata(filename: DocumentMetadata, internal: DocumentMetadata) -> DocumentMetadata:
    warnings: list[str] = []

    def choose(field: str) -> str:
        filename_value = getattr(filename, field)
        internal_value = getattr(internal, field)
        if (
            internal_value
            and filename_value
            and internal_value != filename_value
            and not _metadata_values_equivalent(field, filename_value, internal_value)
        ):
            warnings.append(f"metadata_mismatch_{field}:filename={filename_value}:internal={internal_value}")
        return internal_value or filename_value

    return DocumentMetadata(
        syllabus=choose("syllabus"),
        subject=filename.subject or internal.subject,
        year=choose("year"),
        session=choose("session"),
        original_session_label=choose("original_session_label"),
        normalized_session_key=choose("normalized_session_key"),
        document_type=choose("document_type"),
        component=choose("component"),
        source="internal" if any(getattr(internal, field) for field in ["syllabus", "year", "session", "document_type", "component"]) else "filename",
        warnings=tuple(warnings),
    )


def _metadata_values_equivalent(field: str, filename_value: str, internal_value: str) -> bool:
    if field not in {"session", "original_session_label", "normalized_session_key"}:
        return False
    return _session_compare_key(filename_value) == _session_compare_key(internal_value)


def _session_compare_key(value: str) -> str:
    if value in {"October", "November", "OctNov"}:
        return "OctNov"
    if value in {"May", "June", "MayJune"}:
        return "MayJune"
    return value


def companion_candidates(document: DocumentMetadata, directory: str | Path, document_type: str) -> list[Path]:
    directory = Path(directory)
    if not directory.exists():
        return []
    candidates: list[Path] = []
    for path in sorted(directory.glob("*")):
        if not path.is_file():
            continue
        metadata = parse_filename_metadata(path)
        if metadata.canonical_key and metadata.canonical_key == document.canonical_key and _document_type_matches(metadata.document_type, document_type):
            candidates.append(path)
    return candidates


def _document_type_matches(actual: str, expected: str) -> bool:
    return actual == expected or COMPACT_DOCUMENT_TYPES.get(actual) == expected or COMPACT_DOCUMENT_TYPES.get(expected) == actual


def _normalize_name(value: str) -> str:
    normalized = value.lower()
    normalized = normalized.replace("&", "and")
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    return normalized.strip("_")


def _first_match(tokens: list[str], pattern: str) -> str:
    for token in tokens:
        if re.fullmatch(pattern, token):
            return token
    return ""


def _document_type_from_tokens(tokens: list[str]) -> str:
    joined = "_".join(tokens)
    phrase_checks = [
        ("question_paper", "question_paper"),
        ("exam_paper", "question_paper"),
        ("mark_scheme", "mark_scheme"),
        ("examiner_report", "examiner_report"),
    ]
    for phrase, value in phrase_checks:
        if phrase in joined:
            return value
    for key, value in DOCUMENT_TYPE_ALIASES.items():
        if key in tokens or (len(key) > 2 and key in joined):
            return value
    return ""


def _component_from_tokens(tokens: list[str], document_type: str) -> str:
    if document_type == "examiner_report":
        return ""
    if tokens and re.fullmatch(r"[1-6][0-9]", tokens[-1]):
        return tokens[-1]
    for token in reversed(tokens):
        if re.fullmatch(r"[1-6][0-9]", token):
            return token
        paper_family = re.fullmatch(r"p([1-6])", token)
        if paper_family:
            return paper_family.group(1)
    return ""


def _session_year_from_tokens(tokens: list[str]) -> tuple[str, str]:
    joined = "_".join(tokens)
    phrase_session = _session_from_text(joined)
    if phrase_session:
        year = ""
        for token in tokens:
            if re.fullmatch(r"20\d{2}|\d{2}", token):
                year = _normalize_year(token)
                break
        return phrase_session, year

    for token in tokens:
        compact = re.fullmatch(r"([msw])(\d{2})", token)
        if compact:
            return SESSION_ALIASES[compact.group(1)], _normalize_year(compact.group(2))
    session = ""
    year = ""
    for token in tokens:
        if not session:
            session = SESSION_ALIASES.get(token, "")
        if not year and re.fullmatch(r"20\d{2}|\d{2}", token):
            year = _normalize_year(token)
    return session, year


def _normalize_year(value: str) -> str:
    if len(value) == 4:
        return value
    year = int(value)
    return str(2000 + year if year < 80 else 1900 + year)


def _session_from_text(value: str) -> str:
    normalized = _normalize_name(value)
    if re.search(r"february_?march|feb_?march", normalized):
        return "March"
    if re.search(r"may_?june", normalized):
        return "MayJune"
    if re.search(r"october_?november|oct_?nov", normalized):
        return "OctNov"
    for token, session in SESSION_ALIASES.items():
        if re.search(rf"(?:^|_){re.escape(token)}(?:_|$)", normalized):
            return session
    return ""


def _subject_from_tokens(tokens: list[str]) -> str:
    if "mathematics" in tokens:
        return "Mathematics"
    if "maths" in tokens:
        return "Mathematics"
    return ""
