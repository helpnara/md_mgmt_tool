"""입력 검증을 한 곳으로 (TODO 205) · settings.json 쓰기 원자성과 잠금 (TODO 202) · 제목 변경이 보관함 기록을 따라가게 (TODO 203).

재현 스크립트(docs/review/전수점검-2026-10-15/ probe_check #4 #5 #6 · p2_projects · p3b_entry_title · p7_settings ·
p12_followup)의 모양을 백엔드 시험으로 옮겼다.
"""
from __future__ import annotations

import json
import math

import pytest

from app import deps


BAD_DATES = ["2026-13-01", "2026/01/01", "2026-02-30", "2026-1-1", "2026-01-01T00:00:00", "20260101", "2026-W01"]


def _project(client, title="검증 과제", **extra):
    response = client.post("/api/projects", json={"title": title, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def _project_dirs(vault_dir):
    root = vault_dir / "projects"
    return sorted(p.name for p in root.iterdir() if p.is_dir()) if root.exists() else []


def _is_korean(text: str) -> bool:
    return any("가" <= ch <= "힣" for ch in text)


# ── 날짜 (⑯) ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("field", ["start_date", "due_date", "completed_at"])
@pytest.mark.parametrize("bad", BAD_DATES)
def test_bad_date_on_create_is_400_and_writes_nothing(client, vault_dir, field, bad):
    response = client.post("/api/projects", json={"title": "날짜", field: bad})
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert "2026-03-01 처럼" in detail and bad in detail
    assert _project_dirs(vault_dir) == []


def test_bad_date_message_names_the_field(client):
    detail = client.post("/api/projects", json={"title": "x", "start_date": "2026/03/01"}).json()["detail"]
    assert detail == "시작일은 2026-03-01 처럼 적어 주세요 (받은 값: 2026/03/01)"
    detail = client.post("/api/projects", json={"title": "x", "due_date": "x"}).json()["detail"]
    assert detail.startswith("마감일은")


def test_bad_date_on_update_is_400_and_file_untouched(client, vault_dir):
    made = _project(client, start_date="2026-03-01")
    index_md = vault_dir / "projects" / f"{made['id']}-검증-과제" / "index.md"
    before = index_md.read_text(encoding="utf-8")
    for bad in BAD_DATES:
        response = client.patch(f"/api/projects/{made['id']}", json={"start_date": bad})
        assert response.status_code == 400, bad
    assert index_md.read_text(encoding="utf-8") == before
    # 재색인에도 경고가 없다 — 파일에 원문이 남지 않았다
    assert client.post("/api/reindex").json()["problems"] == []


def test_empty_string_clears_a_date(client):
    made = _project(client, start_date="2026-03-01", due_date="2026-04-01")
    updated = client.patch(f"/api/projects/{made['id']}", json={"start_date": "", "due_date": None}).json()
    assert updated["start_date"] is None and updated["due_date"] is None


def test_surrounding_spaces_are_trimmed(client):
    assert _project(client, start_date=" 2026-01-05 ")["start_date"] == "2026-01-05"


def test_entry_meeting_activity_intake_people_dates_are_strict(client):
    project = _project(client)
    entry = client.post(f"/api/projects/{project['id']}/entries", json={"date": "20260101", "title": "a"})
    assert entry.status_code == 400
    ok = client.post(f"/api/projects/{project['id']}/entries", json={"date": "2026-05-01", "title": "a"}).json()
    assert client.patch(f"/api/entries/{ok['id']}", json={"date": "2026-W01"}).status_code == 400

    meeting = {"person": "홍길동", "date": "2026-10-01", "summary": "s"}
    assert client.post("/api/meetings", json={**meeting, "date": "2026-1-1"}).status_code == 400
    assert client.post("/api/meetings", json={**meeting, "next_date": "2026/12/01"}).status_code == 400

    activity = {"person": "홍길동", "title": "교육", "date": "2026-10-01"}
    assert client.post("/api/activities", json={**activity, "end_date": "2026-02-30"}).status_code == 400

    for field in ("received_on", "start_date", "due_date"):
        assert client.post("/api/intakes", json={"title": "요청", field: "2026-13-01"}).status_code == 400

    assert client.put("/api/people", json={"people": [{"name": "홍길동", "left_on": "x"}]}).status_code == 400


def test_promote_rejects_bad_date_before_making_anything(client, vault_dir):
    intake = client.post("/api/intakes", json={"title": "승격"}).json()
    response = client.post(f"/api/intakes/{intake['id']}/promote", json={"start_date": "2026-13-01"})
    assert response.status_code == 400
    assert "시작일" in response.json()["detail"]
    assert _project_dirs(vault_dir) == []
    assert client.get(f"/api/intakes/{intake['id']}").json()["status"] == "received"


# ── 기간 (㉞) ───────────────────────────────────────────────────────────────


def test_period_inversion_is_400(client, vault_dir):
    response = client.post("/api/projects", json={"title": "기간", "start_date": "2026-03-01", "due_date": "2026-01-01"})
    assert response.status_code == 400
    assert "마감일이 시작일보다 빠릅니다" in response.json()["detail"]
    assert _project_dirs(vault_dir) == []

    made = _project(client, start_date="2026-03-01", due_date="2026-06-01")
    # 한쪽만 보내도 파일에 있던 쪽과 맞춰 본다
    assert client.patch(f"/api/projects/{made['id']}", json={"due_date": "2026-02-01"}).status_code == 400
    assert client.patch(f"/api/projects/{made['id']}", json={"start_date": "2026-07-01"}).status_code == 400
    assert client.patch(f"/api/projects/{made['id']}", json={"start_date": "2026-06-01"}).status_code == 200


def test_period_inversion_intake_meeting_activity(client):
    assert client.post("/api/intakes", json={"title": "r", "start_date": "2026-05-01", "due_date": "2026-04-01"}).status_code == 400
    intake = client.post("/api/intakes", json={"title": "r", "start_date": "2026-05-01"}).json()
    assert client.patch(f"/api/intakes/{intake['id']}", json={"due_date": "2026-04-01"}).status_code == 400

    meeting = {"person": "홍길동", "date": "2026-10-01", "summary": "s", "next_date": "2026-09-01"}
    assert client.post("/api/meetings", json=meeting).status_code == 400
    activity = {"person": "홍길동", "title": "교육", "date": "2026-10-05", "end_date": "2026-10-01"}
    assert client.post("/api/activities", json=activity).status_code == 400


# ── 제목 (⑰ ⑱) ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_blank_project_title_on_update_is_400_and_folder_stays(client, vault_dir, blank):
    made = _project(client, "이름 그대로")
    response = client.patch(f"/api/projects/{made['id']}", json={"title": blank})
    assert response.status_code == 400
    assert response.json()["detail"] == "과제명을 입력하세요."
    assert _project_dirs(vault_dir) == [f"{made['id']}-이름-그대로"]
    assert client.get(f"/api/projects/{made['id']}").json()["title"] == "이름 그대로"


def test_project_title_is_stripped(client, vault_dir):
    made = _project(client, "  앞뒤 공백  ")
    assert made["title"] == "앞뒤 공백"
    updated = client.patch(f"/api/projects/{made['id']}", json={"title": "  새 이름 "}).json()
    assert updated["title"] == "새 이름"
    assert _project_dirs(vault_dir) == [f"{made['id']}-새-이름"]


def test_blank_intake_title_is_400(client):
    assert client.post("/api/intakes", json={"title": "   "}).status_code == 400
    intake = client.post("/api/intakes", json={"title": "요청"}).json()
    response = client.patch(f"/api/intakes/{intake['id']}", json={"title": " "})
    assert response.status_code == 400 and response.json()["detail"] == "과제명을 입력하세요."


@pytest.mark.parametrize("blank", ["", "   "])
def test_entry_filename_no_longer_grows(client, vault_dir, blank):
    project = _project(client, "일지")
    entry = client.post(f"/api/projects/{project['id']}/entries",
                        json={"date": "2026-05-01", "title": "제목", "body": "x"}).json()
    updated = client.patch(f"/api/entries/{entry['id']}", json={"title": blank}).json()
    assert updated["title"] == "진행 기록"
    for i in range(3):
        client.patch(f"/api/entries/{entry['id']}", json={"body": f"수정 {i}"})
    logs = sorted(p.name for p in (vault_dir / "projects" / f"{project['id']}-일지" / "logs").iterdir())
    assert logs == ["2026-05-01-진행-기록.md"]
    assert client.get(f"/api/entries/{entry['id']}").json()["rel_path"] == "logs/2026-05-01-진행-기록.md"


def test_hand_written_entry_without_title_keeps_its_name(client, vault_dir):
    """제목 칸이 없는 손 파일 — 색인은 파일명을 제목으로 쓴다. 본문을 고쳐도 이름이 자라지 않는다."""
    project = _project(client, "손")
    logs = vault_dir / "projects" / f"{project['id']}-손" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "2026-05-01-손으로-쓴-기록.md").write_text("---\ndate: '2026-05-01'\n---\n본문\n", encoding="utf-8")
    client.post("/api/reindex")
    entry = client.get(f"/api/projects/{project['id']}/entries").json()[0]
    for i in range(2):
        assert client.patch(f"/api/entries/{entry['id']}", json={"body": f"고침 {i}"}).status_code == 200
    assert sorted(p.name for p in logs.iterdir()) == ["2026-05-01-손으로-쓴-기록.md"]
    # 날짜만 바꾸면 날짜 머리만 바뀐다
    client.patch(f"/api/entries/{entry['id']}", json={"date": "2026-05-02"})
    assert sorted(p.name for p in logs.iterdir()) == ["2026-05-02-손으로-쓴-기록.md"]


# ── 숫자 (㉞) ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "-Infinity", "1e999"])
def test_nan_and_infinity_effect_are_400(client, vault_dir, raw):
    body = '{"title": "효과", "effect_expected": %s}' % raw
    response = client.post("/api/projects", content=body, headers={"Content-Type": "application/json"})
    assert response.status_code in (400, 422), response.text
    assert _project_dirs(vault_dir) == []


def test_nan_effect_on_update_and_string_nan(client, vault_dir):
    made = _project(client)
    for value in ("nan", "inf"):
        assert client.patch(f"/api/projects/{made['id']}", json={"effect_verified": value}).status_code == 400
    assert client.post("/api/projects", json={"title": "x", "effect_expected": "nan"}).status_code == 400
    assert client.post("/api/projects", json={"title": "x", "effect_expected": 1e308}).status_code == 400
    assert ".nan" not in "".join(p.read_text(encoding="utf-8") for p in (vault_dir / "projects").rglob("index.md"))
    assert client.post("/api/intakes", json={"title": "r", "effect_request": "inf"}).status_code == 400
    assert client.post("/api/activities", json={"person": "a", "title": "t", "date": "2026-01-01", "hours": "nan"}).status_code == 400


def test_finite_number_helper():
    from app.schemas import finite_number

    assert finite_number("", "effect_expected") is None
    assert finite_number(1.5, "effect_expected") == 1.5
    for bad in (math.nan, math.inf, -1, True, "abc"):
        with pytest.raises(ValueError):
            finite_number(bad, "effect_expected")


# ── 목록 — 담당자와 태그는 같은 쉼표 규칙 (㉞) ─────────────────────────────


def test_owners_and_tags_split_commas_the_same_way(client):
    made = _project(client, tags=["a, b", "b", " c  d "], owners=["권경락, 홍길동", "권경락"])
    got = client.get(f"/api/projects/{made['id']}").json()
    assert sorted(got["tags"]) == ["a", "b", "c d"]
    assert got["owners"] == ["권경락", "홍길동"]
    updated = client.patch(f"/api/projects/{made['id']}", json={"tags": ["x,y", "", "x"]}).json()
    assert sorted(updated["tags"]) == ["x", "y"]

    entry = client.post(f"/api/projects/{made['id']}/entries", json={"title": "t", "tags": ["p, q"]}).json()
    assert sorted(entry["tags"]) == ["p", "q"]
    intake = client.post("/api/intakes", json={"title": "r", "tags": ["m, n"]}).json()
    assert intake["tags"] == ["m", "n"]


# ── 사람 이름 · 명부 (㉞) ─────────────────────────────────────────────────────


@pytest.mark.parametrize("person", ["../x", "a/b", "a\\b", ".."])
def test_meeting_and_activity_person_must_be_a_plain_name(client, vault_dir, person):
    meeting = client.post("/api/meetings", json={"person": person, "date": "2026-10-01", "summary": "s"})
    assert meeting.status_code == 400 and _is_korean(meeting.json()["detail"])
    activity = client.post("/api/activities", json={"person": person, "title": "t", "date": "2026-10-01"})
    assert activity.status_code == 400
    people = vault_dir / "people"
    assert not people.exists() or list(people.iterdir()) == []


def test_meeting_person_is_stripped(client):
    client.post("/api/meetings", json={"person": "  홍길동 ", "date": "2026-10-01", "summary": "s"})
    assert [item["person"] for item in client.get("/api/meetings").json()["items"]] == ["홍길동"]


def test_people_put_rejects_bad_left_on_and_duplicates(client):
    response = client.put("/api/people", json={"people": [{"name": "홍길동", "left_on": "2026-13-01", "left_reason": "퇴사"}]})
    assert response.status_code == 400
    assert response.json()["detail"].startswith("홍길동: 떠난 날은")
    response = client.put("/api/people", json={"people": [{"name": "홍길동"}, {"name": " 홍길동 "}]})
    assert response.status_code == 400 and "같은 이름" in response.json()["detail"]
    ok = client.put("/api/people", json={"people": [{"name": "홍길동", "left_on": "2026-01-01", "left_reason": "퇴사"}, {"name": ""}]})
    assert ok.status_code == 200 and [p["name"] for p in ok.json()["people"]] == ["홍길동"]


# ── 설정 (㉞) ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("value", [[1], [], [-1], [1, 2, 3], [50, 70], [100, 200], [-5, -10]])
def test_precheck_thresholds_are_two_ordered_numbers(client, value):
    response = client.put("/api/settings", json={"precheck_thresholds": value})
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert isinstance(detail, str) and _is_korean(detail) and "unpack" not in detail


def test_precheck_thresholds_ok(client):
    response = client.put("/api/settings", json={"precheck_thresholds": [80, 60]})
    assert response.status_code == 200 and response.json()["precheck_thresholds"] == [80, 60]


def test_report_weekday_range(client):
    assert client.put("/api/settings", json={"report_weekday": 7}).status_code == 400
    assert client.put("/api/settings", json={"report_weekday": -1}).status_code == 400
    assert client.put("/api/settings", json={"report_weekday": 6}).status_code == 200


@pytest.mark.parametrize("author", ["a\nb", "a\rb", "가" * 41])
def test_author_newline_and_length(client, author):
    response = client.put("/api/settings", json={"author": author})
    assert response.status_code == 400 and _is_korean(response.json()["detail"])


def test_author_is_stripped(client):
    assert client.put("/api/settings", json={"author": "  권경락 "}).json()["author"] == "권경락"


def test_project_types_may_be_emptied_as_decided_in_todo_100(client):
    # TODO 100 — 속성을 안 쓰는 팀도 있다. 빈 목록은 막지 않는다 (205 검토에서 다시 확인).
    assert client.put("/api/settings/project-types", json={"types": []}).status_code == 200
    assert client.get("/api/settings/project-types").json()["types"] == []


@pytest.mark.parametrize("key", ["a/b", "a\\b", "..", "a b", "../x"])
def test_project_type_keys_must_be_safe(client, key):
    response = client.put("/api/settings/project-types", json={"types": [{"key": key, "label": "이름"}]})
    assert response.status_code == 400 and _is_korean(response.json()["detail"])


def test_backup_skip_assets_default_and_type(client):
    assert client.get("/api/settings").json()["backup_skip_assets"] is False
    assert client.put("/api/settings", json={"backup_skip_assets": "yes"}).status_code == 422
    assert client.put("/api/settings", json={"backup_skip_assets": 1}).status_code == 422
    assert client.put("/api/settings", json={"backup_skip_assets": True}).json()["backup_skip_assets"] is True
    from app.services import settings as settings_service

    with pytest.raises(ValueError):
        settings_service.save({"backup_skip_assets": "true"})
    assert settings_service.load()["backup_skip_assets"] is True


def test_backup_skip_assets_bad_shape_in_file_falls_back(client, vault_dir):
    (vault_dir / "settings.json").write_text(json.dumps({"backup_skip_assets": "yes"}), encoding="utf-8")
    from app.services import settings as settings_service

    assert settings_service.load()["backup_skip_assets"] is False
    assert "backup_skip_assets" in settings_service.unreadable_keys()


# ── 같은 이름 과제 — 막지 않고 알린다 (㉞) ───────────────────────────────────


def test_same_title_project_warns_but_is_created(client):
    first = _project(client, "중복 과제")
    assert first["warnings"] == []
    second = client.post("/api/projects", json={"title": " 중복 과제 "})
    assert second.status_code == 201
    assert second.json()["warnings"] == [f"같은 이름의 과제가 이미 있습니다: {first['id']}"]
    assert second.json()["id"] != first["id"]


# ── 422 한글 문구 (㉞) ──────────────────────────────────────────────────────


def test_422_messages_are_korean_and_name_the_field(client):
    response = client.post("/api/projects", json={"title": "x", "effect_expected": "abc"})
    assert response.status_code == 422
    body = response.json()
    assert isinstance(body["detail"], list)  # 모양은 그대로 — loc · msg · type
    assert body["detail"][0]["msg"] == "기대효과: 숫자로 적어 주세요"
    assert body["message"] == "기대효과: 숫자로 적어 주세요"

    cases = [
        ({"title": "x", "owners": "홍길동"}, "담당자: 목록으로 보내야 합니다"),
        ({"owners": []}, "과제명: 꼭 필요한 칸입니다"),
        ({"title": 1}, "과제명: 글자로 적어 주세요"),
        ({"title": "x", "owners": [1]}, "담당자: 글자로 적어 주세요"),
    ]
    for payload, expected in cases:
        msgs = [item["msg"] for item in client.post("/api/projects", json=payload).json()["detail"]]
        assert expected in msgs, (payload, msgs)

    weekday = client.put("/api/settings", json={"report_weekday": "월"}).json()
    assert weekday["detail"][0]["msg"] == "보고 요일: 정수로 적어 주세요"
    raw = client.patch("/api/projects/2026-001", content="x", headers={"Content-Type": "application/json"}).json()
    assert all(_is_korean(item["msg"]) for item in raw["detail"])


def test_422_is_still_recorded_in_the_error_log(client):
    from app.services import errorlog

    client.post("/api/projects", json={"title": "x", "effect_expected": "abc"})
    assert any(item.get("status") == 422 for item in errorlog.recent())


# ── settings.json — 임시 파일 + replace, 쓰기 잠금 (TODO 202 ㉓) ─────────────


def test_settings_write_is_atomic(client, vault_dir, monkeypatch):
    from app.services import settings as settings_service

    client.put("/api/settings", json={"author": "처음"})
    path = vault_dir / "settings.json"
    before = path.read_text(encoding="utf-8")

    replaced: list[tuple[str, str]] = []
    real_replace = settings_service.os.replace

    def spy(src, dst):
        replaced.append((str(src), str(dst)))
        return real_replace(src, dst)

    monkeypatch.setattr(settings_service.os, "replace", spy)
    client.put("/api/settings", json={"author": "둘째"})
    assert replaced and replaced[-1][1] == str(path) and replaced[-1][0].endswith(".tmp")

    def boom(src, dst):
        raise OSError("디스크 가득")

    monkeypatch.setattr(settings_service.os, "replace", boom)
    with pytest.raises(OSError):
        settings_service.save({"author": "셋째"})
    # 실패해도 온전한 옛 파일이 남고, 임시 파일은 치운다
    assert json.loads(path.read_text(encoding="utf-8"))["author"] == "둘째"
    assert [p.name for p in vault_dir.iterdir() if p.name.endswith(".tmp")] == []
    assert before != path.read_text(encoding="utf-8")


@pytest.mark.parametrize("method,url,payload", [
    ("put", "/api/settings", {"author": "a"}),
    ("put", "/api/people", {"people": [{"name": "홍길동"}]}),
    ("post", "/api/people", {"name": "홍길동"}),
])
def test_settings_endpoints_take_the_write_lock(client, monkeypatch, method, url, payload):
    monkeypatch.setattr(deps, "WRITE_LOCK_TIMEOUT", 0.05)
    assert deps._write_lock.acquire(timeout=1)
    try:
        response = getattr(client, method)(url, json=payload)
    finally:
        deps._write_lock.release()
    assert response.status_code == 503
    assert getattr(client, method)(url, json=payload).status_code in (200, 201)


# ── 제목 변경이 보관함 기록을 따라간다 (TODO 203 — 부르는 쪽) ──────────────────


def test_project_title_change_rewrites_trash_origins(client, vault_dir):
    from app.services import trash as trash_service

    made = _project(client, "옛 이름")
    entry = client.post(f"/api/projects/{made['id']}/entries", json={"date": "2026-05-01", "title": "지울 것"}).json()
    assert client.delete(f"/api/entries/{entry['id']}").status_code == 204
    client.patch(f"/api/projects/{made['id']}", json={"title": "새 이름"})

    lines = [json.loads(line) for line in trash_service._manifest_path().read_text(encoding="utf-8").splitlines() if line.strip()]
    origins = [item["origin"] for item in lines if item.get("kind") == "entry"]
    assert origins and all(origin.startswith(f"projects/{made['id']}-새-이름/") for origin in origins), origins


def test_rename_calls_rewrite_origins_with_folder_names(client, monkeypatch):
    from app.services import trash as trash_service

    calls: list[dict] = []
    real = trash_service.rewrite_origins

    def spy(mapping):
        calls.append(dict(mapping))
        return real(mapping)

    monkeypatch.setattr(trash_service, "rewrite_origins", spy)
    made = _project(client, "과제 하나")
    client.patch(f"/api/projects/{made['id']}", json={"title": "과제 둘"})
    intake = client.post("/api/intakes", json={"title": "요청 하나"}).json()
    client.patch(f"/api/intakes/{intake['id']}", json={"title": "요청 둘"})
    assert {f"{made['id']}-과제-하나": f"{made['id']}-과제-둘"} in calls
    assert {f"{intake['id']}-요청-하나": f"{intake['id']}-요청-둘"} in calls
    # 제목이 그대로면(폴더가 안 움직이면) 부르지 않는다
    calls.clear()
    client.patch(f"/api/projects/{made['id']}", json={"status": "planned"})
    assert calls == []


def test_intake_log_draft_is_described_as_a_review_log(client):
    """TODO 211 ③ — 검토 기록의 임시 보관이 홈의 "작성 중이던 글" 에서 "찾을 수 없음" 으로 보이지 않는다."""
    made = client.post("/api/intakes", json={"title": "임시 보관 확인", "received_on": "2026-10-01"}).json()
    key = f"intake:{made['id']}--log-new"
    assert client.put(f"/api/drafts/{key}", json={"content": {"title": "면담", "body": "쓰던 글"}}).status_code in (200, 204)
    item = next(d for d in client.get("/api/drafts").json()["items"] if d["key"] == key)
    assert item["label"] == "검토 기록" and not item["missing"] and made["id"] in item["where"]
