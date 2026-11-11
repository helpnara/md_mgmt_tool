"""역량 태그 정리함 — 여러 경우를 한 번에 (TODO 280).

사용자(2026-11-11): 적용이 올바르게 안 되고, "액세스가 거부되었습니다" 같은 오류가 난다. 경우를 세워 시험하고 고친다.
사람 · 경험은 지어낸 것이다(`test_contributions.team`).
"""
from __future__ import annotations

import os

import pytest

from app.vault import markdown as md
from tests.test_contributions import team  # noqa: F401


def _exp(client, person="가팀원", title="경험", **extra):
    made = client.post("/api/experiences", json={"person": person, "title": title, "kind": "업무", **extra})
    assert made.status_code in (200, 201), made.text
    return made.json()


def _unknown(client):
    return {(t["axis"], t["name"]): t for t in client.get("/api/experiences/skills/unknown").json()["items"]}


def _apply(client, actions):
    return client.post("/api/experiences/skills/cleanup", json={"actions": actions})


def _dict(client):
    return client.get("/api/experiences/skills").json()["dictionary"]


# ── 1. 네 가지 정리가 모두 · 한 번에 ──────────────────────────────────────────────
def test_alias_new_tool_drop_all_at_once_and_list_empties(team):  # noqa: F811
    owner = team["owner"]
    a = _exp(owner, title="하나", skills=[{"axis": "기술", "name": "현장 데이터 정제"}, {"axis": "업무", "name": "설비 담당 협의"}])
    b = _exp(owner, person="나팀원", title="둘", skills=[{"axis": "기술", "name": "현장 데이터 정제"}, {"axis": "기술", "name": "사내계측툴"},
                                                         {"axis": "기술", "name": "시스템 구축"}])
    assert set(_unknown(owner)) == {("기술", "현장 데이터 정제"), ("업무", "설비 담당 협의"), ("기술", "사내계측툴"), ("기술", "시스템 구축")}
    out = _apply(owner, [
        {"axis": "기술", "name": "현장 데이터 정제", "action": "alias", "target_axis": "기술", "target_name": "데이터 파이프라인"},
        {"axis": "업무", "name": "설비 담당 협의", "action": "new", "target_axis": "리더십"},
        {"axis": "기술", "name": "사내계측툴", "action": "tool"},
        {"axis": "기술", "name": "시스템 구축", "action": "drop"}]).json()
    assert sorted(out["changed"]) == sorted([a["id"], b["id"]]) and out["failed"] == [] and out["left"] == 0
    first = owner.get(f"/api/experiences/{a['id']}").json()
    assert first["skills"] == [{"axis": "기술", "name": "데이터 파이프라인"}, {"axis": "리더십", "name": "설비 담당 협의"}]
    second = owner.get(f"/api/experiences/{b['id']}").json()
    assert second["skills"] == [{"axis": "기술", "name": "데이터 파이프라인"}] and second["tools"] == ["사내계측툴"]
    entry = next(d for d in _dict(owner) if d["name"] == "데이터 파이프라인")
    assert "현장 데이터 정제" in entry["aliases"]
    assert _unknown(owner) == {}


# ── 2. 같은 결정을 두 번 — 결과가 같다 ───────────────────────────────────────────
def test_apply_twice_is_harmless(team):  # noqa: F811
    owner = team["owner"]
    _exp(owner, skills=[{"axis": "기술", "name": "현장 데이터 정제"}])
    action = [{"axis": "기술", "name": "현장 데이터 정제", "action": "alias", "target_axis": "기술", "target_name": "데이터 파이프라인"}]
    assert len(_apply(owner, action).json()["changed"]) == 1
    again = _apply(owner, action).json()
    assert again["changed"] == [] and again["failed"] == []
    entry = next(d for d in _dict(owner) if d["name"] == "데이터 파이프라인")
    assert entry["aliases"].count("현장 데이터 정제") == 1


# ── 3. "새 역량" 인데 그 이름이 이미 다른 역량의 다른 이름이면 — 그 역량으로 ───────────
def test_new_whose_name_is_already_an_alias_maps_to_that_entry(team):  # noqa: F811
    owner = team["owner"]
    made = _exp(owner, skills=[{"axis": "업무", "name": "현장 데이터 정제"}])
    dictionary = _dict(owner)
    for d in dictionary:
        if d["name"] == "데이터 파이프라인":
            d["aliases"] = [*d["aliases"], "현장데이터정제x"]
    owner.put("/api/settings", json={"skill_dictionary": dictionary})
    out = _apply(owner, [{"axis": "업무", "name": "현장 데이터 정제", "action": "new", "target_axis": "업무"}]).json()
    assert out["changed"] == [made["id"]] and out["left"] == 0
    assert {"axis": "업무", "name": "현장 데이터 정제"} in owner.get(f"/api/experiences/{made['id']}").json()["skills"]


# ── 4. 확정한 경험도 바뀌고 상태는 그대로 ─────────────────────────────────────────
def test_confirmed_experience_is_updated_and_stays_confirmed(team):  # noqa: F811
    owner = team["owner"]
    made = _exp(owner, skills=[{"axis": "기술", "name": "현장 데이터 정제"}])
    from app.services import experiences as exp
    from app.deps import connect
    conn = connect()
    try:
        exp._set_status(conn, made["id"], "확정", {"confirmed_at": exp.now_iso(), "confirmed_by": "팀장"})
    finally:
        conn.close()
    _apply(owner, [{"axis": "기술", "name": "현장 데이터 정제", "action": "drop"}])
    after = owner.get(f"/api/experiences/{made['id']}").json()
    assert after["status"] == "확정" and after["skills"] == []


# ── 5. 틀린 결정이 하나라도 있으면 아무것도 바꾸지 않는다 ─────────────────────────────
def test_bad_decision_changes_nothing(team):  # noqa: F811
    owner = team["owner"]
    _exp(owner, skills=[{"axis": "기술", "name": "현장 데이터 정제"}])
    before = _dict(owner)
    bad = _apply(owner, [{"axis": "기술", "name": "현장 데이터 정제", "action": "drop"},
                         {"axis": "기술", "name": "x", "action": "alias", "target_axis": "기술", "target_name": "사전에 없는 것"}])
    assert bad.status_code == 400 and _dict(owner) == before and ("기술", "현장 데이터 정제") in _unknown(owner)


# ── 6. 잠깐 잠긴 파일(윈도우의 액세스 거부)은 다시 시도해 고친다 ─────────────────────
def test_transient_access_denied_is_retried(team, monkeypatch):  # noqa: F811
    owner = team["owner"]
    made = _exp(owner, skills=[{"axis": "기술", "name": "현장 데이터 정제"}])
    real = os.replace
    left = {"n": 2}

    def flaky(src, dst):
        if str(dst).endswith(f"{made['id']}.md") and left["n"] > 0:
            left["n"] -= 1
            raise PermissionError(5, "액세스가 거부되었습니다")
        return real(src, dst)

    monkeypatch.setattr(md.os, "replace", flaky)
    out = _apply(owner, [{"axis": "기술", "name": "현장 데이터 정제", "action": "drop"}]).json()
    assert out["changed"] == [made["id"]] and out["failed"] == []


# ── 7. 계속 잠긴 파일 — 나머지는 고치고 못 고친 것을 알린다, 다시 누르면 남은 것만 ─────────
def test_locked_file_is_reported_and_rest_applied_then_retry_finishes(team, monkeypatch):  # noqa: F811
    owner = team["owner"]
    a = _exp(owner, title="하나", skills=[{"axis": "기술", "name": "현장 데이터 정제"}])
    b = _exp(owner, title="둘", skills=[{"axis": "기술", "name": "현장 데이터 정제"}])
    real = os.replace

    def locked(src, dst):
        if str(dst).endswith(f"{a['id']}.md"):
            raise PermissionError(5, "액세스가 거부되었습니다")
        return real(src, dst)

    monkeypatch.setattr(md.os, "replace", locked)
    monkeypatch.setattr("app.vault.paths.SAVE_RETRY_DELAYS", (0.0,))
    action = [{"axis": "기술", "name": "현장 데이터 정제", "action": "alias", "target_axis": "기술", "target_name": "데이터 파이프라인"}]
    out = _apply(owner, action)
    assert out.status_code == 200, out.text
    body = out.json()
    assert body["changed"] == [b["id"]] and [f["id"] for f in body["failed"]] == [a["id"]]
    assert "사용 중" in body["failed"][0]["reason"]
    monkeypatch.setattr(md.os, "replace", real)
    # 사전에는 이미 다른 이름으로 들어가 있다 — 정리함 목록에서는 사라지지만, 파일은 아직 옛 태그. 다시 맞추기로 끝낸다
    again = owner.post("/api/experiences/skills/rematch", json={"person": "가팀원"}).json()
    assert a["id"] in again["changed"]
    assert owner.get(f"/api/experiences/{a['id']}").json()["skills"] == [{"axis": "기술", "name": "데이터 파이프라인"}]


# ── 8. AI 의 답 읽기 — 화면 이름 · 여러 표기 ─────────────────────────────────────────
@pytest.mark.parametrize("right,action,axis", [
    ("도구", "tool", None), ("보유 기술(도구)", "tool", None), ("보유기술", "tool", None), ("버림", "drop", None),
    ("새 역량(업무)", "new", "업무"), ("새 역량(전문기술)", "new", "기술"), ("새역량", "new", "기술"),
    ("데이터 파이프라인", "alias", "기술"), ("데이터파이프라인 ?", "alias", "기술"),
])
def test_answer_words(team, right, action, axis):  # noqa: F811
    owner = team["owner"]
    _exp(owner, skills=[{"axis": "기술", "name": "현장 데이터 정제"}])
    items = owner.post("/api/experiences/skills/answer", json={"text": f"- 현장 데이터 정제 | {right}\n- 없는 태그 | 버림"}).json()["items"]
    assert len(items) == 1 and items[0]["action"] == action
    if axis:
        assert items[0].get("target_axis") == axis
