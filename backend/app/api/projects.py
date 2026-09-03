from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import FINISHED_STATUSES, STATUS_KEYS, get_settings
from ..deps import get_db
from ..vault.markdown import ExternalChangeError
from ..vault.paths import FileInUseError
from ..services import projects as svc
from ..services import search as search_svc
from ..services import settings as settings_service
from ..schemas import ProjectCreate, ProjectUpdate

router = APIRouter(prefix="/api/projects", tags=["projects"])

SORTS = {
    "updated": "p.updated_at DESC",
    # 마지막 보고가 오래된 과제부터. 보고한 적 없는 과제가 맨 앞에 온다.
    "reported": "CASE WHEN p.last_reported_at IS NULL THEN 0 ELSE 1 END, p.last_reported_at ASC",
    "due": "CASE WHEN p.due_date IS NULL THEN 1 ELSE 0 END, p.due_date ASC",
    "title": "p.title ASC",
    "created": "p.created_at DESC",
    # 효과가 큰 과제부터. 실증효과가 있으면 그것을, 없으면 기대효과를 기준으로 본다.
    # 효과를 안 적은 과제는 맨 뒤로 보낸다 (0으로 취급하면 실제 0원 과제와 섞인다).
    "effect": (
        "CASE WHEN COALESCE(p.effect_verified, p.effect_expected) IS NULL THEN 1 ELSE 0 END,"
        " COALESCE(p.effect_verified, p.effect_expected) DESC, p.title ASC"
    ),
}


def _tags(conn: sqlite3.Connection, project_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT t.name FROM tag t JOIN project_tag pt ON pt.tag_id = t.id WHERE pt.project_id = ? ORDER BY t.name",
        (project_id,),
    ).fetchall()
    return [row["name"] for row in rows]


def _owners(conn: sqlite3.Connection, project_id: str) -> list[str]:
    return [
        row["name"]
        for row in conn.execute(
            "SELECT name FROM project_owner WHERE project_id = ? ORDER BY position, name",
            (project_id,),
        )
    ]


def _serialize(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "status": row["status"],
        "type": row["type"],
        "group": row["grp"],
        "owners": _owners(conn, row["id"]),
        "start_date": row["start_date"],
        "due_date": row["due_date"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_reported_at": row["last_reported_at"],
        # 효과 금액 (억원/년). 실증효과는 과제가 끝나야 나오므로 대개 비어 있다.
        "effect_expected": row["effect_expected"],
        "effect_verified": row["effect_verified"],
        # 과제를 등록한 사람 (담당자와 다르다). 로그인이 생기면 자동으로 채워진다.
        "created_by": row["created_by"],
        "tags": _tags(conn, row["id"]),
        "entry_count": conn.execute(
            "SELECT COUNT(*) AS n FROM entry WHERE project_id = ?", (row["id"],)
        ).fetchone()["n"],
    }


# 마감 기준 빠른 필터.
# 끝난 과제(완료·중단)는 빼 둔다 — 마감이 지났다고 경고할 이유가 없고,
# 무엇보다 대시보드가 세는 수와 이 필터가 거르는 수가 어긋나면 안 된다.
_NOT_FINISHED = f"p.status NOT IN ({','.join(repr(s) for s in FINISHED_STATUSES)})"
_UPCOMING = f"p.due_date IS NOT NULL AND p.due_date >= DATE('now', 'localtime') AND {_NOT_FINISHED}"
DUE_FILTERS = {
    "overdue": f"p.due_date IS NOT NULL AND p.due_date < DATE('now', 'localtime') AND {_NOT_FINISHED}",
    "7": f"{_UPCOMING} AND p.due_date <= DATE('now', 'localtime', '+7 day')",
    "14": f"{_UPCOMING} AND p.due_date <= DATE('now', 'localtime', '+14 day')",
    "30": f"{_UPCOMING} AND p.due_date <= DATE('now', 'localtime', '+30 day')",
}


@router.get("")
def list_projects(
    conn: sqlite3.Connection = Depends(get_db),
    status: str | None = None,
    type: str | None = None,
    group: str | None = None,
    tag: str | None = None,
    owner: str | None = None,
    q: str | None = None,
    due: str | None = None,
    sort: str = Query("updated"),
) -> list[dict]:
    where, params = [], []
    if status:
        where.append("p.status = ?")
        params.append(status)
    if type == "none":
        # 속성을 아직 안 정한 과제만. 대시보드의 '미지정' 칸이 이 값을 쓴다.
        where.append("(p.type IS NULL OR p.type = '')")
    elif type:
        where.append("p.type = ?")
        params.append(type)
    if group:
        where.append("p.grp = ?")
        params.append(group)
    if tag:
        where.append(
            "p.id IN (SELECT pt.project_id FROM project_tag pt JOIN tag t ON t.id = pt.tag_id WHERE t.name = ?)"
        )
        params.append(tag)
    if owner == "none":
        # 담당자를 아직 안 정한 과제만. 대시보드의 '미지정' 칸이 이 값을 쓴다.
        where.append("NOT EXISTS (SELECT 1 FROM project_owner po WHERE po.project_id = p.id)")
    elif owner:
        where.append("p.id IN (SELECT po.project_id FROM project_owner po WHERE po.name = ?)")
        params.append(owner)
    if due in DUE_FILTERS:
        where.append(DUE_FILTERS[due])
    if q and q.strip():
        # 과제 본문뿐 아니라 진행일지·첨부 파일명에 걸려도 그 과제를 남긴다.
        matched = search_svc.project_ids_matching(conn, q.strip())
        if not matched:
            return []
        where.append(f"p.id IN ({','.join('?' * len(matched))})")
        params.extend(matched)

    clause = f"WHERE {' AND '.join(where)}" if where else ""
    order = SORTS.get(sort, SORTS["updated"])
    rows = conn.execute(f"SELECT p.* FROM project p {clause} ORDER BY {order}", params).fetchall()
    return [_serialize(conn, row) for row in rows]


@router.post("", status_code=201)
def create_project(payload: ProjectCreate, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    try:
        project_id = svc.create_project(conn, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    row = conn.execute("SELECT * FROM project WHERE id = ?", (project_id,)).fetchone()
    return _serialize(conn, row)


@router.get("/{project_id}")
def get_project(project_id: str, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    row = conn.execute("SELECT * FROM project WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="과제를 찾을 수 없습니다.")
    data = _serialize(conn, row)
    data["body"] = row["body"]
    data["dir_name"] = row["dir_name"]
    # 상단 요약에 쓸 값 — 펼쳐 보지 않아도 상태를 알 수 있게 한다.
    from ..services.reports import unreported_entries

    data["unreported_entries"] = len(unreported_entries(conn, project_id))
    data["report_count"] = conn.execute(
        "SELECT COUNT(*) AS n FROM report WHERE project_id = ?", (project_id,)
    ).fetchone()["n"]
    files = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(size_bytes), 0) AS bytes FROM attachment WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    data["attachment_count"] = files["n"]
    data["attachment_bytes"] = files["bytes"]
    # 새 진행일지를 빈칸이 아니라 서식에서 시작하도록 함께 실어 보낸다.
    data["entry_template"] = settings_service.entry_template(row["type"])
    return data


@router.patch("/{project_id}")
def update_project(
    project_id: str, payload: ProjectUpdate, conn: sqlite3.Connection = Depends(get_db)
) -> dict:
    try:
        svc.update_project(conn, project_id, payload.changes())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="과제를 찾을 수 없습니다.") from exc
    except ExternalChangeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileInUseError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return get_project(project_id, conn)


@router.post("/{project_id}/archive", status_code=204)
def archive_project(project_id: str, conn: sqlite3.Connection = Depends(get_db)) -> None:
    try:
        svc.archive_project(conn, project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="과제를 찾을 수 없습니다.") from exc
    except FileInUseError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc
