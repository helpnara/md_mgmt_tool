"""프로그램을 새 버전으로 바꿨을 때, 예전에 만들어 둔 색인이 걸림돌이 되면 안 된다."""
from __future__ import annotations

import sqlite3

import pytest

from app.db import SCHEMA_VERSION, connect, init_schema, open_index

# 업데이트 전 버전이 쓰던 project 테이블 (type 컬럼이 없다)
OLD_SCHEMA = """
CREATE TABLE project (
  id TEXT PRIMARY KEY, dir_name TEXT, title TEXT, status TEXT, grp TEXT, owner TEXT,
  start_date TEXT, due_date TEXT, created_at TEXT, updated_at TEXT,
  last_reported_at TEXT, body TEXT, file_mtime REAL
);
CREATE TABLE entry (id INTEGER PRIMARY KEY, project_id TEXT, rel_path TEXT, date TEXT,
                    title TEXT, body TEXT, created_at TEXT, updated_at TEXT, file_mtime REAL);
"""


def make_old_database(path):
    conn = sqlite3.connect(path)
    conn.executescript(OLD_SCHEMA)
    conn.execute(
        "INSERT INTO project(id, title, status) VALUES ('2026-001', '예전 과제', 'plan_report')"
    )
    conn.commit()
    conn.close()


def test_old_index_is_rebuilt_instead_of_breaking(tmp_path):
    """'table project has no column named type' 오류로 실행이 막히던 상황."""
    path = tmp_path / "index.sqlite3"
    make_old_database(path)

    conn = connect(path)
    assert init_schema(conn) is True  # 구조가 어긋나 다시 만들었다

    columns = [row[1] for row in conn.execute("PRAGMA table_info(project)")]
    assert "type" in columns
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION

    # 새 컬럼을 쓰는 쓰기가 정상 동작한다.
    conn.execute(
        "INSERT INTO project(id, dir_name, title, status, type) VALUES (?, ?, ?, ?, ?)",
        ("2026-001", "2026-001-x", "새 과제", "in_progress", "rnd"),
    )
    conn.commit()


def test_current_index_is_left_alone(tmp_path):
    """이미 최신 구조면 굳이 다시 만들지 않는다."""
    path = tmp_path / "index.sqlite3"
    conn = connect(path)
    assert init_schema(conn) is False  # 처음 만드는 경우
    conn.close()

    again = connect(path)
    assert init_schema(again) is False  # 두 번째 실행에서도 그대로 둔다


def test_data_comes_back_after_a_rebuild(client, vault_dir):
    """색인을 다시 만들어도 과제·진행일지는 md 파일에서 그대로 복구된다."""
    project = client.post(
        "/api/projects", json={"title": "복구 확인", "type": "smart", "owners": ["권경락"]}
    ).json()
    client.post(
        f"/api/projects/{project['id']}/entries", json={"date": "2026-09-03", "title": "기록"}
    )

    from app import deps

    deps.teardown()
    db_path = vault_dir / ".index" / "index.sqlite3"
    # 예전 버전이 남긴 색인처럼 만들어 둔다.
    sqlite3.connect(db_path).close()
    db_path.unlink()
    make_old_database(db_path)

    conn = connect(db_path)
    assert init_schema(conn) is True
    deps._conn = conn

    assert client.post("/api/reindex").json()["indexed"] == 1
    restored = client.get(f"/api/projects/{project['id']}").json()
    assert restored["title"] == "복구 확인"
    assert restored["type"] == "smart"
    assert restored["owners"] == ["권경락"]
    assert len(client.get(f"/api/projects/{project['id']}/entries").json()) == 1


def test_broken_index_file_is_thrown_away_and_remade(tmp_path):
    """색인 파일이 깨져도 실행이 막히면 안 된다 — 버리고 다시 만든다."""
    path = tmp_path / "index.sqlite3"
    path.write_bytes(b"not a database at all")

    conn, rebuilt = open_index(path)
    assert rebuilt is True
    columns = [row[1] for row in conn.execute("PRAGMA table_info(project)")]
    assert "type" in columns


def test_old_index_is_upgraded_through_the_normal_entry_point(tmp_path):
    path = tmp_path / "index.sqlite3"
    make_old_database(path)
    conn, rebuilt = open_index(path)
    assert rebuilt is True
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
