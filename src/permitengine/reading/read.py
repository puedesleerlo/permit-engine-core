"""Stages 2, 4 and 8: asking the models, in one flow, for real or simulated readers. Writes one reading record per case."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Protocol

from ..models.budget import BudgetExceeded
from ..models.jev import JevClient, JevFailure
from ..models.llm import LlmClient, ModelFailure
from ..pipeline.case import BASIC, SCREEN, Context
from ..reading.quotes import check_field, check_spectators
from ..store.records import write_record
from ..workspace import EngineError, Workspace
from .needed_types import needed_types
from .schemas import judge_schema, link_extract_schema

UNTYPED_FORM_FIELDS = ("description", "attachments")


def typed_values(form: dict, spectators=None) -> dict:
    """What later stages may read of the form: typed values only, never free text."""
    values = {k: v for k, v in form.items() if k not in UNTYPED_FORM_FIELDS}
    values["expected_spectators"] = spectators
    return values


class Reader(Protocol):
    source: str
    models: dict

    def link_extract(self, app, types: list) -> dict: ...

    def judge(self, app, items: list, typed: dict) -> dict: ...

    def jev(self, app, state: dict, questions: dict) -> dict: ...


def verified_items(output: dict, app, ctx: Context) -> list:
    items = []
    for entry in output.get("evidence", []):
        if entry.get("status") != "found":
            continue
        definition = ctx.evidence_type(entry["evidence_type"]) or {}
        passages = []
        for item in entry.get("fields", []):
            if check_field(item, entry.get("document"), app.attachments) is None:
                passages.append({"name": item["name"], "value": item["value"], "quote": item["quote"]})
        if passages:
            # The judge needs the sentence that makes the claim, which is rarely inside a typed field's quote. The document
            # has passed the quote check, so it is an attachment, never the form or the cover letter.
            items.append({"evidence_type": entry["evidence_type"], "name": definition.get("name"), "requires": definition.get("claim"),
                          "passages": passages, "document": app.attachments[entry["document"]]})
    return items


def jev_questions(trees: dict, applies: dict) -> dict:
    questions = {}
    for tree in trees.values():
        if applies.get(tree.hazard):
            for question in tree.questions:
                if question["kind"] == "jev":
                    questions[question["id"]] = question
    return questions


def reader_view(definition: dict) -> dict:
    """What the first pass is told about a type. How code compares a field afterwards is not its business."""
    fields = [{"name": f["name"], "type": f.get("type", "string")} for f in definition.get("fields", [])]
    return {"id": definition["id"], "name": definition.get("name"), "terms": definition.get("terms", []), "claim": definition.get("claim"),
            "whole_document": bool(definition.get("whole_document")), "fields": fields}


def jev_state(app, output: dict, typed: dict, questions: dict, ctx: Context, verdicts: dict) -> dict:
    """One state per case: typed values, evidence records and the whole plan documents the questions need. Never the cover letter."""
    linked = {e["evidence_type"]: e for e in output.get("evidence", []) if e.get("status") == "found"}
    documents, evidence = {}, {}
    for question in questions.values():
        for need in question.get("needs", []):
            if need in linked and linked[need].get("document") in app.attachments:
                documents[need] = app.attachments[linked[need]["document"]]
            elif need not in typed and ctx.evidence_type(need) is not None:
                documents[need] = None
    for type_id, entry in linked.items():
        fields = [{"name": f["name"], "value": f["value"]} for f in entry.get("fields", []) if check_field(f, entry.get("document"), app.attachments) is None]
        if fields:
            evidence[type_id] = {"verdict": verdicts.get(type_id), "fields": fields}
    return {"event": "A street race that needs a city permit.", "application": typed, "evidence": evidence, "documents": documents}


def read_case(app, reader: Reader, ctx: Context) -> dict:
    record = {"case_id": app.case_id, "source": reader.source, "models": reader.models, "needed_types": needed_types(ctx),
              "stopped": None, "first_pass": {"status": "skipped"}, "judge": {"status": "skipped"}, "jev": {"status": "skipped"}}
    basic = ctx.policy.one(BASIC, {"form": app.form, "fee_paid": app.form.get("fee_paid")})
    if basic.get("failed"):
        record["stopped"] = "basic"
        return record
    types = [reader_view(ctx.evidence_type(t)) for t in record["needed_types"]]
    try:
        output = reader.link_extract(app, types)
        record["first_pass"] = {"status": "ok", "output": output}
    except ModelFailure as exc:
        record["first_pass"] = {"status": "failed", "reason": str(exc)}
        output = {"evidence": [], "expected_spectators": None, "unmapped_documents": []}
    spectators = check_spectators(output.get("expected_spectators"), app.form)
    typed = typed_values(app.form, spectators)
    items = verified_items(output, app, ctx)
    if items:
        try:
            record["judge"] = {"status": "ok", "output": reader.judge(app, items, typed)}
        except ModelFailure as exc:
            record["judge"] = {"status": "failed", "reason": str(exc)}
    applies = ctx.policy.one(SCREEN, {"form": app.form, "extracted": {"expected_spectators": spectators}})
    questions = jev_questions(ctx.trees, applies)
    if questions:
        judged = (record["judge"].get("output") or {}).get("verdicts", [])
        state = jev_state(app, output, typed, questions, ctx, {v["evidence_type"]: v["verdict"] for v in judged})
        try:
            record["jev"] = {"status": "ok", "answers": reader.jev(app, state, questions)}
        except (JevFailure, ModelFailure) as exc:
            record["jev"] = {"status": "failed", "reason": str(exc)}
    return record


class RealReader:
    source = "real"

    def __init__(self, ws: Workspace, llm: LlmClient, jev: JevClient):
        self.llm = llm
        self.jev_client = jev
        self.models = {"llm": llm.spec.model, "jev": jev.model}
        self.prompt_link = (ws.rules / "prompts" / "link_extract.md").read_text(encoding="utf-8")
        self.prompt_judge = (ws.rules / "prompts" / "judge.md").read_text(encoding="utf-8")

    def link_extract(self, app, types: list) -> dict:
        system = f"{self.prompt_link}\n\nEvidence types:\n{json.dumps(types, indent=1, sort_keys=True, ensure_ascii=False)}"
        user = json.dumps({"form": app.form, "cover_letter": app.cover_letter, "attachments": app.attachments}, indent=1, sort_keys=True, ensure_ascii=False)
        return self.llm.structured("link_extract", system, user, link_extract_schema([t["id"] for t in types]), app.case_id)

    def judge(self, app, items: list, typed: dict) -> dict:
        user = json.dumps({"case": typed, "evidence": items}, indent=1, sort_keys=True, ensure_ascii=False)
        return self.llm.structured("judge", self.prompt_judge, user, judge_schema([i["evidence_type"] for i in items]), app.case_id)

    def jev(self, app, state: dict, questions: dict) -> dict:
        sent = {qid: {"type": "noul", "instructions": q["instructions"]} for qid, q in sorted(questions.items())}
        reply = self.jev_client.ask("jev", state, sent, app.case_id)
        answers = {}
        for question_id in sent:
            value = (reply["answers"].get(question_id) or {}).get("noul")
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 1:
                raise JevFailure(f"no usable answer for {question_id}")
            answers[question_id] = float(value)
        return answers


def read_many(ws: Workspace, case_ids: list, reader: Reader, ctx: Context, folder: Path, concurrency: int) -> dict:
    """Up to `concurrency` cases at once, each with at most one Jev request running. A budget stop ends the run, keeping what was written."""
    stop = threading.Event()
    stopped_by = []
    done = []

    def one(case_id):
        if stop.is_set():
            return
        try:
            record = read_case(ws.application(case_id), reader, ctx)
        except BudgetExceeded as exc:
            stop.set()
            stopped_by.append(str(exc))
            return
        write_record(folder, record)
        done.append(case_id)

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        list(pool.map(one, case_ids))
    if not case_ids:
        raise EngineError("no cases to read")
    return {"done": done, "stopped_by": stopped_by[0] if stopped_by else None}
