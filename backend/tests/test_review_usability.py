"""전수 검토의 사용성 항목 (TODO 106) — 백엔드가 맡은 몫."""
from __future__ import annotations


def make(client, title, **extra):
    return client.post("/api/projects", json={"title": title, **extra}).json()


# ── B. 개요가 아직 서식 그대로인가 ──────────────────────────────────────────

def test_a_fresh_project_has_a_blank_overview(client):
    project = make(client, "새 과제")
    assert client.get(f"/api/projects/{project['id']}").json()["overview_blank"] is True


def test_writing_the_overview_clears_the_flag(client):
    project = make(client, "새 과제")
    client.patch(f"/api/projects/{project['id']}", json={"body": "## 배경\n\n수율이 3% 낮다.\n"})
    assert client.get(f"/api/projects/{project['id']}").json()["overview_blank"] is False


def test_search_does_not_quote_the_template_as_content(client):
    make(client, "양극재 스케일업")
    hit = client.get("/api/search", params={"q": "양극재"}).json()["projects"][0]
    # 제목으로는 찾히되, 서식 안내 문장은 발췌에 실리지 않는다.
    assert hit["snippet"] == ""


# ── C. 완료했는데 실증효과가 비어 있다 ──────────────────────────────────────

def test_home_counts_finished_projects_without_verified_effect(client):
    make(client, "실증 있음", status="done", effect_verified=1.2)
    make(client, "실증 없음", status="done")
    make(client, "아직 진행중")
    team = client.get("/api/home").json()["team"]
    assert team["done_unverified"] == 1


def test_the_list_filters_to_those_projects(client):
    make(client, "실증 있음", status="done", effect_verified=1.2)
    missing = make(client, "실증 없음", status="done")
    listed = client.get("/api/projects", params={"verified": "none", "year": ""}).json()
    assert [row["id"] for row in listed] == [missing["id"]]


# ── F. 시작일 없는 예정 과제는 뒤로 ─────────────────────────────────────────

def test_an_idle_planned_project_does_not_lead_the_candidates(client):
    idle = make(client, "아직 아무것도 없는 예정 과제", status="planned")
    working = make(client, "일하는 중", status="in_progress")
    client.post(f"/api/projects/{working['id']}/entries", json={"date": "2026-09-01", "title": "기록", "body": "x"})
    ids = [item["id"] for item in client.get("/api/report-candidates").json()["items"]]
    assert ids == [working["id"], idle["id"]]


def test_a_planned_project_with_a_record_comes_back_to_the_top(client):
    planned = make(client, "예정이지만 기록이 있다", status="planned")
    client.post(f"/api/projects/{planned['id']}/entries", json={"date": "2026-09-01", "title": "사전 조사", "body": "x"})
    reported = make(client, "보고한 과제", status="in_progress")
    draft = client.post(f"/api/projects/{reported['id']}/reports/draft", json={"report_date": "2026-08-25"}).json()
    client.post(f"/api/reports/{draft['id']}/freeze")
    ids = [item["id"] for item in client.get("/api/report-candidates").json()["items"]]
    assert ids[0] == planned["id"]


def test_a_planned_project_with_a_start_date_keeps_the_old_rule(client):
    # 시작일이 있으면 "착수했는데 보고를 안 한 것" 이다. 그대로 맨 위.
    started = make(client, "시작일 있는 예정", status="planned", start_date="2026-08-01")
    make(client, "진행중", status="in_progress")
    ids = [item["id"] for item in client.get("/api/report-candidates").json()["items"]]
    assert ids[0] == started["id"]
