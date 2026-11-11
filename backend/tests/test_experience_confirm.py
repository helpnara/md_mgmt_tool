"""역량 사전 · 정합성 · 확정 (TODO 260 · 253 의 4단계, docs/팀원이력정리/4단계.md).

사람 · 과제 · 경험은 모두 지어낸 것이다(`test_contributions.team` — 팀장 · 가팀원 · 나팀원).
"""
from __future__ import annotations

from app.experience import consistency as rules
from app.experience import skills as skill_rules
from tests.test_contributions import team  # noqa: F401
from tests.test_experience_import import _block, _read

FULL = {"person": "가팀원", "title": "판정 기준 정리", "kind": "업무", "start": "2026-03", "end": "2026-09",
        "role": "판정 기준 정리는 본인, 설비 연동은 설비팀", "situation": "육안 판정 편차", "actions": ["불량 유형 재분류"],
        "quants": [{"metric": "재검 건수", "value": "월 30건 → 12건", "baseline": "기존 육안 판정", "baseline_kind": "비교", "when": "2026"}]}


def _make(client, **change):
    return client.post("/api/experiences", json={**FULL, **change}).json()


# ── 역량 사전 (4단계.md 2절) ──────────────────────────────────────────────────
def test_default_dictionary_and_settings_roundtrip(team):  # noqa: F811
    owner = team["owner"]
    data = owner.get("/api/experiences/skills").json()
    assert len(data["dictionary"]) == 46 and data["custom"] is False      # 원본 9절의 표(글은 50개라 적었다)
    assert {d["axis"] for d in data["dictionary"]} == set(skill_rules.AXES)
    mine = [{"axis": "기술", "name": "이미지 판정", "aliases": ["비전 검사", "이미지 판정"]}]
    assert owner.put("/api/settings", json={"skill_dictionary": mine}).status_code == 200
    data = owner.get("/api/experiences/skills").json()
    assert data["custom"] is True and data["dictionary"] == [{"axis": "기술", "name": "이미지 판정", "aliases": ["비전 검사"]}]
    for bad in ([{"axis": "기타", "name": "x"}], [{"axis": "기술", "name": ""}],
                [{"axis": "기술", "name": "가"}, {"axis": "업무", "name": "가"}], "목록 아님"):
        assert owner.put("/api/settings", json={"skill_dictionary": bad}).status_code in (400, 422), bad
    assert owner.put("/api/settings", json={"skill_dictionary": []}).status_code == 200      # 빈 목록 = 기본으로
    assert len(owner.get("/api/experiences/skills").json()["dictionary"]) == 46


def test_tags_match_dictionary_names_and_axes(team):  # noqa: F811
    owner = team["owner"]
    made = _make(owner, skills=[{"axis": "업무", "name": "객체 탐지"}, {"axis": "기술", "name": "현장 감각"},
                                {"axis": "업무", "name": "PoC"}, {"axis": "기술", "name": "파이썬"}])
    assert made["skills"] == [{"axis": "기술", "name": "비전 AI 객체탐지"}, {"axis": "기술", "name": "현장 감각"},
                              {"axis": "문제해결", "name": "가설 검증·파일럿"}]           # 동의어 → 대표 이름 · 사전의 축
    assert made["skills_unknown"] == ["현장 감각"]                                      # ② 사전에 없음 — 그대로 둔다
    assert made["tools"] == ["Python"]                                                  # 273 — 보유 기술 사전의 이름은 보유 기술로(대표 이름)
    listing = owner.get("/api/experiences", params={"person": "가팀원"}).json()
    chips = {(s["axis"], s["name"]): s for s in listing["skills"]}
    assert chips[("기술", "현장 감각")]["known"] is False and chips[("기술", "비전 AI 객체탐지")]["count"] == 1


def test_same_alias_twice_goes_to_first():
    table = skill_rules.index(skill_rules.default_dictionary())
    assert table[skill_rules.key("요구사항 정의")] == ("업무", "요구사항 관리")             # 원본 표에서 둘에 있다 — 앞의 것


def test_merge_skill_rewrites_tags_and_keeps_old_name_as_alias(team):  # noqa: F811
    owner = team["owner"]
    _make(owner, skills=[{"axis": "업무", "name": "제품 기획"}])
    result = owner.post("/api/experiences/skills/merge", json={"source": {"axis": "업무", "name": "제품 기획"},
                                                               "target": {"axis": "업무", "name": "요구사항 관리"}}).json()
    assert result["changed"] == ["E-001"]
    assert owner.get("/api/experiences/E-001").json()["skills"] == [{"axis": "업무", "name": "요구사항 관리"}]
    dictionary = owner.get("/api/experiences/skills").json()["dictionary"]
    assert not any(d["name"] == "제품 기획" for d in dictionary)
    assert "제품 기획" in next(d for d in dictionary if d["name"] == "요구사항 관리")["aliases"]
    assert owner.post("/api/experiences/skills/merge", json={"source": {"axis": "기술", "name": "a"},
                                                             "target": {"axis": "기술", "name": "사전에 없는 것"}}).status_code == 400


def test_rematch_after_dictionary_change(team):  # noqa: F811
    owner = team["owner"]
    _make(owner, skills=[{"axis": "기술", "name": "현장 통계"}])
    owner.put("/api/settings", json={"skill_dictionary": [{"axis": "기술", "name": "데이터 분석 도구", "aliases": ["현장 통계"]}]})
    assert owner.post("/api/experiences/skills/rematch", json={"person": "가팀원"}).json()["changed"] == ["E-001"]
    item = owner.get("/api/experiences/E-001").json()
    assert item["skills"] == [{"axis": "기술", "name": "데이터 분석 도구"}] and item["skills_unknown"] == []


# ── 정합성 (4단계.md 3절) ─────────────────────────────────────────────────────
def _codes(item):
    return {w["code"] for w in item["consistency"]}


def test_consistency_codes(team):  # noqa: F811
    owner, pid = team["owner"], team["shared"]          # 가팀원의 담당 = 과제 시작 2026-03 부터
    a = _make(owner, project=pid, start="2026-01", actions=["2024 발표 자료 정리"],
              evidences=[{"type": "특허", "text": "판정 방법 특허"}, {"type": "수상", "text": "품질 우수상", "year": "2026"}])
    b = _make(owner, title="판정 기준 정리 ", start="", role="주관",
              evidences=[{"type": "특허", "text": "판정 방법 특허"}, {"type": "수상", "text": "품질 우수 상장", "year": "2026"}])
    first, second = owner.get(f"/api/experiences/{a['id']}").json(), owner.get(f"/api/experiences/{b['id']}").json()
    assert {"X-02", "X-03", "X-04", "X-05", "X-08"} <= _codes(first) and "R-07" not in _codes(first)
    assert {"X-07", "X-08", "X-05", "R-07"} <= _codes(second)
    clean = _make(owner, title="전혀 다른 일", project=pid, evidences=[])
    assert _codes(owner.get(f"/api/experiences/{clean['id']}").json()) == set()
    # 다른 사람의 경험과는 보지 않는다(④)
    other = _make(owner, person="나팀원", title="판정 기준 정리")
    assert "X-08" not in _codes(owner.get(f"/api/experiences/{other['id']}").json())
    # 목록의 경고 수에 더해진다
    listing = {i["id"]: i for i in owner.get("/api/experiences", params={"person": "가팀원"}).json()["items"]}
    assert listing[a["id"]]["warn_count"] >= 5 and listing[clean["id"]]["warn_count"] == 0


def test_role_subject_rule():
    assert rules.role_ok("판정 기준은 본인") and not rules.role_ok("주관 · 판정 기준 정리") and not rules.role_ok("")


def test_acknowledge_lifts_condition_and_comes_back_when_content_changes(team):  # noqa: F811
    owner = team["owner"]
    item = _make(owner, role="주관")
    warning = next(w for w in item["consistency"] if w["code"] == "R-07")
    assert any(m.startswith("5.") for m in item["confirm_missing"])
    after = owner.post(f"/api/experiences/{item['id']}/acknowledge", json={"code": "R-07", "key": warning["key"]}).json()
    assert next(w for w in after["consistency"] if w["code"] == "R-07")["acknowledged"] is True
    assert after["confirm_missing"] == []
    assert after["acknowledged"][0]["at"]                                     # 언제 넘겼나(원본 FR-F2)
    changed = owner.patch(f"/api/experiences/{item['id']}", json={"role": "주관 · 검토"}).json()
    assert any(m.startswith("5.") for m in changed["confirm_missing"])         # 내용이 바뀌면 다시 묻는다
    assert owner.post(f"/api/experiences/{item['id']}/acknowledge", json={"code": "X-99", "key": ""}).status_code == 400


# ── 확정 (4단계.md 4절) ───────────────────────────────────────────────────────
def test_confirm_needs_five_conditions_then_unconfirm(team):  # noqa: F811
    owner = team["owner"]
    thin = _make(owner, title="빈 경험", situation="", actions=[], quants=[], open_questions=["본인 몫은?"])
    refused = owner.post(f"/api/experiences/{thin['id']}/confirm")
    assert refused.status_code == 400 and "2." in refused.json()["detail"] and "3." in refused.json()["detail"]
    full = _make(owner)
    assert full["status"] == "초안" and full["confirm_missing"] == []
    done = owner.post(f"/api/experiences/{full['id']}/confirm").json()               # ⑥ 초안에서도 조건만 맞으면
    assert done["status"] == "확정" and done["confirmed_at"]
    assert owner.post(f"/api/experiences/{full['id']}/confirm").status_code == 400   # 이미 확정
    kept = owner.patch(f"/api/experiences/{full['id']}", json={"lesson": "고친 교훈"}).json()
    assert kept["status"] == "확정"                                                 # ⑧ 고쳐도 상태 유지
    assert owner.patch(f"/api/experiences/{full['id']}", json={"confirmed_at": "1999"}).json()["confirmed_at"] == done["confirmed_at"]
    back = owner.post(f"/api/experiences/{full['id']}/unconfirm").json()
    assert back["status"] == "구조화" and back["confirmed_at"] == ""
    assert owner.post(f"/api/experiences/{full['id']}/unconfirm").status_code == 400
    assert owner.get("/api/experiences", params={"person": "가팀원"}).json()["counts"]["구조화"] == 1


def test_confirm_quant_unknown_kind_blocks(team):  # noqa: F811
    owner = team["owner"]
    item = _make(owner, quants=[{"metric": "재검", "value": "12건", "baseline": "기준 없음", "baseline_kind": "미확인"}])
    assert any(m.startswith("4.") for m in item["confirm_missing"])
    assert owner.post(f"/api/experiences/{item['id']}/confirm").status_code == 400


def test_import_cannot_merge_into_confirmed(team):  # noqa: F811
    owner = team["owner"]
    full = _make(owner)
    owner.post(f"/api/experiences/{full['id']}/confirm")
    data = _read(owner, _block()).json()
    assert all(t["id"] != full["id"] for t in data["targets"])                         # 이어 붙일 후보에 없다
    refused = owner.post("/api/experiences/import", json={"person": "가팀원", "response": data["response"],
                                                          "items": [{"index": 0, "action": "이어서", "target": full["id"]}]})
    assert refused.status_code == 400 and "확정" in refused.json()["detail"]


# ── 권한 (⑦) ──────────────────────────────────────────────────────────────────
def test_only_managers_confirm_ack_merge(team):  # noqa: F811
    owner, member, viewer = team["owner"], team["member"], team["viewer"]
    item = _make(owner, role="주관")
    key = next(w for w in item["consistency"] if w["code"] == "R-07")["key"]
    assert member.post(f"/api/experiences/{item['id']}/confirm").status_code == 403
    assert member.post(f"/api/experiences/{item['id']}/acknowledge", json={"code": "R-07", "key": key}).status_code == 403
    assert member.post("/api/experiences/skills/merge", json={"source": {"axis": "기술", "name": "a"},
                                                              "target": {"axis": "기술", "name": "b"}}).status_code == 403
    assert member.get(f"/api/experiences/{item['id']}").json()["consistency"]                 # 보기는 된다(자기 것)
    assert viewer.post(f"/api/experiences/{item['id']}/confirm").status_code == 403
