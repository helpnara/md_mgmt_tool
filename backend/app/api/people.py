"""담당자 명부.

담당자는 지금 그냥 문자열이라 `권경락` / `권 경락` / `권경락 책임` 이 따로 쌓인다.
**지금도 문제이고**, 나중에 계정을 붙일 때는 더 큰 문제가 된다.

명부는 그 앞단계다. 표준 이름을 모아 두고 자동완성이 그것을 쓰게 한다.
사번·계정 칸은 지금 비어 있는 것이 정상이다 — 로그인이 생길 때 채운다.
"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
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
    # 이 사람의 PC 주소 (TODO 233). **보내지 않으면 지금 값을 물려준다** — IP 칸이 없는 옛 화면이 저장해도 지워지지 않게
    ips: list[str] | None = None
    # 팀장 (TODO 235) — 한 명. 보내지 않으면 지금 값을 물려준다
    leader: bool | None = None
    # 275 — 화면에서 이름 칸을 고쳤으면 옛 이름. 계정 · PC 주소 · 팀장 표시를 옛 이름으로 찾아 물려준다(예전엔 새 이름으로 찾아 잃었다)
    former: str | None = None


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


# 설정 파일을 쓰는 끝점은 쓰기 잠금 안에서 (TODO 202 ㉓) — `get_db` 가 쓰기 요청의 차례를 세운다.
# 잠금 밖이면 명부 저장과 기록 추가(명부에 이름을 더한다)가 겹칠 때 한쪽이 사라졌다.

@router.put("")
def replace_people(payload: PeopleUpdate, request: Request, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    # 화면이 안 보내는 칸(account, TODO 126 · ips, TODO 233)은 지금 값을 물려준다.
    current = {person["name"]: person for person in settings_service.people()}
    rows = []
    for person in payload.people:
        row = person.model_dump()
        former = (row.pop("former", None) or "").strip()
        kept = current.get(former or row["name"].strip(), {}) or current.get(row["name"].strip(), {})
        if row.get("account") is None:
            row["account"] = kept.get("account", "")
        if row.get("ips") is None:
            row["ips"] = list(kept.get("ips") or [])
        if row.get("leader") is None:
            row["leader"] = bool(kept.get("leader"))
        rows.append(row)
    # 팀장 PC 에서는 팀장 지정 · 팀장 PC 주소 · 팀장의 떠난 날을 바꾸지 않는다 (TODO 247) — 관리자(서버 PC)의 일
    from .. import permissions, who

    if who.of(request).role == who.LEADER and \
            permissions.leader_signature(rows) != permissions.leader_signature(settings_service.people()):
        raise HTTPException(status_code=403, detail=permissions.ADMIN_ONLY_DETAIL)
    try:
        return {"people": settings_service.save({"people": rows})["people"]}
    except ValueError as exc:  # 틀린 떠난 날 · 겹친 이름 (TODO 205)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/visitors")
def visitors() -> dict:
    """오늘 바깥에서 접속한 주소 · 누구로 알아봤는지 (TODO 233) — 설정 → 명부에서 등록 안 된 주소를 사람에게 붙인다.

    `/api/people` 아래라 바깥(팀원 · 읽기)에는 막혀 있다(share.BLOCKED_PREFIXES).
    """
    from .. import share, who

    mapping = who.ip_map()
    items = []
    for item in share.visitor_list():
        try:
            ip = who.normalize_ip(item["ip"])
        except ValueError:
            continue
        items.append({**item, "ip": ip, "name": mapping.get(ip, "")})
    return {"items": items}


@router.post("", status_code=201)
def add_person(payload: AddPerson, conn: sqlite3.Connection = Depends(get_db)) -> dict:
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
