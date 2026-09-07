"""보고가 담는 기간 — **보고일 이후에 쓴 기록은 그 보고에 들어가지 않는다** (TODO 81).

이 결함은 실사용 초기에 반드시 부딪히는 자리에 있었다. 다른 도구에서 옮겨 오면서
진행일지를 먼저 다 넣고 과거 보고를 날짜 지정해 입력하면, **첫 보고가 1년치를 통째로
삼키고** 나머지 보고는 전부 "진행일지 0건"이 됐다. 그 결과 세 화면이 동시에 거짓말을 한다 —
수행 이력에서 보고 마커가 사라지고, 과제 상세가 "미보고 0건"이라 적고,
보고 대상 추천의 근거(미보고 분량)가 전부 0이 된다.
"""
from __future__ import annotations


def make(client, title="보고 기간 확인"):
    return client.post("/api/projects", json={"title": title}).json()["id"]


def add_entry(client, project_id, date, title="기록"):
    return client.post(
        f"/api/projects/{project_id}/entries",
        json={"date": date, "title": title, "body": f"## 내용\n\n{title}"},
    ).json()


def test_a_report_does_not_swallow_entries_written_after_it(client):
    project = make(client)
    add_entry(client, project, "2026-09-01", "1주차 진행")
    add_entry(client, project, "2026-09-05", "2주차 진행")

    draft = client.post(
        f"/api/projects/{project}/reports/draft", json={"report_date": "2026-09-02"}
    ).json()

    # 보고일까지만 담는다.
    assert draft["covers_from"] == "2026-09-01"
    assert draft["covers_to"] == "2026-09-01"
    assert "1주차 진행" in draft["body"]
    assert "2주차 진행" not in draft["body"]

    client.post(f"/api/reports/{draft['id']}/freeze")

    # 사흘 뒤 기록은 여전히 보고 대상으로 남아 있어야 한다.
    detail = client.get(f"/api/projects/{project}").json()
    assert detail["unreported_entries"] == 1


def test_catching_up_on_months_of_history_keeps_each_report_in_its_own_period(client):
    """도구를 처음 들일 때의 이관 시나리오. 기록을 먼저 다 넣고 과거 보고를 차례로 만든다."""
    project = make(client, "지난 이력 이관")
    for month in (3, 4, 5, 6):
        add_entry(client, project, f"2026-{month:02d}-05", f"{month}월 진행")

    covered = []
    for month in (3, 4, 5, 6):
        draft = client.post(
            f"/api/projects/{project}/reports/draft", json={"report_date": f"2026-{month:02d}-20"}
        ).json()
        client.post(f"/api/reports/{draft['id']}/freeze")
        covered.append((draft["covers_from"], draft["covers_to"]))

    # 첫 보고가 전부 삼키지 않고 달마다 한 건씩 나뉜다.
    assert covered == [
        ("2026-03-05", "2026-03-05"),
        ("2026-04-05", "2026-04-05"),
        ("2026-05-05", "2026-05-05"),
        ("2026-06-05", "2026-06-05"),
    ]
    reports = client.get(f"/api/projects/{project}/reports").json()
    assert [row["entry_count"] for row in reports] == [1, 1, 1, 1]
    assert client.get(f"/api/projects/{project}").json()["unreported_entries"] == 0


def test_normal_weekly_flow_is_unchanged(client):
    """평소 흐름 — 보고일은 앞날이므로 지금까지 쓴 기록이 모두 담긴다."""
    project = make(client, "평소 흐름")
    add_entry(client, project, "2026-09-01")
    add_entry(client, project, "2026-09-03")

    draft = client.post(
        f"/api/projects/{project}/reports/draft", json={"report_date": "2026-09-08"}
    ).json()
    assert (draft["covers_from"], draft["covers_to"]) == ("2026-09-01", "2026-09-03")
    client.post(f"/api/reports/{draft['id']}/freeze")
    assert client.get(f"/api/projects/{project}").json()["unreported_entries"] == 0


def test_pulling_the_report_date_earlier_drops_the_later_entries_at_freeze(client):
    """초안을 만든 뒤 보고일을 앞당긴 경우에도 확정 시점에 다시 걸러 낸다."""
    project = make(client, "보고일 앞당김")
    add_entry(client, project, "2026-09-01", "앞선 기록")
    add_entry(client, project, "2026-09-06", "나중 기록")

    draft = client.post(
        f"/api/projects/{project}/reports/draft", json={"report_date": "2026-09-08"}
    ).json()
    client.patch(f"/api/reports/{draft['id']}", json={"report_date": "2026-09-02"})
    client.post(f"/api/reports/{draft['id']}/freeze")

    # 09-06 기록은 09-02 자 보고가 담을 수 없다 — 아직 보고되지 않은 것으로 남는다.
    assert client.get(f"/api/projects/{project}").json()["unreported_entries"] == 1


def test_unreported_count_is_not_capped_by_any_date(client):
    """미보고 '분량'은 날짜를 자르지 않는다 — 앞으로 보고해야 할 양이 곧 그 수다."""
    project = make(client, "미보고 분량")
    add_entry(client, project, "2026-09-01")
    add_entry(client, project, "2026-12-31")

    candidates = client.get("/api/report-candidates").json()["items"]
    mine = next(item for item in candidates if item["id"] == project)
    assert mine["unreported_entries"] == 2
