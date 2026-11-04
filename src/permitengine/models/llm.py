"""The LLM client. Vendors sit behind one small interface, with one adapter file each in `providers/`. A provider's `send` takes
a spec, system text, user text and a schema, and returns {"refused", "text", "usage", "model"} and "cut_off" when it applies.

The caller holds what is common: stored answers, the one spend meter, and validating every answer against the schema with one
retry. Keys come in explicitly from the environment. Errors carry a status or a class name, never a message, because a message
can quote the request. Only one model answers a read, so no server-side fallback is used: a refusal goes to an officer.
"""
import json
import re
from decimal import Decimal

import jsonschema

from ..store.cache import Cache, cache_key
from ..workspace import EngineError
from .budget import Budget
from .provider_api import LlmSpec, Provider, ProviderError
from .providers import adapter_for_model, adapter_named

_MILLION = Decimal(1_000_000)
_CHARS_PER_TOKEN = 3
_EXPECTED_OUTPUT_TOKENS = 1500


class ModelFailure(Exception):
    """The model refused, or gave a bad answer twice. The case goes to an officer as model_failure."""


def provider_name(model: str) -> str:
    return adapter_for_model(model).NAME


def choose_model(settings, flag: str | None = None) -> str:
    """The `--model` flag, then `models.llm.id` in settings, then the model the settings name under a vendor."""
    named = settings.get("models.llm.id", None) if not flag else None
    if flag or named:
        return flag or named
    for key in settings.entries:
        if re.fullmatch(r"models\.[\w-]+\.id", key):
            return settings.get(key)
    raise EngineError("settings name no LLM model")


def _price_row(settings, prefix: str) -> dict | None:
    input_key, output_key = f"{prefix}.input_usd_per_million", f"{prefix}.output_usd_per_million"
    if input_key not in settings.entries or output_key not in settings.entries:
        return None
    usd_in, usd_out = settings.get(input_key), settings.get(output_key)
    if usd_in is None or usd_out is None:  # an explicit null: the price is not confirmed
        return None
    usd_in, usd_out = Decimal(str(usd_in)), Decimal(str(usd_out))
    # Settings without cache rates count a cached token as a full input token and a cache write at the documented 1.25 times,
    # which can only overstate spend.
    cache_read = settings.get(f"{prefix}.cache_read_usd_per_million", None)
    cache_write = settings.get(f"{prefix}.cache_write_usd_per_million", None)
    return {"input": usd_in, "output": usd_out, "cache_read": Decimal(str(cache_read)) if cache_read is not None else usd_in,
            "cache_write": Decimal(str(cache_write)) if cache_write is not None else usd_in * Decimal("1.25")}


def _prices(settings, model: str) -> dict | None:
    """`prices.<model>.*` first. A vendor's `prices.<name>.*` are the rates of its `models.<name>.id` only, so another model never borrows them."""
    found = _price_row(settings, f"prices.{model}")
    name = adapter_for_model(model).SETTINGS_NAME
    if found is None and model == settings.get(f"models.{name}.id", None):
        found = _price_row(settings, f"prices.{name}")
    return found


def spec_from_settings(settings, model: str | None = None) -> LlmSpec:
    model = choose_model(settings, model)
    adapter = adapter_for_model(model)
    prices = _prices(settings, model)
    if prices is None and adapter.PRICE_REQUIRED:
        raise EngineError(f"settings give no price for {model}, so the meter could not stop a run")
    effort = settings.get(f"models.{adapter.SETTINGS_NAME}.effort", adapter.DEFAULT_EFFORT)
    return LlmSpec(model=model, provider=adapter.NAME, effort=effort, prices=prices)


def cost_usd(spec: LlmSpec, usage: dict) -> Decimal | None:
    if spec.prices is None:
        return None
    return (usage["input_tokens"] * spec.prices["input"] + usage["output_tokens"] * spec.prices["output"] +
            usage["cache_read_tokens"] * spec.prices["cache_read"] + usage["cache_write_tokens"] * spec.prices["cache_write"]) / _MILLION


def provider_from_env(name: str) -> Provider:
    return adapter_named(name).PROVIDER.from_env()


class LlmClient:
    def __init__(self, spec: LlmSpec, provider: Provider, cache: Cache, budget: Budget):
        self.spec = spec
        self.provider = provider
        self.cache = cache
        self.budget = budget
        self.calls = 0
        self.stored_hits = 0

    @staticmethod
    def from_env(settings, cache: Cache, budget: Budget, model: str | None = None) -> "LlmClient":
        spec = spec_from_settings(settings, model)
        return LlmClient(spec, provider_from_env(spec.provider), cache, budget)

    def _estimate(self, system: str, user: str) -> Decimal:
        if self.spec.prices is None:
            return Decimal(0)
        tokens = (len(system) + len(user)) // _CHARS_PER_TOKEN
        return (tokens * self.spec.prices["input"] + _EXPECTED_OUTPUT_TOKENS * self.spec.prices["output"]) / _MILLION

    def _call_once(self, kind: str, system: str, user: str, schema: dict, case_id: str) -> dict:
        key = cache_key(kind, {"system": system, "schema": schema}, user, self.spec.model)
        stored = self.cache.get(kind, key)
        if stored is not None:
            self.stored_hits += 1
            return stored
        estimate = self._estimate(system, user)
        self.budget.reserve(usd=estimate)
        try:
            self.calls += 1
            answer = self.provider.send(self.spec, system, user, schema)
        except BaseException:
            self.budget.release(reserved_usd=estimate)
            raise
        usd = cost_usd(self.spec, answer["usage"])
        self.budget.settle(reserved_usd=estimate, usd=usd, kind=kind, case_id=case_id, model=self.spec.model, **answer["usage"])
        answer.update(key=key, kind=kind, requested_model=self.spec.model, usd=None if usd is None else str(usd))
        if not answer.get("cut_off"):
            self.cache.put(kind, key, answer)
        return answer

    def structured(self, kind: str, system: str, user: str, schema: dict, case_id: str) -> dict:
        """The parsed answer, validated whichever provider gave it. A refusal, or a bad answer after one retry, raises ModelFailure.

        A budget stop raises BudgetExceeded, which ends the run rather than one case.
        """
        last = "no answer"
        for attempt in range(2):
            prompt = user if attempt == 0 else f"{user}\n\nYour last answer did not fit the required schema. Answer again, following it exactly."
            try:
                answer = self._call_once(kind, system, prompt, schema, case_id)
            except ProviderError as exc:
                last = str(exc)
                continue
            if answer.get("refused"):
                raise ModelFailure("the model refused")
            if answer.get("text") is None:
                last = "the answer was empty or cut off"
                continue
            try:
                parsed = json.loads(answer["text"])
                jsonschema.validate(parsed, schema)
            except (ValueError, jsonschema.ValidationError):
                last = "the answer did not fit the schema"
                continue
            return parsed
        raise ModelFailure(last)
