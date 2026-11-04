"""The adapter for Moonshot's Kimi models. It goes through the same reader and checks, and has not run a real test."""
import json
import os
import time
import urllib.error
import urllib.request

from ...workspace import EngineError
from ..provider_api import API_KEY_ENV, UNREADABLE, LlmSpec, ProviderError

NAME = "moonshot"
MODEL_PREFIX = "kimi-"
SETTINGS_NAME = "moonshot"
PRICE_REQUIRED = False  # an unknown price is recorded as tokens
DEFAULT_EFFORT = "low"
VENDOR_WORDS = ("moonshot", "kimi")
URL = "https://api.moonshot.ai/v1/chat/completions"
_TIMEOUT_SECONDS = 180


def post_chat(body: dict, key: str, retries: int = 3) -> dict:
    data = json.dumps(body).encode("utf-8")
    for attempt in range(retries):
        request = urllib.request.Request(URL, data=data, method="POST",
                                         headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as reply:
                return json.load(reply)
        except urllib.error.HTTPError as exc:
            exc.close()
            if exc.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise ProviderError(f"the server answered with status {exc.code}") from None
        except (OSError, ValueError) as exc:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise ProviderError(f"the request failed ({type(exc).__name__})") from None
    raise ProviderError("the request failed")


class MoonshotProvider:
    """OpenAI-style chat API. `transport(body) -> reply` holds the key in a closure, and tests replace it.

    JSON mode only promises JSON, so the schema goes in the fixed block and the caller validates every answer against it.
    """

    def __init__(self, transport):
        self.transport = transport

    @staticmethod
    def from_env() -> "MoonshotProvider":
        key = os.environ.get(API_KEY_ENV)
        if not key:
            raise EngineError(f"{API_KEY_ENV} is not set. See .env.example")
        return MoonshotProvider(lambda body: post_chat(body, key))

    def send(self, spec: LlmSpec, system: str, user: str, schema: dict) -> dict:
        fixed = f"{system}\n\nAnswer with one JSON object and nothing else. It must fit this JSON Schema:\n{json.dumps(schema, sort_keys=True)}"
        body = {"model": spec.model, "messages": [{"role": "system", "content": fixed}, {"role": "user", "content": user}],
                "response_format": {"type": "json_object"}, "max_completion_tokens": spec.max_tokens}
        if spec.effort:
            body["reasoning_effort"] = spec.effort
        reply = self.transport(body)
        try:
            return self._read(reply)
        except UNREADABLE:
            raise ProviderError("the reply could not be read") from None

    @staticmethod
    def _read(reply: dict) -> dict:
        if reply.get("error"):
            raise ProviderError("the server reported an error")
        usage = reply["usage"]  # required: without it a call would look free, and the meter could not stop a run
        cached = usage.get("cached_tokens") or (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
        used = {"input_tokens": usage["prompt_tokens"] - cached, "output_tokens": usage["completion_tokens"],
                "cache_read_tokens": cached, "cache_write_tokens": 0}
        choice = reply["choices"][0]
        message, finish = choice["message"], choice.get("finish_reason")
        if message.get("refusal") or finish == "content_filter":
            return {"refused": True, "text": None, "usage": used, "model": reply.get("model")}
        if finish == "length":
            return {"refused": False, "text": None, "usage": used, "cut_off": True, "model": reply.get("model")}
        return {"refused": False, "text": message.get("content"), "usage": used, "model": reply.get("model")}


PROVIDER = MoonshotProvider
