CREATE TABLE IF NOT EXISTS handoffs (
  id TEXT PRIMARY KEY,
  input_keys TEXT NOT NULL,
  sender_role TEXT NOT NULL,
  recipient_role TEXT NOT NULL,
  requested_action TEXT NOT NULL,
  status TEXT NOT NULL,
  idempotency_key TEXT NOT NULL UNIQUE,
  metadata TEXT NOT NULL DEFAULT '{}',
  evidence TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  handoff_id TEXT NOT NULL REFERENCES handoffs(id),
  event TEXT NOT NULL,
  detail TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_handoffs_status ON handoffs(status);
CREATE INDEX IF NOT EXISTS idx_audit_handoff ON audit_log(handoff_id);
CREATE TABLE IF NOT EXISTS artifacts (
  artifact_id TEXT NOT NULL,
  version TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  kind TEXT NOT NULL,
  source_uri TEXT NOT NULL,
  registered_at TEXT NOT NULL,
  PRIMARY KEY (artifact_id, version)
);
