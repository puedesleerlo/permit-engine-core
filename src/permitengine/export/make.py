"""The static export the interface plays. Writes to a temporary folder, scans every file, and only then replaces the real one."""
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..models.provider_api import API_KEY_ENV
from ..models.providers import vendor_words
from ..config import load_settings
from ..store.log import Log
from ..workspace import EngineError, Workspace

DENY_WORDS = vendor_words()
DENY_PATTERN = re.compile(r"(?<![a-z])(" + "|".join(DENY_WORDS) + r")(?![a-z])", re.IGNORECASE)
KEY_PATTERNS = (re.compile(r"sk-[A-Za-z0-9_-]{16,}"), re.compile(r"Bearer\s+[A-Za-z0-9._-]{16,}"), re.compile(r"api[_-]?key", re.IGNORECASE),
                re.compile(r"AKIA[0-9A-Z]{16}"))
LONG_TOKEN = re.compile(r"[A-Za-z0-9_-]{40,}")
KEY_ENV = (API_KEY_ENV, "JEV_API_KEY")
EVENT_TYPES = {"case.submitted", "checks.done", "evidence.linked", "evidence.judged", "requirements.checked", "hazards.screened", "trees.evaluated", "risk.computed",
               "decision.made", "officer.ruled", "correction.made", "weights.updated", "thresholds.rechosen", "permit.issued", "change.released"}
CONDITION_NAMES = ("Lower loss than the first guess", "Lower loss than the shuffled control", "More approvals than the first guess", "Risky approvals not clearly above 5%")
ARM_ORDER = ("First guess", "Trained on labelled cases", "Shuffled labels (control)", "One LLM reads and decides (baseline)", "Jev asked directly")


def scan_text(text: str) -> list:
    """Why this text may not be published. An empty list means it may."""
    problems = []
    for match in DENY_PATTERN.finditer(text):
        problems.append(f"names a vendor or model: {match.group(0)}")
    for pattern in KEY_PATTERNS:
        if pattern.search(text):
            problems.append("holds something resembling a key")
    for match in LONG_TOKEN.finditer(text):
        token = match.group(0)
        if any(c.isdigit() for c in token) and any(c.islower() for c in token) and any(c.isupper() for c in token):
            problems.append("holds something resembling a key")
    for name in KEY_ENV:
        value = os.environ.get(name)
        if value and value in text:
            problems.append("holds a key")
    return problems


def scan_folder(folder: Path) -> list:
    problems = []
    for path in sorted(Path(folder).rglob("*")):
        if path.is_file():
            problems += [f"{path.relative_to(folder)}: {why}" for why in scan_text(path.read_text(encoding="utf-8"))]
    return problems


def latest_run(ws: Workspace) -> str:
    runs = sorted(ws.runs.glob("*.sqlite"), key=lambda p: p.stat().st_mtime)
    if not runs:
        raise EngineError(f"no runs in {ws.runs}; run `run-demo` first")
    return runs[-1].stem


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")


def _events(log: Log) -> list:
    out = []
    for event in log.events():
        if event["type"] not in EVENT_TYPES:
            raise EngineError(f"event type {event['type']} is not in the export contract")
        row = {"seq": event["seq"], "sim_time": event["sim_time"], "case_id": event["case_id"], "type": event["type"], "actor": event["actor"],
               "simulated": event["simulated"], "summary": event["summary"]}
        if event["type"] in ("correction.made", "thresholds.rechosen"):
            row["learning_index"] = event["payload"]["learning_index"]
        out.append(row)
    return out


def _load_yaml(path: Path, default):
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else default


def _rules(ws: Workspace) -> dict:
    ordinance = _load_yaml(ws.rules / "ordinance.yaml", {})
    clauses = ordinance.get("clauses", ordinance) if isinstance(ordinance, dict) else ordinance
    emap = _load_yaml(ws.rules / "evidence_map.yaml", {})
    settings = load_settings(ws.settings_file)
    rows = [{"key": e["key"], "value": e.get("value"), "limits": e.get("limits"), "owner": e.get("owner"), "why": e.get("why"), "if_raised": e.get("if_raised")}
            for e in settings.entries.values() if e.get("public") is True]
    hazards = [_load_yaml(p, {}) for p in sorted((ws.rules / "hazards").glob("*.yaml"))]
    return {"ordinance": [{"id": c["id"], "text": c["text"]} for c in clauses] if isinstance(clauses, list) else [],
            "evidence_types": emap.get("evidence_types", []), "requirements": emap.get("requirements", []), "does_not_count": emap.get("does_not_count", []),
            "settings": rows, "hazards": hazards}


def _public_arm(arm: dict, split: str) -> dict:
    return {"name": arm["name"], "loss": arm.get("loss"), "right_level": arm.get("right_level"), "approved": arm.get("approved"), "risky_among_approved": arm.get("risky_among_approved"),
            "right_route_share": (arm.get("on_all_cases") or {}).get("agrees_with_right_route"),
            "interval": arm.get("interval", [None, None]), "status": arm.get("status", "run"), "split": split}


def _arms(ws: Workspace, source: str, first_guess_dir, model_name) -> list:
    final = _final_report(ws, source)
    candidate = ws.weights / "candidates" / "trained" / "weights.json"
    found = {}
    if final is not None:
        found = {arm["name"]: _public_arm(arm, "test") for arm in final["arms"]}
    elif candidate.exists() and json.loads(candidate.read_text(encoding="utf-8")).get("fitted_on", {}).get("answers") == source:
        from ..evaluation.report import validation_report

        report = validation_report(ws, source, model_name, Path(first_guess_dir) if first_guess_dir else None)
        found = {arm["name"]: _public_arm(arm, "validation") for arm in report["arms"]}
    return [found.get(name) or {"name": name, "loss": None, "approved": None, "risky_among_approved": None, "interval": [None, None], "status": "not_run", "split": None} for name in ARM_ORDER]


def _final_report(ws: Workspace, source: str) -> dict | None:
    """Only a report on the same kind of answers as this run, so a simulated export never shows a real result, or the reverse."""
    path = ws.reports / "final.json"
    if not path.exists():
        return None
    final = json.loads(path.read_text(encoding="utf-8"))
    return final if final.get("answers") == source else None


def _final_test(ws: Workspace, source: str) -> dict:
    final = _final_report(ws, source)
    if final is None:
        conditions = [{"name": name, "passed": None, "detail": "The sealed test has not run."} for name in CONDITION_NAMES]
        return {"status": "not_run", "verdict": None, "conditions": conditions, "forbidden_permits": None, "risky_approvals": None}
    return {k: final.get(k) for k in ("status", "verdict", "conditions", "forbidden_permits", "risky_approvals", "approved", "risky_interval", "forbidden_interval", "limits")}


def make_export(ws: Workspace, run_id: str | None = None, model_name: str | None = None) -> dict:
    run_id = run_id or latest_run(ws)
    log = Log(ws.runs / f"{run_id}.sqlite", run_id, create=False)
    run = log.named("run")
    if run is None:
        raise EngineError(f"run {run_id} did not finish")
    cases = log.named("cases")
    learning = log.named("learning")
    events = _events(log)
    learning["arms"] = _arms(ws, run["source"], run["manifest"].get("first_guess_dir"), model_name)
    learning["final_test"] = _final_test(ws, run["source"])
    tone_file = ws.reports / "tone.json"
    if run["source"] == "real" and tone_file.exists():
        tone = json.loads(tone_file.read_text(encoding="utf-8"))
        learning["tone"] = {"requests": tone["requests"], "compared": sum(t["compared"] for t in tone["tones"].values()), "decision_flips": sum(t["decision_flips"] for t in tone["tones"].values()),
                            "evidence_flips": {k: t["evidence_flips"] for k, t in tone["tones"].items()}, "noise_evidence_flips": (tone.get("noise_floor") or {}).get("evidence_flips"),
                            "noise_decision_flips": (tone.get("noise_floor") or {}).get("decision_flips")}
    manifest = {"run_id": run_id, "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"), "source": run["source"], "synthetic": True,
                "officer_label": run["officer_label"], "jev_model": run["jev_model"], "case_count": len(cases), "event_count": len(events), "officer_accuracy": run["officer_accuracy"],
                "notes": ["All applications are synthetic."] + (["Answers in this run are simulated: no model read these cases."] if run["source"] == "simulated" else [])}
    ws.root.joinpath("export").mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="demo-", dir=ws.root / "export"))
    try:
        _write(temporary / "manifest.json", manifest)
        _write(temporary / "events.json", events)
        _write(temporary / "cases.json", cases)
        _write(temporary / "learning.json", learning)
        _write(temporary / "rules.json", _rules(ws))
        for row in cases:
            _write(temporary / "cases" / f"{row['case_id']}.json", log.named(f"case:{row['case_id']}"))
        problems = scan_folder(temporary)
        if problems:
            raise EngineError("the export was not published: " + "; ".join(sorted(set(problems))[:20]))
        if ws.export.exists():
            shutil.rmtree(ws.export)
        ws.export.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(temporary), ws.export)
    finally:
        log.close()
        if temporary.exists():
            shutil.rmtree(temporary)
    if ws.web_data.exists():
        shutil.rmtree(ws.web_data)
    ws.web_data.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ws.export, ws.web_data)
    return {"export": str(ws.export), "web": str(ws.web_data), "cases": len(cases), "events": len(events)}
