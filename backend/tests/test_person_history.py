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


def test_year_review_counts_my_year_against_last_year(team):  # noqa: F811
    """나의 한 해 (TODO 244 A3) — 그 해에 맡은 · 마친 과제, 내가 쓴 일지, 보고, 중간 성과, 교육, 새 기술 · 도구, 그 밖의 성과."""
    owner, member, viewer, pid = team["owner"], team["member"], team["viewer"], team["shared"]
    old = owner.post("/api/projects", json={"title": "작년 과제", "owners": ["가팀원"], "status": "done",
                                            "start_date": "2025-02-03", "completed_at": "2025-11-28"}).json()["id"]
    owner.put(f"/api/projects/{old}/contributions/가팀원", json={"skills": ["Python"]})
    member.put(f"/api/projects/{pid}/contributions/가팀원", json={
        "role": "주관", "skills": ["Python", "LightGBM"], "milestones": [{"date": "2026-06-30", "text": "상반기"}]})
    owner.patch(f"/api/projects/{pid}", json={"status": "done", "completed_at": "2026-10-01", "outcome": "재작업 38 → 19건"})
    member.post(f"/api/projects/{pid}/entries", json={"date": "2026-05-01", "title": "내가 쓴 일지"})
    owner.post(f"/api/projects/{pid}/entries", json={"date": "2026-05-02", "title": "팀장이 쓴 일지"})
    draft = owner.post(f"/api/projects/{pid}/reports/draft", json={"report_date": "2026-07-01"}).json()
    owner.post(f"/api/reports/{draft['id']}/freeze")
    owner.post("/api/activities", json={"person": "가팀원", "date": "2026-04-10", "kind": "education", "title": "교육", "hours": 8})
    data = viewer.get("/api/person-history/year", params={"name": "가팀원", "year": "2026"}).json()
    assert (data["projects"], data["done"], data["lead"], data["entries"], data["reports"], data["milestones"]) == (1, 1, 1, 1, 1, 1)
    assert (data["activities"], data["hours"]) == (1, 8)
    assert data["new_skills"] == ["LightGBM"]  # Python 은 작년에도 썼다
    assert data["outcomes"] == [{"id": pid, "title": "함께 하는 과제", "outcome": "재작업 38 → 19건"}]
    assert data["last"]["projects"] == 1 and data["last"]["done"] == 1
    assert viewer.get("/api/person-history/year", params={"name": "가팀원", "year": "26"}).status_code == 422
    # 마친 과제 (A4)
    summary = owner.get(f"/api/projects/{pid}").json()["done_summary"]
    assert summary["months"] == 7 and summary["entries"] == 2 and summary["reports"] == 1 and summary["milestones"] == 1
    assert summary["outcome"] == "재작업 38 → 19건" and summary["people"] == 2
    assert owner.get(f"/api/projects/{old}").json()["done_summary"]["months"] == 10
    assert [item["id"] for item in member.get("/api/projects/my-work").json()["recent_done"]] == [pid]
    # 배경 · 목표 (B6)
    owner.patch(f"/api/projects/{pid}", json={"body": "## 배경\n\n> 안내 줄\n\n재작업이 월 38건\n\n## 목표\n\n- 20건 이하\n- 재현율 80%\n\n## 추진내용\n\n생략"})
    item = next(p for p in viewer.get("/api/person-history", params={"name": "가팀원"}).json()["projects"] if p["id"] == pid)
    assert item["context"] == {"background": "재작업이 월 38건", "goal": "20건 이하 · 재현율 80%"}
