"""메인 화면 상단 대시보드.

한눈에 "지금 무엇을 봐야 하는가"만 답한다. 지표를 늘리지 않는다 —
숫자가 많아지면 대시보드가 아니라 또 하나의 표가 된다.

담는 것은 넷뿐이다.
  · 상태별 과제 수      — 눌러서 그 상태로 거른다
  · 속성별 과제 수      — 눌러서 그 속성으로 거른다
  · 이번 주 보고 대상   — 상위 몇 건. 누르면 그 과제 상세로 간다
  · 마감 임박 / 기한 초과 — 작게. 있을 때만 눈에 띈다
"""
from __future__ import annotations

import sqlite3

from ..config import FINISHED_STATUSES, PROJECT_TYPES, STATUSES, TYPE_LABELS
from . import reports as reports_service

# 대시보드에 세우는 보고 대상 후보 수. 주간 회의에서 훑을 만큼만 보여 준다.
CANDIDATE_LIMIT = 5
# "마감 임박"으로 볼 잔여 일수
DUE_SOON_DAYS = 7


def _counts(conn: sqlite3.Connection, column: str) -> dict[str, int]:
    rows = conn.execute(f"SELECT {column} AS key, COUNT(*) AS n FROM project GROUP BY {column}")
    return {(row["key"] or ""): row["n"] for row in rows}


def summary(conn: sqlite3.Connection, limit: int = CANDIDATE_LIMIT) -> dict:
    status_counts = _counts(conn, "status")
    type_counts = _counts(conn, "type")

    placeholders = ",".join("?" * len(FINISHED_STATUSES))
    # 끝난 과제는 마감 경고에서 뺀다. 보류는 멈춰 있을 뿐이라 그대로 센다.
    overdue = conn.execute(
        f"SELECT COUNT(*) AS n FROM project"
        f" WHERE due_date IS NOT NULL AND due_date < DATE('now', 'localtime')"
        f"   AND status NOT IN ({placeholders})",
        FINISHED_STATUSES,
    ).fetchone()["n"]
    due_soon = conn.execute(
        f"SELECT COUNT(*) AS n FROM project"
        f" WHERE due_date IS NOT NULL"
        f"   AND due_date >= DATE('now', 'localtime')"
        f"   AND due_date <= DATE('now', 'localtime', '+{DUE_SOON_DAYS} day')"
        f"   AND status NOT IN ({placeholders})",
        FINISHED_STATUSES,
    ).fetchone()["n"]

    candidates = reports_service.candidates(conn)[:limit]

    return {
        "total": conn.execute("SELECT COUNT(*) AS n FROM project").fetchone()["n"],
        # 0건인 칸은 보내지 않는다. 빈 칸이 늘어나면 눈이 갈 곳을 잃는다.
        "statuses": [
            {"key": key, "label": label, "count": status_counts[key]}
            for key, label, _ in STATUSES
            if status_counts.get(key)
        ],
        "types": [
            {"key": key, "label": label, "count": type_counts[key]}
            for key, label in PROJECT_TYPES
            if type_counts.get(key)
        ]
        # 속성을 안 정한 과제도 세고, 눌러서 거를 수 있게 키를 준다.
        + ([{"key": "none", "label": "미지정", "count": type_counts[""]}] if type_counts.get("") else []),
        "due_soon": due_soon,
        "due_soon_days": DUE_SOON_DAYS,
        "overdue": overdue,
        "report_date": reports_service.default_report_date(),
        "candidates": candidates,
    }


__all__ = ["summary", "CANDIDATE_LIMIT", "DUE_SOON_DAYS", "TYPE_LABELS"]
