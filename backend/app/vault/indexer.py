"""vault 스캔 → SQLite 인덱스 갱신.

파일이 진실의 원천이므로 인덱스는 항상 파일을 보고 다시 만든다.
외부 편집기(Obsidian 등)로 고친 내용도 이 경로로 반영된다.
"""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path
from typing import Any, NamedTuple

from ..config import TYPE_KEYS, get_settings, normalize_status
from . import markdown as md


class IndexProblem(NamedTuple):
    """읽지 못한 파일. 사용자에게 알려 주고 나머지는 계속 인덱싱한다."""

    rel_path: str
    reason: str


def _load_doc(path: Path, root: Path, problems: list[IndexProblem] | None) -> md.MarkdownDoc | None:
    """front matter가 깨진 파일 하나 때문에 전체 인덱싱이 멈추지 않게 한다."""
    try:
        return md.load(path)
    except Exception as exc:  # YAML 오류, 인코딩 오류 등 무엇이든
        if problems is not None:
            reason = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
            problems.append(IndexProblem(path.relative_to(root).as_posix(), reason))
        return None


def _as_str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (date_cls,)):
        return value.isoformat()
    return str(value)


def _as_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


def _as_effect(value: object) -> float | None:
    """효과 금액(억원/년). 손으로 고친 파일에 숫자가 아닌 값이 들어와도 색인을 멈추지 않는다."""
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _sync_tags(conn: sqlite3.Connection, table: str, column: str, owner_id: Any, tags: list[str]) -> None:
    conn.execute(f"DELETE FROM {table} WHERE {column} = ?", (owner_id,))
    for name in tags:
        conn.execute("INSERT OR IGNORE INTO tag(name) VALUES (?)", (name,))
        row = conn.execute("SELECT id FROM tag WHERE name = ?", (name,)).fetchone()
        conn.execute(
            f"INSERT OR IGNORE INTO {table}({column}, tag_id) VALUES (?, ?)",
            (owner_id, row["id"]),
        )


def _sync_owners(conn: sqlite3.Connection, project_id: str, owners: list[str]) -> None:
    conn.execute("DELETE FROM project_owner WHERE project_id = ?", (project_id,))
    for position, name in enumerate(owners):
        conn.execute(
            "INSERT OR IGNORE INTO project_owner(project_id, name, position) VALUES (?, ?, ?)",
            (project_id, name, position),
        )


def _index_entries(
    conn: sqlite3.Connection,
    project_id: str,
    project_dir: Path,
    problems: list[IndexProblem] | None = None,
) -> str | None:
    """진행일지를 인덱싱하고 가장 최근 수정 시각을 돌려준다."""
    logs_dir = project_dir / "logs"
    seen: list[str] = []
    latest: str | None = None
    for path in sorted(logs_dir.glob("*.md")) if logs_dir.exists() else []:
        doc = _load_doc(path, project_dir.parent.parent, problems)
        if doc is None:
            # 깨진 파일은 건너뛰되 인덱스에서 지우지는 않는다 (직전 내용을 유지).
            seen.append(path.relative_to(project_dir).as_posix())
            continue
        rel_path = path.relative_to(project_dir).as_posix()
        entry_date = _as_str(doc.meta.get("date")) or path.name[:10]
        title = _as_str(doc.meta.get("title")) or path.stem
        updated_at = _as_str(doc.meta.get("updated_at"))
        conn.execute(
            """
            INSERT INTO entry(project_id, rel_path, date, title, author, body,
                              created_at, updated_at, file_mtime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, rel_path) DO UPDATE SET
              date=excluded.date, title=excluded.title, author=excluded.author, body=excluded.body,
              created_at=excluded.created_at, updated_at=excluded.updated_at,
              file_mtime=excluded.file_mtime
            """,
            (
                project_id,
                rel_path,
                entry_date,
                title,
                _as_str(doc.meta.get("author")),
                doc.body,
                _as_str(doc.meta.get("created_at")),
                updated_at,
                path.stat().st_mtime,
            ),
        )
        row = conn.execute(
            "SELECT id FROM entry WHERE project_id = ? AND rel_path = ?", (project_id, rel_path)
        ).fetchone()
        _sync_tags(conn, "entry_tag", "entry_id", row["id"], _as_list(doc.meta.get("tags")))
        seen.append(rel_path)
        for candidate in (updated_at, entry_date):
            if candidate and (latest is None or candidate > latest):
                latest = candidate

    placeholders = ",".join("?" * len(seen))
    if seen:
        conn.execute(
            f"DELETE FROM entry WHERE project_id = ? AND rel_path NOT IN ({placeholders})",
            (project_id, *seen),
        )
    else:
        conn.execute("DELETE FROM entry WHERE project_id = ?", (project_id,))
    return latest


def project_id_from_dir_name(dir_name: str) -> str:
    """폴더명에서 과제 id 를 얻는다. 두 형태를 모두 읽는다.

        2026-001-제목        →  2026-001
        2026-소재-001-제목    →  2026-소재-001

    규칙: 맨 앞 네 자리 연도로 시작하고, 그 뒤 **처음 나오는 숫자 토막**이 일련번호다.
    그 사이에 있는 것이 팀 코드다. (팀 코드는 숫자만으로 지을 수 없게 막아 두었다 —
    그래야 일련번호와 헷갈리지 않는다)

    이 함수는 front matter 의 id 를 못 읽었을 때만 쓰는 예비 수단이다.
    """
    parts = dir_name.split("-")
    if len(parts) < 2 or not (len(parts[0]) == 4 and parts[0].isdigit()):
        return dir_name
    for index in range(1, len(parts)):
        if parts[index].isdigit():
            return "-".join(parts[: index + 1])
    return dir_name


def index_project(
    conn: sqlite3.Connection, project_dir: Path, problems: list[IndexProblem] | None = None
) -> str | None:
    """과제 폴더 하나를 인덱싱한다. 반환값은 과제 id."""
    index_md = project_dir / "index.md"
    if not index_md.exists():
        return None

    doc = _load_doc(index_md, project_dir.parent.parent, problems)
    if doc is None:
        # 개요 문서를 못 읽으면 이 과제는 이번 회차에 건드리지 않는다.
        return project_id_from_dir_name(project_dir.name)
    project_id = _as_str(doc.meta.get("id")) or project_id_from_dir_name(project_dir.name)
    # owners(복수)가 우선이고, 예전 문서의 owner(단수)도 그대로 읽는다.
    owners = _as_list(doc.meta.get("owners")) or _as_list(doc.meta.get("owner"))
    # 예전에 상태로 쓰이던 '기획보고' 같은 값은 상태+속성으로 나눠 읽는다.
    status, implied_type = normalize_status(_as_str(doc.meta.get("status")))
    project_type = _as_str(doc.meta.get("type")) or implied_type
    if project_type not in TYPE_KEYS:
        project_type = None
    updated_at = _as_str(doc.meta.get("updated_at"))

    conn.execute(
        """
        INSERT INTO project(id, dir_name, title, status, type, grp, owner, start_date, due_date,
                            effect_expected, effect_verified, created_by,
                            created_at, updated_at, body, file_mtime)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          dir_name=excluded.dir_name, title=excluded.title, status=excluded.status,
          type=excluded.type, grp=excluded.grp, owner=excluded.owner, start_date=excluded.start_date,
          due_date=excluded.due_date,
          effect_expected=excluded.effect_expected, effect_verified=excluded.effect_verified,
          created_by=excluded.created_by, created_at=excluded.created_at,
          updated_at=excluded.updated_at, body=excluded.body, file_mtime=excluded.file_mtime
        """,
        (
            project_id,
            project_dir.name,
            _as_str(doc.meta.get("title")) or project_dir.name,
            status,
            project_type,
            _as_str(doc.meta.get("group")),
            ", ".join(owners) or None,
            _as_str(doc.meta.get("start_date")),
            _as_str(doc.meta.get("due_date")),
            _as_effect(doc.meta.get("effect_expected")),
            _as_effect(doc.meta.get("effect_verified")),
            _as_str(doc.meta.get("created_by")),
            _as_str(doc.meta.get("created_at")),
            updated_at,
            doc.body,
            index_md.stat().st_mtime,
        ),
    )
    _sync_tags(conn, "project_tag", "project_id", project_id, _as_list(doc.meta.get("tags")))
    _sync_owners(conn, project_id, owners)

    latest_entry = _index_entries(conn, project_id, project_dir, problems)
    if latest_entry and (updated_at is None or latest_entry > updated_at):
        conn.execute("UPDATE project SET updated_at = ? WHERE id = ?", (latest_entry, project_id))

    _index_reports(conn, project_id, project_dir, problems)
    _index_attachments(conn, project_id, project_dir)
    _rebuild_search(conn, project_id)
    return project_id


def _index_reports(
    conn: sqlite3.Connection,
    project_id: str,
    project_dir: Path,
    problems: list[IndexProblem] | None = None,
) -> None:
    """reports/<날짜>/report.md 를 인덱싱하고, 포함된 진행일지를 연결한다."""
    reports_dir = project_dir / "reports"
    seen: list[str] = []
    for path in sorted(reports_dir.glob("*/report.md")) if reports_dir.exists() else []:
        doc = _load_doc(path, project_dir.parent.parent, problems)
        if doc is None:
            seen.append(path.relative_to(project_dir).as_posix())
            continue
        rel_path = path.relative_to(project_dir).as_posix()
        report_date = _as_str(doc.meta.get("report_date")) or path.parent.name
        conn.execute(
            """
            INSERT INTO report(project_id, report_date, title, rel_path, covers_from, covers_to,
                               author, body, frozen_at, report_type, audience, file_mtime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, rel_path) DO UPDATE SET
              report_date=excluded.report_date, title=excluded.title,
              covers_from=excluded.covers_from, covers_to=excluded.covers_to,
              author=excluded.author,
              body=excluded.body, frozen_at=excluded.frozen_at,
              report_type=excluded.report_type, audience=excluded.audience,
              file_mtime=excluded.file_mtime
            """,
            (
                project_id,
                report_date,
                _as_str(doc.meta.get("title")) or f"{report_date} 보고",
                rel_path,
                _as_str(doc.meta.get("covers_from")),
                _as_str(doc.meta.get("covers_to")),
                _as_str(doc.meta.get("author")),
                doc.body,
                _as_str(doc.meta.get("frozen_at")),
                _as_str(doc.meta.get("report_type")),
                _as_str(doc.meta.get("audience")),
                path.stat().st_mtime,
            ),
        )
        report_row = conn.execute(
            "SELECT id FROM report WHERE project_id = ? AND rel_path = ?", (project_id, rel_path)
        ).fetchone()

        # 보고가 담은 진행일지 연결 — '미보고 분량' 계산의 근거가 된다.
        conn.execute("DELETE FROM report_entry WHERE report_id = ?", (report_row["id"],))
        for entry_rel in _as_list(doc.meta.get("covered_entries")):
            entry = conn.execute(
                "SELECT id FROM entry WHERE project_id = ? AND rel_path = ?", (project_id, entry_rel)
            ).fetchone()
            if entry:
                conn.execute(
                    "INSERT OR IGNORE INTO report_entry(report_id, entry_id) VALUES (?, ?)",
                    (report_row["id"], entry["id"]),
                )
        seen.append(rel_path)

    if seen:
        placeholders = ",".join("?" * len(seen))
        conn.execute(
            f"DELETE FROM report WHERE project_id = ? AND rel_path NOT IN ({placeholders})",
            (project_id, *seen),
        )
    else:
        conn.execute("DELETE FROM report WHERE project_id = ?", (project_id,))

    latest = conn.execute(
        "SELECT MAX(report_date) AS last FROM report WHERE project_id = ? AND frozen_at IS NOT NULL",
        (project_id,),
    ).fetchone()
    conn.execute(
        "UPDATE project SET last_reported_at = ? WHERE id = ?", (latest["last"], project_id)
    )


def _index_attachments(conn: sqlite3.Connection, project_id: str, project_dir: Path) -> None:
    """assets/ 아래 실제 파일을 인덱싱하고, 본문에서 참조하는 일지와 연결한다.

    외부에서 파일을 직접 넣어 둔 경우에도 목록에 잡히게 하기 위함이다.
    """
    from ..services.attachments import ENTRY_DOC_DIR, guess_mime, referenced_paths  # 순환 참조 방지

    entries = conn.execute(
        "SELECT id, rel_path, body FROM entry WHERE project_id = ?", (project_id,)
    ).fetchall()
    owner_of: dict[str, int] = {}
    for entry in entries:
        for ref in referenced_paths([(entry["body"] or "", ENTRY_DOC_DIR)]):
            owner_of.setdefault(ref, entry["id"])

    # 진행일지 첨부(assets/)와 보고 자료(reports/<날짜>/assets/)를 모두 훑는다.
    candidates: list[Path] = []
    for directory in (project_dir / "assets", project_dir / "reports"):
        if directory.exists():
            candidates.extend(sorted(directory.rglob("*")))

    seen: list[str] = []
    for path in candidates:
        if not path.is_file() or path.suffix == ".md":
            continue
        rel_path = path.relative_to(project_dir).as_posix()
        size = path.stat().st_size
        known = conn.execute(
            "SELECT id, size_bytes, sha256 FROM attachment WHERE project_id = ? AND rel_path = ?",
            (project_id, rel_path),
        ).fetchone()
        # 크기가 그대로면 해시를 다시 계산하지 않는다 (대용량 파일 대비).
        if known and known["size_bytes"] == size and known["sha256"]:
            digest = known["sha256"]
        else:
            digest = _sha256_of(path)
        conn.execute(
            """
            INSERT INTO attachment(project_id, entry_id, rel_path, orig_name, mime, size_bytes,
                                   sha256, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, rel_path) DO UPDATE SET
              entry_id=COALESCE(excluded.entry_id, attachment.entry_id),
              mime=excluded.mime, size_bytes=excluded.size_bytes, sha256=excluded.sha256
            """,
            (
                project_id,
                owner_of.get(rel_path),
                rel_path,
                path.name.split("-", 1)[-1] if path.name[:3].isdigit() else path.name,
                guess_mime(path.name, None),
                size,
                digest,
                datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
            ),
        )
        seen.append(rel_path)

    if seen:
        placeholders = ",".join("?" * len(seen))
        conn.execute(
            f"DELETE FROM attachment WHERE project_id = ? AND rel_path NOT IN ({placeholders})",
            (project_id, *seen),
        )
    else:
        conn.execute("DELETE FROM attachment WHERE project_id = ?", (project_id,))


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rebuild_search(conn: sqlite3.Connection, project_id: str) -> None:
    """검색 색인을 이 과제 몫만 다시 만든다.

    색인에 넣는 것은 **사람이 검색창에 칠 만한 것 전부**다 (TODO 53).
    예전에는 과제와 진행일지의 제목·본문만 넣어서, "전사 주요업무 보고" 로 찾으면
    아무것도 안 나왔다 — 보고 문서가 아예 색인 대상이 아니었기 때문이다.

    태그·담당자는 과제의 본문 뒤에 덧붙인다. 따로 갈래를 만들 만큼 긴 글이 아니고,
    "권경락" 으로 찾으면 그 사람이 맡은 과제가 나오는 것이 자연스럽다.
    """
    conn.execute("DELETE FROM search_fts WHERE project_id = ?", (project_id,))
    project = conn.execute("SELECT title, body FROM project WHERE id = ?", (project_id,)).fetchone()
    if project:
        extras = [row["name"] for row in conn.execute(
            "SELECT name FROM project_owner WHERE project_id = ?", (project_id,)
        )]
        extras += [row["name"] for row in conn.execute(
            "SELECT t.name FROM tag t JOIN project_tag pt ON pt.tag_id = t.id"
            " WHERE pt.project_id = ?", (project_id,)
        )]
        body = "\n".join([project["body"] or "", *extras])
        conn.execute(
            "INSERT INTO search_fts(kind, ref_id, project_id, title, body) VALUES ('project', ?, ?, ?, ?)",
            (project_id, project_id, project["title"], body),
        )
    for row in conn.execute("SELECT id, title, body FROM entry WHERE project_id = ?", (project_id,)):
        conn.execute(
            "INSERT INTO search_fts(kind, ref_id, project_id, title, body) VALUES ('entry', ?, ?, ?, ?)",
            (str(row["id"]), project_id, row["title"], row["body"] or ""),
        )
    # 보고 문서. 피보고자("전사 주요업무 보고")로 찾는 일이 잦아 제목 쪽에 함께 넣는다.
    for row in conn.execute(
        "SELECT id, title, body, audience, report_date FROM report WHERE project_id = ?", (project_id,)
    ):
        title = " ".join(filter(None, [row["report_date"], row["title"], row["audience"]]))
        conn.execute(
            "INSERT INTO search_fts(kind, ref_id, project_id, title, body) VALUES ('report', ?, ?, ?, ?)",
            (str(row["id"]), project_id, title, row["body"] or ""),
        )


def reindex_all(conn: sqlite3.Connection) -> tuple[int, list[IndexProblem]]:
    """vault 전체 재인덱싱. DB를 지운 뒤에도 이것만 돌리면 복구된다.

    파일 하나가 깨져 있어도 나머지는 정상적으로 인덱싱하고, 문제 파일 목록을 함께 돌려준다.
    """
    settings = get_settings()
    settings.ensure_dirs()
    problems: list[IndexProblem] = []
    found: list[str] = []
    for project_dir in sorted(settings.projects_dir.iterdir()):
        if not project_dir.is_dir() or project_dir.name.startswith("."):
            continue
        project_id = index_project(conn, project_dir, problems)
        if project_id:
            found.append(project_id)

    if found:
        placeholders = ",".join("?" * len(found))
        conn.execute(f"DELETE FROM project WHERE id NOT IN ({placeholders})", tuple(found))
    else:
        conn.execute("DELETE FROM project")
    conn.commit()
    return len(found), problems
