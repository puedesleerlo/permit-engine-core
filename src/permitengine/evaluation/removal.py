"""What Jev adds: replace each Jev question with its mean over validation cases and count the decisions that flip."""
import copy
import json
import statistics
from pathlib import Path

from ..pipeline.case import decide_many, load_context
from ..trees.loader import load_model
from ..workspace import Workspace
from .common import answers_folder, choose_thresholds, prepare_split
from .labels import load_labels


def removal(ws: Workspace, answers: str = "simulated", model_name: str | None = None, first_guess_dir: Path | None = None) -> dict:
    ctx = load_context(ws, first_guess_dir)
    splits = ws.splits()
    labels = load_labels(ws, ("validation",))
    prepared = list(prepare_split(ws, ctx, splits["validation"], answers_folder(ws, ctx, answers, model_name)).values())
    model = load_model(ws.weights / "candidates" / "trained")
    thresholds = model.thresholds or choose_thresholds(model, prepared, labels, ctx)
    going = [p for p in prepared if not p.stopped]
    base = [r["decision"]["route"] for r in decide_many(going, model, thresholds, ctx)]
    questions = sorted({q["id"] for tree in ctx.trees.values() for q in tree.questions if q["kind"] == "jev"})
    rows = {}
    for question in questions:
        values = [p.answers[question] for p in going if question in p.answers]
        mean = statistics.mean(values) if values else 0.5
        changed = []
        for p in going:
            other = copy.copy(p)
            other.answers = dict(p.answers)
            if question in other.answers:
                other.answers[question] = mean
            changed.append(other)
        routes = [r["decision"]["route"] for r in decide_many(changed, model, thresholds, ctx)]
        rows[question] = {"mean": mean, "flips": sum(a != b for a, b in zip(base, routes)), "cases": len(going)}
    report = {"split": "validation", "answers": answers, "synthetic": True, "questions": rows,
              "note": "Near zero flips would be a valid finding: it would mean Jev adds little on these cases."}
    ws.reports.mkdir(parents=True, exist_ok=True)
    (ws.reports / "removal.json").write_text(json.dumps(report, indent=1, sort_keys=True), encoding="utf-8")
    return report
