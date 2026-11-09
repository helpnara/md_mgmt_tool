"""전체 백업 ZIP 에서 되살리기 (TODO 246). `/api/backup` 밑이라 공유 바깥(팀원 포함)에는 막혀 있다."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from ..deps import get_db
from ..services import restore as svc

router = APIRouter(prefix="/api/backup/restore", tags=["restore"])


class ApplyRequest(BaseModel):
    token: str


@router.post("/inspect")
def inspect(file: UploadFile = File(...)) -> dict:
    """올린 ZIP 을 임시 파일로 받아 살펴본다 — 무엇이 들었나, 되살릴 수 있나, 지금 데이터는 얼마나 바뀌나."""
    token = svc.save_upload(file.file)
    try:
        report = svc.inspect(svc.upload_path(token), file.filename or "")
    except svc.RestoreError as exc:
        svc.discard_upload(token)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not report["ok"]:
        svc.discard_upload(token)
        return {**report, "token": None}
    return {**report, "token": token}


@router.post("")
def apply(payload: ApplyRequest, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """지금 데이터를 먼저 백업하고, 올린 백업으로 데이터 폴더를 바꾸고, 색인을 다시 만든다."""
    try:
        return svc.apply(conn, payload.token)
    except svc.RestoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
