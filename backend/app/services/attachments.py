"""첨부 파일 저장.

용량 상한이 없으므로 전체를 메모리에 올리지 않고 청크 단위로 흘려보낸다.
저장 위치는 과제 폴더 안의 상대 경로라, 외부 뷰어에서도 링크가 그대로 열린다.
"""
from __future__ import annotations

import hashlib
import mimetypes
import os
import re
import shutil
import sqlite3
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Iterable

from ..config import get_settings
from ..vault import paths
from .projects import now_iso, project_dir

CHUNK_SIZE = 1024 * 1024  # 1MB
MIN_FREE_BYTES = 200 * 1024 * 1024  # 여유 공간이 이보다 적으면 중단한다
THUMB_MAX = 480
_UNSAFE = re.compile(r"[\\/:*?\"<>|\x00-\x1f]+")
_REF_PATTERN = re.compile(r"\]\(\s*(assets/[^)\s]+)")


def safe_filename(name: str) -> str:
    """경로 구분자와 제어문자를 제거한다. 한글과 공백은 유지한다."""
    name = unicodedata.normalize("NFC", name or "")
    name = _UNSAFE.sub("", name).strip().lstrip(".")
    return name or "attachment"


def is_image(mime: str | None) -> bool:
    return bool(mime and mime.startswith("image/"))


def guess_mime(name: str, fallback: str | None) -> str:
    if fallback and fallback != "application/octet-stream":
        return fallback
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


def _stream_to_temp(source: BinaryIO, directory: Path) -> tuple[Path, str, int]:
    """청크로 임시 파일에 쓰면서 같은 패스에 sha256과 크기를 계산한다."""
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    fd, tmp_name = tempfile.mkstemp(dir=str(directory), suffix=".part")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as target:
            while True:
                chunk = source.read(CHUNK_SIZE)
                if not chunk:
                    break
                if shutil.disk_usage(directory).free < MIN_FREE_BYTES:
                    raise OSError("디스크 여유 공간이 부족합니다.")
                target.write(chunk)
                digest.update(chunk)
                size += len(chunk)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return tmp_path, digest.hexdigest(), size


def save_attachment(
    conn: sqlite3.Connection,
    project_id: str,
    entry_id: int | None,
    entry_date: str,
    filename: str,
    source: BinaryIO,
    content_type: str | None = None,
    report_id: int | None = None,
) -> dict:
    directory = project_dir(conn, project_id)
    bucket = paths.safe_join(directory, "assets", entry_date)
    tmp_path, sha256, size = _stream_to_temp(source, bucket)

    # 같은 과제에 동일한 파일이 이미 있으면 다시 저장하지 않는다.
    existing = conn.execute(
        "SELECT * FROM attachment WHERE project_id = ? AND sha256 = ?", (project_id, sha256)
    ).fetchone()
    if existing and (directory / existing["rel_path"]).exists():
        tmp_path.unlink(missing_ok=True)
        return dict(existing) | {"deduplicated": True}

    clean_name = safe_filename(filename)
    target = bucket / f"{paths.next_sequence_prefix(bucket)}-{clean_name}"
    if target.exists():
        target = paths.unique_path(bucket, target.stem, target.suffix)
    os.replace(tmp_path, target)

    rel_path = target.relative_to(directory).as_posix()
    conn.execute(
        """
        INSERT INTO attachment(project_id, entry_id, report_id, rel_path, orig_name, mime,
                               size_bytes, sha256, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(project_id, rel_path) DO UPDATE SET
          entry_id=excluded.entry_id, report_id=excluded.report_id, orig_name=excluded.orig_name,
          mime=excluded.mime, size_bytes=excluded.size_bytes, sha256=excluded.sha256
        """,
        (
            project_id,
            entry_id,
            report_id,
            rel_path,
            clean_name,
            guess_mime(clean_name, content_type),
            size,
            sha256,
            now_iso(),
        ),
    )
    conn.commit()
    sync_entry_meta(conn, entry_id)
    row = conn.execute(
        "SELECT * FROM attachment WHERE project_id = ? AND rel_path = ?", (project_id, rel_path)
    ).fetchone()
    return dict(row) | {"deduplicated": False}


def sync_entry_meta(conn: sqlite3.Connection, entry_id: int | None) -> None:
    """진행일지 front matter의 attachments 목록을 실제 첨부와 맞춘다.

    본문에서 참조하지 않는 자료도 md 파일만 보고 알 수 있게 하기 위함이다.
    """
    if entry_id is None:
        return
    from ..vault import markdown as md
    from .entries import entry_path

    try:
        _, path = entry_path(conn, entry_id)
    except KeyError:
        return
    rel_paths = [
        row["rel_path"]
        for row in conn.execute(
            "SELECT rel_path FROM attachment WHERE entry_id = ? ORDER BY rel_path", (entry_id,)
        )
    ]
    doc = md.load(path)
    if doc.meta.get("attachments") == rel_paths:
        return
    doc.meta = md.merge_meta(doc.meta, {"attachments": rel_paths})
    md.save(path, doc)


def attachment_file(conn: sqlite3.Connection, attachment_id: int) -> tuple[sqlite3.Row, Path]:
    row = conn.execute("SELECT * FROM attachment WHERE id = ?", (attachment_id,)).fetchone()
    if row is None:
        raise KeyError(attachment_id)
    directory = project_dir(conn, row["project_id"])
    return row, paths.safe_join(directory, row["rel_path"])


def thumbnail(conn: sqlite3.Connection, attachment_id: int) -> Path:
    """썸네일은 vault/.index/thumbs 아래 캐시한다 (과제 폴더를 어지럽히지 않는다)."""
    row, path = attachment_file(conn, attachment_id)
    if not is_image(row["mime"]):
        raise ValueError("이미지가 아닙니다.")

    cache_dir = get_settings().index_dir / "thumbs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / f"{row['sha256']}.jpg"
    if cached.exists():
        return cached

    from PIL import Image

    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((THUMB_MAX, THUMB_MAX))
        image.save(cached, "JPEG", quality=82)
    return cached


def referenced_paths(bodies: Iterable[str]) -> set[str]:
    found: set[str] = set()
    for body in bodies:
        found.update(_REF_PATTERN.findall(body or ""))
    return found


def list_attachments(conn: sqlite3.Connection, project_id: str) -> list[dict]:
    """과제의 첨부 목록. 본문에서 참조되지 않는 파일은 orphan으로 표시만 한다."""
    bodies = [row["body"] or "" for row in conn.execute(
        "SELECT body FROM entry WHERE project_id = ?", (project_id,)
    )]
    bodies += [row["body"] or "" for row in conn.execute(
        "SELECT body FROM project WHERE id = ?", (project_id,)
    )]
    referenced = referenced_paths(bodies)
    rows = conn.execute(
        "SELECT * FROM attachment WHERE project_id = ? ORDER BY rel_path", (project_id,)
    ).fetchall()
    return [dict(row) | {"orphan": row["rel_path"] not in referenced} for row in rows]


def delete_attachment(conn: sqlite3.Connection, attachment_id: int) -> None:
    row, path = attachment_file(conn, attachment_id)
    trash = get_settings().trash_dir
    trash.mkdir(parents=True, exist_ok=True)
    if path.exists():
        target = paths.unique_path(
            trash, f"{row['project_id']}-{datetime.now():%Y%m%d%H%M%S}-{path.stem}", path.suffix
        )
        shutil.move(str(path), str(target))
    conn.execute("DELETE FROM attachment WHERE id = ?", (attachment_id,))
    conn.commit()
    sync_entry_meta(conn, row["entry_id"])
