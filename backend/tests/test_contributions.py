"""담당과 역할 — 역할 · 맡은 부분 · 담당 기간 · 회고 세 줄 · 금액 아닌 성과 (TODO 237).

팀원이 나중에 본인의 업무 이력 · 성과를 정리할 재료. 팀장(127.0.0.1) · 팀원(명부에 등록한 10.0.0.5) · 읽기(10.0.0.9) 셋으로 본다.
시험의 오늘은 2026-10-20 (conftest).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.vault import markdown as md

MEMBER_IP = "10.0.0.5"
TODAY = "2026-10-20"


@pytest.fixture()
def team(tmp_path, monkeypatch):
    monkeypatch.setenv("MD_MGMT_VAULT", str(tmp_path / "vault"))
    monkeypatch.setenv("MD_MGMT_SHARE", "1")
    get_settings.cache_clear()
    from app import readcache, share, who

    monkeypatch.setattr(share, "_today", {"date": None, "ips": set(), "requests": 0})
    monkeypatch.setattr(share, "_seen", {})
    who.forget()
    from app.main import app

    with TestClient(app, client=("127.0.0.1", 51101)) as owner, \
            TestClient(app, client=(MEMBER_IP, 51102)) as member, \
            TestClient(app, client=("10.0.0.9", 51103)) as viewer:
        assert owner.put("/api/people", json={"people": [
            {"name": "팀장", "leader": True}, {"name": "가팀원", "ips": [MEMBER_IP]}, {"name": "나팀원"}]}).status_code == 200
        shared = owner.post("/api/projects", json={
            "title": "함께 하는 과제", "owners": ["가팀원", "나팀원"], "status": "in_progress", "start_date": "2026-03-02"}).json()
        readcache.bump()
        yield {"owner": owner, "member": member, "viewer": viewer, "shared": shared["id"]}
    who.forget()
    get_settings.cache_clear()


def _index_md(project_id: str):
    projects = get_settings().projects_dir
    return next(projects.glob(f"{project_id}*")) / "index.md"


def _rows(client, project_id):
    return {row["name"]: row for row in client.get(f"/api/projects/{project_id}").json()["contributions"]}


def test_owners_without_record_read_from_start_date_and_file_stays_clean(team):
    rows = _rows(team["owner"], team["shared"])
    assert list(rows) == ["가팀원", "나팀원"]
    assert rows["가팀원"]["from"] == "2026-03-02" and rows["가팀원"]["to"] is None
    assert rows["가팀원"]["derived"] is True and rows["가팀원"]["current"] is True
    # 미리 적어 두지 않는다 — 누가 고칠 때 처음 적힌다
    assert "contributions" not in md.load(_index_md(team["shared"])).meta


def test_owner_changes_follow_the_period(team):
    owner, pid = team["owner"], team["shared"]
    assert owner.patch(f"/api/projects/{pid}", json={"owners": ["가팀원", "다팀원"]}).status_code == 200
    rows = _rows(owner, pid)
    assert rows["나팀원"]["to"] == TODAY and rows["나팀원"]["current"] is False  # 빠진 사람은 오늘까지
    assert rows["다팀원"]["from"] == TODAY and rows["다팀원"]["current"] is True  # 든 사람은 오늘부터
    assert rows["가팀원"]["from"] == "2026-03-02" and rows["가팀원"]["derived"] is False  # 원래 사람은 시작일부터 적힌다
    assert list(rows) == ["가팀원", "다팀원", "나팀원"]  # 지금 담당이 먼저
    # 다시 맡으면 끝 날짜가 지워진다
    owner.patch(f"/api/projects/{pid}", json={"owners": ["가팀원", "다팀원", "나팀원"]})
    rows = _rows(owner, pid)
    assert rows["나팀원"]["to"] is None and rows["나팀원"]["from"] == "2026-03-02"
    # 순서만 바꾸면 기간은 그대로
    before = md.load(_index_md(pid)).meta["contributions"]
    owner.patch(f"/api/projects/{pid}", json={"owners": ["나팀원", "가팀원", "다팀원"]})
    assert md.load(_index_md(pid)).meta["contributions"] == before


def test_not_started_project_drops_a_person_who_never_worked(team):
    owner = team["owner"]
    pid = owner.post("/api/projects", json={"title": "내년 과제", "owners": ["가팀원"], "start_date": "2027-01-04"}).json()["id"]
    owner.patch(f"/api/projects/{pid}", json={"owners": ["나팀원"]})
    rows = _rows(owner, pid)
    assert "가팀원" not in rows  # 시작 전에 빠졌고 적은 것도 없다 — 일한 적이 없다
    assert rows["나팀원"]["from"] == "2027-01-04"  # 시작 전에 든 사람은 시작일부터


def test_leader_writes_role_period_and_retro_with_rules(team):
    owner, pid = team["owner"], team["shared"]
    url = f"/api/projects/{pid}/contributions/가팀원"
    done = owner.put(url, json={"role": "주관", "part": "데이터 수집 · 분석 모델", "from": "2026-04-01",
                                "problem": "수작업 집계가 주 4시간", "did": "자동 집계 스크립트", "result": "주 30분"})
    assert done.status_code == 200, done.text
    row = {r["name"]: r for r in done.json()["contributions"]}["가팀원"]
    assert (row["role"], row["part"], row["from"], row["did"]) == ("주관", "데이터 수집 · 분석 모델", "2026-04-01", "자동 집계 스크립트")
    saved = md.load(_index_md(pid)).meta["contributions"]
    assert saved[0]["name"] == "가팀원" and saved[0]["result"] == "주 30분"
    assert "to" not in saved[0]  # 빈 칸은 적지 않는다
    # 보낸 칸만 바뀐다
    owner.put(url, json={"part": "분석 모델"})
    assert _rows(owner, pid)["가팀원"]["did"] == "자동 집계 스크립트"
    # 규칙
    assert owner.put(url, json={"role": "팀장"}).status_code == 400
    assert owner.put(url, json={"part": "두\n줄"}).status_code == 400
    assert owner.put(url, json={"to": "2026-03-01"}).status_code == 400  # 시작보다 빠른 끝
    assert owner.put(url, json={"from": "2026-13-01"}).status_code == 400
    assert owner.put(url, json={"did": "가" * 1001}).status_code == 400
    assert owner.put(f"/api/projects/{pid}/contributions/없는사람", json={"role": "참여"}).status_code == 404
    # 고친 뒤 다시 읽어도(파일이 원본) 그대로
    owner.post("/api/reindex")
    assert _rows(owner, pid)["가팀원"]["part"] == "분석 모델"


def test_member_writes_only_own_row_and_not_the_period(team):
    member, owner, viewer, pid = team["member"], team["owner"], team["viewer"], team["shared"]
    mine = member.put(f"/api/projects/{pid}/contributions/가팀원", json={"role": "참여", "did": "현장 데이터 수집"})
    assert mine.status_code == 200, mine.text
    other = member.put(f"/api/projects/{pid}/contributions/나팀원", json={"did": "남의 회고"})
    assert other.status_code == 403 and "자기 줄만" in other.json()["detail"]
    period = member.put(f"/api/projects/{pid}/contributions/가팀원", json={"from": "2026-05-01"})
    assert period.status_code == 403 and "팀장" in period.json()["detail"]
    # 지금 값 그대로 보내는 것은 된다(화면이 양식 전체를 보낼 때)
    same = member.put(f"/api/projects/{pid}/contributions/가팀원", json={"from": "2026-03-02", "result": "수집 2주 단축"})
    assert same.status_code == 200, same.text
    assert viewer.put(f"/api/projects/{pid}/contributions/가팀원", json={"did": "읽기"}).status_code == 403
    # 남의 과제는 담당이 아니라서
    theirs = owner.post("/api/projects", json={"title": "나팀원만", "owners": ["나팀원"]}).json()["id"]
    assert member.put(f"/api/projects/{theirs}/contributions/나팀원", json={"did": "x"}).status_code == 403
    # 금액 아닌 성과는 과제 칸 — 팀원은 못 고친다(효과 금액과 같다)
    assert member.patch(f"/api/projects/{pid}", json={"outcome": "30% 단축"}).status_code == 403
    # 팀장 홈의 "팀원이 고친 것" 에 남는다
    recent = owner.get("/api/edits/recent").json()["items"]
    assert any(item["name"] == "가팀원" and item["action"] == "역할 · 회고 수정" for item in recent)


def test_retro_due_lists_my_done_projects_with_empty_retro(team):
    owner, member, viewer, pid = team["owner"], team["member"], team["viewer"], team["shared"]
    assert member.get("/api/projects/retro-due").json()["items"] == []  # 아직 진행중
    owner.patch(f"/api/projects/{pid}", json={"status": "done"})
    due = member.get("/api/projects/retro-due").json()
    assert due["name"] == "가팀원" and [item["id"] for item in due["items"]] == [pid]
    assert owner.get("/api/projects/retro-due").json()["items"] == []  # 팀장은 담당이 아니다
    assert viewer.get("/api/projects/retro-due").json() == {"name": "", "items": []}
    member.put(f"/api/projects/{pid}/contributions/가팀원", json={"result": "끝"})
    assert member.get("/api/projects/retro-due").json()["items"] == []
    # 팀장 자신의 과제
    led = owner.post("/api/projects", json={"title": "팀장 과제", "owners": ["팀장"], "status": "done",
                                            "start_date": "2026-01-05", "completed_at": "2026-09-30"}).json()["id"]
    assert [item["id"] for item in owner.get("/api/projects/retro-due").json()["items"]] == [led]
    # 끝난 지 1년 넘은 것은 묻지 않는다
    old = owner.post("/api/projects", json={"title": "오래된 과제", "owners": ["팀장"], "status": "done",
                                            "start_date": "2025-01-06", "completed_at": "2025-06-30"}).json()["id"]
    assert old not in [item["id"] for item in owner.get("/api/projects/retro-due").json()["items"]]


def test_outcome_one_line(team):
    owner = team["owner"]
    pid = owner.post("/api/projects", json={"title": "성과 과제", "outcome": "  작업 시간 40% 단축  "}).json()["id"]
    assert owner.get(f"/api/projects/{pid}").json()["outcome"] == "작업 시간 40% 단축"
    assert owner.patch(f"/api/projects/{pid}", json={"outcome": "두\n줄"}).status_code == 400
    assert owner.patch(f"/api/projects/{pid}", json={"outcome": "가" * 201}).status_code == 400
    assert owner.patch(f"/api/projects/{pid}", json={"outcome": ""}).json()["outcome"] is None
    blank = owner.post("/api/projects", json={"title": "없음"}).json()["id"]
    assert owner.get(f"/api/projects/{blank}").json()["outcome"] is None
    assert "outcome" not in md.load(_index_md(blank)).meta  # 비면 파일에 적지 않는다
    listed = owner.get("/api/projects").json()
    assert "outcome" in (listed["items"] if isinstance(listed, dict) else listed)[0]


def test_handover_records_period_and_rename_only_renames(team):
    owner, pid = team["owner"], team["shared"]
    owner.put(f"/api/projects/{pid}/contributions/나팀원", json={"role": "참여", "did": "설비 조건 정리"})
    assert owner.post("/api/people/handover", json={"old": "나팀원", "new": "다팀원"}).status_code == 200
    rows = _rows(owner, pid)
    assert rows["나팀원"]["to"] == TODAY and rows["나팀원"]["did"] == "설비 조건 정리"  # 지난 일은 그 사람 것으로 남는다
    assert rows["다팀원"]["from"] == TODAY
    # 표기 통일 — 같은 사람이라 이름만
    assert owner.post("/api/people/rename", json={"old": "가팀원", "new": "가 팀원"}).status_code == 200
    rows = _rows(owner, pid)
    assert "가팀원" not in rows and rows["가 팀원"]["from"] == "2026-03-02" and rows["가 팀원"]["to"] is None


def test_export_carries_roles_retro_and_outcome(team):
    owner, pid = team["owner"], team["shared"]
    owner.patch(f"/api/projects/{pid}", json={"outcome": "불량 12건 → 3건"})
    owner.put(f"/api/projects/{pid}/contributions/가팀원", json={"role": "주관", "did": "원인 분석\n개선안 적용"})
    text = owner.get(f"/api/projects/{pid}/export?format=md").text
    assert "## 담당과 역할" in text and "불량 12건 → 3건" in text
    assert "**가팀원** · 주관 · 2026-03-02 ~ 지금" in text
    assert "  - 내가 한 일:\n    - 원인 분석\n    - 개선안 적용" in text  # 여러 줄은 아래로 목록 (TODO 241)
    # 적은 것이 없는 과제는 절째 빠진다
    plain = owner.post("/api/projects", json={"title": "빈 과제", "owners": ["나팀원"]}).json()["id"]
    assert "담당과 역할" not in owner.get(f"/api/projects/{plain}/export?format=md").text


def test_hand_written_contributions_are_read_leniently(team):
    owner, pid = team["owner"], team["shared"]
    path = _index_md(pid)
    doc = md.load(path)
    doc.meta["contributions"] = [{"name": "가팀원", "role": "주관", "from": "2026-03-10", "did": "손으로 적음"},
                                 {"role": "이름 없음"}, "글자 한 줄", {"name": "옛사람", "to": "2026-05-01", "role": "이상한값"}]
    md.save(path, doc)
    owner.post("/api/reindex")
    rows = _rows(owner, pid)
    assert rows["가팀원"]["did"] == "손으로 적음" and rows["가팀원"]["derived"] is False
    assert rows["옛사람"]["current"] is False and rows["옛사람"]["role"] == ""
    assert rows["나팀원"]["derived"] is True


def test_skills_per_person_row(team):
    """기술 · 도구 (TODO 239 ②) — 쉼표 규칙 · 30자 · 10개, 팀원은 자기 줄, 이력 · 내보내기에 함께."""
    owner, member, pid = team["owner"], team["member"], team["shared"]
    url = f"/api/projects/{pid}/contributions/가팀원"
    done = member.put(url, json={"skills": "Python, SQL,  python 회귀 , SQL"})
    assert done.status_code == 200, done.text
    row = {r["name"]: r for r in done.json()["contributions"]}["가팀원"]
    assert row["skills"] == ["Python", "SQL", "python 회귀"]  # 겹친 것 · 빈 것은 버린다
    assert md.load(_index_md(pid)).meta["contributions"][0]["skills"] == ["Python", "SQL", "python 회귀"]
    assert owner.put(url, json={"skills": ["가" * 31]}).status_code == 400
    assert owner.put(url, json={"skills": [f"기술{i}" for i in range(11)]}).status_code == 400
    assert member.put(f"/api/projects/{pid}/contributions/나팀원", json={"skills": ["Excel"]}).status_code == 403
    owner.put(f"/api/projects/{pid}/contributions/나팀원", json={"skills": ["SQL", "Excel"]})
    assert owner.get(f"/api/projects/{pid}").json()["known_skills"][:1] == ["SQL"]  # 많이 쓴 것부터
    history = owner.get("/api/person-history", params={"name": "가팀원"}).json()
    assert history["projects"][0]["skills"] == ["Python", "SQL", "python 회귀"]
    assert {"name": "SQL", "count": 1} in history["skills"]
    text = owner.get(f"/api/projects/{pid}/export?format=md").text
    assert "보유 기술(도구): Python, SQL, python 회귀" in text
    # 비우기
    assert owner.put(url, json={"skills": []}).json()["contributions"][0]["skills"] == []
    assert "skills" not in md.load(_index_md(pid)).meta["contributions"][0]


def test_problem_field_is_gone(team):
    """'무엇이 문제였나' 는 없앴다 (TODO 239 ⑤) — 받지도 보이지도 않고, 손으로 적어 둔 값은 다음 저장에서 빠진다."""
    owner, member, pid = team["owner"], team["member"], team["shared"]
    path = _index_md(pid)
    doc = md.load(path)
    doc.meta["contributions"] = [{"name": "가팀원", "problem": "손으로 적은 배경"}]
    md.save(path, doc)
    owner.post("/api/reindex")
    assert "problem" not in _rows(owner, pid)["가팀원"]
    owner.patch(f"/api/projects/{pid}", json={"status": "done"})
    assert [item["id"] for item in member.get("/api/projects/retro-due").json()["items"]] == [pid]  # 회고는 비었다
    owner.put(f"/api/projects/{pid}/contributions/가팀원", json={"problem": "새 배경", "did": "한 일"})
    saved = md.load(path).meta["contributions"][0]
    assert "problem" not in saved and saved["did"] == "한 일"
    text = owner.get(f"/api/projects/{pid}/export?format=md").text
    assert "손으로 적은 배경" not in text and "새 배경" not in text
