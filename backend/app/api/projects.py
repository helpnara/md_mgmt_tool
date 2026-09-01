from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import STATUS_KEYS, get_settings
from ..deps import get_db
from ..vault.markdown import ExternalChangeError
from ..vault.paths import FileInUseError
from ..services import projects as svc
from ..services import search as search_svc
from ..schemas import ProjectCreate, ProjectUpdate

router = APIRouter(prefix="/api/projects", tags=["projects"])

SORTS = {
    "updated": "p.updated_at DESC",
    "due": "CASE WHEN p.due_date IS NULL THEN 1 ELSE 0 END, p.due_date ASC",
    "title": "p.title ASC",
    "created": "p.created_at DESC",
}


def _tags(conn: sqlite3.Connection, project_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT t.name FROM tag t JOIN project_tag pt ON pt.tag_id = t.id WHERE pt.project_id = ? ORDER BY t.name",
        (project_id,),
    ).fetchall()
    return [row["name"] for row in rows]


def _owners(conn: sqlite3.Connection, project_id: str) -> list[str]:
    return [
        row["name"]
        for row in conn.execute(
            "SELECT name FROM project_owner WHERE project_id = ? ORDER BY position, name",
            (project_id,),
        )
    ]


def _serialize(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "status": row["status"],
        "group": row["grp"],
        "owners": _owners(conn, row["id"]),
        "start_date": row["start_date"],
        "due_date": row["due_date"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_reported_at": row["last_reported_at"],
        "tags": _tags(conn, row["id"]),
        "entry_count": conn.execute(
            "SELECT COUNT(*) AS n FROM entry WHERE project_id = ?", (row["id"],)
        ).fetchone()["n"],
    }


# 마감 기준 빠른 필터: 값 → (SQL 조건, 파라미터 생성기)
DUE_FILTERS = {
    "overdue": "p.due_date IS NOT NULL AND p.due_date < DATE('now', 'localtime')",
    "7": "p.due_date IS NOT NULL AND p.due_date <= DATE('now', 'localtime', '+7 day')",
    "14": "p.due_date IS NOT NULL AND p.due_date <= DATE('now', 'localtime', '+14 day')",
    "30": "p.due_date IS NOT NULL AND p.due_date <= DATE('now', 'localtime', '+30 day')",
}


@router.get("")
def list_projects(
    conn: sqlite3.Connection = Depends(get_db),
    status: str | None = None,
    group: str | None = None,
    tag: str | None = None,
    owner: str | None = None,
    q: str | None = None,
    due: str | None = None,
    sort: str = Query("updated"),
) -> list[dict]:
    where, params = [], []
    if status:
        where.append("p.status = ?")
        params.append(status)
    if group:
        where.append("p.grp = ?")
        params.append(group)
    if tag:
        where.append(
            "p.id IN (SELECT pt.project_id FROM project_tag pt JOIN tag t ON t.id = pt.tag_id WHERE t.name = ?)"
        )
        params.append(tag)
    if owner:
        where.append("p.id IN (SELECT po.project_id FROM project_owner po WHERE po.name = ?)")
        params.append(owner)
    if due in DUE_FILTERS:
        where.append(DUE_FILTERS[due])
    if q and q.strip():
        # 과제 본문뿐 아니라 진행일지·첨부 파일명에 걸려도 그 과제를 남긴다.
        matched = search_svc.project_ids_matching(conn, q.strip())
        if not matched:
            return []
        where.append(f"p.id IN ({','.join('?' * len(matched))})")
        params.extend(matched)

    clause = f"WHERE {' AND '.join(where)}" if where else ""
    order = SORTS.get(sort, SORTS["updated"])
    rows = conn.execute(f"SELECT p.* FROM project p {clause} ORDER BY {order}", params).fetchall()
    return [_serialize(conn, row) for row in rows]


@router.post("", status_code=201)
def create_project(payload: ProjectCreate, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    try:
        project_id = svc.create_project(conn, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    row = conn.execute("SELECT * FROM project WHERE id = ?", (project_id,)).fetchone()
    return _serialize(conn, row)


@router.get("/{project_id}")
def get_project(project_id: str, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    row = conn.execute("SELECT * FROM project WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="과제를 찾을 수 없습니다.")
    data = _serialize(conn, row)
    data["body"] = row["body"]
    data["dir_name"] = row["dir_name"]
    return data


@router.patch("/{project_id}")
def update_project(
    project_id: str, payload: ProjectUpdate, conn: sqlite3.Connection = Depends(get_db)
) -> dict:
    try:
        svc.update_project(conn, project_id, payload.changes())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="과제를 찾을 수 없습니다.") from exc
    except ExternalChangeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileInUseError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return get_project(project_id, conn)


@router.post("/{project_id}/archive", status_code=204)
def archive_project(project_id: str, conn: sqlite3.Connection = Depends(get_db)) -> None:
    try:
        svc.archive_project(conn, project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="과제를 찾을 수 없습니다.") from exc
    except FileInUseError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc
