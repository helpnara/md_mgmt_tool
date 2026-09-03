"""보고 이력 — 찾기(T13) · 변경분(T11) · 리마인더(T12).

보고는 과제 폴더마다 흩어져 쌓인다. 여기서 지키는 것은 셋이다.
  · 과제를 가로질러 찾을 수 있어야 한다
  · "지난번 보고와 뭐가 달라졌나"에 답할 수 있어야 한다
  · 보고 주기를 사람이 기억하지 않아도 되어야 한다
"""
from __future__ import annotations

from datetime import date

import pytest

from app.services import reports as svc


def make_project(client, title="과제", **kwargs):
    payload = {"title": title, "status": "in_progress"}
    payload.update(kwargs)
    response = client.post("/api/projects", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def make_report(client, project_id, *, report_date, audience=None, body=None, freeze=False):
    response = client.post(
        f"/api/projects/{project_id}/reports/draft",
        json={"report_date": report_date, "audience": audience},
    )
    assert response.status_code == 201, response.text
    report = response.json()
    if body is not None:
        report = client.patch(f"/api/reports/{report['id']}", json={"body": body}).json()
    if freeze:
        report = client.post(f"/api/reports/{report['id']}/freeze").json()
    return report


# ── 찾기 (T13) ────────────────────────────────────────────────────────────────

def test_reports_from_every_project_come_back_newest_first(client):
    first = make_project(client, "첫 과제")
    second = make_project(client, "둘째 과제")
    make_report(client, first["id"], report_date="2026-08-04")
    make_report(client, second["id"], report_date="2026-09-01")
    make_report(client, first["id"], report_date="2026-08-18")

    rows = client.get("/api/reports").json()
    assert [row["report_date"] for row in rows] == ["2026-09-01", "2026-08-18", "2026-08-04"]
    # 어느 과제의 보고인지 목록에서 바로 알 수 있어야 한다.
    assert rows[0]["project_title"] == "둘째 과제"


def test_filter_by_audience_is_a_partial_match(client):
    project = make_project(client)
    make_report(client, project["id"], report_date="2026-08-04", audience="전사 주요업무 보고")
    make_report(client, project["id"], report_date="2026-08-11", audience="팀 주간회의")

    rows = client.get("/api/reports", params={"audience": "주요업무"}).json()
    assert [row["audience"] for row in rows] == ["전사 주요업무 보고"]


def test_filter_by_period_includes_both_ends(client):
    project = make_project(client)
    for day in ("2026-08-04", "2026-08-11", "2026-08-18"):
        make_report(client, project["id"], report_date=day)

    rows = client.get("/api/reports", params={"from": "2026-08-04", "to": "2026-08-11"}).json()
    assert [row["report_date"] for row in rows] == ["2026-08-11", "2026-08-04"]


def test_search_looks_in_body_title_and_project_name(client):
    project = make_project(client, "소재 개발")
    other = make_project(client, "공정 개선")
    make_report(client, project["id"], report_date="2026-08-04")
    make_report(client, other["id"], report_date="2026-08-11", body="## 보고 요약\n\n시험 성적서 회신")

    assert len(client.get("/api/reports", params={"q": "소재"}).json()) == 1
    hit = client.get("/api/reports", params={"q": "성적서"}).json()
    assert len(hit) == 1
    # 어디에 걸렸는지 알 수 있게 발췌를 붙인다.
    assert "성적서" in hit[0]["excerpt"]


def test_filter_by_state_separates_drafts_from_finished_reports(client):
    project = make_project(client)
    make_report(client, project["id"], report_date="2026-08-04", freeze=True)
    make_report(client, project["id"], report_date="2026-08-11")

    assert [row["frozen"] for row in client.get("/api/reports", params={"state": "frozen"}).json()] == [True]
    assert [row["frozen"] for row in client.get("/api/reports", params={"state": "draft"}).json()] == [False]


def test_list_does_not_carry_the_whole_body(client):
    """보고가 쌓여도 목록 응답이 무거워지지 않아야 한다."""
    project = make_project(client)
    make_report(client, project["id"], report_date="2026-08-04", body="본문" * 500)
    assert "body" not in client.get("/api/reports").json()[0]


# ── 변경분 (T11) ──────────────────────────────────────────────────────────────

def test_first_report_has_nothing_to_compare_with(client):
    project = make_project(client)
    report = make_report(client, project["id"], report_date="2026-08-04")
    assert client.get(f"/api/reports/{report['id']}/diff").json()["previous"] is None


def test_diff_shows_what_changed_since_the_last_finished_report(client):
    project = make_project(client)
    make_report(
        client, project["id"], report_date="2026-08-04",
        body="## 보고 요약\n\n- 시제품 1차 제작\n- 협력사 미팅\n", freeze=True,
    )
    now = make_report(
        client, project["id"], report_date="2026-08-11",
        body="## 보고 요약\n\n- 시제품 2차 제작\n- 협력사 미팅\n",
    )

    data = client.get(f"/api/reports/{now['id']}/diff").json()
    assert data["previous"]["report_date"] == "2026-08-04"
    assert data["added"] == 1 and data["removed"] == 1
    kinds = {line["kind"] for line in data["lines"]}
    assert "add" in kinds and "del" in kinds
    assert any(line["kind"] == "add" and "2차" in line["text"] for line in data["lines"])
    assert any(line["kind"] == "del" and "1차" in line["text"] for line in data["lines"])
    # 안 바뀐 줄은 남아 있어도 되지만, 바뀐 줄을 못 찾을 만큼 많으면 안 된다.
    assert any(line["kind"] == "same" for line in data["lines"])


def test_drafts_are_never_the_thing_we_compare_against(client):
    """기준은 '지난번에 실제로 보고한 것'이다. 초안은 아직 보고가 아니다."""
    project = make_project(client)
    make_report(client, project["id"], report_date="2026-08-04", body="확정본\n", freeze=True)
    make_report(client, project["id"], report_date="2026-08-11", body="초안\n")
    now = make_report(client, project["id"], report_date="2026-08-18", body="이번 것\n")

    assert client.get(f"/api/reports/{now['id']}/diff").json()["previous"]["report_date"] == "2026-08-04"


def test_diff_does_not_reach_into_another_project(client):
    mine = make_project(client, "내 과제")
    other = make_project(client, "남의 과제")
    make_report(client, other["id"], report_date="2026-08-04", freeze=True)
    report = make_report(client, mine["id"], report_date="2026-08-11")

    assert client.get(f"/api/reports/{report['id']}/diff").json()["previous"] is None


def test_long_unchanged_stretches_are_folded(client):
    project = make_project(client)
    filler = "\n".join(f"- 변함없는 줄 {i}" for i in range(30))
    make_report(client, project["id"], report_date="2026-08-04", body=f"{filler}\n- 예전 줄\n", freeze=True)
    now = make_report(client, project["id"], report_date="2026-08-11", body=f"{filler}\n- 새 줄\n")

    lines = client.get(f"/api/reports/{now['id']}/diff").json()["lines"]
    assert any(line["kind"] == "gap" for line in lines)
    # 30줄이 그대로 실려 오면 접은 의미가 없다.
    assert len(lines) < 15


def test_diff_of_a_missing_report_is_404(client):
    assert client.get("/api/reports/9999/diff").status_code == 404


# ── 리마인더 (T12) ────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "day, phase",
    [
        (date(2026, 9, 7), "select"),   # 월요일 — 오늘 고른다
        (date(2026, 9, 8), "report"),   # 화요일 — 오늘 보고한다
    ],
)
def test_banner_appears_on_the_two_days_that_matter(client, db, day, phase):
    project = make_project(client)
    client.post(f"/api/projects/{project['id']}/entries", json={"date": "2026-09-05", "body": "진행"})

    data = svc.reminder(db, day)
    assert data["phase"] == phase
    assert data["report_date"] == "2026-09-08"
    assert data["pending"] == 1


@pytest.mark.parametrize("day", [date(2026, 9, 9), date(2026, 9, 10), date(2026, 9, 12)])
def test_no_banner_on_other_days(client, db, day):
    """매일 뜨면 곧 안 보게 된다. 선정일·보고일에만 띄운다."""
    assert svc.reminder(db, day) is None


def test_banner_counts_what_is_already_prepared(client, db):
    project = make_project(client)
    make_report(client, project["id"], report_date="2026-09-08")
    other = make_project(client, "둘째")
    make_report(client, other["id"], report_date="2026-09-08", freeze=True)

    data = svc.reminder(db, date(2026, 9, 8))
    assert data["drafts"] == 1 and data["done"] == 1


def test_dashboard_carries_the_reminder_slot(client):
    make_project(client)
    assert "reminder" in client.get("/api/dashboard").json()


# ── 마지막 보고처 (보고 대상 표의 새 칸) ──────────────────────────────────────

def test_candidate_carries_where_the_last_report_went(client):
    """날짜만으로는 어떤 수준의 보고였는지 알 수 없다. 보고처를 함께 준다."""
    project = make_project(client)
    make_report(client, project["id"], report_date="2026-08-04", audience="팀 주간회의", freeze=True)
    last = make_report(
        client, project["id"], report_date="2026-08-18", audience="전사 주요업무 보고", freeze=True
    )

    item = client.get("/api/report-candidates").json()["items"][0]
    assert item["last_report_audience"] == "전사 주요업무 보고"
    # 그 보고를 바로 열 수 있게 id 도 함께 준다.
    assert item["last_report_id"] == last["id"]


def test_a_draft_is_not_the_last_report(client):
    """확정하지 않은 초안은 아직 보고가 아니다. 마지막 보고처가 초안을 가리키면 안 된다."""
    project = make_project(client)
    make_report(client, project["id"], report_date="2026-08-04", audience="팀 주간회의", freeze=True)
    make_report(client, project["id"], report_date="2026-08-18", audience="전사 주요업무 보고")

    item = client.get("/api/report-candidates").json()["items"][0]
    assert item["last_report_audience"] == "팀 주간회의"


def test_never_reported_project_has_no_last_report(client):
    make_project(client)
    item = client.get("/api/report-candidates").json()["items"][0]
    assert item["never_reported"] is True
    assert item["last_report_audience"] is None and item["last_report_id"] is None


def test_a_report_without_an_audience_is_not_an_error(client):
    """피보고자를 안 적고 보고한 건도 있다. 화면이 '미기재'로 보여 준다."""
    project = make_project(client)
    make_report(client, project["id"], report_date="2026-08-04", freeze=True)

    item = client.get("/api/report-candidates").json()["items"][0]
    assert item["never_reported"] is False
    assert item["last_report_audience"] is None


# ── 주간 보고 요일 설정 (TODO 50) ─────────────────────────────────────────────

def set_weekday(client, weekday):
    response = client.put("/api/settings", json={"report_weekday": weekday})
    assert response.status_code == 200, response.text
    return response.json()


def test_report_day_defaults_to_tuesday(client):
    """지금까지 쓰던 값. 설정을 건드리지 않은 사람의 동작이 바뀌면 안 된다."""
    assert client.get("/api/settings").json()["report_weekday"] == 1
    assert svc.default_report_date(date(2026, 9, 3)) == "2026-09-08"  # 목 → 다음 화


def test_the_report_day_follows_the_setting(client):
    set_weekday(client, 4)  # 금요일
    # 2026-09-03 은 목요일 → 다음 날이 금요일
    assert svc.default_report_date(date(2026, 9, 3)) == "2026-09-04"
    set_weekday(client, 0)  # 월요일
    assert svc.default_report_date(date(2026, 9, 3)) == "2026-09-07"


def test_today_counts_when_it_is_the_report_day(client):
    set_weekday(client, 3)  # 목요일
    assert svc.default_report_date(date(2026, 9, 3)) == "2026-09-03"


def test_the_reminder_moves_with_the_setting(client, db):
    """보고 예정일과 리마인더가 따로 놀면 '내일 보고입니다' 안내가 거짓말이 된다."""
    set_weekday(client, 4)  # 금요일
    assert svc.reminder(db, date(2026, 9, 4))["phase"] == "report"   # 금 = 보고일
    assert svc.reminder(db, date(2026, 9, 3))["phase"] == "select"   # 목 = 선정일
    assert svc.reminder(db, date(2026, 9, 2)) is None                # 수 = 조용


def test_the_reminder_names_the_same_day_the_draft_would_use(client, db):
    for weekday in range(7):
        set_weekday(client, weekday)
        today = date(2026, 9, 3)
        note = svc.reminder(db, today)
        if note:
            assert note["report_date"] == svc.default_report_date(today), weekday


def test_sunday_wraps_around_to_saturday_for_the_selection_day(client, db):
    set_weekday(client, 6)  # 일요일 보고
    assert svc.reminder(db, date(2026, 9, 5))["phase"] == "select"  # 토
    assert svc.reminder(db, date(2026, 9, 6))["phase"] == "report"  # 일


def test_a_weekday_outside_the_week_is_refused(client):
    for bad in (7, -1, "화요일"):
        response = client.put("/api/settings", json={"report_weekday": bad})
        assert response.status_code in (400, 422), (bad, response.text)
    # 거절당해도 기존 값은 그대로다.
    assert client.get("/api/settings").json()["report_weekday"] == 1


def test_a_broken_setting_falls_back_instead_of_crashing(client, vault_dir):
    import json as json_module

    path = vault_dir / "settings.json"
    path.write_text(json_module.dumps({"report_weekday": "엉뚱한 값"}), encoding="utf-8")
    # 설정이 깨졌다고 보고 예정일을 못 구하면 도구 전체가 멈춘다.
    assert svc.default_report_date(date(2026, 9, 3)) == "2026-09-08"


def test_meta_carries_the_weekday_for_the_screen(client):
    set_weekday(client, 2)
    assert client.get("/api/meta").json()["report_weekday"] == 2
