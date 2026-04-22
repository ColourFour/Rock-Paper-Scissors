import ast
import importlib
import sys
from pathlib import Path

from exam_bank.cli import build_parser


CLI_PATH = Path("src/exam_bank/cli.py")
LEGACY_SURFACES = {
    "exam_bank.manual_review",
    "exam_bank.practice_page",
    "exam_bank.qa",
    "exam_bank.review",
    "exam_bank.topic_pdfs",
}


def _reset_exam_bank_modules() -> None:
    for name in list(sys.modules):
        if name == "exam_bank" or name.startswith("exam_bank."):
            sys.modules.pop(name, None)


def _modules_loaded_by_import(module_name: str) -> set[str]:
    _reset_exam_bank_modules()
    before = set(sys.modules)
    importlib.import_module(module_name)
    after = set(sys.modules)
    return {name for name in after - before if name.startswith("exam_bank")}


def _function_call_names(path: Path, function_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            call_names: set[str] = set()
            for child in ast.walk(node):
                if not isinstance(child, ast.Call):
                    continue
                target = child.func
                if isinstance(target, ast.Name):
                    call_names.add(target.id)
                elif isinstance(target, ast.Attribute):
                    call_names.add(target.attr)
            return call_names
    raise AssertionError(f"Function not found: {function_name}")


def test_pipeline_import_excludes_legacy_runtime_surfaces() -> None:
    loaded = _modules_loaded_by_import("exam_bank.pipeline")

    assert "exam_bank.pipeline" in loaded
    assert loaded.isdisjoint(LEGACY_SURFACES)


def test_cli_import_does_not_load_legacy_surfaces_until_requested() -> None:
    loaded = _modules_loaded_by_import("exam_bank.cli")

    assert "exam_bank.cli" in loaded
    assert loaded.isdisjoint(LEGACY_SURFACES)


def test_cli_exposes_single_process_front_door() -> None:
    parser = build_parser()
    action = parser._subparsers._group_actions[0]  # type: ignore[attr-defined]

    assert set(action.choices) == {"process"}

    process_calls = _function_call_names(CLI_PATH, "cmd_process")
    assert process_calls >= {"load_config", "process_inputs", "_print_result"}
    assert process_calls.isdisjoint(
        {
            "run_qa",
            "build_practice_page",
            "build_manual_review_page",
            "apply_manual_review",
            "review_items_from_records",
            "append_review_items",
            "build_topic_pdfs_from_records",
        }
    )


def test_legacy_runtime_files_are_removed_or_archived() -> None:
    assert not Path("src/exam_bank/qa.py").exists()
    assert not Path("src/exam_bank/practice_page.py").exists()
    assert not Path("src/exam_bank/manual_review.py").exists()
    assert not Path("src/exam_bank/topic_pdfs.py").exists()
    assert not Path("src/exam_bank/review.py").exists()
    assert not Path("tests/test_qa.py").exists()
    assert not Path("tests/test_practice_page.py").exists()
    assert not Path("tests/test_manual_review.py").exists()
    assert not Path("tests/test_topic_pdfs.py").exists()
    assert not Path("app").exists()
    assert not Path("practice").exists()

    assert Path("archive/topic_pdfs_legacy/src/exam_bank/topic_pdfs.py").exists()
    assert Path("archive/topic_pdfs_legacy/src/exam_bank/review.py").exists()
    assert Path("archive/topic_pdfs_legacy/tests/test_topic_pdfs.py").exists()
