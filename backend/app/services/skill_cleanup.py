"""역량 태그 정리함 (TODO 262 · 261 — docs/팀원이력정리/역량태그입력.md).

사전에 없는 태그를 **팀 전체에서 모아** 한 번에 정리한다 — 경험 하나씩 [기존 역량으로 ▾] 를 고르는 일은 크다(사용자 2026-11-10).
태그마다 네 가지 중 하나: **동의어로**(사전의 대표 역량에 다른 이름으로 더하고 태그를 바꿈) · **새 역량으로**(사전에 더함) ·
**도구로**(역량 태그에서 빼고 도구 칸으로) · **빼기**(태그를 지움 — 넓은 말).

**AI 로 맞추기** — 사전과 정리할 태그로 프롬프트를 만들고(먼저 보이고 복사 — 71), 돌아온 `태그 | 맞출 곳` 줄을 읽어
**제안으로만** 채운다. 적용은 사람이 [적용]으로(정할 것 — AI 의 답을 그대로 사전에 넣지 않는다).
"""
from __future__ import annotations

import re
import sqlite3
from typing import Any

from ..config import get_settings
from ..experience import skills as skill_rules
from . import experiences as exp
from . import settings as settings_service

ACTIONS = ("alias", "new", "tool", "drop")
ACTION_WORDS = {"도구": "tool", "버림": "drop", "빼기": "drop", "넓음": "drop"}
_NEW = re.compile(r"^새\s*역량\s*(?:[(（:：]\s*(?P<axis>[^)）]+?)\s*[)）]?)?$")


def _all_paths() -> list:
    return sorted(get_settings().people_dir.glob("*/experiences/E-*.md"))


def unknown_tags(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """사전에 없는 태그 — 팀 전체, 쓰는 경험이 많은 것부터. 비슷한 대표 역량 제안 · 팀의 기술 · 도구에 있나."""
    dictionary = settings_service.skill_dictionary()
    known = {(d["axis"], d["name"]) for d in dictionary}
    tools = exp.team_tools()
    found: dict[tuple[str, str], dict[str, Any]] = {}
    for path in _all_paths():
        try:
            item = exp.read_file(path)
        except Exception:
            continue
        for skill in item["skills"] if isinstance(item["skills"], list) else []:
            if not isinstance(skill, dict) or not skill.get("name"):
                continue
            mark = (skill.get("axis") or "기술", skill["name"])
            if mark in known:
                continue
            row = found.setdefault(mark, {"axis": mark[0], "name": mark[1], "experiences": [], "people": []})
            row["experiences"].append(item["id"])
            if item["person"] not in row["people"]:
                row["people"].append(item["person"])
    out = []
    for row in found.values():
        out.append({**row, "count": len(row["experiences"]), "suggest": skill_rules.similar(row["name"], dictionary),
                    "tool_like": skill_rules.key(row["name"]) in tools})
    out.sort(key=lambda row: (-row["count"], row["axis"], row["name"]))
    return out


def apply(conn: sqlite3.Connection, actions: list[dict[str, Any]]) -> dict[str, Any]:
    """정리 — 사전을 한 번 고치고, 모든 경험의 태그를 한 번에 바꾼다. 모두 먼저 검사한다(하나라도 틀리면 아무것도 안 바꿈)."""
    dictionary = [dict(d, aliases=list(d.get("aliases") or [])) for d in settings_service.skill_dictionary()]
    by_name = {(d["axis"], d["name"]): d for d in dictionary}
    plan: dict[tuple[str, str], tuple[str, tuple[str, str] | None]] = {}
    for raw in actions:
        mark = (str(raw.get("axis") or ""), " ".join(str(raw.get("name") or "").split()))
        action = str(raw.get("action") or "")
        if not mark[1] or action not in ACTIONS:
            raise exp.ExperienceError(f"정리 방법을 알 수 없습니다: {mark[1] or '(빈칸)'} — {action or '(빈칸)'}")
        target = None
        if action == "alias":
            target = (str(raw.get("target_axis") or ""), str(raw.get("target_name") or ""))
            if target not in by_name:
                raise exp.ExperienceError(f"사전에 없는 역량으로는 맞추지 않습니다: {target[1] or '(빈칸)'}")
        if action == "new":
            axis = str(raw.get("target_axis") or mark[0])
            if axis not in skill_rules.AXES:
                raise exp.ExperienceError(f"역량 축은 {' · '.join(skill_rules.AXES)} 중 하나입니다: {axis}")
            target = (axis, mark[1])
        plan[mark] = (action, target)
    # 사전 고치기
    taken = skill_rules.index(dictionary)
    for (axis, name), (action, target) in plan.items():
        if action == "alias" and skill_rules.key(name) not in taken:
            by_name[target]["aliases"].append(name)
            taken[skill_rules.key(name)] = target
        elif action == "new" and target not in by_name and skill_rules.key(name) not in taken:
            entry = {"axis": target[0], "name": name, "aliases": []}
            dictionary.append(entry)
            by_name[target] = entry
            taken[skill_rules.key(name)] = target
    settings_service.save({"skill_dictionary": skill_rules.validate(dictionary)})
    # 경험 고치기
    changed = []
    for path in _all_paths():
        stored = exp.read_file(path)
        skills, tools = [], list(stored["tools"])
        touched = False
        for skill in stored["skills"]:
            mark = (skill.get("axis"), skill.get("name"))
            if mark not in plan:
                skills.append(skill)
                continue
            touched = True
            action, target = plan[mark]
            if action in ("alias", "new"):
                skills.append({"axis": target[0], "name": target[1]})
            elif action == "tool" and skill["name"] not in tools:
                tools.append(skill["name"])
        if not touched:
            continue
        fields = exp.clean({**stored, "skills": skills, "tools": tools}, stored, opened=(stored["status"],))
        exp._write(path, stored["id"], fields,
                   {"created_at": stored["created_at"], "updated_at": exp.now_iso(), "created_by": stored["created_by"]})
        changed.append(stored["id"])
    exp.reindex(conn)
    conn.commit()
    return {"changed": changed, "dictionary": len(dictionary)}


# ── AI 로 맞추기 — 프롬프트 · 답 읽기 ─────────────────────────────────────────

PROMPT_HEAD = """[역할]
당신은 제조 · 데이터 분석 조직의 역량 체계를 정리하는 담당자입니다.
아래 [정리할 태그]는 팀원 경험에 붙은 역량 태그 중 [역량 사전]에 없는 것입니다. 태그마다 어디로 맞출지 정해 주세요.

[규칙]
1. 같은 뜻의 역량이 사전에 있으면 그 **대표 이름**을 그대로 씁니다(사전의 글자 그대로).
2. 프로그래밍 언어 · 소프트웨어 · 장비 이름이면 "도구" 라고 씁니다.
3. "개발 · 구축 · 분석" 처럼 너무 넓어서 무엇을 잘했는지 드러나지 않으면 "버림" 이라고 씁니다.
4. 사전에 없지만 팀에 꼭 필요한 역량이면 "새 역량(축)" 이라고 씁니다. 축은 기술 · 업무 · 리더십 · 문제해결 중 하나.
5. 확실하지 않으면 줄 끝에 " ?" 를 붙입니다.

[출력 형식] — 아래 모양의 줄만, 태그마다 한 줄. 설명을 쓰지 않습니다.
- 태그 | 대표 이름
- 태그 | 도구
- 태그 | 버림
- 태그 | 새 역량(업무)
"""


def tag_prompt(conn: sqlite3.Connection) -> dict[str, Any]:
    dictionary = settings_service.skill_dictionary()
    tags = unknown_tags(conn)
    lines = [PROMPT_HEAD, "[역량 사전] (축: 대표 이름 (다른 이름))"]
    for axis in skill_rules.AXES:
        entries = [d for d in dictionary if d["axis"] == axis]
        if entries:
            lines.append(f"- {axis}: " + ", ".join(f"{d['name']}" + (f" ({' · '.join(d['aliases'])})" if d["aliases"] else "") for d in entries))
    lines += ["", "[정리할 태그] (축 — 태그 · 쓰는 경험 수)"]
    lines += [f"- {t['axis']} — {t['name']} · {t['count']}" for t in tags] or ["(없음)"]
    text = "\n".join(lines).rstrip() + "\n"
    return {"text": text if tags else "", "chars": len(text) if tags else 0, "tags": len(tags)}


def read_answer(conn: sqlite3.Connection, text: str) -> list[dict[str, Any]]:
    """AI 의 답 → 제안(적용하지 않는다). 정리할 태그에 없는 줄 · 사전에 없는 대표 이름은 `problem` 으로 알린다."""
    dictionary = settings_service.skill_dictionary()
    table = skill_rules.index(dictionary)
    tags = {skill_rules.key(t["name"]): t for t in unknown_tags(conn)}
    out = []
    for line in (text or "").splitlines():
        line = re.sub(r"^\s*[-•·*]\s*", "", line).strip().strip("`")
        if "|" not in line:
            continue
        left, right = (part.strip() for part in line.split("|", 1))
        unsure = right.endswith("?")
        right = right.rstrip("? ").strip()
        tag = tags.get(skill_rules.key(left))
        if not tag:
            continue
        row: dict[str, Any] = {"axis": tag["axis"], "name": tag["name"], "unsure": unsure, "raw": right, "problem": ""}
        new = _NEW.match(right)
        if right in ACTION_WORDS:
            row["action"] = ACTION_WORDS[right]
        elif new:
            axis = (new.group("axis") or tag["axis"]).strip()
            row.update(action="new", target_axis=axis if axis in skill_rules.AXES else tag["axis"])
        elif skill_rules.key(right) in table:
            axis, name = table[skill_rules.key(right)]
            row.update(action="alias", target_axis=axis, target_name=name)
        else:
            row.update(action="", problem=f"사전에 없는 이름입니다: {right}")
        out.append(row)
    return out


def add_suggested() -> dict[str, Any]:
    """[추천 동의어 더하기](261 ③)."""
    dictionary, added = skill_rules.add_suggested(settings_service.skill_dictionary())
    if added:
        settings_service.save({"skill_dictionary": dictionary})
    return {"added": added}
