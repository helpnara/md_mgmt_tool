"""명부에서 떠난 사람은 팀원역량에서 다르게 (TODO 194).

줄은 남는다 — 그 사람이 받은 교육은 사실이다. 다만 **면담 대상**에는 세우지 않는다: "먼저 볼 사람" 에도, 면담 때가 지남에도.
"""
from __future__ import annotations


def test_a_departed_person_keeps_the_row_but_leaves_the_interview_list(client):
    client.put("/api/people", json={"people": [
        {"name": "김현우"},
        {"name": "홍길동", "left_on": "2026-09-30", "left_reason": "전배"},
    ]})
    client.post("/api/activities", json={"person": "홍길동", "date": "2025-03-10", "kind": "education", "title": "지난 교육"})
    client.post("/api/meetings", json={"person": "홍길동", "date": "2025-04-01", "kind": "정기", "summary": "지난 면담", "followups": ["남은 것"]})

    people = {item["name"]: item for item in client.get("/api/activities/summary?year=2026").json()["people"]}
    gone, here = people["홍길동"], people["김현우"]
    assert gone["left"] is True and gone["left_on"] == "2026-09-30" and gone["left_reason"] == "전배"
    assert gone["count"] == 0 and gone["last_date"] == "2025-03-10"  # 올해 0건, 이력은 그대로
    assert gone["quiet"] is False, "떠난 사람은 '먼저 볼 사람' 이 아니다"
    assert gone["meeting_due"] is False and gone["next_meeting"] is None
    assert gone["last_meeting"] == "2025-04-01", "지난 면담은 남는다"
    assert here["left"] is False and here["quiet"] is True, "남은 사람은 기록이 없으니 먼저 볼 사람"
