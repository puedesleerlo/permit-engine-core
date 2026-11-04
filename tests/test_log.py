import sqlite3

import pytest

from permitengine.store.log import Log
from permitengine.workspace import EngineError


def make(tmp_path):
    return Log(tmp_path / "run.sqlite", "run")


def add(log, kind="case.submitted"):
    return log.append("R1-plain", kind, "script", True, "2027-01-04T09:00:00", "hash", "summary", {"a": 1})


def test_updates_and_deletes_fail(tmp_path):
    log = make(tmp_path)
    add(log)
    log.put_blob({"x": 1})
    log.set_named("n", {"y": 1})
    for statement in ("UPDATE events SET summary = 'x'", "DELETE FROM events", "UPDATE blobs SET body = 'x'", "DELETE FROM blobs", "UPDATE named SET hash = 'x'", "DELETE FROM named"):
        with pytest.raises(sqlite3.IntegrityError):
            log.db.execute(statement)
    assert len(log.events()) == 1


def test_a_failed_write_leaves_nothing_behind(tmp_path):
    log = make(tmp_path)
    with pytest.raises(RuntimeError):
        with log.transaction():
            add(log)
            add(log, "decision.made")
            raise RuntimeError("the write failed")
    assert log.events() == []


def test_a_run_is_never_overwritten(tmp_path):
    make(tmp_path).close()
    with pytest.raises(EngineError):
        make(tmp_path)


def test_events_come_back_in_order_with_their_fields(tmp_path):
    log = make(tmp_path)
    first = add(log)
    second = log.append("R1-plain", "decision.made", "rego", False, "2027-01-04T09:01:00", "hash", "done", {"b": [1, 2]}, parents=[first], base_id="R1", tone="plain")
    rows = log.events()
    assert [r["seq"] for r in rows] == [first, second]
    assert rows[1]["parents"] == [first] and rows[1]["payload"] == {"b": [1, 2]} and rows[1]["simulated"] is False
    assert log.events("decision.made")[0]["seq"] == second
    assert log.blob(log.put_blob({"k": 1})) == {"k": 1}
    with pytest.raises(EngineError):
        log.blob("missing")


def test_a_missing_log_is_refused(tmp_path):
    with pytest.raises(EngineError):
        Log(tmp_path / "none.sqlite", "none", create=False)
