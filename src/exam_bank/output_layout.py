from __future__ import annotations

from pathlib import Path
import re

from .config import AppConfig
from .document_metadata import DocumentMetadata, parse_filename_metadata


_SESSION_FOLDER_LABELS = {
    "March": "spring",
    "May": "summer",
    "June": "summer",
    "MayJune": "summer",
    "November": "autumn",
    "October": "autumn",
    "OctNov": "autumn",
}


def question_image_output_path(
    question_pdf: str | Path,
    question_number: str,
    config: AppConfig,
) -> Path:
    metadata = parse_filename_metadata(question_pdf)
    paper_dir = paper_output_dir(config, metadata)
    return paper_dir / "questions" / _question_png_name(question_number)


def mark_scheme_image_output_path(
    mark_scheme_pdf: str | Path,
    question_number: str,
    config: AppConfig,
) -> Path:
    metadata = parse_filename_metadata(mark_scheme_pdf)
    paper_dir = paper_output_dir(config, metadata)
    return paper_dir / "mark_scheme" / _question_png_name(question_number)


def paper_output_dir(config: AppConfig, metadata: DocumentMetadata) -> Path:
    return config.output.root_dir() / paper_family_dir_name(metadata.paper_family) / paper_instance_id(
        metadata.component,
        metadata.normalized_session_key or metadata.session,
        metadata.year,
    )


def paper_instance_id(component: str, session: str, year: str) -> str:
    component_code = component_code_from_values(component)
    session_code = _SESSION_FOLDER_LABELS.get(session, _safe_segment(session.lower()) or "session")
    year_code = year[-2:] if len(year) >= 2 else "xx"
    return f"{component_code}{session_code}{year_code}"


def question_id(paper: str, question_number: str) -> str:
    return f"{paper}_{_question_id_suffix(question_number)}"


def paper_family_dir_name(paper_family: str) -> str:
    normalized = paper_family.strip().lower()
    if re.fullmatch(r"p[1-6]", normalized):
        return normalized
    return "unknown"


def component_code_from_values(component: str, source_paper_code: str = "") -> str:
    for value in [source_paper_code, component]:
        digits = "".join(char for char in str(value) if char.isdigit())
        if len(digits) >= 2:
            return digits[-2:]
        if len(digits) == 1:
            return digits.zfill(2)
    return "xx"


def relative_to_output_root(path: str | Path, config: AppConfig) -> str:
    path = Path(path)
    try:
        return str(path.relative_to(config.output.root_dir()))
    except ValueError:
        return str(path)


def _question_png_name(question_number: str) -> str:
    return f"{_question_id_suffix(question_number)}.png"


def _question_id_suffix(question_number: str) -> str:
    digits = "".join(char for char in question_number if char.isdigit())
    if digits:
        return f"q{int(digits):02d}"
    return f"q{_safe_segment(question_number)}"


def _safe_segment(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in value).strip("_") or "unknown"
