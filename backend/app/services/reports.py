"""보고 이력.

진행 이력(계속 자라는 것)과 보고 기록(그 시점에 고정되는 것)을 분리한다.
확정된 보고 문서는 이후 진행일지가 바뀌어도 함께 바뀌지 않는다.
"""
from __future__ import annotations

import posixpath
from pathlib import Path
import re
import sqlite3
from datetime import date as date_cls
from datetime import datetime, timedelta
from typing import Any

from ..config import get_settings
from ..vault import markdown as md
from ..vault import paths
from ..vault.indexer import index_project
from . import settings as settings_service
from . import trash as trash_service
from .projects import now_iso, project_dir

# 진행일지 본문의 첨부 링크(../assets/…)를 보고 문서 위치에서 본 경로로 바꾼다.
_ENTRY_LINK = re.compile(r"\]\(\s*\.\./(assets/[^)\s]+)")

DRAFT_TEMPLATE = """## 보고 요약

{summary}

## 특이사항 및 이슈

## 다음 계획
"""


def default_report_date(today: date_cls | None = None) -> str:
    """다음 보고 예정일. 오늘이 보고 요일이면 오늘, 아니면 돌아오는 그 요일.

    보고 요일은 팀마다 다르므로 설정에서 읽는다 (기본값 화요일).
    리마인더도 **같은 값**을 본다 — 따로 두면 "내일 보고입니다" 안내가
    실제 보고 예정일과 어긋난다.
    """
    today = today or date_cls.today()
    days_ahead = (settings_service.report_weekday() - today.weekday()) % 7
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
        return settings_service.report_template().format(summary="- (이번 기간에 새로 작성된 진행일지가 없습니다)")

    summary = "\n".join(f"- {row['date']} {row['title']}" for row in entries)
    sections = []
    for row in entries:
        # 진행일지에서 옮겨 온 첨부 링크가 보고 문서 위치에서도 열리게 경로를 고친다.
        body = _ENTRY_LINK.sub(r"](../../\1", row["body"] or "")
        sections.append(f"### {row['date']} {row['title']}\n\n{body.strip()}")

    return (
        settings_service.report_template().format(summary=summary).replace(
            "## 특이사항 및 이슈",
            "## 진행 내용\n\n" + "\n\n".join(sections) + "\n\n## 특이사항 및 이슈",
        )
    )


def create_draft(
    conn: sqlite3.Connection,
    project_id: str,
    report_date: str | None = None,
    author: str | None = None,
    audience: str | None = None,
) -> int:
    directory = project_dir(conn, project_id)
    report_date = paths.validate_date(report_date, default_report_date())
    # 같은 날짜에 중간·완료 보고를 각각 남길 수 있어야 한다.
    # 첫 건은 reports/2026-09-08/, 다음부터 -2, -3 … 을 붙인다.
    folder = paths.unique_path(directory / "reports", report_date, "")
    (folder / "assets").mkdir(parents=True, exist_ok=True)

    entries = unreported_entries(conn, project_id)
    meta: dict[str, Any] = {
        "report_date": report_date,
        "title": f"{report_date} 보고",
        "covers_from": entries[0]["date"] if entries else None,
        "covers_to": entries[-1]["date"] if entries else None,
        "covered_entries": [row["rel_path"] for row in entries],
        "author": settings_service.current_author(author) or None,
        "attachments": [],
        "frozen_at": None,
        "report_type": None,  # 예약 필드 — 필요해지면 UI에 노출한다
        "audience": (audience or "").strip() or None,
        "created_at": now_iso(),
    }
    md.save(folder / "report.md", md.MarkdownDoc(meta, _draft_body(entries)))
    index_project(conn, directory)
    conn.commit()

    rel_path = (folder / "report.md").relative_to(directory).as_posix()
    row = conn.execute(
        "SELECT id FROM report WHERE project_id = ? AND rel_path = ?", (project_id, rel_path)
    ).fetchone()
    if row is None:
        raise RuntimeError(f"보고 문서를 인덱싱하지 못했습니다: {rel_path}")
    return int(row["id"])


def report_row(conn: sqlite3.Connection, report_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM report WHERE id = ?", (report_id,)).fetchone()
    if row is None:
        raise KeyError(report_id)
    return row


def report_path(conn: sqlite3.Connection, report_id: int):
    row = report_row(conn, report_id)
    return row, paths.safe_join(project_dir(conn, row["project_id"]), row["rel_path"])


# 확정 뒤에도 고칠 수 있는 항목. 보고 '내용'이 아니라 꼬리표에 해당한다.
# 보고일은 여기 없다 — 확정된 보고의 날짜는 "언제 보고했는가"라는 사실이므로,
# 고치려면 확정을 먼저 풀어야 한다.
EDITABLE_WHEN_FROZEN = {"audience", "title", "report_type"}
META_FIELDS = {"title", "report_type", "audience", "report_date"}


def _move_report_folder(
    conn: sqlite3.Connection, report_id: int, directory: Path, path: Path, new_date: str
) -> Path:
    """보고일이 바뀌면 문서가 든 폴더도 따라 옮긴다.

    보고 문서는 `reports/<보고일>/report.md` 에 있고 첨부도 그 아래에 있다.
    날짜만 고치고 폴더를 두면 폴더 이름과 내용이 어긋나, 나중에 폴더만 보고는
    무슨 보고인지 알 수 없게 된다. 첨부까지 함께 옮겨야 하므로 폴더째 옮긴다.
    """
    folder = path.parent
    target = paths.unique_path(folder.parent, new_date, "")
    paths.move(folder, target)
    new_path = target / path.name

    old_rel, new_rel = (
        path.relative_to(directory).as_posix(),
        new_path.relative_to(directory).as_posix(),
    )
    # 인덱스가 '새 문서 + 사라진 문서'로 보고 id를 새로 발급하지 않도록 먼저 경로를 옮겨 둔다.
    # id가 바뀌면 화면이 잡고 있던 보고를 잃고, 어떤 진행일지를 담았는지도 끊긴다.
    conn.execute("UPDATE report SET rel_path = ? WHERE id = ?", (new_rel, report_id))
    old_prefix, new_prefix = f"{old_rel.rsplit('/', 1)[0]}/", f"{new_rel.rsplit('/', 1)[0]}/"
    conn.execute(
        "UPDATE attachment SET rel_path = ? || SUBSTR(rel_path, ?)"
        " WHERE report_id = ? AND rel_path LIKE ? || '%'",
        (new_prefix, len(old_prefix) + 1, report_id, old_prefix),
    )
    return new_path


def update_report(conn: sqlite3.Connection, report_id: int, updates: dict[str, Any]) -> None:
    row, path = report_path(conn, report_id)
    if row["frozen_at"]:
        # 피보고자를 잘못 적었다고 확정을 풀었다 다시 걸 이유는 없다.
        # 다만 본문은 그대로 잠근다 — 그 시점의 기록이어야 하기 때문이다.
        if set(updates) - EDITABLE_WHEN_FROZEN:
            raise PermissionError(
                "확정된 보고의 본문은 수정할 수 없습니다. "
                "피보고자·제목만 고칠 수 있고, 내용을 고치려면 먼저 확정을 해제하세요."
            )

    md.ensure_unchanged(path, row["file_mtime"])
    doc = md.load(path)
    body = updates.pop("body", None)

    # 보고일을 바꾸면 폴더도 함께 옮긴다.
    new_date = updates.get("report_date")
    if new_date is not None:
        new_date = paths.validate_date(new_date, row["report_date"])
        updates["report_date"] = new_date
        # 제목을 손대지 않았다면(기본 제목 그대로면) 날짜를 따라가게 한다.
        if "title" not in updates and doc.meta.get("title") == f"{row['report_date']} 보고":
            updates["title"] = f"{new_date} 보고"

    meta = md.merge_meta(doc.meta, {k: v for k, v in updates.items() if k in META_FIELDS})
    md.save(path, md.MarkdownDoc(meta, body if body is not None else doc.body))

    directory = project_dir(conn, row["project_id"])
    if new_date is not None and new_date != row["report_date"]:
        path = _move_report_folder(conn, row["id"], directory, path, new_date)
    index_project(conn, directory)
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
    """보고 문서를 보관함으로 옮긴다.

    **확정된 보고는 지우지 못한다** (TODO 61 — 2026-09-04 사용자 결정).
    그 문서는 "언제 무엇을 보고했는가"라는 사실이라, 확정을 한 번 풀게 하는 것 자체가
    "이건 기록이다"라는 신호가 된다. 지우려면 확정을 먼저 해제한다.
    """
    row, path = report_path(conn, report_id)
    if row["frozen_at"]:
        raise PermissionError(
            "확정된 보고는 지울 수 없습니다. 지우려면 [확정 해제]를 먼저 눌러 주세요."
        )
    trash = get_settings().trash_dir
    trash.mkdir(parents=True, exist_ok=True)
    folder = path.parent
    target = paths.unique_path(
        trash, f"{row['project_id']}-report-{row['report_date']}-{datetime.now():%Y%m%d%H%M%S}", ""
    )
    paths.move(folder, target)
    trash_service.record(
        "report",
        label=f"{row['report_date']} 보고" + (f" · {row['audience']}" if row["audience"] else ""),
        moved_to=target,
        origin=folder,
        project_id=row["project_id"],
    )
    index_project(conn, project_dir(conn, row["project_id"]))
    conn.commit()


def last_report_info(conn: sqlite3.Connection, project_id: str) -> sqlite3.Row | None:
    """마지막으로 **확정한** 보고 한 건.

    `project.last_reported_at` 은 날짜만 들고 있어 "언제"까지만 답한다. 정작 알고 싶은 것은
    **누구에게 보고했는가**다 — 팀 주간회의에 올린 것과 전사 보고에 올린 것은 같은 날짜라도
    수준이 다르다. 여기서 그 한 건을 통째로 집어 온다.
    """
    return conn.execute(
        "SELECT report_date, audience, title, id FROM report"
        " WHERE project_id = ? AND frozen_at IS NOT NULL"
        " ORDER BY report_date DESC, id DESC LIMIT 1",
        (project_id,),
    ).fetchone()


# 보고 대상 표에서 열 머리글을 눌러 정렬할 수 있는 값들 (TODO 57).
# 기본은 아래 `_default_key` — 어느 한 열로 표현할 수 없는 순서라 여기 넣지 않는다.
CANDIDATE_SORTS = ("id", "title", "status", "type", "last_reported_at", "audience", "unreported")


def candidates(
    conn: sqlite3.Connection,
    include_inactive: bool = False,
    *,
    status: str | None = None,
    type: str | None = None,
    owner: str | None = None,
    sort: str | None = None,
    order: str = "asc",
) -> list[dict]:
    """보고 대상 후보.

    **기본 순서** (TODO 52 — 사용자가 정한 규칙)

    1. **한 번도 보고하지 않은 과제가 맨 위.** 시작이 오래된 것부터.
    2. 그다음은 **마지막 보고가 오래된 것부터** (D+150 이 D+100 보다 위).
    3. 같으면 미보고 진행일지가 많은 쪽, 그래도 같으면 과제 번호 순.

    예전에는 점수 하나로 줄을 세웠는데 두 가지가 어긋났다.
    경과일에 상한(기준 주기의 8배 = 56일)이 있어 **D+100 과 D+150 이 같은 값**이 됐고,
    보고한 적 없는 과제는 기준일이 시작일이라 오히려 **맨 아래**로 갔다.
    "오래 방치된 것이 먼저"라는 규칙은 상한도 예외도 없어야 지켜진다.
    """
    from ..config import STATUSES

    active = {key for key, _, candidate in STATUSES if candidate}
    today = date_cls.today()

    results = []
    for project in conn.execute("SELECT * FROM project ORDER BY id"):
        if not include_inactive and project["status"] not in active:
            continue
        if status and project["status"] != status:
            continue
        if type == "none":
            if project["type"]:
                continue
        elif type and project["type"] != type:
            continue
        if owner is not None and not _has_owner(conn, project["id"], owner):
            continue

        unreported = unreported_entries(conn, project["id"])
        last_reported = project["last_reported_at"]
        last_report = last_report_info(conn, project["id"])
        days_since = _days_between(last_reported or project["start_date"] or project["created_at"], today)

        results.append(
            {
                "id": project["id"],
                "title": project["title"],
                "status": project["status"],
                "type": project["type"],
                "group": project["grp"],
                "due_date": project["due_date"],
                "owners": [row["name"] for row in conn.execute(
                    "SELECT name FROM project_owner WHERE project_id = ? ORDER BY position, name",
                    (project["id"],),
                )],
                "last_reported_at": last_reported,
                # 날짜만으로는 어떤 수준의 보고였는지 알 수 없다. 보고처를 함께 준다.
                "last_report_audience": last_report["audience"] if last_report else None,
                "last_report_id": last_report["id"] if last_report else None,
                "days_since_report": days_since,
                "unreported_entries": len(unreported),
                "latest_entry_date": unreported[-1]["date"] if unreported else None,
                "never_reported": last_reported is None,
            }
        )

    results.sort(key=_sort_key(sort, order))
    return results


def _has_owner(conn: sqlite3.Connection, project_id: str, owner: str) -> bool:
    if owner == "none":
        row = conn.execute(
            "SELECT 1 FROM project_owner WHERE project_id = ? LIMIT 1", (project_id,)
        ).fetchone()
        return row is None
    row = conn.execute(
        "SELECT 1 FROM project_owner WHERE project_id = ? AND name = ? LIMIT 1", (project_id, owner)
    ).fetchone()
    return row is not None


def _days_between(baseline: object, today: date_cls) -> int | None:
    if not baseline:
        return None
    try:
        return (today - date_cls.fromisoformat(str(baseline)[:10])).days
    except ValueError:
        return None


def _default_key(item: dict) -> tuple:
    """기본 순서 — 보고 이력 없음 먼저, 그다음 마지막 보고가 오래된 것부터."""
    return (
        0 if item["never_reported"] else 1,
        # 오래된 것이 먼저이므로 경과일은 큰 것이 앞. 날짜를 못 읽으면 뒤로 보낸다.
        -(item["days_since_report"] if item["days_since_report"] is not None else -1),
        -item["unreported_entries"],
        item["id"],
    )


def _sort_key(sort: str | None, order: str):
    """열 머리글로 고른 정렬 (TODO 57). 고르지 않았으면 기본 순서.

    빈 값은 **오름·내림 어느 쪽이든 항상 뒤로** 보낸다. 오름차순일 때만 앞에 오면
    같은 열을 두 번 눌렀을 때 빈 줄이 위아래로 튀어 예측이 안 된다.
    """
    if sort not in CANDIDATE_SORTS:
        return _default_key

    descending = order == "desc"

    def key(item: dict) -> tuple:
        if sort == "unreported":
            raw: object = item["unreported_entries"]
        elif sort == "audience":
            raw = item["last_report_audience"]
        else:
            raw = item.get(sort)
        missing = raw is None or raw == ""
        if isinstance(raw, (int, float)):
            value: object = -raw if descending else raw
        else:
            value = str(raw or "")
        # 정렬 방향과 무관하게 빈 값을 뒤로 두려고, 뒤집기 전에 자리를 먼저 정한다.
        return (1 if missing else 0, value, item["id"])

    if not descending:
        return key

    def reversed_key(item: dict):
        first, value, ident = key(item)
        return (first, _Reversed(value) if isinstance(value, str) else value, ident)

    return reversed_key


class _Reversed:
    """문자열을 거꾸로 세우기 위한 감싸개. 숫자는 부호를 뒤집으면 되지만 문자열은 안 된다."""

    __slots__ = ("value",)

    def __init__(self, value: str) -> None:
        self.value = value

    def __lt__(self, other: "_Reversed") -> bool:
        return other.value < self.value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Reversed) and other.value == self.value


# ─────────────────────────────────────────────────────────────────────────────
# 보고 이력 찾기 (T13)
#
# 보고 문서는 과제 폴더 안에 흩어져 있다. 과제를 가로질러 한 번에 훑을 수 있게,
# 보고만 따로 모아 보는 길을 낸다. (상단 검색창은 TODO 53 에서 따로 다룬다)
# ─────────────────────────────────────────────────────────────────────────────

SEARCH_LIMIT = 200


def search(
    conn: sqlite3.Connection,
    *,
    audience: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    query: str | None = None,
    project_id: str | None = None,
    state: str | None = None,
    limit: int = SEARCH_LIMIT,
) -> list[dict]:
    """조건에 맞는 보고 문서를 최근 순으로 돌려준다.

    본문은 담지 않는다 — 목록에서 쓸 일이 없고, 보고가 쌓이면 응답만 무거워진다.
    대신 검색어에 걸린 자리를 알 수 있게 짧은 발췌를 붙인다.
    """
    where = ["1=1"]
    params: list[Any] = []

    if audience:
        # 회의체 이름은 "전사 주요업무 보고"처럼 길어 정확히 치기 어렵다. 부분 일치로 본다.
        where.append("LOWER(IFNULL(r.audience, '')) LIKE '%' || LOWER(?) || '%'")
        params.append(audience)
    if date_from:
        where.append("r.report_date >= ?")
        params.append(date_from)
    if date_to:
        where.append("r.report_date <= ?")
        params.append(date_to)
    if project_id:
        where.append("r.project_id = ?")
        params.append(project_id)
    if state == "frozen":
        where.append("r.frozen_at IS NOT NULL")
    elif state == "draft":
        where.append("r.frozen_at IS NULL")
    if query:
        where.append(
            "(LOWER(IFNULL(r.title, '')) LIKE '%' || LOWER(?) || '%'"
            " OR LOWER(IFNULL(r.body, '')) LIKE '%' || LOWER(?) || '%'"
            " OR LOWER(p.title) LIKE '%' || LOWER(?) || '%')"
        )
        params.extend([query, query, query])

    rows = conn.execute(
        "SELECT r.*, p.title AS project_title, p.dir_name AS project_dir,"
        "       p.status AS project_status, p.type AS project_type"
        "  FROM report r JOIN project p ON p.id = r.project_id"
        f" WHERE {' AND '.join(where)}"
        # 같은 날 여러 건이면 나중에 만든 것이 위로. 날짜만으로는 순서가 흔들린다.
        " ORDER BY r.report_date DESC, r.id DESC"
        " LIMIT ?",
        [*params, max(1, limit)],
    ).fetchall()

    results = []
    for row in rows:
        results.append(
            {
                "id": row["id"],
                "project_id": row["project_id"],
                "project_title": row["project_title"],
                "project_status": row["project_status"],
                "project_type": row["project_type"],
                "report_date": row["report_date"],
                "title": row["title"],
                "audience": row["audience"],
                "author": row["author"],
                "frozen_at": row["frozen_at"],
                "frozen": bool(row["frozen_at"]),
                "covers_from": row["covers_from"],
                "covers_to": row["covers_to"],
                "entry_count": conn.execute(
                    "SELECT COUNT(*) AS n FROM report_entry WHERE report_id = ?", (row["id"],)
                ).fetchone()["n"],
                "excerpt": _excerpt(row["body"], query),
            }
        )
    return results


def _excerpt(body: str | None, query: str | None, width: int = 60) -> str:
    """검색어 둘레를 잘라 낸다. 검색어가 없으면 첫 줄 몇 글자."""
    text = " ".join((body or "").split())
    if not text:
        return ""
    if query:
        found = text.lower().find(query.lower())
        if found >= 0:
            start = max(0, found - width // 2)
            piece = text[start : start + width]
            return ("…" if start > 0 else "") + piece + ("…" if start + width < len(text) else "")
    return text[:width] + ("…" if len(text) > width else "")


# ─────────────────────────────────────────────────────────────────────────────
# 지난 보고 대비 변경분 (T11)
#
# 보고 자리에서 가장 많이 받는 질문이 "지난주와 뭐가 달라졌나"다.
# 확정된 보고는 이미 그 시점 그대로 굳어 있으므로, 비교만 하면 답이 나온다.
# ─────────────────────────────────────────────────────────────────────────────

DIFF_CONTEXT = 2  # 바뀐 줄 앞뒤로 함께 보여 줄 줄 수


def previous_report(conn: sqlite3.Connection, row: sqlite3.Row) -> sqlite3.Row | None:
    """같은 과제에서 이 보고 **직전에 확정된** 보고.

    초안끼리 비교하면 기준이 흔들린다. "지난번에 실제로 보고한 것"만 상대로 삼는다.
    같은 날짜에 여러 건이면 id 가 작은 쪽이 앞선 것이다.
    """
    return conn.execute(
        "SELECT * FROM report"
        " WHERE project_id = ? AND frozen_at IS NOT NULL AND id <> ?"
        "   AND (report_date < ? OR (report_date = ? AND id < ?))"
        " ORDER BY report_date DESC, id DESC LIMIT 1",
        (row["project_id"], row["id"], row["report_date"], row["report_date"], row["id"]),
    ).fetchone()


def diff_with_previous(conn: sqlite3.Connection, report_id: int) -> dict:
    """이 보고와 직전 확정 보고의 차이."""
    import difflib

    row = report_row(conn, report_id)
    before = previous_report(conn, row)
    if before is None:
        return {"previous": None, "added": 0, "removed": 0, "lines": []}

    old_lines = (before["body"] or "").splitlines()
    new_lines = (row["body"] or "").splitlines()

    lines: list[dict[str, str]] = []
    added = removed = 0
    opcodes = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False).get_opcodes()
    for index, (tag, i1, i2, j1, j2) in enumerate(opcodes):
        if tag == "equal":
            same = new_lines[j1:j2]
            # 안 바뀐 줄은 **바뀐 줄 둘레만** 남긴다. 전체를 실으면 "무엇이 달라졌나"가
            # 도로 묻히고, 문서가 길수록 응답만 무거워진다.
            head = [] if index == 0 else same[:DIFF_CONTEXT]
            tail = [] if index == len(opcodes) - 1 else same[-DIFF_CONTEXT:]
            if len(head) + len(tail) >= len(same):
                lines.extend({"kind": "same", "text": text} for text in same)
                continue
            lines.extend({"kind": "same", "text": text} for text in head)
            lines.append({"kind": "gap", "text": f"⋯ {len(same) - len(head) - len(tail)}줄 같음"})
            lines.extend({"kind": "same", "text": text} for text in tail)
            continue
        for text in old_lines[i1:i2]:
            lines.append({"kind": "del", "text": text})
            removed += 1
        for text in new_lines[j1:j2]:
            lines.append({"kind": "add", "text": text})
            added += 1

    return {
        "previous": {
            "id": before["id"],
            "report_date": before["report_date"],
            "title": before["title"],
            "audience": before["audience"],
        },
        "added": added,
        "removed": removed,
        "lines": lines,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 보고 리마인더 (T12)
#
# 보고 요일 하루 전에 대상을 고르고, 그날 보고한다. 이 주기는 사람이 기억할 일이
# 아니라 화면이 알려 줄 일이다. 다만 매일 뜨면 곧 안 보게 되므로,
# **선정일과 보고일에만** 띄운다. 요일은 설정에서 읽는다 (TODO 50).
# ─────────────────────────────────────────────────────────────────────────────

def reminder(conn: sqlite3.Connection, today: date_cls | None = None) -> dict | None:
    """오늘이 선정일이거나 보고일이면 알림 내용을, 아니면 None.

    보고 요일은 설정에서 읽고, 선정일은 그 **하루 전**이다.
    """
    today = today or date_cls.today()
    report_weekday = settings_service.report_weekday()
    weekday = today.weekday()
    if weekday == report_weekday:
        phase = "report"
    elif weekday == (report_weekday - 1) % 7:
        phase = "select"
    else:
        return None

    report_date = default_report_date(today)
    drafts = conn.execute(
        "SELECT COUNT(*) AS n FROM report WHERE report_date = ? AND frozen_at IS NULL",
        (report_date,),
    ).fetchone()["n"]
    done = conn.execute(
        "SELECT COUNT(*) AS n FROM report WHERE report_date = ? AND frozen_at IS NOT NULL",
        (report_date,),
    ).fetchone()["n"]
    # 후보는 대시보드가 이미 계산해 둔 것과 같은 기준이어야 한다.
    pending = sum(1 for item in candidates(conn) if item["unreported_entries"] > 0)

    return {
        "phase": phase,
        "report_date": report_date,
        "drafts": drafts,
        "done": done,
        "pending": pending,
    }
