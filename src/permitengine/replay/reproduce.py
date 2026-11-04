"""Reproduce a logged decision from stored inputs, with no calls allowed, and check it is identical. Refuses if anything is missing."""
from pathlib import Path

from .. import ARITHMETIC_VERSION
from ..hashing import canonical, content_hash
from ..pipeline.case import load_context, run_case
from ..store.log import Log
from ..store.manifest import rules_hash, settings_hash
from ..trees.loader import Model
from ..workspace import EngineError, Workspace


def reproduce(ws: Workspace, run_id: str, case_id: str | None = None) -> dict:
    log = Log(ws.runs / f"{run_id}.sqlite", run_id, create=False)
    events = log.events("decision.made", case_id)
    if not events:
        raise EngineError(f"no logged decision for {case_id or 'this run'}")
    checked, mismatched = 0, []
    context_cache = {}
    for event in events:
        payload = event["payload"]
        manifest = log.blob(payload["manifest"])
        if manifest["arithmetic_version"] != ARITHMETIC_VERSION:
            raise EngineError(f"refused: the log used arithmetic version {manifest['arithmetic_version']}, and this code is {ARITHMETIC_VERSION}")
        first_guess_dir = manifest.get("first_guess_dir")
        ctx = context_cache.get(first_guess_dir)
        if ctx is None:
            ctx = context_cache[first_guess_dir] = load_context(ws, Path(first_guess_dir) if first_guess_dir else None)
        if rules_hash(ws) != manifest["rules_hash"]:
            raise EngineError("refused: rules have changed since this decision")
        if settings_hash(ws) != manifest["settings_hash"]:
            raise EngineError("refused: settings have changed since this decision")
        app = ws.application(event["case_id"])
        if content_hash(app.hash_input()) != manifest["application"]:
            raise EngineError(f"refused: the application for {event['case_id']} has changed since this decision")
        record = log.blob(manifest["record"])
        weights = log.blob(manifest["weights"])
        model = Model(manifest["weights_version"], ctx.trees, weights["levels"], weights["counts"])
        result = run_case(app, record, model, manifest["thresholds"], ctx)
        same = canonical(result["decision"]) == canonical(payload["decision"]) and canonical(result["input"]) == canonical(payload["input"])
        checked += 1
        if not same:
            mismatched.append(event["case_id"])
    log.close()
    return {"run_id": run_id, "checked": checked, "identical": checked - len(mismatched), "mismatched": mismatched}
