"""팀원 역량 이력 (TODO 72). 과제와 이어지지 않는 별개의 기록이다."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..deps import get_db
from ..services import activities as svc
from ..vault.paths import FileInUseError, InvalidDateError

router = APIRouter(prefix="/api/activities", tags=["activities"])


class ActivityIn(BaseModel):
    person: str | None = None
    date: str | None = None
    kind: str | None = None
    title: str | None = None
    host: str | None = None
    place: str | None = None
    # 시간·비용은 옵션이다. 비워 두는 것이 정상이므로 None 과 "" 를 모두 받는다.
    hours: float | str | None = None
    cost: float | str | None = None
    takeaway: str | None = None
    link: str | None = None
    tags: list[str] | None = None
    body: str | None = None

    def changes(self) -> dict:
        return self.model_dump(exclude_unset=True)


@router.get("")
def list_activities(
    conn: sqlite3.Connection = Depends(get_db),
    person: str | None = None,
    kind: str | None = None,
    year: str | None = Query(None, pattern=r"^(\d{4})?$"),
    q: str | None = None,
) -> list[dict]:
    return svc.listing(conn, person=person or None, kind=kind or None,
                       year=year or None, q=(q or "").strip() or None)


@router.get("/summary")
def summary(
    conn: sqlite3.Connection = Depends(get_db),
    year: str | None = Query(None, pattern=r"^(\d{4})?$"),
) -> dict:
    return svc.summary(conn, year=year or None)


@router.post("", status_code=201)
def create_activity(payload: ActivityIn, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    try:
        activity_id = svc.create(conn, payload.model_dump())
    except InvalidDateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": activity_id}


@router.patch("/{activity_id}")
def update_activity(
    activity_id: int, payload: ActivityIn, conn: sqlite3.Connection = Depends(get_db)
) -> dict:
    try:
        svc.update(conn, activity_id, payload.changes())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다.") from exc
    except InvalidDateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileInUseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True}


@router.delete("/{activity_id}", status_code=204)
def delete_activity(activity_id: int, conn: sqlite3.Connection = Depends(get_db)) -> None:
    try:
        svc.delete(conn, activity_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다.") from exc
    except FileInUseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
