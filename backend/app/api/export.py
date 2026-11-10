from __future__ import annotations

import os
import re
import sqlite3
import tempfile
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from starlette.background import BackgroundTask

from .. import share
from ..deps import get_db
from ..services import export as svc

router = APIRouter(prefix="/api", tags=["export"])


def _disposition(filename: str) -> str:
    # 한글 파일명은 RFC 5987 형식으로 보내되, 그것을 모르는 도구(curl -OJ 등)를 위해
    # ASCII 대체 이름도 함께 넣는다.
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "-", filename).strip("-") or "export"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


def _attachment(content: bytes | str, filename: str, media_type: str) -> Response:
    body = content.encode("utf-8") if isinstance(content, str) else content
    return Response(content=body, media_type=media_type, headers={"Content-Disposition": _disposition(filename)})


@router.get("/backup")
def backup_everything(
    assets: str = Query("all", pattern="^(all|none)$"),
    conn: sqlite3.Connection = Depends(get_db),
) -> Response:
    """vault 전체 백업. 설정 화면에서 내려받는다.

    zip 을 **임시 파일에 흘려 쓴 뒤** 그 파일을 내려보내고, 다 보내면 지운다 (TODO 202 ⑬) — 첨부가 GB 여도
    메모리에 통째로 올리지 않는다. `assets=none` 이면 첨부(`assets/`)를 뺀 문서만 (TODO 197 ③).
    """
    from ..services import backup_jobs, workspace

    with_assets = assets != "none"
    # 작업 파일은 데이터 폴더 드라이브의 `.work/` 에(TODO 267 — %TEMP% 는 C: 라 모자랐다) · 쓰기 전에 남은 자리를 본다
    folder = workspace.work_dir("backup")
    try:
        workspace.ensure_space(folder, backup_jobs.estimate(with_assets)["bytes"], "전체 백업 만들기")
    except workspace.SpaceError as exc:
        raise HTTPException(status_code=507, detail=str(exc)) from exc
    fd, tmp_name = tempfile.mkstemp(dir=str(folder), prefix="과제이력-백업-", suffix=".zip.part")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            svc.write_backup_all(handle, assets=with_assets)
    except OSError as exc:
        tmp_path.unlink(missing_ok=True)
        if exc.errno == 28:
            raise HTTPException(status_code=507, detail=str(workspace.space_error_from(exc, folder, "전체 백업"))) from exc
        raise
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    filename = svc.backup_all_filename(with_assets)
    return FileResponse(
        tmp_path,
        media_type="application/zip",
        headers={"Content-Disposition": _disposition(filename)},
        background=BackgroundTask(tmp_path.unlink, missing_ok=True),
    )


# ── 전체 백업 — 뒤에서 만들고 진행을 보인다 (TODO 266) ──────────────────────

class BackupJobIn(BaseModel):
    assets: bool = True


@router.get("/backup/estimate")
def backup_estimate(assets: str = Query("all", pattern="^(all|none)$")) -> dict:
    """담을 파일 수 · 크기(문서 · 첨부) · 작업 자리의 남은 자리 — 시작 전에 보인다."""
    from ..services import backup_jobs

    return backup_jobs.estimate(assets != "none")


@router.post("/backup/jobs", status_code=201)
def backup_job_start(payload: BackupJobIn) -> dict:
    from ..services import backup_jobs, workspace

    try:
        return backup_jobs.start(payload.assets).as_dict()
    except workspace.SpaceError as exc:
        raise HTTPException(status_code=507, detail=str(exc)) from exc


@router.get("/backup/jobs/current")
def backup_job_current() -> dict:
    """지금 작업(없으면 null) — 다른 화면에 갔다 와도 이어 보이게."""
    from ..services import backup_jobs

    job = backup_jobs.current()
    return {"job": job.as_dict() if job else None}


@router.get("/backup/jobs/{job_id}")
def backup_job_status(job_id: str) -> dict:
    from ..services import backup_jobs

    try:
        return backup_jobs.get(job_id).as_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="그 백업 작업이 없습니다(프로그램을 다시 켰거나 이미 받았습니다).") from exc


@router.post("/backup/jobs/{job_id}/cancel")
def backup_job_cancel(job_id: str) -> dict:
    from ..services import backup_jobs

    try:
        return backup_jobs.cancel(job_id).as_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="그 백업 작업이 없습니다.") from exc


@router.get("/backup/jobs/{job_id}/file")
def backup_job_file(job_id: str) -> Response:
    """다 만든 zip 을 내려보내고, 다 보내면 지운다."""
    from ..services import backup_jobs

    try:
        job = backup_jobs.take(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="아직 다 만들지 않았거나 이미 받은 백업입니다.") from exc
    return FileResponse(job.path, media_type="application/zip", headers={"Content-Disposition": _disposition(job.filename)},
                        background=BackgroundTask(backup_jobs.release, job_id))


@router.get("/projects/{project_id}/export")
def export_project(
    request: Request,
    project_id: str,
    format: str = Query("zip", pattern="^(md|zip|html|backup)$"),
    assets: str = Query("zip", pattern="^(zip|inline|link)$"),
    include_reports_full: bool = False,
    conn: sqlite3.Connection = Depends(get_db),
) -> Response:
    """과제 이력을 한 덩어리로 내보낸다.

    - md   : 마크다운 한 파일 (assets=inline이면 이미지를 파일 안에 심는다)
    - zip  : 병합 마크다운 + 참조된 첨부 (압축을 풀면 링크가 그대로 살아 있다)
    - html : 이미지까지 담긴 단일 HTML
    - backup: 과제 폴더 원본 구조 그대로 — **읽기 전용 공유의 바깥에는 열지 않는다** (TODO 206 ㉙, 결정 ④):
      화면에 없는 수기 파일까지 통째로 나간다. md · zip · html 내보내기는 바깥에서도 된다.
    """
    from .. import who

    # 팀장 PC(TODO 247)는 팀의 자료를 맡은 쪽이라 연다 — 전체 백업을 내려받을 수 있는 것과 같다
    if format == "backup" and share.is_remote(request) and not who.of(request).manages:
        raise HTTPException(status_code=403, detail=share.READONLY_DETAIL)
    try:
        if format == "zip":
            filename, content = svc.export_zip(conn, project_id, include_reports_full)
            return _attachment(content, filename, "application/zip")
        if format == "backup":
            filename, content = svc.backup_zip(conn, project_id)
            return _attachment(content, filename, "application/zip")
        if format == "html":
            filename, text = svc.export_html(conn, project_id, include_reports_full)
            return _attachment(text, filename, "text/html; charset=utf-8")

        filename, text, _ = svc.merged_markdown(conn, project_id, assets, include_reports_full)
        return _attachment(text, filename, "text/markdown; charset=utf-8")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="과제를 찾을 수 없습니다.") from exc
