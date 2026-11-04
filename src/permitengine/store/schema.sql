CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  case_id TEXT,
  base_id TEXT,
  tone TEXT,
  type TEXT NOT NULL,
  parents TEXT NOT NULL,
  actor TEXT NOT NULL,
  simulated INTEGER NOT NULL,
  sim_time TEXT NOT NULL,
  manifest_hash TEXT NOT NULL,
  summary TEXT NOT NULL,
  payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS blobs (
  hash TEXT PRIMARY KEY,
  body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS named (
  name TEXT PRIMARY KEY,
  hash TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'the event log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'the event log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS blobs_no_update BEFORE UPDATE ON blobs BEGIN SELECT RAISE(ABORT, 'the event log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS blobs_no_delete BEFORE DELETE ON blobs BEGIN SELECT RAISE(ABORT, 'the event log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS named_no_update BEFORE UPDATE ON named BEGIN SELECT RAISE(ABORT, 'the event log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS named_no_delete BEFORE DELETE ON named BEGIN SELECT RAISE(ABORT, 'the event log is append-only'); END;
