"""날짜는 파일명과 폴더명이 되므로 검증 없이 받으면 안 된다."""
from __future__ import annotations

from pathlib import Path


def make_project(client):
    return client.post("/api/projects", json={"title": "날짜 검증"}).json()


def test_path_separators_in_date_are_rejected(client, vault_dir):
    project = make_project(client)
    for bad in ["2026/09/03", "../../탈출", "..\\..\\탈출"]:
        response = client.post(
            f"/api/projects/{project['id']}/entries", json={"date": bad, "title": "테스트"}
        )
        assert response.status_code == 400, f"{bad} → {response.status_code}"

    # 과제 폴더 밖에 아무것도 만들어지지 않아야 한다.
    stray = [path for path in Path(vault_dir).rglob("*.md") if "탈출" in path.name]
    assert stray == []
    assert list((vault_dir / "projects").glob("*.md")) == []


def test_impossible_dates_are_rejected(client):
    project = make_project(client)
    for bad in ["2026-13-99", "2026-02-30", "그냥 글자"]:
        assert (
            client.post(
                f"/api/projects/{project['id']}/entries", json={"date": bad, "title": "테스트"}
            ).status_code
            == 400
        )


def test_empty_date_falls_back_to_today(client):
    from datetime import date

    project = make_project(client)
    entry = client.post(
        f"/api/projects/{project['id']}/entries", json={"date": "", "title": "오늘"}
    ).json()
    assert entry["date"] == date.today().isoformat()


def test_changing_an_entry_date_is_validated_too(client):
    project = make_project(client)
    entry = client.post(
        f"/api/projects/{project['id']}/entries", json={"date": "2026-09-03", "title": "기록"}
    ).json()
    assert client.patch(f"/api/entries/{entry['id']}", json={"date": "../탈출"}).status_code == 400
    assert client.get(f"/api/entries/{entry['id']}").json()["date"] == "2026-09-03"


def test_report_date_is_validated(client, vault_dir):
    project = make_project(client)
    response = client.post(
        f"/api/projects/{project['id']}/reports/draft", json={"report_date": "../../보고탈출"}
    )
    assert response.status_code == 400
    assert not any("보고탈출" in path.name for path in Path(vault_dir).rglob("*"))
