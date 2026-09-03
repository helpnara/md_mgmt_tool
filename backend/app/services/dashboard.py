"""메인 화면 상단 대시보드.

한눈에 "지금 무엇을 봐야 하는가"만 답한다. 지표를 늘리지 않는다 —
숫자가 많아지면 대시보드가 아니라 또 하나의 표가 된다.

담는 것은 넷뿐이다.
  · 상태별 과제 수      — 눌러서 그 상태로 거른다
  · 속성별 과제 수      — 눌러서 그 속성으로 거른다
  · 담당자별 과제 수    — 지금 누가 몇 개를 들고 있나
  · 이번 주 보고 대상   — 상위 몇 건. 누르면 그 과제 상세로 간다
  · 마감 임박 / 기한 초과 — 작게. 있을 때만 눈에 띈다
  · 보고 리마인더       — 선정일·보고일에만. 매일 뜨면 곧 안 보게 된다
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


def _owner_counts(conn: sqlite3.Connection) -> list[dict]:
    """담당자별 과제 수. 많이 맡은 사람부터, 같으면 이름순.

    한 과제에 담당자가 여러 명일 수 있어 이 수들의 합은 전체 과제 수보다 클 수 있다.
    화면에서 그 사실을 알려 주도록, 합이 다른지는 보는 쪽이 판단한다.
    상태·속성 칸과 마찬가지로 끝난 과제도 포함한다 — 기준이 섞이면
    "N건"을 눌렀을 때 나오는 수와 어긋난다(5.8).
    """
    owners = [
        {"key": row["name"], "label": row["name"], "count": row["n"]}
        for row in conn.execute(
            "SELECT name, COUNT(*) AS n FROM project_owner GROUP BY name ORDER BY n DESC, name"
        )
    ]
    unassigned = conn.execute(
        "SELECT COUNT(*) AS n FROM project p"
        " WHERE NOT EXISTS (SELECT 1 FROM project_owner po WHERE po.project_id = p.id)"
    ).fetchone()["n"]
    if unassigned:
        owners.append({"key": "none", "label": "미지정", "count": unassigned})
    return owners


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
        "owners": _owner_counts(conn),
        "due_soon": due_soon,
        "due_soon_days": DUE_SOON_DAYS,
        "overdue": overdue,
        "report_date": reports_service.default_report_date(),
        # 오늘이 선정일도 보고일도 아니면 None 이다. 화면은 그때 배너를 접는다.
        "reminder": reports_service.reminder(conn),
        "candidates": candidates,
    }


__all__ = ["summary", "CANDIDATE_LIMIT", "DUE_SOON_DAYS", "TYPE_LABELS"]
