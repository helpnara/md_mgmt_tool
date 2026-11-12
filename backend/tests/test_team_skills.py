"""팀 역량 · 기술 스택 (TODO 284) — 사람 · 과제는 지어낸 것이다(`test_contributions.team`)."""
from __future__ import annotations

from tests.test_contributions import team  # noqa: F401


def _exp(client, person, title, status="구조화", start="2026-03", skills=(), tools=(), end=""):
    made = client.post("/api/experiences", json={"person": person, "title": title, "kind": "업무", "start": start, "end": end,
                                                 "skills": [{"axis": a, "name": n} for a, n in skills], "tools": list(tools)})
    assert made.status_code in (200, 201), made.text
    eid = made.json()["id"]
    if status != "초안":
        from app.config import get_settings  # 상태는 파일 머리말로 바로 — 확정 절차는 다른 시험이 본다
        from app.vault import markdown as md
        path = next(get_settings().people_dir.rglob(f"{eid}*.md"))
        doc = md.load(path)
        doc.meta["status"] = status
        md.save(path, doc)
        client.post("/api/reindex")
    return eid


def test_overview_counts_structured_and_confirmed_only(team):  # noqa: F811
    owner, pid = team["owner"], team["shared"]
    _exp(owner, "가팀원", "분석 경험", "확정", skills=[("업무", "데이터 분석")], tools=["파이썬"])
    _exp(owner, "나팀원", "분석 경험 둘", "구조화", skills=[("업무", "데이터 분석")], tools=["Minitab"])
    _exp(owner, "나팀원", "초안 경험", "초안", skills=[("리더십", "코칭")], tools=["Docker"])
    owner.put(f"/api/projects/{pid}/contributions/가팀원", json={"skills": "Python, 사내툴X"})
    data = owner.get("/api/team-skills").json()
    assert data["period"] == "3y" and [p["name"] for p in data["people"]] == ["팀장", "가팀원", "나팀원"]
    row = next(r for r in data["skills"] if r["name"] == "데이터 분석")
    assert row["holders"] == 2 and row["cells"]["가팀원"]["count"] == 1 and row["cells"]["가팀원"]["last"] == "2026"
    assert not any(r["name"] == "코칭" and r["holders"] for r in data["skills"])   # 초안은 세지 않는다
    tools = {t["name"]: t for layer in data["stack"] for t in layer["tools"]}
    assert tools["Python"]["person_count"] == 1 and tools["Python"]["project_count"] == 1 and tools["Python"]["experience_count"] == 1
    assert "Docker" not in tools
    layer_of = {t["name"]: layer["layer"] for layer in data["stack"] for t in layer["tools"]}
    assert layer_of["Python"] == "언어" and layer_of["Minitab"] == "분석/AI" and layer_of["사내툴X"] == "층 없음 · 사전에 없음"
    assert "사내툴X" in data["completeness"]["unlisted_tools"]
    people = {p["name"]: p for p in data["completeness"]["people"]}
    assert people["나팀원"]["초안"] == 1 and people["나팀원"]["구조화"] == 1
    assert {"kind": "보유 기술", "group": "언어", "name": "Python", "person": "가팀원"} in data["only_one"]


def test_period_left_and_private(team):  # noqa: F811
    owner, member = team["owner"], team["member"]
    _exp(owner, "가팀원", "옛 경험", "확정", start="2020-01", end="2020-06", skills=[("업무", "데이터 분석")])
    assert not any(r["holders"] for r in owner.get("/api/team-skills", params={"period": "3y"}).json()["skills"] if r["name"] == "데이터 분석")
    assert any(r["holders"] for r in owner.get("/api/team-skills", params={"period": "all"}).json()["skills"] if r["name"] == "데이터 분석")
    people = owner.get("/api/people").json()["people"]
    people = [{**p, "left_on": "2026-06-30", "left_reason": "퇴사"} if p["name"] == "나팀원" else p for p in people] + [{"name": "TBD"}]
    owner.put("/api/people", json={"people": people})
    names = [p["name"] for p in owner.get("/api/team-skills").json()["people"]]
    assert "나팀원" not in names and "TBD" not in names
    assert "나팀원" in [p["name"] for p in owner.get("/api/team-skills", params={"left": "1"}).json()["people"]]
    assert member.get("/api/team-skills").status_code == 403
    assert owner.get("/api/team-skills", params={"period": "x"}).status_code == 422


def test_tool_layer_saved_and_old_dictionary_filled(team):  # noqa: F811
    owner = team["owner"]
    tools = owner.get("/api/experiences/tools").json()
    assert "언어" in tools["layers"] and next(d for d in tools["dictionary"] if d["name"] == "Python")["layer"] == "언어"
    # 층 칸이 없던 옛 사전 → 기본 층으로, 새 층 이름도 저장
    assert owner.put("/api/settings", json={"tool_dictionary": [{"name": "Python", "aliases": []}, {"name": "사내툴X", "aliases": [], "layer": "사내 개발"}]}).status_code == 200
    tools = owner.get("/api/experiences/tools").json()
    layer = {d["name"]: d["layer"] for d in tools["dictionary"]}
    assert layer == {"Python": "언어", "사내툴X": "사내 개발"} and "사내 개발" in tools["layers"]
