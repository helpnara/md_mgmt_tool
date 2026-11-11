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
    from ..services import running

    try:
        with running.track("삭제 보관함에서 되돌리기", "trash-restore"):   # 되돌린 뒤 색인 다시 만들기(TODO 268)
            return svc.restore(conn, trash_name)
    except svc.RestoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileInUseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
