from __future__ import annotations

import io

from PIL import Image


def make_png(color: str = "red", size: tuple[int, int] = (900, 600)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, "PNG")
    return buffer.getvalue()


def setup_entry(client) -> tuple[str, int]:
    project = client.post("/api/projects", json={"title": "리튬전지 수명평가"}).json()
    entry = client.post(
        f"/api/projects/{project['id']}/entries",
        json={"date": "2026-09-03", "title": "1차 측정"},
    ).json()
    return project["id"], entry["id"]


def upload(client, entry_id: int, name: str, data: bytes, mime: str = "image/png"):
    return client.post(
        f"/api/entries/{entry_id}/attachments", files={"file": (name, data, mime)}
    )


def test_upload_saves_relative_path_next_to_the_entry(client, vault_dir):
    project_id, entry_id = setup_entry(client)
    response = upload(client, entry_id, "측정그래프.png", make_png())
    assert response.status_code == 201, response.text
    saved = response.json()

    assert saved["rel_path"] == "assets/2026-09-03/001-측정그래프.png"
    # 진행일지는 logs/ 안에 있으므로 링크는 ../ 로 시작해야 외부 뷰어에서도 열린다.
    assert saved["markdown"] == "![측정그래프.png](../assets/2026-09-03/001-측정그래프.png)"
    assert saved["is_image"] is True
    assert (vault_dir / "projects" / f"{project_id}-리튬전지-수명평가" / saved["rel_path"]).exists()


def test_sequence_prefix_avoids_overwriting_same_name(client):
    _, entry_id = setup_entry(client)
    first = upload(client, entry_id, "표.png", make_png("red")).json()
    second = upload(client, entry_id, "표.png", make_png("blue")).json()
    assert first["rel_path"] == "assets/2026-09-03/001-표.png"
    assert second["rel_path"] == "assets/2026-09-03/002-표.png"


def test_identical_file_is_stored_once(client):
    _, entry_id = setup_entry(client)
    data = make_png("green")
    first = upload(client, entry_id, "동일.png", data).json()
    second = upload(client, entry_id, "동일.png", data).json()
    assert second["deduplicated"] is True
    assert second["rel_path"] == first["rel_path"]


def test_filename_cannot_escape_the_project_folder(client, vault_dir):
    _, entry_id = setup_entry(client)
    saved = upload(client, entry_id, "../../탈출.png", make_png()).json()
    assert saved["rel_path"] == "assets/2026-09-03/001-탈출.png"
    assert not (vault_dir.parent / "탈출.png").exists()


def test_non_image_attachment_gets_link_markdown(client):
    _, entry_id = setup_entry(client)
    saved = upload(
        client, entry_id, "원시데이터.xlsx", b"PK\x03\x04fake",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ).json()
    assert saved["is_image"] is False
    assert saved["markdown"] == "[원시데이터.xlsx](../assets/2026-09-03/001-원시데이터.xlsx)"
    assert saved["thumb_url"] is None


def test_file_is_served_by_relative_path(client):
    project_id, entry_id = setup_entry(client)
    saved = upload(client, entry_id, "그래프.png", make_png()).json()
    response = client.get(saved["url"])
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"

    thumb = client.get(saved["thumb_url"])
    assert thumb.status_code == 200
    with Image.open(io.BytesIO(thumb.content)) as image:
        assert max(image.size) <= 480


def test_serving_rejects_path_traversal(client):
    """클라이언트가 정규화하지 못하도록 인코딩된 상위 경로로 시도한다."""
    project_id, entry_id = setup_entry(client)
    upload(client, entry_id, "그래프.png", make_png())
    dir_name = client.get(f"/api/projects/{project_id}").json()["dir_name"]

    escaped = "%2e%2e%2f" * 6 + "etc%2fpasswd"
    for url in (f"/files/{dir_name}/{escaped}", f"/files/{escaped}", f"/{escaped}"):
        response = client.get(url)
        assert b"root:" not in response.content, url


def test_orphan_attachments_are_flagged_not_deleted(client):
    project_id, entry_id = setup_entry(client)
    linked = upload(client, entry_id, "쓰는이미지.png", make_png("red")).json()
    upload(client, entry_id, "안쓰는이미지.png", make_png("blue"))
    client.patch(f"/api/entries/{entry_id}", json={"body": f"결과\n\n{linked['markdown']}"})

    summary = client.get(f"/api/projects/{project_id}/attachments").json()
    assert summary["orphan_count"] == 1
    assert summary["total_bytes"] > 0
    orphans = [item["orig_name"] for item in summary["items"] if item["orphan"]]
    assert orphans == ["안쓰는이미지.png"]


def test_delete_moves_attachment_to_trash(client, vault_dir):
    _, entry_id = setup_entry(client)
    saved = upload(client, entry_id, "삭제대상.png", make_png()).json()
    assert client.delete(f"/api/attachments/{saved['id']}").status_code == 204
    assert client.get(f"/api/entries/{entry_id}/attachments").json() == []
    assert list((vault_dir / ".trash").glob("*삭제대상.png"))


def test_externally_added_files_appear_after_reindex(client, vault_dir):
    project_id, entry_id = setup_entry(client)
    assets = vault_dir / "projects" / f"{project_id}-리튬전지-수명평가" / "assets" / "2026-09-03"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "001-외부복사.png").write_bytes(make_png("purple"))

    client.post("/api/reindex")
    names = [item["orig_name"] for item in client.get(f"/api/projects/{project_id}/attachments").json()["items"]]
    assert names == ["외부복사.png"]


def test_entry_frontmatter_lists_attachments(client, vault_dir):
    """본문에서 참조하지 않아도 md 파일만 보고 첨부를 알 수 있어야 한다."""
    project_id, entry_id = setup_entry(client)
    upload(client, entry_id, "그래프.png", make_png())
    upload(client, entry_id, "원시.xlsx", b"PK\x03\x04fake", "application/octet-stream")

    path = (
        vault_dir / "projects" / f"{project_id}-리튬전지-수명평가" / "logs" / "2026-09-03-1차-측정.md"
    )
    raw = path.read_text(encoding="utf-8")
    assert "- assets/2026-09-03/001-그래프.png" in raw
    assert "- assets/2026-09-03/002-원시.xlsx" in raw

    saved = client.get(f"/api/entries/{entry_id}/attachments").json()
    client.delete(f"/api/attachments/{saved[0]['id']}")
    assert "001-그래프.png" not in path.read_text(encoding="utf-8")
