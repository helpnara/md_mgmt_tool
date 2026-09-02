from __future__ import annotations

import sqlite3
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..config import get_settings
from ..deps import get_db
from ..services import attachments as svc
from ..vault import paths
from ..vault.paths import FileInUseError

router = APIRouter(tags=["attachments"])


def _serialize(row: dict, dir_name: str, doc_dir: str = svc.ENTRY_DOC_DIR) -> dict:
    url = f"/files/{quote(dir_name)}/{quote(row['rel_path'])}"
    image = svc.is_image(row["mime"])
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
        "thumb_url": f"/api/attachments/{row['id']}/thumb" if image else None,
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
    entry_id: int, file: UploadFile = File(...), conn: sqlite3.Connection = Depends(get_db)
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
    except OSError as exc:
        raise HTTPException(status_code=507, detail=str(exc)) from exc
    return _serialize(saved, _dir_name(conn, entry["project_id"]))


@router.get("/api/entries/{entry_id}/attachments")
def list_entry_attachments(entry_id: int, conn: sqlite3.Connection = Depends(get_db)) -> list[dict]:
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
    except OSError as exc:
        raise HTTPException(status_code=507, detail=str(exc)) from exc
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
def preview_spreadsheet(attachment_id: int, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """엑셀 보고 자료를 브라우저에서 바로 훑어볼 수 있게 표/이미지를 뽑아 준다."""
    try:
        return svc.spreadsheet_preview(conn, attachment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="첨부를 찾을 수 없습니다.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/attachments/{attachment_id}/thumb")
def get_thumbnail(attachment_id: int, conn: sqlite3.Connection = Depends(get_db)) -> FileResponse:
    try:
        return FileResponse(svc.thumbnail(conn, attachment_id), media_type="image/jpeg")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="첨부를 찾을 수 없습니다.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/attachments/{attachment_id}", status_code=204)
def delete_attachment(attachment_id: int, conn: sqlite3.Connection = Depends(get_db)) -> None:
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
    return FileResponse(target)
