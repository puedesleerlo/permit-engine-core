"""One SQLite file per run. Triggers reject updates and deletes. Everything a case writes goes in one transaction."""
import json
import sqlite3
from pathlib import Path

from ..hashing import canonical, content_hash
from ..workspace import EngineError

SCHEMA = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")


class Log:
    def __init__(self, path: Path, run_id: str, create: bool = True):
        self.path = Path(path)
        self.run_id = run_id
        if create:
            if self.path.exists():
                raise EngineError(f"{self.path} already exists. A run is never overwritten; name a new run or move the old file.")
            self.path.parent.mkdir(parents=True, exist_ok=True)
        elif not self.path.exists():
            raise EngineError(f"run log {self.path} does not exist")
        self.db = sqlite3.connect(self.path, isolation_level=None)
        if create:
            self.db.executescript(SCHEMA)

    def transaction(self):
        return _Transaction(self.db)

    def append(self, case_id, kind, actor, simulated, sim_time, manifest_hash, summary, payload, parents=(), base_id=None, tone=None) -> int:
        cursor = self.db.execute(
            "INSERT INTO events (run_id, case_id, base_id, tone, type, parents, actor, simulated, sim_time, manifest_hash, summary, payload)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (self.run_id, case_id, base_id, tone, kind, json.dumps(list(parents)), actor, int(simulated), sim_time, manifest_hash, summary,
             canonical(payload)))
        return cursor.lastrowid

    def put_blob(self, value) -> str:
        key = content_hash(value)
        self.db.execute("INSERT OR IGNORE INTO blobs (hash, body) VALUES (?, ?)", (key, canonical(value)))
        return key

    def blob(self, key: str):
        row = self.db.execute("SELECT body FROM blobs WHERE hash = ?", (key,)).fetchone()
        if row is None:
            raise EngineError(f"blob {key} is missing from the log")
        return json.loads(row[0])

    def set_named(self, name: str, value) -> None:
        key = self.put_blob(value)
        self.db.execute("INSERT INTO named (name, hash) VALUES (?, ?)", (name, key))

    def named(self, name: str):
        row = self.db.execute("SELECT hash FROM named WHERE name = ?", (name,)).fetchone()
        return None if row is None else self.blob(row[0])

    def events(self, kind=None, case_id=None) -> list:
        query = "SELECT seq, run_id, case_id, base_id, tone, type, parents, actor, simulated, sim_time, manifest_hash, summary, payload FROM events"
        where, args = [], []
        if kind:
            where.append("type = ?")
            args.append(kind)
        if case_id:
            where.append("case_id = ?")
            args.append(case_id)
        if where:
            query += " WHERE " + " AND ".join(where)
        rows = self.db.execute(query + " ORDER BY seq", args).fetchall()
        names = ("seq", "run_id", "case_id", "base_id", "tone", "type", "parents", "actor", "simulated", "sim_time", "manifest_hash", "summary", "payload")
        out = []
        for row in rows:
            event = dict(zip(names, row))
            event["parents"] = json.loads(event["parents"])
            event["payload"] = json.loads(event["payload"])
            event["simulated"] = bool(event["simulated"])
            out.append(event)
        return out

    def close(self) -> None:
        self.db.close()


class _Transaction:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        self.db.execute("BEGIN IMMEDIATE")
        return self

    def __exit__(self, kind, value, traceback):
        self.db.execute("ROLLBACK" if kind else "COMMIT")
        return False
