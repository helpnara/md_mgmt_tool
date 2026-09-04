"""요청마다 새 DB 커넥션.

**하나를 돌려쓰면 안 된다.** FastAPI 는 동기 엔드포인트를 스레드 풀에서 돌리므로
요청 여러 건이 동시에 흐른다. 그때 커넥션 하나를 나눠 쓰면 두 가지가 터진다.

  · 한쪽이 커서를 훑는 도중 다른 쪽이 커밋하면 그 커서가 끊긴다
    → `sqlite3.ProgrammingError: bad parameter or other API misuse` (실사용에서 나온 500)
  · 같은 커넥션이면 **아직 커밋하지 않은 중간 상태까지 보인다.**
    재인덱싱이 과제를 지웠다 다시 넣는 사이에 다른 요청이 읽으면 빈 결과를 본다

요청마다 커넥션을 따로 열면 둘 다 사라진다. WAL 이라 읽는 쪽은 서로를 막지 않고,
각자 **마지막으로 커밋된 상태**만 본다. 여는 비용은 마이크로초 단위다.

`_conn` 은 기동 때 한 번 쓰는 것(색인 점검·재작성)과 뒤에서 도는 백업용으로만 남긴다.
"""
from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator

from fastapi import Request

from .db import connect, open_index

_conn: sqlite3.Connection | None = None

# 쓰는 요청은 한 번에 하나씩만 흐르게 한다.
#
# SQLite 는 읽던 커넥션이 쓰기로 올라설 때 다른 쪽이 이미 쓰고 있으면 **기다리지 않고**
# 곧바로 "database is locked" 를 낸다 (busy_timeout 이 듣지 않는 구간이다).
# 게다가 두 쓰기가 겹치면 논리적으로도 어긋난다 — 과제를 만드는 사이에 전체 재인덱싱이
# 끼어들면, 방금 만든 과제를 "폴더에 없던 것"으로 보고 색인에서 지워 버린다.
#
# 이 도구는 한 사람이 쓴다. 쓰기를 줄 세워도 잃는 것이 없고, 이 두 가지가 함께 사라진다.
# 읽기는 그대로 동시에 흐른다 (WAL 이라 서로를 막지 않는다).
_write_lock = threading.Lock()

# 읽기만 하는 메서드. 나머지는 모두 쓰기로 본다.
_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def setup() -> tuple[sqlite3.Connection, bool]:
    """기동용 커넥션. 색인 구조를 점검하고 필요하면 다시 만든다."""
    global _conn
    _conn, rebuilt = open_index()
    return _conn, rebuilt


def teardown() -> None:
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None


def get_db(request: Request) -> Iterator[sqlite3.Connection]:
    """이 요청만 쓰는 커넥션. 끝나면 닫는다. 쓰는 요청이면 순서를 기다린다."""
    if _conn is None:
        raise RuntimeError("DB가 초기화되지 않았습니다.")

    writing = request.method not in _READ_METHODS
    if writing:
        _write_lock.acquire()
    try:
        conn = connect()
        try:
            yield conn
        finally:
            conn.close()
    finally:
        if writing:
            _write_lock.release()
