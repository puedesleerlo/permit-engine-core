"""Jev asked directly for each level, one question per tree that applies, on the pipeline's own inputs. See decision record 0002."""
import json
from pathlib import Path

from ..models.budget import Budget, BudgetExceeded
from ..models.jev import JevClient, JevFailure
from ..pipeline.case import Context, Prepared, load_context, prepare_many
from ..reading.read import typed_values
from ..store.cache import Cache
from ..store.records import load_records
from ..trees.loader import LEVEL_NAMES
from ..workspace import EngineError, Workspace
from .common import answers_folder

LEVEL_TEXT = {
    "likelihood": {"rare": "Not expected at an event like this one.", "possible": "Could well happen at an event like this one.",
                   "likely": "Expected to happen at an event like this one, unless something changes."},
    "severity": {"minor": "If it happens, treated on site, with no lasting harm.", "serious": "If it happens, people need hospital care but recover.",
                 "critical": "If it happens, it is life-threatening or causes lasting harm."},
}


def request_for(p: Prepared, ctx: Context) -> tuple:
    """The same inputs the trees read, and one level question per tree that applies. Never the cover letter."""
    questions = {}
    documents = {}
    linked = {r["evidence_type"]: r for r in p.evidence if r["status"] == "found"}
    for tree_id, tree in ctx.trees.items():
        if not p.applies.get(tree.hazard):
            continue
        hazard = ctx.hazards.get(tree.hazard, {})
        meaning = hazard.get("description") or tree.hazard.replace("_", " ")
        questions[f"level__{tree_id}"] = {"type": "choice", "instructions": f"Which {tree.scale} level is right for the {tree.hazard} hazard at this event? {tree.hazard} means: {meaning}",
                                          "criteria": LEVEL_TEXT[tree.scale]}
        for question in tree.questions:
            for need in question.get("needs", []):
                if need in linked and linked[need]["document"] in p.app.attachments:
                    documents[need] = p.app.attachments[linked[need]["document"]]
    state = {"event": "A street race that needs a city permit.", "application": typed_values(p.app.form, p.spectators),
             "evidence": {r["evidence_type"]: {"status": r["status"], "verdict": r["verdict"], "fields": [{"name": f["name"], "value": f["value"]} for f in r["fields"] if f["verified"]]} for r in p.evidence},
             "rule_answers": p.rule_answers, "documents": documents}
    return state, questions


def answers_path(ws: Workspace, jev_model: str) -> Path:
    return ws.cache / "comparisons" / "direct_jev" / f"{jev_model}.json"


def read_levels(reply: dict, questions: dict, trees: dict) -> dict:
    out = {}
    for key in questions:
        tree_id = key.removeprefix("level__")
        names = LEVEL_NAMES[trees[tree_id].scale]
        probabilities = reply["answers"][key]["probabilities"]
        out[tree_id] = [float(probabilities[name]) for name in names]
    return out


def run_direct(ws: Workspace, ctx: Context, jev: JevClient, folder: Path, splits=("test", "validation")) -> dict:
    """Validation answers choose Jev's own thresholds, so its approvals are compared fairly. Test answers are scored once."""
    all_splits = ws.splits()
    case_ids = [c for name in splits for c in all_splits[name]]
    records = load_records(folder, case_ids)
    prepared = prepare_many([(ws.application(c), records[c]) for c in case_ids], ctx)
    stopped = []

    def one(p):
        if p.stopped or stopped:
            return p.case_id, None
        state, questions = request_for(p, ctx)
        try:
            return p.case_id, read_levels(jev.ask("direct_jev", state, questions, p.case_id), questions, ctx.trees)
        except (JevFailure, KeyError, TypeError, ValueError) as exc:
            return p.case_id, {"failed": type(exc).__name__}
        except BudgetExceeded as exc:
            stopped.append(str(exc))
            return p.case_id, None

    answers = dict(jev.map(one, prepared))
    path = answers_path(ws, jev.model)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"model": jev.model, "answers": {k: v for k, v in answers.items() if v is not None}}, indent=1, sort_keys=True), encoding="utf-8")
    return {"answered": sum(v is not None for v in answers.values()), "stopped_by": stopped[0] if stopped else None}


def load_direct(ws: Workspace, jev_model: str) -> dict | None:
    path = answers_path(ws, jev_model)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def command(ws: Workspace, model_name: str | None = None) -> dict:
    ctx = load_context(ws)
    settings = ctx.settings
    budget = Budget(ws.ledger / "spend.jsonl", settings.get("budget.max_usd_total"), settings.get("budget.max_jev_input_tokens"))
    jev_model = settings.get("models.jev.id")
    if not jev_model:
        raise EngineError("models.jev.id is not set in settings")
    jev = JevClient.from_env(jev_model, Cache(ws.cache / "answers"), budget, settings.get("models.max_concurrency"))
    result = run_direct(ws, ctx, jev, answers_folder(ws, ctx, "real", model_name))
    result["meter"] = budget.summary()
    return result
