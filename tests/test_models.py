import json
import stat
import sqlite3
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest

from support import ANOTHER_TESTED_MODEL, OTHER_MODEL, OTHER_VENDOR, OtherProvider, TESTED_MODEL, TESTED_SETTINGS, TESTED_VENDOR, MainProvider
from permitengine.config import Settings
from permitengine.models.budget import Budget, BudgetExceeded
from permitengine.models.jev import JevClient, JevFailure
from permitengine.models.llm import (LlmClient, LlmSpec, ModelFailure, ProviderError, choose_model, provider_name,
                                     spec_from_settings)
from permitengine.export.make import DENY_WORDS, scan_text
from permitengine.store.cache import Cache
from permitengine.workspace import EngineError

FIXTURES = Path(__file__).parent / "fixtures"
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["ruling"], "properties": {"ruling": {"type": "string", "enum": ["approve", "deny"]}}}
TESTED = LlmSpec(TESTED_MODEL, TESTED_VENDOR, "low", {"input": Decimal("4"), "output": Decimal("20"), "cache_read": Decimal("0.2"), "cache_write": Decimal("5")})
OTHER_UNKNOWN = LlmSpec(OTHER_MODEL, OTHER_VENDOR, "low", None)
OTHER_PRICED = LlmSpec(OTHER_MODEL, OTHER_VENDOR, None, {"input": Decimal("1"), "output": Decimal("2"), "cache_read": Decimal("0.1"), "cache_write": Decimal("0")})
FAKE_TESTED_KEY = "sk-ant-fixture-not-a-real-key-000000000000"
FAKE_OTHER_KEY = "sk-moon-fixture-not-a-real-key-000000000"


def other_reply(name):
    return json.loads((FIXTURES / OTHER_VENDOR / f"{name}.json").read_text(encoding="utf-8"))


class FakeTransport:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.bodies = []

    def __call__(self, body):
        self.bodies.append(body)
        return self.replies.pop(0)


def llm_reply(text='{"ruling":"approve"}', stop_reason="end_turn"):
    usage = SimpleNamespace(input_tokens=1000, output_tokens=100, cache_read_input_tokens=50, cache_creation_input_tokens=10)
    content = [SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)]
    return SimpleNamespace(stop_reason=stop_reason, content=content, usage=usage, model=TESTED_MODEL)


class FakeLlm:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.sent = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.sent.append(kwargs)
        return self.replies.pop(0)


def client(tmp_path, spec, provider, max_usd=30):
    return LlmClient(spec, provider, Cache(tmp_path / "cache"), Budget(tmp_path / "spend.jsonl", max_usd, 1000))


def test_the_tested_provider_sends_the_schema_and_a_cache_marker_and_no_fallback(tmp_path):
    fake = FakeLlm(llm_reply())
    llm = client(tmp_path, TESTED, MainProvider(fake))
    assert llm.structured("k", "system", "user", SCHEMA, "c1") == {"ruling": "approve"}
    sent = fake.sent[0]
    assert sent["output_config"]["format"]["schema"] == SCHEMA
    assert sent["output_config"]["effort"] == "low"
    assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "fallbacks" not in sent


def test_a_second_read_makes_no_calls(tmp_path):
    fake = FakeLlm(llm_reply())
    llm = client(tmp_path, TESTED, MainProvider(fake))
    llm.structured("k", "system", "user", SCHEMA, "c1")
    assert llm.structured("k", "system", "user", SCHEMA, "c1") == {"ruling": "approve"}
    assert llm.calls == 1


def test_a_refusal_is_a_model_failure_and_is_not_retried(tmp_path):
    fake = FakeLlm(llm_reply(stop_reason="refusal"))
    llm = client(tmp_path, TESTED, MainProvider(fake))
    with pytest.raises(ModelFailure):
        llm.structured("k", "system", "user", SCHEMA, "c1")
    assert llm.calls == 1


def test_a_bad_answer_gets_one_retry_then_fails(tmp_path):
    fake = FakeLlm(llm_reply('{"ruling":"maybe"}'), llm_reply("not json"))
    llm = client(tmp_path, TESTED, MainProvider(fake))
    with pytest.raises(ModelFailure):
        llm.structured("k", "system", "user", SCHEMA, "c1")
    assert llm.calls == 2


def test_a_cut_off_answer_gets_one_retry(tmp_path):
    fake = FakeLlm(llm_reply(stop_reason="max_tokens"), llm_reply())
    llm = client(tmp_path, TESTED, MainProvider(fake))
    assert llm.structured("k", "system", "user", SCHEMA, "c1") == {"ruling": "approve"}


def test_an_sdk_error_keeps_its_message_out(tmp_path):
    class Exploding:
        beta = SimpleNamespace(messages=SimpleNamespace(create=lambda **_: (_ for _ in ()).throw(RuntimeError(f"quotes {FAKE_TESTED_KEY}"))))

    provider = MainProvider(Exploding())
    with pytest.raises(ProviderError) as caught:
        provider.send(TESTED, "s", "u", SCHEMA)
    assert FAKE_TESTED_KEY not in str(caught.value)


def test_budget_stops_a_call_before_it_is_made(tmp_path):
    fake = FakeLlm(llm_reply())
    llm = client(tmp_path, TESTED, MainProvider(fake), max_usd="0.0001")
    with pytest.raises(BudgetExceeded):
        llm.structured("k", "system", "user", SCHEMA, "c1")
    assert fake.sent == [] and llm.calls == 0


def test_the_meter_persists_across_processes(tmp_path):
    path = tmp_path / "spend.jsonl"
    first = Budget(path, 30, 1000)
    first.settle(usd="29.5", kind="k", case_id="c", model="m")
    first.settle(jev_tokens=900, kind="j", case_id="c", model="jev")
    second = Budget(path, 30, 1000)
    assert second.spent_usd == Decimal("29.5")
    assert second.jev_tokens == 900
    with pytest.raises(BudgetExceeded):
        second.reserve(usd="0.6")
    with pytest.raises(BudgetExceeded):
        second.reserve(jev_tokens=101)
    second.reserve(usd="0.4", jev_tokens=100)


def test_concurrent_reservations_cannot_pass_the_limit_together(tmp_path):
    budget = Budget(tmp_path / "s.jsonl", 1, 1000)
    budget.reserve(usd="0.7")
    with pytest.raises(BudgetExceeded):
        budget.reserve(usd="0.4")
    budget.settle(reserved_usd="0.7", usd="0.1", kind="k", case_id="c", model="m")
    budget.reserve(usd="0.4")


# The other provider


def test_other_provider_validates_and_returns_an_answer(tmp_path):
    transport = FakeTransport(other_reply("good"))
    llm = client(tmp_path, OTHER_UNKNOWN, OtherProvider(transport))
    assert llm.structured("k", "system", "user", SCHEMA, "c1") == {"ruling": "approve"}
    body = transport.bodies[0]
    assert body["model"] == OTHER_MODEL
    assert body["max_completion_tokens"] == 16000
    assert body["reasoning_effort"] == "low"
    assert body["response_format"] == {"type": "json_object"}
    assert json.dumps(SCHEMA, sort_keys=True) in body["messages"][0]["content"]
    assert body["messages"][1] == {"role": "user", "content": "user"}


def test_other_provider_gets_one_retry_on_a_bad_response_then_model_failure(tmp_path):
    transport = FakeTransport(other_reply("wrong_schema"), other_reply("not_json"))
    llm = client(tmp_path, OTHER_UNKNOWN, OtherProvider(transport))
    with pytest.raises(ModelFailure):
        llm.structured("k", "system", "user", SCHEMA, "c1")
    assert len(transport.bodies) == 2


def test_other_provider_recovers_on_the_retry(tmp_path):
    transport = FakeTransport(other_reply("wrong_schema"), other_reply("good"))
    llm = client(tmp_path, OTHER_UNKNOWN, OtherProvider(transport))
    assert llm.structured("k", "system", "user", SCHEMA, "c1") == {"ruling": "approve"}


def test_other_provider_refusal_and_content_filter_are_model_failures(tmp_path):
    for name in ("refusal", "content_filter"):
        transport = FakeTransport(other_reply(name))
        llm = client(tmp_path / name, OTHER_UNKNOWN, OtherProvider(transport))
        with pytest.raises(ModelFailure):
            llm.structured("k", "system", "user", SCHEMA, "c1")
        assert len(transport.bodies) == 1


def test_other_provider_cut_off_gets_one_retry(tmp_path):
    transport = FakeTransport(other_reply("cut_off"), other_reply("good"))
    llm = client(tmp_path, OTHER_UNKNOWN, OtherProvider(transport))
    assert llm.structured("k", "system", "user", SCHEMA, "c1") == {"ruling": "approve"}


def test_a_reply_with_no_usage_is_an_error_not_free(tmp_path):
    reply = other_reply("good")
    del reply["usage"]
    with pytest.raises(ProviderError):
        OtherProvider(FakeTransport(reply)).send(OTHER_UNKNOWN, "s", "u", SCHEMA)


def test_unknown_price_records_tokens_and_says_so_and_guesses_nothing(tmp_path):
    llm = client(tmp_path, OTHER_UNKNOWN, OtherProvider(FakeTransport(other_reply("good"))))
    llm.structured("k", "system", "user", SCHEMA, "c1")
    entry = json.loads((tmp_path / "spend.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert entry["price"] == "unknown" and entry["usd"] is None
    assert entry["input_tokens"] == 900 and entry["cache_read_tokens"] == 100 and entry["output_tokens"] == 40
    assert llm.budget.spent_usd == 0
    assert f"Price unknown for {OTHER_MODEL}" in llm.budget.summary()
    reread = Budget(tmp_path / "spend.jsonl", 30, 1000)
    assert reread.unpriced[OTHER_MODEL] == {"input_tokens": 1000, "output_tokens": 40, "calls": 1}
    assert reread.spent_usd == 0


def test_a_known_other_provider_price_counts_toward_the_same_limit(tmp_path):
    path = tmp_path / "spend.jsonl"
    Budget(path, 30, 1000).settle(usd="29.99999", kind="k", case_id="c", model=TESTED_MODEL)
    budget = Budget(path, 30, 1000)
    transport = FakeTransport(other_reply("good"))
    llm = LlmClient(OTHER_PRICED, OtherProvider(transport), Cache(tmp_path / "cache"), budget)
    with pytest.raises(BudgetExceeded):
        llm.structured("k", "system", "x" * 90000, SCHEMA, "c1")
    assert transport.bodies == []


def test_other_provider_cost_uses_cached_tokens_once(tmp_path):
    llm = client(tmp_path, OTHER_PRICED, OtherProvider(FakeTransport(other_reply("good"))))
    llm.structured("k", "system", "user", SCHEMA, "c1")
    assert llm.budget.spent_usd == (Decimal(900) * 1 + Decimal(40) * 2 + Decimal(100) * Decimal("0.1")) / 1_000_000


def test_answers_from_different_providers_do_not_mix(tmp_path):
    cache = Cache(tmp_path / "cache")
    budget = Budget(tmp_path / "spend.jsonl", 30, 1000)
    fake = FakeLlm(llm_reply('{"ruling":"approve"}'))
    reply = other_reply("good")
    reply["choices"][0]["message"]["content"] = '{"ruling":"deny"}'
    main_llm = LlmClient(TESTED, MainProvider(fake), cache, budget)
    other_llm = LlmClient(OTHER_UNKNOWN, OtherProvider(FakeTransport(reply)), cache, budget)
    assert main_llm.structured("k", "s", "u", SCHEMA, "c") == {"ruling": "approve"}
    assert other_llm.structured("k", "s", "u", SCHEMA, "c") == {"ruling": "deny"}
    assert main_llm.calls == 1 and other_llm.calls == 1


def _settings(**values):
    return Settings({k: {"key": k, "value": v} for k, v in values.items()})


def test_the_flag_then_settings_select_the_provider():
    settings = _settings(**{f"models.{TESTED_SETTINGS}.id": TESTED_MODEL, f"models.{TESTED_SETTINGS}.effort": "low", f"prices.{TESTED_SETTINGS}.input_usd_per_million": 4, f"prices.{TESTED_SETTINGS}.output_usd_per_million": 20, f"prices.{OTHER_MODEL}.input_usd_per_million": None, f"prices.{OTHER_MODEL}.output_usd_per_million": None})
    assert choose_model(settings) == TESTED_MODEL
    assert choose_model(settings, OTHER_MODEL) == OTHER_MODEL
    assert provider_name(OTHER_MODEL) == OTHER_VENDOR and provider_name(TESTED_MODEL) == TESTED_VENDOR
    with pytest.raises(EngineError):
        provider_name("gpt-5")
    spec = spec_from_settings(settings, OTHER_MODEL)
    assert spec.provider == OTHER_VENDOR and spec.prices is None
    assert spec_from_settings(settings).prices["input"] == Decimal("4")
    wider = _settings(**{"models.llm.id": OTHER_MODEL, f"models.{TESTED_SETTINGS}.id": TESTED_MODEL})
    assert choose_model(wider) == OTHER_MODEL


def test_a_priced_provider_with_no_price_stops_rather_than_running_unmetered():
    settings = _settings(**{f"models.{TESTED_SETTINGS}.id": TESTED_MODEL, f"prices.{TESTED_SETTINGS}.input_usd_per_million": 4, f"prices.{TESTED_SETTINGS}.output_usd_per_million": 20})
    with pytest.raises(EngineError):
        spec_from_settings(_settings(**{f"models.{TESTED_SETTINGS}.id": TESTED_MODEL}))
    # The rates of the configured model are never borrowed by another one.
    with pytest.raises(EngineError):
        spec_from_settings(settings, ANOTHER_TESTED_MODEL)


def test_without_cache_rates_the_meter_can_only_overstate():
    settings = _settings(**{f"models.{TESTED_SETTINGS}.id": TESTED_MODEL, f"prices.{TESTED_SETTINGS}.input_usd_per_million": 4, f"prices.{TESTED_SETTINGS}.output_usd_per_million": 20})
    prices = spec_from_settings(settings).prices
    assert prices["cache_read"] == Decimal("4") and prices["cache_write"] == Decimal("5")


def test_other_provider_prices_in_settings_are_used_when_given():
    settings = _settings(**{f"models.{TESTED_SETTINGS}.id": TESTED_MODEL, f"prices.{OTHER_MODEL}.input_usd_per_million": 1, f"prices.{OTHER_MODEL}.output_usd_per_million": 2})
    assert spec_from_settings(settings, OTHER_MODEL).prices["output"] == Decimal("2")


def test_keys_come_from_the_environment_and_a_missing_key_stops(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(EngineError):
        OtherProvider.from_env()
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(EngineError):
        MainProvider.from_env()


def test_keys_are_absent_from_stored_data(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", FAKE_OTHER_KEY)
    provider = OtherProvider.from_env()
    real_transport = provider.transport
    assert real_transport is not None
    provider.transport = FakeTransport(other_reply("good"))
    llm = client(tmp_path, OTHER_UNKNOWN, provider)
    llm.structured("k", "system", "user", SCHEMA, "c1")
    jev = JevClient("jev-1", FakeTransport({"model": "jev-1", "answers": {"q": {"noul": 0.5}}, "usage": {"input_tokens": 3, "output_tokens": 1}}), Cache(tmp_path / "cache"), llm.budget)
    jev.ask("jev", {"a": 1}, {"q": {"type": "noul", "instructions": "x"}}, "c1")
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert FAKE_OTHER_KEY not in path.read_text(encoding="utf-8")


def test_the_deny_list_covers_both_providers():
    for word in (TESTED_VENDOR, OTHER_VENDOR):
        assert word in DENY_WORDS
    for text in (f"answered by {OTHER_MODEL}", OTHER_VENDOR.title(), TESTED_MODEL, OTHER_MODEL.upper()):
        assert scan_text(text)
    assert not scan_text("an agentic LLM read this. Octopus Running Club.")


# Jev


def jev_client(tmp_path, *replies, model="jev-1.14.0"):
    transport = FakeTransport(*replies)
    return JevClient(model, transport, Cache(tmp_path / "cache"), Budget(tmp_path / "spend.jsonl", 30, 1000), 8), transport


def test_jev_wrong_returned_model_is_a_failure(tmp_path):
    jev, _ = jev_client(tmp_path, {"model": "jev-2", "answers": {}, "usage": {"input_tokens": 1}})
    with pytest.raises(JevFailure):
        jev.ask("jev", {"a": 1}, {"q": {"type": "noul", "instructions": "x"}}, "c")


def test_jev_second_ask_makes_no_call_and_concurrency_is_capped(tmp_path):
    reply = {"model": "jev-1.14.0", "answers": {"q": {"noul": 0.7}}, "usage": {"input_tokens": 5, "output_tokens": 1}}
    jev, transport = jev_client(tmp_path, reply)
    assert jev.max_concurrency == 4
    questions = {"q": {"type": "noul", "instructions": "x"}}
    first = jev.ask("jev", {"a": 1}, questions, "c")
    second = jev.ask("jev", {"a": 1}, questions, "c")
    assert first["answers"] == second["answers"]
    assert len(transport.bodies) == 1


def test_jev_token_limit_stops_a_call(tmp_path):
    jev, transport = jev_client(tmp_path)
    with pytest.raises(BudgetExceeded):
        jev.ask("jev", {"a": "x" * 10000}, {"q": {"type": "noul", "instructions": "x"}}, "c")
    assert transport.bodies == []


def test_schemas_used_for_validation_reject_extra_fields():
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"ruling": "approve", "extra": 1}, SCHEMA)
