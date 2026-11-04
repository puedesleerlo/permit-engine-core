"""Stages 1 to 10 for a case, as a pure function of the stored record, the application, weights and thresholds.

Stages 1 to 8 do not depend on weights, so they run once per case and in batches. Stages 9 and 10 run with the weights of the moment.
"""
import yaml
from dataclasses import dataclass, field
from pathlib import Path

from ..config import Settings, load_settings
from ..policy.opa import Policy, PolicyError
from ..reading.compare import compare_fields
from ..reading.quotes import check_field, check_spectators
from ..risk.score import score
from ..trees.loader import load_trees
from ..workspace import EngineError, Workspace

BASIC = "data.permit.basic.result"
QUESTIONS = "data.permit.questions.answers"
SCREEN = "data.permit.screen.applies"
REQUIREMENTS = "data.permit.requirements.status"
DECISION = "data.permit.decision.result"
FAIL_CLOSED = {"row": 1, "route": "officer", "reason_code": "policy_unavailable", "clauses": [],
               "text": "The rules engine could not run, so an officer decides."}
PASSING_BASIC = {"form_complete": True, "fee_paid": True, "date_allowed": True, "failed": [], "clauses": {}}


@dataclass
class Context:
    settings: Settings
    policy: Policy
    evidence_map: dict
    trees: dict
    hazards: dict
    stop_switch: bool = False

    @property
    def anchors(self) -> dict:
        return {"likelihood": self.settings.anchors("likelihood"), "severity": self.settings.anchors("severity")}

    def evidence_type(self, type_id: str) -> dict | None:
        return next((t for t in self.evidence_map.get("evidence_types", []) if t["id"] == type_id), None)

    def ceiling(self) -> float:
        return self.settings.get("decision.severity_ceiling")


def load_context(ws: Workspace, first_guess_dir: Path | None = None) -> Context:
    settings = load_settings(ws.settings_file)
    path = ws.rules / "evidence_map.yaml"
    if not path.exists():
        raise EngineError(f"{path} does not exist")
    evidence_map = yaml.safe_load(path.read_text(encoding="utf-8"))
    hazards = {}
    folder = ws.rules / "hazards"
    if folder.exists():
        for hazard_path in sorted(folder.glob("*.yaml")):
            raw = yaml.safe_load(hazard_path.read_text(encoding="utf-8"))
            hazards[raw["id"]] = raw
    return Context(settings=settings, policy=Policy(ws.rules), evidence_map=evidence_map, trees=load_trees(ws.rules, first_guess_dir),
                   hazards=hazards, stop_switch=bool(settings.get("decision.stop_switch", False)))


@dataclass
class Prepared:
    case_id: str
    app: object
    record: dict
    basic: dict = field(default_factory=dict)
    stopped: bool = False
    evidence: list = field(default_factory=list)
    unmapped: list = field(default_factory=list)
    requirements: dict = field(default_factory=dict)
    spectators: int | None = None
    rule_answers: dict = field(default_factory=dict)
    applies: dict = field(default_factory=dict)
    answers: dict = field(default_factory=dict)
    contradicted: bool = False
    model_failure: bool = False
    policy_failure: bool = False
    source: str = "stored"


def _build_evidence(record: dict, app, ctx: Context) -> tuple:
    first = record.get("first_pass") or {}
    output = first.get("output") or {}
    judged = {v["evidence_type"]: v for v in ((record.get("judge") or {}).get("output") or {}).get("verdicts", [])}
    extracted = {entry["evidence_type"]: entry for entry in output.get("evidence", [])}
    records = []
    for type_id in record.get("needed_types") or sorted(extracted):
        definition = ctx.evidence_type(type_id) or {}
        entry = extracted.get(type_id)
        document = entry.get("document") if entry else None
        found = bool(entry and entry.get("status") == "found")
        fields = []
        if found:
            for item in entry.get("fields", []):
                reason = check_field(item, document, app.attachments)
                fields.append({"name": item.get("name"), "value": item.get("value"), "quote": item.get("quote"),
                               "verified": reason is None, "rejected_because": reason})
        verified = [f for f in fields if f["verified"]]
        verdict, reason = None, "no_evidence"
        if found and definition.get("whole_document"):
            verdict, reason = None, None  # Jev reads the whole plan; nothing here is judged
        elif found:
            if not verified:
                verdict, reason = "unsupported", "quote_failed"
            elif type_id in judged:
                verdict, reason = judged[type_id]["verdict"], judged[type_id].get("reason")
            else:
                verdict, reason = "unsupported", "not_judged"
        rec = {"evidence_type": type_id, "status": "found" if found else "absent", "document": document, "fields": fields,
               "verdict": verdict, "reason": reason, "source": "stored", "field_failed": False, "field_mismatch": False}
        compare_fields(rec, definition, app.form, ctx.evidence_map.get("date_formats", []))
        if rec["field_mismatch"]:
            rec["verdict"], rec["reason"] = "contradicted", rec.get("mismatch_reason") or "a field does not match the form"
        records.append(rec)
    return records, output.get("unmapped_documents", []), check_spectators(output.get("expected_spectators"), app.form)


def _evidence_probability(types, by_type, settings) -> float:
    verdicts = [by_type[t]["verdict"] for t in types if t in by_type and by_type[t]["status"] == "found"]
    if "contradicted" in verdicts:
        return settings.get("evidence.p_contradicted")
    if "supported" in verdicts:
        return settings.get("evidence.p_supported")
    return settings.get("evidence.p_unsupported")


def _answers(p: Prepared, ctx: Context) -> dict:
    by_type = {r["evidence_type"]: r for r in p.evidence}
    jev = (p.record.get("jev") or {}).get("answers") or {}
    answers = {question: 1.0 if value else 0.0 for question, value in p.rule_answers.items()}
    for tree in ctx.trees.values():
        for question in tree.questions:
            if question["kind"] == "evidence":
                answers[question["id"]] = _evidence_probability(question["evidence_types"], by_type, ctx.settings)
            elif question["kind"] == "jev" and question["id"] in jev:
                answers[question["id"]] = float(jev[question["id"]])
    return answers


def _missing_jev(p: Prepared, ctx: Context) -> bool:
    for tree in ctx.trees.values():
        if p.applies.get(tree.hazard):
            for question in tree.questions:
                if question["kind"] == "jev" and question["id"] not in p.answers:
                    return True
    return False


def prepare_many(items: list, ctx: Context) -> list:
    """`items` are (application, record). Stages 1 to 8, from stored answers. Rego failing fails closed for every case in the batch."""
    prepared = [Prepared(case_id=app.case_id, app=app, record=record, source=record.get("source", "stored")) for app, record in items]
    try:
        basics = ctx.policy.batch(BASIC, [{"form": p.app.form, "fee_paid": p.app.form.get("fee_paid")} for p in prepared])
        for p, basic in zip(prepared, basics):
            p.basic = basic
            p.stopped = bool(basic.get("failed"))
        going = [p for p in prepared if not p.stopped]
        for p in going:
            p.model_failure = any((p.record.get(part) or {}).get("status") == "failed" for part in ("first_pass", "judge", "jev"))
            p.evidence, p.unmapped, p.spectators = _build_evidence(p.record, p.app, ctx)
            p.contradicted = any(r["verdict"] == "contradicted" for r in p.evidence)
        rule_inputs = [{"form": p.app.form, "extracted": {"expected_spectators": p.spectators}} for p in going]
        requirement_inputs = [{"records": {r["evidence_type"]: {"status": r["status"], "verdict": r["verdict"], "field_failed": r["field_failed"],
                                                                "field_mismatch": r["field_mismatch"]} for r in p.evidence}} for p in going]
        rules = ctx.policy.batch(QUESTIONS, rule_inputs)
        screens = ctx.policy.batch(SCREEN, rule_inputs)
        statuses = ctx.policy.batch(REQUIREMENTS, requirement_inputs)
        for p, rule, screen, status in zip(going, rules, screens, statuses):
            p.rule_answers, p.applies, p.requirements = rule, screen, status
            p.answers = _answers(p, ctx)
            if _missing_jev(p, ctx):
                p.model_failure = True
    except PolicyError:
        for p in prepared:
            p.policy_failure = True
            p.stopped = False
            p.basic = dict(PASSING_BASIC)
    return prepared


def decision_input(p: Prepared, scored: dict, thresholds: dict, ctx: Context) -> dict:
    # A failed model leaves requirements unknown, not unclear, so the reason given is the failure.
    requirements = {} if p.model_failure else {k: v["status"] for k, v in p.requirements.items()}
    return {"basic": p.basic, "requirements": requirements, "evidence_contradicted": p.contradicted,
            "unmapped_documents": len(p.unmapped), "model_failure": p.model_failure, "policy_failure": p.policy_failure,
            "stop_switch": ctx.stop_switch, "highest_severity": scored["highest_severity"], "ceiling": ctx.ceiling(),
            "risk": scored["risk"], "t_low": thresholds["t_low"], "t_high": thresholds["t_high"]}


def decide_many(prepared: list, model, thresholds: dict, ctx: Context) -> list:
    """Stages 9 and 10. `thresholds` is one dict for all cases."""
    anchors = ctx.anchors
    scored = []
    for p in prepared:
        if p.stopped or p.policy_failure:
            scored.append({"hazards": {}, "risk": 0.0, "highest_severity": 0.0})
        else:
            scored.append(score(model, p.answers, p.applies, anchors))
    inputs = [decision_input(p, s, thresholds, ctx) for p, s in zip(prepared, scored)]
    try:
        decisions = ctx.policy.batch(DECISION, inputs)
    except PolicyError:
        decisions = [dict(FAIL_CLOSED) for _ in prepared]
    return [{"case_id": p.case_id, "scored": s, "decision": d, "input": i} for p, s, d, i in zip(prepared, scored, decisions, inputs)]


def run_case(app, record: dict, model, thresholds: dict, ctx: Context) -> dict:
    prepared = prepare_many([(app, record)], ctx)
    result = decide_many(prepared, model, thresholds, ctx)[0]
    p = prepared[0]
    result.update(basic=p.basic, evidence=p.evidence, unmapped=p.unmapped, requirements=p.requirements, spectators=p.spectators,
                  rule_answers=p.rule_answers, applies=p.applies, answers=p.answers)
    return result
