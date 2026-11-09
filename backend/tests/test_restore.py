"""전체 백업 ZIP 에서 되살리기 (TODO 246) — 새 서버로 옮길 때."""
from __future__ import annotations

import io
import tempfile
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings


@pytest.fixture(autouse=True)
def own_temp(tmp_path, monkeypatch):
    """올린 파일 · 비상 백업이 시스템 임시 폴더에 섞이지 않게"""
    temp = tmp_path / "tmp"
    temp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp))


def _upload(client, data: bytes, name: str = "과제이력-전체백업-20261101.zip"):
    return client.post("/api/backup/restore/inspect", files={"file": (name, data, "application/zip")})


def _zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return buffer.getvalue()


def _titles(client) -> set[str]:
    return {item["title"] for item in client.get("/api/projects").json()}


def test_round_trip_backup_then_restore_replaces_data_and_keeps_safety_copy(client, vault_dir):
    client.put("/api/people", json={"people": [{"name": "가팀원"}, {"name": "나팀원"}]})
    kept = client.post("/api/projects", json={"title": "옮길 과제", "owners": ["가팀원"], "status": "in_progress"}).json()
    client.post(f"/api/projects/{kept['id']}/entries", json={"date": "2026-10-01", "title": "옮길 일지"})
    backup = client.get("/api/backup").content

    # 백업 뒤에 생긴 것 — 되살리면 사라져야 한다(합치지 않고 바꾼다)
    client.post("/api/projects", json={"title": "나중 과제", "owners": ["나팀원"], "status": "in_progress"})
    assert _titles(client) == {"옮길 과제", "나중 과제"}

    report = _upload(client, backup).json()
    assert report["ok"] and report["token"]
    assert report["projects"] == 1 and report["settings"] is True and report["date"] == "2026-11-01"
    assert report["current"]["projects"] == 2 and report["current"]["has_data"] is True

    done = client.post("/api/backup/restore", json={"token": report["token"]})
    assert done.status_code == 200, done.text
    result = done.json()
    assert result["projects"] == 1
    assert _titles(client) == {"옮길 과제"}
    entries = client.get(f"/api/projects/{kept['id']}/entries").json()
    assert "옮길 일지" in str(entries)
    # 지금 데이터는 먼저 통째로 — 그 안에 '나중 과제' 가 있다
    safety = result["safety_backup"]
    assert safety and "과제이력-되살리기전-" in safety
    with zipfile.ZipFile(safety) as archive:
        assert any("나중 과제" in name or "index.md" in name for name in archive.namelist())
        assert len([n for n in archive.namelist() if n.endswith("/index.md") and n.startswith("projects/")]) == 2
    # 작업 자리는 치웠고, 같은 표로 두 번은 안 된다
    assert not (vault_dir / ".restoring").exists()
    assert client.post("/api/backup/restore", json={"token": report["token"]}).status_code == 400


def test_empty_vault_restores_without_safety_backup(client):
    data = _zip({"projects/P1-옮김/index.md": "---\nid: P2026-001\ntitle: 빈 서버로\nstatus: in_progress\n---\n\n본문\n",
                 "settings.json": "{}"})
    report = _upload(client, data).json()
    assert report["ok"] and report["current"]["has_data"] is False
    result = client.post("/api/backup/restore", json={"token": report["token"]}).json()
    assert result["safety_backup"] is None
    assert _titles(client) == {"빈 서버로"}


def test_wrapped_folder_is_unwrapped(client):
    data = _zip({"vault/projects/P1-감싼/index.md": "---\nid: P2026-001\ntitle: 감싼 백업\nstatus: in_progress\n---\n",
                 "vault/settings.json": "{}"})
    report = _upload(client, data).json()
    assert report["ok"] and report["wrapped"] == "vault" and report["projects"] == 1
    client.post("/api/backup/restore", json={"token": report["token"]})
    assert _titles(client) == {"감싼 백업"}


def test_foreign_or_broken_zip_is_refused(client, vault_dir):
    foreign = _upload(client, _zip({"readme.txt": "다른 프로그램"})).json()
    assert foreign["ok"] is False and foreign["token"] is None
    assert "이 도구의 백업이 아닙니다" in foreign["problems"][0]
    broken = _upload(client, b"not a zip at all")
    assert broken.status_code == 400 and "ZIP" in broken.json()["detail"]
    assert client.post("/api/backup/restore", json={"token": "../../etc"}).status_code == 400


def test_names_pointing_outside_are_skipped_and_index_trash_ignored(client, vault_dir, tmp_path):
    data = _zip({
        "projects/P1-안전/index.md": "---\nid: P2026-001\ntitle: 안전한 과제\nstatus: in_progress\n---\n",
        "../밖으로.txt": "탈출",
        "/절대.txt": "탈출",
        ".index/index.sqlite3": "색인 아님",
        ".trash/버린것.md": "버림",
    })
    report = _upload(client, data).json()
    assert report["ok"] and any("밖을 가리키는" in p for p in report["problems"])
    client.post("/api/backup/restore", json={"token": report["token"]})
    assert not (tmp_path / "밖으로.txt").exists()
    assert not (vault_dir / ".trash" / "버린것.md").exists()
    assert _titles(client) == {"안전한 과제"}


def test_missing_backup_folder_is_reported(client):
    data = _zip({"projects/P1-a/index.md": "---\nid: P2026-001\ntitle: 폴더\nstatus: in_progress\n---\n",
                 "settings.json": '{"backup_dir": "Z:/옛서버/백업"}'})
    result = client.post("/api/backup/restore", json={"token": _upload(client, data).json()["token"]}).json()
    assert result["backup_dir_missing"] == "Z:/옛서버/백업"


def test_failed_swap_keeps_current_data(client, vault_dir, monkeypatch):
    client.post("/api/projects", json={"title": "지금 과제", "status": "in_progress"})
    data = _zip({"projects/P1-b/index.md": "---\nid: P2026-009\ntitle: 바꿀 과제\nstatus: in_progress\n---\n"})
    token = _upload(client, data).json()["token"]
    from app.services import restore

    real = restore.Path.replace
    calls = {"n": 0}

    def flaky(self, target):
        calls["n"] += 1
        if calls["n"] == 3:  # 몇 개 옮긴 뒤에 멈춘다(파일을 누가 열고 있다)
            raise PermissionError("사용 중")
        return real(self, target)

    monkeypatch.setattr(restore.Path, "replace", flaky)
    res = client.post("/api/backup/restore", json={"token": token})
    monkeypatch.setattr(restore.Path, "replace", real)
    assert res.status_code == 400 and "그대로" in res.json()["detail"]
    client.post("/api/reindex")
    assert _titles(client) == {"지금 과제"}


def test_remote_cannot_restore(tmp_path, monkeypatch):
    monkeypatch.setenv("MD_MGMT_VAULT", str(tmp_path / "vault"))
    monkeypatch.setenv("MD_MGMT_SHARE", "1")
    get_settings.cache_clear()
    from app.main import app

    with TestClient(app, client=("10.0.0.9", 51003)) as viewer:
        assert _upload(viewer, _zip({"settings.json": "{}"})).status_code == 403
        assert viewer.post("/api/backup/restore", json={"token": "0" * 32}).status_code == 403
    get_settings.cache_clear()
