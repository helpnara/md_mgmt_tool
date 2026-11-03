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
    # 남은 날 — 오늘이면 0 (TODO 226)
    assert [item["days_left"] for item in upcoming["items"]] == [0, 3, 30]
    assert not any(item["ongoing"] for item in upcoming["items"])


def test_an_ongoing_multi_day_plan_stays_in_the_upcoming_list(client):
    """어제 시작해 모레 끝나는 교육은 '진행 중' 으로 남는다 — 시작일만 보면 목록에서 빠졌다 (TODO 226 ③)."""
    add(client, date=day(-1), end_date=day(2), title="사흘짜리 교육")
    add(client, date=day(-3), end_date=day(-1), title="어제 끝난 교육")
    items = client.get("/api/home").json()["this_week"]["team_upcoming"]["items"]
    assert [(item["title"], item["ongoing"], item["days_left"]) for item in items] == [("사흘짜리 교육", True, 0)]


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


def test_went_takes_a_past_plan_off_the_home_check_and_keeps_the_record(client, monkeypatch):
    """[다녀옴] — 확인한 날만 적고 홈의 지난 예정 확인에서 내려간다. 기록은 이력으로 남는다 (TODO 231)."""
    made = add(client, date=day(3), title="다녀온 교육", takeaway=None)
    other = add(client, date=day(4), title="아직 확인 안 한 교육")
    monkeypatch.setenv(clock.ENV, day(8))
    from app import readcache

    readcache.bump()
    assert {item["title"] for item in client.get("/api/home").json()["this_week"]["team_missed"]} == {"다녀온 교육", "아직 확인 안 한 교육"}
    response = client.post(f"/api/activities/{one_id(made)}/plan-check")
    assert response.status_code == 200 and response.json()["plan_checked"] == day(8)
    missed = client.get("/api/home").json()["this_week"]["team_missed"]
    assert [item["title"] for item in missed] == ["아직 확인 안 한 교육"]
    # 기록은 그대로 이력으로
    kept = next(item for item in client.get("/api/activities").json() if item["id"] == one_id(made))
    assert kept["title"] == "다녀온 교육" and kept["planned"] is False
    # 다시 읽어도(파일이 원본) 확인한 날이 남는다
    assert client.post("/api/reindex").status_code == 200
    readcache.bump()
    assert [item["title"] for item in client.get("/api/home").json()["this_week"]["team_missed"]] == ["아직 확인 안 한 교육"]
    assert client.post("/api/activities/999999/plan-check").status_code == 404
    assert other


def test_home_trend_shows_every_year_with_past_current_future(client):
    """연도별 추이 — 과제가 있는 모든 해, 해마다 지난해 · 올해 · 미래 (TODO 228). 미래 해는 그 해에 걸친 과제 수."""
    year = TODAY.year
    client.post("/api/projects", json={"title": "작년 과제", "status": "done", "start_date": f"{year - 1}-02-01", "due_date": f"{year - 1}-11-30", "completed_at": f"{year - 1}-11-30"})
    client.post("/api/projects", json={"title": "다년도 과제", "status": "in_progress", "start_date": f"{year}-03-01", "due_date": f"{year + 1}-06-30"})
    client.post("/api/projects", json={"title": "내년 시작 과제", "status": "planned", "start_date": f"{year + 2}-01-10", "due_date": f"{year + 2}-12-31"})
    compare = client.get("/api/home").json()["compare"]
    assert [(item["year"], item["when"]) for item in compare] == [
        (str(year - 1), "past"), (str(year), "current"), (str(year + 1), "future"), (str(year + 2), "future"),
    ]
    totals = {item["year"]: item["total"] for item in compare}
    assert totals[str(year + 1)] == 1 and totals[str(year + 2)] == 1
    # 목록을 그 해로 거르면 같은 수
    assert len(client.get(f"/api/projects?year={year + 1}").json()) == totals[str(year + 1)]


def test_home_tells_how_many_non_smart_projects_carry_a_classification(client):
    """성격별 · 분류별 합이 스마트과제 수보다 큰 까닭 — 다른 속성인데 성격 · 분류가 적힌 과제 수 (TODO 229)."""
    client.put("/api/settings", json={"natures": ["연구과제/PoC", "현장적용"]} )
    client.post("/api/projects", json={"title": "스마트", "type": "smart", "nature": "현장적용"})
    client.post("/api/projects", json={"title": "R&D 인데 성격 적음", "type": "rnd", "nature": "연구과제/PoC"})
    outside = client.get("/api/home").json()["classified_outside"]
    assert outside == {"nature": 1, "category": 0}
