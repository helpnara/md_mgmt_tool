"""배너가 **말한 것과 데려가는 곳이 같은가** (TODO 91).

"초안 1건이 확정을 기다립니다" 라고 이름까지 적어 놓고 후보 목록으로 보내면,
방금 들은 그 한 건을 사용자가 다시 찾아야 한다. 개수만으로는 갈 곳을 만들 수 없으므로
서버가 **초안이 무엇인지**(과제·보고 id·제목)를 함께 준다.
"""
from __future__ import annotations

import datetime


def make(client, title):
    project = client.post("/api/projects", json={"title": title}).json()["id"]
    client.post(
        f"/api/projects/{project}/entries",
        json={"date": "2026-09-01", "title": "진행", "body": "내용"},
    )
    return project


def report_day(client):
    """오늘이 보고일이 되도록 요일을 맞춘다 — 그래야 배너가 뜬다."""
    weekday = datetime.date.today().weekday()
    client.put("/api/settings", json={"report_weekday": weekday})
    return client.get("/api/dashboard").json()["reminder"]


def test_reminder_names_the_drafts_it_is_talking_about(client):
    project = make(client, "이름이 필요한 과제")
    reminder = report_day(client)
    draft = client.post(
        f"/api/projects/{project}/reports/draft",
        json={"report_date": reminder["report_date"], "audience": "팀 주간회의"},
    ).json()

    reminder = client.get("/api/dashboard").json()["reminder"]
    assert reminder["drafts"] == 1
    # 개수와 목록이 같은 것을 세야 한다.
    assert [item["id"] for item in reminder["draft_items"]] == [draft["id"]]
    item = reminder["draft_items"][0]
    assert item["project_id"] == project
    assert item["project_title"] == "이름이 필요한 과제"
    assert item["audience"] == "팀 주간회의"


def test_confirmed_reports_leave_the_waiting_list(client):
    project = make(client, "확정하면 빠진다")
    reminder = report_day(client)
    draft = client.post(
        f"/api/projects/{project}/reports/draft", json={"report_date": reminder["report_date"]}
    ).json()
    client.post(f"/api/reports/{draft['id']}/freeze")

    reminder = client.get("/api/dashboard").json()["reminder"]
    assert reminder["drafts"] == 0
    assert reminder["draft_items"] == []
    # 대신 "오늘 보고한 것" 으로 옮겨 간다 — 배너가 보고 이력으로 데려갈 근거다.
    assert reminder["done"] == 1


def test_the_candidates_screen_gets_the_same_drafts(client):
    """배너가 4건 이상일 때 보내는 화면. 같은 자료를 서로 다르게 세면 안 된다."""
    ids = []
    reminder = report_day(client)
    for index in range(3):
        project = make(client, f"초안 과제 {index}")
        ids.append(
            client.post(
                f"/api/projects/{project}/reports/draft",
                json={"report_date": reminder["report_date"]},
            ).json()["id"]
        )

    from_banner = client.get("/api/dashboard").json()["reminder"]["draft_items"]
    from_screen = client.get("/api/report-candidates").json()["drafts"]
    assert {item["id"] for item in from_screen} == set(ids)
    # 순서까지 같아야 한다 — 배너의 칩 순서와 화면의 줄 순서가 다르면 같은 것으로 안 읽힌다.
    assert [item["id"] for item in from_banner] == [item["id"] for item in from_screen]


def test_drafts_for_other_days_are_not_counted(client):
    """다음 주 보고를 미리 만들어 두었다고 오늘 배너가 재촉하면 안 된다."""
    project = make(client, "다음 주 보고")
    reminder = report_day(client)
    later = "2026-12-31"
    assert later != reminder["report_date"]
    client.post(f"/api/projects/{project}/reports/draft", json={"report_date": later})

    reminder = client.get("/api/dashboard").json()["reminder"]
    assert reminder["drafts"] == 0
    assert reminder["draft_items"] == []


def test_the_count_is_not_capped_by_the_list_limit(client):
    """목록은 앞의 몇 건만 오지만 **건수는 전부**여야 한다.

    자른 길이를 그대로 건수로 쓰면 "초안 10건" 이라 적고 실제로는 더 있는 일이 생긴다 —
    대시보드에서 이미 한 번 겪은 종류다 (TODO 82).
    """
    from app.services.reports import DRAFT_LIST_LIMIT

    reminder = report_day(client)
    total = DRAFT_LIST_LIMIT + 3
    for index in range(total):
        project = make(client, f"많은 초안 {index}")
        client.post(
            f"/api/projects/{project}/reports/draft", json={"report_date": reminder["report_date"]}
        )

    reminder = client.get("/api/dashboard").json()["reminder"]
    assert reminder["drafts"] == total
    assert len(reminder["draft_items"]) == DRAFT_LIST_LIMIT
