"""이름이 바뀌면 폴더·파일도 따라가야 나중에 탐색기에서 찾기 쉽다."""
from __future__ import annotations


def make_project(client, title="리튬전지 수명평가"):
    return client.post("/api/projects", json={"title": title}).json()


def test_project_rename_moves_the_folder_with_its_contents(client, vault_dir):
    project = make_project(client)
    entry = client.post(
        f"/api/projects/{project['id']}/entries", json={"date": "2026-09-03", "title": "기록"}
    ).json()
    client.post(
        f"/api/entries/{entry['id']}/attachments",
        files={"file": ("자료.xlsx", b"PK\x03\x04", "application/octet-stream")},
    )

    client.patch(f"/api/projects/{project['id']}", json={"title": "리튬전지 수명평가 2차"})

    folders = sorted(path.name for path in (vault_dir / "projects").iterdir())
    assert folders == [f"{project['id']}-리튬전지-수명평가-2차"]

    moved = vault_dir / "projects" / folders[0]
    assert (moved / "logs" / "2026-09-03-기록.md").exists()
    assert (moved / "assets" / "2026-09-03" / "001-자료.xlsx").exists()
    assert len(client.get(f"/api/projects/{project['id']}/entries").json()) == 1


def test_entry_rename_follows_title_and_date(client, vault_dir):
    project = make_project(client)
    entry = client.post(
        f"/api/projects/{project['id']}/entries", json={"date": "2026-09-03", "title": "원래 제목"}
    ).json()
    logs = vault_dir / "projects" / f"{project['id']}-리튬전지-수명평가" / "logs"
    assert (logs / "2026-09-03-원래-제목.md").exists()

    client.patch(f"/api/entries/{entry['id']}", json={"title": "고친 제목"})
    assert (logs / "2026-09-03-고친-제목.md").exists()
    assert not (logs / "2026-09-03-원래-제목.md").exists()

    client.patch(f"/api/entries/{entry['id']}", json={"date": "2026-09-20"})
    assert (logs / "2026-09-20-고친-제목.md").exists()
    assert sorted(path.name for path in logs.iterdir()) == ["2026-09-20-고친-제목.md"]

    # 같은 기록이 계속 열려야 한다 (id 유지).
    assert client.get(f"/api/entries/{entry['id']}").json()["rel_path"] == "logs/2026-09-20-고친-제목.md"


def test_entry_rename_does_not_collide_with_an_existing_file(client, vault_dir):
    project = make_project(client)
    keep = client.post(
        f"/api/projects/{project['id']}/entries", json={"date": "2026-09-03", "title": "측정"}
    ).json()
    other = client.post(
        f"/api/projects/{project['id']}/entries", json={"date": "2026-09-03", "title": "분석"}
    ).json()

    client.patch(f"/api/entries/{other['id']}", json={"title": "측정"})
    logs = vault_dir / "projects" / f"{project['id']}-리튬전지-수명평가" / "logs"
    names = sorted(path.name for path in logs.iterdir())
    assert names == ["2026-09-03-측정-2.md", "2026-09-03-측정.md"]
    assert client.get(f"/api/entries/{keep['id']}").json()["rel_path"] == "logs/2026-09-03-측정.md"


def test_renaming_a_reported_entry_keeps_it_out_of_the_next_draft(client):
    """이름을 바꿨다고 이미 보고한 내용이 미보고로 되살아나면 안 된다."""
    project = make_project(client)
    entry = client.post(
        f"/api/projects/{project['id']}/entries", json={"date": "2026-09-03", "title": "보고한 기록"}
    ).json()
    report = client.post(
        f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-09-08"}
    ).json()
    client.post(f"/api/reports/{report['id']}/freeze")

    client.patch(f"/api/entries/{entry['id']}", json={"title": "이름만 고친 기록"})

    candidate = next(
        item for item in client.get("/api/report-candidates").json()["items"]
        if item["id"] == project["id"]
    )
    assert candidate["unreported_entries"] == 0

    second = client.post(
        f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-09-15"}
    ).json()
    assert "이름만 고친 기록" not in second["body"]


def test_attachments_stay_valid_after_an_entry_rename(client, vault_dir):
    project = make_project(client)
    entry = client.post(
        f"/api/projects/{project['id']}/entries", json={"date": "2026-09-03", "title": "첨부 기록"}
    ).json()
    saved = client.post(
        f"/api/entries/{entry['id']}/attachments",
        files={"file": ("그래프.png", b"\x89PNG\r\n\x1a\n", "image/png")},
    ).json()
    client.patch(f"/api/entries/{entry['id']}", json={"body": f"결과\n\n{saved['markdown']}"})

    client.patch(f"/api/entries/{entry['id']}", json={"title": "이름 바꾼 기록"})

    # 첨부는 제자리에 있고 링크도 그대로 유효하다 (경로가 날짜 기준이라 이름과 무관).
    directory = vault_dir / "projects" / f"{project['id']}-리튬전지-수명평가"
    assert (directory / "assets" / "2026-09-03" / "001-그래프.png").exists()
    summary = client.get(f"/api/projects/{project['id']}/attachments").json()
    assert summary["orphan_count"] == 0
