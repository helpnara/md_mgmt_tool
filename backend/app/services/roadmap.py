"""다년도 과제 로드맵 (TODO 174) — 선행 과제로 이어진 줄기들을 한 화면에.

과제 상세의 단계 줄기(172)는 **과제 하나에서** 앞뒤를 본다. 관리자에게 필요한 것은 반대 방향이다 —
팀이 끌고 가는 다년도 과제가 **모두** 어디쯤 와 있고, 어느 줄기가 막혀 있고, 내년에 이어 세울 단계가
무엇인지. 그래서 이어진 과제가 둘 이상인 묶음(줄기)을 모두 모아 기간 · 단계 · 상태와 **살펴볼 것**을 함께 준다.

이 모듈은 색인만 읽는다 — 파일을 고치지 않는다. 단계를 세는 규칙은 172 와 같다(가장 긴 선행 길 + 1).
"""
from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any

from ..config import STATUS_LABELS

ENDED = {"done", "dropped"}          # 끝난 과제 — 지연 · 선행 경고를 따지지 않는다
STARTED = {"in_progress", "on_hold"}  # 이미 손을 댄 과제 — "선행이 아직" 을 따진다

# 살펴볼 것의 종류. 무거운 것(warn)은 붉게, 가벼운 것(info)은 흐리게 보인다.
KINDS: dict[str, str] = {
    "overdue": "warn",        # 마감이 지났는데 끝나지 않았다
    "pred_dropped": "warn",   # 선행이 중단됐는데 후속은 살아 있다
    "missing": "warn",        # 선행을 찾을 수 없다(보관함 · 번호 잘못)
    "pred_open": "info",      # 후속을 시작했는데 선행이 아직 끝나지 않았다(겹쳐 가는 것일 수 있다)
    "no_dates": "info",       # 시작일이나 마감일이 없어 막대를 다 그리지 못한다
    "next_open": "info",      # 올해 끝나는 마지막 단계 — 이어 갈 다음 단계 과제가 없다
}


def _end_of(row: dict[str, Any]) -> str | None:
    """막대의 끝 — 끝난 과제는 끝낸 날, 아니면 마감일."""
    if row["status"] == "done" and row.get("completed_at"):
        return row["completed_at"]
    return row.get("due_date")


def build(conn: sqlite3.Connection, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    today_text = today.isoformat()
    rows = {
        row["id"]: dict(row)
        for row in conn.execute(
            "SELECT id, title, status, type, grp, start_date, due_date, completed_at,"
            " effect_expected, effect_verified FROM project"
        )
    }
    owners: dict[str, list[str]] = {}
    for row in conn.execute("SELECT project_id, name FROM project_owner ORDER BY position, name"):
        owners.setdefault(row["project_id"], []).append(row["name"])
    preds: dict[str, list[str]] = {}
    succs: dict[str, list[str]] = {}
    for row in conn.execute("SELECT project_id, predecessor_id FROM project_predecessor ORDER BY predecessor_id"):
        if row["project_id"] not in rows:
            continue
        preds.setdefault(row["project_id"], []).append(row["predecessor_id"])
        succs.setdefault(row["predecessor_id"], []).append(row["project_id"])

    # 줄기 = 선행 · 후속으로 이어진 묶음. 찾을 수 없는 선행도 자리를 차지한다(끊긴 것이 보여야 한다).
    parent: dict[str, str] = {}

    def find(node: str) -> str:
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for child, items in preds.items():
        for pred in items:
            a, b = find(child), find(pred)
            if a != b:
                parent[a] = b
    groups: dict[str, list[str]] = {}
    for node in list(parent):
        groups.setdefault(find(node), []).append(node)

    # 단계 — 가장 긴 선행 길 + 1 (172 와 같다). 손으로 고친 파일의 고리에 대비해 지나온 길을 들고 간다.
    stage: dict[str, int] = {}

    def depth(node: str, trail: frozenset[str]) -> int:
        if node in stage:
            return stage[node]
        if node in trail or node not in rows:
            return 1
        value = 1 + max((depth(p, trail | {node}) for p in preds.get(node, [])), default=0)
        stage[node] = value
        return value

    lineages: list[dict[str, Any]] = []
    for members in groups.values():
        if len(members) < 2:
            continue
        projects: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []

        def warn(project_id: str, kind: str, text: str) -> None:
            warnings.append({"project_id": project_id, "kind": kind, "level": KINDS[kind], "text": text})

        for node in members:
            row = rows.get(node)
            if row is None:
                projects.append({
                    "id": node, "title": None, "status": None, "missing": True, "stage": 1,
                    "predecessors": [], "successors": sorted(succs.get(node, [])),
                })
                continue
            end = _end_of(row)
            info = {
                "id": node,
                "title": row["title"],
                "status": row["status"],
                "type": row["type"],
                "group": row["grp"],
                "owners": owners.get(node, []),
                "start_date": row["start_date"],
                "due_date": row["due_date"],
                "completed_at": row["completed_at"],
                "end_date": end,
                "effect_expected": row["effect_expected"],
                "effect_verified": row["effect_verified"],
                "stage": depth(node, frozenset()),
                "predecessors": preds.get(node, []),
                "successors": sorted(succs.get(node, [])),
                "missing": False,
            }
            projects.append(info)
            status = row["status"]
            alive = status not in ENDED
            if alive and row["due_date"] and row["due_date"] < today_text:
                warn(node, "overdue", f"마감 {row['due_date']} 이 지났습니다 — {STATUS_LABELS.get(status, status)}")
            for pred in preds.get(node, []):
                pred_row = rows.get(pred)
                if pred_row is None:
                    warn(node, "missing", f"선행 {pred} 를 찾을 수 없습니다 — 삭제 보관함에 있거나 번호가 바뀌었습니다")
                elif alive and pred_row["status"] == "dropped":
                    warn(node, "pred_dropped", f"선행 {pred} 이 중단됐는데 이 과제는 {STATUS_LABELS.get(status, status)}입니다")
                elif status in STARTED and pred_row["status"] not in ENDED:
                    warn(node, "pred_open", f"선행 {pred} 이 아직 {STATUS_LABELS.get(pred_row['status'], pred_row['status'])}입니다")
            if not row["start_date"] or not end:
                warn(node, "no_dates", "시작일 · 마감일이 다 있어야 막대가 그려집니다")
            if not succs.get(node) and status != "dropped" and end and end[:4] == str(today.year):
                warn(node, "next_open", f"올해({today.year}) 끝나는 마지막 단계입니다 — 이어 갈 다음 단계 과제가 없습니다")

        present = [item for item in projects if not item["missing"]]
        if not present:
            continue
        projects.sort(key=lambda item: (item["stage"], item.get("start_date") or "9999", item["id"]))
        starts = [item["start_date"] for item in present if item.get("start_date")]
        ends = [item["end_date"] for item in present if item.get("end_date")]
        statuses = [item["status"] for item in present]
        if any(s in STARTED or s == "reviewing" for s in statuses):
            state = "active"
        elif all(s in ENDED for s in statuses):
            state = "ended"
        else:
            state = "planned"
        live_stages = [item["stage"] for item in present if item["status"] not in ENDED]
        # 줄기의 이름 — 1단계에서 가장 먼저 시작한 과제의 이름(줄기의 시작)
        root = next(item for item in projects if not item["missing"])
        lineages.append({
            "key": root["id"],
            "title": root["title"],
            "state": state,
            "stage_count": max(item["stage"] for item in projects),
            "current_stage": max(live_stages) if live_stages else None,
            "start_date": min(starts) if starts else None,
            "end_date": max(ends) if ends else None,
            "effect_expected": sum(item["effect_expected"] or 0 for item in present),
            "effect_verified": sum(item["effect_verified"] or 0 for item in present),
            "projects": projects,
            "warnings": warnings,
        })

    order = {"active": 0, "planned": 1, "ended": 2}
    lineages.sort(key=lambda item: (order[item["state"]], -(int((item["end_date"] or "0000")[:4])), item["key"]))
    return {
        "today": today_text,
        "lineages": lineages,
        "summary": {
            "lineages": len(lineages),
            "projects": sum(len([p for p in item["projects"] if not p["missing"]]) for item in lineages),
            "active": sum(1 for item in lineages if item["state"] == "active"),
            "warn": sum(1 for item in lineages for w in item["warnings"] if w["level"] == "warn"),
            "next_open": sum(1 for item in lineages for w in item["warnings"] if w["kind"] == "next_open"),
        },
    }
