"""팀원의 내 할 일 (TODO 242) — 팀원 PC 의 홈 [할 일] 이 그린다.

* 내 진행 과제 — 지금 담당이고 끝나지 않은(완료 · 중단이 아닌) 과제. 마지막 일지(누가 썼든) 며칠 전 · 마감 D-N.
* **일지 쓸 때가 됐어요**(C3) — 진행중 · 검토중인 과제에 마지막 일지가 `STALE_DAYS` 일을 넘었으면. 일지가 아직 없으면 시작일부터 센다.
  팀장 화면의 "오래 방치"(마지막 *보고* 로부터)와 다른 규칙이다 — 날수는 접수 묵힘(`intake_stale_days`)과 같은 14일.
* 회고를 적을 과제(237) · 팀장의 인정 한 줄(242 A2, 새것 순 다섯).
"""
from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any

from .. import clock
from .projects import NOT_SYSTEM_ENTRY

STALE_DAYS = 14
ACTIVE = ("in_progress", "reviewing")
PRAISE_LIMIT = 5


def retro_due(conn: sqlite3.Connection, name: str) -> list[dict[str, Any]]:
    """회고를 적을 과제 (237) — 내 것, 끝난 지 1년 안, 회고(내가 한 일 · 결과)가 모두 빈 것."""
    rows = conn.execute(
        "SELECT p.id, p.title, p.completed_at FROM project p JOIN project_contribution c ON c.project_id = p.id"
        " WHERE c.name = ? AND p.status = 'done' AND p.completed_at >= DATE(app_today(), '-365 day')"
        " AND COALESCE(c.did, '') = '' AND COALESCE(c.result, '') = ''"
        " ORDER BY p.completed_at DESC, p.id DESC",
        (name,),
    ).fetchall()
    return [dict(row) for row in rows]


def _days(since: str | None, today: date) -> int | None:
    try:
        return (today - date.fromisoformat(since[:10])).days if since else None
    except ValueError:
        return None


def my_work(conn: sqlite3.Connection, name: str) -> dict[str, Any]:
    today = clock.today()
    rows = conn.execute(
        "SELECT p.id, p.title, p.status, p.start_date, p.due_date, c.role,"
        f" (SELECT MAX(e.date) FROM entry e WHERE e.project_id = p.id AND {NOT_SYSTEM_ENTRY}) AS last_entry"
        " FROM project_contribution c JOIN project p ON p.id = c.project_id"
        " WHERE c.name = ? AND c.current = 1 AND p.status NOT IN ('done', 'dropped')",
        (name,),
    ).fetchall()
    projects = []
    for row in rows:
        since = row["last_entry"] or row["start_date"]
        quiet = _days(since, today)
        started = not row["start_date"] or row["start_date"] <= today.isoformat()
        due = _days(today.isoformat(), date.fromisoformat(row["due_date"])) if row["due_date"] else None
        projects.append({
            "id": row["id"], "title": row["title"], "status": row["status"], "role": row["role"] or "",
            "due_date": row["due_date"], "days_left": due,
            "last_entry": row["last_entry"], "days_since_entry": quiet,
            "stale": row["status"] in ACTIVE and started and quiet is not None and quiet > STALE_DAYS,
        })
    # 일지가 필요한 것 → 마감이 가까운 것 → 번호 순
    projects.sort(key=lambda item: (not item["stale"], item["days_left"] if item["days_left"] is not None else 99999, item["id"]))
    praises = [
        {"project_id": row["project_id"], "title": row["title"], "praise": row["praise"], "praise_at": row["praise_at"],
         "new": (_days(row["praise_at"], today) or 0) <= STALE_DAYS}
        for row in conn.execute(
            "SELECT c.project_id, p.title, c.praise, c.praise_at FROM project_contribution c JOIN project p ON p.id = c.project_id"
            " WHERE c.name = ? AND COALESCE(c.praise, '') <> '' ORDER BY c.praise_at DESC, c.project_id DESC LIMIT ?",
            (name, PRAISE_LIMIT))
    ]
    # 최근 마친 내 과제 (TODO 244 A4) — 끝난 지 30일 안
    recent_done = [
        {"id": row["id"], "title": row["title"], "completed_at": row["completed_at"]}
        for row in conn.execute(
            "SELECT p.id, p.title, p.completed_at FROM project p JOIN project_contribution c ON c.project_id = p.id"
            " WHERE c.name = ? AND p.status = 'done' AND p.completed_at >= DATE(app_today(), '-30 day')"
            " ORDER BY p.completed_at DESC, p.id DESC", (name,))
    ]
    return {"projects": projects, "retro_due": retro_due(conn, name), "praises": praises, "stale_days": STALE_DAYS,
            "recent_done": recent_done}
