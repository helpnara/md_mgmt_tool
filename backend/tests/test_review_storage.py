"""전수점검 2026-10-15 — 저장 · 보관함 · 첨부 (TODO 202 · 203 · 204, 197 ③).

재현 스크립트(`docs/review/전수점검-2026-10-15/repro.py` C · D · G · I, `p6_attachments.py`)의 시나리오를
백엔드 시험으로 옮긴 것.
"""
from __future__ import annotations

import io
import json
import zipfile

import pytest
from PIL import Image

from app.services import backup


def png(color: str = "red") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), color).save(buffer, "PNG")
    return buffer.getvalue()


def make_project(client, title="저장 과제"):
    response = client.post("/api/projects", json={"title": title})
    assert response.status_code == 201, response.text
    return client.get(f"/api/projects/{response.json()['id']}").json()  # dir_name 은 상세에 있다


def add_entry(client, project_id, title="기록", date="2026-01-05", body="내용"):
    response = client.post(
        f"/api/projects/{project_id}/entries", json={"title": title, "date": date, "body": body}
    )
    assert response.status_code == 201, response.text
    return response.json()


def upload(client, entry_id, name, data, mime="image/png"):
    return client.post(f"/api/entries/{entry_id}/attachments", files={"file": (name, data, mime)})


# ── 202 백업 ────────────────────────────────────────────────────────────


def test_backup_interrupted_midway_leaves_no_zip_and_stays_due(client, tmp_path, monkeypatch):
    """디스크가 차서 중간에 멈추면 잘린 zip 이 `.zip` 으로 남지 않고, 다음에 다시 한다 (TODO 202 ⑤)."""
    make_project(client)
    target = tmp_path / "백업"
    target.mkdir()
    assert client.put("/api/settings", json={"backup_dir": str(target)}).status_code == 200

    from app.services import export

    def half_then_fail(destination, assets=True):
        with open(destination, "wb") as handle:
            handle.write(b"PK\x03\x04 half written")
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(export, "write_backup_all", half_then_fail)
    response = client.post("/api/settings/backup/run")
    assert response.status_code == 400
    assert "백업을 쓰지 못했습니다" in response.json()["detail"]

    assert list(target.iterdir()) == []  # .zip 도 .part 도 없다
    assert backup.due() is True
    status = client.get("/api/settings/backup/status").json()
    assert status["count"] == 0
    assert status["last"]["ok"] is False


def test_any_exception_in_auto_backup_is_recorded(client, tmp_path, monkeypatch, db):
    """MemoryError 같은 것도 설정 화면에 실패로 남는다 — 루프가 조용히 삼키지 않는다 (TODO 202 ⑬)."""
    make_project(client)
    target = tmp_path / "백업"
    target.mkdir()
    client.put("/api/settings", json={"backup_dir": str(target)})

    from app.services import export

    def boom(destination, assets=True):
        raise MemoryError("too big")

    monkeypatch.setattr(export, "write_backup_all", boom)
    assert backup.maybe_run(db) is None
    last = client.get("/api/settings/backup/status").json()["last"]
    assert last["ok"] is False and "MemoryError" in last["error"]
    assert list(target.iterdir()) == []

    # 루프 바깥(due 판단 등)에서 난 예외도 기록한다
    monkeypatch.setattr(backup, "due", lambda: (_ for _ in ()).throw(RuntimeError("뜻밖")))
    assert backup.maybe_run(db) is None
    assert "RuntimeError" in client.get("/api/settings/backup/status").json()["last"]["error"]


def test_partial_files_are_not_counted_as_backups(client, tmp_path):
    target = tmp_path / "백업"
    target.mkdir()
    client.put("/api/settings", json={"backup_dir": str(target)})
    (target / f"{backup.PREFIX}20260101-0000.zip.part").write_bytes(b"half")
    assert backup.due() is True
    assert client.get("/api/settings/backup/status").json()["count"] == 0

    make_project(client)
    result = client.post("/api/settings/backup/run").json()
    # 지난번 조각은 치워지고 완성본만 남는다
    assert sorted(item.name for item in target.iterdir()) == [result["file"]]
    assert zipfile.is_zipfile(target / result["file"])


def test_backup_skips_temp_files(client, vault_dir):
    project = make_project(client)
    folder = vault_dir / "projects" / project["dir_name"]
    (folder / "tmpabc.tmp").write_text("쓰는 중", encoding="utf-8")
    (folder / "assets").mkdir(exist_ok=True)
    (folder / "assets" / "upload.part").write_bytes(b"half")

    names = zipfile.ZipFile(io.BytesIO(client.get("/api/backup").content)).namelist()
    assert any(name.endswith("index.md") for name in names)
    assert not any(name.endswith((".tmp", ".part")) for name in names)


def test_backup_download_without_assets(client, vault_dir):
    """`GET /api/backup?assets=none` — 문서만, 첨부(assets/) 없이 (TODO 197 ③)."""
    project = make_project(client)
    entry = add_entry(client, project["id"])
    assert upload(client, entry["id"], "그래프.png", png()).status_code == 201

    full = client.get("/api/backup")
    assert full.status_code == 200
    assert any("/assets/" in name for name in zipfile.ZipFile(io.BytesIO(full.content)).namelist())

    slim = client.get("/api/backup?assets=none")
    assert slim.status_code == 200
    assert "첨부제외" in slim.headers["content-disposition"] or "%EC%B2%A8%EB%B6%80" in slim.headers["content-disposition"]
    names = zipfile.ZipFile(io.BytesIO(slim.content)).namelist()
    assert any(name.endswith("index.md") for name in names)
    assert any("/logs/" in name for name in names)
    assert not any("assets/" in name for name in names)

    assert client.get("/api/backup?assets=bogus").status_code == 422


def test_auto_backup_honours_skip_assets_setting(client, tmp_path, monkeypatch):
    project = make_project(client)
    entry = add_entry(client, project["id"])
    upload(client, entry["id"], "그래프.png", png())
    target = tmp_path / "백업"
    target.mkdir()
    client.put("/api/settings", json={"backup_dir": str(target)})

    from app.services import settings as settings_service

    original = settings_service.load
    monkeypatch.setattr(settings_service, "load", lambda: {**original(), "backup_skip_assets": True})

    result = client.post("/api/settings/backup/run").json()
    assert result["skip_assets"] is True
    names = zipfile.ZipFile(target / result["file"]).namelist()
    assert any(name.endswith("index.md") for name in names)
    assert not any("assets/" in name for name in names)
    assert client.get("/api/settings/backup/status").json()["skip_assets"] is True


# ── 202 manifest · 203 보관함 복구 ──────────────────────────────────────


def test_manifest_rewrite_is_atomic(client, vault_dir, monkeypatch):
    """다시 쓰다 실패해도 보관함 기록이 통째로 사라지지 않는다 (TODO 202 ㉔)."""
    from app.services import trash

    project = make_project(client)
    entry = add_entry(client, project["id"])
    assert client.delete(f"/api/entries/{entry['id']}").status_code == 204
    manifest = vault_dir / ".trash" / "manifest.jsonl"
    before = manifest.read_text(encoding="utf-8")

    def fail(*args, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(trash.os, "replace", fail)
    with pytest.raises(OSError):
        trash.rewrite_origins({project["dir_name"]: "2026-001-새-이름"})
    assert manifest.read_text(encoding="utf-8") == before
    assert not [p for p in manifest.parent.iterdir() if p.name.endswith(".tmp")]
    monkeypatch.undo()

    assert trash.rewrite_origins({project["dir_name"]: "2026-001-새-이름"}) == 1
    assert "projects/2026-001-새-이름/logs/" in manifest.read_text(encoding="utf-8")


def test_rewrite_origins_handles_intakes_and_prefix_form(client, vault_dir):
    from app.services import trash

    vault_dir.joinpath(".trash").mkdir(exist_ok=True)
    lines = [
        {"trash_name": "a", "kind": "intake_log", "origin": "intakes/R2026-001-옛/logs/x.md", "label": "a"},
        {"trash_name": "b", "kind": "entry", "origin": "projects/2026-001-옛/logs/y.md", "label": "b"},
    ]
    (vault_dir / ".trash" / "manifest.jsonl").write_text(
        "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines), encoding="utf-8"
    )
    assert trash.rewrite_origins("intakes/R2026-001-옛", "intakes/R2026-001-새") == 1
    assert trash.rewrite_origins({"2026-001-옛": "2026-001-새"}) == 1
    origins = [json.loads(line)["origin"] for line in (vault_dir / ".trash" / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    assert origins == ["intakes/R2026-001-새/logs/x.md", "projects/2026-001-새/logs/y.md"]


def test_restore_after_project_title_change_lands_in_current_folder(client, vault_dir):
    """기록 삭제 → 과제 제목 수정 → 복구 — 지금 폴더로 돌아오고 유령 폴더가 없다 (TODO 203, repro C)."""
    project = make_project(client, "첫 제목")
    entry = add_entry(client, project["id"])
    client.delete(f"/api/entries/{entry['id']}")
    assert client.patch(f"/api/projects/{project['id']}", json={"title": "둘째 제목"}).status_code == 200

    name = client.get("/api/trash").json()[0]["trash_name"]
    response = client.post(f"/api/trash/{name}/restore")
    assert response.status_code == 200, response.text
    assert response.json()["restored_to"].startswith(f"projects/{project['id']}-둘째-제목/logs/")

    assert len(client.get(f"/api/projects/{project['id']}/entries").json()) == 1
    assert sorted(p.name for p in (vault_dir / "projects").iterdir()) == [f"{project['id']}-둘째-제목"]


def test_restore_into_renamed_intake_folder(client, vault_dir):
    intake = client.post("/api/intakes", json={"title": "요청"}).json()
    uploaded = client.post(
        f"/api/intakes/{intake['id']}/attachments", files={"file": ("자료.txt", b"x", "text/plain")}
    )
    assert uploaded.status_code == 201, uploaded.text
    rel_path = uploaded.json()["rel_path"] if "rel_path" in uploaded.json() else None
    if rel_path is None:
        detail = client.get(f"/api/intakes/{intake['id']}").json()
        rel_path = detail["attachments"][0]["rel_path"]
    assert client.delete(f"/api/intakes/{intake['id']}/attachments", params={"path": rel_path}).status_code == 204

    # 접수 폴더 이름이 바뀌었다(제목 변경 · 탐색기) — 재색인 뒤 복구
    old = vault_dir / "intakes" / intake["dir_name"]
    new = old.with_name(f"{intake['id']}-바뀐-요청")
    old.rename(new)
    client.post("/api/reindex")

    name = client.get("/api/trash").json()[0]["trash_name"]
    response = client.post(f"/api/trash/{name}/restore")
    assert response.status_code == 200, response.text
    assert response.json()["restored_to"].startswith(f"intakes/{new.name}/")
    assert not old.exists()


def test_restore_when_project_is_gone_keeps_old_behaviour(client, vault_dir):
    project = make_project(client, "사라질 과제")
    entry = add_entry(client, project["id"])
    client.delete(f"/api/entries/{entry['id']}")
    entry_trash = client.get("/api/trash").json()[0]["trash_name"]
    assert client.post(f"/api/projects/{project['id']}/archive").status_code == 204

    response = client.post(f"/api/trash/{entry_trash}/restore")
    assert response.status_code == 200, response.text
    assert response.json()["restored_to"].startswith(f"projects/{project['dir_name']}/logs/")


# ── 204 첨부 ────────────────────────────────────────────────────────────


def test_fake_png_gets_no_thumbnail_and_thumb_is_415(client):
    """확장자만 .png · 0바이트 — 목록이 썸네일 주소를 주지 않고, 직접 불러도 500 이 아니다 (TODO 204 ⑭)."""
    project = make_project(client)
    entry = add_entry(client, project["id"])
    for name, data in (("photo.png", b"not really a png"), ("zero.png", b""), ("bad.png", b"\x89PNG not" * 10)):
        response = upload(client, entry["id"], name, data)
        assert response.status_code == 201, response.text
        saved = response.json()
        assert saved["thumb_url"] is None
        assert saved["is_image"] is False
        assert not saved["markdown"].startswith("!")
        thumb = client.get(f"/api/attachments/{saved['id']}/thumb")
        assert thumb.status_code == 415
        assert "그림" in thumb.json()["detail"]

    real = upload(client, entry["id"], "real.png", png()).json()
    assert real["is_image"] is True and real["thumb_url"]
    assert client.get(real["thumb_url"]).status_code == 200


def test_truncated_png_thumbnail_is_415_and_leaves_no_temp(client, vault_dir):
    project = make_project(client)
    entry = add_entry(client, project["id"])
    data = png()
    saved = upload(client, entry["id"], "cut.png", data[: len(data) // 2]).json()
    response = client.get(f"/api/attachments/{saved['id']}/thumb")
    assert response.status_code in (200, 415)
    thumbs = vault_dir / ".index" / "thumbs"
    assert not [p for p in thumbs.iterdir() if p.suffix == ".tmp"]


def test_same_file_to_second_entry_is_linked_to_that_entry(client, vault_dir):
    """같은 과제의 다른 진행일지에 같은 파일 — 그 일지의 첨부 목록과 meta 에 보인다 (TODO 204 ⑮, repro I)."""
    project = make_project(client)
    first = add_entry(client, project["id"], "하나", "2026-01-05")
    second = add_entry(client, project["id"], "둘", "2026-01-06")
    upload(client, first["id"], "doc.txt", b"same content", "text/plain")
    response = upload(client, second["id"], "doc.txt", b"same content", "text/plain")
    assert response.status_code == 201
    assert response.json()["entry_id"] == second["id"]

    listed = client.get(f"/api/entries/{second['id']}/attachments").json()
    assert [item["orig_name"] for item in listed] == ["doc.txt"]
    assert len(client.get(f"/api/entries/{first['id']}/attachments").json()) == 1

    from app.vault import markdown as md

    path = next((vault_dir / "projects" / project["dir_name"] / "logs").glob("*둘.md"))
    assert md.load(path).meta.get("attachments") == [listed[0]["rel_path"]]

    # 같은 일지에 다시 올리면 여전히 합친다
    again = upload(client, second["id"], "doc.txt", b"same content", "text/plain").json()
    assert again["deduplicated"] is True and again["id"] == listed[0]["id"]


@pytest.mark.parametrize(
    ("name", "data", "mime"),
    [
        ("page.html", b"<script>alert(1)</script>", "text/html"),
        ("evil.svg", b"<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>", "image/svg+xml"),
        ("data.xml", b"<x/>", "application/xml"),
    ],
)
def test_active_content_is_served_as_download(client, name, data, mime):
    """html · svg 는 같은 주소에서 열리지 않고 내려받기로 (TODO 204 ㉒)."""
    project = make_project(client)
    entry = add_entry(client, project["id"])
    saved = upload(client, entry["id"], name, data, mime).json()
    response = client.get(saved["url"])
    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith("attachment")
    assert response.headers.get("content-security-policy") == "sandbox"
    assert response.headers.get("x-content-type-options") == "nosniff"


def test_plain_image_is_still_served_inline(client):
    project = make_project(client)
    entry = add_entry(client, project["id"])
    saved = upload(client, entry["id"], "그래프.png", png()).json()
    response = client.get(saved["url"])
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert "content-disposition" not in response.headers


def test_cleanup_moves_orphans_to_trash(client, vault_dir):
    """[정리] — 본문에서 쓰지 않는 첨부를 보관함으로, 쓰는 것과 보고 자료는 남긴다 (TODO 204 · 197 ③)."""
    project = make_project(client)
    entry = add_entry(client, project["id"])
    used = upload(client, entry["id"], "쓰는그림.png", png("blue")).json()
    upload(client, entry["id"], "안쓰는그림.png", png("green"))
    upload(client, entry["id"], "메모.txt", b"memo", "text/plain")
    client.patch(f"/api/entries/{entry['id']}", json={"body": f"본문 {used['markdown']}"})

    report = client.post(
        f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-01-10"}
    ).json()
    material = client.post(
        f"/api/reports/{report['id']}/attachments", files={"file": ("보고자료.xlsx", b"PK\x03\x04", "application/octet-stream")}
    )
    assert material.status_code == 201, material.text

    summary = client.get(f"/api/projects/{project['id']}/attachments").json()
    assert summary["orphan_count"] == 2  # 보고 자료는 고아가 아니다

    response = client.post(f"/api/projects/{project['id']}/attachments/cleanup")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["moved"] == 2
    assert sorted(body["names"]) == sorted(["안쓰는그림.png", "메모.txt"])

    left = sorted(item["orig_name"] for item in client.get(f"/api/projects/{project['id']}/attachments").json()["items"])
    assert left == sorted(["쓰는그림.png", "보고자료.xlsx"])
    trash_labels = {item["label"] for item in client.get("/api/trash").json() if item["kind"] == "attachment"}
    assert {"안쓰는그림.png", "메모.txt"} <= trash_labels

    again = client.post(f"/api/projects/{project['id']}/attachments/cleanup").json()
    assert again == {"moved": 0, "names": []}
    assert client.post("/api/projects/2099-999/attachments/cleanup").status_code == 404


def test_health_reports_total_attachment_usage(client):
    health = client.get("/api/health").json()
    assert health["attachments_total_bytes"] == 0 and health["attachments_count"] == 0

    project = make_project(client)
    entry = add_entry(client, project["id"])
    upload(client, entry["id"], "a.txt", b"12345", "text/plain")
    intake = client.post("/api/intakes", json={"title": "요청"}).json()
    client.post(f"/api/intakes/{intake['id']}/attachments", files={"file": ("b.txt", b"123", "text/plain")})

    health = client.get("/api/health").json()
    assert health["attachments_total_bytes"] == 8
    assert health["attachments_count"] == 2


def test_attachments_can_be_deleted_before_their_entry(client):
    """화면이 첨부를 먼저 지우고 진행일지를 지운다 (TODO 213) — 둘 다 된다."""
    project = make_project(client)
    entry = add_entry(client, project["id"])
    first = upload(client, entry["id"], "a.png", png("red")).json()
    second = upload(client, entry["id"], "b.txt", b"b", "text/plain").json()
    assert client.delete(f"/api/attachments/{first['id']}").status_code == 204
    assert client.delete(f"/api/attachments/{second['id']}").status_code == 204
    assert client.delete(f"/api/entries/{entry['id']}").status_code == 204
    assert client.get(f"/api/projects/{project['id']}/attachments").json()["items"] == []


def test_folder_without_index_md_is_reported(client, vault_dir):
    """TODO 203 — index.md 없는 과제 폴더는 조용히 넘기지 않고 알린다 (빈 폴더 · 파일 든 폴더)."""
    empty = vault_dir / "projects" / "2026-099-빈-폴더"
    (empty / "logs").mkdir(parents=True)
    stray = vault_dir / "projects" / "2026-098-옛-폴더" / "logs"
    stray.mkdir(parents=True)
    (stray / "2026-01-05-기록.md").write_text("---\ndate: 2026-01-05\n---\n본문\n", encoding="utf-8")
    problems = {item["path"]: item["reason"] for item in client.post("/api/reindex").json()["problems"]}
    assert "지워도 됩니다" in problems["projects/2026-099-빈-폴더"]
    assert "옮겨 주세요" in problems["projects/2026-098-옛-폴더"]
