"""진행일지 생성·수정·삭제."""
from __future__ import annotations

import sqlite3
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..vault import markdown as md
from ..vault import paths
from ..vault.indexer import index_project
from . import settings as settings_service
from .projects import now_iso, project_dir

META_ORDER = ["date", "title", "author", "tags", "attachments", "created_at", "updated_at"]


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
    logs_dir = directory / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    entry_date = paths.validate_date(data.get("date"))
    title = (data.get("title") or "").strip() or "진행 기록"
    # 파일명 전체를 슬러그로 만들어 경로 구분자가 섞일 여지를 없앤다.
    stem = entry_stem(entry_date, title)
    target = paths.unique_path(logs_dir, stem, ".md")
    paths.safe_join(logs_dir, target.name)  # 최종 확인

    stamp = now_iso()
    # 작성자는 설정에 정해 둔 사용자를 쓴다. 나중에 로그인이 생기면
    # data["author"] 자리에 로그인 사용자가 들어온다.
    author = settings_service.current_author(data.get("author"))
    meta = {
        "date": entry_date,
        "title": title,
        "author": author or None,
        "tags": data.get("tags") or [],
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


def entry_stem(entry_date: str, title: str) -> str:
    """파일명은 '날짜-제목' 규칙을 따른다."""
    return paths.slugify(f"{entry_date}-{title}")


def update_entry(conn: sqlite3.Connection, entry_id: int, updates: dict[str, Any]) -> None:
    row, path = entry_path(conn, entry_id)
    md.ensure_unchanged(path, row["file_mtime"])
    doc = md.load(path)
    body = updates.pop("body", None)
    if updates.get("date"):
        updates["date"] = paths.validate_date(updates["date"])
    meta = md.merge_meta(doc.meta, {k: v for k, v in updates.items() if k in META_ORDER})
    meta["updated_at"] = now_iso()
    md.save(path, md.MarkdownDoc(meta, body if body is not None else doc.body))

    # 제목이나 날짜가 바뀌면 파일명도 따라간다 (탐색기에서 찾기 쉽게).
    directory = project_dir(conn, row["project_id"])
    new_path = _rename_to_match_meta(conn, row, path, meta, directory)

    index_project(conn, directory)
    conn.commit()
    return new_path


def _rename_to_match_meta(
    conn: sqlite3.Connection, row: sqlite3.Row, path: Path, meta: dict[str, Any], directory: Path
) -> Path:
    entry_date = str(meta.get("date") or row["date"])
    title = str(meta.get("title") or row["title"])
    stem = entry_stem(entry_date, title)
    if path.stem == stem:
        return path

    target = paths.unique_path(path.parent, stem, ".md")
    paths.move(path, target)

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
    index_project(conn, project_dir(conn, row["project_id"]))
    conn.commit()
