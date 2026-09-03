from __future__ import annotations

from datetime import date


def make_project(client, title="리튬전지 수명평가", **kwargs):
    payload = {"title": title, "status": "in_progress"}
    payload.update(kwargs)
    return client.post("/api/projects", json=payload).json()


def add_entry(client, project_id, date_str, title, body="내용"):
    return client.post(
        f"/api/projects/{project_id}/entries",
        json={"date": date_str, "title": title, "body": body},
    ).json()


def test_draft_collects_unreported_entries(client, vault_dir):
    project = make_project(client)
    add_entry(client, project["id"], "2026-08-25", "셀 조립", "3종 조립 완료")
    add_entry(client, project["id"], "2026-09-03", "1차 측정", "유지율 98.2%")

    report = client.post(
        f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-09-08"}
    ).json()

    assert report["report_date"] == "2026-09-08"
    assert report["frozen"] is False
    assert report["covers_from"] == "2026-08-25"
    assert report["covers_to"] == "2026-09-03"
    # 초안에는 미보고 진행일지의 제목과 본문이 함께 담긴다.
    assert "셀 조립" in report["body"] and "유지율 98.2%" in report["body"]

    path = vault_dir / "projects" / f"{project['id']}-리튬전지-수명평가" / "reports" / "2026-09-08" / "report.md"
    assert path.exists()


def test_freeze_makes_report_readonly_and_resets_backlog(client):
    project = make_project(client)
    add_entry(client, project["id"], "2026-08-25", "셀 조립")
    report = client.post(
        f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-09-08"}
    ).json()

    client.patch(f"/api/reports/{report['id']}", json={"body": "정리한 보고 내용"})
    frozen = client.post(f"/api/reports/{report['id']}/freeze").json()
    assert frozen["frozen"] is True
    assert frozen["entry_count"] == 1

    # 확정 뒤에는 수정이 막힌다.
    blocked = client.patch(f"/api/reports/{report['id']}", json={"body": "몰래 수정"})
    assert blocked.status_code == 409
    assert client.get(f"/api/reports/{report['id']}").json()["body"] == "정리한 보고 내용"

    # 확정된 보고에 담긴 진행일지는 미보고 분량에서 빠진다.
    candidate = next(
        item for item in client.get("/api/report-candidates").json()["items"]
        if item["id"] == project["id"]
    )
    assert candidate["unreported_entries"] == 0
    assert candidate["last_reported_at"] == "2026-09-08"


def test_frozen_report_keeps_its_snapshot_when_entries_change(client):
    """보고 뒤 진행일지를 고쳐도 보고 문서는 그대로여야 한다."""
    project = make_project(client)
    entry = add_entry(client, project["id"], "2026-08-25", "셀 조립", "초기 결과")
    report = client.post(
        f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-09-08"}
    ).json()
    client.post(f"/api/reports/{report['id']}/freeze")

    client.patch(f"/api/entries/{entry['id']}", json={"body": "나중에 수정한 결과"})
    assert "초기 결과" in client.get(f"/api/reports/{report['id']}").json()["body"]


def test_second_draft_only_covers_entries_after_the_last_report(client):
    project = make_project(client)
    add_entry(client, project["id"], "2026-08-25", "셀 조립")
    first = client.post(
        f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-09-08"}
    ).json()
    client.post(f"/api/reports/{first['id']}/freeze")

    add_entry(client, project["id"], "2026-09-10", "2차 측정", "새 결과")
    second = client.post(
        f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-09-15"}
    ).json()

    assert "2차 측정" in second["body"]
    assert "셀 조립" not in second["body"]
    assert second["covers_from"] == "2026-09-10"


def test_unfreeze_allows_correction_and_records_it(client, vault_dir):
    project = make_project(client)
    add_entry(client, project["id"], "2026-08-25", "셀 조립")
    report = client.post(
        f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-09-08"}
    ).json()
    client.post(f"/api/reports/{report['id']}/freeze")

    assert client.post(f"/api/reports/{report['id']}/unfreeze").json()["frozen"] is False
    assert client.patch(f"/api/reports/{report['id']}", json={"body": "고친 내용"}).status_code == 200

    path = vault_dir / "projects" / f"{project['id']}-리튬전지-수명평가" / "reports" / "2026-09-08" / "report.md"
    assert "unfrozen_at:" in path.read_text(encoding="utf-8")


def test_several_reports_can_share_one_date(client, vault_dir):
    """중간 보고와 완료 보고를 같은 날 각각 남길 수 있어야 한다."""
    project = make_project(client)
    add_entry(client, project["id"], "2026-09-01", "기록")

    first = client.post(
        f"/api/projects/{project['id']}/reports/draft",
        json={"report_date": "2026-09-08", "audience": "팀장"},
    )
    second = client.post(
        f"/api/projects/{project['id']}/reports/draft",
        json={"report_date": "2026-09-08", "audience": "연구소장"},
    )
    assert first.status_code == 201 and second.status_code == 201

    assert first.json()["rel_path"] == "reports/2026-09-08/report.md"
    assert second.json()["rel_path"] == "reports/2026-09-08-2/report.md"
    assert second.json()["report_date"] == "2026-09-08"  # 날짜는 그대로다
    listed = client.get(f"/api/projects/{project['id']}/reports").json()
    assert sorted(item["audience"] for item in listed) == ["연구소장", "팀장"]

    folders = sorted(
        path.name for path in (vault_dir / "projects" / f"{project['id']}-리튬전지-수명평가" / "reports").iterdir()
    )
    assert folders == ["2026-09-08", "2026-09-08-2"]


def test_audience_can_be_fixed_after_freezing_but_body_cannot(client):
    """피보고자를 잘못 적었다고 확정을 풀 이유는 없다. 본문은 그대로 잠근다."""
    project = make_project(client)
    add_entry(client, project["id"], "2026-09-01", "기록")
    report = client.post(
        f"/api/projects/{project['id']}/reports/draft",
        json={"report_date": "2026-09-08", "audience": "팀정"},
    ).json()
    client.post(f"/api/reports/{report['id']}/freeze")

    fixed = client.patch(f"/api/reports/{report['id']}", json={"audience": "팀장"})
    assert fixed.status_code == 200
    assert fixed.json()["audience"] == "팀장"

    blocked = client.patch(f"/api/reports/{report['id']}", json={"body": "내용 수정"})
    assert blocked.status_code == 409


def test_audience_list_is_offered_for_autocomplete(client):
    project = make_project(client)
    for date, audience in (("2026-09-08", "팀장"), ("2026-09-15", "주간회의체")):
        client.post(
            f"/api/projects/{project['id']}/reports/draft",
            json={"report_date": date, "audience": audience},
        )
    assert client.get("/api/meta").json()["audiences"] == ["주간회의체", "팀장"]


def test_candidates_rank_by_elapsed_time_and_backlog(client):
    stale = make_project(client, title="오래된 과제", start_date="2026-01-01")
    for day in ("2026-08-01", "2026-08-10", "2026-08-20"):
        add_entry(client, stale["id"], day, f"{day} 기록")

    fresh = make_project(client, title="최근 보고한 과제", start_date="2026-08-25")
    add_entry(client, fresh["id"], "2026-08-26", "기록")
    report = client.post(
        f"/api/projects/{fresh['id']}/reports/draft", json={"report_date": date.today().isoformat()}
    ).json()
    client.post(f"/api/reports/{report['id']}/freeze")

    items = client.get("/api/report-candidates").json()["items"]
    assert items[0]["id"] == stale["id"]
    assert items[0]["unreported_entries"] == 3
    assert items[0]["score"] > items[-1]["score"]


def test_candidates_exclude_finished_projects(client):
    make_project(client, title="완료된 과제", status="done")
    make_project(client, title="진행중 과제")
    titles = [item["title"] for item in client.get("/api/report-candidates").json()["items"]]
    assert titles == ["진행중 과제"]

    with_all = client.get("/api/report-candidates", params={"include_inactive": True}).json()
    assert len(with_all["items"]) == 2


def test_report_attachment_link_is_relative_to_the_report_folder(client, vault_dir):
    project = make_project(client)
    report = client.post(
        f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-09-08"}
    ).json()
    saved = client.post(
        f"/api/reports/{report['id']}/attachments",
        files={"file": ("주간보고.xlsx", b"PK\x03\x04", "application/octet-stream")},
    ).json()

    assert saved["rel_path"] == "reports/2026-09-08/assets/001-주간보고.xlsx"
    assert saved["markdown"] == "[주간보고.xlsx](assets/001-주간보고.xlsx)"
    assert (vault_dir / "projects" / f"{project['id']}-리튬전지-수명평가" / saved["rel_path"]).exists()

    # 보고 문서만 봐도 어떤 자료로 보고했는지 알 수 있어야 한다.
    report_md = (
        vault_dir / "projects" / f"{project['id']}-리튬전지-수명평가"
        / "reports" / "2026-09-08" / "report.md"
    ).read_text(encoding="utf-8")
    assert "- reports/2026-09-08/assets/001-주간보고.xlsx" in report_md


def test_default_report_date_is_a_tuesday():
    from app.services.reports import default_report_date

    for day in range(1, 29):
        result = date.fromisoformat(default_report_date(date(2026, 9, day)))
        assert result.weekday() == 1  # 화요일
        assert result >= date(2026, 9, day)


def test_project_with_nothing_new_ranks_below_one_with_backlog(client):
    """보고할 새 내용이 없으면 아무리 오래 방치됐어도 위로 올라오면 안 된다."""
    ancient = make_project(client, title="아주 오래됐지만 진행 없는 과제", start_date="2015-01-01")
    active = make_project(client, title="최근 진행이 쌓인 과제", start_date="2026-08-25")
    for day in ("2026-08-26", "2026-08-27", "2026-08-28", "2026-08-31"):
        add_entry(client, active["id"], day, f"{day} 기록")

    items = client.get("/api/report-candidates").json()["items"]
    assert items[0]["id"] == active["id"]

    scores = {item["id"]: item["score"] for item in items}
    assert scores[ancient["id"]] == 2.0  # 경과 항 상한 8.0 × 진행 없음 계수 0.25
    assert scores[active["id"]] > scores[ancient["id"]]


def test_elapsed_term_is_capped(client):
    """10년 방치된 과제와 1년 방치된 과제가 같은 상한에 걸린다."""
    old_one = make_project(client, title="1년 전 과제", start_date="2025-09-01")
    older = make_project(client, title="10년 전 과제", start_date="2015-09-01")
    for project in (old_one, older):
        add_entry(client, project["id"], "2026-08-30", "기록")

    scores = {item["id"]: item["score"] for item in client.get("/api/report-candidates").json()["items"]}
    assert scores[old_one["id"]] == scores[older["id"]] == 8.5  # 상한 8.0 + 미보고 1건


# ── 보고일 바꾸기 ─────────────────────────────────────

def _project(client, title="보고일 과제"):
    return client.post("/api/projects", json={"title": title}).json()


def test_draft_uses_the_given_date_not_only_the_default(client):
    """초안을 만들 때 날짜를 직접 정할 수 있어야 한다.

    기본값(다음 화요일)만 쓸 수 있으면 지난 보고를 뒤늦게 기록할 수 없다.
    """
    project = _project(client)
    draft = client.post(
        f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-08-11"}
    ).json()
    assert draft["report_date"] == "2026-08-11"


def test_changing_the_date_moves_the_folder(client, vault_dir):
    """보고 문서는 reports/<보고일>/ 에 있다. 날짜만 고치면 폴더와 내용이 어긋난다."""
    project = _project(client, "폴더 이동")
    draft = client.post(
        f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-09-08"}
    ).json()
    directory = vault_dir / "projects" / f"{project['id']}-폴더-이동" / "reports"
    assert (directory / "2026-09-08" / "report.md").exists()

    updated = client.patch(f"/api/reports/{draft['id']}", json={"report_date": "2026-09-15"}).json()
    assert updated["report_date"] == "2026-09-15"
    assert (directory / "2026-09-15" / "report.md").exists()
    assert not (directory / "2026-09-08").exists()
    # 기본 제목이었다면 날짜를 따라간다.
    assert updated["title"] == "2026-09-15 보고"


def test_changing_the_date_carries_attachments_along(client, vault_dir):
    project = _project(client, "첨부 이동")
    draft = client.post(
        f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-09-08"}
    ).json()
    client.post(
        f"/api/reports/{draft['id']}/attachments",
        files={"file": ("보고자료.xlsx", b"x", "application/vnd.ms-excel")},
    )
    client.patch(f"/api/reports/{draft['id']}", json={"report_date": "2026-09-15"})

    directory = vault_dir / "projects" / f"{project['id']}-첨부-이동" / "reports"
    assert (directory / "2026-09-15" / "assets" / "001-보고자료.xlsx").exists()
    names = [a["orig_name"] for a in client.get(f"/api/reports/{draft['id']}/attachments").json()]
    assert names == ["보고자료.xlsx"]


def test_a_title_the_user_wrote_is_left_alone(client):
    project = _project(client, "제목 유지")
    draft = client.post(
        f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-09-08"}
    ).json()
    client.patch(f"/api/reports/{draft['id']}", json={"title": "전사 주요업무 보고"})
    updated = client.patch(f"/api/reports/{draft['id']}", json={"report_date": "2026-09-15"}).json()
    assert updated["title"] == "전사 주요업무 보고"


def test_frozen_report_keeps_its_date(client):
    """확정된 보고의 날짜는 '언제 보고했는가'라는 사실이다. 풀어야 고칠 수 있다."""
    project = _project(client, "확정 날짜")
    draft = client.post(
        f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-09-08"}
    ).json()
    client.post(f"/api/reports/{draft['id']}/freeze")

    response = client.patch(f"/api/reports/{draft['id']}", json={"report_date": "2026-09-15"})
    assert response.status_code == 409

    client.post(f"/api/reports/{draft['id']}/unfreeze")
    assert (
        client.patch(f"/api/reports/{draft['id']}", json={"report_date": "2026-09-15"}).json()[
            "report_date"
        ]
        == "2026-09-15"
    )


def test_invalid_date_is_rejected(client):
    project = _project(client, "잘못된 날짜")
    draft = client.post(f"/api/projects/{project['id']}/reports/draft", json={}).json()
    for bad in ("2026-13-45", "../../탈출", "그냥글자"):
        assert client.patch(f"/api/reports/{draft['id']}", json={"report_date": bad}).status_code == 400


def test_moving_onto_an_existing_date_does_not_overwrite(client, vault_dir):
    """같은 날짜에 이미 보고가 있으면 덮어쓰지 않고 옆에 놓는다."""
    project = _project(client, "같은 날 이동")
    first = client.post(
        f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-09-15"}
    ).json()
    second = client.post(
        f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-09-08"}
    ).json()

    client.patch(f"/api/reports/{second['id']}", json={"report_date": "2026-09-15"})
    reports = client.get(f"/api/projects/{project['id']}/reports").json()
    assert len(reports) == 2
    assert all(r["report_date"] == "2026-09-15" for r in reports)
    directory = vault_dir / "projects" / f"{project['id']}-같은-날-이동" / "reports"
    assert (directory / "2026-09-15").exists() and (directory / "2026-09-15-2").exists()
    assert client.get(f"/api/reports/{first['id']}").status_code == 200
