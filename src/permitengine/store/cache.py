"""Stored answers for real calls, named by a hash of kind, payload, input and model. A second read makes no calls."""
import json
import os
import threading
from pathlib import Path

from ..hashing import content_hash


def cache_key(kind: str, payload, input_value, model: str) -> str:
    return content_hash({"kind": kind, "payload": payload, "input": input_value, "model": model})


class Cache:
    def __init__(self, folder: Path):
        self.folder = Path(folder)

    def _path(self, kind: str, key: str) -> Path:
        return self.folder / kind / key[:2] / f"{key}.json"

    def get(self, kind: str, key: str):
        path = self._path(kind, key)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def put(self, kind: str, key: str, value: dict) -> None:
        path = self._path(kind, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(value, indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
