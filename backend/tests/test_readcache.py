"""무거운 읽기의 답 나눠 쓰기 (TODO 190) — 같은 답을 주고, 쓰기 뒤에는 새 답을 준다."""
from __future__ import annotations

from app import readcache


def test_a_write_invalidates_the_shared_answer(client):
    first = client.get("/api/projects").json()
    assert first == []
    client.post("/api/projects", json={"title": "새 과제", "status": "in_progress"})
    assert [p["title"] for p in client.get("/api/projects").json()] == ["새 과제"], "저장 직후의 목록은 새것이어야 한다"
    client.get("/api/home")
    assert readcache.stats()["entries"] >= 1
    client.put("/api/settings", json={"author": "권경락"})  # DB 를 안 거치는 쓰기도 판을 올린다
    assert readcache.stats()["entries"] == 0


def test_the_shared_answer_is_byte_identical_and_keeps_etag(client):
    client.post("/api/projects", json={"title": "하나"})
    a = client.get("/api/meta"); b = client.get("/api/meta")
    assert a.content == b.content and a.headers.get("etag") == b.headers.get("etag")
    assert client.get("/api/meta", headers={"If-None-Match": a.headers["etag"]}).status_code == 304
    detail_a = client.get("/api/home?year=2026").content
    assert client.get("/api/home?year=2026").content == detail_a


def test_remote_and_local_do_not_share_an_answer(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.config import get_settings
    monkeypatch.setenv("MD_MGMT_VAULT", str(tmp_path / "vault")); monkeypatch.setenv("MD_MGMT_SHARE", "1")
    get_settings.cache_clear()
    from app.main import app
    with TestClient(app, client=("127.0.0.1", 1)) as local, TestClient(app, client=("10.0.0.9", 2)) as remote:
        assert local.get("/api/meta").json()["vault"]
        assert remote.get("/api/meta").json()["vault"] == ""
        assert local.get("/api/meta").json()["vault"], "바깥의 답이 주인의 답을 덮지 않는다"
    get_settings.cache_clear()
