"""연말 회고 카드 (TODO 285) — 팀원마다 엽서 한 장(100 × 148mm)에 그 해의 한 일과 팀장의 감사 편지.

사용자(2026-11-12): *"26년 한해를 회고하는 형태로 크리스마스 전에 책과 함께 선물을 주고 싶은데 그 책 속에 카드 형태로 했던 업무와 감사의 마음을 전하고 싶어."*
*"엽서 크기로 … 사람당 한장씩 … A4로 사내에서 출력해서 엽서에 붙이면 되니깐."*

* 재료 — 나의 한 해(person_history.year_review: 마친 · 맡은 과제 · 중간 성과 · 교육 · 새로 쓴 보유 기술), 담당과 역할(역할 · 결과 · **인정 한 줄**).
* 새로 남기는 것 — 사람마다 · 해마다 `people/<이름>/yearcards/<해>.md` — 머리 정보에 카드에 넣을 과제(최대 3) · 한 줄 제목, 본문이 **감사 편지**.
  **팀장 · 관리자만** 본다(`share.BLOCKED_PREFIXES` 의 `/api/yearcards` — 팀원 · 읽기 PC 에는 막힘). 팀원 화면 · 업무 이력 파일 · 검색에 나오지 않는다.
* 넣지 않는 것 — 면담 기록 · 효과 금액 · 다른 사람과의 비교(242 — 숫자는 본인 것만).

TODO 286 — 과제마다 **수행 2줄 · 결과 2줄**(담당과 역할의 "내가 한 일" · "결과", 비면 같은 과제의 경험 — 확정 먼저 — 행동 · 정량),
**역량 3 · 보유 기술(도구) 3**(그 해 자주 나온 순). 줄은 카드에서만 다듬는다 — 머리 정보 `lines` 에 저장, 원본 과제 · 경험은 그대로.
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
PICK_DEFAULT = 2           # 처음엔 위 둘 — 팀장이 2 ~ 3개 고른다 (286)
LINE_COUNT = 2             # 과제마다 수행 · 결과 각 2줄
LINE_MAX = 80              # 한 줄 글자 — 엽서 한 줄 남짓
CHIP_MAX = 3               # 역량 · 보유 기술 각 3개
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
        return {"message": "", "projects": None, "headline": "", "updated_at": "", "lines": {}, "skills": None, "tools": None}
    doc = md.load(path)
    projects = doc.meta.get("projects")
    as_list = lambda value: [str(v) for v in value] if isinstance(value, list) else None  # noqa: E731
    lines = doc.meta.get("lines") if isinstance(doc.meta.get("lines"), dict) else {}
    return {"message": doc.body.strip(), "projects": as_list(projects),
            "headline": str(doc.meta.get("headline") or ""), "updated_at": str(doc.meta.get("updated_at") or ""),
            "lines": {str(k): v for k, v in lines.items() if isinstance(v, dict)},
            "skills": as_list(doc.meta.get("skills")), "tools": as_list(doc.meta.get("tools"))}


def _lines_of(text: str) -> list[str]:
    """글 → 줄 목록(앞의 - · • 를 떼고, 빈 줄 빼고, 한 줄은 LINE_MAX 자까지)."""
    out = []
    for line in (text or "").splitlines():
        line = re.sub(r"^\s*(?:[-•·*]|\d+[.)])\s*", "", line).strip()
        if line:
            out.append(line[:LINE_MAX])
    return out


def _year_experiences(name: str, year: str) -> list[dict[str, Any]]:
    """그 사람의 경험 중 그 해에 걸친 것 — 확정이 앞(기간이 없으면 넣는다: 과제로 해를 가른다)."""
    from . import experiences as exp

    folder = exp.person_dir(name)
    out = []
    for path in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        try:
            item = exp.read_file(path)
        except Exception:  # noqa: BLE001 — 깨진 파일 하나로 카드가 안 열리면 안 된다
            continue
        start, end = (item["start"] or "")[:4], (item["end"] or "")[:4]
        if (start and start > year) or (end and end < year):
            continue
        out.append(item)
    out.sort(key=lambda e: e["status"] != "확정")
    return out


def _quant_line(quant: dict[str, Any]) -> str:
    metric, value = str(quant.get("metric") or "").strip(), str(quant.get("value") or "").strip()
    return f"{metric} {value}".strip()[:LINE_MAX]


def candidates(conn: sqlite3.Connection, name: str, year: str, experiences: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """카드에 넣을 수 있는 과제 — 그 해에 맡았던 과제. 마친 과제 · 인정 한 줄 · 결과가 있는 과제가 앞.

    수행 · 결과 줄의 원본 — 담당과 역할의 "내가 한 일" · "결과"(결과가 비면 과제의 그 밖의 성과), 비면 같은 과제의 경험 행동 · 정량.
    """
    from .person_history import history

    if experiences is None:
        experiences = _year_experiences(name, year)
    out = []
    for item in history(conn, name)["projects"]:
        start = (item.get("from") or "")[:4] or item["year"]
        end = (item.get("to") or "")[:4] or str(clock.today().year)
        if not (start <= year <= end):
            continue
        linked = [e for e in experiences if e["project"] == item["id"]]
        did = _lines_of(item["did"]) or [a[:LINE_MAX] for e in linked for a in e["actions"] if a.strip()]
        result = _lines_of(item["result"]) or _lines_of(item.get("outcome") or "") \
            or [line for e in linked for line in map(_quant_line, e["quants"]) if line] \
            or [line for e in linked for line in _lines_of(e["result_qual"])]
        out.append({"id": item["id"], "title": item["title"], "status": item["status"], "role": item["role"],
                    "did_lines": did, "result_lines": result,
                    "did": did[0] if did else "", "result": result[0] if result else "",
                    "skills": item.get("skills") or [],
                    "praise": item["praise"], "done_this_year": item["status"] == "done" and end == year})
    out.sort(key=lambda c: (not c["done_this_year"], not c["praise"], not c["result"], c["id"]))
    return out


def _ranked(names: list[str]) -> list[str]:
    """자주 나온 순(같으면 먼저 나온 순) — 대소문자 · 띄어쓰기가 달라도 한 이름."""
    count: dict[str, list[Any]] = {}
    for i, raw in enumerate(names):
        name = " ".join(str(raw or "").split())
        if not name:
            continue
        key = name.lower()
        if key not in count:
            count[key] = [name, 0, i]
        count[key][1] += 1
    return [v[0] for v in sorted(count.values(), key=lambda v: (-v[1], v[2]))]


def suggestions(options: list[dict[str, Any]], experiences: list[dict[str, Any]]) -> dict[str, list[str]]:
    """역량 후보(그 해 경험의 역량 태그) · 보유 기술 후보(과제 담당과 역할 기술 + 경험 도구) — 자주 나온 순."""
    skills = [str(s.get("name") or "") for e in experiences for s in e["skills"] if isinstance(s, dict)]
    tools = [t for c in options for t in c["skills"]] + [t for e in experiences for t in e["tools"]]
    return {"skills": _ranked(skills), "tools": _ranked(tools)}


def _picked_lines(option: dict[str, Any], edited: dict[str, Any] | None) -> dict[str, Any]:
    """카드에 나갈 과제 한 줄 — 다듬은 줄이 있으면 그것, 없으면 원본 앞 두 줄."""
    def pick(key: str, source: list[str]) -> list[str]:
        value = (edited or {}).get(key)
        if isinstance(value, list):
            return [str(v)[:LINE_MAX] for v in value][:LINE_COUNT]
        return source[:LINE_COUNT]
    did, result = pick("did", option["did_lines"]), pick("result", option["result_lines"])
    return {**option, "did_lines_card": did, "result_lines_card": result,
            "edited": bool(edited) and (did != option["did_lines"][:LINE_COUNT] or result != option["result_lines"][:LINE_COUNT])}


def card(conn: sqlite3.Connection, name: str, year: str) -> dict[str, Any]:
    from .person_history import year_review

    _check_year(year)
    review = year_review(conn, name, year)
    experiences = _year_experiences(name, year)
    options = candidates(conn, name, year, experiences)
    stored = _stored(name, year)
    chosen = stored["projects"] if stored["projects"] is not None else [c["id"] for c in options[:PICK_DEFAULT]]
    picked = [_picked_lines(c, stored["lines"].get(pid)) for pid in chosen for c in options if c["id"] == pid][:PICK_MAX]
    offer = suggestions(options, experiences)
    skills = stored["skills"] if stored["skills"] is not None else offer["skills"][:CHIP_MAX]
    tools = stored["tools"] if stored["tools"] is not None else offer["tools"][:CHIP_MAX]
    roster = {p["name"]: p for p in settings_service.people()}
    missing = []
    if not stored["message"]:
        missing.append("감사 편지")
    if not picked:
        missing.append("넣을 과제")
    elif not any(c["result_lines_card"] for c in picked):
        missing.append("과제 결과")
    return {
        "name": name, "year": year, "leader": bool(roster.get(name, {}).get("leader")),
        "numbers": {"projects": review["projects"], "done": review["done"], "milestones": review["milestones"],
                    "activities": review["activities"], "hours": review["hours"], "reports": review["reports"]},
        "new_skills": review["new_skills"],
        "skill_options": offer["skills"], "tool_options": offer["tools"],
        "skills": skills[:CHIP_MAX], "tools": tools[:CHIP_MAX],
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
    return {"year": year, "people": people, "pick_max": PICK_MAX, "message_max": MESSAGE_MAX,
            "line_count": LINE_COUNT, "line_max": LINE_MAX, "chip_max": CHIP_MAX}


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
    options = {c["id"]: c for c in candidates(conn, name, year)}
    projects = [str(p) for p in (data.get("projects") or []) if str(p) in options]
    projects = list(dict.fromkeys(projects))[:PICK_MAX]
    # 다듬은 줄 — 고른 과제만, 원본 앞 두 줄과 같으면 남기지 않는다(원본이 바뀌면 따라가게)
    lines: dict[str, dict[str, list[str]]] = {}
    raw_lines = data.get("lines") if isinstance(data.get("lines"), dict) else {}
    for pid in projects:
        edited = raw_lines.get(pid) if isinstance(raw_lines.get(pid), dict) else {}
        keep: dict[str, list[str]] = {}
        for key, source in (("did", options[pid]["did_lines"]), ("result", options[pid]["result_lines"])):
            value = edited.get(key)
            if not isinstance(value, list):
                continue
            clean_lines = [" ".join(str(v).split()) for v in value][:LINE_COUNT]
            if any(len(v) > LINE_MAX for v in clean_lines):
                raise YearCardError(f"수행 · 결과 한 줄은 {LINE_MAX}자까지입니다 — 엽서 한 줄에 들어가게.")
            clean_lines = [v for v in clean_lines if v]
            if clean_lines != source[:LINE_COUNT]:
                keep[key] = clean_lines
        if keep:
            lines[pid] = keep

    def chips(key: str) -> list[str] | None:
        value = data.get(key)
        if not isinstance(value, list):
            return None
        return list(dict.fromkeys(" ".join(str(v).split())[:40] for v in value if str(v).strip()))[:CHIP_MAX]

    path = card_path(name, year)
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {"person": name, "year": year, "headline": headline, "projects": projects,
            "updated_at": clock.now().replace(microsecond=0).isoformat(), "updated_by": by}
    if lines:
        meta["lines"] = lines
    for key in ("skills", "tools"):
        value = chips(key)
        if value is not None:
            meta[key] = value
    md.save(path, md.MarkdownDoc(meta, message + "\n" if message else ""))
    return card(conn, name, year)
