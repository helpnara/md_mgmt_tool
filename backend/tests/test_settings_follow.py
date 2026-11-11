"""설정을 바꾸면 쓰는 곳도 따라가게 (TODO 275 — docs/검토-설정반영-2026-11-11.md 빈틈 1 ~ 4)."""
from __future__ import annotations

from tests.test_contributions import team  # noqa: F401


def _intake(client, **extra):
    return client.post("/api/intakes", json={"title": "분류 시험 접수", "leader": "가팀원", **extra}).json()


# ── 빈틈 1 — 분류 넷의 이름 바꾸기 · 합치기 ─────────────────────────────────────
def test_classification_usage_and_rename_follows_projects_and_intakes(team):  # noqa: F811
    owner = team["owner"]
    p = owner.post("/api/projects", json={"title": "현장 과제", "type": "smart", "nature": "현장적용"}).json()
    i = _intake(owner, nature="현장적용")
    usage = {u["value"]: u for u in owner.get("/api/settings/classifications/usage").json()["usage"]["nature"]}
    assert usage["현장적용"]["projects"] == 1 and usage["현장적용"]["intakes"] == 1 and usage["현장적용"]["listed"] is True
    done = owner.post("/api/settings/classifications/rename", json={"field": "nature", "old": "현장적용", "new": "현장 적용"}).json()
    assert (done["projects"], done["intakes"], done["merged"]) == (1, 1, False)
    assert owner.get(f"/api/projects/{p['id']}").json()["nature"] == "현장 적용"
    assert owner.get(f"/api/intakes/{i['id']}").json()["nature"] == "현장 적용"
    lists = {c["key"]: c["items"] for c in owner.get("/api/meta").json()["classifications"]}
    assert "현장 적용" in lists["nature"] and "현장적용" not in lists["nature"]
    assert lists["nature"].index("현장 적용") == 1                                       # 같은 자리
    natures = {row["label"]: row for row in owner.get("/api/home").json()["natures"]}
    assert "현장적용" not in natures and natures["현장 적용"]["count"] == 1


def test_rename_into_existing_merges_and_unlisted_old_value_shows(team):  # noqa: F811
    owner = team["owner"]
    owner.post("/api/projects", json={"title": "옛 값 과제", "type": "smart", "nature": "옛 성격"})
    usage = {u["value"]: u for u in owner.get("/api/settings/classifications/usage").json()["usage"]["nature"]}
    assert usage["옛 성격"]["listed"] is False and usage["옛 성격"]["projects"] == 1
    done = owner.post("/api/settings/classifications/rename", json={"field": "nature", "old": "옛 성격", "new": "기타"}).json()
    assert done["merged"] is True and done["projects"] == 1
    usage = {u["value"]: u for u in owner.get("/api/settings/classifications/usage").json()["usage"]["nature"]}
    assert "옛 성격" not in usage and usage["기타"]["projects"] == 1
    assert owner.post("/api/settings/classifications/rename", json={"field": "x", "old": "a", "new": "b"}).status_code == 400
    assert owner.post("/api/settings/classifications/rename", json={"field": "nature", "old": "a", "new": "a"}).status_code == 400


# ── 빈틈 2 — 명부 표에서 이름을 고칠 때 ──────────────────────────────────────────
def test_roster_keeps_account_when_renamed_and_counts_other_records(team):  # noqa: F811
    owner = team["owner"]
    people = owner.get("/api/people").json()["people"]
    rows = [{**p, "former": p["name"]} for p in people]
    for row in rows:
        if row["name"] == "가팀원":
            row["name"] = "가 팀원"
    assert owner.put("/api/people", json={"people": rows}).status_code == 200
    renamed = next(p for p in owner.get("/api/people").json()["people"] if p["name"] == "가 팀원")
    assert renamed["ips"]                                                               # PC 주소가 따라왔다(예전엔 잃음)
    # 과제 담당이 아닌 기록(면담)만 남은 옛 이름도 [통일] 목록에
    owner.post("/api/experiences", json={"person": "다팀원", "title": "경험만 있는 사람", "kind": "업무"})
    unregistered = {u["name"]: u for u in owner.get("/api/people").json()["unregistered"]}
    assert unregistered["다팀원"]["used"] == 0 and unregistered["다팀원"]["records"] >= 1
    assert unregistered["가팀원"]["used"] >= 1


# ── 빈틈 3 — 역량 사전에서 이름을 고치면 경험의 태그도 ─────────────────────────────
def test_skill_rename_follows_experience_tags(team):  # noqa: F811
    owner = team["owner"]
    made = owner.post("/api/experiences", json={"person": "가팀원", "title": "태그 경험", "kind": "업무",
                                                "skills": [{"axis": "업무", "name": "품질 관리"}]}).json()
    dictionary = owner.get("/api/experiences/skills").json()["dictionary"]
    changed = [{**d, "name": "품질 보증", "aliases": [*d["aliases"], "품질 관리"]} if d["name"] == "품질 관리" else d for d in dictionary]
    assert owner.put("/api/settings", json={"skill_dictionary": changed}).status_code == 200
    out = owner.post("/api/experiences/skills/rename", json={"source": {"axis": "업무", "name": "품질 관리"},
                                                               "target": {"axis": "업무", "name": "품질 보증"}}).json()
    assert out["changed"] == [made["id"]]
    item = owner.get(f"/api/experiences/{made['id']}").json()
    assert item["skills"] == [{"axis": "업무", "name": "품질 보증"}] and item["skills_unknown"] == []
    bad = owner.post("/api/experiences/skills/rename", json={"source": {"axis": "업무", "name": "a"}, "target": {"axis": "업무", "name": "사전에 없음"}})
    assert bad.status_code == 400


# ── 빈틈 4 — 스마트과제 속성은 뺄 수 없다 ────────────────────────────────────────
def test_smart_type_cannot_be_removed(team):  # noqa: F811
    owner = team["owner"]
    types = owner.get("/api/settings/project-types").json()["types"]
    without = [t for t in types if t["key"] != "smart"]
    r = owner.put("/api/settings/project-types", json={"types": [{"key": t["key"], "label": t["label"]} for t in without]})
    assert r.status_code == 400 and "스마트과제" in r.json()["detail"]
    renamed = [{"key": t["key"], "label": "스마트 과제" if t["key"] == "smart" else t["label"]} for t in types]
    assert owner.put("/api/settings/project-types", json={"types": renamed}).status_code == 200
    # 속성을 안 쓰는 팀(목록을 통째로 비움 — TODO 100)은 되고, 그때 승격한 과제는 속성 없음
    assert owner.put("/api/settings/project-types", json={"types": []}).status_code == 200
    from app.services import intakes
    assert intakes._promote_type() is None


def test_pool_listing_carries_unlisted_values_for_remote_screens(team):  # noqa: F811
    """접수 풀의 거르기 상자 — 옛 값은 접수 목록이 함께 준다(설정 끝점은 서버 PC 밖에서 막혀 있다)."""
    owner, member = team["owner"], team["member"]
    _intake(owner, nature="옛 성격")
    assert owner.get("/api/intakes").json()["unlisted"]["nature"] == ["옛 성격"]
    assert member.get("/api/settings/classifications/usage").status_code == 403
    assert member.get("/api/intakes").json()["unlisted"]["nature"] == ["옛 성격"]
