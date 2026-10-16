"""진행일지 생성·수정·삭제."""
from __future__ import annotations

import re
import sqlite3
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import get_settings
from .. import schemas as rules
from ..vault import markdown as md
from ..vault import versions
from ..vault import paths
from ..vault.indexer import index_project
from . import trash as trash_service
from . import settings as settings_service
from .projects import normalize_tags, now_iso, project_dir

META_ORDER = ["date", "title", "author", "tags", "attachments", "created_at", "updated_at"]

# 제목을 비웠을 때의 이름 — 생성 · 수정이 같다 (TODO 205 ⑰)
DEFAULT_TITLE = "진행 기록"

_DATE_HEAD = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}-?")


def _entry_row(conn: sqlite3.Connection, entry_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM entry WHERE id = ?", (entry_id,)).fetchone()
    if row is None:
        raise KeyError(entry_id)
    return row


def entry_path(conn: sqlite3.Connection, entry_id: int) -> tuple[sqlite3.Row, Path]:
    row = _entry_row(conn, entry_id)
    directory = project_dir(conn, row["project_id"])
    return row, paths.safe_join(directory, row["rel_path"])


def create_entry(conn: sqlite3.Connection, project_id: str, data: dict[str, Any]) -> int:
    directory = project_dir(conn, project_id)
    require_project_folder(directory)
    logs_dir = directory / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    # 날짜는 엄격히, 비우면 오늘 (TODO 205) — `20260101` · `2026-W01` 같은 값이 파일명에 들어가지 않게
    entry_date = check_entry_date(data.get("date"), default=date_cls.today().isoformat())
    # 제목 100자 · 한 줄, 본문 2,000,000자 (TODO 214 D14)
    title = rules.one_line(data.get("title"), "entry_title", rules.TITLE_MAX) or DEFAULT_TITLE
    rules.check_body(data.get("body"))
    # 파일명 전체를 슬러그로 만들어 경로 구분자가 섞일 여지를 없앤다.
    stem = entry_stem(entry_date, title)
    target = paths.unique_path(logs_dir, stem, ".md")
    paths.safe_join(logs_dir, target.name)  # 최종 확인

    stamp = now_iso()
    # 작성자는 설정에 정해 둔 사용자를 쓴다. 나중에 로그인이 생기면
    # data["author"] 자리에 로그인 사용자가 들어온다.
    # 작성자 규칙(40자 · 한 줄)을 거친다 (TODO 214 F13)
    author = settings_service.current_author(rules.clean_author(data.get("author")))
    meta = {
        "date": entry_date,
        "title": title,
        "author": author or None,
        "tags": normalize_tags(conn, data.get("tags")),  # 쉼표 규칙 + 표기 맞추기 (TODO 205 · 214 D12)
        "attachments": [],
        "created_at": stamp,
        "updated_at": stamp,
    }
    md.save(target, md.MarkdownDoc(meta, data.get("body") or ""))
    index_project(conn, directory)
    conn.commit()
    row = conn.execute(
        "SELECT id FROM entry WHERE project_id = ? AND rel_path = ?",
        (project_id, target.relative_to(directory).as_posix()),
    ).fetchone()
    if row is None:  # 인덱싱이 실패했다면 조용히 넘어가지 않는다
        raise RuntimeError(f"진행일지를 인덱싱하지 못했습니다: {target.name}")
    return int(row["id"])


def check_entry_date(value: object, default: str) -> str:
    """진행일지 날짜 (TODO 214 D5) — 형식 · 2000~2100 년은 `strict_day`, 그리고 **오늘보다 뒤는 안 된다**.

    진행일지는 한 일의 기록이다. `9999-12-31` 하나가 그 과제의 "최근 갱신" 을 영영 고정해 정렬 · 묵힘이 깨졌다.
    """
    day = rules.strict_day(value, "date", default=default)
    if day > date_cls.today().isoformat():
        raise paths.InvalidDateError(f"진행일지 날짜가 오늘보다 뒤입니다 ({day}).")
    return day


def period_warnings(conn: sqlite3.Connection, project_id: str, entry_date: str | None) -> list[str]:
    """과제 기간 밖의 날짜면 알린다 — 막지는 않는다 (TODO 214 D5). 착수 전 준비 · 끝난 뒤 정리 기록도 있다.

    기간의 끝은 완료한 과제면 완료일, 아니면 마감일.
    """
    if not entry_date:
        return []
    row = conn.execute(
        "SELECT status, start_date, due_date, completed_at FROM project WHERE id = ?", (project_id,)
    ).fetchone()
    if row is None:
        return []
    start = row["start_date"]
    end = row["completed_at"] if row["status"] == "done" and row["completed_at"] else row["due_date"]
    if (start and entry_date < start) or (end and entry_date > end):
        return [f"과제 기간({start or ''}~{end or ''}) 밖의 날짜입니다."]
    return []


def require_project_folder(directory: Path) -> None:
    """과제 폴더가 아직 그 자리에 있는가 (TODO 200). 탐색기에서 옮기거나 지운 뒤 [다시 읽기] 전이면 색인에는
    있는데 폴더는 없다 — 그대로 진행하면 `logs/` 를 만들며 **유령 폴더**를 되살리고 색인은 500 이었다."""
    if not (directory / "index.md").is_file():
        raise FileNotFoundError(str(directory / "index.md"))


def entry_stem(entry_date: str, title: str) -> str:
    """파일명은 '날짜-제목' 규칙을 따른다."""
    return paths.slugify(f"{entry_date}-{title}")


def update_entry(conn: sqlite3.Connection, entry_id: int, updates: dict[str, Any]) -> None:
    row, path = entry_path(conn, entry_id)
    md.ensure_unchanged(path, row["file_mtime"])
    doc = md.load(path)
    body = updates.pop("body", None)
    if body is not None and body != doc.body:
        rules.check_body(body)  # TODO 214 D14 — 고칠 때만
    if "date" in updates:
        # 비우면 지금 날짜를 그대로 둔다 — 진행일지는 날짜 없이 있을 수 없다 (TODO 205)
        kept = str(doc.meta.get("date") or row["date"])
        raw = rules.clean_text(updates["date"])
        # 날짜를 **바꿀 때만** 미래 · 범위를 따진다 — 손으로 적어 둔 날짜 때문에 본문 저장이 막히지 않게 (TODO 214 D5)
        updates["date"] = kept if not raw or raw == kept else check_entry_date(raw, default=kept)
    if "title" in updates:
        # 비우거나 공백뿐이면 생성 때와 같은 이름 (TODO 205 ⑰). 길이 · 한 줄은 바꿀 때만 (TODO 214 D14)
        title = rules.clean_text(updates["title"])
        if title != rules.clean_text(doc.meta.get("title")):
            title = rules.one_line(title, "entry_title", rules.TITLE_MAX)
        updates["title"] = title or DEFAULT_TITLE
    if "tags" in updates:
        updates["tags"] = normalize_tags(conn, updates["tags"])  # TODO 214 D12
    meta = md.merge_meta(doc.meta, {k: v for k, v in updates.items() if k in META_ORDER})
    meta["updated_at"] = now_iso()
    md.save(path, md.MarkdownDoc(meta, body if body is not None else doc.body))

    # 제목이나 날짜가 바뀌면 파일명도 따라간다 (탐색기에서 찾기 쉽게).
    directory = project_dir(conn, row["project_id"])
    try:
        new_path = _rename_to_match_meta(conn, row, path, meta, directory)
    except (paths.FileInUseError, OSError):
        # TODO 200 — 파일은 저장됐는데 이름 바꾸기만 실패. 색인의 file_mtime 을 맞춰 두고 알린다 —
        # 아니면 다음 저장이 "도구 밖에서 수정됨" 409 로 영영 막힌다.
        index_project(conn, directory)
        conn.commit()
        raise

    index_project(conn, directory)
    conn.commit()
    return new_path


def _rename_to_match_meta(
    conn: sqlite3.Connection, row: sqlite3.Row, path: Path, meta: dict[str, Any], directory: Path
) -> Path:
    entry_date = str(meta.get("date") or row["date"])
    # **파일에 적힌 제목이 원본이다** (TODO 205 ⑰). 예전에는 제목이 비면 색인의 제목을 썼는데, 색인은 제목 없는
    # 파일에 **파일명**(날짜 포함)을 제목으로 적어 둔다 — 그래서 고칠 때마다 `2026-05-01-2026-05-01-…` 로 자랐다.
    title = rules.clean_text(meta.get("title"))
    if not title:
        # 제목 없는 손 파일 — 파일명에서 날짜 머리를 뗀 나머지를 그대로 쓴다(날짜만 바뀌었을 때)
        title = _DATE_HEAD.sub("", path.stem) or DEFAULT_TITLE
    stem = entry_stem(entry_date, title)
    if path.stem == stem:
        return path

    target = paths.unique_path(path.parent, stem, ".md")
    paths.move(path, target)
    versions.follow(path, target)  # 이전 버전도 따라온다 (TODO 142)

    old_rel = path.relative_to(directory).as_posix()
    new_rel = target.relative_to(directory).as_posix()
    # 인덱스가 '새 파일 + 사라진 파일'로 보고 id를 새로 발급하지 않도록 먼저 경로를 옮겨 둔다.
    # 그래야 화면이 잡고 있던 기록을 이름을 바꾼 뒤에도 그대로 연다.
    conn.execute("UPDATE entry SET rel_path = ? WHERE id = ?", (new_rel, row["id"]))
    _repoint_reports(conn, row["project_id"], directory, old_rel, new_rel)
    return target


def _repoint_reports(
    conn: sqlite3.Connection, project_id: str, directory: Path, old_rel: str, new_rel: str
) -> None:
    """보고 문서가 가리키는 진행일지 경로를 새 파일명으로 고쳐 준다.

    확정된 보고의 '내용'은 그대로 두고 가리키는 대상만 따라가게 한다.
    이것을 하지 않으면 이미 보고한 진행일지가 미보고로 되살아난다.
    """
    for report in conn.execute(
        "SELECT rel_path FROM report WHERE project_id = ?", (project_id,)
    ).fetchall():
        report_path = paths.safe_join(directory, report["rel_path"])
        if not report_path.exists():
            continue
        doc = md.load(report_path)
        covered = doc.meta.get("covered_entries") or []
        if old_rel not in covered:
            continue
        doc.meta["covered_entries"] = [new_rel if item == old_rel else item for item in covered]
        md.save(report_path, doc)


def delete_entry(conn: sqlite3.Connection, entry_id: int) -> None:
    row, path = entry_path(conn, entry_id)
    trash = get_settings().trash_dir
    trash.mkdir(parents=True, exist_ok=True)
    target = paths.unique_path(trash, f"{row['project_id']}-{path.stem}-{datetime.now():%Y%m%d%H%M%S}", ".md")
    paths.move(path, target)
    trash_service.record(
        "entry",
        label=f"{row['date']} {row['title'] or path.stem}",
        moved_to=target,
        origin=path,
        project_id=row["project_id"],
    )
    index_project(conn, project_dir(conn, row["project_id"]))
    conn.commit()


# ── 다음 할 일 (TODO 112) ──────────────────────────────────────────────────
#
# 진행일지 서식에 `## 계획` 이 있다. 거기 쓴 것이 다음 기록을 쓸 때까지 어디에도 안 보였다.
# 마지막 기록의 계획 절만 뽑아 과제 상세와 홈이 **표시**한다 — 체크박스도 마감도 두지
# 않는다. 할 일 관리 도구가 되려 하면 이력 도구로서도 어중간해진다.

import re as _re

_PLAN_HEAD = _re.compile(r"^\s{0,3}#{2,3}\s*(다음\s*)?(계획|할\s*일)\s*$|^\s{0,3}#{2,3}\s*다음\s*$")
_ANY_HEAD = _re.compile(r"^\s{0,3}#{1,6}\s")


def plan_section(body: str | None) -> str:
    """본문에서 `## 계획`(또는 `## 다음 계획`·`## 다음`·`## 할 일`) 아래의 글만.

    다음 제목이 나올 때까지다. 빈 줄과 서식 부호(`-`·`*`)는 정리하고, 아무것도 없으면 빈 문자열.
    """
    lines = (body or "").splitlines()
    out: list[str] = []
    taking = False
    for line in lines:
        if _PLAN_HEAD.match(line):
            taking = True
            continue
        if taking and _ANY_HEAD.match(line):
            break
        if taking:
            text = line.strip()
            if text.startswith(("- ", "* ", "• ")):
                text = text[2:].strip()
            if text and not text.startswith(">"):
                out.append(text)
    return "\n".join(out)


# 최근 몇 건까지 거슬러 올라가 계획 절을 찾는가 — 상태 변경 기록(계획이 없다)을 건너뛸 여지
PLAN_LOOKBACK = 3


def latest_plan(conn: sqlite3.Connection, project_id: str) -> dict[str, Any] | None:
    """가장 최근 진행일지의 계획 절. 없거나 비어 있으면 None.

    상태 변경 기록(도구가 남긴 한 줄)은 건너뛴다 — 거기에는 계획이 없다.
    """
    rows = conn.execute(
        "SELECT id, date, title, body FROM entry WHERE project_id = ?"
        " ORDER BY date DESC, id DESC LIMIT ?",
        (project_id, PLAN_LOOKBACK),
    ).fetchall()
    return latest_plan_from_rows(rows)


def latest_plan_from_rows(rows: list[sqlite3.Row]) -> dict[str, Any] | None:
    """`latest_plan` 의 규칙을 **이미 모아 둔 줄**(최근 것부터)에 적용한다 — 홈이 과제마다 묻지 않고 한 번에 모아 쓴다 (TODO 190)."""
    for row in rows:
        if str(row["title"] or "").startswith("(상태)"):
            continue
        text = plan_section(row["body"])
        if text:
            return {"entry_id": row["id"], "date": row["date"], "text": text}
        return None
    return None
