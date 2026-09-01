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


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        conn.executescript(_FTS_TRIGRAM)
    except sqlite3.OperationalError:
        conn.executescript(_FTS_FALLBACK)
    conn.commit()
