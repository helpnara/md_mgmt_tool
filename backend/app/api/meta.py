from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from ..config import COLLAPSED_STATUSES, PROJECT_TYPES, STATUSES, get_settings
from ..deps import get_db
from ..services import settings as settings_service
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
    owners = [
        row["name"]
        for row in conn.execute("SELECT DISTINCT name FROM project_owner ORDER BY name")
    ]
    audiences = [
        row["audience"]
        for row in conn.execute(
            "SELECT DISTINCT audience FROM report WHERE audience IS NOT NULL AND audience <> ''"
            " ORDER BY audience"
        )
    ]
    return {
        "statuses": [
            {"key": key, "label": label, "candidate": candidate, "collapsed": key in COLLAPSED_STATUSES}
            for key, label, candidate in STATUSES
        ],
        "types": [{"key": key, "label": label} for key, label in PROJECT_TYPES],
        "groups": groups,
        "tags": tags,
        "owners": owners,
        "audiences": audiences,
        # 담당자 명부 — 자동완성이 이것을 먼저 쓰고, 없는 이름이면 화면에서 물어본다.
        "people": settings_service.known_names(),
        "project_code": settings_service.project_code(),
        "vault": str(get_settings().vault_dir),
        "report_cycle_days": get_settings().report_cycle_days,
    }


@router.post("/reindex")
def reindex(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    indexed, problems = reindex_all(conn)
    return {
        "indexed": indexed,
        # 읽지 못한 파일은 조용히 넘기지 않고 화면에 알린다.
        "problems": [{"path": item.rel_path, "reason": item.reason} for item in problems],
    }
