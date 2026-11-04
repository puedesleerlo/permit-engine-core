"""The `release` command: makes weights official, with who released them and the hashes they were fitted on. Never overwrites."""
import json
import shutil
from datetime import datetime, timezone

from ..hashing import content_hash
from ..workspace import EngineError, Workspace

KINDS = {"weights": "trained", "crossings": "trained-crossings"}


def release(ws: Workspace, kind: str, version: str, role: str = "policy_owner") -> dict:
    if kind not in KINDS:
        raise EngineError(f"unknown release kind {kind}; kinds are {', '.join(sorted(KINDS))}")
    source = ws.weights / "candidates" / KINDS[kind] / "weights.json"
    if not source.exists():
        raise EngineError(f"{source} does not exist; run `train` first")
    target = ws.weights / version
    if target.exists():
        raise EngineError(f"weights version {version} already exists. Released weights never change in place.")
    body = json.loads(source.read_text(encoding="utf-8"))
    if not body.get("thresholds"):
        raise EngineError("this candidate has no thresholds; run `thresholds` first")
    target.mkdir(parents=True)
    shutil.copyfile(source, target / "weights.json")
    release_record = {"version": version, "kind": kind, "role": role, "released_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      "weights_hash": body.get("weights_hash"), "thresholds": body["thresholds"], "fitted_on": body.get("fitted_on"),
                      "content_hash": content_hash(body)}
    (target / "release.json").write_text(json.dumps(release_record, indent=1, sort_keys=True), encoding="utf-8")
    return release_record
