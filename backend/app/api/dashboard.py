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
) -> dict:
    return svc.summary(conn, limit)
