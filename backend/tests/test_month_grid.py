"""과제 × 월 보고 표 (TODO 77). 홈이 아니라 **보고 이력 화면**의 것이다 (TODO 79).

과제가 늘면 줄이 그만큼 늘어 홈의 "한눈에" 성격과 어긋난다 — 50명 팀이면 과제가 수백 건이다.
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



def test_month_grid_gives_projects_and_reports(client):
    """화면 모양은 서버가 모른다 — 목록만 주고 열두 칸으로 나누는 일은 화면이 한다."""
    project = _make(client, "가끔 보고하는 과제")
    _freeze_report(client, project["id"], "2026-03-10", audience="부문 주간회의")

    grid = client.get("/api/report-month-grid", params={"year": "2026"}).json()
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

    grid = client.get("/api/report-month-grid", params={"year": "2027"}).json()
    assert [item["id"] for item in grid["projects"]] == [old["id"]]
    # 위쪽 '보고 횟수' 와 표의 보고 수가 같아야 한다.
    assert len(grid["reports"]) == client.get(
        "/api/home", params={"year": "2027"}
    ).json()["team"]["reports"]


def test_month_grid_keeps_a_project_with_no_report(client):
    """한 줄이 통째로 비어 있으면 '올해 한 번도 보고하지 않은 과제' 다. 그 사실이 보여야 한다."""
    quiet = _make(client, "한 번도 보고 안 한 과제")

    grid = client.get("/api/report-month-grid", params={"year": "2026"}).json()
    assert [item["id"] for item in grid["projects"]] == [quiet["id"]]
    assert grid["reports"] == []


def test_month_grid_counts_only_frozen_reports(client):
    project = _make(client, "초안만 있는 과제")
    client.post(f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-04-01"})

    grid = client.get("/api/report-month-grid", params={"year": "2026"}).json()
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



def test_month_grid_leaves_out_projects_marked_no_report(client):
    """보고가 필요 없다고 정해 둔 과제. 빈 줄로 세우면 '관리 공백' 처럼 읽힌다 (TODO 80)."""
    _make(client, "보고 필요한 과제")
    _make(client, "현황만 보는 과제", no_report=True)

    grid = client.get("/api/report-month-grid", params={"year": "2026"}).json()
    assert [item["title"] for item in grid["projects"]] == ["보고 필요한 과제"]
    # 몇 건을 뺐는지 화면이 밝힐 수 있어야 한다.
    assert grid["skipped"] == 1
