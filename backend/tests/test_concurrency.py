"""여러 요청이 동시에 흐를 때 (실사용에서 나온 500 · 목록이 나왔다 안 나왔다).

FastAPI 는 동기 엔드포인트를 **스레드 풀**에서 돌리므로 요청 여러 건이 겹친다.
예전에는 커넥션 하나를 나눠 써서 두 가지가 터졌다.

  · 한쪽이 커서를 훑는 도중 다른 쪽이 커밋 → `bad parameter or other API misuse`
  · 아직 커밋하지 않은 중간 상태가 다른 요청에 보임 → 목록이 잠깐 비어 보임

이 시험은 **부하 시험이 아니다.** 커넥션이 요청마다 따로인지, 쓰기가 줄을 서는지를
확인한다 — 그 두 가지가 지켜지면 위 증상은 생기지 않는다.
"""
from __future__ import annotations

import sqlite3
import threading

from app import deps


def test_each_request_gets_its_own_connection(client):
    """커넥션을 돌려쓰면 서로의 중간 상태를 본다. 요청마다 따로여야 한다.

    두 요청이 **동시에 살아 있는 상태**로 견준다. 하나를 닫고 다음을 열면
    파이썬이 같은 자리를 다시 쓸 수 있어 비교가 무의미해진다.
    """
    class FakeRequest:
        method = "GET"

    first, second = deps.get_db(FakeRequest()), deps.get_db(FakeRequest())
    conn_a, conn_b = next(first), next(second)
    try:
        assert conn_a is not conn_b, "두 요청이 같은 커넥션을 받았습니다"
        # 기동용 커넥션과도 달라야 한다.
        assert conn_a is not deps._conn
    finally:
        for generator in (first, second):
            for _ in generator:
                pass


def test_the_request_connection_is_closed_afterwards(client):
    """열어 두고 닫지 않으면 오래 쓸수록 파일 핸들이 쌓인다."""
    class FakeRequest:
        method = "GET"

    generator = deps.get_db(FakeRequest())
    conn = next(generator)
    conn.execute("SELECT 1")
    for _ in generator:  # 의존성 정리 단계
        pass
    try:
        conn.execute("SELECT 1")
    except sqlite3.ProgrammingError:
        return
    raise AssertionError("커넥션이 닫히지 않았습니다")


def test_writes_take_turns(client):
    """쓰기가 겹치면 SQLite 가 곧바로 'database is locked' 를 낸다. 줄을 서야 한다."""
    class Write:
        method = "POST"

    first = deps.get_db(Write())
    next(first)  # 자물쇠를 쥔 상태

    started = threading.Event()
    entered = threading.Event()

    def second():
        started.set()
        generator = deps.get_db(Write())
        next(generator)
        entered.set()
        for _ in generator:
            pass

    thread = threading.Thread(target=second, daemon=True)
    thread.start()
    started.wait(2)
    assert not entered.wait(0.3), "앞선 쓰기가 끝나기 전에 두 번째가 들어왔습니다"

    for _ in first:  # 첫 번째가 끝난다
        pass
    assert entered.wait(2), "앞이 끝났는데도 두 번째가 못 들어왔습니다"
    thread.join(2)


def test_reads_do_not_wait_for_each_other(client):
    """읽기까지 줄 세우면 화면이 느려진다. WAL 이라 서로를 막을 이유가 없다."""
    class Read:
        method = "GET"

    first = deps.get_db(Read())
    next(first)

    entered = threading.Event()

    def second():
        generator = deps.get_db(Read())
        next(generator)
        entered.set()
        for _ in generator:
            pass

    thread = threading.Thread(target=second, daemon=True)
    thread.start()
    assert entered.wait(2), "읽기가 서로를 막고 있습니다"
    for _ in first:
        pass
    thread.join(2)


def test_a_write_that_fails_still_releases_the_turn(client):
    """예외가 나도 자물쇠를 놓아야 한다. 안 놓으면 그다음부터 모든 쓰기가 멈춘다."""
    class Write:
        method = "POST"

    generator = deps.get_db(Write())
    next(generator)
    try:
        generator.throw(RuntimeError("저장 중 오류"))
    except RuntimeError:
        pass

    # 다음 쓰기가 곧바로 들어갈 수 있어야 한다.
    assert deps._write_lock.acquire(timeout=1), "자물쇠가 풀리지 않았습니다"
    deps._write_lock.release()


def test_a_write_request_still_reaches_the_database(client):
    """줄을 세우느라 정작 저장이 안 되면 안 된다."""
    response = client.post("/api/projects", json={"title": "동시성 시험 과제"})
    assert response.status_code == 201
    assert [row["title"] for row in client.get("/api/projects").json()] == ["동시성 시험 과제"]
