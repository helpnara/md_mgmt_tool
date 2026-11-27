"""답하지 않은 지시사항을 홈 · 팀원 내 할 일에 (TODO 334)."""
from __future__ import annotations


def _report_with_feedback(client, project_id, day, feedback):
    report = client.post(f"/api/projects/{project_id}/reports/draft", json={"report_date": day}).json()
    client.post(f"/api/reports/{report['id']}/freeze")
    client.patch(f"/api/reports/{report['id']}", json={"feedback": feedback})
    return report


def test_home_lists_open_feedback_and_drops_answered(client):
    project = client.post("/api/projects", json={"title": "지시 받은 과제", "status": "in_progress"}).json()
    first = _report_with_feedback(client, project["id"], "2026-09-01", "원가 근거를 붙일 것")
    _report_with_feedback(client, project["id"], "2026-09-08", "현장 의견 받기")
    box = client.get("/api/home").json()["this_week"]["feedback_open"]
    assert box["total"] == 2
    assert [item["feedback"] for item in box["items"]] == ["원가 근거를 붙일 것", "현장 의견 받기"]
    assert box["items"][0]["project_title"] == "지시 받은 과제"
    # 답하면 내려간다 — 보고이력 거르기와 같은 수
    client.post(f"/api/reports/{first['id']}/feedback-done", json={"done": True})
    assert client.get("/api/home").json()["this_week"]["feedback_open"]["total"] == 1
    assert len(client.get("/api/reports", params={"feedback": "open"}).json()) == 1
