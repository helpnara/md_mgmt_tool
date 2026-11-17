"""업데이트 (TODO 298) — 서버 PC(관리자)만. 찾기 · 예약(데이터 백업 뒤) · 스스로 끝나 run.py 가 적용하고 다시 켠다."""
from __future__ import annotations

import os
import threading

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .. import updater, who
from ..config import program_home
from ..services import settings as settings_service

router = APIRouter(prefix="/api/update", tags=["update"])
RESTART_DELAY = 1.5


class ApplyIn(BaseModel):
    name: str
    backup: bool | None = None      # 301 — None 이면 예전처럼(백업 폴더가 있으면 백업)


# 301 — 업데이트 전 백업은 뒤에서 돌린다(3GB 면 몇 분). 화면은 GET /api/update/job 으로 진행을 본다.
_job: dict = {"state": "idle"}
_job_lock = threading.Lock()
SPACE_MARGIN = 200 * 1024 * 1024      # 남은 공간 여유(200MB)


def _admin(request: Request) -> None:
    if who.of(request).role != who.OWNER:
        raise HTTPException(status_code=403, detail="업데이트는 서버 PC(관리자)에서만 합니다.")


def _configured() -> str:
    return str(settings_service.load().get("update_dir") or "")


def supervised() -> bool:
    """run.bat(run.py) 의 바깥 고리 아래에서 돌고 있나 — 아니면 스스로 다시 켤 수 없다(손으로 다시 켜야)."""
    return bool(os.environ.get("MD_MGMT_CHILD"))


def _restart() -> None:
    """응답을 보낸 뒤 스스로 끝난다 — run.py 가 예약된 적용을 하고 다시 켠다."""
    threading.Timer(RESTART_DELAY, lambda: os._exit(3)).start()


@router.get("")
def status(request: Request) -> dict:
    _admin(request)
    root = program_home()
    state = updater.read_state(root)
    return {**updater.candidates(root, _configured()), "configured": _configured(), "supervised": supervised(),
            "last": state.get("last"), "history": state.get("history", [])[:5],
            "rollback": bool(updater.latest_rollback(root))}


def backup_check() -> dict:
    """업데이트 전 백업을 할지 정할 재료 (TODO 301) — 백업 폴더 · 오늘 백업 · 예상 크기 · 남은 공간."""
    from datetime import datetime
    from pathlib import Path

    from ..services import backup as backup_service
    from ..services import workspace

    status = backup_service.status()
    folder = status["directory"]
    last = status.get("last") or None
    today = None
    if last and last.get("ok") and last.get("at"):
        try:
            when = datetime.fromisoformat(str(last["at"]).replace(" ", "T"))
            if when.date() == datetime.now().date():
                today = {"at": when.isoformat(timespec="minutes"), "file": last.get("file", "")}
        except ValueError:
            today = None
    # 예상 크기 — 지난 백업 zip 의 크기(가장 가까움), 없으면 담을 파일의 크기(압축 전이라 넉넉)
    expected = status["recent"][0]["size_bytes"] if status.get("recent") else 0
    if not expected and folder:
        from ..services import backup_jobs

        expected = backup_jobs.estimate(assets=not status.get("skip_assets"))["bytes"]
    free = workspace.free_bytes(Path(folder)) if folder and status.get("reachable") else None
    enough = None if free is None else free >= expected + SPACE_MARGIN
    return {"enabled": bool(folder), "reachable": bool(status.get("reachable")), "directory": folder,
            "today": today, "expected_bytes": expected, "free_bytes": free, "enough": enough}


@router.get("/check")
def check(request: Request) -> dict:
    _admin(request)
    return backup_check()


def _work(root, zip_path, by: str, do_backup: bool) -> None:
    from ..services import backup as backup_service
    from ..services import running

    backup_file = ""
    try:
        if do_backup:
            with running.track("업데이트 전 데이터 백업", key="update"):
                backup_file = backup_service.run(None, reason="update")["file"]
        pending = updater.request(root, zip_path, by=by, data_backup=backup_file)
        restarting = supervised()
        with _job_lock:
            _job.update({"state": "restarting" if restarting else "scheduled", "data_backup": backup_file, "pending": pending})
        if restarting:
            _restart()
    except Exception as exc:  # noqa: BLE001 — 어떤 실패든 화면에(업데이트는 하지 않는다)
        message = str(exc) or type(exc).__name__
        if do_backup and not backup_file:
            message = f"업데이트 전 데이터 백업을 만들지 못해 멈췄습니다 — {message}"
        with _job_lock:
            _job.update({"state": "error", "error": message})


@router.get("/job")
def job(request: Request) -> dict:
    """업데이트 준비(백업)의 진행 (TODO 301)."""
    _admin(request)
    from ..services import running

    with _job_lock:
        data = dict(_job)
    tasks = [t for t in running.listing("update") if t["state"] == "running"]
    data["progress"] = tasks[-1] if tasks else None
    return data


@router.post("")
def apply(payload: ApplyIn, request: Request, wait: bool = False) -> dict:
    """업데이트 — 백업(고르면)을 뒤에서 한 뒤 예약하고 스스로 끝난다. `wait` 은 시험용(끝까지 기다림)."""
    _admin(request)
    root = program_home()
    folder = updater.update_dir(root, _configured())
    zip_path = next((p for p in folder.glob("느린나이테-*.zip") if p.stem == payload.name), None)
    if zip_path is None:
        raise HTTPException(status_code=404, detail="업데이트 폴더에 그 배포본이 없습니다.")
    problem = updater.verify(zip_path)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    info = backup_check()
    do_backup = info["enabled"] if payload.backup is None else bool(payload.backup)
    if do_backup:
        if not info["enabled"]:
            raise HTTPException(status_code=400, detail="백업 폴더가 정해져 있지 않습니다 — 백업 없이 업데이트하거나 설정에서 백업 폴더를 정해 주세요.")
        if info["enough"] is False:
            raise HTTPException(status_code=400, detail=f"백업 폴더의 남은 공간이 모자랍니다 — 필요 약 {info['expected_bytes'] // 1024 // 1024:,}MB, 남은 {info['free_bytes'] // 1024 // 1024:,}MB.")
    with _job_lock:
        if _job.get("state") in ("backup", "restarting"):
            raise HTTPException(status_code=409, detail="업데이트를 준비하는 중입니다.")
        _job.clear()
        _job.update({"state": "backup" if do_backup else "starting", "name": payload.name, "backup": do_backup})
    by = who.of(request).name or "관리자"
    if wait:
        _work(root, zip_path, by, do_backup)
    else:
        threading.Thread(target=_work, args=(root, zip_path, by, do_backup), daemon=True).start()
    with _job_lock:
        return {**_job, "restarting": _job.get("state") == "restarting" or (not wait and supervised())}


@router.post("/rollback")
def rollback(request: Request) -> dict:
    _admin(request)
    try:
        pending = updater.request_rollback(program_home(), by=who.of(request).name or "관리자")
    except updater.UpdateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    restarting = supervised()
    if restarting:
        _restart()
    return {"pending": pending, "restarting": restarting}
