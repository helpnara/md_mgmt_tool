"""팀원 면담 (TODO 182). 역량 이력과 다른 표 · 다른 폴더 — 통합 검색 · AI 요약 · 내보내기에 넣지 않는다."""
from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..deps import RowId, get_db
from ..services import meetings as svc
from ..vault.paths import FileInUseError, InvalidDateError

router = APIRouter(prefix="/api/meetings", tags=["meetings"])


class MeetingIn(BaseModel):
    person: str | None = None
    date: str | None = None
    kind: str | None = None
    summary: str | None = None
    # 하기로 한 것 — [{"text": "…", "done": "2026-10-03" | null}]
    followups: list[Any] | None = None
    next_date: str | None = None
    body: str | None = None

    def changes(self) -> dict:
        return self.model_dump(exclude_unset=True)


@router.get("")
def list_meetings(
    conn: sqlite3.Connection = Depends(get_db),
    person: str | None = None,
    year: str | None = Query(None, pattern=r"^(\d{4})?$"),
) -> dict:
    return {
        "items": svc.listing(conn, person=person or None, year=year or None),
        # 팀 전체의 아직 닫지 않은 "하기로 한 것" — 사람을 고르지 않았을 때 화면이 세운다
        "open_followups": svc.open_followups(conn),
    }


@router.post("", status_code=201)
def create_meeting(payload: MeetingIn, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    try:
        return {"id": svc.create(conn, payload.model_dump())}
    except (InvalidDateError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{meeting_id}")
def update_meeting(meeting_id: RowId, payload: MeetingIn, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    try:
        svc.update(conn, meeting_id, payload.changes())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="면담 기록을 찾을 수 없습니다.") from exc
    except (InvalidDateError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileInUseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True}


@router.delete("/{meeting_id}", status_code=204)
def delete_meeting(meeting_id: RowId, conn: sqlite3.Connection = Depends(get_db)) -> None:
    try:
        svc.delete(conn, meeting_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="면담 기록을 찾을 수 없습니다.") from exc
    except FileInUseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
