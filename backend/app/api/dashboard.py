from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Query

from ..deps import get_db
from ..services import dashboard as svc

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
def dashboard(
    conn: sqlite3.Connection = Depends(get_db),
    limit: int = Query(svc.CANDIDATE_LIMIT, ge=1, le=20),
    # 목록과 **같은 연도**를 봐야 한다. 다르면 "N건" 을 눌렀을 때 나오는 수가 어긋난다.
    year: str | None = Query(None, pattern=r"^(\d{4})?$"),
) -> dict:
    return svc.summary(conn, limit, year=year or None)
