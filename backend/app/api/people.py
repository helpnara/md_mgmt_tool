"""담당자 명부.

담당자는 지금 그냥 문자열이라 `권경락` / `권 경락` / `권경락 책임` 이 따로 쌓인다.
**지금도 문제이고**, 나중에 계정을 붙일 때는 더 큰 문제가 된다.

명부는 그 앞단계다. 표준 이름을 모아 두고 자동완성이 그것을 쓰게 한다.
사번·계정 칸은 지금 비어 있는 것이 정상이다 — 로그인이 생길 때 채운다.
"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import get_db
from ..services import people as svc
from ..services import settings as settings_service
from ..vault.markdown import ExternalChangeError

router = APIRouter(prefix="/api/people", tags=["people"])


class Person(BaseModel):
    name: str
    employee_id: str = ""
    # 화면에서 뺀 칸 (TODO 126). **보내지 않으면 지우지 않고 그대로 둔다** —
    # 손으로 적어 둔 것이 있을 수 있고, 나중에 사내 인증을 붙이면 칸만 되살리면 된다.
    account: str | None = None
    # 떠난 날과 사유 (TODO 122). 비어 있으면 지금 있는 사람이다.
    left_on: str = ""
    left_reason: str = ""


class PeopleUpdate(BaseModel):
    people: list[Person]


class AddPerson(BaseModel):
    name: str


class Rename(BaseModel):
    old: str
    new: str


class Handover(BaseModel):
    old: str
    new: str
    # 끝난 과제까지 바꿀지. 기본은 **바꾸지 않는다** — 지난 성과는 사실이다.
    include_finished: bool = False


@router.get("")
def list_people(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return svc.overview(conn)


@router.put("")
def replace_people(payload: PeopleUpdate) -> dict:
    # 화면이 안 보내는 칸(account, TODO 126)은 지금 값을 물려준다.
    kept = {person["name"]: person.get("account", "") for person in settings_service.people()}
    rows = []
    for person in payload.people:
        row = person.model_dump()
        if row.get("account") is None:
            row["account"] = kept.get(row["name"], "")
        rows.append(row)
    return {"people": settings_service.save({"people": rows})["people"]}


@router.post("", status_code=201)
def add_person(payload: AddPerson) -> dict:
    """화면에서 "명부에 없는 이름입니다 — 추가할까요?" 에 예를 눌렀을 때."""
    try:
        return {"people": settings_service.add_person(payload.name)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/handover")
def handover(payload: Handover, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """담당자를 넘긴다 (TODO 122). 표기 통일(`/rename`)과 뜻이 다르다."""
    try:
        return svc.handover(
            conn, payload.old, payload.new, include_finished=payload.include_finished
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ExternalChangeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/rename")
def rename(payload: Rename, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """이미 쓰인 표기를 한 번에 바꾼다 (과제 파일까지 반영)."""
    try:
        return svc.rename_owner(conn, payload.old, payload.new)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ExternalChangeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
