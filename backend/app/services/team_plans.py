"""개인 육성 목표 · 승계 · 짝 계획 (TODO 292 C · B).

팀 역량 화면은 "지금" 을 보여 줬지만 "그래서 누구를 · 언제까지 · 어떻게" 를 적고 됐는지 확인할 칸이 없었다.

* **C 개인 육성 목표** — 사람마다 해마다 키울 역량 1 ~ 3개와 경로. `people/<이름>/growth/<해>.md`.
  면담처럼 민감한 자료 — 검색 · AI 요약 · 내보내기 · 연말카드에 넣지 않는다. 팀원은 자기 것을 **보기만**(나의 한 해에도 한 줄).
  그 해 경험(구조화 · 확정)에 그 역량이 생기면 "시작함 · 경험 n건". 팀장이 [이룸] · [미룸] 을 직접 표시할 수도 있다.
* **B 승계 · 짝 계획** — 혼자만 가진 것 · 떠나면 잃는 것을 누가 언제까지 배울지. `team/succession.md` 한 파일.
  계획을 만든 뒤 배울 사람에게 그 역량 · 보유 기술의 경험(구조화 · 확정)이 생기면 **저절로 "됨"**(근거 경험). 팀장 화면만.
* 둘 다 수준(Lv) · 점수는 없다 — 팀장이 득과 실을 판단하는 자료(292 J).
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .. import clock
from ..config import get_settings
from ..experience import skills as skill_rules
from ..experience import tools as tool_rules
from ..vault import markdown as md
from ..vault import paths
from . import settings as settings_service

COUNTED = ("구조화", "확정")
GOALS_MAX = 3
WAYS = ("과제", "교육", "짝", "기타")
MARKS = ("", "이룸", "미룸")
PLAN_WAYS = ("짝 과제", "공유 세션", "교육", "기타")
PLAN_STATES = ("진행", "됨", "그만둠")
PLAN_KINDS = ("역량", "보유 기술")
DEFAULT_MONTHS = 6
PLANS_MAX = 200
TEXT_MAX = 200


class PlanError(ValueError):
    pass


def _text(value: Any, limit: int = TEXT_MAX) -> str:
    return " ".join(str(value or "").split())[:limit]


# ── 경험에서 그 역량 · 보유 기술 찾기 ───────────────────────────────────────────

def skill_hits(name: str, kind: str, label: str) -> list[dict[str, Any]]:
    """그 사람의 세는 경험(구조화 · 확정) 중 그 역량(사전의 같은 말 포함) · 보유 기술이 든 것."""
    from . import experiences as exp

    folder = exp.person_dir(name)
    if not folder.is_dir():
        return []
    skill_dict = settings_service.skill_dictionary()
    tool_table = tool_rules.index(settings_service.tool_dictionary())
    want = skill_rules.key(label)
    if kind == "역량":
        index = skill_rules.index(skill_dict)
        want = skill_rules.key(index.get(want, ("", label))[1])
    else:
        want = skill_rules.key(tool_table.get(want, label))
    out = []
    for path in sorted(folder.glob("*.md")):
        try:
            item = exp.read_file(path)
        except Exception:  # noqa: BLE001
            continue
        if item["status"] not in COUNTED:
            continue
        if kind == "역량":
            names = [s["name"] for s in skill_rules.match([s for s in item["skills"] if isinstance(s, dict)], skill_dict)]
        else:
            names = [tool_table.get(skill_rules.key(raw), raw) for raw in item["tools"]]
        if any(skill_rules.key(n) == want for n in names):
            out.append({"id": item["id"], "title": item["title"], "status": item["status"], "start": item["start"],
                        "end": item["end"], "created_at": item["created_at"]})
    return out


def _in_year(hit: dict[str, Any], year: str) -> bool:
    first = (hit["start"] or hit["end"] or hit["created_at"] or "")[:4]
    last = (hit["end"] or hit["start"] or hit["created_at"] or "")[:4] or first
    if not first:
        return False
    return first <= year <= (last or year) or (not hit["end"] and first <= year)


# ── C 개인 육성 목표 ──────────────────────────────────────────────────────────

def _growth_path(name: str, year: str) -> Path:
    if not re.fullmatch(r"\d{4}", str(year or "")):
        raise PlanError("해는 네 자리 숫자입니다.")
    return paths.safe_join(get_settings().people_dir, paths.slugify(name), "growth", f"{year}.md")


def _clean_goals(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise PlanError("목표는 목록이어야 합니다.")
    goals, seen = [], set()
    for raw in value:
        if not isinstance(raw, dict):
            continue
        skill = _text(raw.get("skill"), 60)
        if not skill:
            continue
        key = skill_rules.key(skill)
        if key in seen:
            raise PlanError(f"같은 역량이 두 번 있습니다: {skill}")
        seen.add(key)
        way = str(raw.get("way") or "").strip()
        mark = str(raw.get("mark") or "").strip()
        goals.append({"skill": skill, "way": way if way in WAYS else "기타", "note": _text(raw.get("note")),
                      "mark": mark if mark in MARKS else ""})
    if len(goals) > GOALS_MAX:
        raise PlanError(f"육성 목표는 {GOALS_MAX}개까지입니다 — 많으면 하나도 못 키웁니다.")
    return goals


def _read_goals(name: str, year: str) -> dict[str, Any]:
    path = _growth_path(name, year)
    if not path.is_file():
        return {"goals": [], "updated_at": "", "by": ""}
    doc = md.load(path)
    meta = doc.meta or {}
    try:
        goals = _clean_goals(meta.get("goals") or [])
    except PlanError:
        goals = []
    return {"goals": goals, "updated_at": str(meta.get("updated_at") or ""), "by": str(meta.get("by") or "")}


def growth(name: str, year: str | None = None) -> dict[str, Any]:
    """그 사람 그 해의 목표 + 저절로 보이는 진행(그 해 경험 · 확정). 지난해 목표도 함께(접어 보임)."""
    year = year or str(clock.today().year)
    stored = _read_goals(name, year)
    goals = []
    for goal in stored["goals"]:
        hits = [h for h in skill_hits(name, "역량", goal["skill"]) if _in_year(h, year)]
        goals.append({**goal, "experiences": len(hits), "confirmed": sum(1 for h in hits if h["status"] == "확정"),
                      "started": bool(hits), "evidence": hits[:5]})
    last = str(int(year) - 1)
    prev = _read_goals(name, last)["goals"]
    return {"person": name, "year": year, "goals": goals, "updated_at": stored["updated_at"], "by": stored["by"],
            "started": sum(1 for g in goals if g["started"] or g["mark"] == "이룸"),
            "last_year": {"year": last, "goals": prev}, "max": GOALS_MAX, "ways": list(WAYS)}


def save_growth(name: str, year: str, goals: Any, by: str = "") -> dict[str, Any]:
    name = _text(name, 60)
    if not name:
        raise PlanError("사람을 고르세요.")
    clean = _clean_goals(goals)
    path = _growth_path(name, year)
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {"person": name, "year": year, "goals": clean, "updated_at": clock.now().isoformat(timespec="seconds"), "by": by}
    body = f"# {name} — {year} 육성 목표\n\n" + "\n".join(
        f"- {g['skill']} — {g['way']}{(' · ' + g['note']) if g['note'] else ''}{(' (' + g['mark'] + ')') if g['mark'] else ''}" for g in clean) + "\n"
    md.save(path, md.MarkdownDoc(meta, body))
    return growth(name, year)


def growth_counts(names: list[str], year: str | None = None) -> dict[str, dict[str, int]]:
    """사람별 표의 "목표" 칸 — {이름: {goals, started}}. 경험을 읽으므로 목표가 있는 사람만 센다."""
    year = year or str(clock.today().year)
    out = {}
    for name in names:
        try:
            stored = _read_goals(name, year)["goals"]
        except (PlanError, ValueError):
            continue
        if not stored:
            out[name] = {"goals": 0, "started": 0}
            continue
        started = sum(1 for g in stored if g["mark"] == "이룸" or any(_in_year(h, year) for h in skill_hits(name, "역량", g["skill"])))
        out[name] = {"goals": len(stored), "started": started}
    return out


# ── B 승계 · 짝 계획 ──────────────────────────────────────────────────────────

def _plans_path() -> Path:
    return get_settings().vault_dir / "team" / "succession.md"


def _read_plans() -> list[dict[str, Any]]:
    path = _plans_path()
    if not path.is_file():
        return []
    raw = (md.load(path).meta or {}).get("plans") or []
    return [p for p in raw if isinstance(p, dict) and p.get("id")]


def _write_plans(plans: list[dict[str, Any]]) -> None:
    path = _plans_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# 승계 · 짝 계획", "", "> 팀장이 팀의 득과 실을 판단하는 자료입니다 — 평가에 쓰지 않습니다.", ""]
    for p in plans:
        lines.append(f"- [{p['state']}] {p['kind']} · {p['name']} — {', '.join(p.get('holders') or []) or '?'} → {p['learner']}"
                     f" · {p['way']} · 기한 {p['due']}{(' · ' + p['note']) if p.get('note') else ''}")
    md.save(path, md.MarkdownDoc({"plans": plans}, "\n".join(lines) + "\n"))


def _next_id(plans: list[dict[str, Any]]) -> str:
    nums = [int(m.group(1)) for p in plans if (m := re.fullmatch(r"S-(\d+)", str(p.get("id"))))]
    return f"S-{(max(nums) + 1) if nums else 1:03d}"


def _check_plan(data: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    out = dict(plan)
    if "kind" in data:
        out["kind"] = data["kind"] if data["kind"] in PLAN_KINDS else "역량"
    for key in ("name", "learner"):
        if key in data:
            out[key] = _text(data[key], 60)
    if "holders" in data:
        out["holders"] = [_text(h, 60) for h in (data["holders"] or []) if _text(h, 60)][:5]
    if "way" in data:
        out["way"] = data["way"] if data["way"] in PLAN_WAYS else "기타"
    if "note" in data:
        out["note"] = _text(data["note"])
    if "due" in data:
        try:
            out["due"] = date.fromisoformat(str(data["due"])[:10]).isoformat()
        except ValueError:
            raise PlanError("기한은 날짜(YYYY-MM-DD)입니다.") from None
    if "state" in data:
        if data["state"] not in PLAN_STATES:
            raise PlanError(f"상태는 {' · '.join(PLAN_STATES)} 중 하나입니다.")
        out["state"] = data["state"]
        if data["state"] == "됨" and not out.get("done_at"):
            out["done_at"] = clock.today().isoformat()
            out["done_by"] = "직접"
        if data["state"] == "진행":
            out.pop("done_at", None), out.pop("done_by", None), out.pop("evidence", None)
    if not out.get("name"):
        raise PlanError("무엇(역량 · 보유 기술)을 배울지 적어 주세요.")
    if not out.get("learner"):
        raise PlanError("배울 사람을 고르세요.")
    if out.get("learner") in (out.get("holders") or []):
        raise PlanError("가진 사람이 배울 사람일 수는 없습니다.")
    return out


def _auto_done(plan: dict[str, Any]) -> dict[str, Any] | None:
    """계획을 만든 뒤 배울 사람에게 그 역량 · 기술의 경험(구조화 · 확정)이 생겼나 — 생겼으면 그 경험."""
    made = str(plan.get("made") or "")[:10]
    for hit in skill_hits(plan["learner"], plan["kind"], plan["name"]):
        when = max(hit["created_at"][:10], (hit["end"] or hit["start"] or "")[:10])
        if when and when >= made:
            return hit
    return None


def plans(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """계획 목록 — 진행 중인 것은 저절로 "됨" 을 본다(바뀌면 파일에도). 기한 지난 것 표시."""
    items = _read_plans()
    changed = False
    today = clock.today().isoformat()
    for plan in items:
        if plan.get("state") == "진행":
            hit = _auto_done(plan)
            if hit:
                plan.update({"state": "됨", "done_at": today, "done_by": "경험",
                             "evidence": {"id": hit["id"], "title": hit["title"]}})
                changed = True
    if changed:
        _write_plans(items)
    for plan in items:
        plan["overdue"] = plan.get("state") == "진행" and str(plan.get("due") or "") < today
    order = {"진행": 0, "됨": 1, "그만둠": 2}
    items.sort(key=lambda p: (order.get(p.get("state"), 9), str(p.get("due") or ""), p["id"]))
    return {"plans": items, "ways": list(PLAN_WAYS), "states": list(PLAN_STATES), "default_months": DEFAULT_MONTHS,
            "counts": {s: sum(1 for p in items if p.get("state") == s) for s in PLAN_STATES},
            "overdue": sum(1 for p in items if p["overdue"])}


def add_plan(data: dict[str, Any], by: str = "") -> dict[str, Any]:
    items = _read_plans()
    if len(items) >= PLANS_MAX:
        raise PlanError(f"계획은 {PLANS_MAX}개까지입니다 — 끝난 것을 정리해 주세요.")
    due = (clock.today() + timedelta(days=round(DEFAULT_MONTHS * 30.5))).isoformat()
    plan = _check_plan(data, {"id": _next_id(items), "kind": "역량", "name": "", "holders": [], "learner": "", "way": "짝 과제",
                              "due": due, "note": "", "state": "진행", "made": clock.today().isoformat(), "by": by})
    same = next((p for p in items if p.get("state") == "진행" and p["kind"] == plan["kind"]
                 and skill_rules.key(p["name"]) == skill_rules.key(plan["name"]) and p["learner"] == plan["learner"]), None)
    if same:
        raise PlanError(f"같은 계획이 이미 있습니다: {same['id']} — {same['name']} → {same['learner']}")
    items.append(plan)
    _write_plans(items)
    return plan


def update_plan(plan_id: str, data: dict[str, Any]) -> dict[str, Any]:
    items = _read_plans()
    for i, plan in enumerate(items):
        if plan["id"] == plan_id:
            items[i] = _check_plan(data, plan)
            _write_plans(items)
            return items[i]
    raise KeyError(plan_id)


def delete_plan(plan_id: str) -> None:
    items = _read_plans()
    left = [p for p in items if p["id"] != plan_id]
    if len(left) == len(items):
        raise KeyError(plan_id)
    _write_plans(left)
