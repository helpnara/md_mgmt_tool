"""팀 역량 · 기술 스택 (TODO 284) — 팀원 이력(경험 · 과제 담당과 역할)을 팀 한 장으로.

사용자(2026-11-12): *"우리 팀의 역량과 기술 스택에 대해서 잘 정리해서 도식화를 하고 싶은데"* → 1단계(권하는 대로):
* 세는 경험 — **구조화 · 확정**(초안은 뺌). 기간 — 기본 **최근 3년**(올해 · 전체로 바꿈). 기간이 없는 경험은 어느 기간에도 센다(팀이 가진 것).
* 칸 값 — **경험 수**(수준 · Lv 은 넣지 않는다 — 평가와 닿음). 보유 기술은 경험의 보유 기술 + 과제 담당과 역할의 기술.
* 사람 — 명부의 지금 사람(자리 이름 TBD 등 뺌, 떠난 사람은 `left=1` 일 때만). 팀장 · 관리자만(`share.BLOCKED_PREFIXES`).
그림: ① 역량 지도(역량 × 사람) ② 기술 스택(층마다 보유 기술) ④ 한 사람에게만 있는 것 + 완성도 띠.

2단계(2026-11-13 — *"284 2단계 착수하자. 팀원에 대해서 올해 수행한 내용을 대부분은 입력 했어."*):
③ 축별 팀 모양(경험 수 · 가진 역량 가짓수 / 사전 · 사람 수) ⑤ 해마다 새로 생긴 역량 · 보유 기술(팀에 처음 나온 해 — 기간과 상관없이 전체로)
⑥ 과제 분류 × 역량(과제에 이은 경험 — 분류 넷 각각) · 역량 지도의 **중분류** 묶음 · **목표 역량**(팀이 갖출 것 — 사람 수 목표 vs 지금).
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
CLASS_KEYS = ("nature", "category", "delivery", "cost_kind")
TARGET_KINDS = ("역량", "보유 기술")
TARGETS_MAX = 100
NEW_YEARS = 5
TREND_YEARS = 5            # 290 — 축마다 다섯 해 추이
CHANGE_LIST_MAX = 12       # 변동 네 칸마다 보이는 수
INSIGHTS_MAX = 5


def _years(span: tuple[str, str], low: str, this_year: str) -> list[str]:
    """경험 · 담당이 걸친 해(low ~ 올해 안에서). 기간이 없으면 [] — 해마다 셈에서는 뺀다."""
    first, last = span
    if not first:
        return []
    start, end = max(int(first), int(low)), min(int(last or this_year), int(this_year))
    return [str(y) for y in range(start, end + 1)]


def validate_targets(value: Any) -> list[dict[str, Any]]:
    """설정 `team_skill_targets` — [{kind, name, want}]. 같은 것 두 번 없음, 사람 수 1 ~ 99."""
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError("목표 역량은 목록이어야 합니다.")
    if len(value) > TARGETS_MAX:
        raise ValueError(f"목표는 {TARGETS_MAX}개까지입니다.")
    out, seen = [], set()
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError("목표 항목의 모양이 다릅니다.")
        kind = str(raw.get("kind") or "").strip()
        name = " ".join(str(raw.get("name") or "").split())
        if kind not in TARGET_KINDS:
            raise ValueError(f"목표 구분은 {' · '.join(TARGET_KINDS)} 중 하나입니다.")
        if not name or len(name) > 60:
            raise ValueError(f"목표 이름은 1 ~ 60자입니다: {name[:20] or '(빈칸)'}")
        try:
            want = int(raw["want"]) if raw.get("want") not in (None, "") else 1
        except (TypeError, ValueError):
            raise ValueError(f"목표 사람 수는 숫자입니다: {name}") from None
        if not 1 <= want <= 99:
            raise ValueError(f"목표 사람 수는 1 ~ 99명입니다: {name}")
        k = (kind, skill_rules.key(name))
        if k in seen:
            raise ValueError(f"같은 목표가 두 번 있습니다: {name}")
        seen.add(k)
        out.append({"kind": kind, "name": name, "want": want})
    return out
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

    # ⑤ 팀에 처음 나온 해 — 기간과 상관없이(세는 경험 · 담당 전체)
    first_seen: dict[tuple[str, str], dict[str, Any]] = {}

    # 291 — 사람마다 처음 쓴 해(성장 — 본인 지난해와만)
    person_first: dict[tuple[str, str, str], str] = {}

    def seen(kind: str, label: str, year: str, person: str) -> None:
        if not year:
            return
        pk = (person, kind, label)
        if pk not in person_first or year < person_first[pk]:
            person_first[pk] = year
        row = first_seen.get((kind, label))
        if row is None or year < row["year"]:
            first_seen[(kind, label)] = {"kind": kind, "name": label, "year": year, "people": [person]}
        elif year == row["year"] and person not in row["people"]:
            row["people"].append(person)

    # ⑥ 과제 분류 × 역량 — 과제에 이은 경험(기간 안)
    project_class = {row["id"]: {k: row[k] or "" for k in CLASS_KEYS}
                     for row in conn.execute(f"SELECT id, {', '.join(CLASS_KEYS)} FROM project")}
    by_class: dict[str, dict[tuple[str, str], dict[str, int]]] = {k: {} for k in CLASS_KEYS}

    # 290 — 해마다 셈(기간 선택과 상관없이): 역량 (축, 이름) → 해 → 경험 수, 보유 기술 이름 → 해 → 사람
    trend_low = str(int(this_year) - TREND_YEARS + 1)
    skill_years: dict[tuple[str, str], dict[str, int]] = {}
    tool_years: dict[str, dict[str, set[str]]] = {}

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
            raw_skills = [s for s in item["skills"] if isinstance(s, dict)]
            matched = skill_rules.match(raw_skills, skill_dict)
            for skill in matched:
                seen("역량", skill["name"], span[0], name)
            for raw in item["tools"]:
                seen("보유 기술", tool_table.get(skill_rules.key(raw), " ".join(str(raw).split())), span[0], name)
            for y in _years(span, trend_low, this_year):
                for skill in matched:
                    row_ = skill_years.setdefault((skill["axis"], skill["name"]), {})
                    row_[y] = row_.get(y, 0) + 1
                for raw in item["tools"]:
                    label = tool_table.get(skill_rules.key(raw), " ".join(str(raw).split()))
                    tool_years.setdefault(label, {}).setdefault(y, set()).add(name)
            if not _in_period(span, period, this_year):
                continue
            year = min(span[1], this_year) if span[1] else ""
            classes = project_class.get(item["project"] or "", {})
            for k in CLASS_KEYS:
                value = classes.get(k) or ""
                if not value:
                    continue
                for skill in matched:
                    cell = by_class[k].setdefault((skill["axis"], skill["name"]), {})
                    cell[value] = cell.get(value, 0) + 1
            for skill in matched:
                cell = skill_cells.setdefault((skill["axis"], skill["name"]), {}).setdefault(
                    name, {"count": 0, "last": "", "confirmed": 0, "quant": 0})
                cell["count"] += 1
                # 292 F — 근거의 단단함: 팀장 확정 · 확정에 정량 결과까지
                if status == "확정":
                    cell["confirmed"] += 1
                    if any(str(q.get("value") or "").strip() for q in item["quants"] if isinstance(q, dict)):
                        cell["quant"] += 1
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
        listed = rules.split_list(row["skills"])
        for raw in tool_rules.normalize(listed, tool_dict):
            seen("보유 기술", raw, span[0], row["name"])
            for y in _years(span, trend_low, this_year):
                tool_years.setdefault(raw, {}).setdefault(y, set()).add(row["name"])
        if not _in_period(span, period, this_year):
            continue
        if not listed:
            completeness[row["name"]]["empty_tools"] += 1
        for raw in tool_rules.normalize(listed, tool_dict):
            add_tool(raw, row["name"], {"kind": "project", "id": row["id"], "title": row["title"]})

    # ① 역량 지도 — 사전 순(축 · 항목), 사전에 없는 것은 축 끝에
    order = {(item["axis"], item["name"]): i for i, item in enumerate(skill_dict)}
    group_of = {(item["axis"], item["name"]): item.get("group") or "" for item in skill_dict}
    skill_rows = []
    for axis in skill_rules.AXES:
        keys = [k for k in order if k[0] == axis] + sorted(k for k in skill_cells if k[0] == axis and k not in order)
        for k in keys:
            cells = skill_cells.get(k, {})
            confirmed = sum(c.get("confirmed", 0) for c in cells.values())
            quant = sum(c.get("quant", 0) for c in cells.values())
            skill_rows.append({"axis": axis, "name": k[1], "known": k in order, "group": group_of.get(k, ""), "cells": cells,
                               "holders": len(cells), "experiences": sum(c["count"] for c in cells.values()),
                               # 3 = 확정 + 정량 결과, 2 = 확정, 1 = 구조화만 (수준이 아니라 근거의 단단함)
                               "evidence": {"confirmed": confirmed, "quant": quant, "level": 3 if quant else 2 if confirmed else 1 if cells else 0}})

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

    # ③ 축별 팀 모양
    shape = []
    for axis in skill_rules.AXES:
        rows_ = [r for r in skill_rows if r["axis"] == axis]
        holders = {p for r in rows_ for p in r["cells"]}
        shape.append({"axis": axis, "experiences": sum(r["experiences"] for r in rows_), "held": sum(1 for r in rows_ if r["holders"]),
                      "total": sum(1 for r in rows_ if r["known"]), "people": len(holders)})

    # ⑤ 해마다 새로 생긴 것 — 올해부터 NEW_YEARS 해
    years = [str(int(this_year) - i) for i in range(NEW_YEARS)]
    new_by_year = [{"year": y, "items": sorted((v for v in first_seen.values() if v["year"] == y), key=lambda v: (v["kind"], v["name"]))}
                   for y in years]
    earlier = sum(1 for v in first_seen.values() if v["year"] < years[-1])

    # ⑥ 과제 분류 × 역량
    classes_out = {}
    for k in CLASS_KEYS:
        values = sorted({v for cell in by_class[k].values() for v in cell})
        rows_ = [{"axis": a, "name": n, "cells": cell, "total": sum(cell.values())} for (a, n), cell in by_class[k].items()]
        rows_.sort(key=lambda r: (-r["total"], r["name"]))
        classes_out[k] = {"values": values, "rows": rows_}

    # 목표 — 사람 수 목표 vs 지금 가진 사람
    have_skill = {skill_rules.key(r["name"]): r["holders"] for r in skill_rows}
    have_tool = {skill_rules.key(t["name"]): t["person_count"] for layer in stack for t in layer["tools"]}
    targets = []
    skill_index = skill_rules.index(skill_dict)
    for t in settings_service.load().get("team_skill_targets") or []:
        raw = str(t.get("name") or "")
        if t.get("kind") == "역량":      # 동의어로 적어도 사전 이름으로 맞춰 센다(파이썬 = Python)
            label = skill_index.get(skill_rules.key(raw), ("", raw))[1]
            have = have_skill.get(skill_rules.key(label), 0)
        else:
            label = tool_table.get(skill_rules.key(raw), raw)
            have = have_tool.get(skill_rules.key(label), 0)
        targets.append({**t, "matched": label, "have": have, "gap": max(0, int(t.get("want") or 1) - have)})
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
        "shape": shape, "new_by_year": new_by_year, "new_earlier": earlier, "by_class": classes_out, "targets": targets,
        **(found := _change_and_insights(this_year, skill_dict, skill_years, tool_years, first_seen, skill_rows, stack, only_one, targets, completeness)),
        **_questions(this_year, names, skill_dict, skill_rows, stack, only_one, targets, found["change"], person_first),
        "leave": _leave_impact(conn, names, skill_rows, stack),
    }


def _leave_impact(conn: sqlite3.Connection, names: list[str], skill_rows: list, stack: list) -> dict[str, Any]:
    """292 A — 이 사람이 떠나면: 잃는 것(혼자 가진 역량 · 기술)과 이어받을 후보(같은 중분류 · 같은 층을 가진 사람),
    얇아지는 것(가진 사람 둘 → 하나), 지금 맡은 진행 중 과제. 팀장이 득실을 판단하는 자료 — 평가에 쓰지 않는다."""
    held = [r for r in skill_rows if r["holders"]]
    tools = [(layer["layer"], t) for layer in stack for t in layer["tools"]]
    out: dict[str, Any] = {}
    for person in names:
        lost, thin = [], []
        for r in held:
            if person not in r["cells"]:
                continue
            if r["holders"] == 1:
                mates = sorted({p for o in held if o["group"] and o["group"] == r["group"] for p in o["cells"]} - {person},
                               key=lambda p: names.index(p) if p in names else 99)
                lost.append({"kind": "역량", "name": r["name"], "group": r["group"] or r["axis"], "candidates": mates[:3],
                             "experiences": r["cells"][person]["count"]})
            elif r["holders"] == 2:
                thin.append({"kind": "역량", "name": r["name"], "remaining": next(p for p in r["cells"] if p != person)})
        for layer, t in tools:
            if person not in t["people"]:
                continue
            if t["person_count"] == 1:
                mates = sorted({p for lay, o in tools if lay == layer and not o["name"] == t["name"] for p in o["people"]} - {person},
                               key=lambda p: names.index(p) if p in names else 99)
                lost.append({"kind": "보유 기술", "name": t["name"], "group": layer, "candidates": mates[:3],
                             "experiences": t["project_count"] + t["experience_count"]})
            elif t["person_count"] == 2:
                thin.append({"kind": "보유 기술", "name": t["name"], "remaining": next(p for p in t["people"] if p != person)})
        lost.sort(key=lambda x: (-x["experiences"], x["name"]))
        projects = [{"id": row["id"], "title": row["title"]} for row in conn.execute(
            "SELECT p.id, p.title FROM project_contribution c JOIN project p ON p.id = c.project_id"
            " WHERE c.name = ? AND c.current = 1 AND p.status NOT IN ('done', 'dropped') ORDER BY p.id", (person,))]
        out[person] = {"lost": lost, "thin": thin, "projects": projects}
    return out


def _questions(this_year: str, names: list[str], skill_dict: list[dict[str, Any]], skill_rows: list, stack: list, only_one: list,
               targets: list, change: dict, person_first: dict) -> dict[str, Any]:
    """291 — 팀장의 질문에 답하는 카드: 강점 · 빈 곳 · 위험 · 성장 · 할 일 + 한 줄 결론(규칙, AI 아님)."""
    last_year = str(int(this_year) - 1)
    group_of = {(item["axis"], item["name"]): item.get("group") or "" for item in skill_dict}

    # 강점 — 가진 사람이 많고 경험이 많은 역량 다섯 · 쓴 사람이 많은 보유 기술 셋
    held = [r for r in skill_rows if r["holders"]]
    strengths = {
        "skills": [{"name": r["name"], "axis": r["axis"], "group": r["group"], "holders": r["holders"], "experiences": r["experiences"]}
                   for r in sorted(held, key=lambda r: (-r["holders"], -r["experiences"], r["name"]))[:5]],
        "tools": [{"name": t["name"], "people": t["person_count"], "uses": t["project_count"] + t["experience_count"]}
                  for t in sorted((t for layer in stack for t in layer["tools"]), key=lambda t: (-t["person_count"], -(t["project_count"] + t["experience_count"]), t["name"]))[:3]],
    }

    # 빈 곳 — 중분류마다 경험 수(사전에 있는 묶음), 적은 셋 · 아무도 없는 묶음 · 목표 모자람
    totals: dict[tuple[str, str], dict[str, Any]] = {}
    for item in skill_dict:
        g = item.get("group") or ""
        if not g:
            continue
        row = totals.setdefault((item["axis"], g), {"axis": item["axis"], "group": g, "experiences": 0, "held": 0, "total": 0})
        row["total"] += 1
    for r in held:
        row = totals.get((r["axis"], group_of.get((r["axis"], r["name"]), "")))
        if row:
            row["experiences"] += r["experiences"]
            row["held"] += 1
    groups = list(totals.values())
    weak = {
        "low": sorted((g for g in groups if g["experiences"]), key=lambda g: (g["experiences"], g["group"]))[:3],
        "empty": [g for g in groups if not g["experiences"]],
        "gaps": [t for t in targets if t.get("gap")],
    }

    # 위험 — 사람마다 혼자 가진 것, 많이 쓰는데 한 사람뿐인 보유 기술
    per: dict[str, list[dict[str, str]]] = {}
    for o in only_one:
        per.setdefault(o["person"], []).append({"kind": o["kind"], "name": o["name"]})
    risky_tools = sorted((t for layer in stack for t in layer["tools"] if t["person_count"] == 1),
                         key=lambda t: (-(t["project_count"] + t["experience_count"]), t["name"]))[:3]
    risk = {
        "people": [{"person": p, "count": len(items), "items": items[:6]} for p, items in sorted(per.items(), key=lambda kv: (-len(kv[1]), names.index(kv[0]) if kv[0] in names else 99))],
        "tools": [{"name": t["name"], "person": t["people"][0], "uses": t["project_count"] + t["experience_count"]} for t in risky_tools],
    }

    # 성장 — 사람마다 올해 처음 쓴 역량 · 보유 기술(본인 기준), 지난해 처음 쓴 수와만 견줌. 명부 순
    growth = []
    for name in names:
        this_new = sorted(label for (p, kind, label), y in person_first.items() if p == name and y == this_year and kind == "역량")
        this_tools = sorted(label for (p, kind, label), y in person_first.items() if p == name and y == this_year and kind == "보유 기술")
        last_count = sum(1 for (p, _, _), y in person_first.items() if p == name and y == last_year)
        growth.append({"person": name, "skills": this_new, "tools": this_tools, "count": len(this_new) + len(this_tools), "last": last_count})

    # 할 일 — 규칙 넷, 많아야 다섯
    actions: list[dict[str, str]] = []
    holders_of = {r["name"]: set(r["cells"]) for r in held}
    for o in only_one:
        if o["kind"] != "역량" or len(actions) >= 2:
            continue
        g = next((group_of[k] for k in group_of if k[1] == o["name"]), "")
        mates = sorted({p for r in held if r["group"] == g and g for p in holders_of.get(r["name"], set())} - {o["person"]})
        if mates:
            actions.append({"kind": "짝", "text": f"{o['name']} — {{{o['person']}}} 님만 가졌습니다. 같은 묶음({g}) 경험이 있는 {{{mates[0]}}} 님과 짝 과제 · 공유 세션"})
    for t in weak["gaps"][:2]:
        actions.append({"kind": "교육", "text": f"목표 {t['name']} {t['gap']}명 모자람 — 교육 · 배치"})
    for r in [r for r in change["skills"]["stopped"] if r["last"] >= 2][:1]:
        actions.append({"kind": "유지", "text": f"{r['name']}: 지난해 {r['last']}건 → 올해 0 — 계속 가져갈지 정하기"})
    target_names = {t["name"] for t in targets}
    for g in weak["low"][:1]:
        if g["group"] not in target_names:
            actions.append({"kind": "목표", "text": f"{g['group']}: 경험이 적습니다({g['experiences']}건) — 목표를 둘지 정하기"})

    # 한 줄 결론 — 변화 · 강점 · 위험에서 가장 큰 것 하나씩
    parts = []
    moved = [r for r in change["groups"] if r["group"] != "(중분류 없음)" and r["delta"]]
    if moved:
        up = max(moved, key=lambda r: r["delta"])
        dn = min(moved, key=lambda r: r["delta"])
        if up["delta"] > 0:
            parts.append(f"올해 팀은 {up['group']} 쪽으로 넓어졌고(+{up['delta']})")
        if dn["delta"] < 0:
            parts.append(f"{dn['group']} 쪽은 줄었습니다({dn['last']}→{dn['this']})")
    if strengths["skills"]:
        parts.append(f"가장 두터운 역량은 {strengths['skills'][0]['name']}({strengths['skills'][0]['holders']}명)")
    if risk["people"]:
        top = risk["people"][0]
        parts.append(f"혼자만 가진 것 {len(only_one)}개 중 {top['count']}개가 {{{top['person']}}} 님에게 있습니다")
    headline = " · ".join(parts)
    return {"strengths": strengths, "weak": weak, "risk": risk, "growth": growth, "actions": actions[:5], "headline": headline}


def _change_and_insights(this_year: str, skill_dict: list[dict[str, Any]], skill_years: dict, tool_years: dict, first_seen: dict,
                         skill_rows: list, stack: list, only_one: list, targets: list, completeness: dict) -> dict[str, Any]:
    """290 — 지난해와 비교(변동) · 축마다 다섯 해 추이 · 한눈에 숫자 · 인사이트 문장(규칙으로 만듦)."""
    last_year = str(int(this_year) - 1)
    years = [str(int(this_year) - TREND_YEARS + 1 + i) for i in range(TREND_YEARS)]
    group_of = {(item["axis"], item["name"]): item.get("group") or "" for item in skill_dict}

    # 중분류마다 지난해 → 올해 경험 수(사전 순서, 축마다 중분류 없음은 끝)
    groups: dict[tuple[str, str], dict[str, int]] = {}
    for item in skill_dict:
        groups.setdefault((item["axis"], item.get("group") or ""), {"last": 0, "this": 0})
    for key, by_year in skill_years.items():
        g = groups.setdefault((key[0], group_of.get(key, "")), {"last": 0, "this": 0})
        g["last"] += by_year.get(last_year, 0)
        g["this"] += by_year.get(this_year, 0)
    order = {axis: i for i, axis in enumerate(skill_rules.AXES)}
    group_rows = [{"axis": a, "group": g or "(중분류 없음)", "last": v["last"], "this": v["this"], "delta": v["this"] - v["last"]}
                  for (a, g), v in groups.items() if v["last"] or v["this"] or g]
    group_rows.sort(key=lambda r: (order.get(r["axis"], 9), r["group"] == "(중분류 없음)"))

    axes_trend = [{"axis": axis, "years": [{"year": y, "count": sum(v.get(y, 0) for k, v in skill_years.items() if k[0] == axis)} for y in years]}
                  for axis in skill_rules.AXES]

    def changes(rows: dict[str, tuple[int, int]], kind: str) -> dict[str, list[dict[str, Any]]]:
        new = sorted(v["name"] for v in first_seen.values() if v["kind"] == kind and v["year"] == this_year)
        up = sorted(({"name": n, "last": a, "this": b} for n, (a, b) in rows.items() if a and b > a), key=lambda r: (r["last"] - r["this"], r["name"]))
        down = sorted(({"name": n, "last": a, "this": b} for n, (a, b) in rows.items() if b and a > b), key=lambda r: (r["this"] - r["last"], r["name"]))
        stopped = sorted(({"name": n, "last": a, "this": 0} for n, (a, b) in rows.items() if a and not b), key=lambda r: (-r["last"], r["name"]))
        return {"new": new[:CHANGE_LIST_MAX * 2], "up": up[:CHANGE_LIST_MAX], "down": down[:CHANGE_LIST_MAX], "stopped": stopped[:CHANGE_LIST_MAX],
                "counts": {"new": len(new), "up": len(up), "down": len(down), "stopped": len(stopped)}}

    skill_pairs = {k[1]: (v.get(last_year, 0), v.get(this_year, 0)) for k, v in skill_years.items()}
    tool_pairs = {n: (len(v.get(last_year, set())), len(v.get(this_year, set()))) for n, v in tool_years.items()}
    change = {"this": this_year, "last": last_year, "groups": group_rows, "axes_trend": axes_trend,
              "skills": changes(skill_pairs, "역량"), "tools": changes(tool_pairs, "보유 기술")}

    held = sum(1 for r in skill_rows if r["holders"])
    total = sum(1 for r in skill_rows if r["known"])
    tool_count = sum(len(layer["tools"]) for layer in stack)
    gaps = [t for t in targets if t.get("gap")]
    counted = sum(c["구조화"] + c["확정"] for c in completeness.values())
    kpis = {"skills_held": held, "skills_total": total, "skills_new": change["skills"]["counts"]["new"],
            "tools": tool_count, "tools_new": change["tools"]["counts"]["new"], "only_one": len(only_one),
            "target_gaps": len(gaps), "experiences": counted}

    # 인사이트 — 해당 없는 문장은 빼고 많아야 다섯 줄. target = 화면의 섹션
    insights: list[dict[str, str]] = []
    new_skills = change["skills"]["new"]
    if new_skills:
        top = {}
        for n in new_skills:
            g = next((group_of[k] for k in group_of if k[1] == n), "")
            if g:
                top[g] = top.get(g, 0) + 1
        best = max(top.items(), key=lambda p: p[1]) if top else None
        tail = f", 그중 {best[1]}개가 {best[0]}" if best and best[1] >= 2 else ""
        insights.append({"text": f"올해 새로 생긴 역량 {len(new_skills)}개{tail} — {', '.join(new_skills[:4])}{' …' if len(new_skills) > 4 else ''}",
                         "target": "ts-change"})
    moved = [r for r in group_rows if abs(r["delta"]) >= 2 and r["group"] != "(중분류 없음)"]
    if moved:
        upg = max(moved, key=lambda r: r["delta"])
        dng = min(moved, key=lambda r: r["delta"])
        if upg["delta"] > 0:
            insights.append({"text": f"가장 많이 늘어난 묶음은 {upg['group']} — 지난해 {upg['last']} → 올해 {upg['this']}건", "target": "ts-change"})
        if dng["delta"] < 0:
            insights.append({"text": f"가장 많이 줄어든 묶음은 {dng['group']} — 지난해 {dng['last']} → 올해 {dng['this']}건", "target": "ts-change"})
    stopped = [r for r in change["skills"]["stopped"] if r["last"] >= 2]
    if stopped:
        insights.append({"text": f"지난해엔 있었는데 올해 끊긴 역량 {len(stopped)}개 — {', '.join(r['name'] for r in stopped[:3])}{' …' if len(stopped) > 3 else ''}",
                         "target": "ts-change"})
    if only_one:
        per: dict[str, int] = {}
        for o in only_one:
            per[o["person"]] = per.get(o["person"], 0) + 1
        who_, n = max(per.items(), key=lambda p: p[1])
        if n >= 3:
            insights.append({"text": f"한 사람에게만 있는 역량 · 보유 기술 {len(only_one)}개 중 {n}개가 {{{who_}}} 님에게 몰려 있습니다", "target": "ts-risk",
                             "person": who_})
    if gaps:
        first = gaps[0]
        insights.append({"text": f"목표에 모자란 것 {len(gaps)}개 — {first['name']} {first.get('have', 0)} / {first['want']}명"
                                 + (f" 외 {len(gaps) - 1}개" if len(gaps) > 1 else ""), "target": "ts-risk"})
    return {"change": change, "kpis": kpis, "insights": insights[:INSIGHTS_MAX]}
