"""One LLM call per test case, answering approve or deny. Stores answers, reads no labels. Scored in final.py."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..models.budget import Budget, BudgetExceeded
from ..models.llm import LlmClient, ModelFailure
from ..pipeline.case import load_context
from ..reading.schemas import BASELINE_SCHEMA
from ..store.cache import Cache
from ..workspace import Workspace


def baseline_system(ws: Workspace) -> str:
    prompt = (ws.rules / "prompts" / "baseline.md").read_text(encoding="utf-8")
    return prompt.replace("{{ordinance}}", (ws.rules / "ordinance.yaml").read_text(encoding="utf-8"))


def answers_path(ws: Workspace, model: str) -> Path:
    return ws.cache / "comparisons" / "baseline" / f"{model}.json"


def run_baseline(ws: Workspace, llm: LlmClient, concurrency: int) -> dict:
    system = baseline_system(ws)
    case_ids = ws.splits()["test"]
    stopped = []

    def one(case_id):
        if stopped:
            return case_id, None
        app = ws.application(case_id)
        user = json.dumps({"form": app.form, "cover_letter": app.cover_letter, "attachments": app.attachments}, indent=1, sort_keys=True, ensure_ascii=False)
        try:
            return case_id, llm.structured("baseline", system, user, BASELINE_SCHEMA, case_id)
        except ModelFailure as exc:
            return case_id, {"ruling": None, "reason": str(exc)}
        except BudgetExceeded as exc:
            stopped.append(str(exc))
            return case_id, None

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        answers = dict(pool.map(one, case_ids))
    path = answers_path(ws, llm.spec.model)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"model": llm.spec.model, "answers": {k: v for k, v in answers.items() if v is not None}}, indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    return {"answered": sum(v is not None for v in answers.values()), "stopped_by": stopped[0] if stopped else None}


def load_baseline(ws: Workspace, model: str) -> dict | None:
    path = answers_path(ws, model)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def command(ws: Workspace, model_name: str | None = None) -> dict:
    ctx = load_context(ws)
    settings = ctx.settings
    budget = Budget(ws.ledger / "spend.jsonl", settings.get("budget.max_usd_total"), settings.get("budget.max_jev_input_tokens"))
    llm = LlmClient.from_env(settings, Cache(ws.cache / "answers"), budget, model_name)
    result = run_baseline(ws, llm, settings.get("models.max_concurrency"))
    result["meter"] = budget.summary()
    return result
