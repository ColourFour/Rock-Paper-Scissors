from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .document_metadata import DocumentMetadata, parse_filename_metadata


@dataclass
class DocumentRegistryEntry:
    key: str
    syllabus_code: str = ""
    subject: str = ""
    year: str = ""
    original_session_label: str = ""
    normalized_session_key: str = ""
    component: str = ""
    question_paper: Path | None = None
    mark_scheme: Path | None = None
    examiner_reports: list[Path] = field(default_factory=list)
    metadata_by_path: dict[str, DocumentMetadata] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def missing_companions(self) -> list[str]:
        missing: list[str] = []
        if self.question_paper is None:
            missing.append("question_paper")
        if self.mark_scheme is None:
            missing.append("mark_scheme")
        return missing


@dataclass
class DocumentRegistry:
    entries: dict[str, DocumentRegistryEntry] = field(default_factory=dict)
    session_reports: dict[str, list[Path]] = field(default_factory=dict)
    unclassified: list[Path] = field(default_factory=list)

    def question_paper_entries(self) -> list[DocumentRegistryEntry]:
        return sorted(
            (entry for entry in self.entries.values() if entry.question_paper is not None),
            key=lambda entry: entry.key,
        )


def build_document_registry(
    folder: str | Path,
    allowed_document_types: set[str] | None = None,
) -> DocumentRegistry:
    return build_document_registry_from_paths([folder], allowed_document_types=allowed_document_types)


def build_document_registry_from_paths(
    paths: list[str | Path],
    allowed_document_types: set[str] | None = None,
) -> DocumentRegistry:
    registry = DocumentRegistry()
    pdfs = _scan_pdf_paths(paths)
    session_metadata: dict[str, DocumentMetadata] = {}

    for path in pdfs:
        metadata = parse_filename_metadata(path)
        if not metadata.document_type:
            registry.unclassified.append(path)
            continue
        if allowed_document_types is not None and metadata.document_type not in allowed_document_types:
            continue

        if metadata.document_type == "examiner_report" and not metadata.component:
            if metadata.session_key:
                registry.session_reports.setdefault(metadata.session_key, []).append(path)
                session_metadata.setdefault(metadata.session_key, metadata)
            else:
                registry.unclassified.append(path)
            continue

        if not metadata.canonical_key:
            registry.unclassified.append(path)
            continue

        entry = _entry_for_metadata(registry, metadata)
        _attach_document(entry, metadata, path)

    for session_key, reports in registry.session_reports.items():
        metadata = session_metadata.get(session_key)
        for entry in registry.entries.values():
            entry_session = _entry_session_key(entry)
            if entry_session != session_key:
                continue
            for report in reports:
                if report not in entry.examiner_reports:
                    entry.examiner_reports.append(report)
                    if metadata:
                        entry.metadata_by_path[str(report)] = metadata

    return registry


def _scan_pdf_paths(paths: list[str | Path]) -> list[Path]:
    pdfs: list[Path] = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_file() and path.suffix.lower() == ".pdf":
            pdfs.append(path)
        elif path.is_dir():
            pdfs.extend(sorted(item for item in path.rglob("*.pdf") if item.is_file()))
    return sorted(dict.fromkeys(pdfs), key=lambda item: str(item))


def _entry_for_metadata(registry: DocumentRegistry, metadata: DocumentMetadata) -> DocumentRegistryEntry:
    entry = registry.entries.get(metadata.canonical_key)
    if entry is None:
        entry = DocumentRegistryEntry(
            key=metadata.canonical_key,
            syllabus_code=metadata.syllabus,
            subject=metadata.subject,
            year=metadata.year,
            original_session_label=metadata.original_session_label,
            normalized_session_key=metadata.normalized_session_key or metadata.session,
            component=metadata.component,
        )
        registry.entries[metadata.canonical_key] = entry
    return entry


def _attach_document(entry: DocumentRegistryEntry, metadata: DocumentMetadata, path: Path) -> None:
    entry.metadata_by_path[str(path)] = metadata
    if metadata.document_type == "question_paper":
        if entry.question_paper and entry.question_paper != path:
            entry.warnings.append(f"duplicate_question_paper:{path.name}")
        else:
            entry.question_paper = path
    elif metadata.document_type == "mark_scheme":
        if entry.mark_scheme and entry.mark_scheme != path:
            entry.warnings.append(f"duplicate_mark_scheme:{path.name}")
        else:
            entry.mark_scheme = path
    elif metadata.document_type == "examiner_report":
        if path not in entry.examiner_reports:
            entry.examiner_reports.append(path)


def _entry_session_key(entry: DocumentRegistryEntry) -> str:
    if not (entry.syllabus_code and entry.year and entry.normalized_session_key):
        return ""
    return f"{entry.syllabus_code}_{entry.year}_{entry.normalized_session_key}"
