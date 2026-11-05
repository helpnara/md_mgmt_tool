"""팀원도 자기 과제를 고치게 — 등록한 IP 로 사람을 알아본다 (TODO 233).

세 사람으로 같은 요청을 보내 본다 — 팀장(서버 PC 안 127.0.0.1) · 팀원(명부에 등록한 10.0.0.5) · 읽기(등록 안 한 10.0.0.9).
"""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings

MEMBER_IP = "10.0.0.5"


@pytest.fixture()
def team(tmp_path, monkeypatch):
    monkeypatch.setenv("MD_MGMT_VAULT", str(tmp_path / "vault"))
    monkeypatch.setenv("MD_MGMT_SHARE", "1")
    get_settings.cache_clear()
    from app import readcache, share, who

    monkeypatch.setattr(share, "_today", {"date": None, "ips": set(), "requests": 0})
    monkeypatch.setattr(share, "_seen", {})
    who.forget()
    from app.main import app

    with TestClient(app, client=("127.0.0.1", 51001)) as owner, \
            TestClient(app, client=(MEMBER_IP, 51002)) as member, \
            TestClient(app, client=("10.0.0.9", 51003)) as viewer:
        assert owner.put("/api/people", json={"people": [
            {"name": "가팀원", "ips": [MEMBER_IP]}, {"name": "나팀원"}]}).status_code == 200
        mine = owner.post("/api/projects", json={"title": "가팀원 과제", "owners": ["가팀원"], "status": "in_progress"}).json()
        theirs = owner.post("/api/projects", json={"title": "나팀원 과제", "owners": ["나팀원"], "status": "in_progress"}).json()
        readcache.bump()
        yield {"owner": owner, "member": member, "viewer": viewer, "mine": mine["id"], "theirs": theirs["id"]}
    who.forget()
    get_settings.cache_clear()


def test_ip_rules_in_the_roster(team):
    owner = team["owner"]
    # 한 IP 에 두 사람은 안 된다 — 공용 PC 가 잘못 등록되지 않게
    bad = owner.put("/api/people", json={"people": [{"name": "가팀원", "ips": [MEMBER_IP]}, {"name": "나팀원", "ips": [MEMBER_IP]}]})
    assert bad.status_code == 400 and "두 사람" in bad.json()["detail"]
    # 서버 PC 자신의 주소 · 모양이 아닌 것
    assert owner.put("/api/people", json={"people": [{"name": "가팀원", "ips": ["127.0.0.1"]}]}).status_code == 400
    assert owner.put("/api/people", json={"people": [{"name": "가팀원", "ips": ["10.0.0.999"]}]}).status_code == 400
    # 한 모양으로 적힌다 · IP 칸을 보내지 않으면 지금 값을 물려준다
    assert owner.put("/api/people", json={"people": [{"name": "가팀원", "ips": ["::ffff:10.0.0.5"]}, {"name": "나팀원"}]}).status_code == 200
    assert owner.put("/api/people", json={"people": [{"name": "가팀원"}, {"name": "나팀원"}]}).status_code == 200
    people = {p["name"]: p for p in owner.get("/api/people").json()["people"]}
    assert people["가팀원"]["ips"] == [MEMBER_IP]


def test_who_am_i(team):
    me = team["member"].get("/api/me").json()
    assert me == {"role": "member", "name": "가팀원", "projects": [team["mine"]]}
    assert team["viewer"].get("/api/me").json()["role"] == "viewer"
    assert team["owner"].get("/api/me").json()["role"] == "owner"
    # 팀원도 화면 전체로는 읽기 전용이다 — 담당 과제에서만 단추가 선다
    assert team["member"].get("/api/meta").json()["readonly"] is True


def test_member_writes_entries_only_on_own_project_and_is_the_author(team):
    member, viewer, owner = team["member"], team["viewer"], team["owner"]
    made = member.post(f"/api/projects/{team['mine']}/entries", json={"title": "내가 쓴 기록", "body": "본문", "author": "팀장"})
    assert made.status_code == 201, made.text
    assert made.json()["author"] == "가팀원"  # 화면이 보낸 작성자가 아니라 그 사람
    other = member.post(f"/api/projects/{team['theirs']}/entries", json={"title": "남의 과제"})
    assert other.status_code == 403 and "담당 과제만" in other.json()["detail"]
    assert viewer.post(f"/api/projects/{team['mine']}/entries", json={"title": "읽기"}).status_code == 403
    # 고치기 · 지우기는 본인이 쓴 것만
    entry_id = made.json()["id"]
    assert member.patch(f"/api/entries/{entry_id}", json={"body": "고침"}).status_code == 200
    by_owner = owner.post(f"/api/projects/{team['mine']}/entries", json={"title": "팀장이 쓴 기록", "author": "팀장"}).json()
    denied = member.patch(f"/api/entries/{by_owner['id']}", json={"body": "남의 것"})
    assert denied.status_code == 403 and "남이 쓴" in denied.json()["detail"]
    assert member.delete(f"/api/entries/{by_owner['id']}").status_code == 403
    assert member.delete(f"/api/entries/{entry_id}").status_code == 204


def test_member_edits_overview_body_but_not_fields(team):
    member = team["member"]
    assert member.patch(f"/api/projects/{team['mine']}", json={"body": "## 배경\n\n팀원이 고친 개요\n"}).status_code == 200
    denied = member.patch(f"/api/projects/{team['mine']}", json={"status": "done"})
    assert denied.status_code == 403 and "개요 본문만" in denied.json()["detail"]
    for fields in ({"owners": ["가팀원", "나팀원"]}, {"effect_expected": 9.9}, {"due_date": "2026-12-31"}):
        assert member.patch(f"/api/projects/{team['mine']}", json=fields).status_code == 403, fields
    assert member.patch(f"/api/projects/{team['theirs']}", json={"body": "남의 과제"}).status_code == 403


def test_member_cannot_do_the_leaders_work(team):
    member = team["member"]
    for method, path, body in [
        ("post", "/api/projects", {"title": "새 과제"}),
        ("post", f"/api/projects/{team['mine']}/reports/draft", {}),
        ("post", "/api/activities", {"person": "가팀원", "date": "2026-10-01", "title": "교육"}),
        ("post", "/api/meetings", {"person": "가팀원", "date": "2026-10-01"}),
        ("put", "/api/settings", {"author": "가팀원"}),
        ("put", "/api/people", {"people": []}),
        ("post", f"/api/projects/{team['mine']}/archive", None),
        ("post", "/api/reindex", None),
    ]:
        response = getattr(member, method)(path, json=body) if body is not None else getattr(member, method)(path)
        assert response.status_code == 403, (method, path, response.status_code)
    for path in ["/api/settings", "/api/people", "/api/trash", "/api/backup", "/api/edits/recent", "/api/errors"]:
        assert member.get(path).status_code == 403, path


def test_member_attaches_to_own_entry(team):
    member = team["member"]
    entry = member.post(f"/api/projects/{team['mine']}/entries", json={"title": "첨부 기록"}).json()
    png = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
           b"\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")
    up = member.post(f"/api/entries/{entry['id']}/attachments", files={"file": ("사진.png", io.BytesIO(png), "image/png")})
    assert up.status_code == 201, up.text
    assert member.delete(f"/api/attachments/{up.json()['id']}").status_code == 204


def test_drafts_are_kept_per_person(team):
    member, owner = team["member"], team["owner"]
    key = f"overview:{team['mine']}"
    assert member.put(f"/api/drafts/{key}", json={"content": "팀원이 쓰다 만 글"}).status_code == 200
    assert owner.put(f"/api/drafts/{key}", json={"content": "팀장이 쓰다 만 글"}).status_code == 200
    assert member.get(f"/api/drafts/{key}").json()["content"] == "팀원이 쓰다 만 글"
    assert owner.get(f"/api/drafts/{key}").json()["content"] == "팀장이 쓰다 만 글"
    assert len(owner.get("/api/drafts").json()["items"]) == 1
    assert len(member.get("/api/drafts").json()["items"]) == 1
    assert team["viewer"].get("/api/drafts").status_code == 403


def test_member_sees_only_own_meetings(team):
    owner, member, viewer = team["owner"], team["member"], team["viewer"]
    for person in ("가팀원", "나팀원"):
        made = owner.post("/api/meetings", json={"person": person, "date": "2026-09-15", "summary": f"{person} 면담",
                                                 "followups": [{"text": f"{person} 할 일", "done": None}]})
        assert made.status_code == 201, made.text
    mine = member.get("/api/meetings").json()
    assert [item["person"] for item in mine["items"]] == ["가팀원"]
    assert [item["person"] for item in mine["open_followups"]] == ["가팀원"]
    # 다른 사람을 물어도 자기 것만
    assert [item["person"] for item in member.get("/api/meetings?person=나팀원").json()["items"]] == ["가팀원"]
    assert viewer.get("/api/meetings").json() == {"items": [], "open_followups": []}
    # 팀원역량 요약 — 자기 줄의 면담 칸만. 답 나눠 쓰기로 남의 답이 새지 않는다(읽기 → 팀원 → 읽기 차례로)
    rows = {p["name"]: p for p in viewer.get("/api/activities/summary").json()["people"]}
    assert rows["가팀원"]["last_meeting"] is None
    rows = {p["name"]: p for p in member.get("/api/activities/summary").json()["people"]}
    assert rows["가팀원"]["last_meeting"] == "2026-09-15" and rows["나팀원"]["last_meeting"] is None
    rows = {p["name"]: p for p in viewer.get("/api/activities/summary").json()["people"]}
    assert rows["가팀원"]["last_meeting"] is None


def test_leader_sees_what_members_changed(team):
    member, owner = team["member"], team["owner"]
    member.post(f"/api/projects/{team['mine']}/entries", json={"title": "기록 하나"})
    member.post(f"/api/projects/{team['mine']}/entries", json={"title": "기록 둘"})
    member.patch(f"/api/projects/{team['mine']}", json={"body": "개요"})
    owner.post(f"/api/projects/{team['mine']}/entries", json={"title": "팀장 기록"})
    items = owner.get("/api/edits/recent").json()["items"]
    assert [(item["name"], item["action"], item["count"]) for item in items] == [
        ("가팀원", "개요 수정", 1), ("가팀원", "진행일지 추가", 2)]
    assert items[0]["project_title"] == "가팀원 과제"


def test_foreign_origin_cannot_write(team):
    owner = team["owner"]
    evil = owner.post("/api/projects", json={"title": "남의 사이트"}, headers={"Origin": "http://evil.example"})
    assert evil.status_code == 403 and "다른 사이트" in evil.json()["detail"]
    assert owner.post("/api/projects", json={"title": "내 화면"}, headers={"Origin": "http://127.0.0.1:8000"}).status_code == 201
    assert owner.post("/api/projects", json={"title": "null"}, headers={"Origin": "null"}).status_code == 403


def test_second_save_is_told_who_saved_first(team):
    member, owner = team["member"], team["owner"]
    entry = member.post(f"/api/projects/{team['mine']}/entries", json={"title": "함께 고치는 기록"}).json()
    opened = entry["updated_at"]
    import time

    time.sleep(1.1)
    assert member.patch(f"/api/entries/{entry['id']}", json={"body": "팀원이 먼저", "base_updated_at": opened}).status_code == 200
    late = owner.patch(f"/api/entries/{entry['id']}", json={"body": "팀장이 나중", "base_updated_at": opened})
    assert late.status_code == 409 and "가팀원 님이" in late.json()["detail"]
    assert owner.get(f"/api/entries/{entry['id']}").json()["body"].strip() == "팀원이 먼저"
    # 개요도 같다
    project = owner.get(f"/api/projects/{team['mine']}").json()
    time.sleep(1.1)
    assert member.patch(f"/api/projects/{team['mine']}", json={"body": "새 개요", "base_updated_at": project["updated_at"]}).status_code == 200
    assert owner.patch(f"/api/projects/{team['mine']}", json={"body": "옛 개요", "base_updated_at": project["updated_at"]}).status_code == 409


def test_left_person_is_only_a_viewer(team):
    owner, member = team["owner"], team["member"]
    assert owner.put("/api/people", json={"people": [{"name": "가팀원", "left_on": "2026-09-30", "left_reason": "전배"}, {"name": "나팀원"}]}).status_code == 200
    assert member.get("/api/me").json()["role"] == "viewer"
    assert member.post(f"/api/projects/{team['mine']}/entries", json={"title": "떠난 뒤"}).status_code == 403


def test_visitors_list_shows_who_was_recognized(team):
    team["member"].get("/api/projects")
    team["viewer"].get("/api/projects")
    items = {item["ip"]: item for item in team["owner"].get("/api/people/visitors").json()["items"]}
    assert items[MEMBER_IP]["name"] == "가팀원"
    assert items["10.0.0.9"]["name"] == ""
    assert team["member"].get("/api/people/visitors").status_code == 403
