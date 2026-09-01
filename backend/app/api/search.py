from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Query

from ..deps import get_db
from ..services import search as svc

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
def search(
    q: str = Query("", description="검색어"), conn: sqlite3.Connection = Depends(get_db)
) -> dict:
    return svc.search(conn, q)
