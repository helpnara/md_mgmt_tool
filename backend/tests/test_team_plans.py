"""292 2차 — 해마다 남기는 기록(G) · 개인 육성 목표(C) · 승계 · 짝 계획(B). 사람 · 과제는 지어낸 것이다."""
from __future__ import annotations

from app import clock
from tests.test_contributions import team  # noqa: F401
from tests.test_team_skills import _exp


def test_snapshot_save_read_compare_and_auto(team, monkeypatch):  # noqa: F811
    owner = team["owner"]
    _exp(owner, "가팀원", "분석", "확정", skills=[("업무", "데이터 분석")], tools=["파이썬"])
    year = str(clock.today().year)
    saved = owner.post("/api/team-skills/snapshots", json={"year": str(int(year) - 1)}).json()
    assert saved["year"] == str(int(year) - 1) and not saved["auto"]
    snap = owner.get(f"/api/team-skills/snapshots/{int(year) - 1}").json()
    assert "데이터 분석" in snap["body"] and snap["data"]["skills"][0]["holders"] == ["가팀원"]
    # 그 뒤 나팀원도 같은 역량 · 새 역량 — 지난해 기록 ↔ 지금
    _exp(owner, "나팀원", "분석 둘", "구조화", skills=[("업무", "데이터 분석"), ("기술", "공정 개선")])
    view = owner.get("/api/team-skills").json()
    cmp = view["snapshot_compare"]
    assert cmp["year"] == str(int(year) - 1)
    assert {"name": "데이터 분석", "last": 1, "this": 2} in cmp["skills"]["up"] and "공정 개선" in cmp["skills"]["new"]
    assert "역량 · 데이터 분석" in cmp["only_one"]["resolved"]
    assert [s["year"] for s in view["snapshots"]] == [str(int(year) - 1)]
    # 팀원 · 읽기 PC 는 못 본다
    assert team["member"].get(f"/api/team-skills/snapshots/{int(year) - 1}").status_code == 403
    # 해가 바뀐 뒤 1월 — 지난해(올해로 셈) 기록이 없으면 저절로
    monkeypatch.setenv(clock.ENV, f"{int(year) + 1}-01-10")
    view = owner.get("/api/team-skills").json()
    assert any(s["year"] == year and s["auto"] for s in view["snapshots"])
    # 12월이 아니면 홈 알림 없음 · 12월이면 올해 기록이 없을 때
    monkeypatch.setenv(clock.ENV, f"{int(year) + 1}-12-05")
    assert owner.get("/api/team-skills/reminders").json()["snapshot_due"] is True


def test_growth_goals_progress_and_member_reads_own(team):  # noqa: F811
    owner, member, viewer = team["owner"], team["member"], team["viewer"]
    year = str(clock.today().year)
    goals = [{"skill": "데이터 분석", "way": "과제", "note": "불량 예측 과제"}, {"skill": "공정 개선", "way": "교육"}]
    saved = owner.put(f"/api/growth/가팀원/{year}", json={"goals": goals}).json()
    assert [g["skill"] for g in saved["goals"]] == ["데이터 분석", "공정 개선"] and saved["started"] == 0
    assert owner.put(f"/api/growth/가팀원/{year}", json={"goals": goals * 2}).status_code == 400          # 같은 것 두 번
    four = [{"skill": f"역량{i}"} for i in range(4)]
    assert owner.put(f"/api/growth/가팀원/{year}", json={"goals": four}).status_code == 400              # 3개까지
    _exp(owner, "가팀원", "분석", "확정", start=f"{year}-03", skills=[("업무", "데이터 분석")])
    got = owner.get("/api/growth", params={"person": "가팀원", "year": year}).json()
    first = got["goals"][0]
    assert first["started"] and first["experiences"] == 1 and first["confirmed"] == 1 and got["started"] == 1
    # 팀원 — 자기 것만 보고(다른 사람을 물어도 자기 것), 고치지 못한다
    mine = member.get("/api/growth", params={"person": "나팀원"}).json()
    assert mine["person"] == "가팀원" and len(mine["goals"]) == 2
    assert member.put(f"/api/growth/가팀원/{year}", json={"goals": []}).status_code == 403
    assert viewer.get("/api/growth", params={"person": "가팀원"}).status_code == 403
    # 사람별 표의 칸(팀장만) · 나의 한 해(팀장 · 본인만)
    rows = {p["name"]: p for p in owner.get("/api/activities/summary").json()["people"]}
    assert rows["가팀원"]["growth"] == {"goals": 2, "started": 1} and rows["나팀원"]["growth"] == {"goals": 0, "started": 0}
    assert "growth" not in {p["name"]: p for p in member.get("/api/activities/summary").json()["people"]}["가팀원"]
    review = owner.get("/api/person-history/year", params={"name": "가팀원", "year": year}).json()
    assert review["growth"]["goals"] == 2 and review["growth"]["started"] == 1
    assert "growth" in member.get("/api/person-history/year", params={"name": "가팀원", "year": year}).json()
    assert "growth" not in viewer.get("/api/person-history/year", params={"name": "가팀원", "year": year}).json()
    # 팀장이 직접 [이룸]
    goals2 = [{**goals[0]}, {**goals[1], "mark": "이룸"}]
    assert owner.put(f"/api/growth/가팀원/{year}", json={"goals": goals2}).json()["started"] == 2


def test_succession_plan_auto_done_overdue_and_rules(team, monkeypatch):  # noqa: F811
    owner, member = team["owner"], team["member"]
    plan = owner.post("/api/team-skills/succession", json={"kind": "역량", "name": "데이터 분석", "holders": ["가팀원"],
                                                         "learner": "나팀원", "way": "짝 과제"}).json()
    assert plan["id"] == "S-001" and plan["state"] == "진행" and plan["due"] > clock.today().isoformat()
    again = owner.post("/api/team-skills/succession", json={"kind": "역량", "name": "데이터 분석", "learner": "나팀원"})
    assert again.status_code == 400 and "같은 계획" in again.json()["detail"]
    bad = owner.post("/api/team-skills/succession", json={"kind": "역량", "name": "x", "holders": ["가팀원"], "learner": "가팀원"})
    assert bad.status_code == 400
    assert member.get("/api/team-skills/succession").status_code == 403
    # 배울 사람에게 그 역량 경험이 생기면 저절로 "됨"
    _exp(owner, "나팀원", "짝으로 배운 분석", "구조화", start=clock.today().isoformat()[:7], skills=[("업무", "데이터 분석")])
    listed = owner.get("/api/team-skills/succession").json()
    done = listed["plans"][0]
    assert done["state"] == "됨" and done["done_by"] == "경험" and done["evidence"]["title"] == "짝으로 배운 분석"
    # 기한 지난 진행 계획 — 홈 할 일
    other = owner.post("/api/team-skills/succession", json={"kind": "보유 기술", "name": "Minitab", "holders": ["나팀원"],
                                                          "learner": "가팀원", "due": "2026-01-31"}).json()
    rem = owner.get("/api/team-skills/reminders").json()
    assert [o["id"] for o in rem["overdue"]] == [other["id"]]
    assert owner.patch(f"/api/team-skills/succession/{other['id']}", json={"state": "그만둠"}).json()["state"] == "그만둠"
    assert owner.get("/api/team-skills/reminders").json()["overdue"] == []
    assert owner.delete(f"/api/team-skills/succession/{other['id']}").status_code == 204
    assert owner.patch("/api/team-skills/succession/S-999", json={"state": "됨"}).status_code == 404


def test_need_skills_and_candidates(team):  # noqa: F811
    """292 D — 과제 · 접수의 필요 역량(사전 이름으로 맞춤) · 후보(경험 · 해 · 맡은 진행 과제 · 키우는 중 · 배우는 중)."""
    owner, member, pid = team["owner"], team["member"], team["shared"]
    _exp(owner, "가팀원", "분석", "확정", start="2025-03", skills=[("업무", "데이터 분석")])
    _exp(owner, "가팀원", "분석 둘", "구조화", start="2026-03", skills=[("업무", "데이터 분석")])
    _exp(owner, "나팀원", "개선", "구조화", start="2024-05", skills=[("기술", "공정 개선")])
    saved = owner.patch(f"/api/projects/{pid}", json={"need_skills": ["데이터 분석", "공정 개선", "데이터 분석"]}).json()
    assert saved["need_skills"] == ["데이터 분석", "공정 개선"]
    assert owner.get(f"/api/projects/{pid}").json()["need_skills"] == ["데이터 분석", "공정 개선"]
    owner.put(f"/api/growth/팀장/{clock.today().year}", json={"goals": [{"skill": "공정 개선", "way": "과제"}]})
    got = owner.get("/api/team-skills/candidates", params={"skills": "데이터 분석, 공정 개선"}).json()
    by = {p["name"]: p for p in got["people"]}
    assert by["가팀원"]["has"][0] == {"skill": "데이터 분석", "count": 2, "last": "2026"} and by["가팀원"]["busy"] == 1
    assert by["나팀원"]["has"][0]["skill"] == "공정 개선" and by["팀장"]["growing"] == ["공정 개선"] and not by["팀장"]["has"]
    assert [p["name"] for p in got["people"]][0] == "가팀원"        # 경험 많은 사람이 위
    assert member.get("/api/team-skills/candidates", params={"skills": "데이터 분석"}).status_code == 403
    intake = owner.post("/api/intakes", json={"title": "필요 역량 접수", "requester": "생산팀"}).json()
    iid = intake["id"]
    assert owner.patch(f"/api/intakes/{iid}", json={"need_skills": ["데이터 분석"]}).status_code == 200
    assert owner.get(f"/api/intakes/{iid}").json()["need_skills"] == ["데이터 분석"]


def test_education_demand_and_effect(team):  # noqa: F811
    """292 E — 교육 기록의 관련 역량 · 수요(목표 모자람 · 교육 경로 목표) · 효과(교육 뒤 1년 안 경험)."""
    owner = team["owner"]
    owner.put("/api/team-skills/targets", json={"targets": [{"kind": "역량", "name": "데이터 분석", "want": 3}]})
    made = owner.post("/api/activities", json={"person": "가팀원, 나팀원", "kind": "education", "title": "파이썬 데이터 분석 과정",
                                               "date": "2026-02-10", "skills": ["데이터 분석"]}).json()
    rows = owner.get("/api/activities").json()
    assert any(r.get("skills") == ["데이터 분석"] for r in (rows.get("items") if isinstance(rows, dict) else rows))
    owner.post("/api/activities", json={"person": "가팀원", "kind": "education", "title": "역량 칸 빈 교육", "date": "2026-03-01"})
    _exp(owner, "가팀원", "교육 뒤 분석", "구조화", start="2026-05", skills=[("업무", "데이터 분석")])
    owner.put(f"/api/growth/나팀원/{clock.today().year}", json={"goals": [{"skill": "공정 개선", "way": "교육"}]})
    edu = owner.get("/api/team-skills/education").json()
    demand = {d["skill"]: d for d in edu["demand"]}
    assert demand["데이터 분석"]["gap"] == 2 and demand["공정 개선"]["people"] == ["나팀원"]
    eff = next(e for e in edu["effect"] if e["skill"] == "데이터 분석")
    assert [a["person"] for a in eff["used"]] == ["가팀원"] and [w["person"] for w in eff["waiting"]] == ["나팀원"]
    assert edu["unlinked"] == 1 and made


def test_person_shape_own_only(team):  # noqa: F811
    """292 I — 축 넷의 경험 수 · 역량 가짓수, 팀원은 자기 것만."""
    owner, member, viewer = team["owner"], team["member"], team["viewer"]
    _exp(owner, "가팀원", "분석", "구조화", start="2026-03", skills=[("업무", "데이터 분석"), ("기술", "공정 개선")])
    _exp(owner, "가팀원", "옛 것", "구조화", start="2019-03", end="2019-12", skills=[("리더십", "코칭")])
    shape = {a["axis"]: a for a in owner.get("/api/growth/shape", params={"person": "가팀원"}).json()["axes"]}
    assert shape["업무"]["experiences"] == 1 and shape["기술"]["skills"] == 1 and shape["리더십"]["skills"] == 0   # 최근 3년
    every = {a["axis"]: a for a in owner.get("/api/growth/shape", params={"person": "가팀원", "period": "all"}).json()["axes"]}
    assert every["리더십"]["skills"] == 1
    assert member.get("/api/growth/shape", params={"person": "나팀원"}).json()["person"] == "가팀원"
    assert viewer.get("/api/growth/shape", params={"person": "가팀원"}).status_code == 403
