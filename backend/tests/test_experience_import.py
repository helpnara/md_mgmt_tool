"""응답 되받기 — 프롬프트 · 읽기 · 미리보기 · 저장 · 권한 (TODO 258 · 253 의 3단계, docs/팀원이력정리/3단계.md).

사람 · 과제 · 응답은 모두 지어낸 것이다(`test_contributions.team` + `fixtures/experience/` 가상 응답 다섯).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.config import get_settings
from app.services import experience_import as imp
from app.vault import markdown as md
from tests.test_contributions import team  # noqa: F401
from tests.test_experiences import _prepare

FIXTURES = Path(__file__).parent / "fixtures" / "experience"
EXPECTED_BLOCKS = {"fenced.md": 2, "no_fence.md": 2, "span_markers.md": 1, "broken.md": 1, "continued.md": 3}


def _block(title="출하 검사 판정 기준 정리", role="판정 기준 정리는 본인, 설비 연동은 설비팀", extra="", cont="없음", quant="- 재검 건수 | 월 30건 → 12건 | 기준: 기존 육안 판정 | 시점: 2026"):
    return f"""```slow-way
형식: slow-way-experience/0.1
이어짐: {cont}
제목: {title}
기간: 2026-03 ~ 2026-09
회사:
조직:
직위:
역할: {role}
구분: 업무
상황: 육안 판정이라 사람마다 결과가 달랐다.
목표: 재검을 줄인다.
행동:
- 불량 유형을 형태 기준으로 다시 나눔
- 두 단계 판정 설계
결과_정량:
{quant}
결과_정성: 다른 라인의 기준이 됨
비즈니스_영향:
역량_기술: 이미지 판정, Python
역량_업무: 품질 판정 체계
역량_리더십:
역량_문제해결: 문제 재정의
교훈: 놓쳐도 되는 수준을 먼저 합의했다.
증빙:
- 판정 기준서
확인_필요:
- 재검 건수의 정확한 값은?
{extra}```
"""


def _read(client, text, person="가팀원", **extra):
    return client.post("/api/experiences/read", json={"person": person, "text": text, **extra})


def _responses():
    return sorted(get_settings().people_dir.glob("*/experiences/responses/*.md"))


# ── 프롬프트 (3단계.md 2절) ───────────────────────────────────────────────────
def test_prompt_has_rules_format_records_and_leaves_out_names_and_money(team):  # noqa: F811
    owner, pid = team["owner"], team["shared"]
    _prepare(owner, pid)
    data = owner.get("/api/experiences/prompt", params={"person": "가팀원"}).json()
    assert data["projects"] == [pid]                                  # 기본 — 회고가 있고 구조화 경험이 없는 과제
    assert [c["id"] for c in data["choices"] if c["default"]] == [pid]
    text = data["text"]
    assert data["chars"] == len(text)
    for piece in ("형식: slow-way-experience/0.1", "```slow-way", "이어짐: E-nnn?", "결과_정량", "확인_필요",
                  f"## 과제 1. 함께 하는 과제 ({pid})", "- 배경: 출하 검사를 육안으로 해서 편차가 컸다.", "- 목표: 재검을 줄인다.",
                  "- 역할: 주관", "- 맡은 부분: 판정 기준 정리", "- 기술 · 도구: 이미지 판정, Python",
                  "  - 2026-06-30 시범 라인 적용", "- 내가 한 일:", "  - 불량 유형 재분류", "- 결과: 재검 월 30건 → 12건",
                  "[역량 목록]", "- 기술: 비전 AI 객체탐지", "- 문제해결: 문제 재정의", "[기존 경험 목록]"):
        assert piece in text, piece
    # 넣지 않는 것 — 팀원 이름 · 다른 사람 이름 · 효과 금액(3단계.md ⑤)
    assert "가팀원" not in text and "나팀원" not in text
    assert "3.5" not in text and "억원" not in text


def test_prompt_lists_existing_experiences_and_skills_and_takes_any_number_of_projects(team):  # noqa: F811
    owner, pid = team["owner"], team["shared"]
    _prepare(owner, pid)
    owner.post("/api/experiences/draft", json={"person": "가팀원", "projects": [pid]})
    extra = [owner.post("/api/projects", json={"title": f"과제 {n}", "owners": ["가팀원"], "status": "in_progress",
                                                "start_date": "2026-01-01"}).json()["id"] for n in range(7)]
    data = owner.get("/api/experiences/prompt", params={"person": "가팀원", "projects": ",".join([pid, *extra])}).json()
    assert data["projects"] == [pid, *extra]                           # ⑧ 과제 수를 막지 않는다(사용자 2026-11-10)
    assert "## 과제 8. 과제 6" in data["text"]
    assert f"- E-001 | 함께 하는 과제 | 2026-03 ~ ? | {pid}" in data["text"] and data["existing"] == 1
    assert owner.get("/api/experiences/prompt", params={"person": "가팀원", "projects": "2099-999"}).status_code == 400
    empty = owner.get("/api/experiences/prompt", params={"person": "가팀원", "projects": ""}).json()
    assert empty["projects"] == [] and empty["text"] == ""


def test_prompt_default_skips_projects_already_structured(team):  # noqa: F811
    owner, pid = team["owner"], team["shared"]
    _prepare(owner, pid)
    read = _read(owner, _block(), projects=[pid]).json()
    owner.post("/api/experiences/import", json={"person": "가팀원", "response": read["response"],
                                                "items": [{"index": 0, "action": "새로", "project": pid}]})
    data = owner.get("/api/experiences/prompt", params={"person": "가팀원"}).json()
    assert data["projects"] == [] and next(c for c in data["choices"] if c["id"] == pid)["structured"] is True


# ── 읽기 · 미리보기 (3단계.md 6절 ②③) ────────────────────────────────────────
@pytest.mark.parametrize("name", sorted(EXPECTED_BLOCKS))
def test_read_fixture_block_counts_and_keeps_raw(team, name):  # noqa: F811
    owner = team["owner"]
    text = (FIXTURES / name).read_text(encoding="utf-8")
    data = _read(owner, text).json()
    assert len(data["blocks"]) == EXPECTED_BLOCKS[name]
    saved = _responses()
    assert len(saved) == 1 and saved[0].stem == data["response"] == "2026-10-20-01"
    assert md.load(saved[0]).body.strip() == text.strip()             # 규칙 15 — 원문 그대로
    assert not list(get_settings().people_dir.glob("*/experiences/E-*.md"))   # 읽기는 경험을 바꾸지 않는다


def test_read_without_block_keeps_raw_and_says_so(team):  # noqa: F811
    owner = team["owner"]
    data = _read(owner, "죄송합니다. 정리할 수 없습니다.").json()
    assert data["blocks"] == [] and "형식 블록이 없습니다" in data["notice"]
    assert len(_responses()) == 1 and md.load(_responses()[0]).meta["blocks"] == 0
    second = _read(owner, "또 다른 응답").json()
    assert second["response"] == "2026-10-20-02"                       # 같은 날이면 번호를 올린다
    assert _read(owner, "   ").status_code == 400


def test_read_preview_fields_warnings_and_duplicates(team):  # noqa: F811
    owner = team["owner"]
    data = _read(owner, (FIXTURES / "continued.md").read_text(encoding="utf-8")).json()
    assert data["duplicates"] == [[0, 1]]
    first = data["blocks"][0]
    assert first["continues"] == "E-027" and first["continues_known"] is False     # 없는 번호 — 제안만, 기본은 새 경험
    assert first["action"] == "새로" and first["target"] == ""
    assert first["fields"]["start"] == "2026-03" and first["fields"]["end"] == "2026-09"
    broken = _read(owner, (FIXTURES / "broken.md").read_text(encoding="utf-8")).json()
    block = broken["blocks"][0]
    assert block["unknown"] == ["참고 사항"] and any("AI 가 더 적은 칸 — 참고 사항" in q for q in block["fields"]["open_questions"])
    assert broken["unknown_count"] == 1


def test_role_subject_warning(team):  # noqa: F811
    owner = team["owner"]
    data = _read(owner, _block(role="판정 기준 정리") + _block(title="둘째", role="판정 기준 정리는 본인")).json()
    codes = [[w["code"] for w in b["warnings"]] for b in data["blocks"]]
    assert "role_subject" in codes[0] and "role_subject" not in codes[1]


def test_read_append_joins_same_file(team):  # noqa: F811
    owner = team["owner"]
    first = _read(owner, _block()).json()
    more = _read(owner, _block(title="판정 결과 주간 공유"), append_to=first["response"]).json()
    assert more["response"] == first["response"] and len(more["blocks"]) == 2
    assert len(_responses()) == 1 and imp.APPEND_MARK.strip() in md.load(_responses()[0]).body
    assert _read(owner, "x", append_to="2099-01-01-01").status_code == 404
    assert _read(owner, "x", append_to="../../etc").status_code == 404


def test_default_target_is_the_single_draft_of_the_project(team):  # noqa: F811
    owner, pid = team["owner"], team["shared"]
    _prepare(owner, pid)
    owner.post("/api/experiences/draft", json={"person": "가팀원", "projects": [pid]})
    data = _read(owner, _block(), projects=[pid]).json()
    block = data["blocks"][0]
    assert (block["project"], block["action"], block["target"]) == (pid, "이어서", "E-001")
    target = next(t for t in data["targets"] if t["id"] == "E-001")
    assert target["touched"] is False and target["source"] == "담당"
    # 이어짐 E-001(물음표 없음) 이면 과제를 몰라도 그 경험으로
    sure = _read(owner, _block(cont="E-001")).json()["blocks"][0]
    assert (sure["action"], sure["target"], sure["project"]) == ("이어서", "E-001", pid)
    # 물음표는 제안만 — 그래도 그 경험의 과제에 담당 초안이 하나면 그 초안(③)
    maybe = _read(owner, _block(cont="E-001?")).json()["blocks"][0]
    assert (maybe["action"], maybe["target"], maybe["continues_known"]) == ("이어서", "E-001", True)
    loose = owner.post("/api/experiences", json={"person": "가팀원", "title": "과제 없는 경험"}).json()["id"]
    guess = _read(owner, _block(cont=f"{loose}?")).json()["blocks"][0]
    assert (guess["action"], guess["target"]) == ("새로", "")


# ── 저장 (3단계.md 6절 ③ · ④) ─────────────────────────────────────────────────
def test_save_new_makes_structured_with_fields_and_material(team):  # noqa: F811
    owner, pid = team["owner"], team["shared"]
    data = _read(owner, _block(), projects=[pid]).json()
    result = owner.post("/api/experiences/import", json={"person": "가팀원", "response": data["response"],
                                                         "items": [{"index": 0, "action": "새로", "project": pid}]}).json()
    assert result == {"made": ["E-001"], "merged": [], "dropped": 0}
    item = owner.get("/api/experiences/E-001").json()
    assert (item["status"], item["source"], item["project"]) == ("구조화", "응답", pid)
    assert item["title"] == "출하 검사 판정 기준 정리" and (item["start"], item["end"]) == ("2026-03", "2026-09")
    assert item["actions"] == ["불량 유형을 형태 기준으로 다시 나눔", "두 단계 판정 설계"]
    assert item["quants"][0]["metric"] == "재검 건수" and item["quants"][0]["baseline_kind"] == "비교"
    assert {"axis": "기술", "name": "Python"} in item["skills"] and {"axis": "문제해결", "name": "문제 재정의"} in item["skills"]
    assert item["evidences"][0]["text"] == "판정 기준서" and item["open_questions"] == ["재검 건수의 정확한 값은?"]
    assert item["materials"] == [f"response:{data['response']}"]
    assert md.load(_responses()[0]).meta["saved"] == ["E-001"]
    listing = owner.get("/api/experiences", params={"person": "가팀원"}).json()
    assert listing["counts"]["구조화"] == 1


def test_save_rereads_raw_not_client_values_and_drop(team):  # noqa: F811
    owner = team["owner"]
    data = _read(owner, _block() + _block(title="버릴 블록")).json()
    result = owner.post("/api/experiences/import", json={"person": "가팀원", "response": data["response"], "items": [
        {"index": 0, "action": "새로", "title": "화면이 바꾼 제목"}, {"index": 1, "action": "버림"}]}).json()
    assert result["made"] == ["E-001"] and result["dropped"] == 1
    assert owner.get("/api/experiences/E-001").json()["title"] == "출하 검사 판정 기준 정리"
    bad = owner.post("/api/experiences/import", json={"person": "가팀원", "response": data["response"],
                                                      "items": [{"index": 9, "action": "새로"}]})
    assert bad.status_code == 400
    assert owner.post("/api/experiences/import", json={"person": "가팀원", "response": data["response"],
                                                       "items": [{"index": 0, "action": "몰라"}]}).status_code == 400
    assert owner.post("/api/experiences/import", json={"person": "가팀원", "response": "2099-01-01-01",
                                                       "items": []}).status_code == 404
    assert owner.post("/api/experiences/import", json={"person": "가팀원", "response": data["response"],
                                                       "items": [{"index": 0, "project": "2099-999"}]}).status_code == 400


def test_merge_into_untouched_draft_takes_ai_values_and_keeps_money_and_questions(team):  # noqa: F811
    owner, pid = team["owner"], team["shared"]
    _prepare(owner, pid)
    owner.post("/api/experiences/draft", json={"person": "가팀원", "projects": [pid]})
    data = _read(owner, _block(), projects=[pid]).json()
    result = owner.post("/api/experiences/import", json={"person": "가팀원", "response": data["response"], "items": [
        {"index": 0, "action": "이어서", "target": "E-001", "project": pid}]}).json()
    assert result == {"made": [], "merged": ["E-001"], "dropped": 0}
    item = owner.get("/api/experiences/E-001").json()
    assert item["status"] == "구조화" and item["source"] == "담당"             # 출처 · 만든 때는 그대로
    assert item["title"] == "출하 검사 판정 기준 정리"                          # 고친 적 없는 초안 — AI 값
    assert item["actions"] == ["불량 유형을 형태 기준으로 다시 나눔", "두 단계 판정 설계"]
    assert (item["start"], item["end"]) == ("2026-03", "2026-09")              # 초안의 끝이 비어 있었다 — 채움
    # 합치는 칸 — 초안의 효과 금액 정량 · "본인 몫" 질문이 남는다
    assert [q["metric"] for q in item["quants"]] == ["과제 기대효과", "재검 건수"]
    assert any("본인이 기여한 몫" in q for q in item["open_questions"]) and "재검 건수의 정확한 값은?" in item["open_questions"]
    assert {"axis": "기술", "name": "이미지 판정"} in item["skills"]
    assert item["skills"].count({"axis": "기술", "name": "Python"}) == 1
    assert f"response:{data['response']}" in item["materials"]


def test_merge_into_touched_keeps_old_by_default_and_choose_overrides(team):  # noqa: F811
    owner, pid = team["owner"], team["shared"]
    _prepare(owner, pid)
    owner.post("/api/experiences/draft", json={"person": "가팀원", "projects": [pid]})
    owner.patch("/api/experiences/E-001", json={"title": "사람이 고친 제목", "goal": "사람이 고친 목표"})
    data = _read(owner, _block(), projects=[pid]).json()
    assert next(t for t in data["targets"] if t["id"] == "E-001")["touched"] is True
    owner.post("/api/experiences/import", json={"person": "가팀원", "response": data["response"], "items": [
        {"index": 0, "action": "이어서", "target": "E-001", "choose": {"goal": "new"}}]})
    item = owner.get("/api/experiences/E-001").json()
    assert item["title"] == "사람이 고친 제목"                                 # FR-C7 — 사람이 고친 것을 덮지 않는다
    assert item["goal"] == "재검을 줄인다."                                    # 고른 칸만 AI 값
    assert item["project"] == pid                                              # 과제를 비워 보내면 대상의 과제


def test_compare_lists_only_conflicting_fields():
    old = {"title": "가", "goal": "", "actions": ["하나"], "start": "2026-03", "end": "", "source": "담당",
           "created_at": "t", "updated_at": "t"}
    new = {"title": "나", "goal": "목표", "actions": ["하나"], "start": "2026-03", "end": "2026-09"}
    rows = imp.compare(old, new)
    assert [(r["field"], r["default"]) for r in rows] == [("title", "new"), ("period", "new")]
    assert imp.compare({**old, "updated_at": "u"}, new)[0]["default"] == "old"


def test_merge_refuses_other_person_or_confirmed(team):  # noqa: F811
    owner = team["owner"]
    other = owner.post("/api/experiences", json={"person": "나팀원", "title": "남의 경험"}).json()["id"]
    data = _read(owner, _block()).json()
    wrong = owner.post("/api/experiences/import", json={"person": "가팀원", "response": data["response"], "items": [
        {"index": 0, "action": "이어서", "target": other}]})
    assert wrong.status_code == 400 and "다른 사람" in wrong.json()["detail"]
    missing = owner.post("/api/experiences/import", json={"person": "가팀원", "response": data["response"], "items": [
        {"index": 0, "action": "이어서", "target": "E-099"}]})
    assert missing.status_code == 400
    # 한 번에 모두 검사한다 — 앞 블록도 저장되지 않는다
    assert not [p for p in get_settings().people_dir.glob("가팀원/experiences/E-*.md")]


def test_two_blocks_into_same_experience_reread_between(team):  # noqa: F811
    owner = team["owner"]
    base = owner.post("/api/experiences", json={"person": "가팀원", "title": "바탕"}).json()["id"]
    data = _read(owner, _block(quant="- 지표 가 | 1 | 기준: 기존 | 시점: 2026") + _block(quant="- 지표 나 | 2 | 기준: 기존 | 시점: 2026")).json()
    owner.post("/api/experiences/import", json={"person": "가팀원", "response": data["response"], "items": [
        {"index": 0, "action": "이어서", "target": base}, {"index": 1, "action": "이어서", "target": base}]})
    assert [q["metric"] for q in owner.get(f"/api/experiences/{base}").json()["quants"]] == ["지표 가", "지표 나"]


def test_long_values_are_cut_not_refused(team):  # noqa: F811
    owner = team["owner"]
    data = _read(owner, _block(title="가" * 300, role="본인 " + "나" * 900)).json()
    made = owner.post("/api/experiences/import", json={"person": "가팀원", "response": data["response"],
                                                       "items": [{"index": 0}]}).json()["made"]
    item = owner.get(f"/api/experiences/{made[0]}").json()
    assert len(item["title"]) <= 120 and len(item["role"]) <= 500


def test_structured_stays_structured_on_edit_and_patch_cannot_open_it(team):  # noqa: F811
    owner = team["owner"]
    data = _read(owner, _block()).json()
    owner.post("/api/experiences/import", json={"person": "가팀원", "response": data["response"], "items": [{"index": 0}]})
    edited = owner.patch("/api/experiences/E-001", json={"lesson": "고친 교훈"}).json()
    assert edited["status"] == "구조화"                                        # ⑨
    draft = owner.post("/api/experiences", json={"person": "가팀원", "title": "초안"}).json()["id"]
    assert owner.patch(f"/api/experiences/{draft}", json={"status": "구조화"}).status_code == 400


# ── 원문 보기 · 실험 요약 (3단계.md 8절) ──────────────────────────────────────
def test_response_file_and_summary_has_no_values(team):  # noqa: F811
    owner, pid = team["owner"], team["shared"]
    _prepare(owner, pid)
    data = _read(owner, (FIXTURES / "broken.md").read_text(encoding="utf-8"), projects=[pid]).json()
    raw = owner.get(f"/api/experiences/responses/가팀원/{data['response']}").json()
    assert raw["blocks"] == 1 and raw["projects"] == [pid] and "검사 장비 교체 검토" in raw["text"]
    text = owner.get(f"/api/experiences/responses/가팀원/{data['response']}/summary").json()["text"]
    assert "블록 1" in text and "미분류 키 참고 사항" in text and "프롬프트" in text
    assert "검사 장비 교체 검토" not in text                                   # 값은 담지 않는다
    assert owner.get("/api/experiences/responses/가팀원/2099-01-01-01").status_code == 404


# ── 권한 (3단계.md ⑥) ─────────────────────────────────────────────────────────
def test_only_managers_import_member_reads_own_raw_viewer_blocked(team):  # noqa: F811
    owner, member, viewer, pid = team["owner"], team["member"], team["viewer"], team["shared"]
    data = _read(owner, _block()).json()
    other = _read(owner, _block(), person="나팀원").json()
    assert member.get("/api/experiences/prompt", params={"person": "가팀원"}).status_code == 403
    assert _read(member, _block()).status_code == 403
    assert member.post("/api/experiences/import", json={"person": "가팀원", "response": data["response"],
                                                        "items": [{"index": 0}]}).status_code == 403
    assert member.get(f"/api/experiences/responses/가팀원/{data['response']}").status_code == 200
    assert member.get(f"/api/experiences/responses/나팀원/{other['response']}").status_code == 403
    assert member.get(f"/api/experiences/responses/가팀원/{data['response']}/summary").status_code == 403
    assert viewer.get("/api/experiences/prompt", params={"person": "가팀원"}).status_code == 403
    assert viewer.get(f"/api/experiences/responses/가팀원/{data['response']}").status_code == 403
    assert pid


# ── 따라가기 · 검색 ───────────────────────────────────────────────────────────
def test_rename_moves_responses_too(team):  # noqa: F811
    owner = team["owner"]
    data = _read(owner, _block()).json()
    owner.post("/api/experiences/import", json={"person": "가팀원", "response": data["response"], "items": [{"index": 0}]})
    assert owner.post("/api/people/rename", json={"old": "가팀원", "new": "가팀원2"}).status_code == 200
    moved = _responses()
    assert [p.parent.parent.parent.name for p in moved] == ["가팀원2"] and md.load(moved[0]).meta["person"] == "가팀원2"
    assert not (get_settings().people_dir / "가팀원" / "experiences").exists()
    assert owner.get(f"/api/experiences/responses/가팀원2/{data['response']}").status_code == 200


def test_search_does_not_find_responses(team):  # noqa: F811
    owner = team["owner"]
    _read(owner, _block(title="검색되지않는응답원문"))
    assert owner.post("/api/reindex").status_code == 200
    assert owner.get("/api/search", params={"q": "검색되지않는응답원문"}).json()["total"] == 0
    assert owner.get("/api/experiences", params={"person": "가팀원"}).json()["total"] == 0   # 원문은 경험이 아니다


# ── 259 — 같은 경험 기본값 · 요약의 과제 추정 · 저장 방법 · 초안 없는 과제 ────────
def test_two_blocks_pointing_same_draft_default_first_merge_rest_new(team):  # noqa: F811
    owner, pid = team["owner"], team["shared"]
    _prepare(owner, pid)
    owner.post("/api/experiences/draft", json={"person": "가팀원", "projects": [pid]})
    # 실험 2차(Teams Copilot) — 한 과제를 둘로 나누며 둘 다 그 초안을 가리켰다
    data = _read(owner, _block(cont="E-001") + _block(title="판정 결과 주간 공유", cont="E-001"), projects=[pid]).json()
    first, second = data["blocks"]
    assert (first["action"], first["target"], first["action_reason"]) == ("이어서", "E-001", "continues")
    assert (second["action"], second["target"], second["action_reason"], second["project"]) == ("새로", "", "shared", pid)
    assert first["project_reason"] == "continues"


def test_summary_has_project_guess_and_action_without_values(team):  # noqa: F811
    owner, pid = team["owner"], team["shared"]
    _prepare(owner, pid)
    owner.post("/api/experiences/draft", json={"person": "가팀원", "projects": [pid]})
    other = owner.post("/api/projects", json={"title": "다른 과제", "owners": ["가팀원"], "status": "in_progress",
                                              "start_date": "2026-01-01"}).json()["id"]
    text = (_block(cont="E-001") + _block(title="판정 결과 주간 공유", cont="E-001")
            + _block(title="엉뚱한 제목", cont="E-099"))
    data = _read(owner, text, projects=[pid, other]).json()
    summary = owner.get(f"/api/experiences/responses/가팀원/{data['response']}/summary").json()["text"]
    lines = [line for line in summary.splitlines() if line.startswith("- 블록")]
    assert "이어짐 있음(아는 번호)" in lines[0] and "과제 잡힘(이어짐)" in lines[0] and "저장 이어서(이어짐)" in lines[0]
    assert "저장 새로(같은 경험이 앞 블록에)" in lines[1]
    assert "이어짐 있음(없는 번호)" in lines[2] and "과제 없음" in lines[2] and lines[2].endswith("저장 새로")
    assert "같은 경험을 가리킨 블록 1개" in summary
    assert "E-001" not in summary and pid not in summary                     # 번호 같은 값은 넣지 않는다


def test_choices_mark_projects_without_experience(team):  # noqa: F811
    owner, pid = team["owner"], team["shared"]
    _prepare(owner, pid)
    before = owner.get("/api/experiences/prompt", params={"person": "가팀원"}).json()
    assert next(c for c in before["choices"] if c["id"] == pid)["has_experience"] is False
    owner.post("/api/experiences/draft", json={"person": "가팀원", "projects": [pid]})
    after = owner.get("/api/experiences/prompt", params={"person": "가팀원"}).json()
    assert next(c for c in after["choices"] if c["id"] == pid)["has_experience"] is True
