"""사람별 이력 (TODO 238 ①) — 맡은 과제(지금 · 예전)를 맡기 시작한 해별로, 역할 · 기간 · 회고 · 성과와 교육 이력."""
from __future__ import annotations

from tests.test_contributions import team  # noqa: F401 — 같은 세 사람(팀장 · 팀원 · 읽기)


def test_history_collects_projects_roles_retro_and_activities(team):  # noqa: F811
    owner, viewer, pid = team["owner"], team["viewer"], team["shared"]
    owner.put(f"/api/projects/{pid}/contributions/가팀원", json={"role": "주관", "part": "분석 모델", "did": "집계 자동화"})
    owner.patch(f"/api/projects/{pid}", json={"outcome": "작업 시간 40% 단축", "status": "done", "completed_at": "2026-10-01"})
    later = owner.post("/api/projects", json={"title": "넘겨받은 과제", "owners": ["나팀원"], "status": "in_progress",
                                               "start_date": "2025-04-01"}).json()["id"]
    owner.patch(f"/api/projects/{later}", json={"owners": ["가팀원"]})  # 오늘(2026-10-20)부터 가팀원
    owner.post("/api/activities", json={"person": "가팀원", "date": "2026-05-10", "kind": "education", "title": "데이터 분석 교육"})
    data = viewer.get("/api/person-history", params={"name": "가팀원"}).json()  # 읽기 전용에서도 본다(238-3)
    assert data["name"] == "가팀원" and data["in_roster"] is True and data["leader"] is False
    by_id = {item["id"]: item for item in data["projects"]}
    done = by_id[pid]
    assert (done["role"], done["part"], done["did"], done["outcome"]) == ("주관", "분석 모델", "집계 자동화", "작업 시간 40% 단축")
    assert done["from"] == "2026-03-02" and done["to"] == "2026-10-01" and done["year"] == "2026"
    taken = by_id[later]
    assert taken["from"] == "2026-10-20" and taken["to"] is None and taken["year"] == "2026"  # 맡기 시작한 해
    assert data["summary"] == {"projects": 2, "current": 1, "lead": 1, "done": 1, "retro_written": 1,
                               "activities": 1, "entry_only": 0,
                               "reports_this_year": 0, "reports_last_year": 0, "year": "2026"}
    assert [item["title"] for item in data["activities"]] == ["데이터 분석 교육"]
    # 예전 담당도 그 사람 이력에 남는다
    former = viewer.get("/api/person-history", params={"name": "나팀원"}).json()
    assert any(item["id"] == later and item["current"] is False and item["to"] == "2026-10-20" for item in former["projects"])
    # 명부에 없는 이름은 빈 이력
    nobody = viewer.get("/api/person-history", params={"name": "없는사람"}).json()
    assert nobody["projects"] == [] and nobody["in_roster"] is False
    assert viewer.get("/api/person-history", params={"name": " "}).status_code == 400
    # 면담은 싣지 않는다
    assert "meetings" not in data
