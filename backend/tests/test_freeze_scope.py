"""보고를 확정했을 때 '읽기 전용'이 되는 범위는 어디까지인가.

확정되는 것은 그 보고 문서 하나뿐이고, 과제와 진행 이력은 계속 쓸 수 있어야 한다.
"""
from __future__ import annotations


def build(client):
    project = client.post("/api/projects", json={"title": "확정 범위 확인"}).json()
    entry = client.post(
        f"/api/projects/{project['id']}/entries",
        json={"date": "2026-09-03", "title": "보고에 포함된 기록", "body": "원래 내용"},
    ).json()
    report = client.post(
        f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-09-08"}
    ).json()
    client.post(f"/api/reports/{report['id']}/freeze")
    return project, entry, report


def test_only_the_report_becomes_read_only(client):
    project, entry, report = build(client)

    # 확정된 보고 문서만 잠긴다.
    assert client.patch(f"/api/reports/{report['id']}", json={"body": "수정"}).status_code == 409

    # 보고에 포함됐던 진행일지도 계속 수정할 수 있다.
    assert (
        client.patch(f"/api/entries/{entry['id']}", json={"body": "나중에 보완한 내용"}).status_code
        == 200
    )
    assert "보완" in client.get(f"/api/entries/{entry['id']}").json()["body"]

    # 과제 정보와 개요도 그대로 수정할 수 있다.
    assert client.patch(f"/api/projects/{project['id']}", json={"status": "reviewing"}).status_code == 200
    assert client.patch(f"/api/projects/{project['id']}", json={"body": "개요 수정"}).status_code == 200


def test_new_entries_after_a_report_are_fully_editable(client):
    project, _, _ = build(client)

    later = client.post(
        f"/api/projects/{project['id']}/entries",
        json={"date": "2026-09-12", "title": "보고 이후 새 기록", "body": "새 내용"},
    )
    assert later.status_code == 201
    entry_id = later.json()["id"]

    assert client.patch(f"/api/entries/{entry_id}", json={"body": "고친 새 내용"}).status_code == 200
    assert (
        client.post(
            f"/api/entries/{entry_id}/attachments",
            files={"file": ("새자료.xlsx", b"PK\x03\x04", "application/octet-stream")},
        ).status_code
        == 201
    )
    assert client.delete(f"/api/entries/{entry_id}").status_code == 204


def test_new_entries_show_up_as_unreported_for_the_next_report(client):
    """중간·완료 보고가 이어지므로, 확정 이후의 기록은 다음 보고 대상이 되어야 한다."""
    project, _, _ = build(client)
    client.post(
        f"/api/projects/{project['id']}/entries",
        json={"date": "2026-09-12", "title": "보고 이후 새 기록", "body": "새 내용"},
    )

    candidate = next(
        item for item in client.get("/api/report-candidates").json()["items"]
        if item["id"] == project["id"]
    )
    assert candidate["unreported_entries"] == 1

    second = client.post(
        f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-09-15"}
    ).json()
    assert "보고 이후 새 기록" in second["body"]
    assert second["frozen"] is False  # 새 보고는 당연히 편집 가능한 상태로 시작한다


def test_several_reports_can_be_stacked_over_time(client):
    """중간 보고 → 완료 보고처럼 여러 번 보고해도 각각 그 시점으로 남는다."""
    project = client.post("/api/projects", json={"title": "여러 번 보고"}).json()
    dates = ["2026-09-08", "2026-09-15", "2026-09-22"]
    for index, report_date in enumerate(dates, start=1):
        client.post(
            f"/api/projects/{project['id']}/entries",
            json={"date": f"2026-09-0{index}", "title": f"{index}차 진행", "body": f"{index}차 내용"},
        )
        report = client.post(
            f"/api/projects/{project['id']}/reports/draft", json={"report_date": report_date}
        ).json()
        client.post(f"/api/reports/{report['id']}/freeze")

    reports = client.get(f"/api/projects/{project['id']}/reports").json()
    assert [item["report_date"] for item in reports] == sorted(dates, reverse=True)
    assert all(item["frozen"] for item in reports)
    # 각 보고는 자기 시점의 진행일지만 담는다.
    assert [item["entry_count"] for item in reports] == [1, 1, 1]


def test_unfreeze_lets_you_correct_a_past_report(client):
    _, _, report = build(client)
    assert client.post(f"/api/reports/{report['id']}/unfreeze").status_code == 200
    assert client.patch(f"/api/reports/{report['id']}", json={"body": "정정한 내용"}).status_code == 200
    assert client.post(f"/api/reports/{report['id']}/freeze").status_code == 200
