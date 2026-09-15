"""이미 쌓인 문서의 깨진 첨부 링크 고치기 (TODO 116).

114 에서 새로 넣는 링크는 `<…>` 로 감싸게 됐지만, 그 전에 들어간
`![이름](../assets/…/001-측정 결과.png)` 은 그대로 남아 있다. 설정의 [점검]에서
**먼저 세어 보고**, 그다음 한 번에 고친다.

무엇을 고치나 — 목적지가 **그 과제의 실제 첨부 경로와 정확히 같은** 링크만.
본문을 마크다운으로 해석해서 "공백이 있으면 감싼다" 식으로 가면 사람이 쓴 글 속의
괄호까지 건드린다. 알고 있는 파일 이름을 그대로 찾아 바꾸는 것이 안전하다.

확정된 보고는 기본으로 건드리지 않는다 — 그 문서는 "그때 무엇을 보고했는가"다.
사용자가 포함하겠다고 하면 고친다. 어느 쪽이든 저장 전 내용은 이전 버전으로 남는다.
"""
from __future__ import annotations

import posixpath
import sqlite3
from pathlib import Path
from typing import Any

from ..vault import markdown as md
from ..vault.indexer import index_project
from .attachments import ENTRY_DOC_DIR, link_target
from .projects import project_dir


def _needs_wrap(link: str) -> bool:
    return link_target(link) != link


def fix_body(body: str, doc_dir: str, rel_paths: list[str]) -> tuple[str, int]:
    """감싸야 할 첨부 링크를 감싼다. (고친 본문, 바꾼 링크 수)"""
    fixed = body or ""
    count = 0
    for rel_path in rel_paths:
        link = posixpath.relpath(rel_path, doc_dir) if doc_dir else rel_path
        if not _needs_wrap(link):
            continue
        broken = f"]({link})"
        if broken in fixed:
            count += fixed.count(broken)
            fixed = fixed.replace(broken, f"]({link_target(link)})")
    return fixed, count


def _documents(conn: sqlite3.Connection, project_id: str) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = [{"kind": "overview", "rel_path": "index.md", "doc_dir": "", "frozen": False}]
    for row in conn.execute("SELECT rel_path FROM entry WHERE project_id = ? ORDER BY date", (project_id,)):
        docs.append({"kind": "entry", "rel_path": row["rel_path"], "doc_dir": ENTRY_DOC_DIR, "frozen": False})
    for row in conn.execute(
        "SELECT rel_path, frozen_at FROM report WHERE project_id = ? ORDER BY report_date", (project_id,)
    ):
        docs.append({
            "kind": "report",
            "rel_path": row["rel_path"],
            "doc_dir": posixpath.dirname(row["rel_path"]),
            "frozen": bool(row["frozen_at"]),
        })
    return docs


def run(conn: sqlite3.Connection, *, apply: bool, include_frozen: bool) -> dict[str, Any]:
    """apply=False 면 세기만 한다. True 면 고치고 색인을 다시 만든다."""
    changed: list[dict[str, Any]] = []
    skipped_frozen = 0
    total_links = 0
    touched_dirs: list[Path] = []

    for project in conn.execute("SELECT id, title FROM project ORDER BY id").fetchall():
        rel_paths = [
            row["rel_path"]
            for row in conn.execute("SELECT rel_path FROM attachment WHERE project_id = ?", (project["id"],))
        ]
        if not any(_needs_wrap(p) for p in rel_paths):
            continue
        directory = project_dir(conn, project["id"])
        project_touched = False
        for doc_info in _documents(conn, project["id"]):
            path = directory / doc_info["rel_path"]
            if not path.is_file():
                continue
            try:
                doc = md.load(path)
            except Exception:
                continue  # 읽지 못하는 파일은 색인 문제 목록이 따로 알린다
            fixed, count = fix_body(doc.body, doc_info["doc_dir"], rel_paths)
            if count == 0:
                continue
            if doc_info["frozen"] and not include_frozen:
                skipped_frozen += 1
                continue
            total_links += count
            changed.append({
                "project_id": project["id"],
                "project_title": project["title"],
                "kind": doc_info["kind"],
                "rel_path": doc_info["rel_path"],
                "links": count,
                "frozen": doc_info["frozen"],
            })
            if apply:
                md.save(path, md.MarkdownDoc(doc.meta, fixed))
                project_touched = True
        if project_touched:
            touched_dirs.append(directory)

    if apply:
        for directory in touched_dirs:
            index_project(conn, directory)
        conn.commit()

    return {
        "applied": apply,
        "documents": changed,
        "document_count": len(changed),
        "link_count": total_links,
        "skipped_frozen": skipped_frozen,
    }
