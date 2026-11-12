"""연말 회고 카드 (TODO 285) — 사람 · 과제는 지어낸 것이다(`test_contributions.team`)."""
from __future__ import annotations

from tests.test_contributions import team  # noqa: F401


def test_card_defaults_from_year_and_saves_message(team):  # noqa: F811
    owner, pid = team["owner"], team["shared"]
    owner.put(f"/api/projects/{pid}/contributions/가팀원", json={"did": "- 판정 기준 정리", "result": "재검 월 30 → 12건", "praise": "끝까지 챙겨 줘서 고마워요"})
    owner.patch(f"/api/projects/{pid}", json={"status": "done", "completed_at": "2026-10-01"})
    data = owner.get("/api/yearcards/card", params={"name": "가팀원", "year": "2026"}).json()
    assert data["chosen"] == [pid] and data["picked"][0]["result"].startswith("재검") and data["picked"][0]["praise"]
    assert "감사 편지" in data["missing"] and data["saved"] is False
    saved = owner.put("/api/yearcards/card", params={"name": "가팀원", "year": "2026"},
                      json={"message": "올 한 해 고마웠어요.", "headline": "끝까지 챙긴 한 해", "projects": [pid, "없는-과제"]}).json()
    assert saved["saved"] and saved["message"] == "올 한 해 고마웠어요." and saved["chosen"] == [pid] and saved["missing"] == []
    listing = owner.get("/api/yearcards", params={"year": "2026"}).json()
    row = next(p for p in listing["people"] if p["name"] == "가팀원")
    assert row["has_message"] and row["picked"] == 1
    printed = owner.get("/api/yearcards/cards", params={"year": "2026", "names": "가팀원,나팀원"}).json()["cards"]
    assert [c["name"] for c in printed] == ["가팀원", "나팀원"]


def test_message_limit_and_private(team):  # noqa: F811
    owner, member, viewer = team["owner"], team["member"], team["viewer"]
    too_long = owner.put("/api/yearcards/card", params={"name": "가팀원", "year": "2026"}, json={"message": "가" * 401})
    assert too_long.status_code == 400 and "400자" in too_long.json()["detail"]
    assert member.get("/api/yearcards", params={"year": "2026"}).status_code == 403          # 팀원 PC 에는 막힘
    assert viewer.get("/api/yearcards/card", params={"name": "가팀원", "year": "2026"}).status_code == 403
    assert owner.get("/api/yearcards", params={"year": "26"}).status_code == 422


def test_lines_two_each_edit_only_on_card_and_chips(team):  # noqa: F811
    """286 — 수행 2줄 · 결과 2줄(원본 앞 두 줄), 카드에서만 다듬기, 역량 · 보유 기술 3개씩."""
    owner, pid = team["owner"], team["shared"]
    owner.put(f"/api/projects/{pid}/contributions/가팀원", json={
        "did": "- 판정 기준 정리\n- 시험 설계\n- 현장 적용", "result": "- 재검 월 30 → 12건\n- 판정 시간 절반", "skills": "Python, Minitab, Python"})
    owner.post("/api/experiences", json={"person": "가팀원", "title": "판정 기준 경험", "kind": "업무", "project": pid, "start": "2026-03",
                                         "skills": [{"axis": "업무", "name": "문제 정의"}, {"axis": "업무", "name": "데이터 분석"},
                                                    {"axis": "업무", "name": "문제 정의"}], "tools": ["Excel"]})
    data = owner.get("/api/yearcards/card", params={"name": "가팀원", "year": "2026"}).json()
    work = data["picked"][0]
    assert work["did_lines_card"] == ["판정 기준 정리", "시험 설계"] and work["result_lines_card"] == ["재검 월 30 → 12건", "판정 시간 절반"]
    assert data["skills"][:2] == ["문제 재정의", "데이터 분석"] and data["tools"][0] == "Python" and "Excel" in data["tools"]
    saved = owner.put("/api/yearcards/card", params={"name": "가팀원", "year": "2026"}, json={
        "message": "고마워요", "projects": [pid], "skills": ["데이터 분석"], "tools": ["Minitab", "Python"],
        "lines": {pid: {"did": ["판정 기준을 처음부터 다시 세움", "시험 설계"], "result": ["재검 월 30 → 12건", "판정 시간 절반"]}}}).json()
    work = saved["picked"][0]
    assert work["did_lines_card"][0] == "판정 기준을 처음부터 다시 세움" and work["edited"] is True
    assert saved["skills"] == ["데이터 분석"] and saved["tools"] == ["Minitab", "Python"]
    # 원본 과제는 그대로
    row = next(r for r in owner.get(f"/api/projects/{pid}").json()["contributions"] if r["name"] == "가팀원")
    assert row["did"].startswith("- 판정 기준 정리")
    # 원본으로 — 다듬은 줄을 원본과 같게 보내면 남기지 않는다
    back = owner.put("/api/yearcards/card", params={"name": "가팀원", "year": "2026"}, json={
        "message": "고마워요", "projects": [pid], "lines": {pid: {"did": ["판정 기준 정리", "시험 설계"]}}}).json()
    assert back["picked"][0]["edited"] is False and back["skills"][:2] == ["문제 재정의", "데이터 분석"]
    too_long = owner.put("/api/yearcards/card", params={"name": "가팀원", "year": "2026"}, json={
        "projects": [pid], "lines": {pid: {"did": ["가" * 81]}}})
    assert too_long.status_code == 400


def test_result_falls_back_to_experience_quants(team):  # noqa: F811
    owner, pid = team["owner"], team["shared"]
    owner.post("/api/experiences", json={"person": "나팀원", "title": "원단위 경험", "kind": "업무", "project": pid, "start": "2026-04",
                                         "actions": ["조업 조건 분석", "시험 3회"],
                                         "quants": [{"metric": "전극봉 원단위", "value": "2.10 → 1.85 kg/t", "baseline": "2024 평균", "baseline_kind": "비교", "when": "2026"}]})
    work = owner.get("/api/yearcards/card", params={"name": "나팀원", "year": "2026"}).json()["picked"][0]
    assert work["did_lines_card"] == ["조업 조건 분석", "시험 3회"] and work["result_lines_card"] == ["전극봉 원단위 2.10 → 1.85 kg/t"]
