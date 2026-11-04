"""Labels, cards and the rubric reach only the code allowed to read them. Checked on the source, because a leak would otherwise look like skill."""
import ast
from pathlib import Path

import pytest

from permitengine.evaluation import labels as labels_module
from permitengine.workspace import EngineError, Workspace

SRC = Path(__file__).parents[1] / "src" / "permitengine"
FILES = sorted(SRC.rglob("*.py"))
SPOT = {"labels.jsonl": {"evaluation/labels.py"}, "cards.jsonl": {"evaluation/labels.py"}, "expert_rubric": {"officer/real.py"},
        "truth_table": set(), "generator/config": set()}
# Who may import the module that opens labels and cards.
LABEL_READERS = {"evaluation/demo.py", "evaluation/report.py", "evaluation/removal.py", "evaluation/routing_check.py", "evaluation/final.py", "evaluation/simulated_answers.py", "evaluation/read_report.py", "evaluation/lint_rules.py"}
NEVER_EVALUATION = ("pipeline/", "reading/", "policy/", "risk/", "trees/", "store/", "models/", "learning/", "replay/")


def rel(path: Path) -> str:
    return str(path.relative_to(SRC))


def imported_modules(path: Path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            yield ("." * node.level) + (node.module or "")
            for alias in node.names:
                yield ("." * node.level) + (node.module or "") + "." + alias.name


@pytest.mark.parametrize("word,allowed", SPOT.items())
def test_only_the_allowed_files_name_the_hidden_files(word, allowed):
    found = {rel(p) for p in FILES if word in p.read_text(encoding="utf-8")}
    assert found <= allowed, f"{word} is named in {sorted(found - allowed)}"


def test_only_allowed_modules_import_the_labels_module():
    for path in FILES:
        if rel(path) == "evaluation/labels.py":
            continue
        names = list(imported_modules(path))
        if any(name.endswith(".labels") or name.endswith("labels.load_labels") or name.endswith("evaluation.labels") for name in names):
            assert rel(path) in LABEL_READERS, f"{rel(path)} imports the labels module"


def test_pipeline_and_readers_never_import_evaluation_or_the_officer():
    for path in FILES:
        if rel(path).startswith(NEVER_EVALUATION):
            for name in imported_modules(path):
                assert "evaluation" not in name, f"{rel(path)} imports {name}"
                assert "officer" not in name, f"{rel(path)} imports {name}"


def test_learning_opens_no_files():
    for name in ("train.py", "thresholds.py", "corrections.py"):
        source = (SRC / "learning" / name).read_text(encoding="utf-8")
        assert "open(" not in source and "read_text" not in source


def test_only_the_final_report_calls_the_door_to_test_labels():
    callers = {rel(p) for p in FILES if "load_test_labels" in p.read_text(encoding="utf-8")}
    assert callers == {"evaluation/labels.py", "evaluation/final.py"}


def test_test_labels_are_refused_through_the_ordinary_door(tmp_path):
    ws = Workspace(tmp_path)
    with pytest.raises(EngineError):
        labels_module.load_labels(ws, ("train", "test"))
    with pytest.raises(EngineError):
        labels_module.load_labels(ws, ("tone",))
