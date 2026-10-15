from __future__ import annotations

import mimetypes
import re
import sqlite3
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..config import get_settings
from ..deps import get_db, RowId
from ..services import attachments as svc
from ..vault import paths
from ..vault.paths import FileInUseError

router = APIRouter(tags=["attachments"])


def _serialize(row: dict, dir_name: str, doc_dir: str = svc.ENTRY_DOC_DIR) -> dict:
    url = f"/files/{quote(dir_name)}/{quote(row['rel_path'])}"
    image = svc.is_image(row["mime"])
    thumb = False
    if image and row["mime"] != "image/svg+xml":
        # 그림으로 열리는 것에만 썸네일 주소를 준다 (TODO 204 ⑭) — 확장자만 .png 인 파일은 그림이 아니라
        # 파일로 보인다(화면은 is_image 가 거짓이면 파일 아이콘). svg 는 썸네일 없이 원본을 그림으로 보인다.
        try:
            path = paths.safe_join(get_settings().projects_dir / dir_name, row["rel_path"])
        except ValueError:
            path = None
        thumb = path is not None and svc.readable_image(path, row.get("sha256"))
        image = thumb
    return {
        "id": row["id"],
        "entry_id": row["entry_id"],
        "report_id": row["report_id"],
        "rel_path": row["rel_path"],
        "orig_name": row["orig_name"],
        "mime": row["mime"],
        "size_bytes": row["size_bytes"],
        "is_image": image,
        "url": url,
        "thumb_url": f"/api/attachments/{row['id']}/thumb" if thumb else None,
        "preview_url": f"/api/attachments/{row['id']}/preview" if svc.is_spreadsheet(row["mime"]) else None,
        # 링크는 이 첨부를 넣을 문서 위치 기준으로 만든다 (외부 뷰어 호환).
        "markdown": svc.markdown_link(row["rel_path"], row["orig_name"], doc_dir, image),
        "orphan": row.get("orphan", False),
        "deduplicated": row.get("deduplicated", False),
    }


def _dir_name(conn: sqlite3.Connection, project_id: str) -> str:
    row = conn.execute("SELECT dir_name FROM project WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="과제를 찾을 수 없습니다.")
    return row["dir_name"]


@router.post("/api/entries/{entry_id}/attachments", status_code=201)
def upload_to_entry(
    entry_id: RowId, file: UploadFile = File(...), conn: sqlite3.Connection = Depends(get_db)
) -> dict:
    entry = conn.execute("SELECT * FROM entry WHERE id = ?", (entry_id,)).fetchone()
    if entry is None:
        raise HTTPException(status_code=404, detail="진행일지를 찾을 수 없습니다.")
    try:
        saved = svc.save_attachment(
            conn,
            project_id=entry["project_id"],
            filename=file.filename or "attachment",
            source=file.file,
            bucket_rel=f"assets/{entry['date']}",
            doc_dir=svc.ENTRY_DOC_DIR,
            entry_id=entry_id,
            content_type=file.content_type,
        )
    except (FileNotFoundError, PermissionError):
        # 폴더가 밖에서 지워졌거나 잠겨 있다 — main.py 의 공통 처리(409 · 423)로 넘긴다 (TODO 200)
        raise
    except OSError as exc:
        raise HTTPException(status_code=507, detail=f"파일을 저장하지 못했습니다 (저장 공간 · 경로를 확인하세요): {exc}") from exc
    return _serialize(saved, _dir_name(conn, entry["project_id"]))


@router.get("/api/entries/{entry_id}/attachments")
def list_entry_attachments(entry_id: RowId, conn: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    entry = conn.execute("SELECT * FROM entry WHERE id = ?", (entry_id,)).fetchone()
    if entry is None:
        raise HTTPException(status_code=404, detail="진행일지를 찾을 수 없습니다.")
    dir_name = _dir_name(conn, entry["project_id"])
    rows = conn.execute(
        "SELECT * FROM attachment WHERE entry_id = ? ORDER BY rel_path", (entry_id,)
    ).fetchall()
    return [_serialize(dict(row), dir_name) for row in rows]


@router.post("/api/projects/{project_id}/attachments", status_code=201)
def upload_to_project(
    project_id: str, file: UploadFile = File(...), conn: sqlite3.Connection = Depends(get_db)
) -> dict:
    """과제 개요에 직접 붙이는 첨부.

    효과 산출 근거(엑셀·PPT)처럼 특정 진행일지가 아니라 **과제 자체에 딸린 자료**를 위한 것이다.
    진행일지·보고 첨부와 같은 폴더 체계를 쓰되, 날짜가 아니라 `assets/과제` 아래에 모은다.
    """
    dir_name = _dir_name(conn, project_id)  # 없는 과제면 여기서 404
    try:
        saved = svc.save_attachment(
            conn,
            project_id=project_id,
            filename=file.filename or "attachment",
            source=file.file,
            bucket_rel="assets/과제",
            doc_dir=svc.PROJECT_DOC_DIR,
            content_type=file.content_type,
        )
    except (FileNotFoundError, PermissionError):
        # 폴더가 밖에서 지워졌거나 잠겨 있다 — main.py 의 공통 처리(409 · 423)로 넘긴다 (TODO 200)
        raise
    except OSError as exc:
        raise HTTPException(status_code=507, detail=f"파일을 저장하지 못했습니다 (저장 공간 · 경로를 확인하세요): {exc}") from exc
    return _serialize(saved, dir_name, svc.PROJECT_DOC_DIR)


@router.get("/api/projects/{project_id}/attachments")
def list_project_attachments(project_id: str, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    dir_name = _dir_name(conn, project_id)
    # 과제 전체 목록은 개요 문서(과제 폴더) 기준 링크로 보여 준다.
    items = [
        _serialize(row, dir_name, svc.PROJECT_DOC_DIR)
        for row in svc.list_attachments(conn, project_id)
    ]
    return {
        "items": items,
        "total_bytes": sum(item["size_bytes"] or 0 for item in items),
        "orphan_count": sum(1 for item in items if item["orphan"]),
    }


@router.get("/api/attachments/{attachment_id}/preview")
def preview_spreadsheet(attachment_id: RowId, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """엑셀 보고 자료를 브라우저에서 바로 훑어볼 수 있게 표/이미지를 뽑아 준다."""
    try:
        return svc.spreadsheet_preview(conn, attachment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="첨부를 찾을 수 없습니다.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/attachments/{attachment_id}/thumb")
def get_thumbnail(attachment_id: RowId, conn: sqlite3.Connection = Depends(get_db)) -> FileResponse:
    try:
        return FileResponse(svc.thumbnail(conn, attachment_id), media_type="image/jpeg")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="첨부를 찾을 수 없습니다.") from exc
    except svc.UnreadableImage as exc:
        # 열 수 없는 그림 — 500 이 아니라 415 (TODO 204 ⑭)
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/projects/{project_id}/attachments/cleanup")
def cleanup_orphan_attachments(project_id: str, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """본문에서 쓰지 않는 첨부를 보관함으로 (TODO 204 · 197 ③ — [정리]).

    `{"moved": 옮긴 수, "names": [원래 이름, …]}`. 보고 자료는 고아로 치지 않아 옮기지 않는다.
    """
    _dir_name(conn, project_id)  # 없는 과제면 404
    try:
        names = svc.cleanup_orphans(conn, project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="과제를 찾을 수 없습니다.") from exc
    except FileInUseError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc
    return {"moved": len(names), "names": names}


@router.delete("/api/attachments/{attachment_id}", status_code=204)
def delete_attachment(attachment_id: RowId, conn: sqlite3.Connection = Depends(get_db)) -> None:
    try:
        svc.delete_attachment(conn, attachment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="첨부를 찾을 수 없습니다.") from exc
    except FileInUseError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc


@router.get("/files/{dir_name}/{rel_path:path}")
def serve_project_file(
    dir_name: str, rel_path: str, conn: sqlite3.Connection = Depends(get_db)
) -> FileResponse:
    """md 본문의 상대 경로 링크를 그대로 열기 위한 정적 서빙."""
    known = conn.execute("SELECT 1 FROM project WHERE dir_name = ?", (dir_name,)).fetchone()
    if known is None:
        raise HTTPException(status_code=404, detail="과제를 찾을 수 없습니다.")
    try:
        target = paths.safe_join(get_settings().projects_dir / dir_name, rel_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    return file_response(target)


# 같은 주소(origin)에서 열리면 스크립트가 돌 수 있는 종류 (TODO 204 ㉒). `page.html` · `evil.svg` 를 올리면
# 이 도구의 주소에서 그대로 열려 저장형 스크립트가 실행됐다 — 공유 모드면 열람자에게도.
ACTIVE_SUFFIXES = {".html", ".htm", ".xhtml", ".svg", ".svgz", ".xml", ".xht", ".shtml", ".mht", ".mhtml"}
ACTIVE_TYPES = ("text/html", "image/svg+xml", "application/xhtml+xml", "text/xml", "application/xml")


def file_response(target: Path) -> FileResponse:
    """첨부 원본을 보낸다. 스크립트가 돌 수 있는 종류는 **내려받기로만** — 화면 안에서 열지 않는다 (TODO 204 ㉒).

    `Content-Disposition: attachment` 로 브라우저가 열지 않고 저장하게 하고, 그래도 열릴 때를 대비해
    `Content-Security-Policy: sandbox` 로 스크립트를 막는다. `<img src>` 로 넣은 svg 는 그대로 그려진다
    (그림 태그 안의 svg 는 스크립트가 돌지 않는다).
    """
    media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    headers = {"X-Content-Type-Options": "nosniff"}
    if target.suffix.lower() in ACTIVE_SUFFIXES or media_type.split(";")[0].strip().lower() in ACTIVE_TYPES:
        ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "-", target.name).strip("-") or "file"
        headers["Content-Disposition"] = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(target.name)}"
        headers["Content-Security-Policy"] = "sandbox"
    return FileResponse(target, media_type=media_type, headers=headers)
