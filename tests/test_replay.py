"""Reproduce: the logged decision again, from stored inputs, with no calls, and identical. It refuses when an input has changed."""
import json

import pytest

from conftest import FIRST_GUESS
from support import ANOTHER_TESTED_MODEL, OTHER_MODEL, OTHER_VENDOR, OtherProvider, TESTED_MODEL, TESTED_SETTINGS, TESTED_VENDOR, MainProvider
from permitengine.evaluation.demo import run_demo
from permitengine.evaluation.simulated_answers import simulate
from permitengine.replay import reproduce as module
from permitengine.replay.reproduce import reproduce
from permitengine.workspace import EngineError


@pytest.fixture
def run(world):
    simulate(world)
    run_demo(world, "r1", first_guess_dir=FIRST_GUESS)
    return world


def test_reproduce_is_identical_for_every_decision(run):
    out = reproduce(run, "r1")
    assert out["checked"] == 24 and out["identical"] == 24 and out["mismatched"] == []


def test_reproduce_one_case(run):
    case_id = run.splits()["validation"][3]
    assert reproduce(run, "r1", case_id)["checked"] == 1


def test_reproduce_needs_no_stored_records_or_keys_because_the_log_holds_them(run, monkeypatch):
    import shutil

    shutil.rmtree(run.cache)
    for name in ("LLM_API_KEY", "JEV_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert reproduce(run, "r1")["identical"] == 24


def test_reproduce_imports_no_model_client():
    source = (module.__file__ and open(module.__file__, encoding="utf-8").read())
    assert "models" not in source and TESTED_VENDOR not in source


def test_reproduce_refuses_a_changed_application(run):
    case_id = run.splits()["validation"][0]
    path = run.data / "applications" / case_id / "form.json"
    body = json.loads(path.read_text())
    body["expected_runners"] += 1
    path.write_text(json.dumps(body))
    with pytest.raises(EngineError, match="has changed"):
        reproduce(run, "r1", case_id)


def test_reproduce_refuses_changed_rules(run):
    path = run.rules / "ordinance.yaml"
    path.write_text(path.read_text() + "\n# changed\n")
    with pytest.raises(EngineError, match="rules have changed"):
        reproduce(run, "r1")


def test_reproduce_refuses_changed_settings(run):
    path = run.settings_file
    path.write_text(path.read_text() + "\n# changed\n")
    with pytest.raises(EngineError, match="settings have changed"):
        reproduce(run, "r1")


def test_reproduce_refuses_another_arithmetic_version(run, monkeypatch):
    monkeypatch.setattr(module, "ARITHMETIC_VERSION", "other")
    with pytest.raises(EngineError, match="arithmetic"):
        reproduce(run, "r1")


def test_reproduce_notices_a_tampered_log(run):
    import sqlite3

    db = sqlite3.connect(run.runs / "r1.sqlite")
    db.execute("DROP TRIGGER events_no_update")
    rows = db.execute("SELECT seq, payload FROM events WHERE type = 'decision.made'").fetchall()
    seq, payload = rows[0]
    body = json.loads(payload)
    body["decision"]["route"] = "approved" if body["decision"]["route"] != "approved" else "officer"
    db.execute("UPDATE events SET payload = ? WHERE seq = ?", (json.dumps(body), seq))
    db.commit()
    db.close()
    out = reproduce(run, "r1")
    assert len(out["mismatched"]) == 1 and out["identical"] == 23


def test_a_missing_run_is_refused(world):
    with pytest.raises(EngineError):
        reproduce(world, "nope")
