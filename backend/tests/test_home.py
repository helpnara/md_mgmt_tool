"""홈 화면 집계 (TODO 56 · ROADMAP R1).

여기서 지키는 것은 **연도 기준이 둘**이라는 사실과, **담당 중복**이 수를 부풀린다는
사실이다. 둘 다 화면에서 그대로 드러나므로 바뀌면 보고 자리에서 틀린 수를 말하게 된다.
"""
from __future__ import annotations


def _make(client, title, **kwargs):
    payload = {"title": title, "status": "in_progress"}
    payload.update(kwargs)
    return client.post("/api/projects", json=payload).json()


def _freeze_report(client, project_id, date, audience="전사 주요업무 보고"):
    report = client.post(
        f"/api/projects/{project_id}/reports/draft", json={"report_date": date, "audience": audience}
    ).json()
    client.post(f"/api/reports/{report['id']}/freeze")
    return report


def test_team_numbers_count_projects_not_owners(client):
    """팀 합계는 **과제 기준**이다. 담당자가 둘이어도 과제는 하나다."""
    _make(client, "공동 과제", owners=["권경락", "김현우"], effect_expected=3.0)
    _make(client, "혼자 과제", owners=["권경락"], effect_expected=2.0, status="done")

    home = client.get("/api/home").json()
    assert home["team"]["total"] == 2
    assert home["team"]["done"] == 1
    assert home["team"]["effect_expected"] == 5.0


def test_member_totals_may_exceed_the_team_total(client):
    """사람별로 더하면 팀 합계를 넘는다. 이것은 결함이 아니라 담당 중복이다.

    화면이 "담당 중복 포함" 이라고 밝히는 근거가 이 시험이다.
    """
    _make(client, "공동 과제", owners=["권경락", "김현우"], effect_expected=3.0)

    home = client.get("/api/home").json()
    by_member = sum(item["effect_expected"] for item in home["members"])
    assert by_member == 6.0 > home["team"]["effect_expected"] == 3.0


def test_reports_are_counted_by_the_date_they_were_reported(client):
    """보고 횟수만은 **보고일** 연도로 센다.

    2026년 과제를 2027년에 보고했다면 그것은 2027년의 보고다.
    "올해 몇 번 보고했나"에 답하려면 이 기준이어야 한다.
    """
    project = _make(client, "해를 넘긴 과제", owners=["권경락"])
    _freeze_report(client, project["id"], "2026-12-29")
    _freeze_report(client, project["id"], "2027-01-05")

    assert client.get("/api/home", params={"year": "2026"}).json()["team"]["reports"] == 1
    assert client.get("/api/home", params={"year": "2027"}).json()["team"]["reports"] == 1
    # 과제 자체는 2026년 번호이므로 과제 수는 2026년에만 잡힌다.
    assert client.get("/api/home", params={"year": "2026"}).json()["team"]["total"] == 1
    assert client.get("/api/home", params={"year": "2027"}).json()["team"]["total"] == 0


def test_draft_reports_are_not_counted(client):
    """초안은 아직 보고한 것이 아니다."""
    project = _make(client, "초안만 있는 과제")
    client.post(f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-09-08"})

    assert client.get("/api/home").json()["team"]["reports"] == 0


# ── 과제 x 월 보고 표 (TODO 77) ─────────────────────────

def test_month_grid_gives_projects_and_reports(client):
    """화면 모양은 서버가 모른다 — 목록만 주고 열두 칸으로 나누는 일은 화면이 한다."""
    project = _make(client, "가끔 보고하는 과제")
    _freeze_report(client, project["id"], "2026-03-10", audience="부문 주간회의")

    grid = client.get("/api/home", params={"year": "2026"}).json()["monthly_reports"]
    assert [item["id"] for item in grid["projects"]] == [project["id"]]
    assert grid["reports"] == [
        {
            "id": grid["reports"][0]["id"],
            "project_id": project["id"],
            "date": "2026-03-10",
            "audience": "부문 주간회의",
        }
    ]


def test_month_grid_keeps_a_project_reported_from_another_year(client):
    """지난해 번호인데 올해 보고한 과제. 빼면 표의 합이 위쪽 '보고 횟수' 와 어긋난다."""
    old = _make(client, "작년 과제")
    # 과제 번호는 2026 이지만, 보고일을 2027 로 두면 '2027년 표'에서 같은 상황이 된다.
    _freeze_report(client, old["id"], "2027-02-03")

    grid = client.get("/api/home", params={"year": "2027"}).json()["monthly_reports"]
    assert [item["id"] for item in grid["projects"]] == [old["id"]]
    # 위쪽 '보고 횟수' 와 표의 보고 수가 같아야 한다.
    assert len(grid["reports"]) == client.get(
        "/api/home", params={"year": "2027"}
    ).json()["team"]["reports"]


def test_month_grid_keeps_a_project_with_no_report(client):
    """한 줄이 통째로 비어 있으면 '올해 한 번도 보고하지 않은 과제' 다. 그 사실이 보여야 한다."""
    quiet = _make(client, "한 번도 보고 안 한 과제")

    grid = client.get("/api/home", params={"year": "2026"}).json()["monthly_reports"]
    assert [item["id"] for item in grid["projects"]] == [quiet["id"]]
    assert grid["reports"] == []


def test_month_grid_counts_only_frozen_reports(client):
    project = _make(client, "초안만 있는 과제")
    client.post(f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-04-01"})

    grid = client.get("/api/home", params={"year": "2026"}).json()["monthly_reports"]
    assert grid["reports"] == []


# ── 상태 여섯 칸 (TODO 75) ──────────────────────────────

def _one_of_each_status(client):
    from app.config import STATUS_KEYS

    for key in STATUS_KEYS:
        _make(client, f"{key} 과제", status=key, owners=["권경락"], type="rnd")
    return STATUS_KEYS


def test_both_tables_count_all_six_statuses(client):
    """두 표가 같은 헬퍼를 쓴다. 한 화면에서 같은 것을 다르게 세면 안 된다."""
    keys = _one_of_each_status(client)
    home = client.get("/api/home").json()

    member = home["members"][0]
    kind = home["types"][0]
    assert list(member["by_status"]) == list(keys), "상태 순서가 STATUSES 와 다릅니다"
    assert list(kind["by_status"]) == list(keys)
    assert all(member["by_status"][key] == 1 for key in keys)
    assert all(kind["by_status"][key] == 1 for key in keys)


def test_the_six_boxes_add_up_to_the_row_total(client):
    keys = _one_of_each_status(client)
    home = client.get("/api/home").json()

    for row in (*home["members"], *home["types"]):
        total = row.get("total", row.get("count"))
        assert sum(row["by_status"].values()) == total, row


def test_zero_boxes_are_kept_not_dropped(client):
    """줄끼리 세로로 견주는 표라, 칸이 줄마다 달라지면 비교가 안 된다."""
    _make(client, "진행중 하나뿐", status="in_progress", owners=["권경락"], type="smart")

    home = client.get("/api/home").json()
    counts = home["members"][0]["by_status"]
    assert len(counts) == 6
    assert counts["planned"] == 0 and counts["in_progress"] == 1


def test_types_carry_the_effect_money(client):
    """속성별 절단면은 과제 수만으로는 부족하다 — 상부는 금액을 묻는다."""
    _make(client, "스마트 과제", type="smart", effect_expected=4.0, effect_verified=1.5)
    _make(client, "R&D 과제", type="rnd", effect_expected=2.0)

    types = {item["key"]: item for item in client.get("/api/home").json()["types"]}
    assert types["smart"]["effect_expected"] == 4.0
    assert types["smart"]["effect_verified"] == 1.5
    assert types["rnd"]["effect_verified"] == 0


def test_years_lists_only_years_that_have_projects(client):
    _make(client, "올해 과제")
    home = client.get("/api/home").json()
    assert home["years"] == ["2026"]


def test_stale_list_skips_projects_that_have_not_started(client):
    """오래 방치된 과제 자리에 '아직 시작도 안 한 과제'가 오면 뜻이 흐려진다 (TODO 70)."""
    from datetime import date, timedelta

    later = (date.today() + timedelta(days=30)).isoformat()
    _make(client, "다음 달 착수", status="planned", start_date=later)
    running = _make(client, "오래된 과제", start_date="2026-01-02")

    stale = client.get("/api/home").json()["this_week"]["stale"]
    assert [item["id"] for item in stale] == [running["id"]]


def test_this_week_block_answers_what_to_do_now(client):
    """홈을 매일 여는 이유는 지표가 아니라 이 칸이다."""
    project = _make(client, "보고할 과제", start_date="2026-01-02")
    client.post(
        f"/api/projects/{project['id']}/entries", json={"date": "2026-08-20", "title": "기록"}
    )

    week = client.get("/api/home").json()["this_week"]
    assert week["candidates"] == 1
    assert week["report_date"]
