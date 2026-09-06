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
  -- 과제 효과 (억원/년). 기대효과는 착수 시, 실증효과는 끝난 뒤 채운다.
  effect_expected  REAL,
  effect_verified  REAL,
  -- 과제를 등록한 사람. 담당자(누가 하는가)와 다르다 (누가 등록했는가).
  -- 나중에 넣으면 그 전 과제는 영영 빈칸이라 지금부터 남긴다.
  created_by       TEXT,
  body             TEXT,
  file_mtime       REAL
);

CREATE TABLE IF NOT EXISTS entry (
  id         INTEGER PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  rel_path   TEXT NOT NULL,
  date       TEXT NOT NULL,
  title      TEXT NOT NULL,
  author     TEXT,
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
  author      TEXT,
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

-- 팀원 역량 이력 (TODO 72). 과제와 이어지지 않는 별개의 기록이다.
-- 기록 단위는 **사람**이라, 한 행사에 여러 명이 가면 사람 수만큼 줄이 생긴다.
CREATE TABLE IF NOT EXISTS activity (
  id         INTEGER PRIMARY KEY,
  person     TEXT NOT NULL,
  rel_path   TEXT NOT NULL UNIQUE,   -- people/<이름>/activities/<파일>.md
  date       TEXT NOT NULL,
  kind       TEXT NOT NULL,
  title      TEXT NOT NULL,
  host       TEXT,                   -- 주최
  place      TEXT,
  -- 시간·비용은 **옵션**이다 (2026-09-06 사용자). 비워 두는 것이 정상이다.
  hours      REAL,
  cost       REAL,
  -- 면담에서 실제로 읽게 되는 한 줄. 이 칸 때문에 이 화면을 만든다.
  takeaway   TEXT,
  link       TEXT,                   -- 수료증·자료가 있는 사내 공유 폴더 주소 등
  body       TEXT,
  author     TEXT,
  created_at TEXT,
  updated_at TEXT,
  file_mtime REAL
);

CREATE INDEX IF NOT EXISTS idx_activity_person_date ON activity(person, date DESC);
CREATE INDEX IF NOT EXISTS idx_activity_date ON activity(date DESC);

CREATE INDEX IF NOT EXISTS idx_entry_project_date ON entry(project_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_report_project_date ON report(project_id, report_date DESC);
CREATE INDEX IF NOT EXISTS idx_attachment_entry ON attachment(entry_id);
