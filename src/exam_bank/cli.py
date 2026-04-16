from __future__ import annotations

import argparse
import importlib.util
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from .config import AppConfig, load_config
from .manual_review import apply_manual_review, build_manual_review_page
from .pipeline import process_batch, process_folder, process_sample
from .practice_page import build_practice_page
from .qa import run_qa
from .topic_pdfs import TopicPDFResult, build_topic_pdfs_from_json, build_topic_pdfs_from_records


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
    parser = argparse.ArgumentParser(
        description="Build a grouped exam question bank from PDF papers.",
        epilog=(
            "Open generated HTML/CSV files with `open path/to/file` on macOS, "
            "or use `open-qa` / `open-review`. Do not type output paths directly "
            "as shell commands. If you serve files manually and port 8000 is busy, "
            "use another port such as `python3 -m http.server 8001`."
        ),
    )
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

    process_folder_parser = subparsers.add_parser("process-folder", help="Process a folder of QP/MS/ER PDFs using filename-first routing.")
    process_folder_parser.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    process_folder_parser.add_argument("--input-folder", required=True, help="Folder containing question papers, mark schemes, and examiner reports.")
    process_folder_parser.add_argument("--build-topic-pdfs", action="store_true", help="Also build topic-based PDF packs after processing.")
    process_folder_parser.set_defaults(func=cmd_process_folder)

    topic_pdfs = subparsers.add_parser("topic-pdfs", help="Build topic-based PDF packs from an existing question bank JSON.")
    topic_pdfs.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    topic_pdfs.add_argument("--question-bank", help="Path to a question_bank.json file. Defaults to output/json/question_bank.json.")
    topic_pdfs.set_defaults(func=cmd_topic_pdfs)

    qa = subparsers.add_parser("qa", help="Run deterministic QA checks against an existing question bank JSON.")
    qa.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    qa.add_argument("--question-bank", help="Path to a question_bank.json file. Defaults to output/json/question_bank.json.")
    qa.add_argument("--only-failed", action="store_true", help="Write only failing records to the QA reports.")
    qa.set_defaults(func=cmd_qa)

    practice_page = subparsers.add_parser("practice-page", help="Generate a fully static student practice page.")
    practice_page.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    practice_page.add_argument("--question-bank", help="Path to a question_bank.json file. Defaults to output/json/question_bank.json.")
    practice_page.add_argument("--output-dir", help="Output directory. Defaults to output/practice.")
    practice_page.add_argument("--publish-dir", help="GitHub Pages export directory. Defaults to practice_page.publish_dir.")
    practice_page.add_argument("--no-publish", action="store_true", help="Only write the local output/practice page; skip the GitHub Pages export.")
    practice_page.set_defaults(func=cmd_practice_page)

    manual_review_page = subparsers.add_parser("manual-review-page", help="Generate a local browser page for manual topic/difficulty curation.")
    manual_review_page.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    manual_review_page.add_argument("--question-bank", help="Path to a question_bank.json file. Defaults to output/json/question_bank.json.")
    manual_review_page.add_argument("--output-dir", help="Output directory. Defaults to manual_review.output_dir.")
    manual_review_page.set_defaults(func=cmd_manual_review_page)

    apply_review = subparsers.add_parser("apply-manual-review", help="Merge exported manual review JSON into a question bank.")
    apply_review.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    apply_review.add_argument("--question-bank", help="Path to input question_bank.json. Defaults to output/json/question_bank.json.")
    apply_review.add_argument("--review-json", required=True, help="Manual review export JSON from the local review page.")
    apply_review.add_argument("--output-json", help="Merged question bank path. Defaults to output/json/question_bank_reviewed.json.")
    apply_review.set_defaults(func=cmd_apply_manual_review)

    open_qa = subparsers.add_parser("open-qa", help="Open output/qa/review.html. No local server is needed for the generated QA page.")
    open_qa.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    open_qa.set_defaults(func=cmd_open_qa)

    open_review = subparsers.add_parser("open-review", help="Open the main review output CSV.")
    open_review.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    open_review.set_defaults(func=cmd_open_review)

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
        ("examiner_reports_dir", config.input.examiner_reports_dir),
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
        _print_topic_pdf_result(topic_result)
    return 0


def cmd_process_folder(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    result = process_folder(args.input_folder, config)
    _print_result(result.records, result.json_path, result.csv_path, result.review_path)
    if args.build_topic_pdfs or config.topic_pdfs.enable_topic_pdfs:
        topic_result = build_topic_pdfs_from_records(result.records, config)
        _print_topic_pdf_result(topic_result)
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
    _print_topic_pdf_result(topic_result)
    return 0


def cmd_qa(args: argparse.Namespace) -> int:
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
    output_dir = config.output.json_dir.parent / "qa"
    result = run_qa(question_bank, output_dir, only_failed=args.only_failed)
    _print_qa_result(result.summary, result.json_path, result.csv_path, result.review_path)
    return 0


def cmd_practice_page(args: argparse.Namespace) -> int:
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
    output_dir = Path(args.output_dir) if args.output_dir else config.output.json_dir.parent / "practice"
    result = build_practice_page(question_bank, output_dir, config.practice_page)
    print(f"Practice records: {result.usable_records}")
    if result.skipped_records:
        print(f"Practice skipped records: {result.skipped_records}")
    print(f"Practice page: {result.html_path}")
    bug_report = config.practice_page.bug_report
    if bug_report.enabled:
        print(f"Bug report form: {'configured' if bug_report.form_url else 'not configured'}")
        print(f"Copy bug report button: {'enabled' if bug_report.enable_copy_button else 'disabled'}")
    print(f"Open it directly with `open {result.html_path}`; no local server is needed.")

    if config.practice_page.publish_enabled and not args.no_publish:
        publish_dir = Path(args.publish_dir) if args.publish_dir else config.practice_page.publish_dir
        publish_result = build_practice_page(
            question_bank,
            publish_dir,
            config.practice_page,
            copy_assets=config.practice_page.publish_assets,
            asset_dir_name=config.practice_page.publish_asset_dir,
        )
        print(f"Published practice page: {publish_result.html_path}")
        if config.practice_page.publish_assets:
            print(f"Published practice assets copied: {publish_result.copied_assets}")
            if publish_result.missing_assets:
                print(f"Published practice assets missing at generation time: {publish_result.missing_assets}")
        share_url = _practice_share_url(config.practice_page.github_pages_url, publish_result.html_path)
        if share_url:
            print(f"Shareable GitHub Pages URL after push/deploy: {share_url}")
        else:
            print("Shareable GitHub Pages URL: set practice_page.github_pages_url in config.yaml to print this exactly.")
    return 0


def cmd_manual_review_page(args: argparse.Namespace) -> int:
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
    output_dir = Path(args.output_dir) if args.output_dir else config.manual_review.output_dir
    result = build_manual_review_page(question_bank, output_dir, config)
    print(f"Manual review records: {result.record_count}")
    print(f"Manual review page: {result.html_path}")
    print("Start a local server from the repo root:")
    print("  python3 -m http.server 8001")
    print(f"Then open: {_local_server_url(result.html_path, port=8001)}")
    print("Edits are saved in browser localStorage. Use Export review JSON when you are done.")
    return 0


def cmd_apply_manual_review(args: argparse.Namespace) -> int:
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
    review_json = Path(args.review_json)
    if not review_json.exists():
        print(f"Manual review JSON not found: {review_json}", file=sys.stderr)
        return 1
    output_json = Path(args.output_json) if args.output_json else config.output.json_dir / "question_bank_reviewed.json"
    result = apply_manual_review(question_bank, review_json, output_json)
    print(f"Manual review input records: {result.input_record_count}")
    print(f"Manual reviews applied: {result.matched_reviews}")
    if result.unmatched_reviews:
        print(f"Manual reviews not matched to current question bank: {result.unmatched_reviews}")
    print(f"Reviewed question bank: {result.output_json_path}")
    print("Use this reviewed JSON for student outputs, for example:")
    print(f"  python -m exam_bank.cli practice-page --config {args.config} --question-bank {result.output_json_path}")
    print(f"  python -m exam_bank.cli topic-pdfs --config {args.config} --question-bank {result.output_json_path}")
    return 0


def cmd_open_qa(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    return _open_path(config.output.json_dir.parent / "qa" / "review.html", "QA review")


def cmd_open_review(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    return _open_path(config.output.review_dir / config.naming.review_name, "main review")


def _print_result(records: list[object], json_path: Path, csv_path: Path, review_path: Path) -> None:
    print(f"Processed records: {len(records)}")
    print(f"JSON: {json_path}")
    print(f"CSV: {csv_path}")
    print(f"Review: {review_path}")


def _print_topic_pdf_result(result: TopicPDFResult) -> None:
    pdf_paths = result.pdf_paths
    print(f"Topic PDFs: {len(pdf_paths)}")
    for path in pdf_paths:
        print(f"  {path}")
    print(f"Topic PDF embedded mark schemes: {result.mark_scheme_link_count}")
    missing_links = result.missing_mark_scheme_link_count
    if missing_links:
        print(f"Topic PDF records with unavailable mark scheme image: {missing_links}")
    skipped_count = result.skipped_count
    if skipped_count:
        print(f"Topic PDF skipped records: {skipped_count}")
    review_path = result.review_path
    if review_path:
        print(f"Topic PDF review items: {review_path}")


def _print_qa_result(summary: dict[str, object], json_path: Path, csv_path: Path, review_path: Path) -> None:
    status_counts = summary.get("status_counts", {})
    if not isinstance(status_counts, dict):
        status_counts = {}
    print(f"QA validated records: {summary.get('validated_record_count', 0)}")
    print(f"QA skipped P2/P6 records: {summary.get('skipped_record_count', 0)}")
    print(
        "QA status counts: "
        f"pass={status_counts.get('pass', 0)}, "
        f"warning={status_counts.get('warning', 0)}, "
        f"fail={status_counts.get('fail', 0)}"
    )
    print(f"QA JSON: {json_path}")
    print(f"QA CSV: {csv_path}")
    print(f"QA review: {review_path}")
    top_warning = summary.get("top_warning_reason")
    top_fail = summary.get("top_fail_reason")
    if isinstance(top_warning, dict) and top_warning:
        print(f"Top QA warning: {top_warning.get('flag')} ({top_warning.get('count')})")
    if isinstance(top_fail, dict) and top_fail:
        print(f"Top QA fail: {top_fail.get('flag')} ({top_fail.get('count')})")
    print(f"Open QA review: python -m exam_bank.cli open-qa --config config.yaml")


def _open_path(path: Path, label: str) -> int:
    if not path.exists():
        print(
            f"{label.capitalize()} file not found: {path}\n"
            "Run the matching generation command first.",
            file=sys.stderr,
        )
        return 1
    if platform.system() == "Darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        import webbrowser

        webbrowser.open(path.resolve().as_uri())
    print(f"Opened {label}: {path}")
    return 0


def _practice_share_url(configured_base_url: str, html_path: Path) -> str:
    base_url = configured_base_url.strip() or _infer_github_pages_base_url()
    if not base_url:
        return ""
    base_url = base_url.rstrip("/") + "/"
    relative = _index_url_path(html_path)
    return base_url + relative


def _index_url_path(html_path: Path) -> str:
    try:
        relative = html_path.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        relative = html_path
    if relative.name == "index.html":
        relative = relative.parent
    path = relative.as_posix().strip("/")
    return f"{path}/" if path else ""


def _local_server_url(path: Path, *, port: int) -> str:
    try:
        relative = path.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        relative = path
    return f"http://localhost:{port}/{relative.as_posix()}"


def _infer_github_pages_base_url() -> str:
    try:
        completed = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return ""
    remote = completed.stdout.strip()
    if not remote:
        return ""
    owner = repo = ""
    if remote.startswith("git@github.com:"):
        owner_repo = remote.removeprefix("git@github.com:").removesuffix(".git")
        parts = owner_repo.split("/", 1)
        if len(parts) == 2:
            owner, repo = parts
    elif "github.com/" in remote:
        owner_repo = remote.split("github.com/", 1)[1].removesuffix(".git")
        parts = owner_repo.split("/", 1)
        if len(parts) == 2:
            owner, repo = parts
    if not owner or not repo:
        return ""
    owner_host = owner.lower()
    if repo.lower() == f"{owner_host}.github.io":
        return f"https://{owner_host}.github.io/"
    return f"https://{owner_host}.github.io/{repo}/"


if __name__ == "__main__":
    sys.exit(main())
