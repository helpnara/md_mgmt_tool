"""끝점 하나가 보내는 SQL 문장 수의 상한 (TODO 190).

혼자 쓸 때 38ms 던 홈이 열 명이 동시에 열자 6.9초가 됐다 — 한 요청이 **1,164 문장**(과제마다 담당자 · 보고 · 기록을 따로 묻는 N+1)
이었기 때문이다. 순차로 재는 시간은 이것을 못 본다. 그래서 **문장 수**를 센다: 과제가 60건인데 문장이 과제 수에 비례해 늘면 여기서 잡힌다.
"""
from __future__ import annotations

import pytest

from app import deps

PROJECTS = 60

# 과제 수와 무관하게 유지되어야 하는 상한 — 과제가 60건이므로, 과제마다 한 문장만 더해도 넘는다
BUDGET = {
    "/api/home?year=2026": 80,
    "/api/dashboard?year=2026": 40,
    "/api/projects": 20,
    "/api/projects?year=2026": 20,
    "/api/report-candidates?date=2026-10-13": 20,
    "/api/meta": 15,
    "/api/roadmap": 10,
}


@pytest.fixture()
def counting(client, monkeypatch):
    """요청마다 여는 커넥션에 문장 세기를 건다."""
    count = {"n": 0}
    real = deps.connect

    def traced(*args, **kwargs):
        conn = real(*args, **kwargs)
        conn.set_trace_callback(lambda _s: count.__setitem__("n", count["n"] + 1))
        return conn

    monkeypatch.setattr(deps, "connect", traced)
    return count


def seed(client):
    names = ["김현우", "박서연", "정하준", "최민서"]
    for i in range(PROJECTS):
        project = client.post("/api/projects", json={
            "title": f"예산 과제 {i + 1}", "status": "in_progress" if i % 3 else "done",
            "start_date": "2026-01-05", "due_date": "2026-12-20", "owners": [names[i % 4], names[(i + 1) % 4]],
            "tags": ["검증", "자동화"], "partners": [{"team": "품질팀", "people": ["협력자"]}],
            "completed_at": "2026-06-20" if i % 3 == 0 else None,
        }).json()
        for k in range(3):
            client.post(f"/api/projects/{project['id']}/entries", json={
                "date": f"2026-0{k + 1}-10", "title": f"점검 {k + 1}", "body": "## 내용\n- 했다\n\n## 다음 계획\n- 더 한다",
            })
        if i % 2 == 0:
            draft = client.post(f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-03-17", "audience": "팀장"}).json()
            client.post(f"/api/reports/{draft['id']}/freeze")


def test_statement_count_does_not_grow_with_projects(client, counting):
    seed(client)
    over = {}
    for path, budget in BUDGET.items():
        counting["n"] = 0
        response = client.get(path)
        assert response.status_code == 200, (path, response.text)
        if counting["n"] > budget:
            over[path] = (counting["n"], budget)
    assert not over, f"문장 수가 상한을 넘었다 (실제, 상한): {over} — 과제마다 따로 묻는 줄이 들어왔는지 본다"


def test_the_batched_candidates_match_the_per_project_answer(client):
    """묶음 질의로 바꿨어도 과제마다 묻던 답과 같아야 한다 — 담당자 · 미보고 수 · 마지막 보고 · 마지막 기록 날짜."""
    from app.services import reports as svc
    seed(client)
    with __import__("app.db", fromlist=["connect"]).connect() as conn:
        for item in svc.candidates(conn)[:12]:
            owners = [r["name"] for r in conn.execute(
                "SELECT name FROM project_owner WHERE project_id = ? ORDER BY position, name", (item["id"],))]
            unreported = svc.unreported_entries(conn, item["id"])
            last = svc.last_report_info(conn, item["id"])
            assert item["owners"] == owners
            assert item["unreported_entries"] == len(unreported)
            assert item["latest_entry_date"] == (unreported[-1]["date"] if unreported else None)
            assert item["last_report_id"] == (last["id"] if last else None)
