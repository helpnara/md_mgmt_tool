"""SQLite 인덱스. 파생 데이터이므로 언제든 파일에서 재생성할 수 있다."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import get_settings

SCHEMA_PATH = Path(__file__).with_name("vault") / "schema.sql"

# 한국어 부분 문자열 검색을 위해 trigram을 쓰되, 구버전 SQLite에서는 unicode61로 물러난다.
_FTS_TRIGRAM = """
CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
  kind, ref_id UNINDEXED, project_id UNINDEXED, title, body,
  tokenize = "trigram"
);
"""
_FTS_FALLBACK = """
CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
  kind, ref_id UNINDEXED, project_id UNINDEXED, title, body
);
"""


def open_index(db_path: Path | None = None) -> tuple[sqlite3.Connection, bool]:
    """색인을 연다. 구조가 바뀌었거나 파일이 깨졌으면 새로 만든다.

    색인은 md 파일에서 다시 만들 수 있는 파생물이므로, 문제가 생기면
    사용자를 막아 세우는 대신 버리고 다시 만드는 편이 낫다.
    """
    path = db_path or get_settings().db_path
    try:
        conn = connect(path)
        return conn, init_schema(conn)
    except sqlite3.DatabaseError:
        # 파일이 손상됐거나 SQLite가 읽지 못하는 상태 — 지우고 다시 만든다.
        for suffix in ("", "-wal", "-shm"):
            Path(str(path) + suffix).unlink(missing_ok=True)
        conn = connect(path)
        init_schema(conn)
        return conn, True


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    # 쓰는 요청이 겹치면 SQLite 는 곧바로 "database is locked" 를 낸다.
    # 사람이 저장 단추를 누르는 속도에서는 잠깐 기다렸다 쓰는 편이 언제나 낫다.
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


# 인덱스 구조를 바꿀 때마다 하나씩 올린다.
# 값이 달라지면 인덱스를 통째로 다시 만든다 — 원본은 md 파일이므로 잃을 것이 없다.
SCHEMA_VERSION = 6  # 6: 검색 색인에 보고 문서·태그·담당자를 넣음 (TODO 53)


def _drop_everything(conn: sqlite3.Connection) -> None:
    """기존 인덱스 테이블을 모두 지운다 (파생 데이터라 안전하다)."""
    conn.execute("PRAGMA foreign_keys = OFF")
    for kind in ("view", "table"):
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = ? AND name NOT LIKE 'sqlite_%'",
            (kind,),
        ).fetchall()
        for row in rows:
            conn.execute(f'DROP {kind.upper()} IF EXISTS "{row[0]}"')
    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")


def init_schema(conn: sqlite3.Connection) -> bool:
    """스키마를 준비한다. 구조가 바뀌어 다시 만들었으면 True를 돌려준다.

    'CREATE TABLE IF NOT EXISTS' 만으로는 예전에 만들어 둔 DB에 새 컬럼이
    추가되지 않는다. 버전을 확인해 어긋나면 인덱스를 새로 만든다.
    """
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    rebuilt = False
    if current != SCHEMA_VERSION:
        has_tables = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' LIMIT 1"
        ).fetchone()
        if has_tables:
            _drop_everything(conn)
            rebuilt = True

    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        conn.executescript(_FTS_TRIGRAM)
    except sqlite3.OperationalError:
        conn.executescript(_FTS_FALLBACK)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
    return rebuilt
