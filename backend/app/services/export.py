"""과제 이력 내보내기.

보고 직전에 "이 과제가 지금까지 뭘 했는지"를 한 덩어리로 받아 가는 용도다.
"""
from __future__ import annotations

import base64
import io
import mimetypes
import posixpath
import re
import sqlite3
import zipfile
from pathlib import Path

from ..config import STATUS_LABELS
from .attachments import ENTRY_DOC_DIR, PROJECT_DOC_DIR, resolve_link
from .projects import project_dir
from .reports import report_doc_dir

LINK_PATTERN = re.compile(r"(!?)\[([^\]]*)\]\(\s*([^)\s]+)\s*\)")
INLINE_LIMIT = 5 * 1024 * 1024  # 이보다 큰 이미지는 인라인하지 않는다 (파일이 감당 못 하게 커진다)


def _project_row(conn: sqlite3.Connection, project_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM project WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise KeyError(project_id)
    return row


def _tags(conn: sqlite3.Connection, project_id: str) -> list[str]:
    return [
        row["name"]
        for row in conn.execute(
            "SELECT t.name FROM tag t JOIN project_tag pt ON pt.tag_id = t.id"
            " WHERE pt.project_id = ? ORDER BY t.name",
            (project_id,),
        )
    ]


def _report_label(report: sqlite3.Row) -> str:
    """제목이 '2026-09-08 보고'처럼 날짜로 시작하면 날짜를 겹쳐 쓰지 않는다."""
    title = report["title"] or ""
    prefix = f"{report['report_date']} "
    return title[len(prefix):] if title.startswith(prefix) else title


def _report_files(conn: sqlite3.Connection, report_id: int) -> list[str]:
    return [
        row["orig_name"]
        for row in conn.execute(
            "SELECT orig_name FROM attachment WHERE report_id = ? ORDER BY rel_path", (report_id,)
        )
    ]


def _rewrite_links(body: str, doc_dir: str, mode: str, directory: Path, dir_name: str) -> str:
    """문서마다 다른 상대 링크를, 병합 문서 하나에서도 통하도록 바꾼다."""

    def replace(match: re.Match[str]) -> str:
        bang, text, link = match.groups()
        target = resolve_link(link, doc_dir)
        if target is None:
            return match.group(0)  # 외부 링크는 그대로 둔다

        if mode == "zip":
            return f"{bang}[{text}]({target})"
        if mode == "link":
            return f"{bang}[{text}](/files/{dir_name}/{target})"

        # inline: 이미지는 data URI로 심고, 나머지 파일은 이름만 남긴다.
        path = directory / target
        mime = mimetypes.guess_type(target)[0] or ""
        if bang and path.is_file() and path.stat().st_size <= INLINE_LIMIT and mime.startswith("image/"):
            data = base64.b64encode(path.read_bytes()).decode()
            return f"![{text}](data:{mime};base64,{data})"
        return f"[{text} (첨부 파일: {posixpath.basename(target)})]()"

    return LINK_PATTERN.sub(replace, body or "")


def merged_markdown(
    conn: sqlite3.Connection, project_id: str, mode: str = "zip", include_reports_full: bool = False
) -> tuple[str, str, list[str]]:
    """(파일명, 본문, 참조한 첨부 경로 목록)."""
    project = _project_row(conn, project_id)
    directory = project_dir(conn, project_id)
    dir_name = project["dir_name"]

    used: list[str] = []

    def convert(body: str, doc_dir: str) -> str:
        for match in LINK_PATTERN.finditer(body or ""):
            target = resolve_link(match.group(3), doc_dir)
            if target:
                used.append(target)
        return _rewrite_links(body, doc_dir, mode, directory, dir_name)

    tags = _tags(conn, project_id)
    header = [
        f"# {project['title']}",
        "",
        "> "
        + " · ".join(
            filter(
                None,
                [
                    f"상태: {STATUS_LABELS.get(project['status'], project['status'])}",
                    f"기간: {project['start_date'] or '—'} ~ {project['due_date'] or '—'}",
                    f"그룹: {project['grp']}" if project["grp"] else None,
                    f"태그: {', '.join(tags)}" if tags else None,
                    f"담당: {project['owner']}" if project["owner"] else None,
                ],
            )
        ),
        "",
        "## 과제 개요",
        "",
        convert(project["body"] or "", PROJECT_DOC_DIR).strip(),
        "",
        "---",
        "",
        "# 수행 이력",
        "",
    ]

    for entry in conn.execute(
        "SELECT * FROM entry WHERE project_id = ? ORDER BY date ASC, id ASC", (project_id,)
    ):
        header += [f"## {entry['date']} {entry['title']}", "", convert(entry["body"] or "", ENTRY_DOC_DIR).strip(), ""]

    reports = conn.execute(
        "SELECT * FROM report WHERE project_id = ? ORDER BY report_date ASC", (project_id,)
    ).fetchall()
    if reports:
        header += ["---", "", "# 보고 이력", ""]
        for report in reports:
            state = "확정" if report["frozen_at"] else "작성 중"
            summary = (report["body"] or "").strip().splitlines()
            first_line = next((line for line in summary if line.strip() and not line.startswith("#")), "")
            files = _report_files(conn, report["id"])
            note = f" · 보고 자료: {', '.join(files)}" if files else ""
            header += [
                f"- **{report['report_date']}** {_report_label(report)} ({state}) — "
                f"{first_line.lstrip('- ').strip()}{note}"
            ]
        header += [""]

        if include_reports_full:
            for report in reports:
                header += [
                    f"## [보고] {report['report_date']} {_report_label(report)}",
                    "",
                    convert(report["body"] or "", report_doc_dir(report["rel_path"])).strip(),
                    "",
                ]

    filename = f"{dir_name}.md"
    return filename, "\n".join(header).rstrip() + "\n", sorted(set(used))


def export_zip(conn: sqlite3.Connection, project_id: str, include_reports_full: bool = False) -> tuple[str, bytes]:
    """병합 md + 참조된 첨부 폴더. 압축을 풀면 링크가 그대로 살아 있다."""
    directory = project_dir(conn, project_id)
    filename, text, used = merged_markdown(conn, project_id, "zip", include_reports_full)

    # 본문에서 참조한 첨부 + 보고에 사용한 자료(그때 그 엑셀)를 함께 담는다.
    report_files = [
        row["rel_path"]
        for row in conn.execute(
            "SELECT rel_path FROM attachment WHERE project_id = ? AND report_id IS NOT NULL",
            (project_id,),
        )
    ]

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(filename, text)
        for rel_path in sorted(set(used) | set(report_files)):
            path = directory / rel_path
            if path.is_file():
                archive.write(path, rel_path)
    return f"{filename[:-3]}.zip", buffer.getvalue()


def backup_zip(conn: sqlite3.Connection, project_id: str) -> tuple[str, bytes]:
    """원본 폴더 구조 그대로. 다른 도구로 옮겨 갈 때 쓴다."""
    directory = project_dir(conn, project_id)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(directory).as_posix())
    return f"{directory.name}-백업.zip", buffer.getvalue()


HTML_TEMPLATE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>{title}</title>
<style>
 body {{ font-family: "Malgun Gothic", "Apple SD Gothic Neo", system-ui, sans-serif;
        max-width: 900px; margin: 40px auto; padding: 0 20px; line-height: 1.7; color: #1c2024; }}
 h1 {{ border-bottom: 2px solid #e3e6ea; padding-bottom: 8px; }}
 h2 {{ margin-top: 32px; }}
 blockquote {{ color: #6b7280; border-left: 3px solid #e3e6ea; margin: 0; padding-left: 12px; }}
 table {{ border-collapse: collapse; }} th, td {{ border: 1px solid #e3e6ea; padding: 6px 10px; }}
 img {{ max-width: 100%; }} code {{ background: #f1f3f5; padding: 1px 5px; border-radius: 4px; }}
</style></head><body>
{body}
</body></html>
"""


def export_html(conn: sqlite3.Connection, project_id: str, include_reports_full: bool = False) -> tuple[str, str]:
    """이미지까지 담긴 단일 HTML. 메일로 보내거나 인쇄하기 좋다."""
    from markdown_it import MarkdownIt

    filename, text, _ = merged_markdown(conn, project_id, "inline", include_reports_full)
    renderer = MarkdownIt("commonmark", {"breaks": True, "linkify": True}).enable("table")
    project = _project_row(conn, project_id)
    return f"{filename[:-3]}.html", HTML_TEMPLATE.format(
        title=project["title"], body=renderer.render(text)
    )
