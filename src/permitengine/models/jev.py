"""The Jev client, standard library only. One request per case. The returned model is checked against the pinned one."""
import json
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from ..store.cache import Cache, cache_key
from ..workspace import EngineError
from .budget import Budget

API_URL = "https://api.typesafe.ai/v1/systemone"
_CHARS_PER_TOKEN = 3


class JevFailure(Exception):
    pass


def post_json(body: dict, key: str, retries: int = 4) -> dict:
    data = json.dumps(body).encode("utf-8")
    for attempt in range(retries):
        request = urllib.request.Request(API_URL, data=data, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=120) as reply:
                return json.load(reply)
        except urllib.error.HTTPError as exc:
            exc.close()
            if exc.code in (429, 500, 502, 503, 504, 529) and attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise JevFailure(f"Jev answered with status {exc.code}") from None
        except (urllib.error.URLError, OSError, ValueError) as exc:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise JevFailure(f"the Jev request failed ({type(exc).__name__})") from None
    raise JevFailure("the Jev request failed")


def key_from_env() -> str:
    key = os.environ.get("JEV_API_KEY")
    if not key:
        raise EngineError("JEV_API_KEY is not set. See .env.example")
    return key


class JevClient:
    """`transport(body) -> reply` is injected in tests. The real one holds the key in a closure, so stored data never sees it."""

    def __init__(self, model: str, transport, cache: Cache, budget: Budget, max_concurrency: int = 4):
        self.model = model
        self.transport = transport
        self.cache = cache
        self.budget = budget
        self.max_concurrency = min(max_concurrency, 4)
        self.calls = 0
        self.stored_hits = 0

    @staticmethod
    def from_env(model: str, cache: Cache, budget: Budget, max_concurrency: int = 4) -> "JevClient":
        key = key_from_env()
        return JevClient(model, lambda body: post_json(body, key), cache, budget, max_concurrency)

    def ask(self, kind: str, state: dict, questions: dict, case_id: str) -> dict:
        """The full reply: answers, model and usage. A wrong returned model is a failure, and is not stored."""
        body = {"model": self.model, "state": state, "questions": questions}
        key = cache_key(kind, {"questions": questions}, state, self.model)
        stored = self.cache.get(kind, key)
        if stored is not None:
            self.stored_hits += 1
            return stored
        estimate = len(json.dumps(body)) // _CHARS_PER_TOKEN
        self.budget.reserve(jev_tokens=estimate)
        try:
            self.calls += 1
            reply = self.transport(body)
        except BaseException:
            self.budget.release(reserved_tokens=estimate)
            raise
        usage = reply.get("usage") or {}
        self.budget.settle(reserved_tokens=estimate, jev_tokens=int(usage.get("input_tokens", estimate)), kind=kind, case_id=case_id,
                           model=reply.get("model"), output_tokens=usage.get("output_tokens", 0))
        if reply.get("model") != self.model:
            raise JevFailure(f"Jev answered with model {reply.get('model')}, not the pinned {self.model}")
        if not isinstance(reply.get("answers"), dict):
            raise JevFailure("the Jev reply holds no answers")
        self.cache.put(kind, key, reply)
        return reply

    def map(self, function, items) -> list:
        with ThreadPoolExecutor(max_workers=self.max_concurrency) as pool:
            return list(pool.map(function, items))
