"""One file per LLM vendor. Nothing else in the engine names a vendor, and a test checks that.

To add a vendor, add a module here that defines NAME, MODEL_PREFIX, SETTINGS_NAME, PRICE_REQUIRED, DEFAULT_EFFORT, VENDOR_WORDS
and PROVIDER. PROVIDER needs from_env() and send(), as in `..provider_api.Provider`. Modules are found by listing this folder.
"""
import importlib
import pkgutil

from ...workspace import EngineError


def adapters() -> list:
    return [importlib.import_module(f"{__name__}.{info.name}") for info in pkgutil.iter_modules(__path__)]


def adapter_for_model(model: str):
    for adapter in adapters():
        if model.startswith(adapter.MODEL_PREFIX):
            return adapter
    raise EngineError(f"no provider is known for model {model}")


def adapter_named(name: str):
    for adapter in adapters():
        if adapter.NAME == name:
            return adapter
    raise EngineError(f"no provider is named {name}")


def vendor_words() -> tuple:
    """Words that name a vendor or its models. The export refuses any of them."""
    return tuple(word for adapter in adapters() for word in adapter.VENDOR_WORDS)
