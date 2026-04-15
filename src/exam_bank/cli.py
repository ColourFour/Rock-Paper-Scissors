from __future__ import annotations

import argparse
import importlib.util
import shutil
import sys
from pathlib import Path

from .config import AppConfig, load_config
from .pipeline import process_batch, process_sample
from .topic_pdfs import build_topic_pdfs_from_json, build_topic_pdfs_from_records


DEPENDENCIES = {
    "fitz": "PyMuPDF",
    "pdfplumber": "pdfplumber",
    "PIL": "Pillow",
    "pandas": "pandas",
    "pytesseract": "pytesseract",
    "reportlab": "reportlab",
    "yaml": "PyYAML",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a grouped exam question bank from PDF papers.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser("preflight", help="Check dependencies, folders, and config.")
    preflight.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    preflight.set_defaults(func=cmd_preflight)

    sample = subparsers.add_parser("sample", help="Run the pipeline on one question paper.")
    sample.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    sample.add_argument("--question-pdf", required=True, help="Path to one question paper PDF.")
    sample.add_argument("--mark-scheme", help="Optional matching mark scheme PDF.")
    sample.set_defaults(func=cmd_sample)

    process = subparsers.add_parser("process", help="Process all PDFs in input/question_papers.")
    process.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    process.add_argument("--build-topic-pdfs", action="store_true", help="Also build topic-based PDF packs after processing.")
    process.set_defaults(func=cmd_process)

    topic_pdfs = subparsers.add_parser("topic-pdfs", help="Build topic-based PDF packs from an existing question bank JSON.")
    topic_pdfs.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    topic_pdfs.add_argument("--question-bank", help="Path to a question_bank.json file. Defaults to output/json/question_bank.json.")
    topic_pdfs.set_defaults(func=cmd_topic_pdfs)

    args = parser.parse_args(argv)
    return args.func(args)


def cmd_preflight(args: argparse.Namespace) -> int:
    checks: list[tuple[str, bool, str]] = []

    config: AppConfig = AppConfig()
    config_loaded = True
    try:
        config = load_config(args.config)
    except Exception as exc:
        config_loaded = False
        checks.append(("config", False, str(exc)))
    else:
        checks.append(("config", True, f"Loaded {args.config}"))

    for module_name, package_name in DEPENDENCIES.items():
        checks.append((package_name, importlib.util.find_spec(module_name) is not None, f"Python module `{module_name}`"))

    openai_required = config.classification.enable_openai if config_loaded else False
    checks.append(("openai", (not openai_required) or importlib.util.find_spec("openai") is not None, "Required only when classification.enable_openai is true"))

    tesseract = shutil.which("tesseract")
    checks.append(("tesseract", bool(tesseract), tesseract or "Install Tesseract for OCR fallback"))

    for name, directory in [
        ("question_papers_dir", config.input.question_papers_dir),
        ("mark_schemes_dir", config.input.mark_schemes_dir),
        ("mappings_dir", config.input.mappings_dir),
    ]:
        checks.append((name, directory.exists(), str(directory)))

    for name, ok, detail in checks:
        status = "OK" if ok else "MISSING"
        print(f"[{status}] {name}: {detail}")

    if config.input.question_papers_dir.exists():
        pdf_count = len(list(config.input.question_papers_dir.glob("*.pdf")))
        print(f"[INFO] question PDFs found: {pdf_count}")

    return 0 if all(ok for _, ok, _ in checks) else 1


def cmd_sample(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    result = process_sample(args.question_pdf, config, mark_scheme_pdf=args.mark_scheme)
    _print_result(result.records, result.json_path, result.csv_path, result.review_path)
    return 0


def cmd_process(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    result = process_batch(config)
    _print_result(result.records, result.json_path, result.csv_path, result.review_path)
    if args.build_topic_pdfs or config.topic_pdfs.enable_topic_pdfs:
        topic_result = build_topic_pdfs_from_records(result.records, config)
        _print_topic_pdf_result(topic_result.pdf_paths, topic_result.skipped_count, topic_result.review_path)
    return 0


def cmd_topic_pdfs(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    question_bank = Path(args.question_bank) if args.question_bank else config.output.json_dir / config.naming.json_name
    if not question_bank.exists():
        print(
            f"Question bank JSON not found: {question_bank}\n"
            "Run `python -m exam_bank.cli process --config config.yaml` first, "
            "or pass `--question-bank PATH` to an existing JSON export.",
            file=sys.stderr,
        )
        return 1
    topic_result = build_topic_pdfs_from_json(question_bank, config)
    _print_topic_pdf_result(topic_result.pdf_paths, topic_result.skipped_count, topic_result.review_path)
    return 0


def _print_result(records: list[object], json_path: Path, csv_path: Path, review_path: Path) -> None:
    print(f"Processed records: {len(records)}")
    print(f"JSON: {json_path}")
    print(f"CSV: {csv_path}")
    print(f"Review: {review_path}")


def _print_topic_pdf_result(pdf_paths: list[Path], skipped_count: int, review_path: Path | None) -> None:
    print(f"Topic PDFs: {len(pdf_paths)}")
    for path in pdf_paths:
        print(f"  {path}")
    if skipped_count:
        print(f"Topic PDF skipped records: {skipped_count}")
    if review_path:
        print(f"Topic PDF review items: {review_path}")


if __name__ == "__main__":
    sys.exit(main())
