"""진행일지 생성·수정·삭제."""
from __future__ import annotations

import shutil
import sqlite3
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..vault import markdown as md
from ..vault import paths
from ..vault.indexer import index_project
from .projects import now_iso, project_dir

META_ORDER = ["date", "title", "tags", "attachments", "created_at", "updated_at"]


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

    entry_date = str(data.get("date") or date_cls.today().isoformat())
    title = (data.get("title") or "").strip() or "진행 기록"
    target = paths.unique_path(logs_dir, f"{entry_date}-{paths.slugify(title)}", ".md")

    stamp = now_iso()
    meta = {
        "date": entry_date,
        "title": title,
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
    return int(row["id"])


def update_entry(conn: sqlite3.Connection, entry_id: int, updates: dict[str, Any]) -> None:
    row, path = entry_path(conn, entry_id)
    doc = md.load(path)
    body = updates.pop("body", None)
    meta = md.merge_meta(doc.meta, {k: v for k, v in updates.items() if k in META_ORDER})
    meta["updated_at"] = now_iso()
    md.save(path, md.MarkdownDoc(meta, body if body is not None else doc.body))
    index_project(conn, project_dir(conn, row["project_id"]))
    conn.commit()


def delete_entry(conn: sqlite3.Connection, entry_id: int) -> None:
    row, path = entry_path(conn, entry_id)
    trash = get_settings().trash_dir
    trash.mkdir(parents=True, exist_ok=True)
    target = paths.unique_path(trash, f"{row['project_id']}-{path.stem}-{datetime.now():%Y%m%d%H%M%S}", ".md")
    shutil.move(str(path), str(target))
    index_project(conn, project_dir(conn, row["project_id"]))
    conn.commit()
