"""작업 파일 자리 · 남은 자리 (TODO 267).

백업 zip · 되살리기로 올린 zip 같은 **큰 작업 파일**은 서버 PC 의 임시 폴더(`%TEMP%` — 보통 C:)가 아니라
**데이터 폴더와 같은 드라이브**의 `vault/.work/` 에 둔다. 데이터를 네트워크 드라이브에 두면 C: 가 모자라도
"No space left on device" 가 났다(사용자 2026-11-10). 이 폴더는 백업에 넣지 않고, 켤 때 남은 것을 치운다.

쓰기 전에 **남은 자리를 먼저 본다** — 모자라면 어느 드라이브(경로)에 얼마가 더 필요한지 한글로 말한다(507).
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from ..config import get_settings

WORK_DIR = ".work"
MARGIN = 64 * 1024 * 1024          # 남겨 둘 자리 — 다른 저장이 막히지 않게
STALE_SECONDS = 24 * 3600


class SpaceError(Exception):
    """자리가 모자란다 — 끝점이 507 로 돌린다. 말은 그대로 화면에 보인다."""


def work_dir(sub: str = "") -> Path:
    path = get_settings().vault_dir / WORK_DIR
    if sub:
        path = path / sub
    path.mkdir(parents=True, exist_ok=True)
    return path


def human(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit in ("B", "KB") else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def free_bytes(folder: Path) -> int | None:
    try:
        return shutil.disk_usage(folder).free
    except OSError:
        return None


def ensure_space(folder: Path, needed: int, what: str) -> None:
    """`folder` 의 드라이브에 `needed` + 여유가 남았나. 모르면(네트워크 드라이브가 답하지 않음) 막지 않는다."""
    free = free_bytes(folder)
    if free is None:
        return
    if free < needed + MARGIN:
        raise SpaceError(f"{what}에 쓸 자리가 모자랍니다 — {folder} 에 {human(needed)} 가 필요한데 남은 자리는 {human(free)} 입니다. "
                         "그 드라이브를 비우거나, 첨부를 뺀 백업을 고르세요.")


def space_error_from(exc: OSError, folder: Path, what: str) -> SpaceError:
    """쓰다가 난 ENOSPC 를 한글로 — 어느 자리에서 모자랐는지."""
    free = free_bytes(folder)
    left = f"(남은 자리 {human(free)})" if free is not None else ""
    return SpaceError(f"{what}을(를) 쓰다가 자리가 모자랐습니다 — {folder} {left}. 그 드라이브를 비운 뒤 다시 해 주세요.")


def clean_stale(everything: bool = False) -> int:
    """켤 때 — 지난 실행이 남긴 작업 파일을 치운다(`everything`), 아니면 하루 지난 것만."""
    root = get_settings().vault_dir / WORK_DIR
    if not root.is_dir():
        return 0
    removed = 0
    now = time.time()
    for path in sorted(root.rglob("*"), reverse=True):
        try:
            if path.is_file() and (everything or now - path.stat().st_mtime > STALE_SECONDS):
                path.unlink()
                removed += 1
            elif path.is_dir() and not any(path.iterdir()):
                path.rmdir()
        except OSError:
            continue
    return removed


def status() -> dict:
    """설정 → 점검의 한 줄 — 작업 파일 자리 · 남은 자리."""
    folder = get_settings().vault_dir
    free = free_bytes(folder)
    return {"work_dir": str(folder / WORK_DIR), "free_bytes": free}
