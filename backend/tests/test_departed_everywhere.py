"""떠난 사람(전배 · 퇴사)을 화면마다 같은 기준으로 (TODO 323).

떠난 날이 **오늘이거나 지났을 때만** 떠난 사람이다 — 앞날이면 그날까지 지금 사람(214 D8).
"""
from __future__ import annotations

from datetime import timedelta

from app import clock

TODAY = clock.today()


def day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


def roster(client):
    response = client.put("/api/people", json={"people": [
        {"name": "권경락"},
        {"name": "떠난이", "left_on": day(-30), "left_reason": "퇴사"},
        {"name": "갈사람", "left_on": day(30), "left_reason": "전배"},
    ]})
    assert response.status_code == 200, response.text


def test_team_skills_people_use_the_date(client):
    roster(client)
    people = {p["name"]: p for p in client.get("/api/team-skills?left=true").json()["people"]}
    assert people["떠난이"]["left"] is True and people["떠난이"]["left_reason"] == "퇴사"
    assert people["갈사람"]["left"] is False          # 떠날 예정 — "누가 빠지면 끊기나"에 남는다
    default = [p["name"] for p in client.get("/api/team-skills").json()["people"]]
    assert "갈사람" in default and "떠난이" not in default


def test_year_cards_and_person_history_use_the_date(client):
    roster(client)
    cards = {p["name"]: p for p in client.get(f"/api/yearcards?year={TODAY.year}").json()["people"]}
    assert cards["떠난이"]["left"] is True
    assert cards["갈사람"]["left"] is False
    gone = client.get("/api/person-history?name=떠난이").json()
    assert gone["left"] is True and gone["left_reason"] == "퇴사"
    soon = client.get("/api/person-history?name=갈사람").json()
    assert soon["left"] is False and soon["left_on"] == day(30)


def test_home_schedule_skips_people_who_left(client):
    roster(client)
    for person in ("떠난이", "갈사람"):
        response = client.post("/api/activities", json={"person": person, "title": f"{person} 교육", "kind": "education", "date": day(3)})
        assert response.status_code == 201, response.text
        client.post("/api/activities", json={"person": person, "title": f"{person} 먼 교육", "kind": "education", "date": day(60)})
    upcoming = client.get("/api/home").json()["this_week"]["team_upcoming"]
    assert [item["person"] for item in upcoming["items"]] == ["갈사람"]
    assert upcoming["later"] == 1


def test_promotion_does_not_send_a_departed_leader_to_partners(client):
    roster(client)
    item = client.post("/api/intakes", json={"title": "떠난 리더 접수", "leader": "떠난이", "leader_team": "우리팀"}).json()
    plan = client.get(f"/api/intakes/{item['id']}/promote").json()
    assert plan["owners"] == [] and plan["partners"] == []
    assert plan["leader_departed"] == ["떠난이"] and plan["leader_in_roster"] is False
