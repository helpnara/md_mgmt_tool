"""홈(첫 화면) 집계 (TODO 56 · ROADMAP R1).

대시보드가 **"지금 무엇을 봐야 하는가"** 라면, 홈은 **"우리 팀이 올해 무엇을 했는가"** 다.
목적이 다르므로 한 함수에 담지 않는다 — 대시보드는 지표를 늘리지 않기로 한 자리다.

**연도 기준이 둘이라는 점을 기억한다.**

| 무엇 | 기준 | 왜 |
|---|---|---|
| 과제 수 · 완료 · 효과 금액 | **과제 번호 앞 네 자리** | 대시보드·목록과 같은 기준이어야 수가 어긋나지 않는다 (DESIGN 5.8) |
| 보고 횟수 | **보고일(`report_date`)의 연도** | "올해 몇 번 보고했나"는 보고한 날로 세는 것이 자연스럽다 |

둘을 억지로 하나로 맞추면 어느 한쪽이 이상해진다. 대신 **화면이 이 사실을 글자로 밝힌다.**

**보고 횟수는 확정된 보고만 센다.** 초안은 아직 보고한 것이 아니다.

**담당자별 수의 합은 팀 합계보다 클 수 있다.** 한 과제에 담당자가 여럿이면 양쪽에 잡힌다.
효과 금액에서 특히 위험해서(사람별로 더하면 팀 합계를 넘는다) 팀 합계는 **과제 기준**으로
따로 내고, 화면은 사람별 표에 "담당 중복 포함" 이라고 적는다.
"""
from __future__ import annotations

import sqlite3
from datetime import date as date_cls

from ..config import FINISHED_STATUSES, PROJECT_TYPES
from . import reports as reports_service

# 연도 비교 막대에 세우는 해의 수. 더 늘리면 막대가 얇아지기만 한다.
COMPARE_YEARS = 5
# "오래 방치된 과제" 로 보여 줄 수. 셋을 넘으면 목록이지 요약이 아니다.
STALE_LIMIT = 3

_DONE = "done"


def _year_clause(year: str | None, alias: str = "p") -> tuple[str, list]:
    """과제 연도 조건. 과제 번호 앞 네 자리를 본다 (dashboard 와 같은 기준)."""
    if not year:
        return "", []
    return f" AND SUBSTR({alias}.id, 1, 4) = ?", [year]


def years(conn: sqlite3.Connection) -> list[str]:
    """과제가 실제로 있는 해. 최근 것부터."""
    rows = conn.execute(
        "SELECT DISTINCT SUBSTR(id, 1, 4) AS y FROM project"
        " WHERE SUBSTR(id, 1, 4) GLOB '[0-9][0-9][0-9][0-9]' ORDER BY y DESC"
    )
    return [row["y"] for row in rows]


def _team(conn: sqlite3.Connection, year: str | None) -> dict:
    clause, params = _year_clause(year)
    row = conn.execute(
        "SELECT COUNT(*) AS total,"
        f"       SUM(CASE WHEN status = '{_DONE}' THEN 1 ELSE 0 END) AS done,"
        "       SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) AS in_progress,"
        "       COALESCE(SUM(effect_expected), 0) AS effect_expected,"
        "       COALESCE(SUM(effect_verified), 0) AS effect_verified"
        f" FROM project p WHERE 1=1{clause}",
        params,
    ).fetchone()
    return {
        "total": row["total"] or 0,
        "done": row["done"] or 0,
        "in_progress": row["in_progress"] or 0,
        "effect_expected": round(row["effect_expected"] or 0, 2),
        "effect_verified": round(row["effect_verified"] or 0, 2),
        "reports": _report_count(conn, year),
    }


def _report_count(conn: sqlite3.Connection, year: str | None, owner: str | None = None) -> int:
    """확정된 보고의 수. 연도는 **보고일** 기준이다."""
    sql = "SELECT COUNT(*) AS n FROM report r WHERE r.frozen_at IS NOT NULL"
    params: list = []
    if year:
        sql += " AND SUBSTR(r.report_date, 1, 4) = ?"
        params.append(year)
    if owner is not None:
        sql += " AND EXISTS (SELECT 1 FROM project_owner po WHERE po.project_id = r.project_id AND po.name = ?)"
        params.append(owner)
    return conn.execute(sql, params).fetchone()["n"]


def _members(conn: sqlite3.Connection, year: str | None) -> list[dict]:
    """팀원별 성과. 사용자가 정한 네 가지 — 담당 건수 · 완료 · 효과 금액 · 보고 횟수."""
    clause, params = _year_clause(year)
    rows = conn.execute(
        "SELECT po.name AS name, COUNT(*) AS total,"
        f"       SUM(CASE WHEN p.status = '{_DONE}' THEN 1 ELSE 0 END) AS done,"
        "       SUM(CASE WHEN p.status = 'in_progress' THEN 1 ELSE 0 END) AS in_progress,"
        "       COALESCE(SUM(p.effect_expected), 0) AS effect_expected,"
        "       COALESCE(SUM(p.effect_verified), 0) AS effect_verified"
        " FROM project_owner po JOIN project p ON p.id = po.project_id"
        f" WHERE 1=1{clause} GROUP BY po.name",
        params,
    ).fetchall()

    members = []
    for row in rows:
        last = conn.execute(
            "SELECT MAX(r.report_date) AS d FROM report r"
            " JOIN project_owner po ON po.project_id = r.project_id"
            " WHERE po.name = ? AND r.frozen_at IS NOT NULL",
            (row["name"],),
        ).fetchone()["d"]
        members.append(
            {
                "name": row["name"],
                "total": row["total"],
                "done": row["done"] or 0,
                "in_progress": row["in_progress"] or 0,
                "effect_expected": round(row["effect_expected"] or 0, 2),
                "effect_verified": round(row["effect_verified"] or 0, 2),
                "reports": _report_count(conn, year, owner=row["name"]),
                # 마지막 보고는 연도를 걸지 않는다 — "이 사람이 마지막으로 보고한 때"가
                # 궁금한 것이지 "올해 안에서 마지막"이 궁금한 것이 아니다.
                "last_reported_at": last,
            }
        )
    members.sort(key=lambda item: (-item["total"], item["name"]))
    return members


def _types(conn: sqlite3.Connection, year: str | None) -> list[dict]:
    """속성별 과제 수와 효과 금액. 상부 보고에서 자주 요구되는 절단면이다."""
    clause, params = _year_clause(year)
    rows = {
        (row["type"] or ""): row
        for row in conn.execute(
            "SELECT type, COUNT(*) AS n,"
            f"       SUM(CASE WHEN status = '{_DONE}' THEN 1 ELSE 0 END) AS done,"
            "       COALESCE(SUM(effect_expected), 0) AS ee,"
            "       COALESCE(SUM(effect_verified), 0) AS ev"
            f" FROM project p WHERE 1=1{clause} GROUP BY type",
            params,
        )
    }
    out = []
    for key, label in [*PROJECT_TYPES, ("none", "미지정")]:
        row = rows.get("" if key == "none" else key)
        if not row:
            continue
        out.append(
            {
                "key": key,
                "label": label,
                "count": row["n"],
                "done": row["done"] or 0,
                "effect_expected": round(row["ee"] or 0, 2),
                "effect_verified": round(row["ev"] or 0, 2),
            }
        )
    return out


def _monthly_reports(conn: sqlite3.Connection, year: str | None) -> list[dict]:
    """월별 확정 보고 수. **빈 달이 곧 관리 공백**이라 0인 달도 자리를 남긴다."""
    if not year:
        return []
    counts = {
        row["m"]: row["n"]
        for row in conn.execute(
            "SELECT SUBSTR(report_date, 6, 2) AS m, COUNT(*) AS n FROM report"
            " WHERE frozen_at IS NOT NULL AND SUBSTR(report_date, 1, 4) = ? GROUP BY m",
            (year,),
        )
    }
    return [{"month": month, "count": counts.get(f"{month:02d}", 0)} for month in range(1, 13)]


def _compare(conn: sqlite3.Connection) -> list[dict]:
    """최근 몇 해를 나란히. 한 해만 보면 늘고 있는지 줄고 있는지 알 수 없다."""
    return [
        {"year": year, **{k: v for k, v in _team(conn, year).items()}}
        for year in years(conn)[:COMPARE_YEARS]
    ][::-1]  # 화면에는 왼쪽이 과거


def _stale(conn: sqlite3.Connection, limit: int = STALE_LIMIT) -> list[dict]:
    """오래 방치된 과제. 보고 대상과 겹쳐 보이지만 뜻이 다르다 —
    저쪽은 *이번 주에 할 일*, 이쪽은 *이미 새어 나간 것*."""
    items = [
        item
        for item in reports_service.candidates(conn)
        if not item["not_started"] and (item["days_since_report"] or 0) > 0
    ]
    return items[:limit]


def summary(conn: sqlite3.Connection, year: str | None = None) -> dict:
    available = years(conn)

    placeholders = ",".join("?" * len(FINISHED_STATUSES))
    clause, params = _year_clause(year)
    overdue = conn.execute(
        "SELECT COUNT(*) AS n FROM project p"
        " WHERE due_date IS NOT NULL AND due_date < DATE('now', 'localtime')"
        f"   AND status NOT IN ({placeholders}){clause}",
        (*FINISHED_STATUSES, *params),
    ).fetchone()["n"]
    due_soon = conn.execute(
        "SELECT COUNT(*) AS n FROM project p"
        " WHERE due_date IS NOT NULL AND due_date >= DATE('now', 'localtime')"
        "   AND due_date <= DATE('now', 'localtime', '+7 day')"
        f"   AND status NOT IN ({placeholders}){clause}",
        (*FINISHED_STATUSES, *params),
    ).fetchone()["n"]

    candidates = reports_service.candidates(conn)
    return {
        "year": year,
        "years": available,
        "today": date_cls.today().isoformat(),
        "this_week": {
            "report_date": reports_service.default_report_date(),
            "candidates": len(candidates),
            "due_soon": due_soon,
            "overdue": overdue,
            "stale": _stale(conn),
        },
        "team": _team(conn, year),
        "compare": _compare(conn),
        "members": _members(conn, year),
        "types": _types(conn, year),
        "monthly_reports": _monthly_reports(conn, year),
    }


__all__ = ["summary", "years", "COMPARE_YEARS", "STALE_LIMIT"]
