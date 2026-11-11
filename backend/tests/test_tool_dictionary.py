"""역량과 보유 기술 가르기 (TODO 273) — 보유 기술 사전 · 맞춤 · 프롬프트 `도구:` · 요약 · 확정 전 알림.

사람 · 과제 · 경험은 모두 지어낸 것이다(`test_contributions.team`).
"""
from __future__ import annotations

from app.experience import skills as skill_rules
from app.experience import tools as tool_rules
from tests.test_contributions import team  # noqa: F401
from tests.test_experience_confirm import _make
from tests.test_experience_import import _block, _read


def test_default_dictionary_validate_and_normalize():
    dictionary = tool_rules.default_dictionary()
    assert tool_rules.normalize(["파이썬", "python", "SQL", "회귀 분석", " sql "], dictionary) == ["Python", "SQL", "회귀 분석"]
    assert tool_rules.validate([]) is None and tool_rules.validate(None) is None
    for bad in ("x", [{"name": ""}], [{"name": "가"}, {"name": "가"}], [{"name": "가", "aliases": ["나"]}, {"name": "나"}]):
        try:
            tool_rules.validate(bad)
        except ValueError:
            continue
        raise AssertionError(bad)
    # 역량 사전(기본)의 동의어에는 도구 이름이 없다
    aliases = {skill_rules.key(a) for d in skill_rules.default_dictionary() for a in d["aliases"]}
    assert not aliases & {skill_rules.key(n) for n in tool_rules.FORMER_SKILL_ALIASES}
    assert tool_rules.mentioned("ERP 연계와 R 로 분석, 파이썬 스크립트", dictionary) == ["Python", "R", "ERP"]
    assert "R" not in tool_rules.mentioned("ERP 연계", dictionary)


def test_only_dictionary_names_move_to_tools_not_names_typed_in_project_field(team):  # noqa: F811
    owner, pid = team["owner"], team["shared"]
    # 과제의 보유 기술 칸에 역량 이름("회귀 분석")을 적어 둬도, 역량 태그 "회귀 분석" 은 역량에 남는다(예전엔 도구로 넘어갔다)
    owner.put(f"/api/projects/{pid}/contributions/가팀원", json={"skills": ["회귀 분석", "파이썬"]})
    made = _make(owner, skills=[{"axis": "기술", "name": "회귀 분석"}, {"axis": "기술", "name": "C#"}], tools=["sql", "파이썬", "현장 계측기"])
    assert made["skills"] == [{"axis": "기술", "name": "회귀 분석"}]                    # 사전에 없는 역량 이름 — 역량에 그대로
    assert made["tools"] == ["SQL", "Python", "현장 계측기", "C#"]                      # 대표 이름으로 · C# 은 역량 칸에서 넘어옴
    assert not any(s["name"] == "C#" for s in made["skills"])
    # 과제 쪽 색인도 대표 이름으로
    rows = owner.get(f"/api/projects/{pid}").json()["contributions"]
    assert next(r for r in rows if r["name"] == "가팀원")["skills"] == ["회귀 분석", "Python"]


def test_settings_roundtrip_usage_unlisted_and_rematch(team):  # noqa: F811
    owner, pid = team["owner"], team["shared"]
    owner.put(f"/api/projects/{pid}/contributions/가팀원", json={"skills": ["스팟파이어", "현장 계측기", "품질 관리"]})
    _make(owner, tools=["현장 계측기", "Python"])
    data = owner.get("/api/experiences/tools").json()
    assert data["custom"] is False and data["usage"]["Spotfire"] == 1 and data["usage"]["Python"] == 1
    unlisted = {u["name"]: u for u in data["unlisted"]}
    assert unlisted["현장 계측기"]["count"] == 2 and unlisted["품질 관리"]["skill_like"] is True
    mine = [*data["dictionary"], {"name": "계측기", "aliases": ["현장 계측기"]}]
    assert owner.put("/api/settings", json={"tool_dictionary": mine}).status_code == 200
    assert owner.post("/api/experiences/tools/rematch").json()["changed"] == ["E-001"]
    assert owner.get("/api/experiences/E-001").json()["tools"] == ["계측기", "Python"]
    rows = owner.get(f"/api/projects/{pid}").json()["contributions"]
    assert next(r for r in rows if r["name"] == "가팀원")["skills"] == ["Spotfire", "계측기", "품질 관리"]
    assert owner.put("/api/settings", json={"tool_dictionary": [{"name": "가"}, {"name": "가"}]}).status_code in (400, 422)
    assert owner.put("/api/settings", json={"tool_dictionary": []}).status_code == 200
    assert owner.get("/api/experiences/tools").json()["custom"] is False


def test_prompt_has_tool_key_and_response_tools_are_saved(team):  # noqa: F811
    owner, pid = team["owner"], team["shared"]
    owner.put(f"/api/projects/{pid}/contributions/가팀원", json={"did": "- 기준 정리", "result": "재검 감소"})
    text = owner.get("/api/experiences/prompt", params={"person": "가팀원"}).json()["text"]
    assert '13. "도구"에는' in text and "역량_문제해결:\n도구:\n교훈:" in text
    block = _block().replace("교훈:", "도구: 파이썬, MES, 현장 계측기\n교훈:", 1)
    data = _read(owner, block, projects=[pid]).json()
    assert data["blocks"][0]["fields"]["tools"] == ["파이썬", "MES", "현장 계측기"] and data["blocks"][0]["unknown"] == []
    owner.post("/api/experiences/import", json={"person": "가팀원", "response": data["response"],
                                                "items": [{"index": 0, "action": "새로", "project": pid}]})
    assert owner.get("/api/experiences/E-001").json()["tools"][:3] == ["Python", "MES", "현장 계측기"]


def test_summary_and_notes_before_confirm(team):  # noqa: F811
    owner, pid = team["owner"], team["shared"]
    owner.put(f"/api/projects/{pid}/contributions/가팀원", json={"skills": ["Python", "MES"]})
    made = _make(owner, tools=["파이썬"], actions=["SQL 로 이력 추출", "판정 기준 재정리"], end="2025-09", start="2025-03")
    assert made["tool_notes"] and "SQL" in made["tool_notes"][0]
    empty = _make(owner, title="둘째", actions=["기준 재정리"])
    assert "비어 있습니다" in empty["tool_notes"][0]
    tools = {t["name"]: t for t in owner.get("/api/experiences", params={"person": "가팀원"}).json()["tools"]}
    assert tools["Python"]["projects"] == 1 and tools["Python"]["experiences"] == 1 and tools["Python"]["known"] is True
    assert tools["MES"]["experiences"] == 0 and tools["Python"]["last"] >= "2025"
