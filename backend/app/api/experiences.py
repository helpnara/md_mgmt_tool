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
from ..services import experience_export as export_svc
from ..services import experience_import as imp
from ..services import skill_cleanup
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
    tools: list[str] | None = None
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


class ReadIn(BaseModel):
    person: str
    text: str
    projects: list[str] | None = None
    append_to: str | None = None        # [더 붙여넣기] — 앞서 읽은 응답 원문 이름


class Decision(BaseModel):
    index: int
    action: str = "새로"                 # 새로 · 이어서 · 버림
    target: str | None = None
    project: str | None = None
    choose: dict[str, str] | None = None  # 칸 → "old" · "new" (3단계.md ④)


class AckIn(BaseModel):
    code: str
    key: str = ""


class SkillRef(BaseModel):
    axis: str
    name: str


class MergeIn(BaseModel):
    source: SkillRef
    target: SkillRef


class RematchIn(BaseModel):
    person: str


class ExportIn(BaseModel):
    person: str
    scope: str = "all"
    start: str | None = None
    end: str | None = None
    ids: list[str] | None = None
    structured: bool | None = None
    ids_in: bool | None = None
    money: bool | None = None
    anonymize: bool | None = None
    how: str = "저장"           # 저장 · 복사 — 기록용


class CleanupIn(BaseModel):
    actions: list[dict[str, Any]]


class AnswerIn(BaseModel):
    text: str


class ImportIn(BaseModel):
    person: str
    response: str
    items: list[Decision]


MANAGERS_ONLY = "AI 로 정리 · 확정 · 역량 사전은 관리자 · 팀장만 합니다."


def _manager(request: Request) -> None:
    if not who.of(request).manages:
        raise HTTPException(status_code=403, detail=MANAGERS_ONLY)


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


# ── 응답 되받기 (TODO 258 · 3단계.md 4절) — "/{experience_id}" 보다 앞에 둔다 ─────

@router.get("/prompt")
def prompt(request: Request, person: str = Query(..., min_length=1, max_length=40),
           projects: str | None = Query(None, max_length=4000), conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """경험 정리 프롬프트 + 고를 수 있는 과제. `projects` 를 빼면 기본 과제(회고가 있고 아직 구조화 경험이 없는 것)."""
    _manager(request)
    chosen = None if projects is None else [p for p in projects.split(",") if p.strip()]
    try:
        return imp.build_prompt(conn, _name(person), chosen)
    except svc.ExperienceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/read")
def read_response(payload: ReadIn, request: Request, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """[읽기] — 응답 원문을 남기고 미리보기. 경험은 바꾸지 않는다."""
    _manager(request)
    try:
        return imp.read(conn, _name(payload.person), payload.text, payload.projects, payload.append_to)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="이어 붙일 응답 원문이 없습니다.") from exc
    except svc.ExperienceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/import")
def import_response(payload: ImportIn, request: Request, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """[저장] — 블록마다 새로 · 이어서 · 버림. 서버가 원문을 다시 읽는다. 상태는 구조화."""
    _manager(request)
    try:
        return imp.save(conn, _name(payload.person), payload.response, [item.model_dump() for item in payload.items])
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="그런 응답 원문이 없습니다.") from exc
    except svc.ExperienceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/responses/{person}/{name}")
def response_file(person: str, name: str, request: Request) -> dict:
    """응답 원문 보기(경험 상세의 재료). 팀원 PC 는 자기 것만."""
    user = who.of(request)
    if user.role == who.MEMBER and _name(person) != user.name:
        raise HTTPException(status_code=403, detail=NOT_YOURS)
    try:
        return imp.read_response_file(_name(person), name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="그런 응답 원문이 없습니다.") from exc


@router.get("/responses/{person}/{name}/summary")
def response_summary(person: str, name: str, request: Request, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """[실험 요약 복사](3단계.md 8절) — 값 없이 모양만."""
    _manager(request)
    try:
        return imp.summary(conn, _name(person), name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="그런 응답 원문이 없습니다.") from exc


# ── 역량 사전 (TODO 260 · 4단계.md 2절) — "/{experience_id}" 보다 앞에 ─────────

@router.get("/skills")
def skills(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """지금 쓰는 역량 사전 + 태그마다 쓰는 경험 수(사전 카드의 "쓰는 경험")."""
    from ..services import settings as settings_service

    return {"dictionary": settings_service.skill_dictionary(), "usage": svc.skill_usage(conn),
            "custom": settings_service.load().get("skill_dictionary") is not None}


@router.post("/skills/merge")
def merge_skill(payload: MergeIn, request: Request, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    _manager(request)
    try:
        return svc.merge_skill(conn, payload.source.model_dump(), payload.target.model_dump())
    except (svc.ExperienceError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/skills/rematch")
def rematch(payload: RematchIn, request: Request, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    _manager(request)
    return svc.rematch_person(conn, _name(payload.person))


# ── 보유 기술 사전 (TODO 273) ─────────────────────────────────────────────────

@router.get("/tools")
def tools(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """지금 쓰는 보유 기술 사전 + 이름마다 쓰인 횟수 + 사전에 없는데 쓰인 이름([쓰인 이름 불러오기])."""
    from ..experience import skills as skill_rules
    from ..experience import tools as tool_rules
    from ..services import settings as settings_service

    dictionary = settings_service.tool_dictionary()
    table = tool_rules.index(dictionary)
    usage: dict[str, int] = {}
    unlisted: dict[str, int] = {}
    for name, count in svc.used_tool_names(conn).items():
        canonical = table.get(skill_rules.key(name))
        if canonical:
            usage[canonical] = usage.get(canonical, 0) + count
        else:
            unlisted[name] = unlisted.get(name, 0) + count
    skill_names = set(skill_rules.index(settings_service.skill_dictionary()))
    return {"dictionary": dictionary, "usage": usage, "custom": settings_service.load().get("tool_dictionary") is not None,
            # 역량 사전에 있는 이름(회귀 분석 등)은 보유 기술 후보에서 뺀다 — 정의: 분석 기법 · 방법은 역량
            "unlisted": [{"name": n, "count": c, "skill_like": skill_rules.key(n) in skill_names}
                         for n, c in sorted(unlisted.items(), key=lambda p: (-p[1], p[0]))]}


@router.post("/tools/rematch")
def rematch_tools(request: Request, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """보유 기술 사전을 고친 뒤 — 모든 경험과 과제 색인을 지금 사전으로 다시 맞춘다."""
    _manager(request)
    from ..services import running

    with running.track("보유 기술 다시 맞추기", "tools-rematch"):
        return svc.rematch_tools(conn)


# ── 역량 태그 정리함 (TODO 262 · 261 — 역량태그입력.md) ──────────────────────

@router.get("/skills/unknown")
def unknown_tags(request: Request, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    _manager(request)
    return {"items": skill_cleanup.unknown_tags(conn)}


@router.post("/skills/cleanup")
def cleanup_tags(payload: CleanupIn, request: Request, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    _manager(request)
    try:
        return skill_cleanup.apply(conn, payload.actions)
    except (svc.ExperienceError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/skills/prompt")
def tag_prompt(request: Request, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    _manager(request)
    return skill_cleanup.tag_prompt(conn)


@router.post("/skills/answer")
def tag_answer(payload: AnswerIn, request: Request, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """AI 의 `태그 | 맞출 곳` 답 → 제안(적용하지 않는다)."""
    _manager(request)
    return {"items": skill_cleanup.read_answer(conn, payload.text)}


@router.post("/skills/suggest")
def add_suggested(request: Request) -> dict:
    _manager(request)
    return skill_cleanup.add_suggested()


# ── 업무 이력 파일 (TODO 262 · 5단계.md 3 ~ 5절) — 팀원 PC 는 자기 것만(⑥) ───────

def _own(request: Request, person: str) -> str:
    user = who.of(request)
    name = _name(person)
    if user.role == who.MEMBER and name != user.name:
        raise HTTPException(status_code=403, detail="자기 업무 이력 파일만 내보낼 수 있습니다.")
    return name


@router.get("/export")
def export_file(request: Request, person: str = Query(..., min_length=1, max_length=40), scope: str = "all",
                start: str | None = None, end: str | None = None, ids: str | None = None,
                structured: bool | None = None, ids_in: bool | None = None, money: bool | None = None,
                anonymize: bool | None = None, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """업무 이력 파일 글 + 요약 · 경고. 만들기만 한다(저장 · 복사는 화면이 이 글 그대로)."""
    name = _own(request, person)
    try:
        opt = export_svc.options({"scope": scope, "start": start, "end": end, "ids": (ids or "").split(",") if ids else [],
                                  "structured": structured, "ids_in": ids_in, "money": money, "anonymize": anonymize})
        return export_svc.render(conn, name, opt)
    except svc.ExperienceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/export/log", status_code=201)
def export_log(payload: ExportIn, request: Request, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """저장 · 복사했을 때 한 줄 — 누가 · 언제 · 누구의 · 범위 · 옵션(내용 없음, 5단계.md ⑧)."""
    name = _own(request, payload.person)
    user = who.of(request)
    try:
        opt = export_svc.options(payload.model_dump())
    except svc.ExperienceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = export_svc.render(conn, name, opt)
    from ..services import settings as settings_service

    by = user.name or settings_service.current_author(None) or ""
    export_svc.log(name, by, user.role, opt, len(result["ids"]), result["chars"], "복사" if payload.how == "복사" else "저장")
    return {"logged": True}


@router.get("/export/log")
def export_log_rows(request: Request, person: str = Query(..., min_length=1, max_length=40)) -> dict:
    return {"items": export_svc.log_rows(_own(request, person))}


@router.get("/anonymize/candidates")
def anonymize_candidates(request: Request, person: str = Query(..., min_length=1, max_length=40),
                         conn: sqlite3.Connection = Depends(get_db)) -> dict:
    name = _own(request, person)
    return {"items": export_svc.candidates(conn, name), **export_svc.anonymize_rules()}


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
def update_experience(experience_id: str, payload: ExperienceIn, request: Request, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """고치기 — 팀원 PC 는 자기 경험의 초안 · 구조화만(미들웨어가 막고, 여기서는 상태를 빼고 "팀원이 고침" 을 남긴다)."""
    try:
        return svc.update(conn, experience_id, payload.changes(), member=who.of(request).role == who.MEMBER)
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


# ── 정합성 · 확정 (TODO 260 · 4단계.md 3 · 4절) — 관리자 · 팀장만(⑦) ──────────────

def _by(request: Request) -> str:
    user = who.of(request)
    return user.name if user.role == who.LEADER else ""


@router.post("/{experience_id}/confirm")
def confirm(experience_id: str, request: Request, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    _manager(request)
    try:
        return svc.confirm(conn, experience_id, _by(request))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="그런 경험이 없습니다.") from exc
    except svc.ExperienceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{experience_id}/unconfirm")
def unconfirm(experience_id: str, request: Request, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    _manager(request)
    try:
        return svc.unconfirm(conn, experience_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="그런 경험이 없습니다.") from exc
    except svc.ExperienceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{experience_id}/acknowledge")
def acknowledge(experience_id: str, payload: AckIn, request: Request, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    _manager(request)
    try:
        return svc.acknowledge(conn, experience_id, payload.code, payload.key, _by(request))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="그런 경험이 없습니다.") from exc
    except svc.ExperienceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
