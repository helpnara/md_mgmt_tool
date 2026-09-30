"""과제 접수 풀 (TODO 136). 설계는 docs/TODO.md 136 에 있다."""
from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..config import CLASSIFICATION_KEYS, INTAKE_POOL_STATUSES, INTAKE_STATUS_KEYS
from ..deps import get_db
from ..services import intakes as svc
from ..services import settings as settings_service
from ..vault.markdown import ExternalChangeError
from ..vault.paths import FileInUseError

router = APIRouter(tags=["intakes"])


class PartnerIn(BaseModel):
    team: str
    people: list[str] | str = Field(default_factory=list)


class IntakeCreate(BaseModel):
    title: str
    leader: str | None = None
    leader_team: str | None = None
    nature: str | None = None
    category: str | None = None
    delivery: str | None = None
    cost_kind: str | None = None
    start_date: str | None = None
    due_date: str | None = None
    effect_request: float | None = None
    priority: str | None = None
    priority_note: str | None = None
    received_on: str | None = None
    tags: list[str] = Field(default_factory=list)
    body: str | None = None


class IntakeUpdate(BaseModel):
    title: str | None = None
    leader: str | None = None
    leader_team: str | None = None
    nature: str | None = None
    category: str | None = None
    delivery: str | None = None
    cost_kind: str | None = None
    start_date: str | None = None
    due_date: str | None = None
    effect_request: float | None = None
    priority: str | None = None
    priority_note: str | None = None
    picked: bool | None = None
    received_on: str | None = None
    tags: list[str] | None = None
    body: str | None = None

    def changes(self) -> dict[str, Any]:
        # 보낸 칸만 — null 이면 그 칸을 비우겠다는 뜻이다
        return self.model_dump(exclude_unset=True)


class StatusChange(BaseModel):
    status: str
    note: str | None = None
    merged_into: str | None = None


class Promotion(BaseModel):
    title: str | None = None
    type: str | None = None
    status: str | None = None
    owners: list[str] = Field(default_factory=list)
    partners: list[PartnerIn] = Field(default_factory=list)
    start_date: str | None = None
    due_date: str | None = None
    effect_expected: float | None = None
    nature: str | None = None
    category: str | None = None
    delivery: str | None = None
    cost_kind: str | None = None
    tags: list[str] = Field(default_factory=list)
    decision_note: str | None = None


class LogIn(BaseModel):
    date: str | None = None
    title: str | None = None
    body: str | None = None
    tags: list[str] | None = None
    # 편집을 시작할 때 읽어 둔 파일 시각 — 그 사이 밖에서 고쳤으면 덮어쓰지 않는다
    mtime: float | None = None


def _errors(call):
    """서비스의 거절을 화면이 읽을 수 있는 응답으로 옮긴다."""
    try:
        return call()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="접수를 찾을 수 없습니다.") from exc
    except svc.IntakeClosedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ExternalChangeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileInUseError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=507, detail=str(exc)) from exc


SORTS = {
    # 오래 기다린 것부터 — 풀의 기본. 요청자에게 가장 나쁜 것은 답이 없는 것이다.
    "age": "COALESCE(i.received_on, '9999') ASC, i.id ASC",
    "received": "COALESCE(i.received_on, '') DESC, i.id DESC",
    "priority": ("CASE i.priority WHEN '상' THEN 0 WHEN '중' THEN 1 WHEN '하' THEN 2 ELSE 3 END,"
                 " COALESCE(i.received_on, '9999') ASC"),
    "id": "i.id ASC",
    "title": "i.title ASC",
    "status": "i.status ASC, i.id ASC",
    "effect": "CASE WHEN i.effect_request IS NULL THEN 1 ELSE 0 END, i.effect_request DESC, i.id ASC",
    "decided": "COALESCE(i.decided_on, '') DESC, i.id DESC",
}


@router.get("/api/intakes")
def list_intakes(
    conn: sqlite3.Connection = Depends(get_db),
    # pool = 아직 판정이 안 났거나 보류(기본) · closed = 판정이 난 것 · all = 전부
    scope: str = Query("pool", pattern="^(pool|closed|all)$"),
    status: str | None = None,
    nature: str | None = None,
    category: str | None = None,
    delivery: str | None = None,
    cost_kind: str | None = None,
    priority: str | None = None,
    team: str | None = None,
    year: str | None = Query(None, pattern=r"^(\d{4})?$"),
    picked: str | None = Query(None, pattern="^(1)?$"),
    stale: str | None = Query(None, pattern="^(1)?$"),
    # 판정일의 연도 — 요약의 "올해 착수 N" 이 이리로 이어진다 (세는 곳과 거르는 곳이 같아야 한다)
    decided_year: str | None = Query(None, pattern=r"^(\d{4})?$"),
    q: str | None = None,
    sort: str = Query("age"),
    order: str | None = Query(None, pattern="^(asc|desc)$"),
) -> dict:
    where: list[str] = []
    params: list[Any] = []
    pool_marks = ",".join("?" for _ in INTAKE_POOL_STATUSES)
    if status and status in INTAKE_STATUS_KEYS:
        where.append("i.status = ?")
        params.append(status)
    elif scope == "pool":
        where.append(f"i.status IN ({pool_marks})")
        params.extend(INTAKE_POOL_STATUSES)
    elif scope == "closed":
        where.append(f"i.status NOT IN ({pool_marks})")
        params.extend(INTAKE_POOL_STATUSES)
    for column, value in (("nature", nature), ("category", category),
                          ("delivery", delivery), ("cost_kind", cost_kind)):
        if value == "none":
            where.append(f"(i.{column} IS NULL OR TRIM(i.{column}) = '')")
        elif value:
            where.append(f"TRIM(i.{column}) = ?")
            params.append(value)
    if priority == "none":
        where.append("i.priority IS NULL")
    elif priority:
        where.append("i.priority = ?")
        params.append(priority)
    if team:
        where.append("TRIM(i.leader_team) = ?")
        params.append(team)
    if year:
        where.append("SUBSTR(i.received_on, 1, 4) = ?")
        params.append(year)
    if picked:
        where.append("i.picked = 1")
    if decided_year:
        where.append("SUBSTR(i.decided_on, 1, 4) = ?")
        params.append(decided_year)
    if q and q.strip():
        needle = f"%{q.strip()}%"
        where.append("(i.title LIKE ? OR i.id LIKE ? OR i.leader LIKE ? OR i.leader_team LIKE ?"
                     " OR i.tags LIKE ? OR i.body LIKE ?)")
        params.extend([needle] * 6)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    order_by = SORTS.get(sort, SORTS["age"])
    if order == "desc" and sort in ("age", "id", "title", "status"):
        order_by = order_by.replace(" ASC", " DESC")
    elif order == "asc" and sort in ("received", "decided"):
        order_by = order_by.replace(" DESC", " ASC")
    # 열 머리를 눌러 뒤집는 두 가지 (TODO 154) — 비어 있는 값은 어느 쪽이든 맨 뒤
    elif order == "asc" and sort == "effect":
        order_by = "CASE WHEN i.effect_request IS NULL THEN 1 ELSE 0 END, i.effect_request ASC, i.id ASC"
    elif order == "desc" and sort == "priority":
        order_by = ("CASE i.priority WHEN '하' THEN 0 WHEN '중' THEN 1 WHEN '상' THEN 2 ELSE 3 END,"
                    " COALESCE(i.received_on, '9999') ASC")
    rows = conn.execute(f"SELECT i.* FROM intake i {clause} ORDER BY {order_by}", params).fetchall()
    stale_days = settings_service.intake_stale_days()
    items = [svc.serialize(row, stale_days) for row in rows]
    if stale:
        # 묵힘은 날짜 셈이라 SQL 보다 여기서 가르는 편이 규칙이 한 곳에 모인다 (svc.is_stale)
        items = [item for item in items if item["stale"]]
    teams = [row["t"] for row in conn.execute(
        "SELECT DISTINCT TRIM(leader_team) AS t FROM intake WHERE leader_team IS NOT NULL"
        " AND TRIM(leader_team) <> '' ORDER BY t"
    )]
    years = [row["y"] for row in conn.execute(
        "SELECT DISTINCT SUBSTR(received_on, 1, 4) AS y FROM intake WHERE received_on IS NOT NULL"
        " ORDER BY y DESC"
    )]
    return {"items": items, "summary": svc.summary(conn), "teams": teams, "years": years}


@router.get("/api/intakes/next-id")
def next_id(received_on: str | None = None) -> dict:
    """이 접수일로 등록하면 붙을 번호 (과제의 next-id 와 같은 뜻)."""
    return {"id": svc.next_intake_id(svc.intake_year(received_on))}


@router.post("/api/intakes", status_code=201)
def create_intake(payload: IntakeCreate, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    intake_id = _errors(lambda: svc.create_intake(conn, payload.model_dump()))
    return get_intake(intake_id, conn)


@router.get("/api/intakes/{intake_id}")
def get_intake(intake_id: str, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    def load() -> dict:
        row = svc._row(conn, intake_id)
        data = svc.serialize(row)
        data["body"] = row["body"]
        data["file_mtime"] = row["file_mtime"]
        data["logs"] = svc.list_logs(conn, intake_id)
        data["attachments"] = svc.list_attachments(conn, intake_id)
        # 이어진 과제가 아직 있는지 — 과제를 지웠으면 링크 대신 그렇다고 말한다
        linked = row["project_id"] or row["merged_into"]
        data["linked_project"] = None
        if linked:
            project = conn.execute("SELECT id, title, status FROM project WHERE id = ?", (linked,)).fetchone()
            data["linked_project"] = dict(project) if project else {"id": linked, "missing": True}
        return data

    return _errors(load)


@router.patch("/api/intakes/{intake_id}")
def update_intake(intake_id: str, payload: IntakeUpdate, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    _errors(lambda: svc.update_intake(conn, intake_id, payload.changes()))
    return get_intake(intake_id, conn)


@router.post("/api/intakes/{intake_id}/status")
def change_status(intake_id: str, payload: StatusChange, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    _errors(lambda: svc.set_status(conn, intake_id, payload.status, payload.note, payload.merged_into))
    return get_intake(intake_id, conn)


@router.get("/api/intakes/{intake_id}/promote")
def promotion_plan(intake_id: str, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """승격 화면이 미리 채워 보여 줄 값 — 사람이 확인하고 고친 뒤 승격한다."""
    return _errors(lambda: svc.promotion_plan(conn, intake_id))


@router.post("/api/intakes/{intake_id}/promote", status_code=201)
def promote(intake_id: str, payload: Promotion, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    data = payload.model_dump()
    data["partners"] = [
        {"team": item["team"], "people": item["people"]} for item in data.get("partners") or []
    ]
    project_id = _errors(lambda: svc.promote(conn, intake_id, data))
    return {"project_id": project_id, "intake": get_intake(intake_id, conn)}


@router.post("/api/intakes/{intake_id}/archive", status_code=204)
def archive(intake_id: str, conn: sqlite3.Connection = Depends(get_db)) -> None:
    _errors(lambda: svc.archive_intake(conn, intake_id))


# ── 검토 기록 ──────────────────────────────────────────

@router.post("/api/intakes/{intake_id}/logs", status_code=201)
def create_log(intake_id: str, payload: LogIn, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    name = _errors(lambda: svc.create_log(conn, intake_id, payload.model_dump()))
    return {"name": name, "intake": get_intake(intake_id, conn)}


@router.patch("/api/intakes/{intake_id}/logs/{name}")
def update_log(intake_id: str, name: str, payload: LogIn, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    new_name = _errors(lambda: svc.update_log(conn, intake_id, name, payload.model_dump()))
    return {"name": new_name, "intake": get_intake(intake_id, conn)}


@router.delete("/api/intakes/{intake_id}/logs/{name}", status_code=204)
def delete_log(intake_id: str, name: str, conn: sqlite3.Connection = Depends(get_db)) -> None:
    _errors(lambda: svc.delete_log(conn, intake_id, name))


# ── 첨부 ──────────────────────────────────────────────

@router.post("/api/intakes/{intake_id}/attachments", status_code=201)
def upload(intake_id: str, file: UploadFile = File(...), conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return _errors(lambda: svc.save_attachment(conn, intake_id, file.filename or "attachment", file.file))


@router.get("/api/intakes/{intake_id}/attachments/preview")
def preview_attachment(
    intake_id: str, path: str = Query(...), conn: sqlite3.Connection = Depends(get_db)
) -> dict:
    """첨부 엑셀을 그 자리에서 훑어본다 (TODO 138 — 과제 첨부의 [내용 보기]와 같은 판)."""
    return _errors(lambda: svc.attachment_preview(conn, intake_id, path))


@router.delete("/api/intakes/{intake_id}/attachments", status_code=204)
def delete_attachment(
    intake_id: str, path: str = Query(...), conn: sqlite3.Connection = Depends(get_db)
) -> None:
    _errors(lambda: svc.delete_attachment(conn, intake_id, path))


@router.get("/intake-files/{dir_name}/{rel_path:path}")
def serve_file(dir_name: str, rel_path: str, conn: sqlite3.Connection = Depends(get_db)) -> FileResponse:
    """접수 본문의 상대 링크를 그대로 열기 위한 정적 서빙 (과제의 /files 와 같은 역할)."""
    if conn.execute("SELECT 1 FROM intake WHERE dir_name = ?", (dir_name,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="접수를 찾을 수 없습니다.")
    try:
        target = svc.attachment_file(dir_name, rel_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    return FileResponse(target)


# 목록 칸에 쓰는 분류 열쇠 — 화면과 서버가 같은 이름을 쓴다
CLASSIFICATION_FIELDS = CLASSIFICATION_KEYS
