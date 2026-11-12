"""연말 회고 카드 (TODO 285) — 팀원마다 엽서 한 장(100 × 148mm)에 그 해의 한 일과 팀장의 감사 편지.

사용자(2026-11-12): *"26년 한해를 회고하는 형태로 크리스마스 전에 책과 함께 선물을 주고 싶은데 그 책 속에 카드 형태로 했던 업무와 감사의 마음을 전하고 싶어."*
*"엽서 크기로 … 사람당 한장씩 … A4로 사내에서 출력해서 엽서에 붙이면 되니깐."*

* 재료 — 나의 한 해(person_history.year_review: 마친 · 맡은 과제 · 중간 성과 · 교육 · 새로 쓴 보유 기술), 담당과 역할(역할 · 결과 · **인정 한 줄**).
* 새로 남기는 것 — 사람마다 · 해마다 `people/<이름>/yearcards/<해>.md` — 머리 정보에 카드에 넣을 과제(최대 3) · 한 줄 제목, 본문이 **감사 편지**.
  **팀장 · 관리자만** 본다(`share.BLOCKED_PREFIXES` 의 `/api/yearcards` — 팀원 · 읽기 PC 에는 막힘). 팀원 화면 · 업무 이력 파일 · 검색에 나오지 않는다.
* 넣지 않는 것 — 면담 기록 · 효과 금액 · 다른 사람과의 비교(242 — 숫자는 본인 것만).
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from .. import clock
from ..config import get_settings
from ..vault import markdown as md
from ..vault import paths
from . import settings as settings_service

PICK_MAX = 3
MESSAGE_MAX = 400          # 엽서 한 장에 들어갈 만큼 — 화면이 넘침을 따로 알린다
HEADLINE_MAX = 40
_YEAR = re.compile(r"^\d{4}$")


class YearCardError(ValueError):
    pass


def _check_year(year: str) -> str:
    if not _YEAR.match(year or ""):
        raise YearCardError("해는 네 자리 숫자입니다.")
    return year


def card_path(name: str, year: str) -> Path:
    base = get_settings().people_dir
    return paths.safe_join(base, paths.slugify(name), "yearcards", f"{_check_year(year)}.md")


def _stored(name: str, year: str) -> dict[str, Any]:
    path = card_path(name, year)
    if not path.is_file():
        return {"message": "", "projects": None, "headline": "", "updated_at": ""}
    doc = md.load(path)
    projects = doc.meta.get("projects")
    return {"message": doc.body.strip(), "projects": [str(p) for p in projects] if isinstance(projects, list) else None,
            "headline": str(doc.meta.get("headline") or ""), "updated_at": str(doc.meta.get("updated_at") or "")}


def _first_line(text: str) -> str:
    for line in (text or "").splitlines():
        line = re.sub(r"^\s*[-•·*]\s*", "", line).strip()
        if line:
            return line[:120]
    return ""


def candidates(conn: sqlite3.Connection, name: str, year: str) -> list[dict[str, Any]]:
    """카드에 넣을 수 있는 과제 — 그 해에 맡았던 과제. 마친 과제 · 인정 한 줄이 있는 과제가 앞."""
    from .person_history import history

    out = []
    for item in history(conn, name)["projects"]:
        start = (item.get("from") or "")[:4] or item["year"]
        end = (item.get("to") or "")[:4] or str(clock.today().year)
        if not (start <= year <= end):
            continue
        out.append({"id": item["id"], "title": item["title"], "status": item["status"], "role": item["role"],
                    "did": _first_line(item["did"]), "result": _first_line(item["result"]) or _first_line(item.get("outcome") or ""),
                    "praise": item["praise"], "done_this_year": item["status"] == "done" and end == year})
    out.sort(key=lambda c: (not c["done_this_year"], not c["praise"], not c["result"], c["id"]))
    return out


def card(conn: sqlite3.Connection, name: str, year: str) -> dict[str, Any]:
    from .person_history import year_review

    _check_year(year)
    review = year_review(conn, name, year)
    options = candidates(conn, name, year)
    stored = _stored(name, year)
    chosen = stored["projects"] if stored["projects"] is not None else [c["id"] for c in options[:PICK_MAX]]
    picked = [c for pid in chosen for c in options if c["id"] == pid][:PICK_MAX]
    roster = {p["name"]: p for p in settings_service.people()}
    missing = []
    if not stored["message"]:
        missing.append("감사 편지")
    if not picked:
        missing.append("넣을 과제")
    elif not any(c["result"] for c in picked):
        missing.append("과제 결과")
    return {
        "name": name, "year": year, "leader": bool(roster.get(name, {}).get("leader")),
        "numbers": {"projects": review["projects"], "done": review["done"], "milestones": review["milestones"],
                    "activities": review["activities"], "hours": review["hours"], "reports": review["reports"]},
        "new_skills": review["new_skills"][:6],
        "candidates": options, "picked": picked, "chosen": [c["id"] for c in picked],
        "message": stored["message"], "headline": stored["headline"], "updated_at": stored["updated_at"],
        "saved": card_path(name, year).is_file(), "missing": missing,
        "signer": settings_service.current_author(None) or "",
    }


def listing(conn: sqlite3.Connection, year: str) -> dict[str, Any]:
    """그 해의 카드 — 명부의 지금 사람(그 해 안에 떠난 사람도)마다 준비 상태."""
    _check_year(year)
    people = []
    for person in settings_service.people():
        left_on = str(person.get("left_on") or "")
        if left_on and left_on[:4] < year:
            continue
        data = card(conn, person["name"], year)
        people.append({"name": person["name"], "leader": data["leader"], "left_on": left_on, "saved": data["saved"],
                       "missing": data["missing"], "picked": len(data["picked"]), "has_message": bool(data["message"])})
    return {"year": year, "people": people, "pick_max": PICK_MAX, "message_max": MESSAGE_MAX}


def save(conn: sqlite3.Connection, name: str, year: str, data: dict[str, Any], by: str = "") -> dict[str, Any]:
    _check_year(year)
    name = " ".join((name or "").split())
    if not name:
        raise YearCardError("사람 이름이 비어 있습니다.")
    message = str(data.get("message") or "").replace("\r\n", "\n").strip()
    if len(message) > MESSAGE_MAX:
        raise YearCardError(f"감사 편지는 {MESSAGE_MAX}자까지입니다(지금 {len(message)}자) — 엽서 한 장에 들어가게.")
    headline = " ".join(str(data.get("headline") or "").split())
    if len(headline) > HEADLINE_MAX:
        raise YearCardError(f"한 줄 제목은 {HEADLINE_MAX}자까지입니다.")
    options = {c["id"] for c in candidates(conn, name, year)}
    projects = [str(p) for p in (data.get("projects") or []) if str(p) in options]
    projects = list(dict.fromkeys(projects))[:PICK_MAX]
    path = card_path(name, year)
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {"person": name, "year": year, "headline": headline, "projects": projects,
            "updated_at": clock.now().replace(microsecond=0).isoformat(), "updated_by": by}
    md.save(path, md.MarkdownDoc(meta, message + "\n" if message else ""))
    return card(conn, name, year)
