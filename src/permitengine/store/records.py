"""One reading record per case, in one format whether simulated or real. `source` says which."""
import json
from pathlib import Path

from ..workspace import EngineError, Workspace


def records_dir(ws: Workspace, source: str, model: str | None = None) -> Path:
    if source == "simulated":
        return ws.cache / "records" / "simulated"
    if source == "real":
        if not model:
            raise EngineError("real records are stored per model; give the model id")
        return ws.cache / "records" / "real" / model
    raise EngineError(f"unknown answer source {source}")


def write_record(folder: Path, record: dict) -> None:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{record['case_id']}.json").write_text(json.dumps(record, indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def read_record(folder: Path, case_id: str) -> dict | None:
    path = Path(folder) / f"{case_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_records(folder: Path, case_ids) -> dict:
    out, missing = {}, []
    for case_id in case_ids:
        record = read_record(folder, case_id)
        if record is None:
            missing.append(case_id)
        else:
            out[case_id] = record
    if missing:
        raise EngineError(f"{len(missing)} stored reading records are missing from {folder}, such as {missing[0]}. Run `simulate` or `read` first.")
    return out
