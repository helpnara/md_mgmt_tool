"""역량 태그 정리(261) · 업무 이력 파일 · 익명화 · 기록 · 팀원 보완 (TODO 262 · 253 의 5단계, docs/팀원이력정리/5단계.md).

사람 · 과제 · 경험은 모두 지어낸 것이다(`test_contributions.team` — 팀장 · 가팀원 · 나팀원).
"""
from __future__ import annotations

from app.experience import skills as skill_rules
from tests.test_contributions import team  # noqa: F401
from tests.test_experience_confirm import FULL, _make
from tests.test_experiences import _prepare


def _confirmed(client, **change):
    item = _make(client, **change)
    for w in item["consistency"]:
        client.post(f"/api/experiences/{item['id']}/acknowledge", json={"code": w["code"], "key": w["key"]})
    done = client.post(f"/api/experiences/{item['id']}/confirm")
    assert done.status_code == 200, done.text
    return done.json()


def _export(client, **params):
    return client.get("/api/experiences/export", params={"person": "가팀원", **params})


# ── 261 — 도구 칸 · 동의어 · 프롬프트 규칙 ────────────────────────────────────
def test_team_tools_move_from_skills_to_tools(team):  # noqa: F811
    owner, pid = team["owner"], team["shared"]
    _prepare(owner, pid)                                         # 담당과 역할의 기술 · 도구 = 이미지 판정 · Python
    item = _make(owner, skills=[{"axis": "기술", "name": "Python"}, {"axis": "기술", "name": "운영 최적화"}])
    assert item["tools"] == ["Python"]
    assert item["skills"] == [{"axis": "기술", "name": "최적화·시뮬레이션"}]          # 261 ② 동의어


def test_suggested_aliases_for_custom_dictionary(team):  # noqa: F811
    owner = team["owner"]
    owner.put("/api/settings", json={"skill_dictionary": [{"axis": "업무", "name": "요구사항 관리", "aliases": []}]})
    assert owner.post("/api/experiences/skills/suggest").json() == {"added": 3}
    assert owner.post("/api/experiences/skills/suggest").json() == {"added": 0}         # 두 번째는 건너뜀
    aliases = owner.get("/api/experiences/skills").json()["dictionary"][0]["aliases"]
    assert aliases == ["현업 요구사항 분석", "사용자 요구사항 해결", "현업 VOC 분석"]


def test_structure_prompt_has_tag_rule(team):  # noqa: F811
    owner, pid = team["owner"], team["shared"]
    _prepare(owner, pid)
    text = owner.get("/api/experiences/prompt", params={"person": "가팀원"}).json()["text"]
    assert "넓은 말 대신 무엇을 잘했는지" in text and "Python, SQL)은 역량에 쓰지 않습니다" in text


# ── 태그 정리함 (역량태그입력.md) ─────────────────────────────────────────────
def test_unknown_tags_and_cleanup_actions(team):  # noqa: F811
    owner, pid = team["owner"], team["shared"]
    _prepare(owner, pid)
    a = _make(owner, skills=[{"axis": "기술", "name": "알고리즘 개발"}, {"axis": "기술", "name": "현장 데이터 정제"},
                             {"axis": "업무", "name": "설비 담당 협의"}])
    owner.put(f"/api/projects/{pid}/contributions/가팀원", json={"skills": ["이미지 판정", "Python", "MES"]})
    _make(owner, title="둘째", skills=[{"axis": "기술", "name": "알고리즘 개발"}, {"axis": "기술", "name": "Matlab"}])
    items = {t["name"]: t for t in owner.get("/api/experiences/skills/unknown").json()["items"]}
    assert items["알고리즘 개발"]["count"] == 2 and items["알고리즘 개발"]["people"] == ["가팀원"]
    assert items["현장 데이터 정제"]["suggest"]                                          # 비슷한 대표 역량 제안
    bad = owner.post("/api/experiences/skills/cleanup", json={"actions": [
        {"axis": "기술", "name": "현장 데이터 정제", "action": "alias", "target_axis": "기술", "target_name": "사전에 없는 것"}]})
    assert bad.status_code == 400
    done = owner.post("/api/experiences/skills/cleanup", json={"actions": [
        {"axis": "기술", "name": "현장 데이터 정제", "action": "alias", "target_axis": "기술", "target_name": "데이터 파이프라인"},
        {"axis": "업무", "name": "설비 담당 협의", "action": "new", "target_axis": "리더십"},
        {"axis": "기술", "name": "Matlab", "action": "tool"},
        {"axis": "기술", "name": "알고리즘 개발", "action": "drop"}]}).json()
    assert len(done["changed"]) == 2
    first = owner.get(f"/api/experiences/{a['id']}").json()
    assert first["skills"] == [{"axis": "기술", "name": "데이터 파이프라인"}, {"axis": "리더십", "name": "설비 담당 협의"}]
    second = owner.get("/api/experiences/E-002").json()
    assert second["skills"] == [] and second["tools"] == ["Matlab"]
    dictionary = owner.get("/api/experiences/skills").json()["dictionary"]
    assert "현장 데이터 정제" in next(d for d in dictionary if d["name"] == "데이터 파이프라인")["aliases"]
    assert {"axis": "리더십", "name": "설비 담당 협의", "aliases": []} in dictionary
    assert owner.get("/api/experiences/skills/unknown").json()["items"] == []


def test_tag_prompt_and_answer_become_proposals_only(team):  # noqa: F811
    owner = team["owner"]
    _make(owner, skills=[{"axis": "기술", "name": "알고리즘 개발"}, {"axis": "기술", "name": "Matlab"},
                         {"axis": "업무", "name": "현업 협의 회의"}, {"axis": "기술", "name": "현장 데이터 정제"}])
    prompt = owner.get("/api/experiences/skills/prompt").json()
    assert prompt["tags"] == 4 and "- 기술 — 알고리즘 개발 · 1" in prompt["text"] and "[역량 사전]" in prompt["text"]
    answer = """설명은 무시합니다.
- 알고리즘 개발 | 버림
- Matlab | 도구
- 현업 협의 회의 | 요구사항 관리 ?
- 현장 데이터 정제 | 새 역량(기술)
- 없는 태그 | 도구
- 알고리즘 개발2 | 엉뚱한 이름"""
    rows = {r["name"]: r for r in owner.post("/api/experiences/skills/answer", json={"text": answer}).json()["items"]}
    assert rows["알고리즘 개발"]["action"] == "drop" and rows["Matlab"]["action"] == "tool"
    assert (rows["현업 협의 회의"]["action"], rows["현업 협의 회의"]["target_name"], rows["현업 협의 회의"]["unsure"]) == ("alias", "요구사항 관리", True)
    assert (rows["현장 데이터 정제"]["action"], rows["현장 데이터 정제"]["target_axis"]) == ("new", "기술")
    assert "없는 태그" not in rows
    assert len(owner.get("/api/experiences/skills/unknown").json()["items"]) == 4       # 답만으로는 바뀌지 않는다


# ── 업무 이력 파일 (5단계.md 3절) ─────────────────────────────────────────────
def test_export_only_confirmed_and_shape(team):  # noqa: F811
    owner, pid = team["owner"], team["shared"]
    _prepare(owner, pid)
    done = _confirmed(owner, project=pid, start="2026-03", tools=["Python"], skills=[{"axis": "문제해결", "name": "PoC"}],
                      evidences=[{"type": "특허", "text": "판정 방법 특허", "year": "2026"}])
    _make(owner, title="구조화 아님 초안")
    data = _export(owner).json()
    text = data["text"]
    assert data["ids"] == [done["id"]] and data["summary"]["experiences"] == 1
    for piece in ("format: slow-way-career-context", "version: 0.2", "owner: 가팀원", "scope: 전체", "status_included: 확정",
                  "anonymized: false", "experience_count: 1", "# 사용 안내 (AI에게)", "(E-001)", "# 프로필", "- 이름: 가팀원",
                  "- 특허: 판정 방법 특허 (2026)", "# 과제", f"| {pid} | 함께 하는 과제 |", f"## [{done['id']}] 판정 기준 정리",
                  "- 기간: 2026-03 ~ 2026-09", "- 상태: 확정", "- 도구: Python", "### 결과",
                  "- 정량: 재검 건수 | 월 30건 → 12건 | 기준: 기존 육안 판정 | 시점: 2026", "- 문제해결: 가설 검증·파일럿",
                  "# 역량 색인", "| 문제해결 | 가설 검증·파일럿 | E-001 |", "# 기술 · 도구", "| Python | E-001 |",
                  "# 정량 성과 목록", "| 재검 건수 | 월 30건 → 12건 | 기존 육안 판정 | 2026 | E-001 |"):
        assert piece in text, piece
    assert "구조화 아님 초안" not in text                                             # ④ 초안은 들어가지 않는다
    assert "### 목표" not in text and "### 교훈" not in text and "### 확인 필요" not in text   # 빈 칸 절은 뺀다
    assert not any(line.rstrip().endswith(":") for line in text.splitlines() if line.startswith("- "))   # 빈 줄 없음
    assert data["filename"].startswith("업무이력_가팀원_전체_") and data["filename"].endswith(".md")
    assert _export(owner).json()["text"] == text                                         # 같은 입력 = 같은 출력


def test_export_options_ids_money_structured_period_pick(team):  # noqa: F811
    owner, pid = team["owner"], team["shared"]
    _prepare(owner, pid)
    owner.post("/api/experiences/draft", json={"person": "가팀원", "projects": [pid]})       # 효과 금액 정량이 든 초안
    owner.patch("/api/experiences/E-001", json={"role": "판정 기준은 본인", "situation": "편차", "actions": ["재분류"],
                                                "open_questions": [], "title": "초안에서 다듬은 경험", "start": "2026-03", "end": "2026-09"})
    item = owner.get("/api/experiences/E-001").json()
    for w in item["consistency"]:
        owner.post("/api/experiences/E-001/acknowledge", json={"code": w["code"], "key": w["key"]})
    quants = [{**q, "baseline_kind": "집계"} for q in item["quants"]]
    owner.patch("/api/experiences/E-001", json={"quants": quants})
    assert owner.post("/api/experiences/E-001/confirm").status_code == 200
    plain = _export(owner).json()["text"]
    assert "과제 기대효과" not in plain and "억원" not in plain                           # ③ 기본은 효과 금액을 뺀다
    money = _export(owner, money="true").json()
    assert "과제 기대효과" in money["text"] and any("효과 금액" in w for w in money["warnings"])
    no_ids = _export(owner, ids_in="false").json()["text"]
    assert "## 초안에서 다듬은 경험" in no_ids and "[E-001]" not in no_ids and "(E-001)" not in no_ids
    # 구조화 포함
    _make(owner, title="구조화 경험", start="2024-01", end="2024-06")
    owner.post("/api/experiences/E-002/confirm")
    owner.post("/api/experiences/E-002/unconfirm")
    both = _export(owner, structured="true").json()
    assert both["summary"]["structured"] == 1 and any("확정되지 않은 경험 1건" in w for w in both["warnings"])
    # 기간 겹침 · 선택
    period = _export(owner, scope="period", start="2024-01", end="2024-12", structured="true").json()
    assert period["ids"] == ["E-002"] and "scope: 기간 2024-01~2024-12" in period["text"]
    pick = _export(owner, scope="pick", ids="E-001").json()
    assert pick["ids"] == ["E-001"]
    assert _export(owner, scope="period").status_code == 400


def test_anonymize_rules_and_leftover_warning(team):  # noqa: F811
    owner, pid = team["owner"], team["shared"]
    _prepare(owner, pid)
    _confirmed(owner, project=pid, role="판정 기준은 본인, 나팀원과 함께", situation="가나철강의 라인에서 나팀원이 보고한 편차",
               evidences=[{"type": "특허", "text": "등록 10-1234567"}])
    rules = {"rules": [{"kind": "회사", "from": "가나철강", "to": "A사"}, {"kind": "인명", "from": "가팀원", "to": "본인"}]}
    assert owner.put("/api/settings", json={"anonymize_rules": rules}).status_code == 200
    data = _export(owner, anonymize="true").json()
    text = data["text"]
    assert "A사의 라인" in text and "가나철강" not in text and "owner: 익명" in text and "- 이름: 익명" in text
    assert "특허 등록번호" in text and "10-1234567" not in text                           # 기본 정규식
    assert "[E-001]" in text and pid in text                                              # 근거 ID · 과제 번호는 지키기
    assert data["summary"]["replaced"]["회사"] == 1
    assert any("치환하지 않은 후보" in w and "나팀원" in w for w in data["warnings"])        # 명부의 다른 이름이 남았다
    candidates = {c["text"]: c for c in owner.get("/api/experiences/anonymize/candidates", params={"person": "가팀원"}).json()["items"]}
    assert candidates["가팀원"]["in_rules"] is True and candidates["나팀원"]["suggest"].startswith("동료")
    assert owner.put("/api/settings", json={"anonymize_rules": {"patterns": [{"regex": "(", "to": "x"}]}}).status_code == 400
    assert data["filename"].startswith("업무이력_익명_")


def test_export_log_keeps_no_content(team):  # noqa: F811
    owner = team["owner"]
    _confirmed(owner)
    assert owner.post("/api/experiences/export/log", json={"person": "가팀원", "how": "복사"}).status_code == 201
    rows = owner.get("/api/experiences/export/log", params={"person": "가팀원"}).json()["items"]
    assert len(rows) == 1 and rows[0]["how"] == "복사" and rows[0]["count"] == 1 and rows[0]["options"]["scope"] == "all"
    assert "판정 기준 정리" not in str(rows)


# ── 권한 · 팀원 보완 (⑥ · ⑦) ─────────────────────────────────────────────────
def test_member_exports_own_and_fills_own_draft(team):  # noqa: F811
    owner, member, viewer = team["owner"], team["member"], team["viewer"]
    mine = _make(owner, role="주관")
    theirs = _make(owner, person="나팀원", title="남의 것")
    assert member.get("/api/experiences/export", params={"person": "가팀원"}).status_code == 200
    assert member.get("/api/experiences/export", params={"person": "나팀원"}).status_code == 403
    assert member.post("/api/experiences/export/log", json={"person": "가팀원"}).status_code == 201
    assert member.post("/api/experiences/export/log", json={"person": "나팀원"}).status_code == 403
    edited = member.patch(f"/api/experiences/{mine['id']}", json={"lesson": "팀원이 보완", "status": "구조화"})
    assert edited.status_code == 200
    assert edited.json()["lesson"] == "팀원이 보완" and edited.json()["status"] == "초안" and edited.json()["edited_by_member_at"]
    assert member.patch(f"/api/experiences/{theirs['id']}", json={"lesson": "x"}).status_code == 403
    done = _confirmed(owner, title="확정한 것")
    assert done["edited_by_member_at"] == ""
    assert member.patch(f"/api/experiences/{done['id']}", json={"lesson": "x"}).status_code == 403
    assert member.post(f"/api/experiences/{mine['id']}/confirm").status_code == 403
    assert member.delete(f"/api/experiences/{mine['id']}").status_code == 403
    assert member.get("/api/experiences/skills/unknown").status_code == 403
    assert viewer.get("/api/experiences/export", params={"person": "가팀원"}).status_code == 403


def test_similar_suggestion_rule():
    found = skill_rules.similar("현장 데이터 정제", skill_rules.default_dictionary())
    assert found and found[0]["name"] == "데이터 파이프라인"
    assert FULL["person"] == "가팀원"
