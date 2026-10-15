"""읽기 전용 공유 (TODO 191 · 192) — 바깥에서 온 요청은 읽기만, 127.0.0.1 은 그대로."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings


@pytest.fixture()
def shared(tmp_path, monkeypatch):
    """공유를 켠 서버 — 바깥(10.0.0.2)에서 온 클라이언트와 서버 PC 안(127.0.0.1)에서 온 클라이언트 둘."""
    monkeypatch.setenv("MD_MGMT_VAULT", str(tmp_path / "vault"))
    monkeypatch.setenv("MD_MGMT_SHARE", "1")
    get_settings.cache_clear()
    from app import share
    monkeypatch.setattr(share, "_today", {"date": None, "ips": set(), "requests": 0})  # 앞선 시험의 접속 수가 섞이지 않게
    from app.main import app

    with TestClient(app, client=("10.0.0.2", 51000)) as remote, TestClient(app, client=("127.0.0.1", 51001)) as local:
        yield remote, local
    get_settings.cache_clear()


def test_without_share_nothing_changes(client):
    """공유를 켜지 않으면 바깥 주소에서 와도 지금과 같다 — 127.0.0.1 에만 열려 있으니 바깥은 애초에 닿지 않는다."""
    assert client.post("/api/projects", json={"title": "그대로"}).status_code == 201
    meta = client.get("/api/meta").json()
    assert meta["readonly"] is False and meta["share"] is None and meta["vault"]


def test_remote_can_read_but_not_write(shared):
    remote, local = shared
    made = local.post("/api/projects", json={"title": "주인이 만든 과제", "status": "in_progress"}).json()
    assert remote.get("/api/projects").status_code == 200
    assert [p["id"] for p in remote.get("/api/projects").json()] == [made["id"]]
    assert remote.get(f"/api/projects/{made['id']}").status_code == 200
    for method, path, body in [
        ("post", "/api/projects", {"title": "바깥에서"}),
        ("patch", f"/api/projects/{made['id']}", {"title": "바깥에서 고침"}),
        ("delete", f"/api/projects/{made['id']}", None),
        ("put", "/api/settings", {"author": "바깥"}),
        ("post", "/api/reindex", None),
        ("put", "/api/drafts/x", {"text": "x"}),
    ]:
        response = getattr(remote, method)(path, json=body) if body is not None else getattr(remote, method)(path)
        assert response.status_code == 403, (method, path, response.status_code)
        assert "읽기 전용" in response.json()["detail"]
    assert local.get(f"/api/projects/{made['id']}").json()["title"] == "주인이 만든 과제"


def test_remote_cannot_see_the_sensitive_reads(shared):
    remote, local = shared
    for path in ["/api/folders", "/api/backup", "/api/settings", "/api/settings/backup/status", "/api/errors", "/api/trash",
                 "/api/versions?path=x", "/api/drafts", "/api/linkfix", "/api/health", "/api/people"]:
        assert remote.get(path).status_code == 403, path
        assert local.get(path).status_code != 403, path


def test_remote_sees_no_meetings_and_no_vault_path(shared):
    remote, local = shared
    local.post("/api/people", json={"people": [{"name": "홍길동"}]}) if False else None
    created = local.post("/api/meetings", json={"person": "홍길동", "date": "2026-10-01", "kind": "정기", "summary": "비밀", "followups": ["교육"]})
    assert created.status_code == 201, created.text
    assert remote.get("/api/meetings").json() == {"items": [], "open_followups": []}
    assert local.get("/api/meetings").json()["items"]
    summary = remote.get("/api/activities/summary").json()
    for person in summary["people"]:
        assert person["meetings"] == 0 and person["last_meeting"] is None and person["open_followups"] == 0 and not person["meeting_due"]
    meta = remote.get("/api/meta").json()
    assert meta["readonly"] is True and meta["vault"] == "" and meta["share"] is None
    owner = local.get("/api/meta").json()
    assert owner["readonly"] is False and owner["vault"] and owner["share"]["url"].startswith("http://")


def test_remote_requests_are_counted_without_content(shared, tmp_path):
    remote, local = shared
    remote.get("/api/projects")
    remote.get("/api/home")
    share = local.get("/api/meta").json()["share"]
    assert share["visitors"] == 1 and share["requests"] >= 2
    logs = list((tmp_path / "vault" / ".logs").glob("access-*.jsonl"))
    assert logs and "10.0.0.2" in logs[0].read_text(encoding="utf-8")
    assert "주인이" not in logs[0].read_text(encoding="utf-8")


# ── 206 공유의 틈 (검토-전수점검-2026-10-15 3.3 ⑫ ㉖ ㉘ ㉙) ──────────────────


def test_remote_meta_and_home_carry_no_employee_id_or_leave_details(shared):
    remote, local = shared
    local.put("/api/people", json={"people": [{"name": "김퇴사", "employee_id": "E123", "account": "kim", "left_on": "2026-01-01", "left_reason": "퇴사"}]})
    local.post("/api/projects", json={"title": "남은 과제", "owners": ["김퇴사"], "status": "in_progress"})
    left = remote.get("/api/meta").json()["people_left"]
    assert left == [{"name": "김퇴사", "left_reason": "퇴사", "left_on": "2026-01-01"}]
    assert local.get("/api/meta").json()["people_left"][0]["employee_id"] == "E123"
    gaps = remote.get("/api/home").json()["this_week"]["owner_gaps"]
    assert gaps and all("left_reason" not in item and "left_on" not in item for item in gaps)
    assert local.get("/api/home").json()["this_week"]["owner_gaps"][0]["left_reason"] == "퇴사"


def test_remote_cannot_read_api_docs(shared):
    remote, local = shared
    for path in ["/openapi.json", "/docs", "/redoc"]:
        assert remote.get(path).status_code == 403, path
        assert local.get(path).status_code == 200, path


def test_remote_export_backup_is_blocked_but_md_is_open(shared):
    remote, local = shared
    made = local.post("/api/projects", json={"title": "내보낼 과제"}).json()
    assert remote.get(f"/api/projects/{made['id']}/export?format=backup").status_code == 403
    assert local.get(f"/api/projects/{made['id']}/export?format=backup").status_code == 200
    assert remote.get(f"/api/projects/{made['id']}/export?format=md").status_code == 200
    assert remote.get(f"/api/projects/{made['id']}/export?format=zip").status_code == 200


def test_owner_on_its_own_lan_address_is_local(tmp_path, monkeypatch):
    """서버 PC 에서 안내된 공유 주소(PC 이름)로 열면 LAN IP 로 들어온다 — 주인은 자기 주소 어느 것으로도 주인이다 (㉖)."""
    monkeypatch.setenv("MD_MGMT_VAULT", str(tmp_path / "vault"))
    monkeypatch.setenv("MD_MGMT_SHARE", "1")
    get_settings.cache_clear()
    from app import share
    monkeypatch.setattr(share, "_today", {"date": None, "ips": set(), "requests": 0})
    monkeypatch.setattr(share, "_own_addresses", frozenset({"192.168.0.10", "fe80::1"}))
    assert share.is_local_host("192.168.0.10") and share.is_local_host("::ffff:192.168.0.10") and share.is_local_host("fe80::1%eth0")
    assert not share.is_local_host("192.168.0.11") and not share.is_local_host(None)
    from app.main import app

    with TestClient(app, client=("192.168.0.10", 5555)) as owner, TestClient(app, client=("192.168.0.11", 5556)) as other:
        made = owner.post("/api/projects", json={"title": "LAN 주소의 주인"})
        assert made.status_code == 201, made.text
        assert owner.get("/api/meta").json()["readonly"] is False
        assert other.patch(f"/api/projects/{made.json()['id']}", json={"status": "done"}).status_code == 403
        assert other.get("/api/meta").json()["readonly"] is True
    get_settings.cache_clear()
