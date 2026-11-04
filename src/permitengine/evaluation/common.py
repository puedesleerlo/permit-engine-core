"""Shared by the story and the reports: stored answers for a split, per-tree rows, loss and route counts."""
import math
import statistics
from pathlib import Path

from ..learning.thresholds import choose
from ..models.llm import choose_model
from ..pipeline.case import Context, Prepared, decide_many, prepare_many
from ..risk.score import score
from ..store.records import load_records, records_dir
from ..trees.evaluate import distribution, reach
from ..trees.evaluate import loss as tree_loss
from ..workspace import Workspace

AUTOMATIC = ("approved", "returned")


def answers_folder(ws: Workspace, ctx: Context, answers: str, model: str | None) -> Path:
    return records_dir(ws, answers, choose_model(ctx.settings, model) if answers == "real" else None)


def prepare_split(ws: Workspace, ctx: Context, case_ids: list, folder: Path) -> dict:
    records = load_records(folder, case_ids)
    prepared = prepare_many([(ws.application(c), records[c]) for c in case_ids], ctx)
    return {p.case_id: p for p in prepared}


def base_id(case_id: str) -> str:
    return case_id.split("-")[0]


def rows_by_tree(prepared: dict, labels: dict, trees: dict) -> dict:
    """For training: (answers, level) per tree, for cases where the tree applies and a label exists."""
    rows = {t: [] for t in trees}
    for case_id, p in prepared.items():
        if p.stopped or p.policy_failure:
            continue
        for tree_id, tree in trees.items():
            level = labels[case_id]["levels"].get(tree_id)
            if level is not None and p.applies.get(tree.hazard):
                rows[tree_id].append((p.answers, level))
    return rows


def case_loss(model, p: Prepared, label: dict) -> float | None:
    """Mean loss over the trees that apply to this case, or None if none do."""
    values = []
    for tree_id, tree in model.trees.items():
        level = label["levels"].get(tree_id)
        if level is not None and p.applies.get(tree.hazard):
            values.append(tree_loss(tree, model.levels[tree_id], p.answers, level))
    return statistics.mean(values) if values else None


def per_tree_loss(model, prepared: list, labels: dict) -> dict:
    out = {}
    for tree_id, tree in model.trees.items():
        values = []
        for p in prepared:
            if p.stopped or p.policy_failure:
                continue
            level = labels[p.case_id]["levels"].get(tree_id)
            if level is not None and p.applies.get(tree.hazard):
                values.append(tree_loss(tree, model.levels[tree_id], p.answers, level))
        out[tree_id] = statistics.mean(values) if values else None
    return out


def mean_tree_loss(model, prepared: list, labels: dict) -> float | None:
    values = [v for v in per_tree_loss(model, prepared, labels).values() if v is not None]
    return statistics.mean(values) if values else None


def right_level_share(model, prepared: list, labels: dict) -> float | None:
    """How often a tree's most likely level is the level the expert labels give."""
    hit = total = 0
    for p in prepared:
        if p.stopped or p.policy_failure:
            continue
        for tree_id, tree in model.trees.items():
            level = labels[p.case_id]["levels"].get(tree_id)
            if level is None or not p.applies.get(tree.hazard):
                continue
            dist = distribution(model.levels[tree_id], reach(tree, p.answers))
            hit += max(range(3), key=lambda j: dist[j]) == level
            total += 1
    return hit / total if total else None


def choose_thresholds(model, prepared: list, labels: dict, ctx: Context) -> dict:
    """On cases that pass basic checks and are under the severity ceiling. Requirement status does not matter."""
    rows = []
    anchors = ctx.anchors
    for p in prepared:
        if p.stopped or p.policy_failure:
            continue
        scored = score(model, p.answers, p.applies, anchors)
        if scored["highest_severity"] < ctx.ceiling():
            rows.append((scored["risk"], labels[p.case_id]["risky"]))
    return choose(rows, ctx.settings.get("decision.risky_approval_target"), ctx.settings.get("decision.high_risk_precision_target"))


def route_counts(model, prepared: list, thresholds: dict, labels: dict, ctx: Context) -> dict:
    """The full decision table on these cases."""
    results = decide_many(prepared, model, thresholds, ctx)
    approved = [r for r in results if r["decision"]["route"] == "approved"]
    automatic = [r for r in results if r["decision"]["route"] in AUTOMATIC]
    risky = sum(labels[r["case_id"]]["risky"] for r in approved)
    return {
        "cases": len(results), "results": results, "approved": len(approved), "automatic": len(automatic), "risky_among_approved": risky,
        "approved_share": len(approved) / len(results) if results else None,
        "decided_without_officer": len(automatic) / len(results) if results else None,
        "precision": (1 - risky / len(approved)) if approved else None,
    }


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not math.isnan(value)
