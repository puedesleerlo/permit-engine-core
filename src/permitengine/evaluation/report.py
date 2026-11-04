"""Train, choose thresholds, and compare first guess, trained and shuffled on validation."""
import json
from pathlib import Path

from ..learning.train import train_model
from ..pipeline.case import Context, load_context
from ..store.manifest import rules_hash, settings_hash
from ..trees.loader import Model, crossings_tree, first_guess, load_model, save_model
from ..workspace import EngineError, Workspace
from .common import answers_folder, choose_thresholds, mean_tree_loss, per_tree_loss, prepare_split, route_counts, rows_by_tree
from .labels import load_labels
from .stats import wilson

SHUFFLE_SEED = 12345
CANDIDATES = ("trained", "shuffled", "trained-crossings")
ARM_NAMES = {"first-guess": "First guess", "trained": "Trained on labelled cases", "shuffled": "Shuffled labels (control)"}


def train_candidates(ws: Workspace, answers: str = "simulated", model_name: str | None = None, first_guess_dir: Path | None = None) -> dict:
    ctx = load_context(ws, first_guess_dir)
    strength, iterations = ctx.settings.get("training.first_guess_strength"), ctx.settings.get("training.em_iterations")
    first_guess(ctx.trees, strength)  # stops here with a clear message if no first guess exists yet
    splits = ws.splits()
    labels = load_labels(ws, ("train",))
    folder = answers_folder(ws, ctx, answers, model_name)
    prepared = prepare_split(ws, ctx, splits["train"], folder)
    fitted_on = {"dataset_hash": ws.dataset_hash(), "rules_hash": rules_hash(ws), "settings_hash": settings_hash(ws), "answers": answers,
                 "first_guess_dir": str(first_guess_dir) if first_guess_dir else None, "cases": len(prepared)}
    rows = rows_by_tree(prepared, labels, ctx.trees)
    models = {"trained": train_model(ctx.trees, rows, strength, iterations, "trained"),
              "shuffled": train_model(ctx.trees, rows, strength, iterations, "shuffled", shuffle_seed=SHUFFLE_SEED)}
    try:
        wider = dict(ctx.trees)
        wider["traffic.likelihood"] = crossings_tree(ws.rules, ctx.trees["traffic.likelihood"])
        models["trained-crossings"] = train_model(wider, rows, strength, iterations, "trained-crossings")
    except EngineError:
        pass
    for name, model in models.items():
        save_model(model, ws.weights / "candidates" / name, {"fitted_on": fitted_on})
    return {"trained": sorted(models), "rows": {t: len(r) for t, r in rows.items()}, "fitted_on": fitted_on}


def choose_candidate_thresholds(ws: Workspace, answers: str = "simulated", model_name: str | None = None, first_guess_dir: Path | None = None) -> dict:
    ctx = load_context(ws, first_guess_dir)
    splits = ws.splits()
    labels = load_labels(ws, ("validation",))
    prepared = list(prepare_split(ws, ctx, splits["validation"], answers_folder(ws, ctx, answers, model_name)).values())
    out = {}
    for name in CANDIDATES:
        folder = ws.weights / "candidates" / name
        if not (folder / "weights.json").exists():
            continue
        body = json.loads((folder / "weights.json").read_text(encoding="utf-8"))
        model = load_model(folder)
        model.thresholds = choose_thresholds(model, prepared, labels, ctx)
        save_model(model, folder, {"fitted_on": body.get("fitted_on")})
        out[name] = model.thresholds
    if not out:
        raise EngineError("no candidate weights found; run `train` first")
    return out


def arm_row(name: str, model: Model, prepared: list, thresholds: dict, labels: dict, ctx: Context) -> dict:
    counts = route_counts(model, prepared, thresholds, labels, ctx)
    low, high = wilson(counts["risky_among_approved"], counts["approved"])
    return {"name": name, "loss": mean_tree_loss(model, prepared, labels), "approved": counts["approved_share"],
            "risky_among_approved": counts["risky_among_approved"] / counts["approved"] if counts["approved"] else None,
            "interval": [low, high], "approved_count": counts["approved"], "cases": counts["cases"], "t_low": thresholds["t_low"], "t_high": thresholds["t_high"], "threshold_notes": thresholds.get("notes", []),
            "per_tree_loss": per_tree_loss(model, prepared, labels)}


def validation_report(ws: Workspace, answers: str = "simulated", model_name: str | None = None, first_guess_dir: Path | None = None) -> dict:
    ctx = load_context(ws, first_guess_dir)
    splits = ws.splits()
    labels = load_labels(ws, ("validation",))
    prepared = list(prepare_split(ws, ctx, splits["validation"], answers_folder(ws, ctx, answers, model_name)).values())
    arms = []
    first = first_guess(ctx.trees, ctx.settings.get("training.first_guess_strength"))
    arms.append(arm_row(ARM_NAMES["first-guess"], first, prepared, choose_thresholds(first, prepared, labels, ctx), labels, ctx))
    for name in ("trained", "shuffled"):
        folder = ws.weights / "candidates" / name
        if not (folder / "weights.json").exists():
            raise EngineError(f"{folder} has no weights; run `train` first")
        model = load_model(folder)
        arms.append(arm_row(ARM_NAMES[name], model, prepared, model.thresholds or choose_thresholds(model, prepared, labels, ctx), labels, ctx))
    report = {"split": "validation", "answers": answers, "synthetic": True, "arms": arms,
              "note": "Thresholds are chosen on these same validation cases, so these are optimistic beside a held-out test."}
    crossings = ws.weights / "candidates" / "trained-crossings"
    if (crossings / "weights.json").exists():
        grown = load_model(crossings)
        report["crossings"] = {"loss_before": arms[1]["per_tree_loss"]["traffic.likelihood"],
                               "loss_after": per_tree_loss(grown, prepared, labels)["traffic.likelihood"]}
    ws.reports.mkdir(parents=True, exist_ok=True)
    (ws.reports / "validation.json").write_text(json.dumps(report, indent=1, sort_keys=True), encoding="utf-8")
    return report
