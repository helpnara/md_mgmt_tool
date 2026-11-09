"""팀원별 경험 끝점 (TODO 257 · 253 의 2단계 — docs/팀원이력정리/2단계.md 4절).

누가 보나(2단계.md ②) — 관리자 · 팀장은 모두 보고 고친다. 팀원 PC 는 **자기 것 보기만**(쓰기는 permissions 의 허용 목록에 없어 403).
읽기 전용 공유 바깥은 막는다(share.BLOCKED_PREFIXES — 면담과 같은 결). 통합 검색 · 과제 내보내기에는 넣지 않는다.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel

from .. import who
from ..deps import get_db
from ..services import experiences as svc

router = APIRouter(prefix="/api/experiences", tags=["experiences"])
NOT_YOURS = "자기 경험만 볼 수 있습니다."


class ExperienceIn(BaseModel):
    person: str | None = None
    title: str | None = None
    project: str | None = None
    project_text: str | None = None
    affiliation: str | None = None
    start: str | None = None
    end: str | None = None
    role: str | None = None
    kind: str | None = None
    status: str | None = None
    situation: str | None = None
    goal: str | None = None
    actions: list[str] | None = None
    result_qual: str | None = None
    impact: str | None = None
    lesson: str | None = None
    lesson_source: str | None = None
    open_questions: list[str] | None = None
    skills: list[Any] | None = None
    quants: list[dict[str, Any]] | None = None
    evidences: list[dict[str, Any]] | None = None
    related: list[str] | None = None
    materials: list[str] | None = None
    base_updated_at: str | None = None

    def changes(self) -> dict:
        return self.model_dump(exclude_unset=True)


class DraftIn(BaseModel):
    person: str
    projects: list[str] | None = None   # 비우면 회고가 있는 맡은 과제 모두(2단계.md ④)


def _name(value: str) -> str:
    name = " ".join((value or "").split())
    if not name:
        raise HTTPException(status_code=400, detail="사람 이름이 비어 있습니다.")
    return name


@router.get("")
def list_experiences(request: Request, person: str = Query(..., min_length=1, max_length=40),
                     conn: sqlite3.Connection = Depends(get_db)) -> dict:
    user = who.of(request)
    name = user.name if user.role == who.MEMBER else _name(person)
    return {"person": name, **svc.listing(conn, name)}


@router.get("/{experience_id}")
def get_experience(experience_id: str, request: Request, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    try:
        item = svc.get(conn, experience_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="그런 경험이 없습니다.") from exc
    user = who.of(request)
    if user.role == who.MEMBER and item["person"] != user.name:
        raise HTTPException(status_code=403, detail=NOT_YOURS)
    return item


@router.post("", status_code=201)
def create_experience(payload: ExperienceIn, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    data = payload.changes()
    data.pop("base_updated_at", None)
    data["source"] = "직접"
    try:
        experience_id = svc.create(conn, data)
    except svc.ExperienceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return svc.get(conn, experience_id)


@router.post("/draft", status_code=201)
def create_drafts(payload: DraftIn, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """담당과 역할 · 회고에서 초안(2단계.md 5절). 과제를 고르지 않으면 회고가 있는 맡은 과제 모두."""
    name = _name(payload.person)
    projects = payload.projects
    if not projects:
        projects = [r["project_id"] for r in conn.execute(
            "SELECT project_id FROM project_contribution WHERE name = ? ORDER BY project_id", (name,))
            if svc.has_retro(conn, name, r["project_id"])]
    try:
        return svc.create_drafts(conn, name, projects)
    except svc.ExperienceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{experience_id}")
def update_experience(experience_id: str, payload: ExperienceIn, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    try:
        return svc.update(conn, experience_id, payload.changes())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="그런 경험이 없습니다.") from exc
    except svc.ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except svc.ExperienceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{experience_id}", status_code=204)
def delete_experience(experience_id: str, conn: sqlite3.Connection = Depends(get_db)) -> Response:
    try:
        svc.delete(conn, experience_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="그런 경험이 없습니다.") from exc
    return Response(status_code=204)
