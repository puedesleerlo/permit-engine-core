"""Every row of the decision table, reached through the whole pipeline from a stored record, with the real Rego."""
import copy
import pytest

from conftest import COVER_MARKER, FIRST_GUESS, RACE_PLAN, TRAFFIC_GOOD, ambulance, form, insurance, police_letter, write_case
from permitengine.config import Settings
from permitengine.pipeline.case import FAIL_CLOSED, decide_many, load_context, prepare_many, run_case
from permitengine.policy.opa import Policy, PolicyError
from permitengine.trees.loader import first_guess

APPROVE = {"t_low": 10.0, "t_high": 20.0}
BAND = {"t_low": 0.0, "t_high": 10.0}
HIGH = {"t_low": 0.0, "t_high": 0.0}
JEV = {"traffic_plan_adequate": 0.9, "crowd_plan_adequate": 0.9, "medical_plan_adequate": 0.9, "narrow_venue": 0.1}
NEEDED = ["ambulance_agreement", "certificate_of_insurance", "crowd_plan", "medical_plan", "police_escort_email", "police_escort_letter", "race_plan", "traffic_plan"]


def insurance_fields(venue="South Pier", start="2027-01-01", end="2027-12-31", organizer="Test Club"):
    return [{"name": "named_insured", "value": organizer, "quote": f"NAMED INSURED: {organizer}"}, {"name": "venue", "value": venue, "quote": f"VENUE: {venue}, Port Halden"},
            {"name": "start_date", "value": start, "quote": f"Effective: {start}"}, {"name": "end_date", "value": end, "quote": f"Expiry: {end}"}]


def entry(type_id, document=None, fields=()):
    return {"evidence_type": type_id, "status": "found" if document else "absent", "document": document, "fields": list(fields)}


def record(case_id, evidence=(), verdicts=(), unmapped=(), jev=None, **overrides):
    found = {e["evidence_type"]: e for e in evidence}
    rows = [found.get(t, entry(t)) for t in NEEDED]
    out = {"case_id": case_id, "source": "real", "models": {"llm": "fixture", "jev": "fixture"}, "needed_types": NEEDED, "stopped": None,
           "first_pass": {"status": "ok", "output": {"evidence": rows, "expected_spectators": {"value": None, "quote": None}, "unmapped_documents": list(unmapped)}},
           "judge": {"status": "ok", "output": {"verdicts": [{"evidence_type": t, "verdict": v, "reason": None} for t, v in verdicts]}},
           "jev": {"status": "ok", "answers": dict(JEV if jev is None else jev)}}
    out.update(overrides)
    return out


def good_case(world, case_id="T-good", attachments=None, body=None):
    files = {"insurance.txt": insurance(), "race_plan.txt": RACE_PLAN, "traffic_plan.txt": TRAFFIC_GOOD}
    files.update(attachments or {})
    write_case(world, case_id, body or form(), files)
    return world.application(case_id)


def good_record(case_id="T-good", **overrides):
    return record(case_id, [entry("certificate_of_insurance", "insurance.txt", insurance_fields())], [("certificate_of_insurance", "supported")], **overrides)


def weights(ctx):
    return first_guess(ctx.trees, 2)


def decide(world, ctx, app, rec, thresholds=APPROVE):
    return run_case(app, rec, weights(ctx), thresholds, ctx)


def check(result, row, route, code):
    decision = result["decision"]
    assert (decision["row"], decision["route"], decision["reason_code"]) == (row, route, code)
    assert isinstance(decision["text"], str) and decision["text"]


def test_row_0_an_incomplete_form_is_returned_and_no_model_stage_is_used(world, ctx):
    bad = form()
    del bad["venue"]
    app = good_case(world, body=bad)
    result = decide(world, ctx, app, {"case_id": "T-good", "source": "real", "stopped": "basic"})
    check(result, 0, "returned", "form_returned")
    assert result["evidence"] == [] and result["scored"]["risk"] == 0.0


def test_row_0_a_failed_basic_rule_is_a_proposed_denial(world, ctx):
    app = good_case(world, body=form(fee_paid=False))
    check(decide(world, ctx, app, {"case_id": "T-good", "source": "real", "stopped": "basic"}), 0, "proposed_denial", "basic_rule_failed")
    app = good_case(world, "T-winter", body=form(event_date="2027-01-16"))
    check(decide(world, ctx, app, {"case_id": "T-winter", "source": "real", "stopped": "basic"}), 0, "proposed_denial", "basic_rule_failed")


def test_row_1_a_letter_naming_another_date_is_contradicted_whatever_the_verdict(world, ctx):
    app = good_case(world, attachments={"police_letter.txt": police_letter("2027-06-06")})
    letter = entry("police_escort_letter", "police_letter.txt", [{"name": "event_date", "value": "2027-06-06", "quote": "I confirm a police escort for the above event on 2027-06-06."}])
    rec = record("T-good", [entry("certificate_of_insurance", "insurance.txt", insurance_fields()), letter],
                 [("certificate_of_insurance", "supported"), ("police_escort_letter", "supported")])
    result = decide(world, ctx, app, rec)
    check(result, 1, "officer", "red_flag")
    row = next(r for r in result["evidence"] if r["evidence_type"] == "police_escort_letter")
    assert row["verdict"] == "contradicted" and row["field_mismatch"] and row["fields"][0]["matches_form"] is False
    assert result["answers"]["escort_confirmed"] == ctx.settings.get("evidence.p_contradicted")


def test_row_1_named_insured_mismatch_is_contradicted_for_any_evidence_type(world, ctx):
    app = good_case(world, attachments={"insurance.txt": insurance(organizer="Another Club")})
    rec = record("T-good", [entry("certificate_of_insurance", "insurance.txt", insurance_fields(organizer="Another Club"))], [("certificate_of_insurance", "supported")])
    check(decide(world, ctx, app, rec), 1, "officer", "red_flag")


def test_row_1_requirement_unclear_when_verdict_and_fields_disagree(world, ctx):
    app = good_case(world)
    rec = record("T-good", [entry("certificate_of_insurance", "insurance.txt", insurance_fields())], [("certificate_of_insurance", "unsupported")])
    result = decide(world, ctx, app, rec)
    check(result, 1, "officer", "requirement_unclear")
    assert result["requirements"]["event_insurance"]["status"] == "unclear"


def test_row_1_unmapped_documents_never_reach_approval(world, ctx):
    app = good_case(world, attachments={"broker.txt": "A letter from a broker."})
    rec = good_record(unmapped=[{"document": "broker.txt", "why": "It fits no type."}])
    check(decide(world, ctx, app, rec, APPROVE), 1, "officer", "unmapped_evidence")


def test_row_1_refusal_goes_to_an_officer(world, ctx):
    app = good_case(world)
    for part, rec in (("first_pass", good_record(first_pass={"status": "failed", "reason": "the model refused"})),
                      ("judge", good_record(judge={"status": "failed", "reason": "the model refused"})),
                      ("jev", good_record(jev={"status": "failed", "reason": "Jev failed"}))):
        check(decide(world, ctx, app, rec, APPROVE), 1, "officer", "model_failure" if part != "first_pass" else "model_failure")


def test_row_1_a_missing_jev_answer_is_a_model_failure(world, ctx):
    app = good_case(world)
    answers = dict(JEV)
    del answers["medical_plan_adequate"]
    check(decide(world, ctx, app, good_record(jev={"status": "ok", "answers": answers}), APPROVE), 1, "officer", "model_failure")


def test_row_1_policy_failure_fails_closed(world, ctx):
    app = good_case(world)
    broken = copy.copy(ctx)
    broken.policy = Policy(world.root / "no_such_rules")
    result = run_case(app, good_record(), weights(ctx), APPROVE, broken)
    assert result["decision"] == FAIL_CLOSED
    assert result["decision"]["route"] == "officer"
    prepared = prepare_many([(app, good_record())], ctx)
    prepared[0].policy_failure = True
    check(decide_many(prepared, weights(ctx), APPROVE, ctx)[0], 1, "officer", "policy_unavailable")


def test_opa_errors_raise_rather_than_pass(world):
    policy = Policy(world.rules)
    with pytest.raises(PolicyError):
        policy.one("data.permit.no_such.thing", {"form": {}})
    with pytest.raises(PolicyError):
        Policy(world.root / "nowhere").one("data.permit.basic.result", {})
    with pytest.raises(PolicyError):
        Policy(world.rules, opa_bin="no-such-opa-binary").one("data.permit.basic.result", {})


def test_batching_keeps_order_and_is_one_process(world):
    policy = Policy(world.rules)
    inputs = [{"form": {"event_date": f"2027-{m:02d}-16", "route": {}}, "extracted": {"expected_spectators": None}} for m in (1, 6, 7, 9)]
    answers = policy.batch("data.permit.questions.answers", inputs)
    assert [a["hot_date"] for a in answers] == [False, True, True, False]


def test_row_1_stop_switch(world, ctx):
    app = good_case(world)
    stopped = copy.copy(ctx)
    stopped.stop_switch = True
    check(run_case(app, good_record(), weights(ctx), APPROVE, stopped), 1, "officer", "stop_switch")


def test_row_1_severity_ceiling(world, ctx):
    app = good_case(world)
    model = weights(ctx)
    for leaf in range(4):
        model.levels["medical.severity"][leaf] = [0.0, 0.0, 1.0]
    check(run_case(app, good_record(), model, APPROVE, ctx), 1, "officer", "severity_ceiling")


def test_row_2_expired_insurance_is_a_failed_requirement(world, ctx):
    app = good_case(world, attachments={"insurance.txt": insurance(start="2026-01-01", end="2026-12-31")})
    rec = record("T-good", [entry("certificate_of_insurance", "insurance.txt", insurance_fields(start="2026-01-01", end="2026-12-31"))], [("certificate_of_insurance", "unsupported")])
    result = decide(world, ctx, app, rec)
    check(result, 2, "proposed_denial", "requirement_failed")
    assert result["requirements"]["event_insurance"]["status"] == "failed"
    assert result["decision"]["clauses"] == ["ORD-7.1"]


def test_row_2_wrong_venue_is_a_failed_requirement(world, ctx):
    app = good_case(world, attachments={"insurance.txt": insurance(venue="Rookery Common")})
    rec = record("T-good", [entry("certificate_of_insurance", "insurance.txt", insurance_fields(venue="Rookery Common"))], [("certificate_of_insurance", "supported")])
    check(decide(world, ctx, app, rec), 2, "proposed_denial", "requirement_failed")


def test_row_3_missing_insurance_goes_to_an_officer_and_a_broker_letter_reaches_a_different_row(world, ctx):
    app = good_case(world, attachments={"insurance.txt": "Broker letter: cover is being arranged."})
    missing = record("T-good")
    broker = record("T-good", unmapped=[{"document": "insurance.txt", "why": "A broker's letter is not a certificate."}])
    check(decide(world, ctx, app, missing), 3, "officer", "requirement_missing")
    check(decide(world, ctx, app, broker), 1, "officer", "unmapped_evidence")


def test_row_4_approved_with_no_letter_even_with_open_evidence(world, ctx):
    app = good_case(world)
    result = decide(world, ctx, app, good_record(), APPROVE)
    check(result, 4, "approved", "approved")
    assert result["answers"]["escort_confirmed"] == ctx.settings.get("evidence.p_unsupported")


def test_row_5_high_risk(world, ctx):
    check(decide(world, ctx, good_case(world), good_record(), HIGH), 5, "officer", "high_risk")


def test_row_6_review_band(world, ctx):
    check(decide(world, ctx, good_case(world), good_record(), BAND), 6, "officer", "review_band")


def test_invented_quotes_count_as_absent_and_supported_verdict_does_not_save_them(world, ctx):
    app = good_case(world)
    rec = record("T-good", [entry("certificate_of_insurance", "insurance.txt", [{"name": "venue", "value": "Nowhere", "quote": "VENUE: Nowhere"}])], [("certificate_of_insurance", "supported")])
    result = decide(world, ctx, app, rec)
    row = next(r for r in result["evidence"] if r["evidence_type"] == "certificate_of_insurance")
    assert row["verdict"] == "unsupported" and row["reason"] == "quote_failed"
    assert row["fields"][0]["verified"] is False and row["fields"][0]["rejected_because"] == "quote_not_found"
    check(result, 1, "officer", "requirement_unclear")


def test_cover_letter_cannot_prove_anything(world, ctx):
    app = good_case(world, attachments={"insurance.txt": "Not a certificate."}, body=form())
    write_case(world, "T-cover", form(), {"race_plan.txt": RACE_PLAN}, cover=f"{COVER_MARKER} VENUE: South Pier, Port Halden")
    app = world.application("T-cover")
    rec = record("T-cover", [entry("certificate_of_insurance", "cover_letter.txt", [{"name": "venue", "value": "South Pier", "quote": "VENUE: South Pier, Port Halden"}])], [("certificate_of_insurance", "supported")])
    result = run_case(app, rec, weights(ctx), APPROVE, ctx)
    row = next(r for r in result["evidence"] if r["evidence_type"] == "certificate_of_insurance")
    assert row["fields"][0]["rejected_because"] == "barred_source" and row["reason"] == "quote_failed"


def test_spectators_change_the_crowd_questions_and_the_screen(world, ctx):
    body = form(expected_runners=100, description="A small race. We expect around 900 spectators at the finish.")
    write_case(world, "T-crowd", body, {"insurance.txt": insurance()})
    app = world.application("T-crowd")
    plain = record("T-crowd", [entry("certificate_of_insurance", "insurance.txt", insurance_fields())], [("certificate_of_insurance", "supported")])
    assert run_case(app, plain, weights(ctx), APPROVE, ctx)["rule_answers"]["crowd_over_800"] is False
    assert run_case(app, plain, weights(ctx), APPROVE, ctx)["applies"]["crowd_pressure"] is False
    plain["first_pass"]["output"]["expected_spectators"] = {"value": 900, "quote": "We expect around 900 spectators at the finish."}
    result = run_case(app, plain, weights(ctx), APPROVE, ctx)
    assert result["spectators"] == 900 and result["rule_answers"]["crowd_over_800"] is True and result["applies"]["crowd_pressure"] is True


def test_the_pipeline_is_a_pure_function_of_its_inputs(world, ctx):
    app = good_case(world)
    first = decide(world, ctx, app, good_record(), BAND)
    second = decide(world, ctx, app, good_record(), BAND)
    assert first["decision"] == second["decision"] and first["scored"] == second["scored"] and first["input"] == second["input"]


def test_settings_limits_and_allowed_values_stop_the_run(world):
    from permitengine.config import load_settings
    from permitengine.workspace import EngineError

    text = world.settings_file.read_text(encoding="utf-8")
    world.settings_file.write_text(text.replace("key: decision.severity_ceiling\n  value: 0.85", "key: decision.severity_ceiling\n  value: 3"), encoding="utf-8")
    with pytest.raises(EngineError):
        load_settings(world.settings_file)
    world.settings_file.write_text(text.replace("value: jev-1.14.0", "value: jev-9"), encoding="utf-8")
    with pytest.raises(EngineError):
        load_settings(world.settings_file)
