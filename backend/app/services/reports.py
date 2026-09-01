"""보고 이력.

진행 이력(계속 자라는 것)과 보고 기록(그 시점에 고정되는 것)을 분리한다.
확정된 보고 문서는 이후 진행일지가 바뀌어도 함께 바뀌지 않는다.
"""
from __future__ import annotations

import posixpath
import re
import shutil
import sqlite3
from datetime import date as date_cls
from datetime import datetime, timedelta
from typing import Any

from ..config import get_settings
from ..vault import markdown as md
from ..vault import paths
from ..vault.indexer import index_project
from .projects import now_iso, project_dir

# 진행일지 본문의 첨부 링크(../assets/…)를 보고 문서 위치에서 본 경로로 바꾼다.
_ENTRY_LINK = re.compile(r"\]\(\s*\.\./(assets/[^)\s]+)")

MAX_ELAPSED_TERM = 8.0  # 경과 항의 상한 (기준 주기의 8배)
IDLE_PENALTY = 0.25     # 미보고 진행일지가 하나도 없을 때 경과 항에 곱하는 계수

DRAFT_TEMPLATE = """## 보고 요약

{summary}

## 특이사항 및 이슈

## 다음 계획
"""


def default_report_date(today: date_cls | None = None) -> str:
    """주간 보고는 화요일에 한다. 오늘이 화요일이면 오늘, 아니면 다음 화요일."""
    today = today or date_cls.today()
    days_ahead = (1 - today.weekday()) % 7  # 월=0, 화=1
    return (today + timedelta(days=days_ahead)).isoformat()


def report_doc_dir(rel_path: str) -> str:
    return posixpath.dirname(rel_path)


def unreported_entries(conn: sqlite3.Connection, project_id: str) -> list[sqlite3.Row]:
    """확정된 보고에 아직 담기지 않은 진행일지."""
    return conn.execute(
        """
        SELECT e.* FROM entry e
         WHERE e.project_id = ?
           AND e.id NOT IN (
                 SELECT re.entry_id FROM report_entry re
                   JOIN report r ON r.id = re.report_id
                  WHERE r.frozen_at IS NOT NULL
               )
         ORDER BY e.date ASC, e.id ASC
        """,
        (project_id,),
    ).fetchall()


def _draft_body(entries: list[sqlite3.Row]) -> str:
    if not entries:
        return DRAFT_TEMPLATE.format(summary="- (이번 기간에 새로 작성된 진행일지가 없습니다)")

    summary = "\n".join(f"- {row['date']} {row['title']}" for row in entries)
    sections = []
    for row in entries:
        # 진행일지에서 옮겨 온 첨부 링크가 보고 문서 위치에서도 열리게 경로를 고친다.
        body = _ENTRY_LINK.sub(r"](../../\1", row["body"] or "")
        sections.append(f"### {row['date']} {row['title']}\n\n{body.strip()}")

    return (
        DRAFT_TEMPLATE.format(summary=summary).replace(
            "## 특이사항 및 이슈",
            "## 진행 내용\n\n" + "\n\n".join(sections) + "\n\n## 특이사항 및 이슈",
        )
    )


def create_draft(
    conn: sqlite3.Connection, project_id: str, report_date: str | None = None
) -> int:
    directory = project_dir(conn, project_id)
    report_date = report_date or default_report_date()
    folder = paths.safe_join(directory, "reports", report_date)
    if (folder / "report.md").exists():
        raise ValueError(f"{report_date} 보고 문서가 이미 있습니다.")
    (folder / "assets").mkdir(parents=True, exist_ok=True)

    entries = unreported_entries(conn, project_id)
    meta: dict[str, Any] = {
        "report_date": report_date,
        "title": f"{report_date} 보고",
        "covers_from": entries[0]["date"] if entries else None,
        "covers_to": entries[-1]["date"] if entries else None,
        "covered_entries": [row["rel_path"] for row in entries],
        "attachments": [],
        "frozen_at": None,
        "report_type": None,  # 예약 필드 — 필요해지면 UI에 노출한다
        "audience": None,
        "created_at": now_iso(),
    }
    md.save(folder / "report.md", md.MarkdownDoc(meta, _draft_body(entries)))
    index_project(conn, directory)
    conn.commit()

    row = conn.execute(
        "SELECT id FROM report WHERE project_id = ? AND rel_path = ?",
        (project_id, f"reports/{report_date}/report.md"),
    ).fetchone()
    return int(row["id"])


def report_row(conn: sqlite3.Connection, report_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM report WHERE id = ?", (report_id,)).fetchone()
    if row is None:
        raise KeyError(report_id)
    return row


def report_path(conn: sqlite3.Connection, report_id: int):
    row = report_row(conn, report_id)
    return row, paths.safe_join(project_dir(conn, row["project_id"]), row["rel_path"])


def update_report(conn: sqlite3.Connection, report_id: int, updates: dict[str, Any]) -> None:
    row, path = report_path(conn, report_id)
    if row["frozen_at"]:
        raise PermissionError("확정된 보고 문서는 수정할 수 없습니다. 먼저 확정을 해제하세요.")

    doc = md.load(path)
    body = updates.pop("body", None)
    meta = md.merge_meta(doc.meta, {k: v for k, v in updates.items() if k in {"title", "report_type", "audience"}})
    md.save(path, md.MarkdownDoc(meta, body if body is not None else doc.body))
    index_project(conn, project_dir(conn, row["project_id"]))
    conn.commit()


def freeze_report(conn: sqlite3.Connection, report_id: int) -> None:
    """보고 확정. 이 시점의 문서를 그대로 굳히고 포함된 진행일지를 기록한다."""
    row, path = report_path(conn, report_id)
    doc = md.load(path)
    entries = unreported_entries(conn, row["project_id"])
    covered = doc.meta.get("covered_entries") or [entry["rel_path"] for entry in entries]

    doc.meta = md.merge_meta(
        doc.meta,
        {
            "covered_entries": covered,
            "covers_from": doc.meta.get("covers_from") or (covered[0][5:15] if covered else None),
            "frozen_at": now_iso(),
        },
    )
    md.save(path, doc)
    index_project(conn, project_dir(conn, row["project_id"]))
    conn.commit()


def unfreeze_report(conn: sqlite3.Connection, report_id: int) -> None:
    """확정 해제. 되돌린 사실이 문서에 남도록 시각을 기록한다."""
    row, path = report_path(conn, report_id)
    doc = md.load(path)
    doc.meta = md.merge_meta(doc.meta, {"frozen_at": None, "unfrozen_at": now_iso()})
    md.save(path, doc)
    index_project(conn, project_dir(conn, row["project_id"]))
    conn.commit()


def delete_report(conn: sqlite3.Connection, report_id: int) -> None:
    row, path = report_path(conn, report_id)
    trash = get_settings().trash_dir
    trash.mkdir(parents=True, exist_ok=True)
    folder = path.parent
    target = paths.unique_path(
        trash, f"{row['project_id']}-report-{row['report_date']}-{datetime.now():%Y%m%d%H%M%S}", ""
    )
    shutil.move(str(folder), str(target))
    index_project(conn, project_dir(conn, row["project_id"]))
    conn.commit()


def candidates(conn: sqlite3.Connection, include_inactive: bool = False) -> list[dict]:
    """보고 대상 후보. 마지막 보고 후 경과일과 미보고 진행 분량으로 정렬한다."""
    from ..config import STATUSES

    settings = get_settings()
    cycle = max(1, settings.report_cycle_days)
    active = {key for key, _, candidate in STATUSES if candidate}
    today = date_cls.today()

    results = []
    for project in conn.execute("SELECT * FROM project ORDER BY id"):
        if not include_inactive and project["status"] not in active:
            continue

        unreported = unreported_entries(conn, project["id"])
        last_reported = project["last_reported_at"]
        baseline = last_reported or project["start_date"] or project["created_at"]
        days_since = None
        if baseline:
            try:
                days_since = (today - date_cls.fromisoformat(str(baseline)[:10])).days
            except ValueError:
                days_since = None

        # 오래 방치된 과제가 점수를 독점하지 않도록 경과 항에 상한을 둔다.
        elapsed_term = min((days_since or 0) / cycle, MAX_ELAPSED_TERM)
        # 보고할 새 내용이 없으면 아무리 오래됐어도 후순위다. 다만 목록에서 지우지는 않는다
        # ("오래 조용한 과제"는 그 자체로 확인할 거리가 되기 때문).
        if not unreported:
            elapsed_term *= IDLE_PENALTY
        score = round(elapsed_term + len(unreported) * 0.5, 2)
        results.append(
            {
                "id": project["id"],
                "title": project["title"],
                "status": project["status"],
                "group": project["grp"],
                "due_date": project["due_date"],
                "last_reported_at": last_reported,
                "days_since_report": days_since,
                "unreported_entries": len(unreported),
                "latest_entry_date": unreported[-1]["date"] if unreported else None,
                "score": score,
                "never_reported": last_reported is None,
            }
        )

    results.sort(key=lambda item: (-item["score"], item["id"]))
    return results
