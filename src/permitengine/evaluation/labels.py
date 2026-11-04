"""The one place that opens labels and cards. Pipeline and reading code never import this. Test labels have their own door."""
import json

from ..workspace import EngineError, Workspace


def _read_jsonl(path) -> dict:
    if not path.exists():
        raise EngineError(f"{path} does not exist; the data must be generated first")
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["case_id"]] = row
    return rows


def load_labels(ws: Workspace, splits=("train", "validation")) -> dict:
    """Labels for the named splits. The test split is refused here: only final.py reads it, through load_test_labels."""
    if "test" in splits or "tone" in splits:
        raise EngineError("test labels are sealed; only final-report reads them")
    allowed = {case_id for split in splits for case_id in ws.splits()[split]}
    return {k: v for k, v in _read_jsonl(ws.data / "labels.jsonl").items() if k in allowed}


def load_test_labels(ws: Workspace) -> dict:
    allowed = set(ws.splits()["test"])
    return {k: v for k, v in _read_jsonl(ws.data / "labels.jsonl").items() if k in allowed}


def load_cards(ws: Workspace) -> dict:
    return _read_jsonl(ws.data / "cards.jsonl")
