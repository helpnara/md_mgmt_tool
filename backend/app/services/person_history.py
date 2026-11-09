"""사람별 이력 (TODO 238 ①) — 과제(담당과 역할 · 237)와 교육 · 행사(팀원역량 · 72)를 한 사람 기준으로 모은다.

* 과제는 **담당했던 것만**(지금 · 예전, 238-2) — 진행일지 작성자는 233 앞이 모두 팀장 이름이라 섞인다. 일지만 쓴 과제는 수만.
* 연도는 **그 사람이 맡기 시작한 해**(담당 시작) — 없으면 과제 시작일 · 번호의 해.
* 끝 날짜 — 담당 끝, 없으면 과제가 끝났을 때 완료일(중단이면 "중단"), 아직이면 없음(화면이 "지금").
"""
from __future__ import annotations

import sqlite3
from typing import Any

from .. import clock
from .. import contributions
from .. import schemas as rules
from .projects import NOT_SYSTEM_ENTRY, _milestones_of
from . import settings as settings_service


def _end(row: sqlite3.Row) -> str | None:
    if row["to_date"]:
        return row["to_date"]
    if not row["current"]:
        return None
    if row["status"] == "done":
        return row["completed_at"]
    return None


def history(conn: sqlite3.Connection, name: str) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT c.*, p.title, p.status, p.start_date, p.due_date, p.completed_at, p.outcome,"
        " p.effect_expected, p.effect_verified, p.no_effect, p.body"
        " FROM project_contribution c JOIN project p ON p.id = c.project_id WHERE c.name = ?"
        " ORDER BY COALESCE(c.from_date, p.start_date, substr(p.id, 1, 4) || '-01-01') DESC, p.id DESC",
        (name,),
    ).fetchall()
    projects = []
    for row in rows:
        begin = row["from_date"] or row["start_date"]
        projects.append({
            "id": row["project_id"], "title": row["title"], "status": row["status"],
            "year": (begin or row["project_id"])[:4],
            "from": begin, "to": _end(row), "current": bool(row["current"]), "derived": bool(row["derived"]),
            "role": row["role"] or "", "part": row["part"] or "",
            "did": row["did"] or "", "result": row["result"] or "",
            "skills": rules.split_list(row["skills"]),
            "praise": row["praise"] or "", "praise_at": row["praise_at"],
            "milestones": _milestones_of(row["milestones"]),
            "star_entries": contributions.star_entries(conn, row["project_id"]),
            "outcome": row["outcome"] or "",
            "effect_expected": row["effect_expected"], "effect_verified": row["effect_verified"],
            "no_effect": bool(row["no_effect"]),
            # STAR 의 상황 · 과제 (TODO 244 B6) — 과제 개요의 배경 · 목표 절. 서식 안내(>)는 뺀다
            "context": {"background": overview_section(row["body"], "배경"), "goal": overview_section(row["body"], "목표")},
        })
    # 보고에 올라간 횟수 (TODO 242 A1) — 확정한 보고만. 233 앞 일지 작성자는 모두 팀장이라 *과제* 기준으로 센다
    today_year = clock.today().year
    report_counts: dict[str, dict[str, int]] = {}
    for r in conn.execute(
            "SELECT r.project_id, substr(r.report_date, 1, 4) AS y, COUNT(*) AS n FROM report r"
            " JOIN project_contribution c ON c.project_id = r.project_id AND c.name = ?"
            " WHERE r.frozen_at IS NOT NULL GROUP BY r.project_id, y", (name,)):
        report_counts.setdefault(r["project_id"], {})[r["y"]] = r["n"]
    for item in projects:
        counts = report_counts.get(item["id"], {})
        item["reports"] = sum(counts.values())
    reports_this_year = sum(c.get(str(today_year), 0) for c in report_counts.values())
    reports_last_year = sum(c.get(str(today_year - 1), 0) for c in report_counts.values())
    owned = {item["id"] for item in projects}
    entry_only = [
        r["project_id"] for r in conn.execute(
            "SELECT DISTINCT project_id FROM entry WHERE author = ?", (name,))
        if r["project_id"] not in owned
    ]
    today = clock.today().isoformat()
    activities = [
        {"id": r["id"], "date": r["date"], "end_date": r["end_date"], "kind": r["kind"], "title": r["title"],
         "host": r["host"], "hours": r["hours"], "takeaway": r["takeaway"] or "", "planned": r["date"] > today}
        for r in conn.execute(
            "SELECT id, date, end_date, kind, title, host, hours, takeaway FROM activity WHERE person = ?"
            " ORDER BY date DESC, id DESC", (name,))
    ]
    finished = [item for item in projects if item["status"] == "done"]
    # 많이 쓴 기술 · 도구 (TODO 239) — 과제 수로 센다
    skill_counts: dict[str, int] = {}
    for item in projects:
        for skill in item["skills"]:
            skill_counts[skill] = skill_counts.get(skill, 0) + 1
    top_skills = [{"name": key, "count": value}
                  for key, value in sorted(skill_counts.items(), key=lambda pair: (-pair[1], pair[0]))[:12]]
    roster = {person["name"]: person for person in settings_service.people()}
    person = roster.get(name)
    return {
        "name": name,
        "in_roster": person is not None,
        "leader": settings_service.leader_name() == name,
        "left_on": (person or {}).get("left_on") or None,
        "summary": {
            "projects": len(projects),
            "current": sum(1 for item in projects if item["current"] and item["status"] not in ("done", "dropped")),
            "lead": sum(1 for item in projects if item["role"] == "주관"),
            "done": len(finished),
            "retro_written": sum(1 for item in finished if item["did"] or item["result"]),
            "activities": sum(1 for item in activities if not item["planned"]),
            "entry_only": len(entry_only),
            "reports_this_year": reports_this_year,
            "reports_last_year": reports_last_year,
            "year": str(today_year),
        },
        "skills": top_skills,
        "projects": projects,
        "activities": activities,
    }


SECTION_MAX = 400


def overview_section(body: str | None, heading: str) -> str:
    """과제 개요에서 `## <heading>` 절의 글 (TODO 244) — 서식 안내 줄(`>`)은 빼고, 400자까지. 없으면 빈 글."""
    lines, inside = [], False
    for raw in (body or "").splitlines():
        line = raw.strip()
        if line.startswith("#"):
            title = line.lstrip("#").strip()
            if inside:
                break
            inside = title.startswith(heading)
            continue
        if inside and line and not line.startswith(">"):
            # 목록 줄은 글머리표를 떼고 " · " 로 잇는다 — "- 38건 → 20건 - 재현율 80%" 처럼 붙지 않게
            lines.append(line[2:].strip() if line[:2] in ("- ", "* ", "+ ") else line)
    text = " · ".join(lines)
    return text if len(text) <= SECTION_MAX else text[:SECTION_MAX].rstrip() + "…"


def _span(row: sqlite3.Row) -> tuple[str, str]:
    """그 사람이 그 과제를 맡은 기간(시작 해 · 끝 해의 날짜) — 끝이 없으면 오늘, 완료면 완료일."""
    start = row["from_date"] or row["start_date"] or f"{row['project_id'][:4]}-01-01"
    end = row["to_date"] or (row["completed_at"] if row["status"] == "done" else None) or clock.today().isoformat()
    return start, end


def year_review(conn: sqlite3.Connection, name: str, year: str) -> dict[str, Any]:
    """나의 한 해 (TODO 244 A3) — 그 해에 맡은 과제 · 마친 과제 · 주관 · 내가 쓴 일지 · 보고 · 중간 성과 · 교육,
    새로 쓴 기술 · 도구(그 앞 해까지 없던 것), 마친 과제의 그 밖의 성과. `last` 는 지난해 숫자(비교는 나의 지난해와만)."""
    rows = conn.execute(
        "SELECT c.project_id, c.role, c.skills, c.milestones, c.from_date, c.to_date, p.title, p.status,"
        " p.start_date, p.completed_at, p.outcome FROM project_contribution c JOIN project p ON p.id = c.project_id"
        " WHERE c.name = ?", (name,)).fetchall()

    def numbers(y: str) -> dict[str, Any]:
        active = [row for row in rows if _span(row)[0][:4] <= y <= _span(row)[1][:4]]
        done = [row for row in rows if row["status"] == "done" and (row["completed_at"] or "")[:4] == y]
        ids = [row["project_id"] for row in rows]
        marks = ",".join("?" for _ in ids) or "''"
        reports = conn.execute(
            f"SELECT COUNT(*) FROM report WHERE frozen_at IS NOT NULL AND substr(report_date, 1, 4) = ?"
            f" AND project_id IN ({marks})", (y, *ids)).fetchone()[0] if ids else 0
        entries = conn.execute(f"SELECT COUNT(*) FROM entry e WHERE e.author = ? AND substr(e.date, 1, 4) = ? AND {NOT_SYSTEM_ENTRY}",
                               (name, y)).fetchone()[0]
        activity = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(hours), 0) AS h FROM activity WHERE person = ? AND substr(date, 1, 4) = ?"
            " AND date <= ?", (name, y, clock.today().isoformat())).fetchone()
        milestones = sum(1 for row in rows for item in _milestones_of(row["milestones"]) if item["date"][:4] == y)
        return {"projects": len(active), "done": len(done), "lead": sum(1 for row in active if row["role"] == "주관"),
                "entries": entries, "reports": reports, "milestones": milestones,
                "activities": activity["n"], "hours": round(activity["h"] or 0, 1), "_active": active, "_done": done}

    now = numbers(year)
    last = numbers(str(int(year) - 1))
    before = {skill for row in rows if _span(row)[0][:4] < year for skill in rules.split_list(row["skills"])}
    seen: list[str] = []
    for row in now["_active"]:
        for skill in rules.split_list(row["skills"]):
            if skill not in before and skill not in seen:
                seen.append(skill)
    outcomes = [{"id": row["project_id"], "title": row["title"], "outcome": row["outcome"]}
                for row in sorted(now["_done"], key=lambda r: r["completed_at"] or "") if row["outcome"]]
    done_titles = [{"id": row["project_id"], "title": row["title"], "completed_at": row["completed_at"]}
                   for row in sorted(now["_done"], key=lambda r: r["completed_at"] or "")]
    strip = lambda d: {k: v for k, v in d.items() if not k.startswith("_")}  # noqa: E731
    return {"name": name, "year": year, **strip(now), "last": strip(last), "new_skills": seen,
            "outcomes": outcomes, "done_projects": done_titles}
