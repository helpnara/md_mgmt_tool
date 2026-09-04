"""이전 버전 보기·되돌리기 (안쪽 안전망)."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..deps import get_db
from ..vault import versions as svc

router = APIRouter(prefix="/api/versions", tags=["versions"])


class RestoreRequest(BaseModel):
    """vault 기준 상대경로와 되돌릴 버전."""

    path: str
    stamp: str


@router.get("")
def list_versions(path: str = Query(..., min_length=1)) -> dict:
    return {"path": path, "items": svc.list_for(path)}


@router.get("/overview")
def versions_overview() -> dict:
    return svc.overview()


@router.get("/content")
def version_content(path: str = Query(..., min_length=1), stamp: str = Query(..., min_length=1)) -> dict:
    try:
        return {"path": path, "stamp": stamp, "text": svc.read(path, stamp)}
    except svc.VersionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=404, detail="버전을 읽지 못했습니다.") from exc


@router.post("/restore")
def restore_version(payload: RestoreRequest, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    try:
        return svc.restore(conn, payload.path, payload.stamp)
    except svc.VersionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:  # safe_join — vault 밖을 가리키는 경로
        raise HTTPException(status_code=400, detail=str(exc)) from exc
