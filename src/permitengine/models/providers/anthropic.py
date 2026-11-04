"""The adapter for Anthropic's Claude models. The sealed test ran on this one."""
import os

from ...workspace import EngineError
from ..provider_api import API_KEY_ENV, UNREADABLE, LlmSpec, ProviderError

NAME = "anthropic"
MODEL_PREFIX = "claude-"
SETTINGS_NAME = "claude"
PRICE_REQUIRED = True  # with no price, the meter could not stop a run
DEFAULT_EFFORT = None
VENDOR_WORDS = ("claude", "anthropic", "opus", "haiku", "sonnet")


class AnthropicProvider:
    """`client` has the SDK's beta.messages.create. Schema adherence is enforced by the server through output_config."""

    def __init__(self, client):
        self.client = client

    @staticmethod
    def from_env() -> "AnthropicProvider":
        import anthropic

        key = os.environ.get(API_KEY_ENV)
        if not key:
            raise EngineError(f"{API_KEY_ENV} is not set. See .env.example")
        return AnthropicProvider(anthropic.Anthropic(api_key=key))

    def send(self, spec: LlmSpec, system: str, user: str, schema: dict) -> dict:
        output_config = {"format": {"type": "json_schema", "schema": schema}}
        if spec.effort:
            output_config["effort"] = spec.effort
        try:
            reply = self.client.beta.messages.create(
                model=spec.model,
                max_tokens=spec.max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
                output_config=output_config,
            )
        except Exception as exc:  # the SDK's messages can quote the request, so only the class name goes on
            raise ProviderError(f"the call failed ({type(exc).__name__})") from None
        try:
            return self._read(reply)
        except UNREADABLE:
            raise ProviderError("the reply could not be read") from None

    @staticmethod
    def _read(reply) -> dict:
        usage = reply.usage
        if usage is None:  # without usage a call would look free, and the meter could not stop a run
            raise ProviderError("the reply holds no usage")
        used = {"input_tokens": usage.input_tokens or 0, "output_tokens": usage.output_tokens or 0,
                "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
                "cache_write_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0}
        model = getattr(reply, "model", None)
        if reply.stop_reason == "refusal":
            return {"refused": True, "text": None, "usage": used, "model": model}
        if reply.stop_reason == "max_tokens":
            return {"refused": False, "text": None, "usage": used, "cut_off": True, "model": model}
        text = next((block.text for block in reply.content if block.type == "text"), None)
        return {"refused": False, "text": text, "usage": used, "model": model}


PROVIDER = AnthropicProvider
