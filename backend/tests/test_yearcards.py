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


def test_no_count_limits(team):  # noqa: F811
    """287 — 과제 · 역량 · 보유 기술 개수 제한 없음."""
    owner = team["owner"]
    ids = [team["shared"]] + [owner.post("/api/projects", json={"title": f"제한 없음 과제 {i}", "owners": ["가팀원"], "status": "in_progress",
                                                                "start_date": "2026-03-02"}).json()["id"] for i in range(4)]
    skills = [f"역량{i}" for i in range(5)]
    tools = [f"도구{i}" for i in range(5)]
    saved = owner.put("/api/yearcards/card", params={"name": "가팀원", "year": "2026"},
                      json={"projects": ids, "skills": skills, "tools": tools}).json()
    assert len(saved["picked"]) == 5 and saved["skills"] == skills and saved["tools"] == tools
    fresh = owner.get("/api/yearcards/card", params={"name": "나팀원", "year": "2026"}).json()
    assert len(fresh["chosen"]) <= 2            # 처음엔 위 둘


def test_listing_hides_placeholder_names_and_marks_left(team):  # noqa: F811
    """288 — TBD 같은 자리 이름은 빼고, 떠난 사람(그 해에 떠난 사람도)은 left 로 표시."""
    owner = team["owner"]
    people = owner.get("/api/people").json()["people"]
    people += [{"name": "TBD"}, {"name": "미정 (신규)"}, {"name": "공석"},
               {"name": "올해퇴사", "left_on": "2026-06-30", "left_reason": "퇴사"}, {"name": "작년전배", "left_on": "2025-05-01", "left_reason": "전배"}]
    assert owner.put("/api/people", json={"people": people}).status_code == 200
    listing = owner.get("/api/yearcards", params={"year": "2026"}).json()["people"]
    names = {p["name"]: p for p in listing}
    assert not {"TBD", "미정 (신규)", "공석", "작년전배"} & set(names)
    assert names["올해퇴사"]["left"] is True and names["올해퇴사"]["left_reason"] == "퇴사" and names["가팀원"]["left"] is False


def test_311_colleagues_partners_and_signed_date(team):  # noqa: F811
    """311 — 숫자 줄의 함께한 동료 · 부서(본인 · TBD 빼고, 같은 사람 · 부서는 한 번), 서명 날짜(카드마다 · 모두 같게)."""
    owner, pid = team["owner"], team["shared"]
    owner.patch(f"/api/projects/{pid}", json={"owners": ["가팀원", "나팀원", "TBD"],
                                             "partners": [{"team": "설비기술팀", "people": "김철수"}, {"team": "품질팀"}]})
    other = owner.post("/api/projects", json={"title": "둘째 과제", "owners": ["가팀원", "나팀원"], "status": "in_progress",
                                              "start_date": "2026-04-01", "partners": [{"team": "품질팀"}]}).json()["id"]
    card = owner.get("/api/yearcards/card", params={"name": "가팀원", "year": "2026"}).json()
    n = card["numbers"]
    assert n["colleagues"] == 1 and n["colleague_names"] == ["나팀원"]          # TBD · 본인 빼고, 두 과제에서 한 번
    assert n["partners"] == 2 and set(n["partner_teams"]) == {"설비기술팀", "품질팀"}
    assert card["signed_on"] == "" and card["signed_default"] == "2026. 12."
    saved = owner.put("/api/yearcards/card", params={"name": "가팀원", "year": "2026"},
                      json={"message": "고마워요", "projects": [pid, other], "signed_on": "2026. 12. 24."}).json()
    assert saved["signed_on"] == "2026. 12. 24."
    assert owner.put("/api/yearcards/card", params={"name": "가팀원", "year": "2026"},
                     json={"signed_on": "가" * 21}).status_code == 400
    owner.put("/api/yearcards/card", params={"name": "나팀원", "year": "2026"}, json={"message": "수고했어요"})
    done = owner.put("/api/yearcards/signed-on", json={"year": "2026", "signed_on": "2026년 겨울"}).json()
    assert done["cleared"] == ["가팀원"] and done["signed_default"] == "2026년 겨울"     # 따로 적은 날짜는 지우고 기본으로
    for who in ("가팀원", "나팀원", "팀장"):                                              # 저장 안 한 카드도 따른다
        got = owner.get("/api/yearcards/card", params={"name": who, "year": "2026"}).json()
        assert got["signed_on"] == "" and got["signed_default"] == "2026년 겨울"
    owner.put("/api/yearcards/signed-on", json={"year": "2026", "signed_on": ""})
    assert owner.get("/api/yearcards/card", params={"name": "가팀원", "year": "2026"}).json()["signed_default"] == "2026. 12."
    assert owner.get("/api/yearcards/card", params={"name": "가팀원", "year": "2026"}).json()["message"] == "고마워요"   # 편지는 그대로
    assert team["member"].put("/api/yearcards/signed-on", json={"year": "2026", "signed_on": "x"}).status_code == 403


def test_311_card_only_title(team):  # noqa: F811
    """311 — 카드에서만 과제명을 줄인다(원본 과제명 그대로, 같으면 남기지 않음, 40자까지)."""
    owner, pid = team["owner"], team["shared"]
    title = owner.get(f"/api/projects/{pid}").json()["title"]
    saved = owner.put("/api/yearcards/card", params={"name": "가팀원", "year": "2026"},
                      json={"projects": [pid], "lines": {pid: {"title": ["짧은 이름"]}}}).json()
    assert saved["picked"][0]["title_card"] == "짧은 이름" and saved["picked"][0]["title"] == title
    assert owner.get(f"/api/projects/{pid}").json()["title"] == title
    same = owner.put("/api/yearcards/card", params={"name": "가팀원", "year": "2026"},
                     json={"projects": [pid], "lines": {pid: {"title": [title]}}}).json()
    assert same["picked"][0]["title_card"] == title and not same["picked"][0]["edited"]
    assert owner.put("/api/yearcards/card", params={"name": "가팀원", "year": "2026"},
                     json={"projects": [pid], "lines": {pid: {"title": ["가" * 41]}}}).status_code == 400
