"""폴더 고르기 API (TODO 97).

내주는 것은 **폴더 이름과 경로뿐**이다 — 파일은 세지도 보여 주지도 않는다.
이 프로그램은 본인 PC에서 `127.0.0.1` 로만 도는 것이 기본이라 (`run.py --host`),
서버가 곧 그 PC다. 그래서 서버가 폴더 목록을 주는 것이 곧 "내 PC를 훑는" 일이다.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..services import folders as svc

router = APIRouter(prefix="/api/folders", tags=["folders"])


@router.get("")
def list_folders(path: str | None = Query(None)) -> dict:
    """그 폴더 아래의 폴더들. `path` 를 비우면 드라이브 등 처음 자리."""
    try:
        return svc.listing(path)
    except svc.FolderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class NewFolder(BaseModel):
    parent: str
    name: str


@router.post("", status_code=201)
def create_folder(payload: NewFolder) -> dict:
    """고른 자리 아래에 폴더 하나를 만든다 — 탐색기를 따로 열지 않아도 되게."""
    try:
        return {"path": svc.create(payload.parent, payload.name)}
    except svc.FolderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
