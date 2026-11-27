"""주소창의 이름(Host)이 이 서버가 아니면 받지 않는다 — DNS 리바인딩 막기 (TODO 328)."""
from __future__ import annotations

import socket

from app import share


def test_host_rules(monkeypatch):
    assert share.host_ok(None)
    assert share.host_ok("localhost:8000") and share.host_ok("127.0.0.1:8000") and share.host_ok("[::1]:8000")
    name = socket.gethostname().lower().split(".")[0]
    assert share.host_ok(f"{name}:8000") and share.host_ok(f"{name}.corp.local:8000")
    assert not share.host_ok("evil.example.com:8000")
    monkeypatch.setenv("MD_MGMT_ALLOWED_HOSTS", "team-server, other")
    assert share.host_ok("team-server:8000")


def test_foreign_host_is_refused_even_for_reads(client):
    assert client.get("/api/meta").status_code == 200
    refused = client.get("/api/meta", headers={"host": "evil.example.com"})
    assert refused.status_code == 403
    assert "주소" in refused.json()["detail"]
