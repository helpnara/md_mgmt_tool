"""사람별 이력 (TODO 238 ①) — 과제(담당과 역할 · 237)와 교육 · 행사(팀원역량 · 72)를 한 사람 기준으로 모은다.

* 과제는 **담당했던 것만**(지금 · 예전, 238-2) — 진행일지 작성자는 233 앞이 모두 팀장 이름이라 섞인다. 일지만 쓴 과제는 수만.
* 연도는 **그 사람이 맡기 시작한 해**(담당 시작) — 없으면 과제 시작일 · 번호의 해.
* 끝 날짜 — 담당 끝, 없으면 과제가 끝났을 때 완료일(중단이면 "중단"), 아직이면 없음(화면이 "지금").
"""
from __future__ import annotations

import sqlite3
from typing import Any

from .. import clock
from .. import schemas as rules
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
        " p.effect_expected, p.effect_verified, p.no_effect"
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
            "outcome": row["outcome"] or "",
            "effect_expected": row["effect_expected"], "effect_verified": row["effect_verified"],
            "no_effect": bool(row["no_effect"]),
        })
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
        },
        "skills": top_skills,
        "projects": projects,
        "activities": activities,
    }
