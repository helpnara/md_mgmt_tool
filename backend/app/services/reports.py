"""보고 이력.

진행 이력(계속 자라는 것)과 보고 기록(그 시점에 고정되는 것)을 분리한다.
확정된 보고 문서는 이후 진행일지가 바뀌어도 함께 바뀌지 않는다.
"""
from __future__ import annotations

import posixpath
import re
import sqlite3
from datetime import date as date_cls
from datetime import datetime, timedelta
from pathlib import Path
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


def unreported_entries(
    conn: sqlite3.Connection, project_id: str, until: str | None = None
) -> list[sqlite3.Row]:
    """확정된 보고에 아직 담기지 않은 진행일지.

    `until` 을 주면 **그 날짜까지만** 가져온다 (TODO 81). 보고 초안을 만들 때 쓴다 —
    2026-09-02 자 보고가 2026-09-05 에 쓴 기록을 담을 수는 없기 때문이다.
    미보고 '분량'을 셀 때는 날짜를 자르지 않는다. 앞으로 보고해야 할 양이 곧 그 수다.
    """
    sql = """
        SELECT e.* FROM entry e
         WHERE e.project_id = ?
           AND e.id NOT IN (
                 SELECT re.entry_id FROM report_entry re
                   JOIN report r ON r.id = re.report_id
                  WHERE r.frozen_at IS NOT NULL
               )
    """
    params: list[object] = [project_id]
    if until:
        sql += " AND e.date <= ?"
        params.append(until)
    return conn.execute(sql + " ORDER BY e.date ASC, e.id ASC", params).fetchall()


_DATE_HEAD = re.compile(r"^logs/(\d{4}-\d{2}-\d{2})")


def _entry_date(rel_path: str) -> str | None:
    """`logs/2026-09-01-제목.md` 에서 날짜만 떼어 낸다.

    모양이 다르면 `None` 을 준다. 날짜를 못 읽었다고 **기록을 버리면 안 된다** —
    거르는 쪽이 아니라 남기는 쪽으로 실패해야 보고에서 내용이 사라지지 않는다.
    """
    found = _DATE_HEAD.match(rel_path)
    return found.group(1) if found else None


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

    # 보고일 이후에 쓴 기록은 이 보고에 담지 않는다 (TODO 81).
    entries = unreported_entries(conn, project_id, until=report_date)
    # 지난 보고에서 받고 아직 답하지 않은 지시가 있으면 초안 맨 위에 딸려 들어간다 (TODO 107).
    # 답했는지는 팀장 머릿속에만 있었다 — 다음 초안이 먼저 물어보게 한다.
    pending = open_feedback(conn, project_id)
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
    md.save(folder / "report.md", md.MarkdownDoc(meta, _feedback_head(pending) + _draft_body(entries)))
    index_project(conn, directory)
    conn.commit()

    rel_path = (folder / "report.md").relative_to(directory).as_posix()
    row = conn.execute(
        "SELECT id FROM report WHERE project_id = ? AND rel_path = ?", (project_id, rel_path)
    ).fetchone()
    if row is None:
        raise RuntimeError(f"보고 문서를 인덱싱하지 못했습니다: {rel_path}")
    return int(row["id"])


def open_feedback(conn: sqlite3.Connection, project_id: str) -> list[sqlite3.Row]:
    """이 과제의 확정된 보고 중 **지시를 받았는데 아직 답하지 않은** 것. 오래된 것 먼저."""
    return conn.execute(
        "SELECT id, report_date, audience, feedback FROM report"
        " WHERE project_id = ? AND frozen_at IS NOT NULL"
        "   AND feedback IS NOT NULL AND TRIM(feedback) <> ''"
        "   AND (feedback_done IS NULL OR feedback_done = '')"
        " ORDER BY report_date, id",
        (project_id,),
    ).fetchall()


def _feedback_head(pending: list[sqlite3.Row]) -> str:
    """초안 맨 위에 붙는 '지난 보고 지시사항' 절. 없으면 빈 문자열."""
    if not pending:
        return ""
    lines = ["## 지난 보고 지시사항", ""]
    for row in pending:
        head = f"{row['report_date']}" + (f" · {row['audience']}" if row["audience"] else "")
        lines.append(f"- **{head}** — {str(row['feedback']).strip()}")
    lines += ["", "> 위 지시에 답한 뒤 그 보고의 [답변함] 을 눌러 두세요. 다음 초안에 다시 나오지 않습니다.", ""]
    return "\n".join(lines) + "\n"


def mark_feedback_done(conn: sqlite3.Connection, report_id: int, done: bool) -> None:
    """지시에 답했다 / 아직이다. 답한 날을 남긴다 — 언제 닫았는지도 사실이다."""
    update_report(conn, report_id, {"feedback_done": date_cls.today().isoformat() if done else None})


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
# 지시사항(feedback)은 **확정된 보고에서 유일하게 쓸 수 있는 본문**이다 (TODO 107).
# 보고를 하고 나면 지시나 질문이 돌아오는데, 그것을 적을 자리가 잠긴 문서 안에는 없었다.
EDITABLE_WHEN_FROZEN = {"audience", "title", "report_type", "feedback", "feedback_done"}
META_FIELDS = {"title", "report_type", "audience", "report_date", "feedback", "feedback_done"}


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
    entries = unreported_entries(conn, row["project_id"], until=row["report_date"])
    covered = doc.meta.get("covered_entries") or [entry["rel_path"] for entry in entries]
    # 초안을 만든 뒤 보고일을 앞당겼다면 그 뒤 기록이 남아 있을 수 있다 (TODO 81).
    covered = [
        rel
        for rel in covered
        if (_entry_date(rel) or row["report_date"]) <= row["report_date"]
    ]

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
    4. **착수일이 아직 오지 않은 과제는 맨 뒤.** 시작도 안 한 과제는 이번 주 보고 후보가 아니다.

    **별도 보고가 필요 없다고 표시한 과제는 아예 빠진다** (TODO 80). 단순 현황 관리를
    과제로 세운 경우가 있고, 그런 과제를 매주 눈으로 걸러 내는 것이 실제 부담이었다.
    빼는 것은 **후보 목록에서뿐**이다 — 손으로 보고를 남기는 길은 그대로 열려 있다.

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
        # 보고가 필요 없다고 정해 둔 과제. 상태와 무관하게 후보에서 뺀다.
        if project["no_report"]:
            continue
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
        # 착수일이 아직 오지 않으면 경과일이 음수가 된다. 숫자를 그대로 내보내면
        # 화면에 `D+-27` 처럼 읽히지 않는 값이 뜨므로, 아직 시작 안 했다는 사실을
        # 따로 알려 주고 화면이 말로 표현하게 한다 (TODO 70).
        not_started = days_since is not None and days_since < 0

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
                "not_started": not_started,
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
    """기본 순서 — 보고 이력 없음 먼저, 그다음 마지막 보고가 오래된 것부터.

    착수 전 과제는 보고 이력이 없더라도 맨 뒤에 둔다. 시작하지 않은 과제가
    "가장 오래 방치된 과제" 자리를 차지하면 목록의 뜻이 흐려진다 (TODO 70).
    """
    return (
        2 if item.get("not_started") else (0 if item["never_reported"] else 1),
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
    feedback: str | None = None,
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
    if feedback == "open":
        # 지시를 받았는데 아직 답하지 않은 보고만 (TODO 107).
        where.append("r.frozen_at IS NOT NULL AND r.feedback IS NOT NULL AND TRIM(r.feedback) <> ''"
                     " AND (r.feedback_done IS NULL OR r.feedback_done = '')")
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


# 한 줄 발췌에서 걸러 낼 것들. 서식 기호는 화면에서 뜻을 잃고 자리만 차지한다 (TODO 87).
_SKIP_LINE = re.compile(r"^\s*(#{1,6}\s|-{3,}\s*$|\|)")
_INLINE_MARK = re.compile(r"[*_`>]+")


def readable_text(body: str | None) -> str:
    """발췌용 한 줄 — 제목·표·구분선·서식 기호를 뺀 본문 (TODO 87 · 103-C).

    보고 이력의 발췌와 통합 검색의 발췌가 **같은 것**을 써야 한다. 87 에서 보고 이력만
    고치고 검색은 두었더니, 검색 결과에 `## 배경 >` 같은 기호가 그대로 남았다.
    """
    return " ".join(_readable_lines(body))


def _readable_lines(body: str | None) -> list[str]:
    """발췌용으로 읽을 만한 줄만 남긴다 — 제목·표·구분선을 뺀 본문."""
    out = []
    for line in (body or "").splitlines():
        if _SKIP_LINE.match(line):
            continue
        text = _INLINE_MARK.sub("", line).strip()
        text = text.lstrip("-•").strip() if text.startswith(("- ", "* ", "• ")) else text
        if text:
            out.append(text)
    return out


def _excerpt(body: str | None, query: str | None, width: int = 60) -> str:
    """검색어 둘레를 잘라 낸다. 검색어가 없으면 첫 줄 몇 글자.

    마크다운 제목(`## 보고 요약`)은 빼고 읽는다 — 어느 보고에나 똑같이 들어 있어
    한 줄 발췌에서는 서로를 구별해 주지 못한다.
    """
    text = readable_text(body)
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
    # 개수는 **자르기 전** 수여야 한다. 목록만 잘라 놓고 그 길이를 건수로 쓰면
    # "초안 10건" 이라 적고 실제로는 15건인 일이 생긴다 (TODO 82 에서 같은 것을 고쳤다).
    drafts = conn.execute(
        "SELECT COUNT(*) AS n FROM report WHERE report_date = ? AND frozen_at IS NULL",
        (report_date,),
    ).fetchone()["n"]
    items = open_drafts(conn, report_date)
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
        # **개수만으로는 갈 곳을 만들 수 없다** (TODO 91). 배너가 "초안 1건이 확정을
        # 기다립니다" 라고 적어 놓고 후보 목록으로 보내면, 방금 이름까지 들은 그 한 건을
        # 사용자가 다시 찾아야 한다. 어디로 가야 하는지를 함께 준다.
        "draft_items": items,
        "done": done,
        "pending": pending,
    }


# 배너에 이름을 세우는 것은 몇 건까지인가 — 그 위는 목록 화면이 맡는다.
DRAFT_LIST_LIMIT = 10


def open_drafts(conn: sqlite3.Connection, report_date: str) -> list[dict]:
    """그 날짜의 **아직 확정되지 않은** 보고. 화면이 그리로 곧장 갈 수 있게 이름까지 준다.

    앞의 몇 건만 준다 — 이름을 세우는 것은 몇 건까지고, 그 위는 목록 화면이 맡는다.
    **건수를 말할 때 이 길이를 세면 안 된다.** 자르기 전 수를 따로 센다.
    """
    return [
        {
            "id": row["id"],
            "project_id": row["project_id"],
            "project_title": row["project_title"],
            "audience": row["audience"],
        }
        for row in conn.execute(
            "SELECT r.id, r.project_id, r.audience, p.title AS project_title"
            "  FROM report r JOIN project p ON p.id = r.project_id"
            " WHERE r.report_date = ? AND r.frozen_at IS NULL"
            " ORDER BY p.title, r.id LIMIT ?",
            (report_date, DRAFT_LIST_LIMIT),
        )
    ]


# 홈에 이름을 세우는 초안은 몇 건까지인가. 그 위는 보고 대상 화면이 맡는다.
UNFINISHED_LIST_LIMIT = 6
# 보고 대상 화면의 확정 대기 카드는 목록 화면이라 넉넉히 세운다.
WAITING_LIST_LIMIT = 100


def unfinished_drafts(conn: sqlite3.Connection, limit: int = UNFINISHED_LIST_LIMIT) -> dict:
    """**아직 확정하지 않은 보고 전부** — 날짜를 가리지 않는다 (TODO 101).

    `open_drafts` 와 다른 점은 *그 날짜*가 아니라 *모든 날짜*를 본다는 것이다.
    쓰다 만 초안은 보고일이 지나도 사라지지 않고 조용히 쌓인다. 배너(TODO 91)는
    **보고하는 날에만** 뜨므로, 지난주에 쓰다 만 것은 그 다음 보고일까지 아무 데도
    보이지 않았다. 홈의 [이번 주 할 일]이 그것을 계속 들고 있게 한다.

    보고일이 **이미 지난** 초안을 앞에 세운다 — 그것이 진짜 밀린 것이다.
    건수는 자르기 전 수를 따로 센다 (TODO 82 에서 같은 것을 고쳤다).
    """
    today = date_cls.today().isoformat()
    total = conn.execute(
        "SELECT COUNT(*) AS n FROM report WHERE frozen_at IS NULL"
    ).fetchone()["n"]
    overdue = conn.execute(
        "SELECT COUNT(*) AS n FROM report WHERE frozen_at IS NULL AND report_date < ?",
        (today,),
    ).fetchone()["n"]
    items = [
        {
            "id": row["id"],
            "project_id": row["project_id"],
            "project_title": row["project_title"],
            "audience": row["audience"],
            "report_date": row["report_date"],
            # 보고일이 지났는데 아직 확정하지 않았다 — 며칠이나 지났는지 함께 준다.
            "overdue_days": max(0, (date_cls.today() - _date(row["report_date"])).days)
            if row["report_date"] < today
            else 0,
        }
        for row in conn.execute(
            "SELECT r.id, r.project_id, r.report_date, r.audience, p.title AS project_title"
            "  FROM report r JOIN project p ON p.id = r.project_id"
            " WHERE r.frozen_at IS NULL"
            " ORDER BY r.report_date ASC, p.title, r.id LIMIT ?",
            (limit,),
        )
    ]
    return {"total": total, "overdue": overdue, "items": items}


def _date(text: str) -> date_cls:
    """`YYYY-MM-DD` → 날짜. 손으로 고친 파일에 이상한 값이 있어도 화면을 멈추지 않는다."""
    try:
        return date_cls.fromisoformat(text)
    except (TypeError, ValueError):
        return date_cls.today()


def month_grid(conn: sqlite3.Connection, year: str | None) -> dict:
    """과제 × 월 표의 재료 (TODO 77 · 79).

    **화면 모양은 서버가 모른다.** 과제 목록과 보고 목록만 주고, 열두 칸으로 나누는 일은
    화면이 한다. 그래야 "한 달에 두 건이면 어떻게 보일지" 를 고칠 때 서버를 안 건드린다.

    **어떤 과제가 줄이 되는가 — 합집합이다.**

        줄 = (그 해 번호의 과제) ∪ (그 해에 보고가 있었던 과제)

    홈은 연도 기준을 둘 쓴다 (과제는 번호의 연도, 보고는 보고한 날의 연도).
    이 표가 그 둘이 만나는 자리다. 지난해 번호인데 올해 보고한 과제를 빼면
    **표의 합이 위쪽 "보고 횟수" 와 어긋나고**, 올해 번호인데 아직 한 번도 보고 안 한
    과제를 빼면 **비어 있다는 사실이 사라진다.** 둘 다 보여야 한다.

    확정된 보고만 담는다 — 초안은 아직 보고한 것이 아니다.

    **보고가 필요 없다고 표시한 과제는 줄에서 뺀다** (TODO 80). 빈 줄로 세우면
    "관리 공백" 처럼 읽히는데, 그 과제는 원래 보고하지 않기로 한 것이라 뜻이 어긋난다.
    화면이 몇 건을 뺐는지 밝힐 수 있게 `skipped` 로 함께 알려 준다.

    **홈이 아니라 보고 이력 화면의 것이다** (TODO 79). 과제가 늘면 줄이 그만큼 늘어
    홈의 "한눈에" 성격과 어긋난다 — 50명 팀이면 과제가 수백 건이다.
    """
    if not year:
        return {"projects": [], "reports": [], "skipped": 0}

    reports = [
        {
            "id": row["id"],
            "project_id": row["project_id"],
            "date": row["report_date"],
            "audience": row["audience"],
        }
        for row in conn.execute(
            "SELECT id, project_id, report_date, audience FROM report"
            " WHERE frozen_at IS NOT NULL AND SUBSTR(report_date, 1, 4) = ?"
            " ORDER BY report_date, id",
            (year,),
        )
    ]

    reported = {item["project_id"] for item in reports}
    clause = " AND SUBSTR(p.id, 1, 4) = ?"
    params = [year]
    projects = [
        {"id": row["id"], "title": row["title"], "status": row["status"]}
        for row in conn.execute(
            f"SELECT id, title, status FROM project p WHERE no_report = 0{clause} ORDER BY p.id",
            params,
        )
    ]
    skipped = conn.execute(
        f"SELECT COUNT(*) AS n FROM project p WHERE no_report = 1{clause}", params
    ).fetchone()["n"]
    known = {item["id"] for item in projects}
    # 그 해 번호가 아닌데 그 해에 보고한 과제 — 번호가 다르므로 화면에서 바로 구분된다.
    outside = [item for item in reported if item not in known]
    if outside:
        placeholders = ",".join("?" * len(outside))
        projects.extend(
            {"id": row["id"], "title": row["title"], "status": row["status"]}
            for row in conn.execute(
                f"SELECT id, title, status FROM project"
                f" WHERE id IN ({placeholders}) AND no_report = 0 ORDER BY id",
                tuple(outside),
            )
        )
    return {"projects": projects, "reports": reports, "skipped": skipped}
