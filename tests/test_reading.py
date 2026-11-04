"""The real readers, driven only by recorded fixtures. No test makes a call."""
import json
import threading
import time
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import COVER_MARKER, CROWD_PLAN, FIRST_GUESS, MEDICAL_PLAN, RACE_PLAN, TRAFFIC_GOOD, form, insurance, police_letter, write_case
from support import ANOTHER_TESTED_MODEL, OTHER_MODEL, OTHER_VENDOR, OtherProvider, TESTED_MODEL, TESTED_SETTINGS, TESTED_VENDOR, MainProvider
from permitengine.models.budget import Budget, BudgetExceeded
from permitengine.models.jev import JevClient
from permitengine.models.llm import LlmClient, LlmSpec
from permitengine.pipeline.case import run_case
from permitengine.reading.read import RealReader, read_case, read_many
from permitengine.store.cache import Cache
from permitengine.store.records import read_record
from permitengine.trees.loader import first_guess

RECORDED = Path(__file__).parent / "fixtures" / "recorded"
SPEC = LlmSpec(TESTED_MODEL, TESTED_VENDOR, "low", {"input": Decimal("4"), "output": Decimal("20"), "cache_read": Decimal("0.2"), "cache_write": Decimal("5")})
THRESHOLDS = {"t_low": 10.0, "t_high": 20.0}
FILES = {"insurance.txt": insurance(), "race_plan.txt": RACE_PLAN, "traffic_plan.txt": TRAFFIC_GOOD, "crowd_plan.txt": CROWD_PLAN, "medical_plan.txt": MEDICAL_PLAN}


def recorded(name):
    return json.loads((RECORDED / f"{name}.json").read_text(encoding="utf-8"))


def reply(text=None, stop_reason="end_turn"):
    usage = SimpleNamespace(input_tokens=1000, output_tokens=100, cache_read_input_tokens=0, cache_creation_input_tokens=0)
    return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)], usage=usage, model=TESTED_MODEL)


class FakeLlm:
    """Answers by which schema it was sent. Lets a test override either pass."""

    def __init__(self, first=None, judge=None):
        self.first = first or (lambda: reply(json.dumps(recorded("link_extract_good"))))
        self.judge = judge or (lambda: reply(json.dumps(recorded("judge_good"))))
        self.sent = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.sent.append(kwargs)
        properties = kwargs["output_config"]["format"]["schema"]["properties"]
        return self.judge() if "verdicts" in properties else self.first()


class FakeJev:
    def __init__(self, answer=None):
        self.answer = answer or recorded("jev_good")
        self.bodies = []

    def __call__(self, body):
        self.bodies.append(body)
        return self.answer


def reader(world, fake=None, jev=None, max_usd=30, provider=None):
    budget = Budget(world.ledger / "spend.jsonl", max_usd, 100000)
    cache = Cache(world.cache / "answers")
    fake = fake or FakeLlm()
    jev = jev or FakeJev()
    spec = SPEC if provider is None else LlmSpec(OTHER_MODEL, OTHER_VENDOR, "low", None)
    llm = LlmClient(spec, provider or MainProvider(fake), cache, budget)
    return RealReader(world, llm, JevClient("jev-1.14.0", jev, cache, budget)), fake, jev, llm


def case(world, case_id="T-one", body=None, files=None, cover=None):
    args = {} if cover is None else {"cover": cover}
    write_case(world, case_id, body or form(), files or FILES, **args)
    return world.application(case_id)


def weights(ctx):
    return first_guess(ctx.trees, 2)


def test_first_pass_reads_the_cover_letter_and_is_told_only_the_needed_types(world, ctx):
    fake_reader, fake, _, _ = reader(world)
    read_case(case(world), fake_reader, ctx)
    first = next(s for s in fake.sent if "evidence" in s["output_config"]["format"]["schema"]["properties"])
    assert COVER_MARKER in first["messages"][0]["content"]
    assert first["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "certificate_of_insurance" in first["system"][0]["text"]
    assert "on_differ" not in first["system"][0]["text"]  # how code compares is not the reader's business


def test_no_cover_letter_text_in_any_jev_or_judge_payload(world, ctx):
    fake_reader, fake, jev, _ = reader(world)
    record = read_case(case(world, cover=f"Dear officer. {COVER_MARKER} The mayor says yes."), fake_reader, ctx)
    assert record["judge"]["status"] == "ok" and record["jev"]["status"] == "ok"
    judges = [s for s in fake.sent if "verdicts" in s["output_config"]["format"]["schema"]["properties"]]
    assert judges
    for sent in judges:
        assert COVER_MARKER not in json.dumps(sent) and "mayor" not in json.dumps(sent)
    assert jev.bodies
    for body in jev.bodies:
        assert COVER_MARKER not in json.dumps(body) and "mayor" not in json.dumps(body)


def test_free_text_stays_out_of_judge_and_jev_too(world, ctx):
    body = form(description="DESCRIPTIONMARKER a 5K road race.")
    fake_reader, fake, jev, _ = reader(world)
    read_case(case(world, body=body), fake_reader, ctx)
    judge = next(s for s in fake.sent if "verdicts" in s["output_config"]["format"]["schema"]["properties"])
    assert "DESCRIPTIONMARKER" not in json.dumps(judge) and "DESCRIPTIONMARKER" not in json.dumps(jev.bodies[0])


def test_judge_is_one_call_in_a_fresh_context(world, ctx):
    fake_reader, fake, _, _ = reader(world)
    read_case(case(world), fake_reader, ctx)
    judges = [s for s in fake.sent if "verdicts" in s["output_config"]["format"]["schema"]["properties"]]
    assert len(judges) == 1 and len(judges[0]["messages"]) == 1
    assert "evidence_type" in judges[0]["messages"][0]["content"] and "quote" in judges[0]["messages"][0]["content"]
    assert RACE_PLAN not in judges[0]["messages"][0]["content"]  # verified passages, not whole documents


def test_jev_gets_one_request_with_merged_state_and_whole_plans(world, ctx):
    fake_reader, _, jev, _ = reader(world)
    record = read_case(case(world), fake_reader, ctx)
    assert len(jev.bodies) == 1
    body = jev.bodies[0]
    assert body["model"] == "jev-1.14.0"
    assert set(body["questions"]) == {"traffic_plan_adequate", "crowd_plan_adequate", "medical_plan_adequate", "narrow_venue"}
    assert all(q["type"] == "noul" for q in body["questions"].values())
    assert body["state"]["documents"]["traffic_plan"] == TRAFFIC_GOOD and body["state"]["documents"]["race_plan"] == RACE_PLAN
    assert body["state"]["application"]["route"]["road_closure"] is True
    assert body["state"]["evidence"]["certificate_of_insurance"]["verdict"] == "supported"
    assert record["jev"]["answers"]["traffic_plan_adequate"] == 0.81


def test_jev_is_asked_only_about_hazards_that_apply(world, ctx):
    body = form(expected_runners=100, route={"road_closure": False, "arterial_road": False, "major_crossings": 0})
    answers = recorded("jev_good")
    fake_reader, _, jev, _ = reader(world, jev=FakeJev(answers))
    read_case(case(world, body=body, files={"insurance.txt": insurance(), "medical_plan.txt": MEDICAL_PLAN}), fake_reader, ctx)
    assert set(jev.bodies[0]["questions"]) == {"medical_plan_adequate"}


def test_a_second_read_makes_no_calls_and_gives_the_same_record(world, ctx):
    fake_reader, fake, jev, llm = reader(world)
    app = case(world)
    first = read_case(app, fake_reader, ctx)
    calls = llm.calls, fake_reader.jev_client.calls
    second = read_case(app, fake_reader, ctx)
    assert first == second
    assert (llm.calls, fake_reader.jev_client.calls) == calls == (2, 1)


def test_basic_fail_never_calls_a_model(world, ctx):
    fake_reader, fake, jev, _ = reader(world)
    record = read_case(case(world, body=form(fee_paid=False)), fake_reader, ctx)
    assert record["stopped"] == "basic" and fake.sent == [] and jev.bodies == []


def test_first_pass_refusal_goes_to_an_officer(world, ctx):
    fake_reader, fake, jev, _ = reader(world, FakeLlm(first=lambda: reply(stop_reason="refusal")))
    app = case(world)
    record = read_case(app, fake_reader, ctx)
    assert record["first_pass"]["status"] == "failed" and record["judge"]["status"] == "skipped"
    result = run_case(app, record, weights(ctx), THRESHOLDS, ctx)
    assert (result["decision"]["route"], result["decision"]["reason_code"]) == ("officer", "model_failure")


def test_judge_refusal_goes_to_an_officer_as_a_model_failure(world, ctx):
    fake_reader, _, _, _ = reader(world, FakeLlm(judge=lambda: reply(stop_reason="refusal")))
    app = case(world)
    record = read_case(app, fake_reader, ctx)
    assert record["judge"]["status"] == "failed"
    assert run_case(app, record, weights(ctx), THRESHOLDS, ctx)["decision"]["reason_code"] == "model_failure"


def test_bad_schema_twice_goes_to_an_officer(world, ctx):
    bad = {"evidence": "not a list"}
    fake_reader, fake, _, _ = reader(world, FakeLlm(first=lambda: reply(json.dumps(bad))))
    app = case(world)
    record = read_case(app, fake_reader, ctx)
    assert record["first_pass"]["status"] == "failed" and len(fake.sent) == 2
    assert run_case(app, record, weights(ctx), THRESHOLDS, ctx)["decision"]["reason_code"] == "model_failure"


def test_a_wrong_jev_model_goes_to_an_officer(world, ctx):
    answer = {**recorded("jev_good"), "model": "jev-9"}
    fake_reader, _, _, _ = reader(world, jev=FakeJev(answer))
    app = case(world)
    record = read_case(app, fake_reader, ctx)
    assert record["jev"]["status"] == "failed"
    assert run_case(app, record, weights(ctx), THRESHOLDS, ctx)["decision"]["reason_code"] == "model_failure"


def test_an_impossible_jev_answer_is_a_failure(world, ctx):
    answer = recorded("jev_good")
    answer["answers"]["narrow_venue"] = {"noul": 3.0}
    fake_reader, _, _, _ = reader(world, jev=FakeJev(answer))
    assert read_case(case(world), fake_reader, ctx)["jev"]["status"] == "failed"


def _first_pass(evidence_changes, unmapped=()):
    body = recorded("link_extract_good")
    for row in body["evidence"]:
        if row["evidence_type"] in evidence_changes:
            row.update(evidence_changes[row["evidence_type"]])
    body["unmapped_documents"] = list(unmapped)
    return body


def _reach(world, ctx, app, first_pass, judge=None):
    fake = FakeLlm(first=lambda: reply(json.dumps(first_pass)), judge=(lambda: reply(json.dumps(judge))) if judge else None)
    fake_reader, _, _, _ = reader(world, fake)
    return run_case(app, read_case(app, fake_reader, ctx), weights(ctx), THRESHOLDS, ctx)


def test_missing_insurance_and_a_broker_letter_reach_different_rows(world, ctx):
    gone = {"certificate_of_insurance": {"status": "absent", "document": None, "fields": []}}
    files = {k: v for k, v in FILES.items() if k != "insurance.txt"}
    missing = _reach(world, ctx, case(world, "T-gone", files=files), _first_pass(gone))
    assert missing["decision"]["reason_code"] == "requirement_missing"
    broker_files = {**FILES, "insurance.txt": "Broker letter: cover is being arranged."}
    broker = _reach(world, ctx, case(world, "T-broker", files=broker_files), _first_pass(gone, [{"document": "insurance.txt", "why": "A broker's letter is not a certificate."}]))
    assert broker["decision"]["reason_code"] == "unmapped_evidence"


def test_a_letter_naming_another_date_becomes_contradicted(world, ctx):
    files = {**FILES, "police_letter.txt": police_letter("2027-06-06")}
    letter = {"police_escort_letter": {"status": "found", "document": "police_letter.txt", "fields": [{"name": "event_date", "value": "2027-06-06", "quote": "Re: Test Race, 2027-06-06"}]}}
    judge = {"verdicts": [{"evidence_type": "certificate_of_insurance", "verdict": "supported", "reason": None}, {"evidence_type": "police_escort_letter", "verdict": "supported", "reason": None}]}
    result = _reach(world, ctx, case(world, files=files), _first_pass(letter), judge)
    row = next(r for r in result["evidence"] if r["evidence_type"] == "police_escort_letter")
    assert row["verdict"] == "contradicted" and result["decision"]["reason_code"] == "red_flag"


def test_a_date_in_any_of_the_three_formats_matches_the_form(world, ctx):
    for text in ("16 May 2027", "May 16, 2027", "2027-05-16"):
        files = {**FILES, "police_letter.txt": police_letter(text)}
        letter = {"police_escort_letter": {"status": "found", "document": "police_letter.txt", "fields": [{"name": "event_date", "value": text, "quote": f"Re: Test Race, {text}"}]}}
        judge = {"verdicts": [{"evidence_type": "certificate_of_insurance", "verdict": "supported", "reason": None}, {"evidence_type": "police_escort_letter", "verdict": "supported", "reason": None}]}
        result = _reach(world, ctx, case(world, f"T-{text[:2].strip()}", files=files), _first_pass(letter), judge)
        assert next(r for r in result["evidence"] if r["evidence_type"] == "police_escort_letter")["verdict"] == "supported"


def test_expired_insurance_is_failed_not_contradicted(world, ctx):
    files = {**FILES, "insurance.txt": insurance(start="2026-01-01", end="2026-12-31")}
    fields = [{"name": "start_date", "value": "2026-01-01", "quote": "Effective: 2026-01-01"}, {"name": "end_date", "value": "2026-12-31", "quote": "Expiry: 2026-12-31"}]
    certificate = {"certificate_of_insurance": {"status": "found", "document": "insurance.txt", "fields": fields}}
    result = _reach(world, ctx, case(world, files=files), _first_pass(certificate))
    assert result["requirements"]["event_insurance"]["status"] == "failed"
    assert result["decision"]["reason_code"] == "requirement_failed"


def test_budget_stops_the_read_and_keeps_what_was_written(world, ctx):
    fake_reader, fake, _, _ = reader(world, max_usd="0.0001")
    case(world, "T-a"), case(world, "T-b")
    folder = world.cache / "records" / "real" / "m"
    out = read_many(world, ["T-a", "T-b"], fake_reader, ctx, folder, 1)
    assert fake.sent == [] and out["done"] == [] and "limit" in out["stopped_by"]


def test_no_more_than_four_jev_requests_run_at_once(world, ctx):
    running = [0]
    highest = [0]
    lock = threading.Lock()
    answer = recorded("jev_good")

    def transport(body):
        with lock:
            running[0] += 1
            highest[0] = max(highest[0], running[0])
        time.sleep(0.02)
        with lock:
            running[0] -= 1
        return answer

    ids = [f"T-{i}" for i in range(12)]
    for i, case_id in enumerate(ids):
        case(world, case_id, body=form(expected_runners=400 + i))
    fake_reader, _, _, _ = reader(world, jev=transport)
    out = read_many(world, ids, fake_reader, ctx, world.cache / "records" / "real" / "m", 4)
    assert len(out["done"]) == 12 and 1 < highest[0] <= 4


def test_other_provider_goes_through_the_same_reader_and_the_same_checks(world, ctx):
    def wrap(body):
        return {"model": OTHER_MODEL, "usage": {"prompt_tokens": 500, "completion_tokens": 50},
                "choices": [{"message": {"role": "assistant", "content": json.dumps(body)}, "finish_reason": "stop"}]}

    class Transport:
        def __init__(self):
            self.bodies = []

        def __call__(self, body):
            self.bodies.append(body)
            schema_text = body["messages"][0]["content"]
            return wrap(recorded("judge_good") if '"verdicts"' in schema_text else recorded("link_extract_good"))

    transport = Transport()
    fake_reader, _, _, llm = reader(world, provider=OtherProvider(transport))
    app = case(world)
    record = read_case(app, fake_reader, ctx)
    assert record["models"]["llm"] == OTHER_MODEL and record["first_pass"]["status"] == "ok" and record["judge"]["status"] == "ok"
    judge = next(b for b in transport.bodies if '"verdicts"' in b["messages"][0]["content"])
    assert COVER_MARKER not in json.dumps(judge)
    assert run_case(app, record, weights(ctx), THRESHOLDS, ctx)["decision"]["route"] == "approved"
    assert f"Price unknown for {OTHER_MODEL}" in llm.budget.summary()


def test_other_provider_bad_schema_twice_goes_to_an_officer(world, ctx):
    def transport(body):
        return {"model": OTHER_MODEL, "usage": {"prompt_tokens": 500, "completion_tokens": 50},
                "choices": [{"message": {"role": "assistant", "content": '{"evidence": 5}'}, "finish_reason": "stop"}]}

    fake_reader, _, _, llm = reader(world, provider=OtherProvider(transport))
    app = case(world)
    record = read_case(app, fake_reader, ctx)
    assert record["first_pass"]["status"] == "failed" and llm.calls == 2
    assert run_case(app, record, weights(ctx), THRESHOLDS, ctx)["decision"]["reason_code"] == "model_failure"


def test_keys_are_absent_from_stored_data(world, ctx, monkeypatch):
    key = "sk-ant-test-key-that-must-never-be-stored-000000"
    fake_reader, _, _, _ = reader(world)
    monkeypatch.setenv("LLM_API_KEY", key)
    folder = world.cache / "records" / "real" / "m"
    case(world)
    read_many(world, ["T-one"], fake_reader, ctx, folder, 1)
    assert read_record(folder, "T-one")["source"] == "real"
    for root in (world.cache, world.ledger):
        for path in root.rglob("*"):
            if path.is_file():
                assert key not in path.read_text(encoding="utf-8")
