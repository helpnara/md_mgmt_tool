"""팀원 면담 (TODO 182) — 역량 이력과 따로 · 하기로 한 것 · 면담 주기 · 검색에 안 걸림."""
from datetime import date, timedelta


def _meeting(client, **extra):
    payload = {"person": "김현우", "date": "2026-09-10", "kind": "정기", "summary": "3분기 점검"} | extra
    response = client.post("/api/meetings", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_a_meeting_lives_in_its_own_folder_and_table(client, vault_dir):
    meeting_id = _meeting(client, followups=["열처리 교육 신청", {"text": "목표 다시 쓰기", "done": None}],
                          body="## 이야기한 것\n\n이동 희망 없음\n")
    files = list((vault_dir / "people").glob("*/meetings/*.md"))
    assert len(files) == 1 and files[0].name == "2026-09-10-정기.md"
    assert not list((vault_dir / "people").glob("*/activities/*.md"))  # 역량 이력과 섞지 않는다
    item = client.get("/api/meetings", params={"person": "김현우"}).json()["items"][0]
    assert item["id"] == meeting_id and item["open_followups"] == 2
    assert [f["text"] for f in item["followups"]] == ["열처리 교육 신청", "목표 다시 쓰기"]
    # 역량 이력 수에 들지 않는다
    person = next(p for p in client.get("/api/activities/summary").json()["people"] if p["name"] == "김현우")
    assert person["count"] == 0 and person["meetings"] == 1 and person["open_followups"] == 2


def test_closing_a_followup_and_the_team_open_list(client):
    meeting_id = _meeting(client, followups=["교육 신청", "멘토 정하기"])
    assert len(client.get("/api/meetings").json()["open_followups"]) == 2
    client.patch(f"/api/meetings/{meeting_id}", json={
        "followups": [{"text": "교육 신청", "done": "2026-09-20"}, {"text": "멘토 정하기", "done": None}],
    })
    data = client.get("/api/meetings").json()
    assert [item["text"] for item in data["open_followups"]] == ["멘토 정하기"]
    assert data["items"][0]["open_followups"] == 1


def test_meeting_due_by_cycle_or_planned_date(client):
    old = (date.today() - timedelta(days=120)).isoformat()
    _meeting(client, person="박지민", date=old)
    recent = (date.today() - timedelta(days=10)).isoformat()
    _meeting(client, person="이서연", date=recent, next_date=(date.today() + timedelta(days=30)).isoformat())
    people = {p["name"]: p for p in client.get("/api/activities/summary", params={"year": ""}).json()["people"]}
    assert people["박지민"]["meeting_due"] is True       # 기본 주기 90일이 지났다
    assert people["이서연"]["meeting_due"] is False
    assert people["이서연"]["next_meeting"] is not None
    # 주기를 바꾸면 따라간다
    client.put("/api/settings", json={"meeting_cycle_days": 200})
    people = {p["name"]: p for p in client.get("/api/activities/summary").json()["people"]}
    assert people["박지민"]["meeting_due"] is False


def test_rules(client):
    assert client.post("/api/meetings", json={"person": "가, 나", "date": "2026-09-01", "summary": "x"}).status_code == 400
    assert client.post("/api/meetings", json={"person": "가", "date": "2026-09-01"}).status_code == 400  # 요약 없음
    assert client.post("/api/meetings", json={"person": "가", "date": "2026-09-01", "summary": "x",
                                              "next_date": "2026-08-01"}).status_code == 400
    assert client.post("/api/meetings", json={"person": "가", "date": "2026-02-30", "summary": "x"}).status_code == 400


def test_not_searchable_and_delete_goes_to_trash(client, vault_dir):
    meeting_id = _meeting(client, summary="고충 — 야간 근무 부담")
    found = client.get("/api/search", params={"q": "야간 근무"}).json()
    assert found["total"] == 0  # 통합 검색에 걸리지 않는다
    assert client.delete(f"/api/meetings/{meeting_id}").status_code == 204
    assert client.get("/api/meetings").json()["items"] == []
    trash = client.get("/api/trash").json()
    items = trash if isinstance(trash, list) else trash.get("items", [])
    assert any(item.get("kind") == "meeting" for item in items)


def test_kinds_come_from_settings(client):
    assert client.get("/api/meta").json()["meeting_kinds"][0] == "정기"
    client.put("/api/settings", json={"meeting_kinds": "분기 점검\n고충"})
    assert client.get("/api/meta").json()["meeting_kinds"] == ["분기 점검", "고충"]
    client.put("/api/settings", json={"meeting_kinds": ""})
    assert client.get("/api/meta").json()["meeting_kinds"][0] == "정기"


def test_reindex_reads_meetings_back(client, vault_dir):
    _meeting(client, followups=["하나"])
    client.post("/api/reindex")
    assert len(client.get("/api/meetings").json()["items"]) == 1
