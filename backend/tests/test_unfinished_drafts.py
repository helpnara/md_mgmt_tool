"""쓰다 만 보고를 홈이 계속 들고 있는다 (TODO 101).

보고 초안은 **확정하기 전까지 아무 일도 하지 않는다.** 보고 이력에 남지도 않고,
그 진행일지가 미보고에서 빠지지도 않는다. 그런데 쓰다 만 초안은 보고일이 지나도
사라지지 않고 조용히 쌓인다.

배너(TODO 91)는 **보고하는 날에만** 뜬다. 그래서 지난주에 쓰다 만 것은 그 다음
보고일까지 아무 데도 보이지 않았다. 홈의 [이번 주 할 일]이 그것을 들고 있게 한다.
"""
from __future__ import annotations

from datetime import date, timedelta


def make(client, title, **extra):
    return client.post("/api/projects", json={"title": title, **extra}).json()


def draft(client, project_id, report_date, audience=None):
    body = {"report_date": report_date}
    if audience:
        body["audience"] = audience
    return client.post(f"/api/projects/{project_id}/reports/draft", json=body).json()


def week(client) -> dict:
    return client.get("/api/home").json()["this_week"]


def day(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


def test_nothing_to_say_without_drafts(client):
    make(client, "과제")
    data = week(client)
    assert data["drafts"] == 0
    assert data["drafts_overdue"] == 0
    assert data["draft_items"] == []


def test_a_draft_shows_up_with_where_to_go(client):
    project = make(client, "고강도 소재 개발")
    made = draft(client, project["id"], day(2), audience="전사 주요업무 보고")

    data = week(client)
    assert data["drafts"] == 1
    # 개수만으로는 갈 곳을 만들 수 없다 (TODO 91 과 같은 이유).
    assert data["draft_items"][0]["id"] == made["id"]
    assert data["draft_items"][0]["project_id"] == project["id"]
    assert data["draft_items"][0]["project_title"] == "고강도 소재 개발"
    assert data["draft_items"][0]["audience"] == "전사 주요업무 보고"


def test_a_frozen_report_is_no_longer_waiting(client):
    project = make(client, "과제")
    made = draft(client, project["id"], day(0))
    assert week(client)["drafts"] == 1
    client.post(f"/api/reports/{made['id']}/freeze")
    assert week(client)["drafts"] == 0


def test_unfreezing_puts_it_back(client):
    project = make(client, "과제")
    made = draft(client, project["id"], day(0))
    client.post(f"/api/reports/{made['id']}/freeze")
    client.post(f"/api/reports/{made['id']}/unfreeze")
    assert week(client)["drafts"] == 1


def test_deleting_a_draft_takes_it_off_the_list(client):
    project = make(client, "과제")
    made = draft(client, project["id"], day(0))
    client.delete(f"/api/reports/{made['id']}")
    assert week(client)["drafts"] == 0


# ── 여러 건 · 지난 보고일 ────────────────────────────────────────────────────

def test_drafts_from_past_report_days_are_counted_apart(client):
    project = make(client, "과제")
    draft(client, project["id"], day(-14))
    draft(client, project["id"], day(-7))
    draft(client, project["id"], day(3))

    data = week(client)
    assert data["drafts"] == 3
    # 보고일이 지난 것이 진짜 밀린 것이다. 따로 센다.
    assert data["drafts_overdue"] == 2


def test_the_oldest_draft_stands_first(client):
    project = make(client, "과제")
    draft(client, project["id"], day(3))
    draft(client, project["id"], day(-10))
    draft(client, project["id"], day(-3))

    dates = [item["report_date"] for item in week(client)["draft_items"]]
    assert dates == sorted(dates)
    assert dates[0] == day(-10)


def test_how_many_days_late_each_one_is(client):
    project = make(client, "과제")
    draft(client, project["id"], day(-5))
    draft(client, project["id"], day(4))

    items = {item["report_date"]: item["overdue_days"] for item in week(client)["draft_items"]}
    assert items[day(-5)] == 5
    # 아직 오지 않은 보고일은 밀린 것이 아니다.
    assert items[day(4)] == 0


def test_a_draft_made_today_is_not_late(client):
    project = make(client, "과제")
    draft(client, project["id"], day(0))
    assert week(client)["drafts_overdue"] == 0
    assert week(client)["draft_items"][0]["overdue_days"] == 0


def test_drafts_across_several_projects_all_show(client):
    first = make(client, "가 과제")
    second = make(client, "나 과제")
    draft(client, first["id"], day(-1))
    draft(client, second["id"], day(-1))
    titles = [item["project_title"] for item in week(client)["draft_items"]]
    assert sorted(titles) == ["가 과제", "나 과제"]


def test_the_count_is_the_real_count_not_the_listed_length(client):
    """자른 목록의 길이를 건수로 쓰면 'N건'이라 적고 실제로는 더 많은 일이 생긴다.

    TODO 82 에서 대시보드가 같은 결함을 냈다. 여기서 다시 나지 않게 못 박는다.
    """
    from app.services.reports import UNFINISHED_LIST_LIMIT

    project = make(client, "과제")
    over = UNFINISHED_LIST_LIMIT + 3
    for index in range(over):
        draft(client, project["id"], day(-index - 1))

    data = week(client)
    assert data["drafts"] == over
    assert len(data["draft_items"]) == UNFINISHED_LIST_LIMIT


def test_the_year_filter_does_not_hide_a_draft(client):
    """연도를 걸어도 쓰다 만 보고는 그대로 보인다.

    연도는 *과제를 가르는* 조건이지, 지금 손에 쥔 일을 가리는 조건이 아니다.
    지난해 과제에 쓰다 만 보고가 있으면 그것도 오늘 마저 해야 할 일이다.
    """
    project = make(client, "지난해 과제", start_date="2025-03-03")
    assert project["id"].startswith("2025-")
    draft(client, project["id"], day(-2))

    for year in ("", str(date.today().year), "2025"):
        data = client.get("/api/home", params={"year": year} if year else {}).json()["this_week"]
        assert data["drafts"] == 1, year
