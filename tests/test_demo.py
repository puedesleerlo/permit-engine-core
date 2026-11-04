"""The story, on the small world with simulated answers and the temporary first guess."""
import json
from decimal import Decimal
from types import SimpleNamespace

import pytest
import yaml

from conftest import FIRST_GUESS
from support import ANOTHER_TESTED_MODEL, OTHER_MODEL, OTHER_VENDOR, OtherProvider, TESTED_MODEL, TESTED_SETTINGS, TESTED_VENDOR, MainProvider
from permitengine.evaluation.demo import agrees_with_label, needs_correction, run_demo, split_halves
from permitengine.evaluation.simulated_answers import simulate
from permitengine.models.budget import Budget
from permitengine.models.llm import LlmClient, LlmSpec
from permitengine.officer.real import LABEL as LLM_LABEL, LlmOfficer
from permitengine.officer.simulated import LABEL as RULES_LABEL, SimulatedOfficer
from permitengine.store.cache import Cache
from permitengine.store.log import Log
from permitengine.workspace import EngineError


@pytest.fixture
def story(world):
    simulate(world)
    return run_demo(world, "r1", first_guess_dir=FIRST_GUESS)


def test_simulated_records_are_marked_and_the_test_split_is_left_out(world):
    out = simulate(world)
    folder = world.cache / "records" / "simulated"
    assert out["written"] == 54
    for case_id in world.splits()["validation"][:3]:
        assert json.loads((folder / f"{case_id}.json").read_text())["source"] == "simulated"
    assert not (folder / f"{world.splits()['test'][0]}.json").exists()


def test_every_validation_case_is_fed_in_order_and_no_test_case_is(world, story):
    log = Log(world.runs / "r1.sqlite", "r1", create=False)
    submitted = [e["case_id"] for e in log.events("case.submitted")]
    assert submitted == world.splits()["validation"]
    assert not set(e["case_id"] for e in log.events()) & set(world.splits()["test"])


def test_the_curve_starts_at_zero_corrections_and_thresholds_move_with_it(world, story):
    curve = story["curve"]
    assert curve[0]["corrections"] == 0 and curve[0]["index"] == 0
    assert [p["index"] for p in curve] == list(range(len(curve)))
    assert all(p["held_out_cases"] == 15 for p in curve)
    assert [p["corrections"] for p in curve] == sorted(p["corrections"] for p in curve)
    log = Log(world.runs / "r1.sqlite", "r1", create=False)
    rechosen = log.events("thresholds.rechosen")
    assert [e["payload"]["learning_index"] for e in rechosen] == list(range(1, len(curve)))
    for event in log.events("correction.made"):
        assert 0 <= event["payload"]["learning_index"] < len(curve)


def test_decided_without_officer_counts_approved_and_returned_on_the_held_out_half(world, story):
    log = Log(world.runs / "r1.sqlite", "r1", create=False)
    assert 0 <= story["curve"][0]["decided_without_officer"] <= 1
    train = world.splits()["train"]
    a, b = split_halves(train)
    assert len(a) == len(b) == 15 and not set(a) & set(b)
    assert not {e["case_id"] for e in log.events("decision.made")} & set(train)


def test_corrections_are_ai_wrong_and_show_their_changes(world, story):
    log = Log(world.runs / "r1.sqlite", "r1", create=False)
    corrections = log.events("correction.made")
    assert corrections, "this fixture is built to give corrections"
    learning = log.named("learning")
    assert learning["officer"]["corrections"] == len(corrections) == len(learning["corrections"])
    for event in corrections:
        assert event["payload"]["bucket"] == "ai_wrong"
        detail = log.named(f"case:{event['case_id']}")
        assert detail["correction"]["changes"]
        for change in detail["correction"]["changes"]:
            assert sum(change["after"]) == pytest.approx(1.0)
    assert log.named("cases")[-1]["weights_version"].startswith("first-guess")


def test_the_weights_version_counts_every_review_that_taught(world, story):
    log = Log(world.runs / "r1.sqlite", "r1", create=False)
    versions = [row["weights_version"] for row in log.named("cases")]
    assert versions[0] == "first-guess"
    taught = [e for e in log.events() if e["type"] == "weights.updated"]
    assert log.named("run")["final_version"] == f"first-guess+{len(taught)}"


def test_every_review_teaches_and_not_only_disagreements(world, story):
    log = Log(world.runs / "r1.sqlite", "r1", create=False)
    taught = [e for e in log.events() if e["type"] == "weights.updated"]
    corrected = [e for e in log.events() if e["type"] == "correction.made"]
    assert len(taught) > len(corrected)
    buckets = {log.named(f"case:{e['case_id']}")["correction"]["bucket"] for e in taught}
    assert "confirmed" in buckets


def test_officer_accuracy_is_measured_against_labels(world, story):
    assert 0 <= story["officer"]["accuracy"] <= 1
    assert story["officer"]["label"] == RULES_LABEL
    assert "LLM following" not in RULES_LABEL or "standing in" in RULES_LABEL


def test_a_run_is_not_overwritten(world, story):
    with pytest.raises(EngineError):
        run_demo(world, "r1", first_guess_dir=FIRST_GUESS)


def test_no_first_guess_gives_a_clear_message_only_when_weights_are_needed(world):
    for path in (world.rules / "trees").glob("*.yaml"):
        raw = yaml.safe_load(path.read_text())
        raw["leaves"] = []
        path.write_text(yaml.safe_dump(raw))
    assert simulate(world)["written"] == 54  # reading needs no weights
    with pytest.raises(EngineError, match="first-guess leaves"):
        run_demo(world, "r2")


def test_owner_corrections_are_applied_in_order_at_the_end(world):
    simulate(world)
    case_ids = world.splits()["validation"][:2]
    (world.data / "owner_corrections.yaml").write_text(yaml.safe_dump([
        {"case_id": case_ids[0], "outcome_risky": True, "reason": "First owner correction.", "named": [{"tree_id": "medical.severity", "level": 2}]},
        {"case_id": case_ids[1], "outcome_risky": False, "reason": "Second owner correction."}]))
    out = run_demo(world, "owner", first_guess_dir=FIRST_GUESS)
    log = Log(world.runs / "owner.sqlite", "owner", create=False)
    learning = log.named("learning")
    owners = [c for c in learning["corrections"] if c["by"] == "project owner"]
    assert [c["case_id"] for c in owners] == case_ids
    assert owners[0]["reason"] == "First owner correction."
    events = [e for e in log.events("correction.made") if e["actor"] == "policy_owner"]
    assert [e["case_id"] for e in events] == case_ids and all(not e["simulated"] for e in events)
    assert events[0]["seq"] > max(e["seq"] for e in log.events("decision.made"))
    assert log.named(f"case:{case_ids[0]}")["correction"]["named"][0]["tree_id"] == "medical.severity"
    assert out["curve"][-1]["corrections"] >= 2


def test_an_owner_correction_of_a_stopped_or_unknown_case_stops(world):
    simulate(world)
    (world.data / "owner_corrections.yaml").write_text(yaml.safe_dump([{"case_id": "R9999-plain", "outcome_risky": True}]))
    with pytest.raises(EngineError):
        run_demo(world, "bad", first_guess_dir=FIRST_GUESS)


def test_correction_rule_is_the_simulations():
    thresholds = {"t_low": 0.1, "t_high": 0.2}
    assert needs_correction(0.05, thresholds, True)
    assert not needs_correction(0.05, thresholds, False)
    assert needs_correction(0.25, thresholds, False)
    assert not needs_correction(0.25, thresholds, True)
    assert not needs_correction(0.15, thresholds, True) and not needs_correction(0.15, thresholds, False)
    assert not needs_correction(0.05, thresholds, None)


def test_missing_insurance_sent_to_an_officer_is_not_a_wrong_route():
    denial = {"right_route": "denial", "requirements": {"event_insurance": "missing"}}
    assert agrees_with_label("officer", denial)
    assert not agrees_with_label("officer", {"right_route": "denial", "requirements": {"event_insurance": "failed"}})
    assert agrees_with_label("proposed_denial", {"right_route": "denial", "requirements": {"event_insurance": "failed"}})
    assert not agrees_with_label("approved", denial)


def test_the_simulated_officer_is_reproducible_and_hits_its_accuracy():
    labels = {f"C{i}": {"risky": i % 2 == 0, "allowed": True, "levels": {}} for i in range(1000)}
    officer = SimulatedOfficer(labels, 0.9)
    rulings = {c: officer.rule({"case_id": c}) for c in labels}
    again = {c: officer.rule({"case_id": c}) for c in labels}
    assert {c: r.outcome_risky for c, r in rulings.items()} == {c: r.outcome_risky for c, r in again.items()}
    accuracy = sum(r.outcome_risky == labels[c]["risky"] for c, r in rulings.items()) / 1000
    assert 0.87 < accuracy < 0.93
    assert all(r.ruling == ("deny" if r.outcome_risky else "approve") for r in rulings.values())


def _llm_officer(world, text=None, stop_reason="end_turn"):
    text = text or json.dumps({"ruling": "deny", "outcome_risky": True, "reason": "The escort is not confirmed.", "named": [{"tree_id": "traffic.likelihood", "level": 2}]})
    usage = SimpleNamespace(input_tokens=1000, output_tokens=100, cache_read_input_tokens=0, cache_creation_input_tokens=0)
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)], usage=usage, model=TESTED_MODEL)

    spec = LlmSpec(TESTED_MODEL, TESTED_VENDOR, "low", {"input": Decimal("4"), "output": Decimal("20"), "cache_read": Decimal("0.2"), "cache_write": Decimal("5")})
    budget = Budget(world.ledger / "spend.jsonl", 30, 1000)
    llm = LlmClient(spec, MainProvider(SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))), Cache(world.cache / "answers"), budget)
    return LlmOfficer(world, llm), calls, llm


def _view(world):
    case_id = world.splits()["validation"][0]
    model = SimpleNamespace(trees={"traffic.likelihood": SimpleNamespace(hazard="traffic_conflict"), "crowd.likelihood": SimpleNamespace(hazard="crowd_pressure")})
    return {"case_id": case_id, "app": world.application(case_id), "decision": {"row": 6, "route": "officer"}, "risk": 0.1, "hazard_summary": {},
            "model": model, "applies": {"traffic_conflict": True, "crowd_pressure": False}}


def test_the_llm_officer_reads_the_rubric_documents_and_decision_and_is_metered_and_cached(world):
    officer, calls, llm = _llm_officer(world)
    ruling = officer.rule(_view(world))
    assert officer.label == LLM_LABEL == "Simulated officer: an LLM following the expert rubric"
    assert ruling.ruling == "deny" and ruling.outcome_risky is True and ruling.named == [{"tree_id": "traffic.likelihood", "level": 2}]
    sent = calls[0]
    assert "RUBRICMARKER" in sent["system"][0]["text"]
    user = sent["messages"][0]["content"]
    assert "system_decision" in user and "COVERLETTERMARKER" in user and "insurance.txt" in user
    officer.rule(_view(world))
    assert llm.calls == 1
    assert llm.budget.spent_usd > 0


def test_a_failed_llm_officer_gives_no_ruling_and_no_correction(world):
    officer, _, _ = _llm_officer(world, stop_reason="refusal")
    ruling = officer.rule(_view(world))
    assert ruling.ruling is None and ruling.outcome_risky is None
    assert not needs_correction(0.0, {"t_low": 0.1, "t_high": 0.2}, ruling.outcome_risky)
