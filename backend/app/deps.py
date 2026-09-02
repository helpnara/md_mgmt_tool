"""요청별 DB 커넥션. 서버 확장 시 인증 의존성이 붙을 자리이기도 하다."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator

from .db import open_index

_conn: sqlite3.Connection | None = None


def setup() -> tuple[sqlite3.Connection, bool]:
    """(커넥션, 인덱스를 새로 만들었는지) 를 돌려준다."""
    global _conn
    _conn, rebuilt = open_index()
    return _conn, rebuilt


def teardown() -> None:
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None


def get_db() -> Iterator[sqlite3.Connection]:
    if _conn is None:
        raise RuntimeError("DB가 초기화되지 않았습니다.")
    yield _conn
