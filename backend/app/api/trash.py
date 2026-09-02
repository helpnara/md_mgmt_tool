from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_db
from ..services import trash as svc
from ..vault.paths import FileInUseError

router = APIRouter(prefix="/api/trash", tags=["trash"])


@router.get("")
def list_trash() -> list[dict]:
    return svc.list_items()


@router.post("/{trash_name}/restore")
def restore(trash_name: str, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    try:
        return svc.restore(conn, trash_name)
    except svc.RestoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileInUseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
