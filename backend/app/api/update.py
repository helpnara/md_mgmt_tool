"""업데이트 (TODO 298) — 서버 PC(관리자)만. 찾기 · 예약(데이터 백업 뒤) · 스스로 끝나 run.py 가 적용하고 다시 켠다."""
from __future__ import annotations

import os
import sqlite3
import threading

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .. import updater, who
from ..config import program_home
from ..deps import get_db
from ..services import settings as settings_service

router = APIRouter(prefix="/api/update", tags=["update"])
RESTART_DELAY = 1.5


class ApplyIn(BaseModel):
    name: str


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


@router.post("")
def apply(payload: ApplyIn, request: Request, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    _admin(request)
    root = program_home()
    folder = updater.update_dir(root, _configured())
    zip_path = next((p for p in folder.glob("느린나이테-*.zip") if p.stem == payload.name), None)
    if zip_path is None:
        raise HTTPException(status_code=404, detail="업데이트 폴더에 그 배포본이 없습니다.")
    problem = updater.verify(zip_path)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    # 적용 전 데이터 백업 한 벌(자동 백업 폴더가 정해져 있을 때) — 프로그램만 바뀌지만 만일을 위해
    backup_file = ""
    if str(settings_service.load().get("backup_dir") or "").strip():
        from ..services import backup as backup_service

        try:
            backup_file = backup_service.run(conn, reason="update")["file"]
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"업데이트 전 데이터 백업을 만들지 못해 멈췄습니다 — {exc}") from exc
    try:
        pending = updater.request(root, zip_path, by=who.of(request).name or "관리자", data_backup=backup_file)
    except updater.UpdateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    restarting = supervised()
    if restarting:
        _restart()
    return {"pending": pending, "restarting": restarting, "data_backup": backup_file}


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
