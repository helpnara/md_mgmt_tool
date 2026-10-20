"""기록을 지우면 그 기록의 첨부도 함께 보관함으로, 되돌리면 함께 제자리로 (TODO 218).

예전에는 기록(.md)만 보관함으로 가고 첨부는 `assets/` 에 남았다. [정리] 를 눌러야 치워졌고,
기록을 되돌릴 때 첨부를 따로 찾아 되돌려야 본문 링크가 이어졌다.
"""
from __future__ import annotations

from tests.test_attachments import make_png, upload


def setup(client) -> tuple[str, int, dict]:
    project = client.post("/api/projects", json={"title": "첨부 함께 지우기"}).json()
    entry = client.post(
        f"/api/projects/{project['id']}/entries",
        json={"date": "2026-09-03", "title": "측정 기록"},
    ).json()
    saved = upload(client, entry["id"], "그래프.png", make_png()).json()
    client.patch(f"/api/entries/{entry['id']}", json={"body": f"결과\n\n{saved['markdown']}"})
    return project["id"], entry["id"], saved


def project_folder(vault_dir, project_id: str):
    return next((vault_dir / "projects").glob(f"{project_id}-*"))


def test_deleting_an_entry_moves_its_attachments_to_the_trash(client, vault_dir):
    project_id, entry_id, saved = setup(client)
    folder = project_folder(vault_dir, project_id)
    assert (folder / saved["rel_path"]).exists()

    assert client.delete(f"/api/entries/{entry_id}").status_code == 204
    assert not (folder / saved["rel_path"]).exists(), "첨부가 assets/ 에 남았다"
    assert client.get(f"/api/projects/{project_id}/attachments").json()["items"] == []

    # 보관함에는 기록 한 줄 — 첨부는 그 줄에 묶여 보인다
    items = client.get("/api/trash").json()
    assert len(items) == 1
    assert items[0]["kind"] == "entry"
    assert items[0]["attachments"] == ["그래프.png"]


def test_restoring_the_entry_brings_its_attachments_back(client, vault_dir):
    project_id, entry_id, saved = setup(client)
    folder = project_folder(vault_dir, project_id)
    client.delete(f"/api/entries/{entry_id}")
    trash_name = client.get("/api/trash").json()[0]["trash_name"]

    result = client.post(f"/api/trash/{trash_name}/restore").json()
    assert result["attachments_left"] == []
    assert (folder / saved["rel_path"]).exists(), "첨부가 제자리로 안 돌아왔다"
    assert client.get("/api/trash").json() == []

    # 본문 링크가 다시 이어진다 — 고아가 아니다
    items = client.get(f"/api/projects/{project_id}/attachments").json()["items"]
    assert [item["rel_path"] for item in items] == [saved["rel_path"]]
    assert items[0]["orphan"] is False


def test_an_attachment_another_document_links_stays(client, vault_dir):
    """다른 기록이 같은 파일을 링크하면 남긴다 — 옮기면 그쪽 링크가 끊긴다."""
    project_id, entry_id, saved = setup(client)
    client.post(
        f"/api/projects/{project_id}/entries",
        json={"date": "2026-09-04", "title": "다음 기록", "body": f"앞의 그림 다시\n\n{saved['markdown']}"},
    )
    folder = project_folder(vault_dir, project_id)

    client.delete(f"/api/entries/{entry_id}")
    assert (folder / saved["rel_path"]).exists()
    assert client.get("/api/trash").json()[0]["attachments"] == []


def test_an_attachment_the_overview_links_stays(client, vault_dir):
    project_id, entry_id, saved = setup(client)
    client.patch(f"/api/projects/{project_id}", json={"body": f"개요 그림 ![g]({saved['rel_path']})"})
    folder = project_folder(vault_dir, project_id)

    client.delete(f"/api/entries/{entry_id}")
    assert (folder / saved["rel_path"]).exists()


def test_an_unlinked_upload_of_the_entry_goes_too(client, vault_dir):
    """본문에 링크하지 않았어도 이 기록에 올린 파일이면 함께 간다 (첨부 목록에만 있는 자료)."""
    project = client.post("/api/projects", json={"title": "링크 없는 첨부"}).json()
    entry = client.post(
        f"/api/projects/{project['id']}/entries", json={"date": "2026-09-03", "title": "자료만"}
    ).json()
    saved = upload(client, entry["id"], "자료.png", make_png("blue")).json()
    folder = project_folder(vault_dir, project["id"])

    client.delete(f"/api/entries/{entry['id']}")
    assert not (folder / saved["rel_path"]).exists()
    assert client.get("/api/trash").json()[0]["attachments"] == ["자료.png"]


def test_a_child_left_behind_shows_on_its_own_line(client, vault_dir):
    """기록만 돌아가고 첨부가 막혀 남았으면 첨부는 제 줄로 보여 하나씩 되돌릴 수 있다."""
    from app.config import get_settings
    from app.services import trash as trash_service

    project_id, entry_id, saved = setup(client)
    client.delete(f"/api/entries/{entry_id}")
    entry_item = client.get("/api/trash").json()[0]
    child = next(item for item in trash_service._read_manifest() if item.get("parent"))

    # 주인만 손으로 되돌려진 상태를 만든다 — 주인 파일이 보관함에서 사라짐
    (get_settings().trash_dir / entry_item["trash_name"]).unlink()
    items = client.get("/api/trash").json()
    assert [item["trash_name"] for item in items] == [child["trash_name"]]
    assert items[0]["restorable"] is True
    assert client.post(f"/api/trash/{child['trash_name']}/restore").status_code == 200
    assert (project_folder(vault_dir, project_id) / saved["rel_path"]).exists()


def test_a_report_attachment_is_not_touched(client, db):
    """보고 자료(report_id)는 보고의 것 — 기록을 지워도 그대로."""
    from app.services import entries

    project_id, entry_id, _ = setup(client)
    db.execute("PRAGMA foreign_keys = OFF")  # 보고 한 건을 다 만들지 않고 자료 줄만 — 걸러지는지만 본다
    db.execute(
        "INSERT INTO attachment(project_id, entry_id, report_id, rel_path, orig_name) VALUES (?, ?, 1, ?, ?)",
        (project_id, entry_id, "reports/2026-09-05/assets/001-표.xlsx", "표.xlsx"),
    )
    row = db.execute("SELECT * FROM entry WHERE id = ?", (entry_id,)).fetchone()
    names = [attachment["orig_name"] for attachment in entries._owned_attachments(db, row)]
    db.rollback()
    db.execute("PRAGMA foreign_keys = ON")
    assert names == ["그래프.png"]
