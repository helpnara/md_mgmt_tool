"""팀원 역량의 예정 (TODO 221).

미래 날짜의 기록이 예정이다. 숫자(건수 · 시간 · 비용 · 추이 · 마지막 활동 · 뜸한 사람 · 홈 팀원 표)는 **지나간 것만** 세고,
예정은 따로 — 홈 [이번 주 할 일] 의 다가오는 일정, 날짜가 지나고 손대지 않은 것은 "지난 예정 확인".
"""
from __future__ import annotations

from datetime import timedelta

from app import clock

TODAY = clock.today()


def day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


def add(client, **fields):
    payload = {"person": "김예정", "title": "교육", "kind": "education"} | fields
    response = client.post("/api/activities", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def one_id(created) -> int:
    return created["ids"][0] if "ids" in created else created["id"]


def test_a_future_record_is_a_plan_and_stays_out_of_the_numbers(client):
    add(client, date=day(-10), title="지난 교육", hours=8, cost=100000)
    add(client, date=day(5), title="다음 주 교육", hours=16, cost=500000)

    summary = client.get("/api/activities/summary").json()
    person = next(item for item in summary["people"] if item["name"] == "김예정")
    assert person["count"] == 1 and person["planned"] == 1
    assert person["hours"] == 8 and person["cost"] == 100000
    assert person["last_date"] == day(-10)
    assert person["days_since"] == 10
    assert summary["team"]["count"] == 1 and summary["team"]["planned"] == 1

    items = client.get("/api/activities").json()
    assert {item["title"]: item["planned"] for item in items} == {"지난 교육": False, "다음 주 교육": True}
    assert [item["title"] for item in client.get("/api/activities?when=planned").json()] == ["다음 주 교육"]
    assert [item["title"] for item in client.get("/api/activities?when=past").json()] == ["지난 교육"]


def test_a_person_with_only_plans_is_still_quiet(client):
    """예정만 있는 사람은 아직 쌓인 것이 없다 — 면담에서 꺼낼 줄에 그대로 선다."""
    add(client, person="박계획", date=day(20))
    person = next(item for item in client.get("/api/activities/summary").json()["people"] if item["name"] == "박계획")
    assert person["count"] == 0 and person["planned"] == 1 and person["quiet"] is True
    assert person["last_date"] is None


def test_home_shows_upcoming_plans_within_30_days(client):
    add(client, date=day(0), title="오늘 세미나")
    add(client, date=day(3), title="사흘 뒤 교육", place="대전")
    add(client, date=day(30), title="한 달 뒤 학회")
    add(client, date=day(31), title="먼 박람회")
    add(client, date=day(-1), title="어제 교육")

    week = client.get("/api/home").json()["this_week"]
    upcoming = week["team_upcoming"]
    assert upcoming["days"] == 30
    assert [item["title"] for item in upcoming["items"]] == ["오늘 세미나", "사흘 뒤 교육", "한 달 뒤 학회"]
    assert upcoming["items"][1]["place"] == "대전" and upcoming["items"][1]["person"] == "김예정"
    assert upcoming["later"] == 1


def test_home_member_table_counts_only_past_activities(client):
    client.put("/api/settings", json={"people": [{"name": "김예정"}]})
    add(client, date=day(-3))
    add(client, date=day(3))
    members = client.get(f"/api/home?year={TODAY.year}").json()["members"]
    row = next((item for item in members if item["name"] == "김예정"), None)
    if row is not None:  # 담당 과제가 없으면 표에 줄이 없을 수 있다
        assert row["activities"] == 1


def test_a_past_plan_nobody_touched_asks_for_a_check(client, monkeypatch):
    """예정으로 적었다가 날짜가 지났는데 손대지 않았으면 "지난 예정 확인" 에 2주 동안 선다."""
    made = add(client, date=day(3), title="다녀왔나 교육")
    kept = add(client, date=day(5), title="다녀와서 채운 교육")
    # 열흘 뒤로 간다 — 둘 다 날짜가 지났다
    monkeypatch.setenv(clock.ENV, day(10))
    client.patch(f"/api/activities/{one_id(kept)}", json={"takeaway": "좋았다"})
    missed = client.get("/api/home").json()["this_week"]["team_missed"]
    assert [item["title"] for item in missed] == ["다녀왔나 교육"]
    # 2주가 더 지나면 내려간다 — 답을 5초 나눠 쓰는 읽기 캐시(190)를 비운다. 실제로는 날이 바뀌고 5초 안에 따라온다
    monkeypatch.setenv(clock.ENV, day(3 + 15))
    from app import readcache

    readcache.bump()
    assert client.get("/api/home").json()["this_week"]["team_missed"] == []
    assert made  # 지우지 않았다 — 이력으로 남는다


def test_a_record_written_after_the_day_is_not_a_missed_plan(client):
    add(client, date=day(-2), title="다녀와서 적은 교육")
    assert client.get("/api/home").json()["this_week"]["team_missed"] == []
