from __future__ import annotations

import os


def create_project(client, **kwargs):
    payload = {"title": "리튬전지 수명평가", "status": "in_progress", "group": "차세대전지", "tags": ["수명평가"]}
    payload.update(kwargs)
    response = client.post("/api/projects", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_project_writes_readable_markdown(client, vault_dir):
    project = create_project(client)
    assert project["id"].endswith("-001")

    directory = vault_dir / "projects" / f"{project['id']}-리튬전지-수명평가"
    assert (directory / "index.md").exists()
    assert (directory / "logs").is_dir()
    assert (directory / "assets").is_dir()
    assert (directory / "reports").is_dir()

    raw = (directory / "index.md").read_text(encoding="utf-8")
    assert "title: 리튬전지 수명평가" in raw
    assert "status: in_progress" in raw


def test_project_ids_increment_within_year(client):
    first = create_project(client)
    second = create_project(client, title="차세대 양극재")
    assert int(second["id"].split("-")[1]) == int(first["id"].split("-")[1]) + 1


def test_rejects_unknown_status(client):
    response = client.post("/api/projects", json={"title": "x", "status": "없는상태"})
    assert response.status_code == 400


def test_entry_crud_and_listing(client, vault_dir):
    project = create_project(client)
    created = client.post(
        f"/api/projects/{project['id']}/entries",
        json={"date": "2026-09-03", "title": "1차 측정 결과", "body": "측정 완료", "tags": ["측정"]},
    )
    assert created.status_code == 201, created.text
    entry = created.json()
    assert entry["rel_path"] == "logs/2026-09-03-1차-측정-결과.md"
    assert entry["tags"] == ["측정"]

    listed = client.get(f"/api/projects/{project['id']}/entries").json()
    assert [item["title"] for item in listed] == ["1차 측정 결과"]

    updated = client.patch(f"/api/entries/{entry['id']}", json={"body": "측정 완료. 재현성 확인 필요"})
    assert updated.status_code == 200
    assert "재현성" in client.get(f"/api/entries/{entry['id']}").json()["body"]

    assert client.delete(f"/api/entries/{entry['id']}").status_code == 204
    assert client.get(f"/api/projects/{project['id']}/entries").json() == []
    assert list((vault_dir / ".trash").glob("*.md"))  # 즉시 삭제하지 않고 보관


def test_entries_on_same_day_do_not_collide(client):
    project = create_project(client)
    for _ in range(2):
        client.post(
            f"/api/projects/{project['id']}/entries",
            json={"date": "2026-09-03", "title": "측정"},
        )
    paths = {item["rel_path"] for item in client.get(f"/api/projects/{project['id']}/entries").json()}
    assert paths == {"logs/2026-09-03-측정.md", "logs/2026-09-03-측정-2.md"}


def test_project_updated_at_follows_latest_entry(client):
    project = create_project(client)
    client.post(
        f"/api/projects/{project['id']}/entries",
        json={"date": "2030-01-01", "title": "미래 기록"},
    )
    refreshed = client.get(f"/api/projects/{project['id']}").json()
    assert refreshed["updated_at"].startswith("2030-01-01")


def test_renaming_project_moves_its_folder(client, vault_dir):
    project = create_project(client)
    client.patch(f"/api/projects/{project['id']}", json={"title": "리튬전지 수명평가 2차"})
    names = {path.name for path in (vault_dir / "projects").iterdir()}
    assert names == {f"{project['id']}-리튬전지-수명평가-2차"}


def test_external_edit_is_picked_up_by_reindex(client, vault_dir):
    project = create_project(client)
    logs = vault_dir / "projects" / f"{project['id']}-리튬전지-수명평가" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "2026-08-01-외부작성.md").write_text(
        "---\ndate: 2026-08-01\ntitle: 외부에서 쓴 기록\n---\n\n옵시디언으로 작성함\n",
        encoding="utf-8",
    )

    assert client.post("/api/reindex").json()["indexed"] == 1
    titles = [item["title"] for item in client.get(f"/api/projects/{project['id']}/entries").json()]
    assert titles == ["외부에서 쓴 기록"]


def test_reindex_rebuilds_after_database_is_deleted(client, vault_dir):
    project = create_project(client)
    client.post(f"/api/projects/{project['id']}/entries", json={"title": "기록"})

    from app import deps
    from app.db import connect, init_schema

    deps.teardown()
    (vault_dir / ".index" / "index.sqlite3").unlink()
    conn = connect()
    init_schema(conn)
    deps._conn = conn

    assert client.post("/api/reindex").json()["indexed"] == 1
    assert len(client.get(f"/api/projects/{project['id']}/entries").json()) == 1


def test_archive_moves_project_to_trash(client, vault_dir):
    project = create_project(client)
    assert client.post(f"/api/projects/{project['id']}/archive").status_code == 204
    assert client.get(f"/api/projects/{project['id']}").status_code == 404
    assert list((vault_dir / "projects").iterdir()) == []
    assert list((vault_dir / ".trash").iterdir())


def test_meta_exposes_statuses_and_types_separately(client):
    """상태는 진행 단계만, 과제의 성격은 속성으로 분리한다."""
    meta = client.get("/api/meta").json()
    assert [item["label"] for item in meta["statuses"]] == [
        "예정", "검토중", "진행중", "보류", "완료", "중단",
    ]
    assert [item["label"] for item in meta["types"]] == [
        "스마트과제", "R&D", "투자", "기획보고", "국책과제",
    ]


def test_project_filters(client):
    create_project(client)
    create_project(client, title="양극재 개발", group="소재", status="reviewing", tags=["소재"])

    assert len(client.get("/api/projects", params={"status": "reviewing"}).json()) == 1
    assert len(client.get("/api/projects", params={"group": "차세대전지"}).json()) == 1
    assert len(client.get("/api/projects", params={"tag": "소재"}).json()) == 1
    assert len(client.get("/api/projects").json()) == 2


def test_saving_over_an_external_edit_is_refused(client, vault_dir):
    """옵시디언·탐색기로 고친 내용을 말없이 덮어쓰면 안 된다."""
    project = create_project(client)
    entry = client.post(
        f"/api/projects/{project['id']}/entries", json={"title": "기록", "body": "웹에서 쓴 내용"}
    ).json()
    path = vault_dir / "projects" / f"{project['id']}-리튬전지-수명평가" / entry["rel_path"]
    path.write_text(
        path.read_text(encoding="utf-8").replace("웹에서 쓴 내용", "탐색기에서 고친 내용"),
        encoding="utf-8",
    )
    os.utime(path, (path.stat().st_atime, path.stat().st_mtime + 10))

    blocked = client.patch(f"/api/entries/{entry['id']}", json={"body": "웹에서 덮어쓰기"})
    assert blocked.status_code == 409
    assert "다시 읽기" in blocked.json()["detail"]
    assert "탐색기에서 고친 내용" in path.read_text(encoding="utf-8")

    # 다시 읽은 뒤에는 정상적으로 저장된다.
    client.post("/api/reindex")
    assert client.patch(f"/api/entries/{entry['id']}", json={"body": "이제 저장"}).status_code == 200


def test_project_overview_is_also_protected_from_silent_overwrite(client, vault_dir):
    project = create_project(client)
    path = vault_dir / "projects" / f"{project['id']}-리튬전지-수명평가" / "index.md"
    path.write_text(path.read_text(encoding="utf-8") + "\n외부에서 추가한 줄\n", encoding="utf-8")
    os.utime(path, (path.stat().st_atime, path.stat().st_mtime + 10))

    blocked = client.patch(f"/api/projects/{project['id']}", json={"body": "덮어쓰기"})
    assert blocked.status_code == 409


def test_attachment_upload_does_not_trigger_a_false_conflict(client):
    """도구가 스스로 front matter를 고친 뒤에도 저장이 막히면 안 된다."""
    project = create_project(client)
    entry = client.post(
        f"/api/projects/{project['id']}/entries", json={"date": "2026-09-03", "title": "기록"}
    ).json()
    client.post(
        f"/api/entries/{entry['id']}/attachments",
        files={"file": ("자료.xlsx", b"PK\x03\x04", "application/octet-stream")},
    )
    assert client.patch(f"/api/entries/{entry['id']}", json={"body": "첨부 후 저장"}).status_code == 200
