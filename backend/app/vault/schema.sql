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
  -- 별도 보고가 필요 없는 과제 (단순 현황 관리를 과제로 세운 경우).
  -- 보고 대상 후보에서만 빠진다 — 손으로 보고를 남기는 길은 그대로 열려 있다.
  no_report  INTEGER NOT NULL DEFAULT 0,
  -- 과제를 등록한 사람. 담당자(누가 하는가)와 다르다 (누가 등록했는가).
  -- 나중에 넣으면 그 전 과제는 영영 빈칸이라 지금부터 남긴다.
  created_by       TEXT,
  -- 과제가 끝난 날 (TODO 104). 상태가 완료가 되는 순간 자동으로 남고, 손으로 고칠 수 있다.
  -- 홈의 "올해 끝낸 과제" 가 이 날짜로 센다 — 번호의 연도로는 지난해 시작해 올해 끝낸
  -- 과제가 올해 성과에 잡히지 않는다. 나중에 넣으면 그 전 과제는 영영 빈칸이다.
  completed_at     TEXT,
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
  -- 보고 뒤에 받은 지시·질문 (TODO 107). 확정된 보고에서 유일하게 쓸 수 있는 본문이다.
  -- feedback_done 은 다음 보고에서 답한 날 — 비어 있으면 아직 답하지 않은 지시다.
  feedback      TEXT,
  feedback_done TEXT,
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

-- 유관부서와 그 담당자 (TODO 92).
--
-- **팀과 사람을 한 칸에 묶어 적지 않는다.** "설비기술팀: 김철수, 박민수" 처럼 한 문자열로
-- 두면 집계도 검색도 그 문자열을 다시 쪼개야 하고, 쪼개는 규칙이 어긋나는 순간
-- 없는 사람이 생긴다 (TODO 74 에서 겪은 것). 그래서 (팀, 사람) 한 쌍이 한 줄이다.
--
-- 담당자를 아직 모르면 person 이 빈 문자열인 줄 하나로 팀만 남는다 —
-- 팀은 정해졌는데 사람은 나중에 정해지는 일이 흔하다.
CREATE TABLE IF NOT EXISTS project_partner (
  project_id TEXT REFERENCES project(id) ON DELETE CASCADE,
  team       TEXT NOT NULL,
  person     TEXT NOT NULL DEFAULT '',
  position   INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(project_id, team, person)
);

CREATE INDEX IF NOT EXISTS idx_partner_team ON project_partner(team);
CREATE INDEX IF NOT EXISTS idx_partner_person ON project_partner(person);

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
  date       TEXT NOT NULL,          -- 시작일. 연도 집계도 이 날짜를 본다
  -- 2~3일에 걸친 교육을 위한 종료일. 하루짜리면 비어 있다 (옵션)
  end_date   TEXT,
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
