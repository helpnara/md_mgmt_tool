from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Query, Request

from ..deps import get_db
from ..services import home as svc

router = APIRouter(prefix="/api", tags=["home"])


@router.get("/home")
def home(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    # 비우면 전체. 목록·대시보드와 같은 규칙이다 (연도는 과제 번호 앞 네 자리).
    year: str | None = Query(None, pattern=r"^(\d{4})?$"),
    # 반기·분기 (TODO 110). 날짜가 있는 수치(보고 횟수·끝낸 과제·역량 이력)에만 듣는다.
    period: str | None = Query(None, pattern="^(H1|H2|Q1|Q2|Q3|Q4)?$"),
) -> dict:
    data = svc.summary(conn, year=year or None, period=period or None)
    if getattr(request.state, "readonly", False):
        # TODO 206 ⑫ — 읽기 전용 공유에는 떠난 담당자의 사유 · 날짜를 주지 않는다 (명부 끝점은 막혀 있다).
        # 화면은 사유가 없으면 "떠남" 으로 그린다.
        gaps = data.get("this_week", {}).get("owner_gaps") or []
        data["this_week"]["owner_gaps"] = [
            {key: value for key, value in item.items() if key not in ("left_reason", "left_on")} for item in gaps
        ]
    return data
