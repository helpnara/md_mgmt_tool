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
    # 반기·분기 (TODO 110). 날짜가 있는 수치(보고 횟수·끝낸 과제·역량 이력)에만 듣는다.
    period: str | None = Query(None, pattern="^(H1|H2|Q1|Q2|Q3|Q4)?$"),
) -> dict:
    return svc.summary(conn, year=year or None, period=period or None)
