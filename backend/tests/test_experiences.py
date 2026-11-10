"""팀원별 경험 — 저장 · 번호 · 초안 · 권한 (TODO 257 · 253 의 2단계, docs/팀원이력정리/2단계.md).

사람 · 과제는 모두 지어낸 것이다(`test_contributions.team` — 팀장 · 가팀원 · 나팀원).
"""
from __future__ import annotations

from app.config import get_settings
from app.vault import markdown as md
from tests.test_contributions import team  # noqa: F401

BODY = "## 배경\n\n> 서식 안내\n출하 검사를 육안으로 해서 편차가 컸다.\n\n## 목표\n\n재검을 줄인다.\n"


def _prepare(owner, pid):
    owner.patch(f"/api/projects/{pid}", json={"body": BODY, "effect_expected": 3.5})
    owner.put(f"/api/projects/{pid}/contributions/가팀원", json={
        "role": "주관", "part": "판정 기준 정리", "did": "- 불량 유형 재분류\n- 두 단계 판정 설계",
        "result": "재검 월 30건 → 12건", "skills": ["이미지 판정", "Python"],
        "milestones": [{"date": "2026-06-30", "text": "시범 라인 적용"}]})


def _exp_files():
    return sorted(get_settings().people_dir.glob("*/experiences/E-*.md"))


# ── 초안 (2단계.md 5절) ───────────────────────────────────────────────────────
def test_draft_from_contribution_maps_fields(team):  # noqa: F811
    owner, pid = team["owner"], team["shared"]
    _prepare(owner, pid)
    made = owner.post("/api/experiences/draft", json={"person": "가팀원", "projects": [pid]}).json()
    assert made == {"made": ["E-001"], "skipped": []}
    item = owner.get("/api/experiences/E-001").json()
    assert (item["title"], item["project"], item["status"], item["source"], item["kind"]) == ("함께 하는 과제", pid, "초안", "담당", "업무")
    assert item["role"] == "주관 · 판정 기준 정리"
    assert item["start"] == "2026-03" and item["end"] == ""          # 지금 맡고 있다
    assert item["situation"] == "출하 검사를 육안으로 해서 편차가 컸다." and item["goal"] == "재검을 줄인다."
    assert item["actions"] == ["불량 유형 재분류", "두 단계 판정 설계"]
    assert "재검 월 30건 → 12건" in item["result_qual"] and "2026-06-30 시범 라인 적용" in item["result_qual"]
    assert {"axis": "기술", "name": "Python"} in item["skills"]
    # ⑤ 숫자는 정량으로 옮기지 않고 질문으로
    assert any("재검 월 30건" in q and "비교 기준" in q for q in item["open_questions"])
    assert not any("시범 라인 적용" in q for q in item["open_questions"])     # 날짜만 숫자인 줄은 묻지 않는다
    # 효과 금액 — 가져온다(사용자 2026-11-10). 과제 전체 금액이라 본인 몫을 묻는다
    assert item["quants"] == [{"metric": "과제 기대효과", "value": "3.5억원/년", "baseline": "과제 전체 금액(본인 몫 아님)",
                               "baseline_kind": "집계", "when": ""}]
    assert any("본인이 기여한 몫" in q for q in item["open_questions"])
    # 다른 사람(나팀원) 이름은 들어가지 않는다
    assert "나팀원" not in repr(item)
    # 파일 — 사람 폴더 · 번호 이름 · 고정 절
    files = _exp_files()
    assert [path.name for path in files] == ["E-001.md"] and files[0].parent.parent.name == "가팀원"
    doc = md.load(files[0])
    assert doc.meta["id"] == "E-001" and doc.meta["status"] == "초안" and "## 행동\n\n- 불량 유형 재분류" in doc.body


def test_draft_skips_existing_and_all_takes_only_retro_projects(team):  # noqa: F811
    owner, pid = team["owner"], team["shared"]
    _prepare(owner, pid)
    other = owner.post("/api/projects", json={"title": "회고 없는 과제", "owners": ["가팀원"], "status": "in_progress",
                                              "start_date": "2026-05-01"}).json()["id"]
    assert owner.post("/api/experiences/draft", json={"person": "가팀원"}).json() == {"made": ["E-001"], "skipped": []}
    again = owner.post("/api/experiences/draft", json={"person": "가팀원", "projects": [pid]}).json()
    assert again["made"] == [] and "E-001" in again["skipped"][0]["reason"]
    assert owner.post("/api/experiences/draft", json={"person": "가팀원", "projects": ["2099-999"]}).status_code == 400
    assert other  # 회고가 없어 모두 초안에서 빠졌다


# ── 번호 · 고치기 · 지우기 ────────────────────────────────────────────────────
def test_numbers_never_reuse_and_trash_roundtrip(team):  # noqa: F811
    owner = team["owner"]
    a = owner.post("/api/experiences", json={"person": "가팀원", "title": "첫 경험"}).json()
    b = owner.post("/api/experiences", json={"person": "나팀원", "title": "둘째"}).json()
    assert (a["id"], b["id"], a["source"]) == ("E-001", "E-002", "직접")
    assert owner.delete("/api/experiences/E-002").status_code == 204
    assert owner.get("/api/experiences/E-002").status_code == 404
    c = owner.post("/api/experiences", json={"person": "가팀원", "title": "셋째"}).json()
    assert c["id"] == "E-003"                                   # 지운 번호를 다시 쓰지 않는다
    trash = owner.get("/api/trash").json()
    entry = next(item for item in trash if item["kind"] == "experience")
    assert entry["label"].startswith("E-002")
    assert owner.post(f"/api/trash/{entry['trash_name']}/restore").status_code == 200
    assert owner.get("/api/experiences/E-002").json()["title"] == "둘째"


def test_update_conflict_and_rules(team):  # noqa: F811
    owner = team["owner"]
    item = owner.post("/api/experiences", json={"person": "가팀원", "title": "가"}).json()
    saved = owner.patch("/api/experiences/E-001", json={
        "title": "고친 제목", "kind": "업무 외", "start": "2026-03", "end": "2026.09", "actions": ["하나", "- 둘"],
        "quants": [{"metric": "재검", "value": "줄어듦", "baseline": "", "baseline_kind": ""}],
        "skills": [{"axis": "리더십", "name": "후배 지도"}], "evidences": [{"type": "이미지", "text": "현장 사진"}],
        "base_updated_at": item["updated_at"]}).json()
    assert (saved["title"], saved["kind"], saved["end"], saved["actions"]) == ("고친 제목", "업무 외", "2026-09", ["하나", "둘"])
    assert saved["quants"][0]["baseline"] == "기준 없음" and saved["quants"][0]["baseline_kind"] == "미확인"   # ⑦ 미확인 유지
    assert saved["evidences"][0]["type"] == "이미지"                                                       # 1단계 ⑦
    stale = owner.patch("/api/experiences/E-001", json={"title": "늦은 손", "base_updated_at": item["updated_at"]})
    assert stale.status_code == 409
    for bad in ({"status": "확정"}, {"status": "구조화"}, {"kind": "사내"}, {"start": "2026-09", "end": "2026-03"},
                {"title": ""}, {"start": "작년"}, {"quants": [{"metric": "가", "baseline_kind": "모름"}]},
                {"skills": [{"axis": "체력", "name": "x"}]}):
        assert owner.patch("/api/experiences/E-001", json=bad).status_code == 400, bad
    # 사람 · 번호 · 출처 · 만든 때는 고칠 수 없다(보내도 무시)
    owner.patch("/api/experiences/E-001", json={"person": "나팀원", "id": "E-999", "source": "응답"})
    again = owner.get("/api/experiences/E-001").json()
    assert (again["person"], again["id"], again["source"]) == ("가팀원", "E-001", "직접")


def test_listing_counts_order_and_problems(team):  # noqa: F811
    owner, pid = team["owner"], team["shared"]
    _prepare(owner, pid)
    owner.post("/api/experiences/draft", json={"person": "가팀원", "projects": [pid]})
    owner.post("/api/experiences", json={"person": "가팀원", "title": "예전 일", "start": "2024-01", "kind": "업무"})
    data = owner.get("/api/experiences", params={"person": "가팀원"}).json()
    assert data["total"] == 2 and data["counts"] == {"초안": 2, "구조화": 0, "확정": 0}
    assert [item["id"] for item in data["items"]] == ["E-001", "E-002"]     # 시작 늦은 것부터
    first = data["items"][0]
    assert first["project_title"] == "함께 하는 과제" and first["open_count"] >= 2
    detail = owner.get("/api/experiences/E-001").json()
    assert any(p["code"] == "baseline_ask" for p in detail["problems"])     # 집계 기준 — 규칙 12 질문
    assert any(m.startswith("3.") for m in detail["confirm_missing"])        # 확인 필요가 남았다
    assert detail["confirm_missing"][-1].startswith("5.")                   # 정합성 경고(R-07 — "주관 · …") — 4단계
    assert owner.get("/api/experiences", params={"person": "나팀원"}).json()["total"] == 0


def test_draft_end_of_finished_project(team):  # noqa: F811
    """화면 확인에서 찾음(2026-11-10) — 끝난 과제인데 담당이 이어져(current) 끝이 '진행 중' 으로 비었다."""
    owner, pid = team["owner"], team["shared"]
    _prepare(owner, pid)
    owner.patch(f"/api/projects/{pid}", json={"status": "done", "completed_at": "2026-09-30"})
    owner.post("/api/experiences/draft", json={"person": "가팀원", "projects": [pid]})
    item = owner.get("/api/experiences/E-001").json()
    assert (item["start"], item["end"]) == ("2026-03", "2026-09") and item["quants"][0]["when"] == "2026"


# ── 색인 · 이름 · 번호 바꾸기 · 지운 과제 ─────────────────────────────────────
def test_reindex_rebuilds_from_files_and_flags_duplicate_ids(team, db):  # noqa: F811
    from app.vault.indexer import reindex_all

    owner = team["owner"]
    owner.post("/api/experiences", json={"person": "가팀원", "title": "가"})
    db.execute("DELETE FROM experience")
    copy = get_settings().people_dir / "나팀원" / "experiences"
    copy.mkdir(parents=True)
    (copy / "E-001.md").write_text(_exp_files()[0].read_text(encoding="utf-8"), encoding="utf-8")
    _, problems = reindex_all(db)
    assert db.execute("SELECT COUNT(*) FROM experience").fetchone()[0] == 1
    assert any("E-001" in p.reason and "둘" in p.reason for p in problems)


def test_rename_person_moves_folder_and_keeps_number(team):  # noqa: F811
    owner = team["owner"]
    owner.post("/api/experiences", json={"person": "가팀원", "title": "가"})
    result = owner.post("/api/people/rename", json={"old": "가팀원", "new": "가팀원2"}).json()
    assert result["counts"]["experiences"] == 1
    files = _exp_files()
    assert [(p.parent.parent.name, p.name) for p in files] == [("가팀원2", "E-001.md")]
    assert owner.get("/api/experiences/E-001").json()["person"] == "가팀원2"


def test_project_number_change_follows_and_deleted_project_stays(team, db):  # noqa: F811
    from app.services import projects as projects_service

    owner, pid = team["owner"], team["shared"]
    owner.post("/api/experiences", json={"person": "가팀원", "title": "가", "project": pid})
    projects_service.rewrite_project_refs(db, {pid: "2026-새-001"})
    from app.services import experiences as svc
    svc.reindex(db)
    db.commit()
    item = owner.get("/api/experiences/E-001").json()
    assert item["project"] == "2026-새-001" and item["project_gone"] is True      # 그런 과제가 없다 — 경험은 남는다


# ── 권한 (2단계.md ②) · 검색 ─────────────────────────────────────────────────
def test_member_sees_only_own_and_cannot_write_viewer_blocked(team):  # noqa: F811
    owner, member, viewer = team["owner"], team["member"], team["viewer"]
    owner.post("/api/experiences", json={"person": "가팀원", "title": "내 것"})
    owner.post("/api/experiences", json={"person": "나팀원", "title": "남의 것"})
    mine = member.get("/api/experiences", params={"person": "나팀원"}).json()   # 남을 물어도 자기 것만
    assert mine["person"] == "가팀원" and [item["title"] for item in mine["items"]] == ["내 것"]
    assert member.get("/api/experiences/E-001").status_code == 200
    assert member.get("/api/experiences/E-002").status_code == 403
    assert member.post("/api/experiences", json={"person": "가팀원", "title": "x"}).status_code == 403
    assert member.patch("/api/experiences/E-001", json={"title": "x"}).status_code == 403
    assert member.post("/api/experiences/draft", json={"person": "가팀원"}).status_code == 403
    assert viewer.get("/api/experiences", params={"person": "가팀원"}).status_code == 403
    assert viewer.get("/api/experiences/E-001").status_code == 403


def test_search_does_not_find_experiences(team):  # noqa: F811
    owner = team["owner"]
    owner.post("/api/experiences", json={"person": "가팀원", "title": "검색되지않는경험", "situation": "검색되지않는경험"})
    results = owner.get("/api/search", params={"q": "검색되지않는경험"}).json()
    assert results["total"] == 0 and "experiences" not in results
