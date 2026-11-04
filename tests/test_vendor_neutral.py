"""Changing LLM vendor means adding one adapter file, so the rest of the engine must not name one."""
import re
from pathlib import Path

from permitengine.models.llm import spec_from_settings
from permitengine.models.providers import adapter_for_model, adapters, vendor_words
from permitengine.config import Settings

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "src" / "permitengine"
ADAPTERS = SOURCE / "models" / "providers"
VENDOR = re.compile(r"(?<![a-z])(" + "|".join(vendor_words()) + r")(?![a-z])", re.IGNORECASE)


def test_only_the_adapters_name_a_vendor():
    found = [str(path.relative_to(ROOT)) for path in SOURCE.rglob("*.py") if not (path.parent == ADAPTERS and path.name != "__init__.py") and VENDOR.search(path.read_text(encoding="utf-8"))]
    assert not found


def test_every_adapter_declares_what_the_engine_needs():
    assert len(adapters()) >= 2
    for adapter in adapters():
        assert adapter_for_model(adapter.MODEL_PREFIX + "x") is adapter
        assert callable(adapter.PROVIDER.from_env) and callable(adapter.PROVIDER.send)


def test_the_settings_choose_the_model_without_naming_a_vendor_in_code():
    adapter = adapters()[0]
    model = adapter.MODEL_PREFIX + "x"
    settings = Settings({f"models.{adapter.SETTINGS_NAME}.id": {"key": "k", "value": model}, f"prices.{model}.input_usd_per_million": {"key": "k", "value": 1}, f"prices.{model}.output_usd_per_million": {"key": "k", "value": 2}})
    assert spec_from_settings(settings).model == model
