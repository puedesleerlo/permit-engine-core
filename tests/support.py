"""The adapters these tests run through. Outside the adapters, this is the one place the tests name a vendor."""
from permitengine.models.providers.anthropic import AnthropicProvider as MainProvider
from permitengine.models.providers.moonshot import MoonshotProvider as OtherProvider

TESTED_VENDOR = "anthropic"
TESTED_SETTINGS = "claude"
TESTED_MODEL = "claude-opus-5-5"
ANOTHER_TESTED_MODEL = "claude-haiku-5-5"
OTHER_VENDOR = "moonshot"
OTHER_MODEL = "kimi-k3"
