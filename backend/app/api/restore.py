"""전체 백업 ZIP 에서 되살리기 (TODO 246). `/api/backup` 밑이라 공유 바깥(팀원 포함)에는 막혀 있다."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel

from ..deps import get_db
from ..services import restore as svc

router = APIRouter(prefix="/api/backup/restore", tags=["restore"])


class ApplyRequest(BaseModel):
    token: str


@router.post("/inspect")
async def inspect(request: Request) -> dict:
    """올린 ZIP 을 받아 살펴본다 — 무엇이 들었나, 되살릴 수 있나, 지금 데이터는 얼마나 바뀌나.

    화면은 파일을 **본문 그대로** 보낸다(TODO 267) — 받는 대로 데이터 폴더 드라이브의 작업 자리에 쓴다(웹 틀의 %TEMP% 를 거치지 않음).
    예전 모양(multipart 의 `file`)도 받는다.
    """
    from urllib.parse import unquote

    from ..services import workspace

    size = int(request.headers.get("content-length") or 0)
    filename = unquote(request.headers.get("x-filename") or "")
    try:
        if request.headers.get("content-type", "").startswith("multipart/"):
            form = await request.form()
            upload = form.get("file")
            if upload is None or not hasattr(upload, "file"):
                raise HTTPException(status_code=400, detail="올린 파일이 없습니다.")
            filename = upload.filename or filename
            token = await run_in_threadpool(svc.save_upload, upload.file, size)
        else:
            token = await svc.save_upload_stream(request.stream(), size)
    except workspace.SpaceError as exc:
        raise HTTPException(status_code=507, detail=str(exc)) from exc
    return await run_in_threadpool(_inspect_saved, token, filename)


def _inspect_saved(token: str, filename: str) -> dict:
    try:
        report = svc.inspect(svc.upload_path(token), filename)
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


# ── 뒤에서 되살리기 · 단계별 진행 (TODO 268) ─────────────────────────────────
# 쓰기 차례(`get_db` 의 잠금)는 작업 스레드가 잡는다 — 이 끝점들은 DB 를 쓰지 않는다.
from ..services import restore_jobs as jobs  # noqa: E402


@router.post("/jobs")
def start_job(payload: ApplyRequest) -> dict:
    """되살리기를 뒤에서 시작한다 — 도는 것이 있으면 그것을 돌려준다(한 번에 하나)."""
    try:
        return jobs.start(payload.token).as_dict()
    except svc.RestoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/jobs/current")
def current_job() -> dict:
    job = jobs.current()
    return {"job": job.as_dict() if job else None}


@router.get("/jobs/{job_id}")
def job_state(job_id: str) -> dict:
    try:
        return jobs.get(job_id).as_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="그 되살리기 작업이 없습니다(끝난 지 오래됐거나 서버를 다시 켰습니다).") from exc


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    try:
        return jobs.cancel(job_id).as_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="그 되살리기 작업이 없습니다.") from exc
