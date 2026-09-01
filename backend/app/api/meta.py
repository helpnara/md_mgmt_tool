from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from ..config import COLLAPSED_STATUSES, STATUSES, get_settings
from ..deps import get_db
from ..vault.indexer import reindex_all

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {"status": "ok", "vault": str(settings.vault_dir)}


@router.get("/meta")
def meta(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    groups = [
        row["grp"]
        for row in conn.execute(
            "SELECT DISTINCT grp FROM project WHERE grp IS NOT NULL AND grp <> '' ORDER BY grp"
        )
    ]
    tags = [row["name"] for row in conn.execute("SELECT name FROM tag ORDER BY name")]
    return {
        "statuses": [
            {"key": key, "label": label, "candidate": candidate, "collapsed": key in COLLAPSED_STATUSES}
            for key, label, candidate in STATUSES
        ],
        "groups": groups,
        "tags": tags,
        "vault": str(get_settings().vault_dir),
        "report_cycle_days": get_settings().report_cycle_days,
    }


@router.post("/reindex")
def reindex(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return {"indexed": reindex_all(conn)}
