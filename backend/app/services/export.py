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
from typing import BinaryIO

from ..config import CLASSIFICATION_KEYS, CLASSIFICATION_LABELS, STATUS_LABELS
from . import settings as settings_service
from .attachments import ENTRY_DOC_DIR, PROJECT_DOC_DIR, resolve_link, link_target
from .projects import project_dir
from .reports import report_doc_dir

# 목적지가 `<…>` 로 감싸인 링크(공백 있는 파일 이름)도 잡는다 (TODO 114).
LINK_PATTERN = re.compile(r"(!?)\[([^\]]*)\]\(\s*(?:<([^>\n]*)>|([^)\s]+))\s*\)")
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
        bang, text, angled, plain = match.groups()
        link = angled if angled is not None else plain
        target = resolve_link(link, doc_dir)
        if target is None:
            return match.group(0)  # 외부 링크는 그대로 둔다

        if mode == "zip":
            return f"{bang}[{text}]({link_target(target)})"
        if mode == "link":
            return f"{bang}[{text}]({link_target(f'/files/{dir_name}/{target}')})"

        # inline: 이미지는 data URI로 심고, 나머지 파일은 이름만 남긴다.
        path = directory / target
        mime = mimetypes.guess_type(target)[0] or ""
        if bang and path.is_file() and path.stat().st_size <= INLINE_LIMIT and mime.startswith("image/"):
            data = base64.b64encode(path.read_bytes()).decode()
            return f"![{text}](data:{mime};base64,{data})"
        return f"[{text} (첨부 파일: {posixpath.basename(target)})]()"

    return LINK_PATTERN.sub(replace, body or "")


_FENCE = re.compile(r"^\s*(```|~~~)")
_HEADING = re.compile(r"^(#{1,5})(\s)")


def demote_headings(text: str) -> str:
    """본문의 제목을 한 단계 내린다 (TODO 241) — `## 과제 개요` 아래의 개요 `## 배경` 이 같은 단계라 문서 차례가 납작했다.

    코드 블록 안은 건드리지 않는다. `######` 는 더 내릴 수 없어 그대로.
    """
    out, fenced = [], False
    for line in text.split("\n"):
        if _FENCE.match(line):
            fenced = not fenced
        elif not fenced:
            line = _HEADING.sub(lambda m: "#" + m.group(1) + m.group(2), line)
        out.append(line)
    return "\n".join(out)


def _number(value: float | None) -> str | None:
    return None if value is None else f"{value:,.2f}".rstrip("0").rstrip(".")


def _info_table(conn: sqlite3.Connection, project: sqlite3.Row, tags: list[str], type_labels: dict) -> list[str]:
    """과제 정보 표 (TODO 241) — 면담 · 팀원 역량 말고는 모두. 과제 상세의 머리 · [과제 정보 수정] 에 있는 칸들.

    빈 칸은 줄째 뺀다. 효과 금액 · 완료일 · 분류 넷 · 유관부서 · 선행 · 후속 과제 · 접수 · 등록 · 보고 대상 여부.
    """
    from .projects import _predecessors_of, _successors_of

    def titled(ids: list[str]) -> str:
        out = []
        for project_id in ids:
            row = conn.execute("SELECT title FROM project WHERE id = ?", (project_id,)).fetchone()
            out.append(f"{project_id} {row['title']}" if row else project_id)
        return " · ".join(out)

    status = STATUS_LABELS.get(project["status"], project["status"])
    if project["status"] == "done" and project["completed_at"]:
        status += f" (완료일 {project['completed_at']})"
    classes = " · ".join(
        f"{CLASSIFICATION_LABELS[key]}: {project[key]}" for key in CLASSIFICATION_KEYS if project[key])
    partners: dict[str, list[str]] = {}
    for row in conn.execute(
            "SELECT team, person FROM project_partner WHERE project_id = ? ORDER BY position", (project["id"],)):
        partners.setdefault(row["team"], [])
        if row["person"]:
            partners[row["team"]].append(row["person"])
    partner_text = " · ".join(f"{team} ({', '.join(people)})" if people else team for team, people in partners.items())
    if project["no_effect"]:
        effect = "효과 금액으로 관리하지 않는 과제"
    else:
        expected, verified = _number(project["effect_expected"]), _number(project["effect_verified"])
        effect = " · ".join(filter(None, [f"기대 {expected}" if expected else None, f"실증 {verified}" if verified else None])) or None
    created = " · ".join(filter(None, [project["created_by"], (project["created_at"] or "")[:10] or None])) or None
    rows = [
        ("과제 번호", project["id"]),
        ("상태", status),
        ("속성", type_labels.get(project["type"]) if project["type"] else None),
        ("기간", f"{project['start_date'] or '—'} ~ {project['due_date'] or '—'}"),
        ("분류", classes or None),
        ("그룹", project["grp"]),
        ("태그", ", ".join(tags) or None),
        ("담당", project["owner"]),
        ("유관부서", partner_text or None),
        ("효과 (억원/년)", effect),
        ("그 밖의 성과", project["outcome"]),
        ("선행 과제", titled(_predecessors_of(conn, project["id"])) or None),
        ("후속 과제", titled(_successors_of(conn, project["id"])) or None),
        ("접수", project["intake_id"]),
        ("등록", created),
        ("보고", "별도 보고 대상 아님" if project["no_report"] else None),
    ]
    cell = lambda text: str(text).replace("|", "\\|").replace("\n", " ")  # noqa: E731
    lines = ["## 과제 정보", "", "| 항목 | 내용 |", "|---|---|"]
    lines += [f"| {label} | {cell(value)} |" for label, value in rows if value]
    return lines + [""]


def _contribution_lines(conn: sqlite3.Connection, project: sqlite3.Row) -> list[str]:
    """담당과 역할 · 회고 · 금액 아닌 성과 (TODO 237) — 업무 이력 정리의 재료. 적은 것이 없으면 절째 뺀다."""
    from .projects import contributions_of

    rows = contributions_of(conn, project["id"])
    written = [row for row in rows if row["role"] or row["part"] or row["skills"] or row["milestones"] or row["did"]
               or row["result"] or not row["derived"]]
    if not written:
        return []
    end_of_project = {"done": project["completed_at"], "dropped": "중단"}.get(project["status"])
    lines = ["## 담당과 역할", ""]
    for row in rows:
        period = f"{row['from'] or '?'} ~ {row['to'] or end_of_project or '지금'}"
        head = " · ".join(filter(None, [f"**{row['name']}**", row["role"], row["part"], period]))
        lines.append(f"- {head}")
        if row["skills"]:
            lines.append(f"  - 보유 기술(도구): {', '.join(row['skills'])}")
        if row["milestones"]:
            lines.append("  - 중간 성과:")
            lines += [f"    - {item['date']} {item['text']}" for item in row["milestones"]]
        for key, label in (("did", "내가 한 일"), ("result", "결과")):
            if row[key]:
                items = [line.strip() for line in row[key].strip().split("\n") if line.strip()]
                if len(items) == 1 and not items[0].startswith("- "):
                    lines.append(f"  - {label}: {items[0]}")
                else:
                    # 여러 줄 · 글머리표는 아래로 한 단계 들여 쓴 목록 (TODO 241) — "내가 한 일: - …" 처럼 붙지 않게
                    lines.append(f"  - {label}:")
                    lines += [f"    - {item[2:].strip() if item.startswith('- ') else item}" for item in items]
    return lines + [""]


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
            angled, plain = match.group(3), match.group(4)
            target = resolve_link(angled if angled is not None else plain, doc_dir)
            if target:
                used.append(target)
        return _rewrite_links(body, doc_dir, mode, directory, dir_name)

    tags = _tags(conn, project_id)
    # 속성 이름은 설정에서 온다 — 사용자가 고친 이름이 내보내는 문서에도 그대로 나가야 한다.
    type_labels = settings_service.type_labels()
    header = [
        f"# {project['title']}",
        "",
        "> "
        + " · ".join(
            filter(
                None,
                [
                    f"상태: {STATUS_LABELS.get(project['status'], project['status'])}",
                    # 속성 이름은 설정에서 온다 — 사용자가 고친 이름이 그대로 나가야 한다 (TODO 100).
                    f"속성: {type_labels[project['type']]}" if project["type"] in type_labels else None,
                    f"기간: {project['start_date'] or '—'} ~ {project['due_date'] or '—'}",
                    f"그룹: {project['grp']}" if project["grp"] else None,
                    f"태그: {', '.join(tags)}" if tags else None,
                    f"담당: {project['owner']}" if project["owner"] else None,
                ],
            )
        ),
        "",
        *_info_table(conn, project, tags, type_labels),
        "## 과제 개요",
        "",
        demote_headings(convert(project["body"] or "", PROJECT_DOC_DIR).strip()),
        "",
        *_contribution_lines(conn, project),
        "---",
        "",
        "# 수행 이력",
        "",
    ]

    for entry in conn.execute(
        "SELECT * FROM entry WHERE project_id = ? ORDER BY date ASC, id ASC", (project_id,)
    ):
        header += [f"## {entry['date']} {entry['title']}", ""]
        # 누가 썼나 · 일지 태그 (TODO 241) — 233 뒤로는 팀원이 쓴 일지도 있다. 업무 이력을 요약할 때 "누가 한 일" 을 가른다
        entry_tags = [row["name"] for row in conn.execute(
            "SELECT t.name FROM entry_tag et JOIN tag t ON t.id = et.tag_id WHERE et.entry_id = ? ORDER BY t.name", (entry["id"],))]
        meta_line = " · ".join(filter(None, [f"작성: {entry['author']}" if entry["author"] else None,
                                             f"태그: {', '.join(entry_tags)}" if entry_tags else None]))
        if meta_line:
            header += [f"> {meta_line}", ""]
        header += [demote_headings(convert(entry["body"] or "", ENTRY_DOC_DIR).strip()), ""]

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
            audience = f" · 보고 대상: {report['audience']}" if report["audience"] else ""
            header += [
                f"- **{report['report_date']}** {_report_label(report)} ({state}{audience}) — "
                f"{first_line.lstrip('- ').strip()}{note}"
            ]
        header += [""]

        if include_reports_full:
            for report in reports:
                header += [
                    f"## [보고] {report['report_date']} {_report_label(report)}",
                    "",
                    demote_headings(convert(report["body"] or "", report_doc_dir(report["rel_path"])).strip()),
                    "",
                ]

    filename = f"{dir_name}.md"
    return filename, "\n".join(header).rstrip() + "\n", sorted(set(used))


def _zip_files(destination, first: tuple[str, str] | None, files: list[tuple[Path, str]], progress=None) -> None:
    """파일들을 zip 으로 **흘려 쓴다**(TODO 268 — 예전에는 메모리에 통째로 만들었다). `progress(n, N, 크기, 전체 크기)`."""
    import os

    sizes = []
    for path, _name in files:
        try:
            sizes.append(os.path.getsize(path))
        except OSError:
            sizes.append(0)
    total, done = sum(sizes), 0
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        if first:
            archive.writestr(*first)
        for index, ((path, name), size) in enumerate(zip(files, sizes), start=1):
            try:
                archive.write(path, name)
            except FileNotFoundError:
                continue
            done += size
            if progress is not None:
                progress(index, len(files), done, total)


def export_zip_name(conn: sqlite3.Connection, project_id: str, kind: str) -> str:
    directory = project_dir(conn, project_id)
    return f"{directory.name}-백업.zip" if kind == "backup" else f"{directory.name}.zip"


def write_export_zip(conn: sqlite3.Connection, project_id: str, destination, include_reports_full: bool = False,
                     progress=None) -> str:
    """병합 md + 참조된 첨부 폴더. 압축을 풀면 링크가 그대로 살아 있다. zip 이름을 돌려준다."""
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
    files = [(directory / rel, rel) for rel in sorted(set(used) | set(report_files)) if (directory / rel).is_file()]
    _zip_files(destination, (filename, text), files, progress)
    return f"{filename[:-3]}.zip"


def export_zip(conn: sqlite3.Connection, project_id: str, include_reports_full: bool = False) -> tuple[str, bytes]:
    buffer = io.BytesIO()
    name = write_export_zip(conn, project_id, buffer, include_reports_full)
    return name, buffer.getvalue()


def write_backup_zip(conn: sqlite3.Connection, project_id: str, destination, progress=None) -> str:
    """원본 폴더 구조 그대로. 다른 도구로 옮겨 갈 때 쓴다."""
    directory = project_dir(conn, project_id)
    files = [(path, path.relative_to(directory).as_posix()) for path in sorted(directory.rglob("*")) if path.is_file()]
    _zip_files(destination, None, files, progress)
    return f"{directory.name}-백업.zip"


def backup_zip(conn: sqlite3.Connection, project_id: str) -> tuple[str, bytes]:
    buffer = io.BytesIO()
    name = write_backup_zip(conn, project_id, buffer)
    return name, buffer.getvalue()


# 백업에 넣지 않는 것 (TODO 202 ㉜) — 저장 도중의 임시 파일(`markdown.save` 의 `.tmp`, 업로드 · 백업의 `.part`).
# 반쯤 쓴 파일이 백업에 섞이면 되살릴 때 원본과 구별이 안 된다.
TEMP_SUFFIXES = (".tmp", ".part")
# 첨부 제외 백업 (TODO 197 ③ · 202) 에서 건너뛰는 폴더 이름 — 과제 · 보고 · 접수의 첨부가 모두 `assets/` 아래에 있다.
ASSETS_DIR = "assets"


def backup_all_filename(assets: bool = True) -> str:
    from datetime import datetime

    return f"과제이력-전체백업-{datetime.now():%Y%m%d}{'' if assets else '-첨부제외'}.zip"


def _vault_files(vault: Path, assets: bool) -> list[tuple[Path, str]]:
    """백업에 담을 파일 (경로, zip 안 이름). 색인 · 휴지통 · 임시 파일은 뺀다.

    `assets=False` 이면 **첨부(`assets/` 폴더)를 통째로 뺀다** (TODO 197 ③) — 문서(.md) · 설정 · 이전 버전 ·
    기록은 남긴다. 문서만 있으면 이력은 되살릴 수 있고, 첨부는 GB 단위로 커지기 때문이다.
    썸네일 캐시는 `.index` 안이라 어느 쪽이든 빠진다.

    훑는 중에 폴더가 사라지거나 이름이 바뀌어도 멈추지 않는다 (TODO 202 ㉜) — `os.walk` 는 못 읽는 폴더를 건너뛴다.
    """
    import os

    found: list[tuple[Path, str]] = []
    for root, dirnames, filenames in os.walk(vault):
        here = Path(root)
        rel_root = here.relative_to(vault)
        if rel_root == Path("."):
            # 색인(.index)과 휴지통(.trash)은 다시 만들 수 있거나 버린 것이라 뺀다.
            dirnames[:] = [name for name in dirnames if name not in {".index", ".trash", ".restoring", ".work"}]  # .restoring = 되살리기 작업 자리 (TODO 246) · .work = 큰 작업 파일 (267)
        if not assets:
            dirnames[:] = [name for name in dirnames if name != ASSETS_DIR]
        dirnames.sort()
        for name in sorted(filenames):
            if name.endswith(TEMP_SUFFIXES):
                continue
            found.append((here / name, (rel_root / name).as_posix()))
    return found


class BackupCancelled(Exception):
    """진행 표시의 [그만두기] (TODO 266)."""


def write_backup_all(destination: Path | BinaryIO, assets: bool = True, progress=None) -> int:
    """vault 전체 zip 을 **디스크로 흘려 쓴다** (TODO 202 ⑬) — 메모리에 통째로 올리지 않는다.

    첨부가 GB 면 예전 방식(BytesIO)은 MemoryError 로 자동 백업이 한 번도 성공하지 못했다.
    `destination` 은 임시 경로(`.part`)여야 한다 — 다 쓴 뒤 이름을 바꾸는 것은 부르는 쪽 몫이다.
    담은 파일 수를 돌려준다.

    `progress(files_done, files_total, bytes_done, bytes_total)` — 파일마다 부른다(TODO 266 진행 표시). False 를 돌려주면 멈춘다.
    """
    import os

    from ..config import get_settings

    vault = get_settings().vault_dir
    files = _vault_files(vault, assets)
    sizes = []
    for path, _name in files:
        try:
            sizes.append(os.path.getsize(path))
        except OSError:
            sizes.append(0)
    total = sum(sizes)
    done = 0
    count = 0
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for index, ((path, name), size) in enumerate(zip(files, sizes), start=1):
            try:
                archive.write(path, name)
            except FileNotFoundError:
                continue  # 훑은 뒤 사라진 파일 (저장 도중의 이름 바꾸기 등) — 건너뛴다 (TODO 202 ㉜)
            count += 1
            done += size
            if progress is not None and progress(index, len(files), done, total) is False:
                raise BackupCancelled()
    return count


def backup_all(conn: sqlite3.Connection, assets: bool = True) -> tuple[str, bytes]:
    """vault 전체를 바이트로 — 작은 vault · 시험용. 화면 내려받기와 자동 백업은 `write_backup_all` 로 디스크에 쓴다."""
    buffer = io.BytesIO()
    write_backup_all(buffer, assets)
    return backup_all_filename(assets), buffer.getvalue()


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
    # 앱 화면과 같은 규칙: 본문에 섞인 raw HTML은 실행하지 않고 글자로 보여 준다.
    renderer = MarkdownIt("commonmark", {"breaks": True, "linkify": True, "html": False}).enable("table")
    project = _project_row(conn, project_id)
    return f"{filename[:-3]}.html", HTML_TEMPLATE.format(
        title=project["title"], body=restore_line_breaks(renderer.render(text))
    )


def restore_line_breaks(html: str) -> str:
    """표 칸 안의 `<br>` 만 줄바꿈으로 되살린다 — 화면(`markdown.ts`)과 같은 규칙 (TODO 148).
    속성이 붙은 태그와 코드 안은 글자 그대로 둔다."""
    import re

    parts = re.split(r"(<code[\s\S]*?</code>)", html)
    return "".join(
        part if index % 2 else re.sub(r"&lt;br\s*/?&gt;", "<br>", part, flags=re.I)
        for index, part in enumerate(parts)
    )
