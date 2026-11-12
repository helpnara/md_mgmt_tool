"""팀 역량 · 기술 스택 (TODO 284) — 팀원 이력(경험 · 과제 담당과 역할)을 팀 한 장으로.

사용자(2026-11-12): *"우리 팀의 역량과 기술 스택에 대해서 잘 정리해서 도식화를 하고 싶은데"* → 1단계(권하는 대로):
* 세는 경험 — **구조화 · 확정**(초안은 뺌). 기간 — 기본 **최근 3년**(올해 · 전체로 바꿈). 기간이 없는 경험은 어느 기간에도 센다(팀이 가진 것).
* 칸 값 — **경험 수**(수준 · Lv 은 넣지 않는다 — 평가와 닿음). 보유 기술은 경험의 보유 기술 + 과제 담당과 역할의 기술.
* 사람 — 명부의 지금 사람(자리 이름 TBD 등 뺌, 떠난 사람은 `left=1` 일 때만). 팀장 · 관리자만(`share.BLOCKED_PREFIXES`).
그림: ① 역량 지도(역량 × 사람) ② 기술 스택(층마다 보유 기술) ④ 한 사람에게만 있는 것 + 완성도 띠.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from .. import clock
from .. import schemas as rules
from ..experience import skills as skill_rules
from ..experience import tools as tool_rules
from . import settings as settings_service

COUNTED = ("구조화", "확정")
PERIODS = ("3y", "year", "all")
USES_MAX = 40


def _span(start: str, end: str, this_year: str) -> tuple[str, str]:
    """경험 · 담당 기간 → (첫 해, 끝 해). 비면 ("", "")."""
    first, last = (start or "")[:4], (end or "")[:4]
    if first and not last:
        last = this_year
    if last and not first:
        first = last
    return first, last


def _in_period(span: tuple[str, str], period: str, this_year: str) -> bool:
    first, last = span
    if period == "all" or not first:
        return True
    low = this_year if period == "year" else str(int(this_year) - 2)
    return last >= low and first <= this_year


def team_people(include_left: bool) -> list[dict[str, Any]]:
    from .yearcards import is_placeholder

    out = []
    for person in settings_service.people():
        if is_placeholder(person["name"]):
            continue
        left = bool(person.get("left_on"))
        if left and not include_left:
            continue
        out.append({"name": person["name"], "left": left, "leader": bool(person.get("leader"))})
    return out


def overview(conn: sqlite3.Connection, period: str = "3y", include_left: bool = False) -> dict[str, Any]:
    from . import experiences as exp

    if period not in PERIODS:
        raise ValueError("기간은 3y · year · all 중 하나입니다.")
    this_year = str(clock.today().year)
    people = team_people(include_left)
    names = [p["name"] for p in people]
    skill_dict = settings_service.skill_dictionary()
    tool_dict = settings_service.tool_dictionary()
    tool_table = tool_rules.index(tool_dict)
    layer_of = {item["name"]: item.get("layer") or "" for item in tool_dict}
    known_skills = {(item["axis"], item["name"]) for item in skill_dict}

    completeness = {n: {"name": n, "초안": 0, "구조화": 0, "확정": 0, "unknown_tags": 0, "empty_tools": 0} for n in names}
    # 역량: (축, 이름) → 사람 → {count, last}
    skill_cells: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    # 보유 기술: 이름 → {people: {사람: n}, projects: set, experiences: n, uses: []}
    tools: dict[str, dict[str, Any]] = {}

    def add_tool(raw: str, person: str, source: dict[str, str]) -> None:
        name = tool_table.get(skill_rules.key(raw), " ".join(str(raw).split()))
        if not name:
            return
        row = tools.setdefault(name, {"people": {}, "projects": set(), "experiences": 0, "uses": [], "known": name in layer_of})
        row["people"][person] = row["people"].get(person, 0) + 1
        if source["kind"] == "project":
            row["projects"].add(source["id"])
        else:
            row["experiences"] += 1
        if len(row["uses"]) < USES_MAX:
            row["uses"].append({"person": person, **source})

    for name in names:
        folder = exp.person_dir(name)
        for path in sorted(folder.glob("*.md")) if folder.is_dir() else []:
            try:
                item = exp.read_file(path)
            except Exception:  # noqa: BLE001 — 깨진 파일 하나로 그림이 안 열리면 안 된다
                continue
            status = item["status"] if item["status"] in completeness[name] else "초안"
            completeness[name][status] += 1
            if status not in COUNTED:
                continue
            span = _span(item["start"], item["end"], this_year)
            if not _in_period(span, period, this_year):
                continue
            year = min(span[1], this_year) if span[1] else ""
            raw_skills = [s for s in item["skills"] if isinstance(s, dict)]
            for skill in skill_rules.match(raw_skills, skill_dict):
                cell = skill_cells.setdefault((skill["axis"], skill["name"]), {}).setdefault(name, {"count": 0, "last": ""})
                cell["count"] += 1
                if year > cell["last"]:
                    cell["last"] = year
                if (skill["axis"], skill["name"]) not in known_skills:
                    completeness[name]["unknown_tags"] += 1
            for raw in item["tools"]:
                add_tool(raw, name, {"kind": "experience", "id": item["id"], "title": item["title"]})

    placeholders = ",".join("?" * len(names)) or "''"
    for row in conn.execute(
            "SELECT c.name, c.skills, c.from_date, c.to_date, c.current, p.id, p.title, p.start_date, p.due_date, p.completed_at"
            f" FROM project_contribution c JOIN project p ON p.id = c.project_id WHERE c.name IN ({placeholders})", names):
        end = row["to_date"] or ("" if row["current"] else (row["completed_at"] or row["due_date"] or ""))
        span = _span(row["from_date"] or row["start_date"] or "", end, this_year)
        if not _in_period(span, period, this_year):
            continue
        listed = rules.split_list(row["skills"])
        if not listed:
            completeness[row["name"]]["empty_tools"] += 1
        for raw in tool_rules.normalize(listed, tool_dict):
            add_tool(raw, row["name"], {"kind": "project", "id": row["id"], "title": row["title"]})

    # ① 역량 지도 — 사전 순(축 · 항목), 사전에 없는 것은 축 끝에
    order = {(item["axis"], item["name"]): i for i, item in enumerate(skill_dict)}
    skill_rows = []
    for axis in skill_rules.AXES:
        keys = [k for k in order if k[0] == axis] + sorted(k for k in skill_cells if k[0] == axis and k not in order)
        for k in keys:
            cells = skill_cells.get(k, {})
            skill_rows.append({"axis": axis, "name": k[1], "known": k in order, "cells": cells,
                               "holders": len(cells), "experiences": sum(c["count"] for c in cells.values())})

    # ② 기술 스택 — 층마다(사전의 층 순서, 층 없음 · 사전에 없음은 끝)
    layers = list(dict.fromkeys([*tool_rules.DEFAULT_LAYERS, *(layer_of[n] for n in layer_of if layer_of[n])]))
    stack = []
    for layer in [*layers, ""]:
        items = []
        for name, row in tools.items():
            if (layer_of.get(name, "") if row["known"] else "") != layer:
                continue
            items.append({"name": name, "known": row["known"], "people": sorted(row["people"], key=names.index),
                          "person_count": len(row["people"]), "project_count": len(row["projects"]),
                          "experience_count": row["experiences"], "uses": row["uses"]})
        if items:
            items.sort(key=lambda t: (-t["person_count"], -(t["project_count"] + t["experience_count"]), t["name"].lower()))
            stack.append({"layer": layer or "층 없음 · 사전에 없음", "unlayered": not layer, "tools": items})

    # ④ 한 사람에게만
    only_one = [{"kind": "역량", "group": r["axis"], "name": r["name"], "person": next(iter(r["cells"]))}
                for r in skill_rows if r["holders"] == 1]
    only_one += [{"kind": "보유 기술", "group": layer["layer"], "name": t["name"], "person": t["people"][0]}
                 for layer in stack for t in layer["tools"] if t["person_count"] == 1]

    no_layer = sorted(n for n, row in tools.items() if row["known"] and not layer_of.get(n))
    return {
        "period": period, "year": this_year, "include_left": include_left, "people": people,
        "completeness": {
            "people": [completeness[n] for n in names],
            "unknown_tags": sum(c["unknown_tags"] for c in completeness.values()),
            "unlisted_tools": sorted(n for n, row in tools.items() if not row["known"]),
            "no_layer_tools": no_layer,
            "empty_tool_projects": sum(c["empty_tools"] for c in completeness.values()),
        },
        "skills": skill_rows, "stack": stack, "only_one": only_one,
    }
