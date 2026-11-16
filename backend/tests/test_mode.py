"""체험 자료 · 내 자료 모드 (TODO 295)."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.delenv("MD_MGMT_VAULT", raising=False)
    monkeypatch.setenv("MD_MGMT_HOME", str(tmp_path))
    monkeypatch.setenv("MD_MGMT_SHARE", "1")
    get_settings.cache_clear()
    from app import who
    from app.main import app

    who.forget()
    with TestClient(app, client=("127.0.0.1", 51201)) as owner, TestClient(app, client=("10.0.0.77", 51202)) as other:
        yield {"owner": owner, "other": other, "home": tmp_path}
    get_settings.cache_clear()


def _wait(client) -> dict:
    for _ in range(600):
        st = client.get("/api/mode").json()
        if not st["job"]["running"]:
            return st
        time.sleep(0.1)
    raise AssertionError("모드 바꾸기가 끝나지 않음")


def test_first_run_demo_then_mine_and_back(home):
    owner, other = home["owner"], home["other"]
    st = owner.get("/api/mode").json()
    assert st["mode"] == "mine" and st["fixed"] is False and st["choose"] is True and st["demo_ready"] is False
    assert owner.post("/api/mode", json={"mode": "demo"}).status_code == 200
    st = _wait(owner)
    assert st["mode"] == "demo" and st["job"]["stage"] == "끝" and st["demo_ready"] is True and st["choose"] is False, st
    projects = owner.get("/api/projects").json()
    assert len(projects) == 20
    statuses = [p["status"] for p in projects]
    assert statuses.count("in_progress") == 9 and statuses.count("done") == 8 and statuses.count("on_hold") == 1 and statuses.count("dropped") == 2
    people = owner.get("/api/people").json()["people"]
    assert len([p for p in people if not p.get("left_on")]) == 10 and len([p for p in people if p.get("left_on")]) == 2
    kpis = owner.get("/api/team-skills").json()["kpis"]
    assert kpis["experiences"] >= 10 and kpis["skills_held"] >= 10
    # 체험 중에는 다른 PC 는 막힘(안내 · 모드만 열림), 바꾸기는 서버 PC 만
    assert other.get("/api/projects").status_code == 403 and other.get("/api/mode").status_code == 200
    assert other.post("/api/mode", json={"mode": "mine"}).status_code == 403
    assert (home["home"] / "demo-vault" / "projects").is_dir()
    # 내 자료로 — 비어 있고, 체험 자료는 그대로 남는다
    owner.post("/api/mode", json={"mode": "mine"})
    st = _wait(owner)
    assert st["mode"] == "mine" and owner.get("/api/projects").json() == [] and st["demo_ready"] is True
    owner.post("/api/projects", json={"title": "내 첫 과제"})
    # 다시 체험으로 — 만들지 않고 그대로, 내 자료도 그대로
    owner.post("/api/mode", json={"mode": "demo"})
    assert len(_wait(owner) and owner.get("/api/projects").json()) == 20
    owner.post("/api/mode", json={"mode": "mine"})
    _wait(owner)
    assert [p["title"] for p in owner.get("/api/projects").json()] == ["내 첫 과제"]


def test_reset_and_validation(home):
    owner = home["owner"]
    owner.post("/api/mode", json={"mode": "demo"})
    _wait(owner)
    first = owner.get("/api/projects").json()[0]["id"]
    owner.patch(f"/api/projects/{first}", json={"title": "고친 제목"})
    owner.post("/api/mode", json={"mode": "demo", "reset": True})
    _wait(owner)
    assert "고친 제목" not in [p["title"] for p in owner.get("/api/projects").json()]
    assert owner.post("/api/mode", json={"mode": "x"}).status_code == 400
    assert owner.post("/api/mode", json={"mode": "mine", "mine_dir": "상대경로"}).status_code == 400


def test_fixed_vault_cannot_switch(tmp_path, monkeypatch):
    monkeypatch.setenv("MD_MGMT_VAULT", str(tmp_path / "vault"))
    get_settings.cache_clear()
    from app.main import app

    with TestClient(app, client=("127.0.0.1", 51203)) as owner:
        st = owner.get("/api/mode").json()
        assert st["fixed"] is True and st["choose"] is False
        assert owner.post("/api/mode", json={"mode": "demo"}).status_code == 400
    get_settings.cache_clear()
