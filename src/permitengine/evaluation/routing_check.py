"""Soft against hard routing on validation, and Jev's calibration against the cards on train. No model calls."""
import copy
import json
from pathlib import Path

from ..pipeline.case import load_context
from ..trees.loader import load_model
from ..workspace import Workspace
from .common import answers_folder, choose_thresholds, mean_tree_loss, prepare_split, route_counts
from .labels import load_cards, load_labels

BINS = 5


def _hard(p):
    other = copy.copy(p)
    other.answers = {k: 1.0 if v >= 0.5 else 0.0 for k, v in p.answers.items()}
    return other


def _calibration(prepared: dict, cards: dict, question: str) -> dict:
    pairs = [(p.answers[question], bool(cards[case_id]["facts"][question])) for case_id, p in prepared.items()
             if question in p.answers and question in cards[case_id]["facts"]]
    if not pairs:
        return {"cases": 0, "error": None}
    bins = {}
    for value, truth in pairs:
        bins.setdefault(min(int(value * BINS), BINS - 1), []).append((value, truth))
    error = sum(abs(sum(v for v, _ in row) / len(row) - sum(t for _, t in row) / len(row)) * len(row) for row in bins.values()) / len(pairs)
    return {"cases": len(pairs), "error": error, "above_limit": error > 0.10}


def routing_check(ws: Workspace, answers: str = "simulated", model_name: str | None = None, first_guess_dir: Path | None = None) -> dict:
    ctx = load_context(ws, first_guess_dir)
    splits = ws.splits()
    folder = answers_folder(ws, ctx, answers, model_name)
    labels = load_labels(ws, ("validation",))
    validation = list(prepare_split(ws, ctx, splits["validation"], folder).values())
    train = prepare_split(ws, ctx, splits["train"], folder)
    model = load_model(ws.weights / "candidates" / "trained")
    thresholds = model.thresholds or choose_thresholds(model, validation, labels, ctx)
    hard = [_hard(p) for p in validation]
    arms = {}
    for name, cases in (("soft", validation), ("hard", hard)):
        counts = route_counts(model, cases, thresholds, labels, ctx)
        arms[name] = {"loss": mean_tree_loss(model, cases, labels), "approved": counts["approved_share"], "precision": counts["precision"],
                      "decided_without_officer": counts["decided_without_officer"]}
    cards = load_cards(ws)
    questions = sorted({q["id"] for tree in ctx.trees.values() for q in tree.questions if q["kind"] == "jev"})
    report = {"answers": answers, "synthetic": True, "validation": arms, "calibration_on_train": {q: _calibration(train, cards, q) for q in questions}}
    ws.reports.mkdir(parents=True, exist_ok=True)
    (ws.reports / "routing_check.json").write_text(json.dumps(report, indent=1, sort_keys=True), encoding="utf-8")
    return report
