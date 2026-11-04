"""Canonical JSON and content hashes, for stored-answer keys and manifests."""
import hashlib
import json
from pathlib import Path


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_hash(value) -> str:
    return sha256_text(canonical(value))


def files_hash(paths) -> str:
    """Hash of file names and bytes, in sorted order, so moving a tree of files elsewhere keeps its hash."""
    digest = hashlib.sha256()
    for path in sorted(Path(p) for p in paths):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
