PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS project (
  id               TEXT PRIMARY KEY,
  dir_name         TEXT NOT NULL UNIQUE,
  title            TEXT NOT NULL,
  status           TEXT NOT NULL,
  type             TEXT,
  grp              TEXT,
  owner            TEXT,
  start_date       TEXT,
  due_date         TEXT,
  created_at       TEXT,
  updated_at       TEXT,
  last_reported_at TEXT,
  body             TEXT,
  file_mtime       REAL
);

CREATE TABLE IF NOT EXISTS entry (
  id         INTEGER PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  rel_path   TEXT NOT NULL,
  date       TEXT NOT NULL,
  title      TEXT NOT NULL,
  body       TEXT,
  created_at TEXT,
  updated_at TEXT,
  file_mtime REAL,
  UNIQUE(project_id, rel_path)
);

CREATE TABLE IF NOT EXISTS report (
  id          INTEGER PRIMARY KEY,
  project_id  TEXT NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  report_date TEXT NOT NULL,
  title       TEXT,
  rel_path    TEXT NOT NULL,
  covers_from TEXT,
  covers_to   TEXT,
  body        TEXT,
  frozen_at   TEXT,
  report_type TEXT,
  audience    TEXT,
  file_mtime  REAL,
  UNIQUE(project_id, rel_path)
);

CREATE TABLE IF NOT EXISTS report_entry (
  report_id INTEGER REFERENCES report(id) ON DELETE CASCADE,
  entry_id  INTEGER REFERENCES entry(id)  ON DELETE CASCADE,
  PRIMARY KEY(report_id, entry_id)
);

CREATE TABLE IF NOT EXISTS attachment (
  id         INTEGER PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  entry_id   INTEGER REFERENCES entry(id) ON DELETE SET NULL,
  report_id  INTEGER REFERENCES report(id) ON DELETE SET NULL,
  rel_path   TEXT NOT NULL,
  orig_name  TEXT NOT NULL,
  mime       TEXT,
  size_bytes INTEGER,
  sha256     TEXT,
  created_at TEXT,
  UNIQUE(project_id, rel_path)
);

-- 과제 담당자 (한 명부터 여러 명까지)
CREATE TABLE IF NOT EXISTS project_owner (
  project_id TEXT REFERENCES project(id) ON DELETE CASCADE,
  name       TEXT NOT NULL,
  position   INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(project_id, name)
);

CREATE TABLE IF NOT EXISTS tag (
  id   INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS project_tag (
  project_id TEXT REFERENCES project(id) ON DELETE CASCADE,
  tag_id     INTEGER REFERENCES tag(id) ON DELETE CASCADE,
  PRIMARY KEY(project_id, tag_id)
);

CREATE TABLE IF NOT EXISTS entry_tag (
  entry_id INTEGER REFERENCES entry(id) ON DELETE CASCADE,
  tag_id   INTEGER REFERENCES tag(id) ON DELETE CASCADE,
  PRIMARY KEY(entry_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_entry_project_date ON entry(project_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_report_project_date ON report(project_id, report_date DESC);
CREATE INDEX IF NOT EXISTS idx_attachment_entry ON attachment(entry_id);
