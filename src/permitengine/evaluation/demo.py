"""The story behind the demo, as in experiments/sim_demo_curve.py: start from the first guess, feed the validation cases in order,
and let an officer's corrections and re-chosen thresholds move the system. Everything goes in one log, from which the export is made.
"""
import statistics
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from .. import ARITHMETIC_VERSION
from ..hashing import content_hash
from ..learning.corrections import edge, net_update
from ..learning.train import train_model
from ..models.budget import Budget
from ..models.llm import LlmClient
from ..officer.base import Officer, Ruling
from ..officer.real import LlmOfficer
from ..officer.simulated import SimulatedOfficer
from ..pipeline.case import Context, Prepared, decide_many, load_context
from ..store.cache import Cache
from ..store.log import Log
from ..store.manifest import rules_hash, settings_hash
from ..trees.evaluate import entropy
from ..trees.loader import LEVEL_NAMES, Model, crossings_tree, first_guess
from ..workspace import EngineError, Workspace
from .common import answers_folder, choose_thresholds, mean_tree_loss, per_tree_loss, prepare_split, right_level_share, route_counts, rows_by_tree
from .labels import load_labels

START = datetime(2027, 1, 4, 9, 0, 0)
RIGHT_ROUTE = {"approved": "approve", "returned": "returned", "proposed_denial": "denial", "officer": "officer"}
AGENTIC = "agentic LLM"
MIN_LEAF_CASES = 15  # below this, a leaf's entropy is too noisy to flag a tree


def split_halves(case_ids: list) -> tuple:
    """Two fixed halves: thresholds on one, curve points on the other."""
    return case_ids[0::2], case_ids[1::2]


def needs_correction(risk: float, thresholds: dict, outcome_risky) -> bool:
    if outcome_risky is None:
        return False
    return (risk < thresholds["t_low"] and outcome_risky) or (risk >= thresholds["t_high"] and not outcome_risky)


def agrees_with_label(route: str, label: dict) -> bool:
    """A missing or unmapped insurance document is labelled a denial, and the table rightly sends it to an officer first."""
    if route == "officer" and label["right_route"] == "denial" and label["requirements"].get("event_insurance") == "missing":
        return True
    return RIGHT_ROUTE[route] == label["right_route"]


def apply_correction(model: Model, p: Prepared, outcome_risky: bool, named: list, thresholds: dict, ctx: Context) -> list:
    """`thresholds` set the network's edge between risky and not."""
    c0, k = edge(thresholds["t_low"], thresholds["t_high"])
    evidence = {item["tree_id"]: item["level"] for item in named if p.applies.get(model.trees[item["tree_id"]].hazard)}
    changes = net_update(model, p.answers, p.applies, outcome_risky, c0, k, ctx.anchors, evidence, ctx.settings.get("corrections.discount"))
    model.corrections += 1
    model.version = f"first-guess+{model.corrections}"
    return changes


def curve_point(index, seq, corrections, model, held_out: list, thresholds: dict, labels: dict, ctx: Context) -> dict:
    counts = route_counts(model, held_out, thresholds, labels, ctx)
    return {"index": index, "corrections": corrections, "seq": seq, "decided_without_officer": counts["decided_without_officer"],
            "precision": counts["precision"], "loss": mean_tree_loss(model, held_out, labels), "right_level": right_level_share(model, held_out, labels), "t_low": thresholds["t_low"],
            "t_high": thresholds["t_high"], "held_out_cases": len(held_out)}


def _hazard_names(ctx: Context) -> dict:
    return {hazard_id: raw.get("name") or hazard_id.replace("_", " ").capitalize() for hazard_id, raw in ctx.hazards.items()}


def _question_text(question: dict) -> str:
    return question.get("text") or question.get("instructions") or question["id"].replace("_", " ").capitalize() + "?"


def _tree_detail(block: dict | None, tree, answers: dict) -> dict | None:
    if block is None:
        return None
    return {"tree_id": block["tree_id"], "value": block["value"], "entropy": block["entropy"], "levels": block["levels"], "level_names": LEVEL_NAMES[tree.scale],
            "questions": [{"id": q["id"], "kind": q["kind"], "text": _question_text(q), "answer": answers.get(q["id"]), "clause": q.get("clause")} for q in tree.questions],
            "leaves": block["leaves"]}


def _hazard_why(hazard_id: str, applies: bool, ctx: Context) -> str:
    condition = ctx.hazards.get(hazard_id, {}).get("applies_when", "")
    return condition if applies else f"This does not apply here. It applies when: {condition}"


def _hazard_list(result: dict, p: Prepared, model: Model, ctx: Context) -> list:
    names = _hazard_names(ctx)
    hazards = []
    for hazard_id, scales in sorted(model.by_hazard().items()):
        block = result["scored"]["hazards"].get(hazard_id, {})
        applies = bool(block.get("applies"))
        hazards.append({"id": hazard_id, "name": names.get(hazard_id, hazard_id), "applies": applies,
                        "why": _hazard_why(hazard_id, applies, ctx),
                        "likelihood": _tree_detail(block.get("likelihood"), model.trees[scales["likelihood"]], p.answers),
                        "severity": _tree_detail(block.get("severity"), model.trees[scales["severity"]], p.answers),
                        "product": block.get("product", 0.0)})
    return hazards


def _source_word(p: Prepared) -> str:
    return "simulated" if p.source == "simulated" else "stored"


def _evidence_rows(p: Prepared) -> list:
    rows = []
    for rec in p.evidence:
        rows.append({"evidence_type": rec["evidence_type"], "status": rec["status"], "document": rec["document"],
                     "fields": [{"name": f["name"], "value": f["value"], "quote": f["quote"], "verified": f["verified"], "matches_form": f.get("matches_form")} for f in rec["fields"]],
                     "verdict": rec["verdict"], "reason": rec["reason"], "source": _source_word(p)})
    return rows


def _checks(p: Prepared) -> list:
    clauses = p.basic.get("clauses", {})
    failed = set(p.basic.get("failed", []))
    return [{"id": check, "passed": check not in failed, "clause": clauses.get(check)} for check in ("fee_paid", "form_complete", "date_allowed")]


def _requirement_rows(p: Prepared) -> list:
    return [{"id": rid, "status": row["status"], "clause": row.get("clause"), "evidence_type": row.get("evidence_type")} for rid, row in sorted(p.requirements.items())]


def _title(form: dict) -> str:
    return form.get("event_name") or f"{form.get('organizer') or 'An organizer'} race"


def _submitted(form: dict) -> str:
    runners = form.get("expected_runners")
    size = f" with {runners} runners" if runners else ""
    day = f" on {form['event_date']}" if form.get("event_date") else ""
    return f"{form.get('organizer') or 'An organizer'} applied for a race{size}{day}."


def _view(p: Prepared, result: dict, model: Model | None) -> dict:
    summary = {}
    for hazard_id, block in result["scored"]["hazards"].items():
        if block.get("applies"):
            summary[hazard_id] = {"likelihood": block["likelihood"]["value"], "severity": block["severity"]["value"], "product": block["product"]}
    return {"case_id": p.case_id, "app": p.app, "decision": result["decision"], "risk": result["scored"]["risk"], "hazard_summary": summary,
            "model": model, "answers": p.answers if model is not None else None, "applies": p.applies}


class _Clock:
    def __init__(self):
        self.now = START

    def tick(self, minutes: int = 1) -> str:
        self.now += timedelta(minutes=minutes)
        return self.now.isoformat()


def _make_officer(kind: str, ws: Workspace, ctx: Context, labels: dict, model_name: str | None) -> Officer:
    if kind == "simulated":
        return SimulatedOfficer(labels, ctx.settings.get("officer.accuracy_simulated"))
    if kind == "real":
        budget = Budget(ws.ledger / "spend.jsonl", ctx.settings.get("budget.max_usd_total"), ctx.settings.get("budget.max_jev_input_tokens"))
        return LlmOfficer(ws, LlmClient.from_env(ctx.settings, Cache(ws.cache / "answers"), budget, model_name))
    raise EngineError(f"unknown officer {kind}")


def _tree_rows(model: Model, first: Model, trained: Model, held_out: list, labels: dict, ctx: Context) -> list:
    """Counts and levels are the system's now. Entropy and the flag come from the trees trained on labelled cases, whose leaves hold enough cases."""
    minimum = MIN_LEAF_CASES
    means = {}
    for tree_id in trained.levels:
        counted = [entropy(d) for d, c in zip(trained.levels[tree_id], trained.counts[tree_id]) if sum(c) >= minimum]
        means[tree_id] = statistics.mean(counted) if counted else None
    known = [v for v in means.values() if v is not None]
    highest = max(known) if known else None
    flag = ctx.settings.get("trees.entropy_flag")
    losses = per_tree_loss(model, held_out, labels)
    rows = []
    for tree_id, tree in model.trees.items():
        leaves = [{"when": when, "count": sum(model.counts[tree_id][l]), "entropy": entropy(model.levels[tree_id][l]),
                   "levels_first": first.levels[tree_id][l], "levels_now": model.levels[tree_id][l]} for l, when in enumerate(tree.whens)]
        rows.append({"tree_id": tree_id, "mean_leaf_entropy": means[tree_id], "flagged": bool(means[tree_id] is not None and means[tree_id] == highest and means[tree_id] > flag),
                     "loss": losses[tree_id], "leaves": leaves})
    return rows


def crossings_result(ws: Workspace, ctx: Context, train: dict, validation: dict, labels: dict) -> dict:
    """Train with and without the planted question, and compare on validation. Released only if loss falls."""
    strength, iterations = ctx.settings.get("training.first_guess_strength"), ctx.settings.get("training.em_iterations")
    base = ctx.trees["traffic.likelihood"]
    try:
        grown = crossings_tree(ws.rules, base)
    except EngineError as exc:
        return {"status": "not_run", "loss_before": None, "loss_after": None, "text": str(exc)}
    plain = {"traffic.likelihood": base}
    wider = {"traffic.likelihood": grown}
    rows = rows_by_tree(train, labels, plain)
    before_model = train_model(plain, rows, strength, iterations, "before")
    after_model = train_model(wider, rows, strength, iterations, "after")
    held_out = list(validation.values())
    before = per_tree_loss(before_model, held_out, labels)["traffic.likelihood"]
    after = per_tree_loss(after_model, held_out, labels)["traffic.likelihood"]
    released = before is not None and after is not None and after < before
    verdict = "lowers" if released else "does not lower"
    text = f"Adding the question about many major crossings {verdict} validation loss on traffic likelihood, from {before:.3f} to {after:.3f}. The question was authored in advance."
    return {"status": "released" if released else "rejected", "loss_before": before, "loss_after": after, "text": text}


def run_demo(ws: Workspace, run_id: str = "demo-1", answers: str = "simulated", officer_kind: str = "simulated", model_name: str | None = None,
             first_guess_dir: Path | None = None) -> dict:
    ctx = load_context(ws, first_guess_dir)
    settings = ctx.settings
    model = first_guess(ctx.trees, settings.get("training.first_guess_strength"))
    first = model.copy()
    splits = ws.splits()
    labels = load_labels(ws)
    folder = answers_folder(ws, ctx, answers, model_name)
    train = prepare_split(ws, ctx, splits["train"], folder)
    validation = prepare_split(ws, ctx, splits["validation"], folder)
    if any(p.policy_failure for p in validation.values()):
        raise EngineError("Rego failed while preparing the cases, so every case would go to an officer. Check opa and rules/rego before the story runs.")
    half_a, half_b = split_halves(splits["train"])
    chooser = [train[c] for c in half_a]
    held_out = [train[c] for c in half_b]
    officer = _make_officer(officer_kind, ws, ctx, labels, model_name)
    simulated = answers == "simulated"
    every = settings.get("curve.rechoose_every")
    manifest_base = {"rules_hash": rules_hash(ws), "settings_hash": settings_hash(ws), "opa_version": ctx.policy.opa_version(), "rego_hash": ctx.policy.bundle_hash(),
                     "arithmetic_version": ARITHMETIC_VERSION, "answers": answers, "dataset_hash": ws.dataset_hash(),
                     "first_guess_dir": str(first_guess_dir) if first_guess_dir else None}
    log = Log(ws.runs / f"{run_id}.sqlite", run_id)
    clock = _Clock()
    thresholds = choose_thresholds(model, chooser, labels, ctx)
    curve = [curve_point(0, 1, 0, model, held_out, thresholds, labels, ctx)]
    case_rows, details, corrections_list = [], {}, []
    officer_rows = {"reviewed": 0, "agreed": 0, "corrections": 0, "levels_named": 0, "levels_right": 0}
    since_rechoose = 0

    def manifest_hash() -> str:
        return content_hash({**manifest_base, "weights": model.weights_hash(), "thresholds": thresholds})

    def rechoose(case_id, seq_parent):
        nonlocal thresholds
        thresholds = choose_thresholds(model, chooser, labels, ctx)
        index = len(curve)
        seq = log.append(case_id, "thresholds.rechosen", "system", simulated, clock.tick(), manifest_hash(),
                         f"Thresholds re-chosen after {model.corrections} officer reviews: approve under {thresholds['t_low']:.3f}, high risk from {thresholds['t_high']:.3f}.",
                         {"thresholds": thresholds, "learning_index": index}, parents=[seq_parent] if seq_parent else [])
        curve.append(curve_point(index, seq, model.corrections, model, held_out, thresholds, labels, ctx))
        return seq

    for case_id in splits["validation"]:
        p = validation[case_id]
        label = labels[case_id]
        form = p.app.form
        clock.tick(30)
        seqs = []
        result = decide_many([p], model, thresholds, ctx)[0]
        decision = result["decision"]
        scored = result["scored"]
        record_blob = None
        with log.transaction():
            record_blob = log.put_blob(p.record)
            weights_blob = log.put_blob(model.weights_json())
            manifest = {**manifest_base, "weights_version": model.version, "weights": weights_blob, "thresholds": thresholds, "record": record_blob,
                        "application": content_hash(p.app.hash_input()), "last_correction": model.corrections, "models": p.record.get("models")}
            m_hash = log.put_blob(manifest)

            def add(kind, actor, summary, payload, is_simulated=simulated):
                seq = log.append(case_id, kind, actor, is_simulated, clock.tick(), m_hash, summary, payload, parents=seqs[-1:], base_id=case_id.split("-")[0],
                                 tone=case_id.split("-", 1)[1] if "-" in case_id else None)
                seqs.append(seq)
                return seq

            first_seq = add("case.submitted", "script", _submitted(form), {"form": form}, True)
            passed = not p.basic.get("failed")
            add("checks.done", "rego", "The fee, form and date checks passed." if passed else f"Basic checks failed: {', '.join(p.basic.get('failed', []))}.", {"basic": p.basic}, False)
            if not p.stopped:
                found = sum(r["status"] == "found" for r in p.evidence)
                add("evidence.linked", AGENTIC, f"The {AGENTIC} linked documents to {found} of {len(p.evidence)} kinds of evidence it was asked for, and {len(p.unmapped)} documents fit none.",
                    {"evidence": _evidence_rows(p), "unmapped": p.unmapped, "spectators": p.spectators})
                verdicts = {}
                for r in p.evidence:
                    if r["verdict"]:
                        verdicts[r["verdict"]] = verdicts.get(r["verdict"], 0) + 1
                add("evidence.judged", AGENTIC, "Evidence judged: " + (", ".join(f"{n} {v}" for v, n in sorted(verdicts.items())) or "nothing to judge") + ".",
                    {"verdicts": {r["evidence_type"]: r["verdict"] for r in p.evidence}})
                add("requirements.checked", "rego", "Requirements: " + (", ".join(f"{k} {v['status']}" for k, v in sorted(p.requirements.items())) or "none") + ".",
                    {"requirements": p.requirements}, False)
                applying = [h for h, v in sorted(p.applies.items()) if v]
                add("hazards.screened", "rego", "Hazards that apply: " + (", ".join(h.replace("_", " ") for h in applying) or "none") + ".",
                    {"applies": p.applies, "rule_answers": p.rule_answers}, False)
                add("trees.evaluated", "jev", "Tree questions answered and the trees evaluated.", {"answers": p.answers})
                add("risk.computed", "code", f"Risk is {scored['risk']:.3f}, with highest severity {scored['highest_severity']:.2f}.",
                    {"risk": scored["risk"], "highest_severity": scored["highest_severity"], "t_low": thresholds["t_low"], "t_high": thresholds["t_high"]}, False)
            decided_seq = add("decision.made", "rego", decision.get("text", ""),
                              {"decision": decision, "input": result["input"], "risk": scored["risk"], "highest_severity": scored["highest_severity"], "thresholds": thresholds,
                               "weights_version": model.version, "manifest": m_hash}, False)
            if decision["route"] == "approved":
                add("permit.issued", "system", "Permit issued automatically.", {"after": "decision"}, False)

            ruling = Ruling(None, None, "", [])
            reviewed = decision["route"] != "returned"
            if reviewed:
                view = _view(p, result, model if not p.stopped else None)
                ruling = officer.rule(view)
                add("officer.ruled", "officer", ruling.reason, {"ruling": ruling.ruling, "outcome_risky": ruling.outcome_risky, "named": ruling.named}, True)
                officer_rows["reviewed"] += 1
                officer_rows["agreed"] += ruling.outcome_risky is not None and ruling.outcome_risky == label["risky"]
                if decision["route"] != "approved" and ruling.ruling == "approve":
                    add("permit.issued", "system", "Permit issued on the officer's ruling.", {"after": "officer"}, False)

            correction = None
            learning_index = len(curve) - 1
            if not p.stopped and ruling.outcome_risky is not None:
                # Every review teaches, not only disagreements: teaching only from cases the system got wrong skews the weights.
                # See docs/decisions/0004-how-the-demo-shows-learning.md and experiments/story_variants.py.
                disagreed = needs_correction(scored["risk"], thresholds, ruling.outcome_risky)
                for item in ruling.named:
                    truth = label["levels"].get(item["tree_id"])
                    if truth is not None:
                        officer_rows["levels_named"] += 1
                        officer_rows["levels_right"] += item["level"] == truth
                changes = apply_correction(model, p, ruling.outcome_risky, ruling.named, thresholds, ctx)
                since_rechoose += 1
                tree_ids = sorted({c["tree_id"] for c in changes})
                word = "risky" if ruling.outcome_risky else "not risky"
                bucket = "ai_wrong" if disagreed else "confirmed"
                if disagreed:
                    officer_rows["corrections"] += 1
                    correction_seq = add("correction.made", "officer", f"The officer found this case {word}, against the system's estimate.",
                                         {"bucket": bucket, "outcome_risky": ruling.outcome_risky, "named": ruling.named, "learning_index": learning_index}, True)
                    corrections_list.append({"case_id": case_id, "seq": correction_seq, "bucket": bucket, "outcome_risky": ruling.outcome_risky,
                                             "reason": ruling.reason, "tree_ids": tree_ids, "by": "simulated"})
                add("weights.updated", "code", f"The officer's review moved leaf counts on {len(tree_ids)} trees. Weights are now {model.version}.",
                    {"weights_version": model.version, "tree_ids": tree_ids}, False)
                correction = {"bucket": bucket, "outcome_risky": ruling.outcome_risky, "named": ruling.named,
                              "changes": [{k: c[k] for k in ("tree_id", "leaf", "before", "after", "count_before", "count_after")} for c in changes]}
                if since_rechoose >= every:
                    seqs.append(rechoose(case_id, seqs[-1]))
                    since_rechoose = 0

            row = {"case_id": case_id, "title": _title(form), "first_seq": first_seq, "decided_seq": decided_seq, "route": decision["route"],
                   "reason_code": decision["reason_code"], "row": decision["row"], "risk": scored["risk"], "t_low": result["input"]["t_low"], "t_high": result["input"]["t_high"],
                   "weights_version": manifest["weights_version"], "officer": decision["route"] == "officer", "corrected": correction is not None and correction["bucket"] == "ai_wrong", "label_risky": label["risky"], "label_allowed": label["allowed"],
                   "agreed_with_label": agrees_with_label(decision["route"], label)}
            case_rows.append(row)
            details[case_id] = {
                "case_id": case_id, "title": row["title"],
                "documents": {"form": form, "cover_letter": p.app.cover_letter, "attachments": [{"name": n, "text": t} for n, t in sorted(p.app.attachments.items())]},
                "checks": _checks(p), "evidence": _evidence_rows(p), "unmapped_documents": p.unmapped, "requirements": _requirement_rows(p),
                "hazards": _hazard_list(result, p, model, ctx) if not p.stopped else [],
                "risk": scored["risk"], "highest_severity": scored["highest_severity"], "t_low": row["t_low"], "t_high": row["t_high"], "ceiling": ctx.ceiling(),
                "decision": decision,
                "officer": None if not reviewed else {"label": officer.label, "ruling": ruling.ruling, "outcome_risky": ruling.outcome_risky, "reason": ruling.reason, "named": ruling.named,
                                                      "agrees_with_label": ruling.outcome_risky is not None and ruling.outcome_risky == label["risky"],
                                                      "kind": "ruling" if decision["route"] in ("officer", "proposed_denial") else "review"},
                "correction": correction,
                "manifest": {"weights_version": manifest["weights_version"], "thresholds": {"t_low": row["t_low"], "t_high": row["t_high"]}, "rules_hash": manifest_base["rules_hash"], "source": _source_word(p)},
                "events": list(seqs),
            }

    with log.transaction():
        if since_rechoose:
            rechoose(None, None)
            since_rechoose = 0
        applied = _owner_corrections(ws, model, validation, thresholds, ctx, log, clock, manifest_hash, corrections_list, details, case_rows, len(curve) - 1)
        if applied:
            rechoose(None, None)
        rows = rows_by_tree(train, labels, ctx.trees)
        trained = train_model(ctx.trees, rows, settings.get("training.first_guess_strength"), settings.get("training.em_iterations"), "trained")
        crossings = crossings_result(ws, ctx, train, validation, labels)
        if crossings["status"] == "released":
            log.append(None, "change.released", "policy_owner", True, clock.tick(), manifest_hash(), crossings["text"], {"change": "traffic.likelihood.crossings", **crossings})
        accuracy = officer_rows["agreed"] / officer_rows["reviewed"] if officer_rows["reviewed"] else None
        learning = {"curve": curve, "cards": {"first": {k: curve[0][k] for k in ("right_level", "decided_without_officer", "precision")}, "final": {k: curve[-1][k] for k in ("right_level", "decided_without_officer", "precision")}},
                    "trees": _tree_rows(model, first, trained, held_out, labels, ctx), "crossings": crossings, "corrections": corrections_list,
                    "officer": {"reviewed": officer_rows["reviewed"], "corrections": officer_rows["corrections"] + applied, "accuracy": accuracy, "label": officer.label,
                                "level_accuracy": officer_rows["levels_right"] / officer_rows["levels_named"] if officer_rows["levels_named"] else None}}
        for name, value in (("cases", case_rows), ("learning", learning), ("run", {"run_id": run_id, "source": answers, "officer_label": officer.label, "officer_accuracy": accuracy,
                                                                                    "manifest": manifest_base, "jev_model": _jev_model(validation),
                                                                                    "final_weights": model.weights_json(), "final_version": model.version})):
            log.set_named(name, value)
        for case_id, detail in details.items():
            log.set_named(f"case:{case_id}", detail)
    out = {"run_id": run_id, "log": str(log.path), "cases": len(case_rows), "events": len(log.events()), "curve": curve, "officer": learning["officer"], "crossings": crossings}
    log.close()
    return out


def _jev_model(validation: dict) -> str | None:
    for p in validation.values():
        model = (p.record.get("models") or {}).get("jev")
        if model:
            return model
    return None


def _owner_corrections(ws, model, validation, thresholds, ctx, log, clock, manifest_hash, corrections_list, details, case_rows, learning_index) -> int:
    path = ws.data / "owner_corrections.yaml"
    if not path.exists():
        return 0
    items = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    by_case = {row["case_id"]: row for row in case_rows}
    for item in items:
        case_id = item["case_id"]
        if case_id not in validation:
            raise EngineError(f"owner correction names {case_id}, which is not in the validation split")
        p = validation[case_id]
        if p.stopped:
            raise EngineError(f"owner correction names {case_id}, which stopped at the basic checks and has no trees to correct")
        named = item.get("named") or []
        changes = apply_correction(model, p, item["outcome_risky"], named, thresholds, ctx)
        tree_ids = sorted({c["tree_id"] for c in changes})
        reason = item.get("reason", "")
        seq = log.append(case_id, "correction.made", "policy_owner", False, clock.tick(), manifest_hash(), reason or "The project owner corrected this case.",
                         {"bucket": "ai_wrong", "outcome_risky": item["outcome_risky"], "named": named, "learning_index": learning_index})
        log.append(case_id, "weights.updated", "code", False, clock.tick(), manifest_hash(), f"Leaf counts moved on {len(tree_ids)} trees. Weights are now {model.version}.",
                   {"weights_version": model.version, "tree_ids": tree_ids})
        corrections_list.append({"case_id": case_id, "seq": seq, "bucket": "ai_wrong", "outcome_risky": item["outcome_risky"], "reason": reason, "tree_ids": tree_ids, "by": "project owner"})
        details[case_id]["correction"] = {"bucket": "ai_wrong", "outcome_risky": item["outcome_risky"], "named": named,
                                          "changes": [{k: c[k] for k in ("tree_id", "leaf", "before", "after", "count_before", "count_after")} for c in changes]}
        details[case_id]["events"].append(seq)
        by_case[case_id]["corrected"] = True
    return len(items)
