from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_db
from ..vault.markdown import ExternalChangeError
from ..vault.paths import FileInUseError, InvalidDateError
from ..schemas import EntryCreate, EntryUpdate
from ..services import entries as svc

router = APIRouter(tags=["entries"])


def _tags(conn: sqlite3.Connection, entry_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT t.name FROM tag t JOIN entry_tag et ON et.tag_id = t.id WHERE et.entry_id = ? ORDER BY t.name",
        (entry_id,),
    ).fetchall()
    return [row["name"] for row in rows]


def _serialize(conn: sqlite3.Connection, row: sqlite3.Row, with_body: bool = True) -> dict:
    data = {
        "id": row["id"],
        "project_id": row["project_id"],
        "rel_path": row["rel_path"],
        "date": row["date"],
        "title": row["title"],
        "author": row["author"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "tags": _tags(conn, row["id"]),
    }
    if with_body:
        data["body"] = row["body"]
    return data


@router.get("/api/projects/{project_id}/entries")
def list_entries(project_id: str, conn: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM entry WHERE project_id = ? ORDER BY date DESC, id DESC", (project_id,)
    ).fetchall()
    return [_serialize(conn, row) for row in rows]


@router.post("/api/projects/{project_id}/entries", status_code=201)
def create_entry(
    project_id: str, payload: EntryCreate, conn: sqlite3.Connection = Depends(get_db)
) -> dict:
    try:
        entry_id = svc.create_entry(conn, project_id, payload.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="과제를 찾을 수 없습니다.") from exc
    except InvalidDateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    row = conn.execute("SELECT * FROM entry WHERE id = ?", (entry_id,)).fetchone()
    return _serialize(conn, row)


@router.get("/api/entries/{entry_id}")
def get_entry(entry_id: int, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    row = conn.execute("SELECT * FROM entry WHERE id = ?", (entry_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="진행일지를 찾을 수 없습니다.")
    return _serialize(conn, row)


@router.patch("/api/entries/{entry_id}")
def update_entry(
    entry_id: int, payload: EntryUpdate, conn: sqlite3.Connection = Depends(get_db)
) -> dict:
    try:
        svc.update_entry(conn, entry_id, payload.changes())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="진행일지를 찾을 수 없습니다.") from exc
    except ExternalChangeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidDateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    row = conn.execute("SELECT * FROM entry WHERE id = ?", (entry_id,)).fetchone()
    return _serialize(conn, row)


@router.delete("/api/entries/{entry_id}", status_code=204)
def delete_entry(entry_id: int, conn: sqlite3.Connection = Depends(get_db)) -> None:
    try:
        svc.delete_entry(conn, entry_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="진행일지를 찾을 수 없습니다.") from exc
    except FileInUseError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc
