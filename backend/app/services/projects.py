"""과제 생성·수정. 파일을 먼저 쓰고 인덱스를 갱신한다."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import DEFAULT_STATUS, STATUS_KEYS, get_settings
from ..vault import markdown as md
from ..vault import paths
from ..vault.indexer import index_project

# 카드 제목이 "과제 개요"이므로 본문은 같은 제목을 반복하지 않는다.
INDEX_TEMPLATE = """## 배경

## 목표

## 산출물

## 관련 링크
"""

META_ORDER = [
    "id", "title", "status", "group", "tags", "owners",
    "start_date", "due_date", "created_at", "updated_at",
]


def normalize_owners(value: object) -> list[str]:
    """담당자는 한 명일 수도, 여러 명일 수도 있다. 쉼표로 적어도 받아 준다."""
    if not value:
        return []
    items = [value] if isinstance(value, str) else [str(item) for item in value]
    # 한 칸에 "권경락, 홍길동" 처럼 적어 보내도 나눠 받는다.
    raw = [part for item in items for part in item.split(",")]
    seen: list[str] = []
    for name in (item.strip() for item in raw):
        if name and name not in seen:
            seen.append(name)
    return seen


def now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def next_project_id(year: int | None = None) -> str:
    settings = get_settings()
    settings.ensure_dirs()
    year = year or datetime.now().year
    prefix = f"{year}-"
    used = 0
    for child in settings.projects_dir.iterdir():
        if child.is_dir() and child.name.startswith(prefix):
            seq = child.name[len(prefix):].split("-")[0]
            if seq.isdigit():
                used = max(used, int(seq))
    return f"{year}-{used + 1:03d}"


def project_dir(conn: sqlite3.Connection, project_id: str) -> Path:
    row = conn.execute("SELECT dir_name FROM project WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise KeyError(project_id)
    return paths.safe_join(get_settings().projects_dir, row["dir_name"])


def create_project(conn: sqlite3.Connection, data: dict[str, Any]) -> str:
    settings = get_settings()
    settings.ensure_dirs()
    title = (data.get("title") or "").strip()
    if not title:
        raise ValueError("과제명을 입력하세요.")

    status = data.get("status") or DEFAULT_STATUS
    if status not in STATUS_KEYS:
        raise ValueError(f"알 수 없는 상태: {status}")

    project_id = next_project_id()
    dir_name = paths.project_dir_name(project_id, title)
    directory = paths.safe_join(settings.projects_dir, dir_name)
    (directory / "logs").mkdir(parents=True, exist_ok=True)
    (directory / "assets").mkdir(parents=True, exist_ok=True)
    (directory / "reports").mkdir(parents=True, exist_ok=True)

    stamp = now_iso()
    meta = {
        "id": project_id,
        "title": title,
        "status": status,
        "group": data.get("group") or None,
        "tags": data.get("tags") or [],
        "owners": normalize_owners(data.get("owners") or data.get("owner")),
        "start_date": data.get("start_date") or None,
        "due_date": data.get("due_date") or None,
        "created_at": stamp,
        "updated_at": stamp,
    }
    md.save(directory / "index.md", md.MarkdownDoc(meta, data.get("body") or INDEX_TEMPLATE))
    index_project(conn, directory)
    conn.commit()
    return project_id


def update_project(conn: sqlite3.Connection, project_id: str, updates: dict[str, Any]) -> None:
    directory = project_dir(conn, project_id)
    index_md = directory / "index.md"
    known = conn.execute("SELECT file_mtime FROM project WHERE id = ?", (project_id,)).fetchone()
    md.ensure_unchanged(index_md, known["file_mtime"] if known else None)
    doc = md.load(index_md)

    if "status" in updates and updates["status"] not in STATUS_KEYS:
        raise ValueError(f"알 수 없는 상태: {updates['status']}")

    body = updates.pop("body", None)
    if "owners" in updates or "owner" in updates:
        updates["owners"] = normalize_owners(updates.pop("owners", None) or updates.pop("owner", None))
    changes = {k: v for k, v in updates.items() if k in META_ORDER or k == "group"}
    # 예전 문서의 owner(단수) 키가 남아 있으면 owners로 옮겨 적는다.
    if "owners" in changes and "owner" in doc.meta:
        doc.meta.pop("owner")
    meta = md.merge_meta(doc.meta, changes)
    meta["updated_at"] = now_iso()
    md.save(index_md, md.MarkdownDoc(meta, body if body is not None else doc.body))

    new_title = meta.get("title")
    if new_title:
        expected = paths.project_dir_name(project_id, str(new_title))
        if expected != directory.name:
            target = paths.safe_join(get_settings().projects_dir, expected)
            if target.exists():  # 남아 있던 폴더와 겹치면 뒤에 번호를 붙인다
                target = paths.unique_path(get_settings().projects_dir, expected, "")
            paths.move(directory, target)
            directory = target

    index_project(conn, directory)
    conn.commit()


def archive_project(conn: sqlite3.Connection, project_id: str) -> None:
    """삭제하지 않고 .trash/ 로 옮긴다."""
    settings = get_settings()
    directory = project_dir(conn, project_id)
    settings.trash_dir.mkdir(parents=True, exist_ok=True)
    target = paths.unique_path(settings.trash_dir, f"{directory.name}-{datetime.now():%Y%m%d%H%M%S}", "")
    paths.move(directory, target)
    conn.execute("DELETE FROM project WHERE id = ?", (project_id,))
    conn.execute("DELETE FROM search_fts WHERE project_id = ?", (project_id,))
    conn.commit()
