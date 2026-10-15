"""전수 점검(2026-10-15)에서 재현된 데이터 손상 · 500 · 기동 실패 — TODO 198 · 199 · 200 · 201-⑦.

점검 때 쓴 재현 스크립트(docs/review/전수점검-2026-10-15/)를 백엔드 시험으로 옮긴 것이다 — 646 건 중 어느 것도
이것들을 잡지 못했다. 잠김은 윈도우에서만 나므로 `paths.move` · `os.replace` 를 바꿔 끼워 흉내 낸다.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.vault import markdown as md  # noqa: E402
from app.vault import paths  # noqa: E402

BOM = b"\xef\xbb\xbf"


def _korean(text: str) -> bool:
    return any("가" <= ch <= "힣" for ch in text)


def _index_md(vault_dir: Path, project_id: str) -> Path:
    return next((vault_dir / "projects").glob(f"{project_id}-*")) / "index.md"


def _problems(client) -> list[dict]:
    return client.get("/api/meta").json()["problems"]


def _lock_moves(monkeypatch):
    """윈도우에서 엑셀이 폴더 · 파일을 잡고 있는 상태."""

    def refuse(source, target):
        raise paths.FileInUseError(f"'{Path(source).name}' 을(를) 다른 프로그램이 사용 중이라 옮길 수 없습니다.")

    monkeypatch.setattr(paths, "move", refuse)


# ── 198 · BOM · 머리 정보 없는 index.md ──────────────────────────────────────────────


def test_loads_strips_a_leading_bom():
    doc = md.loads("﻿---\ntitle: 비오엠\nowners: [홍길동]\n---\n\n본문\n")
    assert doc.meta == {"title": "비오엠", "owners": ["홍길동"]}
    assert doc.body.strip() == "본문"


def test_bom_index_md_keeps_its_meta_through_reindex_and_patch(client, vault_dir):
    """메모장이 BOM 을 붙여 저장한 index.md — 전에는 빈 과제가 되고 상태 하나 바꾸면 머리 정보가 본문으로 밀려났다."""
    made = client.post(
        "/api/projects",
        json={"title": "비오엠", "start_date": "2026-01-01", "due_date": "2026-12-31", "owners": ["홍길동"],
              "effect_expected": 12.5},
    ).json()
    index = _index_md(vault_dir, made["id"])
    index.write_bytes(BOM + index.read_bytes())

    result = client.post("/api/reindex")
    assert result.status_code == 200
    bom_problems = [item for item in result.json()["problems"] if "BOM" in item["reason"]]
    assert bom_problems and bom_problems[0]["path"].endswith("index.md")
    assert any("BOM" in item["reason"] for item in _problems(client))

    got = client.get(f"/api/projects/{made['id']}").json()
    assert (got["title"], got["owners"], got["effect_expected"], got["due_date"]) == ("비오엠", ["홍길동"], 12.5, "2026-12-31")

    assert client.patch(f"/api/projects/{made['id']}", json={"status": "on_hold"}).status_code == 200
    text = index.read_text(encoding="utf-8")
    assert text.startswith("---\n")  # BOM 없이 다시 쓰였다
    assert "title: 비오엠" in text and "- 홍길동" in text and "effect_expected: 12.5" in text
    assert "status: on_hold" in text
    # 이 도구로 한 번 저장했으니 BOM 경고도 사라진다
    assert not any("BOM" in item["reason"] for item in _problems(client))
    got = client.get(f"/api/projects/{made['id']}").json()
    assert (got["title"], got["owners"], got["status"]) == ("비오엠", ["홍길동"], "on_hold")


def test_index_md_without_front_matter_is_reported_not_indexed_as_an_empty_project(client, vault_dir):
    made = client.post("/api/projects", json={"title": "머리 없음", "owners": ["김담당"]}).json()
    other = client.post("/api/projects", json={"title": "멀쩡함"}).json()
    index = _index_md(vault_dir, made["id"])
    index.write_text("# 그냥 글\n\n머리 정보가 없는 파일\n", encoding="utf-8")

    result = client.post("/api/reindex")
    assert result.status_code == 200
    reasons = [item["reason"] for item in result.json()["problems"] if item["path"].endswith("index.md")]
    assert reasons and all(_korean(reason) for reason in reasons)
    assert any("front matter" in reason and "BOM" in reason for reason in reasons)

    # 직전에 색인한 내용은 그대로 — 제목이 폴더명으로, 담당이 빈칸으로 바뀌지 않는다
    ids = [item["id"] for item in client.get("/api/projects").json()]
    assert made["id"] in ids and other["id"] in ids
    got = client.get(f"/api/projects/{made['id']}").json()
    assert (got["title"], got["owners"]) == ("머리 없음", ["김담당"])


def test_front_matter_that_parses_to_nothing_is_also_reported(client, vault_dir):
    made = client.post("/api/projects", json={"title": "빈 머리"}).json()
    _index_md(vault_dir, made["id"]).write_text("---\n---\n\n본문만\n", encoding="utf-8")
    result = client.post("/api/reindex").json()
    assert any(item["path"].endswith("index.md") and "front matter" in item["reason"] for item in result["problems"])
    assert client.get(f"/api/projects/{made['id']}").json()["title"] == "빈 머리"


def test_save_refuses_to_overwrite_front_matter_with_an_empty_meta(tmp_path):
    path = tmp_path / "index.md"
    original = "---\ntitle: 지켜야 함\nowners:\n- 홍길동\n---\n\n본문\n"
    path.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError) as caught:
        md.save(path, md.MarkdownDoc({}, "덮어쓰려는 본문"))
    assert _korean(str(caught.value)) and "front matter" in str(caught.value)
    assert path.read_text(encoding="utf-8") == original

    # 원래 머리 정보가 없는 파일은 그대로 저장된다 (본문만 있는 메모)
    plain = tmp_path / "plain.md"
    plain.write_text("그냥 글\n", encoding="utf-8")
    md.save(plain, md.MarkdownDoc({}, "바뀐 글"))
    assert plain.read_text(encoding="utf-8") == "바뀐 글\n"


# ── 199 · 손으로 고친 id · 재색인은 멈추지 않고 · 기동은 안 죽는다 ──────────────────────────


def _fresh_app(vault: Path):
    os.environ["MD_MGMT_VAULT"] = str(vault)
    from app.config import get_settings

    get_settings.cache_clear()
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def test_hand_edited_id_reindexes_with_a_warning_and_the_app_restarts(tmp_path, monkeypatch):
    """index.md 의 `id:` 를 손으로 고치면 — 전에는 재색인 500(dir_name UNIQUE), 재시작은 IntegrityError 로 안 켜졌다."""
    monkeypatch.setenv("MD_MGMT_VAULT", str(tmp_path / "vault"))
    vault = tmp_path / "vault"
    with _fresh_app(vault) as client:
        made = client.post("/api/projects", json={"title": "손으로 고침"}).json()
        index = _index_md(vault, made["id"])
        index.write_text(index.read_text(encoding="utf-8").replace(f"id: {made['id']}", "id: 2026-007"), encoding="utf-8")

        result = client.post("/api/reindex")
        assert result.status_code == 200
        body = result.json()
        assert body["indexed"] == 1
        assert any("2026-007" in item["reason"] and _korean(item["reason"]) for item in body["problems"])
        assert [item["id"] for item in client.get("/api/projects").json()] == ["2026-007"]
        assert client.get("/api/projects/2026-007").json()["title"] == "손으로 고침"
        assert client.get(f"/api/projects/{made['id']}").status_code == 404

    # 같은 vault 로 다시 켠다 — lifespan 의 기동 재색인이 살아남아야 한다
    with _fresh_app(vault) as client:
        assert [item["id"] for item in client.get("/api/projects").json()] == ["2026-007"]
        assert any("2026-007" in item["reason"] for item in _problems(client))

    from app.config import get_settings

    get_settings.cache_clear()


def test_reindex_continues_past_a_folder_that_raises(client, vault_dir, monkeypatch):
    first = client.post("/api/projects", json={"title": "사고 나는 폴더"}).json()
    second = client.post("/api/projects", json={"title": "멀쩡한 폴더"}).json()
    from app.vault import indexer

    real = indexer.index_project

    def flaky(conn, project_dir, problems=None):
        if project_dir.name.startswith(first["id"]):
            raise sqlite3.IntegrityError("UNIQUE constraint failed: project.dir_name")
        return real(conn, project_dir, problems)

    monkeypatch.setattr(indexer, "index_project", flaky)
    result = client.post("/api/reindex")
    assert result.status_code == 200
    body = result.json()
    folder = [item for item in body["problems"] if first["id"] in item["path"]]
    assert folder and "IntegrityError" in folder[0]["reason"] and _korean(folder[0]["reason"])
    # 사고 난 폴더의 색인 줄은 지워지지 않고, 나머지는 정상 색인
    ids = {item["id"] for item in client.get("/api/projects").json()}
    assert ids == {first["id"], second["id"]}


def test_startup_drops_the_index_and_retries_once_when_reindex_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MD_MGMT_VAULT", str(tmp_path / "vault"))
    from app import main as main_module

    real = main_module.reindex_all
    calls = {"n": 0}

    def fails_once(conn):
        calls["n"] += 1
        if calls["n"] == 1:
            raise sqlite3.IntegrityError("UNIQUE constraint failed: project.dir_name")
        return real(conn)

    monkeypatch.setattr(main_module, "reindex_all", fails_once)
    with _fresh_app(tmp_path / "vault") as client:
        assert client.get("/api/projects").status_code == 200
    assert calls["n"] == 2
    out = capsys.readouterr().out
    assert "색인을 버리고" in out and "IntegrityError" in out
    from app.config import get_settings

    get_settings.cache_clear()


def test_startup_reraises_when_the_retry_also_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MD_MGMT_VAULT", str(tmp_path / "vault"))
    from app import main as main_module

    def always(conn):
        raise ValueError("projects/2026-001-깨짐/index.md: 읽을 수 없음")

    monkeypatch.setattr(main_module, "reindex_all", always)
    with pytest.raises(ValueError):
        with _fresh_app(tmp_path / "vault"):
            pass
    out = capsys.readouterr().out
    assert "2026-001-깨짐" in out and "다시 켜 주세요" in out
    from app import deps
    from app.config import get_settings

    deps.teardown()
    get_settings.cache_clear()


def test_corrupt_index_recovery_closes_the_failed_connection_before_deleting(tmp_path, monkeypatch):
    """윈도우는 열려 있는 sqlite 파일을 지우지 못한다 — 복구 경로가 커넥션을 먼저 닫아야 한다."""
    from app import db

    opened: list[sqlite3.Connection] = []
    real_connect = db.connect

    def tracking_connect(path=None):
        conn = real_connect(path)
        opened.append(conn)
        return conn

    real_init = db.init_schema
    state = {"failed": False}

    def failing_init(conn):
        if not state["failed"]:
            state["failed"] = True
            raise sqlite3.DatabaseError("file is not a database")
        return real_init(conn)

    monkeypatch.setattr(db, "connect", tracking_connect)
    monkeypatch.setattr(db, "init_schema", failing_init)
    conn, rebuilt = db.open_index(tmp_path / ".index" / "index.sqlite")
    assert rebuilt is True and len(opened) == 2
    with pytest.raises(sqlite3.ProgrammingError):  # 첫 커넥션은 닫혀 있다
        opened[0].execute("SELECT 1")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    conn.close()


# ── 200 · 잠김 · 바깥 수정 · 파일 없음을 한 곳에서 ─────────────────────────────────────


def test_project_rename_blocked_by_a_lock_is_423_and_the_retry_succeeds(client, vault_dir, monkeypatch):
    made = client.post("/api/projects", json={"title": "원래 제목"}).json()
    assert client.get("/api/projects").json()[0]["title"] == "원래 제목"  # 읽기 캐시를 채워 둔다

    _lock_moves(monkeypatch)
    first = client.patch(f"/api/projects/{made['id']}", json={"title": "바뀐 제목"})
    assert first.status_code == 423 and _korean(first.json()["detail"])
    # 파일은 이미 저장됐다 — 실패로 끝난 쓰기도 캐시를 비워 목록이 바로 새 제목을 보인다
    assert client.get("/api/projects").json()[0]["title"] == "바뀐 제목"
    assert client.get(f"/api/projects/{made['id']}").json()["title"] == "바뀐 제목"

    monkeypatch.undo()
    # 엑셀을 닫고 다시 저장 — 전에는 file_mtime 이 옛값이라 [다시 읽기] 를 눌러도 영영 409 였다
    retry = client.patch(f"/api/projects/{made['id']}", json={"status": "done"})
    assert retry.status_code == 200, retry.text
    assert retry.json()["title"] == "바뀐 제목" and retry.json()["status"] == "done"
    assert (vault_dir / "projects" / f"{made['id']}-바뀐-제목" / "index.md").is_file()


def test_entry_rename_blocked_by_a_lock_is_423_not_500_and_the_retry_succeeds(client, monkeypatch):
    made = client.post("/api/projects", json={"title": "과제"}).json()
    entry = client.post(f"/api/projects/{made['id']}/entries", json={"title": "기록 하나", "date": "2026-01-05"}).json()

    _lock_moves(monkeypatch)
    first = client.patch(f"/api/entries/{entry['id']}", json={"title": "기록 둘"})
    assert first.status_code == 423 and _korean(first.json()["detail"])
    monkeypatch.undo()

    retry = client.patch(f"/api/entries/{entry['id']}", json={"body": "다시 저장"})
    assert retry.status_code == 200, retry.text
    assert retry.json()["title"] == "기록 둘" and retry.json()["rel_path"].endswith("2026-01-05-기록-둘.md")


def test_report_date_move_blocked_by_a_lock_is_423_and_the_retry_succeeds(client, monkeypatch):
    made = client.post("/api/projects", json={"title": "과제"}).json()
    report = client.post(f"/api/projects/{made['id']}/reports/draft", json={"report_date": "2026-03-03"}).json()

    _lock_moves(monkeypatch)
    first = client.patch(f"/api/reports/{report['id']}", json={"report_date": "2026-03-10"})
    assert first.status_code == 423 and _korean(first.json()["detail"])
    monkeypatch.undo()

    retry = client.patch(f"/api/reports/{report['id']}", json={"audience": "팀장"})
    assert retry.status_code == 200, retry.text
    # 날짜는 파일대로 — 폴더 이름만 옛 날짜로 남는다(색인은 머리 정보의 report_date 를 읽는다)
    assert retry.json()["report_date"] == "2026-03-10" and retry.json()["audience"] == "팀장"


def test_locked_md_on_save_is_423_with_a_korean_message(client, monkeypatch):
    """md 를 다른 프로그램이 잡고 있으면 os.replace 가 PermissionError — 전에는 모든 PATCH/POST 가 500."""
    made = client.post("/api/projects", json={"title": "잠긴 파일"}).json()

    def refuse(src, dst):
        raise PermissionError(13, "[WinError 32] The process cannot access the file")

    monkeypatch.setattr(md.os, "replace", refuse)
    response = client.patch(f"/api/projects/{made['id']}", json={"status": "done"})
    assert response.status_code == 423
    assert "다른 프로그램" in response.json()["detail"] and "index.md" in response.json()["detail"]


def test_a_bare_permission_error_from_a_service_is_423_korean(client, monkeypatch):
    from app.services import projects as svc

    def denied(conn, project_id, updates):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(svc, "update_project", denied)
    made = client.post("/api/projects", json={"title": "권한"}).json()
    response = client.patch(f"/api/projects/{made['id']}", json={"status": "done"})
    assert response.status_code == 423 and "다른 프로그램이 파일을 쓰고 있습니다" in response.json()["detail"]


def test_project_folder_removed_in_explorer_gives_409_korean_not_500(client, vault_dir):
    made = client.post("/api/projects", json={"title": "외부삭제"}).json()
    entry = client.post(f"/api/projects/{made['id']}/entries", json={"title": "일지", "date": "2026-03-01"}).json()
    report = client.post(f"/api/projects/{made['id']}/reports/draft", json={"report_date": "2026-03-02"}).json()
    folder = vault_dir / "projects" / client.get(f"/api/projects/{made['id']}").json()["dir_name"]
    shutil.rmtree(folder)

    for response in (
        client.patch(f"/api/projects/{made['id']}", json={"title": "x"}),
        client.patch(f"/api/projects/{made['id']}", json={"body": "x"}),
        client.post(f"/api/projects/{made['id']}/entries", json={"title": "x"}),
        client.patch(f"/api/entries/{entry['id']}", json={"body": "x"}),
        client.delete(f"/api/entries/{entry['id']}"),
        client.patch(f"/api/reports/{report['id']}", json={"body": "x"}),
        client.post(f"/api/reports/{report['id']}/freeze"),
        client.delete(f"/api/reports/{report['id']}"),
        client.post(f"/api/projects/{made['id']}/reports/draft", json={}),
    ):
        assert response.status_code == 409, response.text
        assert "파일이 폴더에 없습니다" in response.json()["detail"] and "[다시 읽기]" in response.json()["detail"]
    # 지워진 폴더를 되살리지 않는다 (유령 폴더)
    assert not folder.exists()
    # [다시 읽기] 로 맞춘다
    client.post("/api/reindex")
    assert client.get(f"/api/projects/{made['id']}").status_code == 404


def test_entry_file_removed_in_explorer_gives_409_korean(client, vault_dir):
    made = client.post("/api/projects", json={"title": "일지삭제"}).json()
    entry = client.post(f"/api/projects/{made['id']}/entries", json={"title": "파일삭제", "date": "2026-04-01"}).json()
    dir_name = client.get(f"/api/projects/{made['id']}").json()["dir_name"]
    (vault_dir / "projects" / dir_name / entry["rel_path"]).unlink()

    for response in (
        client.patch(f"/api/entries/{entry['id']}", json={"body": "x"}),
        client.delete(f"/api/entries/{entry['id']}"),
    ):
        assert response.status_code == 409 and "파일이 폴더에 없습니다" in response.json()["detail"]


def test_a_failed_write_still_invalidates_the_read_cache(client, monkeypatch):
    """4xx 로 끝난 쓰기도 파일을 건드렸을 수 있다 — 423 뒤 목록이 5초 동안 옛값이면 안 된다."""
    made = client.post("/api/projects", json={"title": "캐시"}).json()
    client.post(f"/api/projects/{made['id']}/entries", json={"title": "첫 기록"})
    assert client.get("/api/projects").json()[0]["entry_count"] == 1  # 캐시에 들어간다

    from app.services import entries as entries_service

    real = entries_service.create_entry

    def save_then_fail(conn, project_id, data):
        real(conn, project_id, data)
        raise paths.FileInUseError("busy")

    monkeypatch.setattr(entries_service, "create_entry", save_then_fail)
    assert client.post(f"/api/projects/{made['id']}/entries", json={"title": "둘째 기록"}).status_code == 423
    assert client.get("/api/projects").json()[0]["entry_count"] == 2


# ── 201-⑦ · 거절된 생성은 폴더도 번호도 남기지 않는다 ────────────────────────────────────


def test_rejected_create_leaves_no_folder_and_consumes_no_number(client, vault_dir):
    before = client.get("/api/projects/next-id").json()["id"]
    projects = vault_dir / "projects"

    for payload in (
        {"title": "효과 음수", "effect_expected": -1},
        {"title": "실증 음수", "effect_verified": -0.5},
        {"title": "완료일 형식", "completed_at": "2026/01/01"},
        {"title": "없는 상태", "status": "flying"},
        {"title": "없는 속성", "type": "no-such-type"},
        {"title": "없는 선행", "predecessors": ["2020-999"]},
        {"title": "   "},
    ):
        response = client.post("/api/projects", json=payload)
        assert response.status_code == 400, (payload, response.text)
        assert _korean(response.json()["detail"])
        assert [child.name for child in projects.iterdir() if child.is_dir()] == [], payload

    assert client.get("/api/projects/next-id").json()["id"] == before
    made = client.post("/api/projects", json={"title": "정상"}).json()
    assert made["id"] == before  # 거절된 시도들이 번호를 쓰지 않았다
