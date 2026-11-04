"""What every LLM adapter shares. Nothing here names a vendor."""
from dataclasses import dataclass
from typing import Protocol

API_KEY_ENV = "LLM_API_KEY"
UNREADABLE = (KeyError, IndexError, TypeError, AttributeError, ValueError)


class ProviderError(Exception):
    pass


@dataclass(frozen=True)
class LlmSpec:
    model: str
    provider: str
    effort: str | None
    prices: dict | None  # USD per million tokens: input, output, cache_read, cache_write. None means the price is unknown
    max_tokens: int = 16000


class Provider(Protocol):
    def send(self, spec: LlmSpec, system: str, user: str, schema: dict) -> dict: ...
