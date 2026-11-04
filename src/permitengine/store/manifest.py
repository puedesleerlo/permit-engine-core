"""Hashes of what a decision used, for the manifest."""
from ..hashing import canonical, sha256_text
from ..workspace import Workspace


def rules_hash(ws: Workspace) -> str:
    parts = {}
    for path in sorted(ws.rules.rglob("*")):
        if path.is_file():
            parts[str(path.relative_to(ws.rules))] = path.read_bytes().hex()
    return sha256_text(canonical(parts))


def settings_hash(ws: Workspace) -> str:
    return sha256_text(ws.settings_file.read_text(encoding="utf-8"))
