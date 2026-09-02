from __future__ import annotations

import sqlite3
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from ..deps import get_db
from ..vault.markdown import ExternalChangeError
from ..services import attachments as attach_svc
from ..services import reports as svc
from ..vault import paths

router = APIRouter(tags=["reports"])


class ReportCreate(BaseModel):
    report_date: str | None = None
    audience: str | None = None


class ReportUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    audience: str | None = None  # 피보고자 또는 회의체명

    def changes(self) -> dict:
        return {k: v for k, v in self.model_dump().items() if v is not None}


def _serialize(conn: sqlite3.Connection, row: sqlite3.Row, with_body: bool = True) -> dict:
    data = {
        "id": row["id"],
        "project_id": row["project_id"],
        "report_date": row["report_date"],
        "title": row["title"],
        "author": row["author"],
        "audience": row["audience"],
        "rel_path": row["rel_path"],
        "doc_dir": svc.report_doc_dir(row["rel_path"]),
        "covers_from": row["covers_from"],
        "covers_to": row["covers_to"],
        "frozen_at": row["frozen_at"],
        "frozen": bool(row["frozen_at"]),
        "entry_count": conn.execute(
            "SELECT COUNT(*) AS n FROM report_entry WHERE report_id = ?", (row["id"],)
        ).fetchone()["n"],
    }
    if with_body:
        data["body"] = row["body"]
    return data


@router.get("/api/projects/{project_id}/reports")
def list_reports(project_id: str, conn: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM report WHERE project_id = ? ORDER BY report_date DESC", (project_id,)
    ).fetchall()
    return [_serialize(conn, row) for row in rows]


@router.post("/api/projects/{project_id}/reports/draft", status_code=201)
def create_draft(
    project_id: str, payload: ReportCreate, conn: sqlite3.Connection = Depends(get_db)
) -> dict:
    try:
        report_id = svc.create_draft(conn, project_id, payload.report_date, audience=payload.audience)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="과제를 찾을 수 없습니다.") from exc
    except paths.InvalidDateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _serialize(conn, svc.report_row(conn, report_id))


@router.get("/api/reports/{report_id}")
def get_report(report_id: int, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    try:
        return _serialize(conn, svc.report_row(conn, report_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="보고 문서를 찾을 수 없습니다.") from exc


@router.patch("/api/reports/{report_id}")
def update_report(
    report_id: int, payload: ReportUpdate, conn: sqlite3.Connection = Depends(get_db)
) -> dict:
    try:
        svc.update_report(conn, report_id, payload.changes())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="보고 문서를 찾을 수 없습니다.") from exc
    except (PermissionError, ExternalChangeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _serialize(conn, svc.report_row(conn, report_id))


@router.post("/api/reports/{report_id}/freeze")
def freeze_report(report_id: int, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    try:
        svc.freeze_report(conn, report_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="보고 문서를 찾을 수 없습니다.") from exc
    return _serialize(conn, svc.report_row(conn, report_id))


@router.post("/api/reports/{report_id}/unfreeze")
def unfreeze_report(report_id: int, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    try:
        svc.unfreeze_report(conn, report_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="보고 문서를 찾을 수 없습니다.") from exc
    return _serialize(conn, svc.report_row(conn, report_id))


@router.delete("/api/reports/{report_id}", status_code=204)
def delete_report(report_id: int, conn: sqlite3.Connection = Depends(get_db)) -> None:
    try:
        svc.delete_report(conn, report_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="보고 문서를 찾을 수 없습니다.") from exc
    except paths.FileInUseError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc


@router.get("/api/reports/{report_id}/attachments")
def list_report_attachments(report_id: int, conn: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    from .attachments import _serialize as serialize_attachment

    try:
        row = svc.report_row(conn, report_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="보고 문서를 찾을 수 없습니다.") from exc
    dir_name = conn.execute(
        "SELECT dir_name FROM project WHERE id = ?", (row["project_id"],)
    ).fetchone()["dir_name"]
    doc_dir = svc.report_doc_dir(row["rel_path"])
    rows = conn.execute(
        "SELECT * FROM attachment WHERE report_id = ? ORDER BY rel_path", (report_id,)
    ).fetchall()
    return [serialize_attachment(dict(item), dir_name, doc_dir) for item in rows]


@router.post("/api/reports/{report_id}/attachments", status_code=201)
def upload_report_attachment(
    report_id: int, file: UploadFile = File(...), conn: sqlite3.Connection = Depends(get_db)
) -> dict:
    from .attachments import _serialize as serialize_attachment

    try:
        row = svc.report_row(conn, report_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="보고 문서를 찾을 수 없습니다.") from exc
    if row["frozen_at"]:
        raise HTTPException(status_code=409, detail="확정된 보고에는 자료를 추가할 수 없습니다.")

    doc_dir = svc.report_doc_dir(row["rel_path"])
    try:
        saved = attach_svc.save_attachment(
            conn,
            project_id=row["project_id"],
            filename=file.filename or "attachment",
            source=file.file,
            bucket_rel=f"{doc_dir}/assets",
            doc_dir=doc_dir,
            report_id=report_id,
            content_type=file.content_type,
        )
    except OSError as exc:
        raise HTTPException(status_code=507, detail=str(exc)) from exc

    dir_name = conn.execute(
        "SELECT dir_name FROM project WHERE id = ?", (row["project_id"],)
    ).fetchone()["dir_name"]
    return serialize_attachment(saved, dir_name, doc_dir)


@router.get("/api/report-candidates")
def report_candidates(
    include_inactive: bool = False, conn: sqlite3.Connection = Depends(get_db)
) -> dict:
    from ..config import get_settings

    return {
        "cycle_days": get_settings().report_cycle_days,
        "default_report_date": svc.default_report_date(),
        "items": svc.candidates(conn, include_inactive),
    }
