"""전체 백업 ZIP 에서 되살리기 (TODO 246) — 새 서버로 옮길 때.

[전체 백업](`export.write_backup_all`)은 데이터 폴더(vault)의 짜임 그대로 담는다 — `projects/` · `people/` · `intakes/` ·
`settings.json` · `.versions/` · `.logs/` · `.drafts/`. 그래서 되살리기는 그 ZIP 을 데이터 폴더 자리에 다시 펴는 일이다.

정한 것 (2026-11-09 사용자 — 추천안대로)
* **바꾸기** — 합치지 않는다. 지금 데이터는 **먼저 통째로 백업**해 둔다(자동 백업 폴더 · 없으면 데이터 폴더 옆).
* 이 PC 의 화면에서만 — 끝점이 `/api/backup` 밑이라 공유 바깥(팀원 포함)에는 막혀 있다(`share.BLOCKED_PREFIXES`).
* 자동 백업 폴더는 백업 속 값을 그대로 두되, 이 PC 에 없으면 알린다.

안전
* 올린 ZIP 은 임시 파일에 흘려 받는다(첨부가 GB 여도 메모리에 올리지 않는다). 살펴보기 → 되살리기는 그 파일 하나로.
* 이름은 하나씩 따진다 — 절대 경로 · `..` · 드라이브 글자는 거부, 색인(`.index`) · 휴지통(`.trash`)은 건너뛴다.
* 데이터 폴더 **안의** 작업 자리(`.restoring/`)에 먼저 다 풀고 나서 맨 윗단 항목을 차례로 맞바꾼다 — 같은 드라이브라 옮기기가 즉시다.
  도중에 실패하면 옮긴 것을 되돌려 **지금 데이터는 그대로** 둔다. 색인(`.index`)은 열려 있으므로 옮기지 않고 비운 뒤 다시 만든다.
"""
from __future__ import annotations

import os
import re
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

from ..config import get_settings

WORK_DIR = ".restoring"
# 데이터 폴더 안에서 되살리기가 건드리지 않는 것 — 열려 있는 색인과 작업 자리
KEEP_IN_PLACE = {".index", WORK_DIR}
# ZIP 에 있어도 펴지 않는 것 — 다시 만들 수 있거나 버린 것
SKIP_TOP = {".index", ".trash", WORK_DIR}
# 이 도구의 데이터 폴더라고 볼 수 있는 맨 윗단 이름 — 하나도 없으면 엉뚱한 ZIP 이다
KNOWN_TOP = {"projects", "people", "intakes", "settings.json"}
SAFETY_PREFIX = "과제이력-되살리기전-"
UPLOAD_DIR_NAME = "느린나이테-되살리기"
_TOKEN = re.compile(r"^[0-9a-f]{32}$")


class RestoreError(Exception):
    """되살릴 수 없는 이유 — 그대로 화면에 보여 준다."""


# ── 올린 파일 ─────────────────────────────────────────────

def _upload_dir() -> Path:
    path = Path(tempfile.gettempdir()) / UPLOAD_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_upload(source: BinaryIO) -> str:
    """올린 ZIP 을 임시 폴더에 흘려 쓰고 표(token)를 돌려준다. 하루 지난 것 · 앞서 올린 것은 치운다(한 번에 하나)."""
    folder = _upload_dir()
    for stale in folder.glob("*.zip"):
        try:
            stale.unlink()
        except OSError:
            pass
    token = uuid.uuid4().hex
    target = folder / f"{token}.zip"
    with target.open("wb") as handle:
        shutil.copyfileobj(source, handle, length=1024 * 1024)
    return token


def upload_path(token: str) -> Path:
    if not _TOKEN.match(token or ""):
        raise RestoreError("올린 백업을 찾을 수 없습니다. 파일을 다시 골라 주세요.")
    path = _upload_dir() / f"{token}.zip"
    if not path.is_file():
        raise RestoreError("올린 백업을 찾을 수 없습니다(프로그램을 다시 켰거나 오래 지났습니다). 파일을 다시 골라 주세요.")
    return path


def discard_upload(token: str) -> None:
    try:
        upload_path(token).unlink()
    except (RestoreError, OSError):
        pass


# ── ZIP 살펴보기 ──────────────────────────────────────────

def _clean_name(raw: str) -> PurePosixPath | None:
    """ZIP 안 이름을 데이터 폴더 안의 상대 경로로. 위험한 이름이면 None."""
    name = raw.replace("\\", "/")
    if not name or name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        return None
    parts = [part for part in name.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        return None
    return PurePosixPath(*parts)


def _plan(archive: zipfile.ZipFile) -> tuple[list[tuple[zipfile.ZipInfo, PurePosixPath]], list[str], str]:
    """펼 항목 (ZipInfo, 데이터 폴더 안 경로) · 거부한 이름 · 벗겨 낸 머리 폴더.

    백업을 한 번 더 폴더째 묶었으면(`vault/projects/…`, `과제이력-전체백업-…/projects/…`) 그 한 겹은 벗긴다.
    """
    entries: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
    rejected: list[str] = []
    for info in archive.infolist():
        if info.is_dir():
            continue
        clean = _clean_name(info.filename)
        if clean is None:
            rejected.append(info.filename)
            continue
        entries.append((info, clean))
    tops = {path.parts[0] for _, path in entries}
    strip = ""
    if not tops & KNOWN_TOP and len(tops) == 1:
        only = next(iter(tops))
        inner = {path.parts[1] for _, path in entries if len(path.parts) > 1}
        if inner & KNOWN_TOP:
            strip = only
            entries = [(info, PurePosixPath(*path.parts[1:])) for info, path in entries if len(path.parts) > 1]
    entries = [(info, path) for info, path in entries if path.parts[0] not in SKIP_TOP]
    return entries, rejected, strip


def _count(names: list[PurePosixPath]) -> dict[str, int]:
    projects = {p.parts[1] for p in names if len(p.parts) == 3 and p.parts[0] == "projects" and p.parts[2] == "index.md"}
    intakes = {p.parts[1] for p in names if len(p.parts) == 3 and p.parts[0] == "intakes" and p.parts[2] == "request.md"}
    people = {p.parts[1].removesuffix(".md") for p in names
              if len(p.parts) >= 2 and p.parts[0] == "people" and not p.parts[1].startswith(".")
              and (len(p.parts) > 2 or p.parts[1].endswith(".md"))}
    assets = sum(1 for p in names if "assets" in p.parts[:-1])
    return {"projects": len(projects), "people": len(people), "intakes": len(intakes), "assets": assets}


def current_summary() -> dict[str, Any]:
    """지금 데이터 폴더 — 되살리면 바뀌는 것."""
    vault = get_settings().vault_dir
    names: list[PurePosixPath] = []
    for sub in ("projects", "people", "intakes"):
        base = vault / sub
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.is_file():
                names.append(PurePosixPath(path.relative_to(vault).as_posix()))
    counts = _count(names)
    counts["has_data"] = bool(names) or (vault / "settings.json").is_file()
    return counts


def inspect(path: Path, filename: str = "") -> dict[str, Any]:
    """[되살리기] 전에 보여 줄 것 — 무엇이 든 백업인가, 되살릴 수 있는가."""
    problems: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            entries, rejected, strip = _plan(archive)
            broken = archive.testzip() if path.stat().st_size < 200 * 1024 * 1024 else None
    except zipfile.BadZipFile:
        raise RestoreError("ZIP 파일이 아니거나 깨져 있습니다. 설정 → [전체 백업 내려받기]로 받은 파일인지 확인해 주세요.")
    names = [p for _, p in entries]
    tops = {p.parts[0] for p in names}
    if not tops & KNOWN_TOP:
        problems.append("이 도구의 백업이 아닙니다 — ZIP 맨 위에 projects · people · intakes 폴더나 settings.json 이 없습니다.")
    if broken:
        problems.append(f"ZIP 안의 파일이 깨져 있습니다: {broken}")
    if rejected:
        problems.append(f"데이터 폴더 밖을 가리키는 이름 {len(rejected)}개는 건너뜁니다: {', '.join(rejected[:3])}")
    stamp = re.search(r"(20\d{6})", filename or "")
    newest = max((info.date_time for info, _ in entries), default=None)
    date = (f"{stamp.group(1)[:4]}-{stamp.group(1)[4:6]}-{stamp.group(1)[6:]}" if stamp
            else (f"{newest[0]:04d}-{newest[1]:02d}-{newest[2]:02d}" if newest else None))
    summary = _count(names)
    return {
        "filename": filename,
        "date": date,
        "files": len(entries),
        "bytes": sum(info.file_size for info, _ in entries),
        "zip_bytes": path.stat().st_size,
        "settings": "settings.json" in tops,
        "with_assets": summary["assets"] > 0,
        "wrapped": strip or None,
        **summary,
        "ok": not any(p.startswith(("이 도구의 백업이 아닙니다", "ZIP 안의 파일이 깨져")) for p in problems),
        "problems": problems,
        "current": current_summary(),
    }


# ── 되살리기 ──────────────────────────────────────────────

def _safety_backup() -> str | None:
    """지금 데이터를 통째로(첨부 포함) 한 벌. 자동 백업 폴더 → 데이터 폴더 옆 → 임시 폴더 순으로 쓸 수 있는 곳에.

    자동 백업의 층 보관이 지우지 않도록 이름 머리를 다르게 둔다(`과제이력-되살리기전-`).
    """
    from . import settings as settings_service
    from .export import write_backup_all

    vault = get_settings().vault_dir
    candidates: list[Path] = []
    configured = str(settings_service.load().get("backup_dir") or "").strip()
    if configured and Path(configured).is_dir():
        candidates.append(Path(configured))
    candidates += [vault.parent, Path(tempfile.gettempdir())]
    name = f"{SAFETY_PREFIX}{datetime.now():%Y%m%d-%H%M%S}.zip"
    last_error: Exception | None = None
    for folder in candidates:
        target = folder / name
        part = target.with_name(target.name + ".part")
        try:
            write_backup_all(part, assets=True)
            part.replace(target)
            return str(target)
        except OSError as exc:
            last_error = exc
            part.unlink(missing_ok=True)
    raise RestoreError(f"지금 데이터를 먼저 백업하지 못해 되살리기를 멈췄습니다: {last_error}")


def _extract(path: Path, into: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        entries, _, _ = _plan(archive)
        for info, rel in entries:
            target = into.joinpath(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as handle:
                shutil.copyfileobj(source, handle, length=1024 * 1024)
            stamp = datetime(*info.date_time).timestamp() if info.date_time[0] >= 1980 else None
            if stamp:
                try:
                    os.utime(target, (stamp, stamp))
                except OSError:
                    pass


def _swap(vault: Path, new: Path, old: Path) -> None:
    """맨 윗단 항목을 맞바꾼다. 실패하면 되돌린다 — 지금 데이터는 그대로."""
    moved_out: list[str] = []
    moved_in: list[str] = []
    try:
        for item in sorted(vault.iterdir()):
            if item.name in KEEP_IN_PLACE:
                continue
            item.replace(old / item.name)
            moved_out.append(item.name)
        for item in sorted(new.iterdir()):
            item.replace(vault / item.name)
            moved_in.append(item.name)
    except OSError as exc:
        for name in moved_in:
            try:
                (vault / name).replace(new / name)
            except OSError:
                pass
        for name in moved_out:
            try:
                (old / name).replace(vault / name)
            except OSError:
                pass
        raise RestoreError(
            f"데이터 폴더의 항목을 바꾸지 못해 되돌렸습니다 — 지금 데이터는 그대로입니다. "
            f"다른 프로그램(탐색기 · 편집기)이 데이터 폴더의 파일을 열고 있지 않은지 확인해 주세요. ({exc})"
        ) from exc


def apply(conn: sqlite3.Connection, token: str) -> dict[str, Any]:
    """올린 백업으로 데이터 폴더를 바꾼다 — 먼저 지금 데이터를 백업하고, 다 푼 뒤 맞바꾸고, 색인을 다시 만든다."""
    from .. import readcache
    from ..db import reset_index
    from ..vault.indexer import reindex_all
    from . import backup as backup_service
    from . import settings as settings_service

    path = upload_path(token)
    report = inspect(path)
    if not report["ok"]:
        raise RestoreError(report["problems"][0])
    vault = get_settings().vault_dir
    with backup_service._run_lock:  # 자동 백업이 도중에 데이터 폴더를 읽지 않게
        safety = _safety_backup() if report["current"]["has_data"] else None
        work = vault / WORK_DIR
        shutil.rmtree(work, ignore_errors=True)
        new, old = work / "new", work / "old"
        new.mkdir(parents=True)
        old.mkdir(parents=True)
        try:
            _extract(path, new)
        except (OSError, zipfile.BadZipFile) as exc:
            shutil.rmtree(work, ignore_errors=True)
            raise RestoreError(f"백업을 풀지 못했습니다 — 지금 데이터는 그대로입니다. ({exc})") from exc
        _swap(vault, new, old)
        shutil.rmtree(work, ignore_errors=True)
    discard_upload(token)

    reset_index(conn)
    indexed, problems = reindex_all(conn)
    conn.commit()
    readcache.bump()

    backup_dir = str(settings_service.load().get("backup_dir") or "").strip()
    return {
        "projects": indexed,
        "people": report["people"],
        "intakes": report["intakes"],
        "files": report["files"],
        "problems": [{"path": item.rel_path, "reason": item.reason} for item in problems],
        "safety_backup": safety,
        "backup_dir_missing": backup_dir if backup_dir and not Path(backup_dir).is_dir() else None,
    }
