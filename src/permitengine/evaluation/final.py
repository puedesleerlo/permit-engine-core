"""The sealed test. Runs once per dataset hash, with no bypass. The ledger is written before test labels are opened.

The whole scoring path first runs on validation, so a bug cannot spend the one look. Only this file reads test labels.
"""
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path

from ..learning.thresholds import choose
from ..models.llm import choose_model
from ..pipeline.case import Context, load_context
from ..store.records import load_records
from ..trees.loader import Model, first_guess, load_model
from ..workspace import EngineError, Workspace
from .baseline import load_baseline
from .common import answers_folder, base_id, case_loss, choose_thresholds, mean_tree_loss, prepare_split, right_level_share, route_counts
from .direct_jev import load_direct
from .labels import load_labels, load_test_labels
from .report import ARM_NAMES
from .stats import bootstrap_difference, wilson

RISKY_LIMIT = 0.05


def _ledger(ws: Workspace) -> dict:
    path = ws.ledger / "test_ledger.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write_ledger(ws: Workspace, ledger: dict) -> None:
    ws.ledger.mkdir(parents=True, exist_ok=True)
    (ws.ledger / "test_ledger.json").write_text(json.dumps(ledger, indent=1, sort_keys=True), encoding="utf-8")


def _arm(name: str, model: Model, prepared: list, thresholds: dict, labels: dict, ctx: Context) -> dict:
    counts = route_counts(model, prepared, thresholds, labels, ctx)
    approved = [r for r in counts["results"] if r["decision"]["route"] == "approved"]
    forbidden = sum(not labels[r["case_id"]]["allowed"] for r in approved)
    low, high = wilson(counts["risky_among_approved"], counts["approved"])
    flow, fhigh = wilson(forbidden, counts["approved"])
    return {"name": name, "loss": mean_tree_loss(model, prepared, labels), "right_level": right_level_share(model, prepared, labels), "approved": counts["approved_share"],
            "risky_among_approved": counts["risky_among_approved"] / counts["approved"] if counts["approved"] else None, "interval": [low, high],
            "approved_count": counts["approved"], "risky_approvals": counts["risky_among_approved"], "forbidden_permits": forbidden, "forbidden_interval": [flow, fhigh],
            "sent_to_officer": sum(r["decision"]["route"] == "officer" for r in counts["results"]) / len(prepared) if prepared else None,
            "wrong_denials": sum(r["decision"]["route"] == "proposed_denial" and labels[r["case_id"]]["allowed"] for r in counts["results"]),
            "decided_without_officer": counts["decided_without_officer"], "t_low": thresholds["t_low"], "t_high": thresholds["t_high"],
            "_routes": {r["case_id"]: r["decision"]["route"] for r in counts["results"]}, "_rows": {r["case_id"]: r["decision"]["row"] for r in counts["results"]}}


def _pairs_loss(a: Model, b: Model, prepared: list, labels: dict) -> tuple:
    pairs, clusters = [], []
    for p in prepared:
        if p.stopped or p.policy_failure:
            continue
        la, lb = case_loss(a, p, labels[p.case_id]), case_loss(b, p, labels[p.case_id])
        if la is not None and lb is not None:
            pairs.append((la, lb))
            clusters.append(base_id(p.case_id))
    return pairs, clusters


def conditions(arms: dict, models: dict, prepared: list, labels: dict) -> list:
    trained, first, control = arms["trained"], arms["first-guess"], arms["shuffled"]
    out = []
    for other, name in (("first-guess", "Lower loss than the first guess"), ("shuffled", "Lower loss than the shuffled control")):
        pairs, clusters = _pairs_loss(models["trained"], models[other], prepared, labels)
        diff = bootstrap_difference(pairs, clusters)
        passed = diff["high"] is not None and diff["high"] < 0
        out.append({"name": name, "passed": passed, "detail": f"Difference in mean loss {diff['mean']:+.3f}, 95% interval {diff['low']:+.3f} to {diff['high']:+.3f}." if diff["mean"] is not None else "No cases.", "difference": diff})
    pairs = [(float(trained["_routes"][p.case_id] == "approved"), float(first["_routes"][p.case_id] == "approved")) for p in prepared]
    diff = bootstrap_difference(pairs, [base_id(p.case_id) for p in prepared])
    passed = diff["low"] is not None and diff["low"] > 0
    out.append({"name": "More approvals than the first guess", "passed": passed, "detail": f"Difference in share approved {diff['mean']:+.3f}, 95% interval {diff['low']:+.3f} to {diff['high']:+.3f}." if diff["mean"] is not None else "No cases.", "difference": diff})
    low = trained["interval"][0]
    passed = low is None or low <= RISKY_LIMIT
    share = "no approvals" if low is None else f"{trained['risky_approvals']} of {trained['approved_count']} approvals labelled risky, Wilson interval {trained['interval'][0]:.3f} to {trained['interval'][1]:.3f}"
    out.append({"name": "Risky approvals not clearly above 5%", "passed": passed, "detail": f"{share}. This fails only if the lower end is above 5%.", "difference": None})
    return out


def _baseline_arm(ws: Workspace, ctx: Context, prepared: list, labels: dict, engine_routes: dict, model_name: str | None) -> dict:
    stored = load_baseline(ws, choose_model(ctx.settings, model_name))
    name = "One LLM reads and decides (baseline)"
    if stored is None:
        return {"name": name, "status": "not_run", "loss": None, "approved": None, "risky_among_approved": None, "interval": [None, None]}
    answers = stored["answers"]

    def score(case_ids):
        rows = [c for c in case_ids if answers.get(c, {}).get("ruling")]
        approved = [c for c in rows if answers[c]["ruling"] == "approve"]
        risky = sum(labels[c]["risky"] for c in approved)
        low, high = wilson(risky, len(approved))
        right = sum((answers[c]["ruling"] == "approve") == (labels[c]["right_route"] == "approve") for c in rows)
        return {"cases": len(rows), "approved": len(approved) / len(rows) if rows else None, "risky_among_approved": risky / len(approved) if approved else None, "interval": [low, high],
                "forbidden_permits": sum(not labels[c]["allowed"] for c in approved), "agrees_with_right_route": right / len(rows) if rows else None}

    every = [p.case_id for p in prepared]
    automatic = [c for c in every if engine_routes[c] in ("approved", "returned")]
    all_cases = score(every)
    return {"name": name, "status": "run", "loss": None, "approved": all_cases["approved"], "risky_among_approved": all_cases["risky_among_approved"], "interval": all_cases["interval"],
            "on_all_cases": all_cases, "on_cases_engine_decided": score(automatic)}


def _direct_arm(ws: Workspace, ctx: Context, prepared: list, labels: dict, engine_routes: dict, engine_rows: dict, thresholds: dict) -> dict:
    name = "Jev asked directly"
    jev_model = ctx.settings.get("models.jev.id", None)
    stored = load_direct(ws, jev_model) if jev_model else None
    if stored is None:
        return {"name": name, "status": "not_run", "loss": None, "approved": None, "risky_among_approved": None, "interval": [None, None]}
    answers = stored["answers"]
    anchors = ctx.anchors
    hazards = sorted({t.hazard for t in ctx.trees.values()})
    pairs_of_trees = [(next(i for i, t in ctx.trees.items() if t.hazard == h and t.scale == "likelihood"),
                       next(i for i, t in ctx.trees.items() if t.hazard == h and t.scale == "severity")) for h in hazards]

    def risk_of(levels):
        return sum(sum(a * b for a, b in zip(levels[lt], anchors["likelihood"])) * sum(a * b for a, b in zip(levels[st], anchors["severity"]))
                   for lt, st in pairs_of_trees if lt in levels and st in levels)

    # Jev's own thresholds, chosen on validation by the same rule as the trees. Falls back to the released t_low if those answers are absent.
    val_labels = load_labels(ws, ("validation",))
    own_rows = [(risk_of(answers[c]), val_labels[c]["risky"]) for c in ws.splits()["validation"] if answers.get(c) and "failed" not in answers[c]]
    own = choose(own_rows, ctx.settings.get("decision.risky_approval_target"), ctx.settings.get("decision.high_risk_precision_target")) if own_rows else None
    t_low = own["t_low"] if own else thresholds["t_low"]

    def score(case_ids):
        losses, risks, hits, total = [], {}, 0, 0
        for case_id in case_ids:
            levels = answers.get(case_id)
            if not levels or "failed" in levels:
                continue
            values = []
            for tree_id, dist in levels.items():
                truth = labels[case_id]["levels"].get(tree_id)
                if truth is None:
                    continue
                values.append(-math.log(max(dist[truth], 1e-6)))
                hits += max(range(3), key=lambda j: dist[j]) == truth
                total += 1
            if values:
                losses.append(statistics.mean(values))
            risks[case_id] = risk_of(levels)
        # The same requirement checks and red flags as the engine: only risk is Jev's. Row 4 and above means those all passed.
        approved = [c for c, r in risks.items() if r < t_low and engine_rows.get(c, 0) >= 4]
        risky = sum(labels[c]["risky"] for c in approved)
        low, high = wilson(risky, len(approved))
        return {"cases": len(risks), "loss": statistics.mean(losses) if losses else None, "right_level": hits / total if total else None, "approved": len(approved) / len(risks) if risks else None,
                "risky_among_approved": risky / len(approved) if approved else None, "interval": [low, high]}

    every = [p.case_id for p in prepared]
    automatic = [c for c in every if engine_routes[c] in ("approved", "returned")]
    all_cases = score(every)
    return {"name": name, "status": "run", "loss": all_cases["loss"], "right_level": all_cases["right_level"], "approved": all_cases["approved"], "risky_among_approved": all_cases["risky_among_approved"], "interval": all_cases["interval"],
            "on_all_cases": all_cases, "on_cases_engine_decided": score(automatic), "t_low": t_low,
            "note": "Jev's risk uses its own threshold, chosen on validation by the same rule as the trees. Approvals apply the same requirement checks and red flags as the engine." if own else "Approvals use the released t_low, because its validation answers are absent."}


def _score(ws: Workspace, ctx: Context, version: str, case_ids: list, labels: dict, folder: Path, thresholds_from: tuple) -> dict:
    prepared = list(prepare_split(ws, ctx, case_ids, folder).values())
    chooser, chooser_labels = thresholds_from
    released = load_model(ws.weights / version)
    if not released.thresholds:
        raise EngineError(f"weights version {version} has no thresholds")
    first = first_guess(ctx.trees, ctx.settings.get("training.first_guess_strength"))
    shuffled_folder = ws.weights / "candidates" / "shuffled"
    shuffled = load_model(shuffled_folder)
    models = {"first-guess": first, "trained": released, "shuffled": shuffled}
    thresholds = {"first-guess": choose_thresholds(first, chooser, chooser_labels, ctx), "trained": released.thresholds,
                  "shuffled": shuffled.thresholds or choose_thresholds(shuffled, chooser, chooser_labels, ctx)}
    arms = {name: _arm(ARM_NAMES[name], models[name], prepared, thresholds[name], labels, ctx) for name in models}
    return {"prepared": prepared, "arms": arms, "models": models, "conditions": conditions(arms, models, prepared, labels), "thresholds": thresholds}


def final_report(ws: Workspace, version: str, answers: str = "real", model_name: str | None = None, first_guess_dir: Path | None = None) -> dict:
    dataset = ws.dataset_hash()
    ledger = _ledger(ws)
    if dataset in ledger:
        raise EngineError(f"the test set for dataset {dataset[:12]} was already opened on {ledger[dataset]['opened_at']}, for version {ledger[dataset]['version']}. "
                          "It runs once per dataset. A new look needs a new test split.")
    ctx = load_context(ws, first_guess_dir)
    splits = ws.splits()
    folder = answers_folder(ws, ctx, answers, model_name)
    test_records = load_records(folder, splits["test"])
    simulated = [c for c, r in test_records.items() if r.get("source") != "real"]
    if simulated:
        raise EngineError(f"{len(simulated)} test-split records are not real answers, such as {simulated[0]}. The one look must be on real answers.")
    val_labels = load_labels(ws, ("validation",))
    validation = list(prepare_split(ws, ctx, splits["validation"], folder).values())
    # A rehearsal of the whole path on validation, including the comparisons and the rendering. If this raises, the ledger is untouched and test labels stay closed.
    rehearsal = _score(ws, ctx, version, splits["validation"], val_labels, folder, (validation, val_labels))
    render_markdown(_build_report(ws, ctx, version, dataset, answers, rehearsal, val_labels, model_name))

    ledger[dataset] = {"version": version, "opened_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "status": "opened", "answers": answers}
    _write_ledger(ws, ledger)

    test_labels = load_test_labels(ws)
    scored = _score(ws, ctx, version, splits["test"], test_labels, folder, (validation, val_labels))
    report = _build_report(ws, ctx, version, dataset, answers, scored, test_labels, model_name)
    verdict = report["verdict"]
    ws.reports.mkdir(parents=True, exist_ok=True)
    (ws.reports / "final.json").write_text(json.dumps(report, indent=1, sort_keys=True), encoding="utf-8")
    (ws.reports / "final.md").write_text(render_markdown(report), encoding="utf-8")
    ledger[dataset]["status"] = "done"
    ledger[dataset]["verdict"] = verdict
    _write_ledger(ws, ledger)
    return report


def _build_report(ws: Workspace, ctx: Context, version: str, dataset: str, answers: str, scored: dict, labels: dict, model_name: str | None) -> dict:
    arms, conds = scored["arms"], scored["conditions"]
    trained = arms["trained"]
    routes = trained["_routes"]
    verdict = "pass" if all(c["passed"] for c in conds) else "fail"
    extra = [_baseline_arm(ws, ctx, scored["prepared"], labels, routes, model_name), _direct_arm(ws, ctx, scored["prepared"], labels, routes, trained["_rows"], scored["thresholds"]["trained"])]
    return {
        "status": "run", "dataset_hash": dataset, "version": version, "synthetic": True, "answers": answers, "verdict": verdict,
        "conditions": [{k: c[k] for k in ("name", "passed", "detail")} for c in conds],
        "differences": {c["name"]: c["difference"] for c in conds},
        "forbidden_permits": trained["forbidden_permits"], "risky_approvals": trained["risky_approvals"], "approved": trained["approved_count"],
        "risky_interval": trained["interval"], "forbidden_interval": trained["forbidden_interval"],
        "arms": [{k: v for k, v in arms[name].items() if not k.startswith("_")} for name in ("first-guess", "trained", "shuffled")] + extra,
        "limits": "About 3 risky approvals in 52 gives a Wilson interval of roughly 2% to 16%, so this test cannot confirm a 5% target. It can only show when risky approvals are clearly above it.",
    }

def _pct(value) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def _num(value) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def render_markdown(report: dict) -> str:
    """Rendered from final.json, so the two cannot disagree."""
    lines = ["# Final test report", "", "All applications are synthetic.", "",
             f"**Verdict: {report['verdict']}.** Weights version `{report['version']}`, on answers marked `{report['answers']}`.", "", "## The pass rule", "",
             "| Condition | Passed | Detail |", "| --- | --- | --- |"]
    for row in report["conditions"]:
        lines.append(f"| {row['name']} | {'yes' if row['passed'] else 'no'} | {row['detail']} |")
    lines += ["", "## Arms", "", "| Arm | Loss | Right level | Approved | Risky among approved | Wilson interval |", "| --- | --- | --- | --- | --- | --- |"]
    for arm in report["arms"]:
        low, high = arm.get("interval", [None, None])
        interval = "n/a" if low is None else f"{low:.1%} to {high:.1%}"
        status = " (not run)" if arm.get("status") == "not_run" else ""
        lines.append(f"| {arm['name']}{status} | {_num(arm.get('loss'))} | {_pct(arm.get('right_level'))} | {_pct(arm.get('approved'))} | {_pct(arm.get('risky_among_approved'))} | {interval} |")
    lines += ["", f"Forbidden permits: {report['forbidden_permits']}. Risky approvals: {report['risky_approvals']} of {report['approved']} approvals.", "", "## What this test cannot show", "", report["limits"], ""]
    return "\n".join(lines)
