"""다년도 과제 로드맵 (TODO 174). 화면이 거르기 · 그리기를 맡고, 서버는 줄기 · 단계 · 살펴볼 것을 센다."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from ..deps import get_db
from ..services import roadmap as svc

router = APIRouter(prefix="/api/roadmap", tags=["roadmap"])


@router.get("")
def get_roadmap(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return svc.build(conn)
