from __future__ import annotations

import sqlite3
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from ..deps import get_db
from ..vault.markdown import ExternalChangeError
from ..services import attachments as attach_svc
from ..services import reports as svc
from ..vault import paths
from ..vault.paths import FileInUseError, InvalidDateError

router = APIRouter(tags=["reports"])


class ReportCreate(BaseModel):
    report_date: str | None = None
    audience: str | None = None


class ReportUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    audience: str | None = None  # 피보고자 또는 회의체명
    report_date: str | None = None  # 바꾸면 문서가 든 폴더도 함께 옮긴다
    # 보고 뒤에 받은 지시 (TODO 107). 확정된 보고에서도 쓸 수 있는 유일한 본문이다.
    feedback: str | None = None

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
        # 보고 뒤에 받은 지시 (TODO 107). feedback_done 은 답한 날 — 비면 아직 답하지 않았다.
        "feedback": row["feedback"],
        "feedback_done": row["feedback_done"],
        "entry_count": conn.execute(
            "SELECT COUNT(*) AS n FROM report_entry WHERE report_id = ?", (row["id"],)
        ).fetchone()["n"],
    }
    if with_body:
        data["body"] = row["body"]
    return data


@router.get("/api/reports")
def search_reports(
    audience: str | None = None,
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
    q: str | None = None,
    project_id: str | None = None,
    state: str | None = Query(None, pattern="^(frozen|draft)$"),
    # 지시를 받았는데 아직 답하지 않은 보고만 (TODO 107)
    feedback: str | None = Query(None, pattern="^(open)?$"),
    limit: int = Query(svc.SEARCH_LIMIT, ge=1, le=500),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[dict]:
    """과제를 가로질러 보고 문서를 찾는다 (피보고자·기간·검색어)."""
    return svc.search(
        conn,
        audience=audience,
        date_from=date_from,
        date_to=date_to,
        query=q,
        project_id=project_id,
        state=state,
        feedback=feedback,
        limit=limit,
    )


class FeedbackDone(BaseModel):
    done: bool = True


@router.post("/api/reports/{report_id}/feedback-done")
def feedback_done(
    report_id: int, payload: FeedbackDone, conn: sqlite3.Connection = Depends(get_db)
) -> dict:
    """지시에 답했다(또는 아직이다). 다음 초안에 그 지시가 다시 나오지 않게 한다 (TODO 107)."""
    try:
        svc.mark_feedback_done(conn, report_id, payload.done)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="보고 문서를 찾을 수 없습니다.") from exc
    except (PermissionError, ExternalChangeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _serialize(conn, svc.report_row(conn, report_id))


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
    except InvalidDateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileInUseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _serialize(conn, svc.report_row(conn, report_id))


@router.get("/api/reports/{report_id}/diff")
def report_diff(report_id: int, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """직전에 확정한 보고와의 차이. 비교할 보고가 없으면 previous 가 null."""
    try:
        return svc.diff_with_previous(conn, report_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="보고 문서를 찾을 수 없습니다.") from exc


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
    except PermissionError as exc:
        # 확정된 보고 — 확정을 먼저 풀어야 한다 (TODO 61).
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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


@router.get("/api/reports/{report_id}/ai-prompt")
def ai_prompt(report_id: int, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """이 보고를 AI 에게 넘길 글 한 덩이. **여기서 AI 를 부르지는 않는다** (TODO 71).

    만들어 주기만 하고, 어디에 붙여넣을지는 사람이 정한다.
    """
    from ..services import ai_prompt as prompt_svc

    try:
        return {"text": prompt_svc.build(conn, report_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="보고를 찾을 수 없습니다.") from exc


@router.get("/api/report-month-grid")
def month_grid(
    year: str = Query(..., pattern=r"^\d{4}$"),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """과제 × 월 보고 표 (TODO 77). 보고 이력 화면이 쓴다 (TODO 79)."""
    return svc.month_grid(conn, year)


@router.get("/api/report-candidates")
def report_candidates(
    include_inactive: bool = False,
    status: str | None = None,
    type: str | None = None,
    owner: str | None = None,
    sort: str | None = None,
    order: str = Query("asc", pattern="^(asc|desc)$"),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """보고 대상 후보. 거르기(TODO 49)와 열 정렬(TODO 57)을 함께 받는다.

    `sort` 를 주지 않으면 기본 순서다 — 보고 이력 없음 먼저, 그다음 오래된 순(TODO 52).
    """
    from ..config import get_settings

    report_date = svc.default_report_date()
    return {
        "cycle_days": get_settings().report_cycle_days,
        "default_report_date": report_date,
        "sorts": list(svc.CANDIDATE_SORTS),
        # 확정을 기다리는 초안도 함께 준다 (TODO 91). 이 화면의 물음이 "이번 주에 무엇을
        # 보고할까" 하나라, 아직 안 끝난 초안은 후보보다 먼저 걸리는 일이다.
        # **날짜를 가리지 않는다** (TODO 103-A). 홈이 모든 날짜의 초안을 세우고 이리로
        # 보내는데, 여기서 그날 것만 보이면 "1건이라더니?" 가 된다. 오래된 것이 먼저다.
        "drafts": svc.unfinished_drafts(conn, limit=svc.WAITING_LIST_LIMIT)["items"],
        "items": svc.candidates(
            conn, include_inactive, status=status, type=type, owner=owner, sort=sort, order=order
        ),
    }
