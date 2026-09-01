"""요청별 DB 커넥션. 서버 확장 시 인증 의존성이 붙을 자리이기도 하다."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator

from .db import connect, init_schema

_conn: sqlite3.Connection | None = None


def setup() -> sqlite3.Connection:
    global _conn
    _conn = connect()
    init_schema(_conn)
    return _conn


def teardown() -> None:
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None


def get_db() -> Iterator[sqlite3.Connection]:
    if _conn is None:
        raise RuntimeError("DB가 초기화되지 않았습니다.")
    yield _conn
