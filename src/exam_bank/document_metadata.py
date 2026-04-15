from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .models import PageLayout


SESSION_ALIASES = {
    "m": "March",
    "march": "March",
    "mar": "March",
    "s": "MayJune",
    "summer": "MayJune",
    "may": "MayJune",
    "june": "MayJune",
    "mayjune": "MayJune",
    "may_june": "MayJune",
    "mj": "MayJune",
    "w": "OctNov",
    "winter": "OctNov",
    "oct": "OctNov",
    "nov": "OctNov",
    "octnov": "OctNov",
    "oct_nov": "OctNov",
    "on": "OctNov",
}

DOCUMENT_TYPE_ALIASES = {
    "qp": "QP",
    "questionpaper": "QP",
    "question_paper": "QP",
    "question": "QP",
    "ms": "MS",
    "markscheme": "MS",
    "mark_scheme": "MS",
    "scheme": "MS",
    "er": "ER",
    "examinerreport": "ER",
    "examiner_report": "ER",
    "report": "ER",
}


@dataclass(frozen=True)
class DocumentMetadata:
    syllabus: str = ""
    year: str = ""
    session: str = ""
    document_type: str = ""
    component: str = ""
    source: str = ""
    warnings: tuple[str, ...] = ()

    @property
    def paper_family(self) -> str:
        return f"P{self.component[0]}" if self.component and self.component[0].isdigit() else "unknown"

    @property
    def canonical_key(self) -> str:
        if not (self.syllabus and self.year and self.session and self.component):
            return ""
        return f"{self.syllabus}_{self.year}_{self.session}_{self.component}"

    def with_document_type(self, document_type: str) -> "DocumentMetadata":
        return DocumentMetadata(
            syllabus=self.syllabus,
            year=self.year,
            session=self.session,
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

    if not year:
        year_match = re.search(r"\b(20\d{2}|\d{2})\b", stem)
        if year_match:
            year = _normalize_year(year_match.group(1))
    if not session:
        session = _session_from_text(stem)

    return DocumentMetadata(
        syllabus=syllabus,
        year=year,
        session=session,
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
        document_type = "MS"
    elif re.search(r"\bexaminer(?:'s)? report\b|\bprincipal examiner\b", cover_text, re.IGNORECASE):
        document_type = "ER"
    elif re.search(r"\bquestion paper\b", cover_text, re.IGNORECASE):
        document_type = "QP"

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
        document_type=document_type,
        component=component,
        source="internal",
    )


def reconcile_document_metadata(filename: DocumentMetadata, internal: DocumentMetadata) -> DocumentMetadata:
    warnings: list[str] = []

    def choose(field: str) -> str:
        filename_value = getattr(filename, field)
        internal_value = getattr(internal, field)
        if internal_value and filename_value and internal_value != filename_value:
            warnings.append(f"metadata_mismatch_{field}:filename={filename_value}:internal={internal_value}")
        return internal_value or filename_value

    return DocumentMetadata(
        syllabus=choose("syllabus"),
        year=choose("year"),
        session=choose("session"),
        document_type=choose("document_type"),
        component=choose("component"),
        source="internal" if any(getattr(internal, field) for field in ["syllabus", "year", "session", "document_type", "component"]) else "filename",
        warnings=tuple(warnings),
    )


def companion_candidates(document: DocumentMetadata, directory: str | Path, document_type: str) -> list[Path]:
    directory = Path(directory)
    if not directory.exists():
        return []
    candidates: list[Path] = []
    for path in sorted(directory.glob("*")):
        if not path.is_file():
            continue
        metadata = parse_filename_metadata(path)
        if metadata.canonical_key and metadata.canonical_key == document.canonical_key and metadata.document_type == document_type:
            candidates.append(path)
    return candidates


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
    for key, value in DOCUMENT_TYPE_ALIASES.items():
        if key in tokens or key in joined:
            return value
    return ""


def _component_from_tokens(tokens: list[str], document_type: str) -> str:
    if document_type:
        lowered = document_type.lower()
        for index, token in enumerate(tokens):
            if token == lowered and index + 1 < len(tokens) and re.fullmatch(r"[1-6][0-9]", tokens[index + 1]):
                return tokens[index + 1]
    for token in reversed(tokens):
        if re.fullmatch(r"[1-6][0-9]", token):
            return token
    return ""


def _session_year_from_tokens(tokens: list[str]) -> tuple[str, str]:
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
    for token, session in SESSION_ALIASES.items():
        if re.search(rf"(?:^|_){re.escape(token)}(?:_|$)", normalized):
            return session
    if re.search(r"may_?june", normalized):
        return "MayJune"
    if re.search(r"oct_?nov", normalized):
        return "OctNov"
    return ""
