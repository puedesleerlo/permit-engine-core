"""The sealed test: one look per dataset hash, no bypass, the pass rule, and the comparisons beside it."""
import json

import pytest

from conftest import FIRST_GUESS
from support import ANOTHER_TESTED_MODEL, OTHER_MODEL, OTHER_VENDOR, OtherProvider, TESTED_MODEL, TESTED_SETTINGS, TESTED_VENDOR, MainProvider
from permitengine.evaluation import final as final_module
from permitengine.evaluation.baseline import run_baseline
from permitengine.evaluation.direct_jev import run_direct
from permitengine.evaluation.final import conditions, final_report, render_markdown
from permitengine.evaluation.labels import load_cards
from permitengine.evaluation.report import choose_candidate_thresholds, train_candidates, validation_report
from permitengine.evaluation.simulated_answers import SimulatedReader, simulate
from permitengine.evaluation.stats import bootstrap_difference, wilson
from permitengine.learning.release import release
from permitengine.models.budget import Budget
from permitengine.models.jev import JevClient
from permitengine.models.llm import LlmClient, LlmSpec
from permitengine.pipeline.case import load_context
from permitengine.reading.read import read_case
from permitengine.store.cache import Cache
from permitengine.store.records import records_dir, write_record
from permitengine.workspace import EngineError

MODEL = TESTED_MODEL


def real_records(world, source="real"):
    """Standing in for a real read in these tests: simulated answers marked real, in a fixture world."""
    ctx = load_context(world, FIRST_GUESS)
    reader = SimulatedReader(load_cards(world), 7)
    folder = records_dir(world, "real", MODEL)
    splits = world.splits()
    for split in ("train", "validation", "test"):
        for case_id in splits[split]:
            record = read_case(world.application(case_id), reader, ctx)
            record["source"] = source
            write_record(folder, record)


@pytest.fixture
def released(world):
    real_records(world)
    train_candidates(world, "real", None, FIRST_GUESS)
    choose_candidate_thresholds(world, "real", None, FIRST_GUESS)
    release(world, "weights", "v1")
    return world


def run_final(world, version="v1"):
    return final_report(world, version, "real", None, FIRST_GUESS)


def test_first_look_writes_the_ledger_and_both_reports(released):
    report = run_final(released)
    ledger = json.loads((released.ledger / "test_ledger.json").read_text())
    entry = ledger[released.dataset_hash()]
    assert entry["version"] == "v1" and entry["status"] == "done" and entry["verdict"] == report["verdict"]
    assert json.loads((released.reports / "final.json").read_text())["verdict"] == report["verdict"]
    assert (released.reports / "final.md").read_text() == render_markdown(report)
    assert report["verdict"] in ("pass", "fail")
    assert [c["name"] for c in report["conditions"]] == ["Lower loss than the first guess", "Lower loss than the shuffled control", "More approvals than the first guess", "Risky approvals not clearly above 5%"]
    names = [arm["name"] for arm in report["arms"]]
    assert names == ["First guess", "Trained on labelled cases", "Shuffled labels (control)", "One LLM reads and decides (baseline)", "Jev asked directly"]


def test_second_final_report_is_refused(released):
    run_final(released)
    before = (released.reports / "final.json").read_text()
    with pytest.raises(EngineError, match="runs once per dataset"):
        run_final(released)
    assert (released.reports / "final.json").read_text() == before


def test_second_final_report_is_refused_after_a_tree_change_and_a_new_version(released):
    run_final(released)
    path = released.rules / "trees" / "medical.severity.yaml"
    path.write_text(path.read_text() + "\n# changed\n")
    release(released, "weights", "v2")
    with pytest.raises(EngineError, match="runs once per dataset"):
        run_final(released, "v2")


def test_the_ledger_is_written_before_test_labels_are_opened(released, monkeypatch):
    seen = {}

    def spy(ws):
        seen["ledger"] = json.loads((ws.ledger / "test_ledger.json").read_text())
        return real(ws)

    real = final_module.load_test_labels
    monkeypatch.setattr(final_module, "load_test_labels", spy)
    run_final(released)
    assert seen["ledger"][released.dataset_hash()]["status"] == "opened"


def test_a_failing_rehearsal_leaves_the_seal_unbroken(released, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("a bug in scoring")

    opened = []
    monkeypatch.setattr(final_module, "conditions", broken)
    monkeypatch.setattr(final_module, "load_test_labels", lambda ws: opened.append(1))
    with pytest.raises(RuntimeError):
        run_final(released)
    assert not (released.ledger / "test_ledger.json").exists() and opened == []


def test_simulated_answers_cannot_spend_the_one_look(world):
    real_records(world, source="simulated")
    train_candidates(world, "real", None, FIRST_GUESS)
    choose_candidate_thresholds(world, "real", None, FIRST_GUESS)
    release(world, "weights", "v1")
    with pytest.raises(EngineError, match="must be on real answers"):
        run_final(world)
    assert not (world.ledger / "test_ledger.json").exists()


def test_a_missing_test_record_stops_before_the_ledger(released):
    folder = records_dir(released, "real", MODEL)
    (folder / f"{released.splits()['test'][0]}.json").unlink()
    with pytest.raises(EngineError, match="missing"):
        run_final(released)
    assert not (released.ledger / "test_ledger.json").exists()


def test_failure_modes_are_counted_separately_with_intervals(released):
    report = run_final(released)
    assert isinstance(report["forbidden_permits"], int) and isinstance(report["risky_approvals"], int)
    assert len(report["risky_interval"]) == 2 and len(report["forbidden_interval"]) == 2
    trained = next(a for a in report["arms"] if a["name"] == "Trained on labelled cases")
    assert "wrong_denials" in trained and "sent_to_officer" in trained
    assert "cannot confirm a 5% target" in report["limits"]


def _arms(approved_a, approved_b, risky, approved_count):
    low, high = wilson(risky, approved_count)
    routes = lambda n: {f"C{i}": "approved" if i < n else "officer" for i in range(100)}
    return {"trained": {"_routes": routes(approved_a), "interval": [low, high], "risky_approvals": risky, "approved_count": approved_count},
            "first-guess": {"_routes": routes(approved_b)}, "shuffled": {"_routes": routes(0)}}


class _P:
    def __init__(self, case_id):
        self.case_id = case_id
        self.stopped = False
        self.policy_failure = False


def test_the_pass_rule(monkeypatch):
    prepared = [_P(f"C{i}") for i in range(100)]
    monkeypatch.setattr(final_module, "_pairs_loss", lambda a, b, p, l: ([(0.5, 1.0)] * 100, list(range(100))))
    out = conditions(_arms(60, 30, 3, 60), {"trained": 0, "first-guess": 0, "shuffled": 0}, prepared, {})
    assert all(c["passed"] for c in out)
    # Clearly above 5%: the lower end of the interval is over 0.05.
    out = conditions(_arms(60, 30, 12, 60), {"trained": 0, "first-guess": 0, "shuffled": 0}, prepared, {})
    assert out[3]["passed"] is False
    # 3 risky in 30 is above 5% as a point, but not clearly, so it does not fail.
    out = conditions(_arms(60, 30, 3, 30), {"trained": 0, "first-guess": 0, "shuffled": 0}, prepared, {})
    assert out[3]["passed"] is True
    # No more approvals than the first guess.
    out = conditions(_arms(30, 30, 1, 30), {"trained": 0, "first-guess": 0, "shuffled": 0}, prepared, {})
    assert out[2]["passed"] is False
    # An interval that includes zero does not pass on loss.
    monkeypatch.setattr(final_module, "_pairs_loss", lambda a, b, p, l: ([(0.5, 1.0), (1.0, 0.5)] * 50, list(range(100))))
    out = conditions(_arms(60, 30, 3, 60), {"trained": 0, "first-guess": 0, "shuffled": 0}, prepared, {})
    assert out[0]["passed"] is False and out[1]["passed"] is False


def test_stats():
    low, high = wilson(3, 52)
    assert low == pytest.approx(0.0198, abs=0.002) and high == pytest.approx(0.156, abs=0.003)
    assert wilson(0, 0) == (None, None)
    out = bootstrap_difference([(1.0, 0.0)] * 50)
    assert out["mean"] == 1.0 and out["low"] == 1.0 and out["high"] == 1.0
    clustered = bootstrap_difference([(1.0, 0.0), (0.0, 1.0)] * 10, clusters=[i // 2 for i in range(20)])
    assert clustered["low"] == clustered["high"] == 0.0
    assert bootstrap_difference([])["mean"] is None


def _other_llm(world, answer):
    def transport(body):
        return {"model": OTHER_MODEL, "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                "choices": [{"message": {"role": "assistant", "content": json.dumps(answer)}, "finish_reason": "stop"}]}

    return LlmClient(LlmSpec(MODEL, OTHER_VENDOR, None, None), OtherProvider(transport), Cache(world.cache / "answers"), Budget(world.ledger / "spend.jsonl", 30, 100000))


def test_baseline_and_direct_jev_store_answers_and_are_reported_beside_the_arms(released):
    out = run_baseline(released, _other_llm(released, {"ruling": "approve", "reason": "Fine."}), 2)
    assert out["answered"] == 12

    def jev_transport(body):
        answers = {}
        for key, question in body["questions"].items():
            names = list(question["criteria"])
            answers[key] = {"choice": names[0], "probabilities": {names[0]: 0.7, names[1]: 0.2, names[2]: 0.1}}
        return {"model": "jev-1.14.0", "answers": answers, "usage": {"input_tokens": 10, "output_tokens": 5}}

    ctx = load_context(released, FIRST_GUESS)
    budget = Budget(released.ledger / "spend.jsonl", 30, 1000000)
    jev = JevClient("jev-1.14.0", jev_transport, Cache(released.cache / "answers"), budget)
    assert run_direct(released, ctx, jev, records_dir(released, "real", MODEL), ("test",))["answered"] == 12
    report = run_final(released)
    baseline = next(a for a in report["arms"] if a["name"].startswith("One LLM"))
    direct = next(a for a in report["arms"] if a["name"] == "Jev asked directly")
    assert baseline["status"] == "run" and baseline["on_all_cases"]["cases"] == 12 and baseline["approved"] == 1.0
    assert "on_cases_engine_decided" in baseline
    assert direct["status"] == "run" and direct["loss"] is not None and "on_cases_engine_decided" in direct


def test_comparisons_not_run_say_so(released):
    report = run_final(released)
    assert next(a for a in report["arms"] if a["name"] == "Jev asked directly")["status"] == "not_run"
    assert "(not run)" in render_markdown(report)


def test_direct_jev_never_sees_the_cover_letter(released):
    bodies = []

    def transport(body):
        bodies.append(body)
        return {"model": "jev-1.14.0", "answers": {}, "usage": {"input_tokens": 1, "output_tokens": 1}}

    ctx = load_context(released, FIRST_GUESS)
    jev = JevClient("jev-1.14.0", transport, Cache(released.cache / "answers"), Budget(released.ledger / "spend.jsonl", 30, 1000000))
    run_direct(released, ctx, jev, records_dir(released, "real", MODEL))
    assert bodies and all("COVERLETTERMARKER" not in json.dumps(b) and "mayor" not in json.dumps(b) for b in bodies)


def test_validation_report_compares_three_arms_and_touches_no_test_labels(world, monkeypatch):
    simulate(world)
    train_candidates(world, "simulated", None, FIRST_GUESS)
    monkeypatch.setattr(final_module, "load_test_labels", lambda ws: pytest.fail("test labels were read"))
    report = validation_report(world, "simulated", None, FIRST_GUESS)
    assert [a["name"] for a in report["arms"]] == ["First guess", "Trained on labelled cases", "Shuffled labels (control)"]
    assert all(a["loss"] is not None for a in report["arms"])
    assert report["arms"][1]["loss"] < report["arms"][0]["loss"]


def test_release_never_overwrites_and_records_where_it_came_from(released):
    with pytest.raises(EngineError, match="never change"):
        release(released, "weights", "v1")
    record = json.loads((released.weights / "v1" / "release.json").read_text())
    assert record["role"] == "policy_owner" and record["fitted_on"]["dataset_hash"] == released.dataset_hash()
    assert record["thresholds"]["t_low"] is not None
    with pytest.raises(EngineError, match="unknown release kind"):
        release(released, "other", "v9")
