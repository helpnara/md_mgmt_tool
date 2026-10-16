"""입력 정합성 — 사람 · 설정 · 접수 · 오류 기록 (TODO 214 · 215 · 216, 2026-10-16).

* 216 — 입력 확인으로 돌려보낸 것(400 · 422)은 "최근 오류" 가 아니라 따로 센다. 고장(423 · 백업 실패)은 그대로 오류.
* 215 — 임시 보관 지우기가 겹치거나 윈도우가 잠깐 거부해도 204, 남은 파일은 숨겼다가 다음 차례에 지운다.
* 214 — 명부 자동 추가 없앰(D6) · 미래의 떠난 날(D8) · 이름 통일 범위(D9 · F6) · 같은 사번(D10) · 팀 코드(D16 · F3) ·
  효과 확인 기준(D4) · 사전점검(D17 · F2) · 착수 메모 · 같은 이름 과제(D11) · 되돌리기(F1) · 설정 숫자 칸(F12 · F14) ·
  역량 미래 날짜 · 시간 상한(D5 · F14) · 면담 구분(F15).
"""
from __future__ import annotations

import json
import pathlib
import shutil
from datetime import date, timedelta

import pytest

TODAY = date.today()
YESTERDAY = (TODAY - timedelta(days=1)).isoformat()
TOMORROW = (TODAY + timedelta(days=1)).isoformat()
NEXT_MONTH = (TODAY + timedelta(days=30)).isoformat()
LAST_MONTH = (TODAY - timedelta(days=30)).isoformat()


def _errors(client) -> dict:
    return client.get("/api/errors").json()


# ── 216 · 입력 거절은 "최근 오류" 가 아니다 ──────────────────────────────────────────


def test_input_rejections_are_counted_but_not_listed_as_errors(client):
    # 400 (서비스의 입력 규칙) · 422 (모양이 틀린 값) · 면담 다음 날짜가 같은 날
    assert client.put("/api/settings", json={"project_code": "12"}).status_code == 400
    assert client.post("/api/projects", json={"title": "x", "effect_expected": "abc"}).status_code == 422
    same_day = client.post("/api/meetings", json={"person": "가", "date": YESTERDAY, "summary": "s",
                                                  "next_date": YESTERDAY})
    assert same_day.status_code == 400 and same_day.json()["detail"] == "다음 면담은 이 면담 뒤여야 합니다."

    data = _errors(client)
    assert data["items"] == []
    assert data["input_count"] == 3 and data["input_today"] == 3
    assert [item["action"] for item in data["inputs"]] == [
        "POST /api/meetings", "POST /api/projects", "PUT /api/settings"]
    assert set(data["inputs"][0]) == {"at", "action", "detail"}
    assert "다음 면담" in data["inputs"][0]["detail"]
    assert data["keep_months"] and data["input_keep"] == 50


def test_real_failures_are_still_errors(client, monkeypatch):
    # 백업 실패(BackupError → 400) 는 입력이 아니다
    assert client.post("/api/settings/backup/run").status_code == 400
    # 파일 잠김(423)
    made = client.post("/api/projects", json={"title": "잠긴 파일"}).json()
    from app.vault import markdown as md

    def refuse(src, dst):
        raise PermissionError(13, "[WinError 32] The process cannot access the file")

    monkeypatch.setattr(md.os, "replace", refuse)
    assert client.patch(f"/api/projects/{made['id']}", json={"status": "done"}).status_code == 423
    monkeypatch.undo()

    data = _errors(client)
    assert [item["status"] for item in data["items"]] == [423, 400]
    assert data["input_count"] == 0 and data["inputs"] == []


def test_the_input_ring_keeps_only_the_latest(client):
    from app.services import errorlog

    for _ in range(errorlog.INPUT_KEEP + 5):
        client.put("/api/settings", json={"project_code": "1"})
    data = _errors(client)
    assert data["input_count"] == errorlog.INPUT_KEEP
    assert len(data["inputs"]) == errorlog.INPUT_RECENT
    # 비우기는 둘 다
    client.delete("/api/errors")
    assert _errors(client)["input_count"] == 0


# ── 215 · 임시 보관 지우기 ─────────────────────────────────────────────────────────


def _draft(client, key="overview:2026-001", text="글"):
    assert client.put(f"/api/drafts/{key}", json={"content": text}).status_code == 200
    return key


def test_deleting_a_draft_twice_is_fine(client):
    key = _draft(client)
    assert client.delete(f"/api/drafts/{key}").status_code == 204
    assert client.delete(f"/api/drafts/{key}").status_code == 204
    assert client.get("/api/drafts").json()["items"] == []
    assert _errors(client)["items"] == []


def _flaky_unlink(monkeypatch, name: str, failures: int | None):
    """그 파일 지우기를 `failures` 번 PermissionError 로 거부한다(None 이면 계속) — 윈도우의 WinError 5 흉내."""
    original = pathlib.Path.unlink
    calls = {"n": 0}

    def unlink(self, *args, **kwargs):
        if self.name == name:
            calls["n"] += 1
            if failures is None or calls["n"] <= failures:
                raise PermissionError(13, "[WinError 5] 액세스가 거부되었습니다")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "unlink", unlink)
    return calls


def test_a_draft_delete_retries_a_transient_refusal(client, vault_dir, monkeypatch):
    key = _draft(client)
    calls = _flaky_unlink(monkeypatch, "overview__2026-001.json", failures=2)
    assert client.delete(f"/api/drafts/{key}").status_code == 204
    assert calls["n"] == 3
    assert not (vault_dir / ".drafts" / "overview__2026-001.json").exists()
    assert _errors(client)["items"] == []


def test_a_draft_that_cannot_be_deleted_is_hidden_then_cleaned(client, vault_dir, monkeypatch):
    from app.services import drafts

    key = _draft(client)
    path = vault_dir / ".drafts" / "overview__2026-001.json"
    _flaky_unlink(monkeypatch, path.name, failures=None)
    assert client.delete(f"/api/drafts/{key}").status_code == 204  # 끝내 안 돼도 오류가 아니다
    assert path.exists() and key in drafts.pending_keys()
    # 지운 것으로 본다 — 열기 · 목록에서 안 보인다
    assert client.get(f"/api/drafts/{key}").json()["content"] is None
    assert client.get("/api/drafts").json()["items"] == []
    assert _errors(client)["items"] == []

    monkeypatch.undo()  # 잡고 있던 프로그램이 놓았다
    assert client.get("/api/drafts").json()["items"] == []  # 목록을 읽을 때 다시 지운다
    assert not path.exists() and drafts.pending_keys() == set()


def test_a_new_draft_clears_the_pending_mark(client, vault_dir, monkeypatch):
    from app.services import drafts

    key = _draft(client, text="첫 글")
    _flaky_unlink(monkeypatch, "overview__2026-001.json", failures=None)
    client.delete(f"/api/drafts/{key}")
    monkeypatch.undo()
    _draft(client, text="새 글")
    assert drafts.pending_keys() == set()
    assert client.get(f"/api/drafts/{key}").json()["content"] == "새 글"


def test_retry_os_gives_up_with_the_last_permission_error(monkeypatch):
    from app.vault import paths

    calls = {"n": 0}

    def always():
        calls["n"] += 1
        raise PermissionError("busy")

    with pytest.raises(PermissionError):
        paths.retry_os(always, delays=(0, 0))
    assert calls["n"] == 3


def _attachment(client):
    project = client.post("/api/projects", json={"title": "첨부 과제"}).json()
    uploaded = client.post(f"/api/projects/{project['id']}/attachments",
                           files={"file": ("표.txt", b"x", "text/plain")}).json()
    return project, uploaded


def test_attachment_delete_retries_a_transient_refusal_but_a_lasting_lock_is_still_423(client, monkeypatch):
    project, first = _attachment(client)
    original = shutil.move
    calls = {"n": 0}

    def flaky(src, dst, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise PermissionError(13, "[WinError 32]")
        return original(src, dst, *args, **kwargs)

    monkeypatch.setattr(shutil, "move", flaky)
    assert client.delete(f"/api/attachments/{first['id']}").status_code == 204
    assert calls["n"] == 3

    second = client.post(f"/api/projects/{project['id']}/attachments",
                         files={"file": ("둘.txt", b"y", "text/plain")}).json()

    def locked(src, dst, *args, **kwargs):
        raise PermissionError(13, "[WinError 32]")

    monkeypatch.setattr(shutil, "move", locked)
    response = client.delete(f"/api/attachments/{second['id']}")
    assert response.status_code in (409, 423)  # 잠김 안내는 그대로 (TODO 200)
    assert "다른 프로그램" in response.json()["detail"]


# ── 214 D6 · 면담 · 역량은 명부에 저절로 넣지 않는다 ───────────────────────────────


def test_meetings_and_activities_do_not_add_unknown_names(client):
    client.put("/api/people", json={"people": [{"name": "권경락"}]})
    meeting = client.post("/api/meetings", json={"person": "권경랑", "date": YESTERDAY, "summary": "s"})
    assert meeting.status_code == 201
    assert meeting.json()["warnings"] == ["명부에 없는 이름입니다: 권경랑"]
    activity = client.post("/api/activities", json={"person": "권경락, 김현우", "title": "교육", "date": YESTERDAY})
    assert activity.json()["warnings"] == ["명부에 없는 이름입니다: 김현우"]
    assert client.get("/api/meta").json()["people"] == ["권경락"]
    # 이름은 그대로 받는다 — 사람별 표에도 선다
    names = {p["name"] for p in client.get("/api/activities/summary").json()["people"]}
    assert {"권경락", "권경랑", "김현우"} <= names
    # 화면이 물어본 뒤 넣는 길
    assert client.post("/api/people", json={"name": "김현우"}).status_code == 201
    known = client.post("/api/meetings", json={"person": "김현우", "date": YESTERDAY, "summary": "s"})
    assert known.json()["warnings"] == []


def test_meeting_future_date_is_allowed_with_a_warning_and_kinds_come_from_the_list(client):
    client.post("/api/people", json={"name": "가"})
    future = client.post("/api/meetings", json={"person": "가", "date": TOMORROW, "summary": "s"})
    assert future.status_code == 201 and any("오늘보다 뒤" in w for w in future.json()["warnings"])

    refused = client.post("/api/meetings", json={"person": "가", "date": YESTERDAY, "summary": "s", "kind": "없는구분"})
    assert refused.status_code == 400 and "면담 구분" in refused.json()["detail"]
    ok = client.post("/api/meetings", json={"person": "가", "date": YESTERDAY, "summary": "s", "kind": "고충"})
    assert ok.status_code == 201
    # 목록에서 그 구분을 빼도 이미 적힌 면담은 다른 칸을 고칠 수 있다
    client.put("/api/settings", json={"meeting_kinds": "정기"})
    assert client.patch(f"/api/meetings/{ok.json()['id']}", json={"summary": "고침"}).status_code == 200
    assert client.patch(f"/api/meetings/{ok.json()['id']}", json={"kind": "수시"}).status_code == 400


# ── 214 D5 · F14 · 역량 기록 ─────────────────────────────────────────────────────────


def test_activity_dates_in_the_future_are_refused(client):
    for payload in ({"date": TOMORROW}, {"date": YESTERDAY, "end_date": TOMORROW}):
        response = client.post("/api/activities", json={"person": "가", "title": "교육", **payload})
        assert response.status_code == 400
        assert response.json()["detail"].startswith("역량 기록은 지나간 일만 적습니다 — 날짜가 오늘보다 뒤입니다")
    assert client.post("/api/activities", json={"person": "가", "title": "교육", "date": TODAY.isoformat()}).status_code == 201


def test_activity_hours_and_cost_have_bounds(client):
    def post(**extra):
        return client.post("/api/activities", json={"person": "가", "title": "교육", "date": LAST_MONTH, **extra})

    assert post(hours=25).status_code == 400
    assert "24시간" in post(hours=25).json()["detail"]
    two_days = (date.fromisoformat(LAST_MONTH) + timedelta(days=1)).isoformat()
    assert post(hours=48, end_date=two_days).status_code == 201
    assert post(hours=49, end_date=two_days).status_code == 400
    assert post(cost=1e13).status_code == 400
    assert post(cost=1e300).status_code == 400
    assert post(cost=2_000_000).status_code == 201


# ── 214 D8 · 미래의 떠난 날 ──────────────────────────────────────────────────────────


def test_a_future_left_on_is_still_here_until_that_day(client):
    client.put("/api/people", json={"people": [
        {"name": "전배예정", "left_on": NEXT_MONTH, "left_reason": "전배"},
        {"name": "떠난이", "left_on": LAST_MONTH, "left_reason": "퇴사"},
    ]})
    meta = client.get("/api/meta").json()
    assert [p["name"] for p in meta["people_left"]] == ["떠난이"]
    summary = {p["name"]: p for p in client.get("/api/activities/summary").json()["people"]}
    assert summary["전배예정"]["left"] is False and summary["떠난이"]["left"] is True

    intake = client.post("/api/intakes", json={"title": "요청", "leader": "전배예정"}).json()
    plan = client.get(f"/api/intakes/{intake['id']}/promote").json()
    assert plan["leader_in_roster"] is True and plan["owners"] == ["전배예정"]
    gone = client.post("/api/intakes", json={"title": "요청2", "leader": "떠난이"}).json()
    assert client.get(f"/api/intakes/{gone['id']}/promote").json()["leader_in_roster"] is False


# ── 214 D9 · F6 · [다른 이름으로 통일] · [넘기기] ─────────────────────────────────────


def test_rename_reaches_partners_activities_meetings_and_intake_leaders(client, vault_dir):
    client.put("/api/people", json={"people": [{"name": "김철수", "employee_id": "7"}]})
    owned = client.post("/api/projects", json={"title": "담당 과제", "owners": ["김철수"]}).json()
    partnered = client.post("/api/projects", json={"title": "협업 과제",
                                                   "partners": [{"team": "설비팀", "people": ["김철수", "박민수"]}]}).json()
    client.post("/api/activities", json={"person": "김철수", "title": "교육A", "date": LAST_MONTH})
    client.post("/api/meetings", json={"person": "김철수", "summary": "m", "date": LAST_MONTH})
    # 새 이름의 폴더가 이미 있다 — 합친다
    client.post("/api/activities", json={"person": "김철순", "title": "교육B", "date": LAST_MONTH})
    intake = client.post("/api/intakes", json={"title": "요청", "leader": "김철수"}).json()

    result = client.post("/api/people/rename", json={"old": "김철수", "new": "김철순"})
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["counts"] == {"owners": 1, "partners": 1, "activities": 1, "meetings": 1, "intakes": 1}
    assert sorted(body["changed"]) == sorted([owned["id"], partnered["id"]]) and body["count"] == 2

    assert client.get(f"/api/projects/{owned['id']}").json()["owners"] == ["김철순"]
    assert client.get(f"/api/projects/{partnered['id']}").json()["partners"][0]["people"] == ["김철순", "박민수"]
    assert {a["person"] for a in client.get("/api/activities").json()} == {"김철순"}
    assert {m["person"] for m in client.get("/api/meetings").json()["items"]} == {"김철순"}
    assert client.get(f"/api/intakes/{intake['id']}").json()["leader"] == "김철순"
    # 파일도 새 이름의 폴더로 — 옛 폴더는 비어서 사라진다
    people = vault_dir / "people"
    assert not (people / "김철수").exists()
    assert len(list((people / "김철순" / "activities").glob("*.md"))) == 2
    assert len(list((people / "김철순" / "meetings").glob("*.md"))) == 1
    assert "person: 김철순" in next((people / "김철순" / "meetings").glob("*.md")).read_text(encoding="utf-8")
    # 명부는 이름만 바뀌고 사번은 따라간다
    assert [(p["name"], p["employee_id"]) for p in client.get("/api/people").json()["people"]] == [("김철순", "7")]
    # 다시 읽어도 같다
    client.post("/api/reindex")
    assert {a["person"] for a in client.get("/api/activities").json()} == {"김철순"}


@pytest.mark.parametrize("new", ["가, 나", "../x", "a/b", "가\n나", "가" * 41, "  "])
def test_rename_and_handover_check_the_new_name(client, new):
    client.post("/api/projects", json={"title": "과제", "owners": ["김철수"]})
    assert client.post("/api/people/rename", json={"old": "김철수", "new": new}).status_code == 400
    assert client.post("/api/people/handover", json={"old": "김철수", "new": new}).status_code == 400
    assert client.get("/api/projects").json()[0]["owners"] == ["김철수"]


def test_rename_can_fix_an_old_bad_name(client, vault_dir):
    """예전 버그로 굳은 `"가, 나"` 같은 이름은 옛 이름으로는 받아 고칠 수 있어야 한다."""
    made = client.post("/api/projects", json={"title": "과제"}).json()
    index_md = next((vault_dir / "projects").glob(f"{made['id']}-*")) / "index.md"
    index_md.write_text(index_md.read_text(encoding="utf-8").replace("owners: []", "owners:\n- 가; 나"), encoding="utf-8")
    client.post("/api/reindex")
    assert client.post("/api/people/rename", json={"old": "가; 나", "new": "가나"}).status_code == 200
    assert client.get(f"/api/projects/{made['id']}").json()["owners"] == ["가나"]


def test_handover_moves_partners_and_open_intakes_but_not_history(client):
    project = client.post("/api/projects", json={"title": "협업", "partners": [{"team": "T", "people": ["홍길동"]}]}).json()
    client.post("/api/activities", json={"person": "홍길동", "title": "교육", "date": LAST_MONTH})
    intake = client.post("/api/intakes", json={"title": "요청", "leader": "홍길동"}).json()
    result = client.post("/api/people/handover", json={"old": "홍길동", "new": "김현우"}).json()
    assert result["counts"]["partners"] == 1 and result["counts"]["intakes"] == 1
    assert result["counts"]["activities"] == 0
    assert client.get(f"/api/projects/{project['id']}").json()["partners"][0]["people"] == ["김현우"]
    assert client.get(f"/api/intakes/{intake['id']}").json()["leader"] == "김현우"
    assert {a["person"] for a in client.get("/api/activities").json()} == {"홍길동"}  # 지난 이력은 그 사람의 것


# ── 214 D10 · F6 · 명부 ──────────────────────────────────────────────────────────────


def test_duplicate_employee_ids_are_refused(client):
    response = client.put("/api/people", json={"people": [
        {"name": "김철수", "employee_id": "100"}, {"name": "박민수", "employee_id": "100"}, {"name": "이영희"},
        {"name": "최수지"}]})
    assert response.status_code == 400
    assert "김철수" in response.json()["detail"] and "박민수" in response.json()["detail"]
    # 빈 사번은 여럿이어도 된다
    assert client.put("/api/people", json={"people": [{"name": "가"}, {"name": "나"}]}).status_code == 200


@pytest.mark.parametrize("name", ["이, 영희", "../x", "a/b", "a\nb", "가" * 41])
def test_roster_names_follow_the_plain_name_rule(client, name):
    assert client.put("/api/people", json={"people": [{"name": name}]}).status_code == 400
    assert client.post("/api/people", json={"name": name}).status_code == 400


def test_an_unknown_left_reason_is_refused_not_cleared(client):
    response = client.put("/api/people", json={"people": [{"name": "떠난이", "left_on": LAST_MONTH, "left_reason": "이상한사유"}]})
    assert response.status_code == 400 and "떠난 사유" in response.json()["detail"]


def test_an_old_odd_name_in_the_roster_does_not_block_saving(client, vault_dir):
    settings = vault_dir / "settings.json"
    settings.write_text(json.dumps({"people": [{"name": "가, 나"}]}, ensure_ascii=False), encoding="utf-8")
    assert client.put("/api/people", json={"people": [{"name": "가, 나"}, {"name": "다"}]}).status_code == 200


# ── 214 D16 · F3 · 팀 코드 ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("code", ["팀-2", "R&D", "팀#1", "a/b", "소재.개발", "Team_1", "12"])
def test_team_code_is_letters_and_digits_only(client, code):
    assert client.put("/api/settings", json={"project_code": code}).status_code == 400
    assert client.post("/api/settings/project-code/renumber/preview", json={"code": code}).status_code == 400


def test_a_bad_team_code_in_the_settings_file_is_read_as_empty(client, vault_dir):
    (vault_dir / "settings.json").write_text(json.dumps({"project_code": "a/b"}), encoding="utf-8")
    assert client.get("/api/meta").json()["project_code"] == ""
    assert "project_code" in client.get("/api/settings").json()["unreadable"]
    made = client.post("/api/projects", json={"title": "과제"}).json()
    assert "/" not in made["id"] and not (vault_dir / "projects" / "a").exists()


# ── 214 D4 · 효과 금액 확인 기준 ─────────────────────────────────────────────────────


def test_effect_confirm_over_in_meta_and_settings(client):
    assert client.get("/api/meta").json()["effect_confirm_over"] == 100
    assert client.put("/api/settings", json={"effect_confirm_over": 250}).status_code == 200
    assert client.get("/api/meta").json()["effect_confirm_over"] == 250
    assert client.put("/api/settings", json={"effect_confirm_over": 0}).status_code == 200
    assert client.get("/api/meta").json()["effect_confirm_over"] == 0
    bad = client.put("/api/settings", json={"effect_confirm_over": -1})
    assert bad.status_code == 400 and "효과 금액 확인 기준" in bad.json()["detail"]
    assert client.put("/api/settings", json={"effect_confirm_over": "abc"}).status_code == 422


# ── 214 F12 · F14 · 설정 숫자 칸 ─────────────────────────────────────────────────────


@pytest.mark.parametrize("key, value, label", [
    ("intake_stale_days", 0, "묵힘 기준일"),
    ("meeting_cycle_days", 0, "면담 주기"),
    ("backup_keep", 0, "일 단위로 남길 백업 수"),
    ("backup_every_hours", 1000, "백업 주기"),
    ("backup_keep_weekly", 1000, "주 단위로 남길 백업 수"),
    ("backup_keep_monthly", -1, "달 단위로 남길 백업 수"),
])
def test_numeric_settings_speak_korean(client, key, value, label):
    response = client.put("/api/settings", json={key: value})
    assert response.status_code == 400
    assert label in response.json()["detail"] and key not in response.json()["detail"]


# ── 214 D17 · F2 · 사전점검 ──────────────────────────────────────────────────────────


def _precheck_items():
    from app.services import precheck

    return precheck.DEFAULT_ITEMS


def test_precheck_note_without_a_level_is_refused(client):
    intake = client.post("/api/intakes", json={"title": "요청"}).json()
    first = _precheck_items()[0]
    response = client.put(f"/api/intakes/{intake['id']}/precheck", json={"items": [
        {"group": first["group"], "item": first["item"], "choice": None, "note": "근거만"}]})
    assert response.status_code == 400
    assert "단계를 고르지 않고 근거만 적었습니다" in response.json()["detail"]


def test_precheck_duplicate_items_are_refused(client):
    intake = client.post("/api/intakes", json={"title": "요청"}).json()
    first = _precheck_items()[0]
    answer = {"group": first["group"], "item": first["item"], "choice": first["choices"][0][0]}
    response = client.put(f"/api/intakes/{intake['id']}/precheck", json={"items": [answer] * 10})
    assert response.status_code == 400 and "두 번" in response.json()["detail"]
    assert client.get(f"/api/intakes/{intake['id']}").json()["precheck"]["score"] is None


# ── 214 D17 · D11 · 승격 ─────────────────────────────────────────────────────────────


def test_promote_keeps_a_decision_note_and_warns_about_a_same_title(client):
    existing = client.post("/api/projects", json={"title": "같은 이름"}).json()
    intake = client.post("/api/intakes", json={"title": "같은 이름"}).json()
    too_long = client.post(f"/api/intakes/{intake['id']}/promote", json={"decision_note": "가" * 201})
    assert too_long.status_code == 400
    assert len(client.get("/api/projects").json()) == 1  # 과제를 만들기 전에 멈췄다

    response = client.post(f"/api/intakes/{intake['id']}/promote",
                           json={"decision_note": "회의에서 착수 결정", "owners": ["모르는사람"]})
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["intake"]["decision_note"] == "회의에서 착수 결정"
    assert data["same_title"] == [{"id": existing["id"], "title": "같은 이름"}]
    assert any(existing["id"] in w for w in data["warnings"])
    assert "명부에 없는 이름입니다: 모르는사람" in data["warnings"]


def test_intake_team_name_that_differs_only_by_spaces_warns(client):
    client.post("/api/intakes", json={"title": "하나", "leader_team": "품질팀"})
    second = client.post("/api/intakes", json={"title": "둘", "leader_team": "품질 팀"}).json()
    assert second["warnings"] and "품질팀" in second["warnings"][0]
    assert client.post("/api/intakes", json={"title": "셋", "leader_team": "설비팀"}).json()["warnings"] == []


# ── 214 F1 · [접수로 되돌리기] 가 손으로 고친 값에 반쯤 실패하지 않는다 ───────────────


def test_demote_with_hand_edited_bad_values_creates_the_intake(client, vault_dir):
    made = client.post("/api/projects", json={"title": "손댄 과제", "type": "smart",
                                              "start_date": "2026-03-01", "due_date": "2026-06-30"}).json()
    index_md = next((vault_dir / "projects").glob(f"{made['id']}-*")) / "index.md"
    text = index_md.read_text(encoding="utf-8")
    text = text.replace("start_date: '2026-03-01'", "start_date: '2026-09-01'").replace(
        "start_date: 2026-03-01", "start_date: 2026-09-01")
    text = text.replace("effect_expected: null", "effect_expected: 99999999")
    if "effect_expected" not in text:
        text = text.replace("title: 손댄 과제", "title: 손댄 과제\neffect_expected: 99999999")
    index_md.write_text(text, encoding="utf-8")
    client.post("/api/reindex")

    response = client.post(f"/api/projects/{made['id']}/to-intake")
    assert response.status_code == 201, response.text
    intake = client.get(f"/api/intakes/{response.json()['intake_id']}").json()
    assert intake["start_date"] == "2026-09-01" and intake["due_date"] is None
    assert intake["effect_request"] is None
    assert any("되돌림" in item["title"] for item in intake["logs"])
    raw = "".join(path.read_text(encoding="utf-8") for path in (vault_dir / "intakes").rglob("logs/*.md"))
    assert "읽지 못해 비운 값" in raw and "마감일" in raw and "요청 효과" in raw
    # 과제는 보관함에 한 번만 — 다시 눌러도 둘이 되지 않는다
    assert client.get(f"/api/projects/{made['id']}").status_code == 404
    assert len(client.get("/api/intakes").json()["items"]) == 1


def test_explicit_author_follows_the_author_rule(client):
    """TODO 214 F13 — 서비스끼리 넘긴 작성자도 작성자 규칙(한 줄 · 40자)을 거친다."""
    from app.services import settings as settings_service

    with pytest.raises(ValueError):
        settings_service.current_author("x\ny")
    with pytest.raises(ValueError):
        settings_service.current_author("가" * 41)
    assert settings_service.current_author("  권경락 ") == "권경락"
