"""입력값 정합성 (TODO 214) — 과제 · 날짜 · 집계 쪽.

검토 기록 `docs/검토-입력정합성-2026-10-16.md` 의 D1 · D2 · D3 · D5 · D11 · D12 · D14 · D15 · D18 과 F4 · F5 · F7 · F10 · F11 · F13 · F15.
재현한 대표 — "효과 관리 안 함" 과제의 금액이 팀 합계에 들어감 · 옛 완료일이 되살아남 · 9999년 진행일지 · 미래 보고 확정.
"""
from __future__ import annotations

import os
import re
from datetime import date, timedelta
from pathlib import Path

TODAY = date.today().isoformat()
TOMORROW = (date.today() + timedelta(days=1)).isoformat()


def make(client, title="과제", **extra):
    response = client.post("/api/projects", json={"title": title, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def index_of(vault_dir: Path, project_id: str) -> Path:
    return next(path for path in (vault_dir / "projects").glob(f"{project_id}-*/index.md"))


def edit_meta(path: Path, **values: str) -> None:
    text = path.read_text(encoding="utf-8")
    for key, value in values.items():
        if re.search(rf"^{key}:.*$", text, flags=re.M):
            text = re.sub(rf"^{key}:.*$", f"{key}: {value}", text, count=1, flags=re.M)
        else:
            text = text.replace("---\n", f"---\n{key}: {value}\n", 1)
    path.write_text(text, encoding="utf-8")


def problems(client) -> list[dict]:
    return client.post("/api/reindex").json()["problems"]


# ── D1 · F10 완료일 ─────────────────────────────────────────────────────────

def test_not_done_project_never_keeps_a_completed_date(client):
    project = make(client, status="in_progress", completed_at="2020-01-01")
    assert project["completed_at"] is None


def test_done_without_a_date_is_today_and_old_date_does_not_come_back(client, vault_dir):
    # 재현 2 — 진행중일 때 받아 둔 2020-01-01 이 완료로 바꾸면 되살아났다
    project = make(client, status="in_progress", completed_at="2020-01-01")
    done = client.patch(f"/api/projects/{project['id']}", json={"status": "done"}).json()
    assert done["completed_at"] == TODAY

    # 손으로 적어 둔 옛 완료일이 남은 진행중 파일도 같다
    other = make(client, "손 편집", status="in_progress")
    edit_meta(index_of(vault_dir, other["id"]), completed_at="'2020-01-01'")
    client.post("/api/reindex")
    done = client.patch(f"/api/projects/{other['id']}", json={"status": "done"}).json()
    assert done["completed_at"] == TODAY


def test_leaving_done_clears_the_date_even_if_it_is_sent(client):
    project = make(client, status="done")
    assert project["completed_at"] == TODAY
    back = client.patch(f"/api/projects/{project['id']}", json={"status": "in_progress", "completed_at": "2026-02-02"})
    assert back.status_code == 200 and back.json()["completed_at"] is None


def test_clearing_the_date_of_a_done_project_means_today(client):
    # F10 — 화면의 안내 "비워 두면 오늘"
    project = make(client, status="done", start_date="2026-01-01", completed_at="2026-03-01")
    cleared = client.patch(f"/api/projects/{project['id']}", json={"completed_at": None}).json()
    assert cleared["completed_at"] == TODAY


def test_completed_date_must_sit_between_start_and_today(client):
    early = client.post("/api/projects", json={
        "title": "앞섬", "status": "done", "start_date": "2026-05-01", "completed_at": "2026-01-01"})
    assert early.status_code == 400 and "시작일" in early.json()["detail"]
    future = client.post("/api/projects", json={"title": "미래", "status": "done", "completed_at": TOMORROW})
    assert future.status_code == 400 and "완료일이 오늘보다 뒤입니다" in future.json()["detail"]
    # 고칠 때도 — 시작일을 완료일 뒤로 옮기면 거절
    project = make(client, status="done", start_date="2026-01-01", completed_at="2026-02-01")
    moved = client.patch(f"/api/projects/{project['id']}", json={"start_date": "2026-03-01"})
    assert moved.status_code == 400


# ── D2 · D3 집계 ────────────────────────────────────────────────────────────

def test_no_effect_project_adds_nothing_to_the_totals(client):
    # 재현 1 — 그 과제 하나만 있는데 홈 기대효과 100 · 실증효과 50
    make(client, "비대상", status="done", no_effect=True, effect_expected=100, effect_verified=50, owners=["가"])
    home = client.get("/api/home").json()
    team = home["team"]
    assert (team["effect_expected"], team["effect_verified"]) == (0, 0)
    assert (team["effect_expected_projects"], team["effect_verified_projects"]) == (0, 0)
    assert home["members"][0]["effect_expected"] == 0
    assert all(item["effect_expected"] == 0 for item in home["types"] + home["groups"])
    # 누르면 나오는 수와 같다(5.8)
    assert client.get("/api/projects", params={"effect": "expected"}).json() == []
    assert client.get("/api/projects", params={"effect": "verified"}).json() == []
    # 파일 · 상세의 값은 그대로 남는다
    row = client.get("/api/projects").json()[0]
    assert (row["effect_expected"], row["effect_verified"]) == (100, 50)
    assert (row["effect_counted_expected"], row["effect_counted_verified"]) == (None, None)


def test_interim_verified_money_of_in_progress_projects_counts_and_is_shown_apart(client):
    """TODO 217 — 진행중 과제도 분기 · 반기 결산으로 실증효과를 적는다. 홈 합계에 들고, 그중 중간 결산이 얼마인지 따로 보인다."""
    year = date.today().strftime("%Y")
    make(client, "진행중", status="in_progress", start_date=f"{year}-01-01", due_date=f"{year}-12-31",
         effect_expected=10, effect_verified=7)
    make(client, "완료", status="done", start_date=f"{year}-01-01", completed_at=f"{year}-03-31",
         effect_expected=2, effect_verified=3)
    make(client, "비대상", status="in_progress", start_date=f"{year}-01-01", due_date=f"{year}-12-31",
         no_effect=True, effect_expected=50, effect_verified=50)
    for params in ({}, {"year": year}):
        team = client.get("/api/home", params=params).json()["team"]
        assert (team["effect_expected"], team["effect_verified"]) == (12, 10)
        assert team["effect_verified_projects"] == 2
        assert (team["effect_verified_interim"], team["effect_verified_interim_projects"]) == (7, 1)
        # 정합성 — 홈의 합계 = 목록 "세는 금액" 의 합 = 눌렀을 때 나오는 목록 (5.8)
        rows = client.get("/api/projects", params=params).json()
        assert sum(item["effect_counted_verified"] or 0 for item in rows) == team["effect_verified"]
        assert sum(item["effect_counted_expected"] or 0 for item in rows) == team["effect_expected"]
        listed = client.get("/api/projects", params={"effect": "verified", **params}).json()
        assert sorted(item["title"] for item in listed) == ["완료", "진행중"]


def test_completing_a_project_moves_interim_money_to_final_without_changing_the_total(client):
    """중간 결산 → 완료: 합계는 그대로, 중간 결산 몫만 0 으로 (같은 돈이 두 번 세어지지 않는다)."""
    year = date.today().strftime("%Y")
    project = make(client, "결산", status="in_progress", start_date=f"{year}-01-01", due_date=f"{year}-12-31",
                   effect_expected=10, effect_verified=4)
    before = client.get("/api/home", params={"year": year}).json()["team"]
    assert (before["effect_verified"], before["effect_verified_interim"]) == (4, 4)
    client.patch(f"/api/projects/{project['id']}", json={"effect_verified": 6})  # 반기 결산 — 누적값으로 고쳐 적음
    mid = client.get("/api/home", params={"year": year}).json()["team"]
    assert (mid["effect_verified"], mid["effect_verified_interim"]) == (6, 6)
    client.patch(f"/api/projects/{project['id']}", json={"status": "done"})
    after = client.get("/api/home", params={"year": year}).json()["team"]
    assert (after["effect_verified"], after["effect_verified_interim"], after["effect_verified_interim_projects"]) == (6, 0, 0)


def test_interim_money_of_a_multi_year_project_counts_in_the_year_it_ends(client):
    """효과는 끝나는 해에 한 번만 센다(TODO 181) — 내년에 끝나는 과제의 중간 결산은 내년 홈에. 두 해에 두 번 세지 않는다."""
    this = int(date.today().strftime("%Y"))
    make(client, "다년도", status="in_progress", start_date=f"{this}-01-01", due_date=f"{this + 1}-06-30",
         effect_expected=10, effect_verified=3)
    now = client.get("/api/home", params={"year": str(this)}).json()["team"]
    later = client.get("/api/home", params={"year": str(this + 1)}).json()["team"]
    assert now["effect_verified"] == 0 and later["effect_verified"] == 3
    assert later["effect_verified_interim"] == 3


def test_done_unverified_count_matches_its_list(client):
    make(client, "비대상 완료", status="done", no_effect=True)
    make(client, "대상 완료", status="done", effect_expected=1)
    count = client.get("/api/home").json()["team"]["done_unverified"]
    listed = client.get("/api/projects", params={"verified": "none"}).json()
    assert count == len(listed) == 1


def test_effect_warnings_on_save(client):
    project = client.post("/api/projects", json={"title": "실증만", "effect_verified": 5}).json()
    assert any("기대효과 없이" in text for text in project["warnings"])
    # 진행중 과제의 실증은 중간 결산으로 센다 — "완료한 과제만" 경고는 없어졌다 (TODO 217)
    assert not any("완료한 과제만" in text for text in project["warnings"])


def test_roadmap_lineage_sums_follow_the_same_rule(client):
    first = make(client, "1단계", status="done", start_date="2025-01-01", completed_at="2025-12-31",
                 effect_expected=5, effect_verified=4)
    make(client, "2단계", status="in_progress", start_date="2026-01-01", predecessors=[first["id"]],
         effect_expected=3, effect_verified=9, no_effect=False)
    make(client, "2단계 비대상", status="done", start_date="2026-01-01", predecessors=[first["id"]],
         effect_expected=100, effect_verified=100, no_effect=True)
    lineage = client.get("/api/roadmap").json()["lineages"][0]
    assert lineage["effect_expected"] == 8
    # 진행중 2단계의 중간 결산 9 도 센다 — 비대상 100 은 뺀다 (TODO 214 D2 · 217)
    assert lineage["effect_verified"] == 13


# ── D5 · F15 날짜 ───────────────────────────────────────────────────────────

def test_dates_outside_2000_to_2100_are_refused_everywhere(client):
    for value in ("0025-01-01", "9999-12-31", "1999-12-31", "2101-01-01"):
        response = client.post("/api/projects", json={"title": "x", "start_date": value})
        assert response.status_code == 400 and "2000~2100" in response.json()["detail"], value
    assert client.post("/api/projects", json={"title": "x", "due_date": "2100-12-31"}).status_code == 201


def test_entry_dates_cannot_be_in_the_future(client):
    project = make(client)
    far = client.post(f"/api/projects/{project['id']}/entries", json={"date": "9999-12-31", "title": "미래"})
    assert far.status_code == 400
    soon = client.post(f"/api/projects/{project['id']}/entries", json={"date": TOMORROW, "title": "내일"})
    assert soon.status_code == 400 and "진행일지 날짜가 오늘보다 뒤입니다" in soon.json()["detail"]
    entry = client.post(f"/api/projects/{project['id']}/entries", json={"title": "오늘"}).json()
    moved = client.patch(f"/api/entries/{entry['id']}", json={"date": TOMORROW})
    assert moved.status_code == 400
    # 최근 갱신이 미래로 고정되지 않는다
    assert client.get(f"/api/projects/{project['id']}").json()["updated_at"] <= TODAY + "T99"


def test_entry_outside_the_project_period_is_kept_with_a_warning(client):
    project = make(client, status="done", start_date="2026-03-01", due_date="2026-06-30", completed_at="2026-06-30")
    early = client.post(f"/api/projects/{project['id']}/entries", json={"date": "2025-01-01", "title": "준비"})
    assert early.status_code == 201
    assert early.json()["warnings"] == ["과제 기간(2026-03-01~2026-06-30) 밖의 날짜입니다."]
    inside = client.post(f"/api/projects/{project['id']}/entries", json={"date": "2026-04-01", "title": "안"}).json()
    assert inside["warnings"] == []
    moved = client.patch(f"/api/entries/{inside['id']}", json={"date": "2026-08-01"}).json()
    assert moved["warnings"] and "밖의 날짜" in moved["warnings"][0]


def test_report_dates_are_strict_and_near_today(client):
    project = make(client)
    url = f"/api/projects/{project['id']}/reports/draft"
    for value in ("20260101", "2026-W02-1", "9999-12-31", (date.today() + timedelta(days=400)).isoformat(),
                  (date.today() - timedelta(days=400)).isoformat()):
        assert client.post(url, json={"report_date": value}).status_code == 400, value
    draft = client.post(url, json={"report_date": TODAY}).json()
    assert client.patch(f"/api/reports/{draft['id']}", json={"report_date": "20261001"}).status_code == 400


def test_a_report_more_than_a_week_ahead_cannot_be_frozen(client):
    project = make(client)
    ahead = (date.today() + timedelta(days=30)).isoformat()
    draft = client.post(f"/api/projects/{project['id']}/reports/draft", json={"report_date": ahead}).json()
    frozen = client.post(f"/api/reports/{draft['id']}/freeze")
    assert frozen.status_code == 400 and "1주 넘게" in frozen.json()["detail"]
    assert client.get(f"/api/reports/{draft['id']}").json()["frozen"] is False
    week = (date.today() + timedelta(days=7)).isoformat()
    client.patch(f"/api/reports/{draft['id']}", json={"report_date": week})
    assert client.post(f"/api/reports/{draft['id']}/freeze").status_code == 200


def test_freeze_recomputes_the_covered_range(client):
    # F5 — 보고일을 앞당긴 뒤 확정하면 담은 범위의 끝이 그대로였다
    project = make(client)
    for day in ("2026-09-01", "2026-09-10", "2026-09-20"):
        client.post(f"/api/projects/{project['id']}/entries", json={"date": day, "title": "e" + day})
    draft = client.post(f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-09-30"}).json()
    assert (draft["covers_from"], draft["covers_to"]) == ("2026-09-01", "2026-09-20")
    client.patch(f"/api/reports/{draft['id']}", json={"report_date": "2026-09-05"})
    frozen = client.post(f"/api/reports/{draft['id']}/freeze").json()
    assert (frozen["covers_from"], frozen["covers_to"]) == ("2026-09-01", "2026-09-01")
    assert frozen["entry_count"] == 1


def test_report_audience_is_trimmed_on_update(client):
    # F11
    project = make(client)
    draft = client.post(f"/api/projects/{project['id']}/reports/draft", json={"report_date": TODAY}).json()
    updated = client.patch(f"/api/reports/{draft['id']}", json={"audience": "  팀장  "}).json()
    assert updated["audience"] == "팀장"


# ── D11 같은 이름 ───────────────────────────────────────────────────────────

def test_title_check_finds_the_same_name_before_saving(client):
    first = make(client, "수명 평가")
    second = make(client, "다른 과제")
    found = client.get("/api/projects/title-check", params={"title": "  수명 평가 "}).json()
    assert found == {"same": [{"id": first["id"], "title": "수명 평가"}]}
    assert client.get("/api/projects/title-check", params={"title": "수명 평가", "exclude": first["id"]}).json() == {"same": []}
    assert client.get("/api/projects/title-check", params={"title": ""}).json() == {"same": []}
    renamed = client.patch(f"/api/projects/{second['id']}", json={"title": "수명 평가"}).json()
    assert renamed["warnings"] == [f"같은 이름의 과제가 이미 있습니다: {first['id']}"]
    untouched = client.patch(f"/api/projects/{second['id']}", json={"group": "소재"}).json()
    assert untouched["warnings"] == []


def test_same_title_projects_helper(db, client):
    from app.services.projects import same_title_projects

    first = make(client, "Alpha")
    make(client, "beta")
    assert same_title_projects(db, " ALPHA ") == [{"id": first["id"], "title": "Alpha"}]
    assert same_title_projects(db, "alpha", exclude_id=first["id"]) == []


# ── D12 태그 ────────────────────────────────────────────────────────────────

def test_tags_are_written_in_the_spelling_already_in_use(client):
    make(client, "처음", tags=["AI"])
    second = make(client, "다음", tags=["ai", "#AI", " A  I ", "#품질  개선"])
    assert second["tags"] == ["AI", "품질 개선"]
    entry = client.post(f"/api/projects/{second['id']}/entries", json={"title": "기록", "tags": ["#ai", "품질개선"]}).json()
    assert sorted(entry["tags"]) == ["AI", "품질 개선"]


def test_old_files_with_different_spellings_merge_when_read(client, vault_dir):
    first = make(client, "처음", tags=["AI"])
    second = make(client, "다음", tags=["품질"])
    path = index_of(vault_dir, second["id"])
    path.write_text(path.read_text(encoding="utf-8").replace("tags:\n- 품질", "tags: [ai, '#Ai']"), encoding="utf-8")
    before = index_of(vault_dir, second["id"]).read_text(encoding="utf-8")
    client.post("/api/reindex")
    assert client.get(f"/api/projects/{second['id']}").json()["tags"] == ["AI"]
    assert {item["id"] for item in client.get("/api/projects", params={"tag": "AI"}).json()} == {first["id"], second["id"]}
    assert index_of(vault_dir, second["id"]).read_text(encoding="utf-8") == before  # 파일은 그대로


# ── D14 길이 · 한 줄 ────────────────────────────────────────────────────────

def test_titles_groups_and_bodies_have_limits(client):
    def refused(payload, word):
        response = client.post("/api/projects", json={"title": "x", **payload})
        assert response.status_code == 400 and word in response.json()["detail"], response.text

    refused({"title": "가" * 101}, "과제명")
    refused({"title": "줄\n바꿈"}, "과제명")
    refused({"title": "제어\x07문자"}, "과제명")
    refused({"group": "그" * 41}, "그룹")
    refused({"group": "a\nb"}, "그룹")
    refused({"body": "a\x00b"}, "본문")
    refused({"body": "x" * 2_000_001}, "본문")
    assert client.post("/api/projects", json={"title": "가" * 100, "body": "줄\n\t탭"}).status_code == 201
    project = make(client)
    long_entry = client.post(f"/api/projects/{project['id']}/entries", json={"title": "e" * 101})
    assert long_entry.status_code == 400 and "제목" in long_entry.json()["detail"]
    assert client.post(f"/api/projects/{project['id']}/entries", json={"title": "a\nb"}).status_code == 400


def test_an_old_long_title_does_not_block_other_fields(client, vault_dir):
    project = make(client, "짧은 제목")
    edit_meta(index_of(vault_dir, project["id"]), title="'" + "긴" * 150 + "'")
    client.post("/api/reindex")
    saved = client.patch(f"/api/projects/{project['id']}", json={"status": "on_hold", "title": "긴" * 150})
    assert saved.status_code == 200, saved.text
    changed = client.patch(f"/api/projects/{project['id']}", json={"title": "다" * 120})
    assert changed.status_code == 400


def test_author_rule_applies_to_created_by_and_entry_author(client):
    # F13
    assert client.post("/api/projects", json={"title": "x", "created_by": "a\nb"}).status_code == 400
    project = make(client, created_by="  홍길동  ")
    assert project["created_by"] == "홍길동"
    response = client.post(f"/api/projects/{project['id']}/entries", json={"title": "t", "author": "가" * 41})
    assert response.status_code == 400


# ── D15 선행 과제 ───────────────────────────────────────────────────────────

def test_an_archived_predecessor_does_not_block_saving(client):
    first = make(client, "1단계", start_date="2025-01-01")
    second = make(client, "2단계", start_date="2026-01-01", predecessors=[first["id"]])
    assert client.post(f"/api/projects/{first['id']}/archive").status_code == 204
    assert client.patch(f"/api/projects/{second['id']}", json={"title": "2단계 고침"}).status_code == 200
    kept = client.patch(f"/api/projects/{second['id']}", json={"predecessors": [first["id"]]})
    assert kept.status_code == 200 and kept.json()["predecessors"] == [first["id"]]
    added = client.patch(f"/api/projects/{second['id']}", json={"predecessors": [first["id"], "2020-999"]})
    assert added.status_code == 400


def test_new_predecessors_are_still_checked(client):
    first = make(client, "앞")
    second = make(client, "뒤", predecessors=[first["id"]])
    assert client.patch(f"/api/projects/{first['id']}", json={"predecessors": [second["id"]]}).status_code == 400
    assert client.patch(f"/api/projects/{first['id']}", json={"predecessors": [first["id"]]}).status_code == 400


def test_inverted_year_order_is_a_warning(client):
    later = make(client, "2026 과제", start_date="2026-02-01")
    earlier = client.post("/api/projects", json={
        "title": "2025 과제", "start_date": "2025-02-01", "predecessors": [later["id"]]})
    assert earlier.status_code == 201
    assert any("착수년도" in text for text in earlier.json()["warnings"])
    again = client.patch(f"/api/projects/{earlier.json()['id']}", json={"predecessors": [later["id"]]}).json()
    assert any("착수년도" in text for text in again["warnings"])


# ── D18 · F4 · F7 손으로 고친 파일 ─────────────────────────────────────────

def test_hand_edited_project_values_are_listed_as_problems(client, vault_dir):
    ids = [make(client, f"H{i}")["id"] for i in range(7)]
    edit_meta(index_of(vault_dir, ids[0]), status="완료")
    edit_meta(index_of(vault_dir, ids[1]), type="없는속성")
    edit_meta(index_of(vault_dir, ids[2]), status="done", completed_at="null")
    edit_meta(index_of(vault_dir, ids[3]), effect_expected="1e300", effect_verified="-5")
    edit_meta(index_of(vault_dir, ids[4]), predecessors="['2020-404']")
    edit_meta(index_of(vault_dir, ids[5]), predecessors=f"['{ids[6]}']")
    edit_meta(index_of(vault_dir, ids[6]), predecessors=f"['{ids[5]}']")
    before = {pid: index_of(vault_dir, pid).read_text(encoding="utf-8") for pid in ids}

    found = problems(client)
    reasons = {pid: [item["reason"] for item in found if f"/{pid}-" in item["path"]] for pid in ids}
    assert any("상태 값(완료)" in text for text in reasons[ids[0]])
    assert any("속성 값(없는속성)" in text for text in reasons[ids[1]])
    assert any("완료일(completed_at)이 없습니다" in text for text in reasons[ids[2]])
    assert sum("effect_" in text for text in reasons[ids[3]]) == 2
    assert any("2020-404" in text for text in reasons[ids[4]])
    assert any("고리" in text for text in reasons[ids[5]]) and any("고리" in text for text in reasons[ids[6]])
    assert all(index_of(vault_dir, pid).read_text(encoding="utf-8") == before[pid] for pid in ids)
    # 문제 목록은 메타에도 늘 실린다
    assert len(client.get("/api/meta").json()["problems"]) == len(found)
    shown = client.get(f"/api/projects/{ids[3]}").json()
    assert (shown["effect_expected"], shown["effect_verified"]) == (None, None)


def test_reversed_period_in_a_file_is_a_problem_but_other_fields_still_save(client, vault_dir):
    project = make(client, "거꾸로")
    edit_meta(index_of(vault_dir, project["id"]), start_date="'2026-12-01'", due_date="'2026-01-01'")
    assert any("시작일" in item["reason"] for item in problems(client))
    assert client.patch(f"/api/projects/{project['id']}", json={"title": "거꾸로 고침"}).status_code == 200
    assert client.patch(f"/api/projects/{project['id']}", json={"due_date": "2026-11-01"}).status_code == 400
    assert client.patch(f"/api/projects/{project['id']}", json={"due_date": "2026-12-31"}).status_code == 200
    assert not any("시작일" in item["reason"] for item in client.get("/api/meta").json()["problems"])


def test_hand_written_entry_without_any_date_uses_the_file_time(client, vault_dir):
    # F7 — `notes.md` 가 날짜 자리에 들어갔다
    project = make(client)
    logs = index_of(vault_dir, project["id"]).parent / "logs"
    note = logs / "notes.md"
    note.write_text("---\ntitle: 손 기록\n---\n본문", encoding="utf-8")
    from datetime import datetime

    stamp = datetime(2026, 5, 4, 12).timestamp()
    os.utime(note, (stamp, stamp))
    bad = logs / "2026-09-01-나쁜날짜.md"
    bad.write_text("---\ndate: '2026-02-30'\ntitle: 틀린 날짜\n---\n", encoding="utf-8")
    found = problems(client)
    entries = {item["title"]: item["date"] for item in client.get(f"/api/projects/{project['id']}/entries").json()}
    assert entries["손 기록"] == "2026-05-04"
    assert entries["틀린 날짜"] == "2026-09-01"  # 이름의 날짜
    assert any("notes.md" in item["path"] and "파일 수정일" in item["reason"] for item in found)
    assert any("나쁜날짜" in item["path"] for item in found)


def test_report_date_problem_is_cleared_not_piled_up(client, vault_dir):
    # F4 — 경로가 틀려 저장할 때마다 하나씩 늘었다
    project = make(client)
    client.post(f"/api/projects/{project['id']}/reports/draft", json={"report_date": TODAY})
    report = next((index_of(vault_dir, project["id"]).parent / "reports").rglob("report.md"))
    text = report.read_text(encoding="utf-8")
    report.write_text(re.sub(r"^report_date:.*$", "report_date: '2026-13-40'", text, count=1, flags=re.M), encoding="utf-8")
    first = [item for item in problems(client) if "report_date" in item["reason"]]
    assert len(first) == 1 and first[0]["path"].startswith("projects/")
    for _ in range(3):
        client.post(f"/api/projects/{project['id']}/entries", json={"title": "x"})
    again = [item for item in client.get("/api/meta").json()["problems"] if "report_date" in item["reason"]]
    assert len(again) == 1


def test_hand_written_activity_and_meeting_values_are_listed(client, vault_dir):
    activity = vault_dir / "people" / "김철수" / "activities" / "교육.md"
    activity.parent.mkdir(parents=True)
    activity.write_text("---\nperson: 김철수\ndate: 지난주\nkind: 모르는구분\ntitle: 교육\n---\n", encoding="utf-8")
    meeting = vault_dir / "people" / "김철수" / "meetings" / "면담.md"
    meeting.parent.mkdir(parents=True)
    meeting.write_text("---\nperson: 김철수\ndate: 어제\nkind: 정기\n---\n", encoding="utf-8")
    found = problems(client)
    activity_reasons = [item["reason"] for item in found if item["path"].endswith("activities/교육.md")]
    assert any("구분(kind)" in text for text in activity_reasons)
    assert any("date" in text for text in activity_reasons)
    assert any(item["path"].endswith("meetings/면담.md") for item in found)
    assert activity.read_text(encoding="utf-8").count("지난주") == 1


def test_far_future_date_in_a_hand_written_entry_is_listed(client, vault_dir):
    project = make(client)
    logs = index_of(vault_dir, project["id"]).parent / "logs"
    (logs / "2026-01-01-먼미래.md").write_text("---\ndate: '9999-12-31'\ntitle: 먼 미래\n---\n", encoding="utf-8")
    assert any("2000~2100" in item["reason"] for item in problems(client))
