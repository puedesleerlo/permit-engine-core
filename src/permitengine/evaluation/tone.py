"""Does a cover letter's tone change what is read or decided? Compares each tone with the plain letter on the same request,
against a noise floor from re-reading the same plain cases past the cache. Uses no labels, so it does not touch the one look.
"""
import json

from ..models.budget import Budget
from ..models.jev import JevClient
from ..models.llm import LlmClient, choose_model
from ..pipeline.case import decide_many, load_context
from ..reading.read import RealReader, read_many
from ..store.cache import Cache
from ..store.records import records_dir
from ..trees.loader import load_model
from ..workspace import EngineError, Workspace
from .common import answers_folder, prepare_split
from .stats import wilson


def reading(record: dict) -> dict:
    first = record["first_pass"].get("output") or {}
    return {"evidence": {e["evidence_type"]: (e.get("status"), sorted((f["name"], str(f["value"])) for f in e.get("fields", []))) for e in first.get("evidence", [])},
            "verdicts": {v["evidence_type"]: v["verdict"] for v in (record["judge"].get("output") or {}).get("verdicts", [])},
            "spectators": (first.get("expected_spectators") or {}).get("value"),
            "unmapped": sorted(u.get("document") or "" for u in first.get("unmapped_documents", []))}


def _compare(pairs: list, prepared_a: dict, prepared_b: dict, model, thresholds: dict, ctx) -> dict:
    a = {r["case_id"]: r["decision"]["route"] for r in decide_many([prepared_a[x] for x, _ in pairs], model, thresholds, ctx)}
    b = {r["case_id"]: r["decision"]["route"] for r in decide_many([prepared_b[y] for _, y in pairs], model, thresholds, ctx)}
    evidence, decisions = [], []
    for x, y in pairs:
        if reading(prepared_a[x].record) != reading(prepared_b[y].record):
            evidence.append(y)
        if a[x] != b[y]:
            decisions.append({"case_id": y, "from": a[x], "to": b[y]})
    n = len(pairs)
    return {"compared": n, "evidence_flips": len(evidence), "evidence_interval": list(wilson(len(evidence), n)), "decision_flips": len(decisions),
            "decision_interval": list(wilson(len(decisions), n)), "decision_changes": decisions}


def tone_report(ws: Workspace, version: str, model_name: str | None = None) -> dict:
    ctx = load_context(ws)
    splits = ws.splits()
    folder = answers_folder(ws, ctx, "real", model_name)
    tones = prepare_split(ws, ctx, splits["tone"], folder)
    bases = sorted({c.split("-")[0] for c in splits["tone"]})
    plain = prepare_split(ws, ctx, [f"{b}-plain" for b in bases], folder)
    model = load_model(ws.weights / version)
    if not model.thresholds:
        raise EngineError(f"weights version {version} has no thresholds")
    out = {"version": version, "requests": len(bases), "tones": {}}
    for tone in sorted({c.split("-", 1)[1] for c in splits["tone"]}):
        pairs = [(f"{b}-plain", f"{b}-{tone}") for b in bases if f"{b}-{tone}" in tones]
        out["tones"][tone] = _compare(pairs, plain, tones, model, model.thresholds, ctx)
    stable = ws.cache / "records" / "stability" / choose_model(ctx.settings, model_name)
    if stable.exists():
        again = prepare_split(ws, ctx, [f"{b}-plain" for b in bases], stable)
        out["noise_floor"] = _compare([(f"{b}-plain", f"{b}-plain") for b in bases], plain, again, model, model.thresholds, ctx)
        out["noise_floor"]["note"] = "The same plain letters read a second time, past the stored answers."
    else:
        out["noise_floor"] = None
    (ws.reports / "tone.json").write_text(json.dumps(out, indent=1, sort_keys=True), encoding="utf-8")
    return out


def stability_read(ws: Workspace, model_name: str | None = None) -> dict:
    """Re-reads the plain letters of the tone requests with an empty cache, so these are real second answers."""
    ctx = load_context(ws)
    settings = ctx.settings
    model = choose_model(settings, model_name)
    budget = Budget(ws.ledger / "spend.jsonl", settings.get("budget.max_usd_total"), settings.get("budget.max_jev_input_tokens"))
    cache = Cache(ws.cache / "answers_stability")
    llm = LlmClient.from_env(settings, cache, budget, model)
    jev = JevClient.from_env(settings.get("models.jev.id"), cache, budget, settings.get("models.max_concurrency"))
    bases = sorted({c.split("-")[0] for c in ws.splits()["tone"]})
    folder = ws.cache / "records" / "stability" / model
    result = read_many(ws, [f"{b}-plain" for b in bases], RealReader(ws, llm, jev), ctx, folder, settings.get("models.max_concurrency"))
    return {"read": len(result["done"]), "stopped_by": result["stopped_by"], "meter": budget.summary()}
