"""첨부 최대 크기 (TODO 335) — 넘으면 받기 전에(또는 넘는 순간) 413, 설정에서 바꾼다."""
from __future__ import annotations

import io


def _project(client):
    return client.post("/api/projects", json={"title": "첨부 크기", "status": "in_progress"}).json()


def test_default_is_2gb_and_small_files_pass(client):
    assert client.get("/api/settings").json()["attach_max_mb"] == 2048
    project = _project(client)
    ok = client.post(f"/api/projects/{project['id']}/attachments", files={"file": ("a.txt", b"hello", "text/plain")})
    assert ok.status_code == 201, ok.text


def test_over_the_limit_is_refused(client):
    client.put("/api/settings", json={"attach_max_mb": 1})
    project = _project(client)
    big = io.BytesIO(b"x" * (3 * 1024 * 1024))
    refused = client.post(f"/api/projects/{project['id']}/attachments", files={"file": ("big.bin", big, "application/octet-stream")})
    assert refused.status_code == 413
    assert "1MB" in refused.json()["detail"]


def test_limit_is_also_enforced_while_streaming(client, monkeypatch):
    from app.services import attachments, settings

    monkeypatch.setattr(settings, "attach_max_bytes", lambda: 1024)
    project = _project(client)
    # 머리 몫(1MB)보다 작아 앞에서는 통과하지만, 받는 동안 넘는 순간 멈춘다
    refused = client.post(f"/api/projects/{project['id']}/attachments", files={"file": ("mid.bin", b"y" * 4096, "application/octet-stream")})
    assert refused.status_code == 413
