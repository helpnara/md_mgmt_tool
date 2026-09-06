from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Query

from ..deps import get_db
from ..services import home as svc

router = APIRouter(prefix="/api", tags=["home"])


@router.get("/home")
def home(
    conn: sqlite3.Connection = Depends(get_db),
    # 비우면 전체. 목록·대시보드와 같은 규칙이다 (연도는 과제 번호 앞 네 자리).
    year: str | None = Query(None, pattern=r"^(\d{4})?$"),
) -> dict:
    return svc.summary(conn, year=year or None)
