"""자동 백업 — 바깥쪽 안전망.

이전 버전 보관(`.versions`)은 **잘못 고쳤을 때**를 막아 준다. 그런데 그것도 vault 안에
있어서, **PC가 고장 나거나 폴더가 통째로 사라지면 함께 없어진다.** 그래서 vault 밖으로
한 벌을 내보내는 길이 따로 있어야 한다.

방식은 단순하게 잡았다 (2026-09-04 사용자 결정) — **백업 폴더를 설정에 정해 두면
그리로 zip 을 떨어뜨린다.** 그 폴더를 네트워크 드라이브나 외장 디스크로 잡으면
곧바로 "다른 곳에 한 벌"이 된다.

마지막 백업 시각은 따로 적지 않고 **폴더에 있는 파일에서 읽는다.** 상태 파일을 따로
두면 그것과 실제가 어긋날 수 있고, 백업은 파일이 있느냐가 전부이기 때문이다.
다만 **실패**는 파일이 안 생기므로 그것만 기록한다.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import get_settings

PREFIX = "과제이력-백업-"
STAMP = "%Y%m%d-%H%M"
STATE_FILE = "backup-state.json"


class BackupError(Exception):
    """백업할 수 없는 이유 — 그대로 화면에 보여 준다."""


def validate_dir(raw: str) -> str:
    """백업 폴더를 검사한다. 비우면 자동 백업을 끈다는 뜻이다."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise BackupError("백업 폴더는 전체 경로로 적어 주세요. (예: D:\\백업\\과제이력)")
    if not path.exists():
        raise BackupError(f"그런 폴더가 없습니다: {path}")
    if not path.is_dir():
        raise BackupError("폴더가 아니라 파일을 가리키고 있습니다.")

    # vault 안에 백업하면 백업이 다음 백업에 담겨 눈덩이처럼 커진다.
    vault = get_settings().vault_dir.resolve()
    resolved = path.resolve()
    if resolved == vault or vault in resolved.parents:
        raise BackupError(
            "백업 폴더를 데이터 폴더 안에 둘 수 없습니다. "
            "백업이 다음 백업에 담겨 계속 커집니다. 다른 디스크나 공유 폴더를 지정해 주세요."
        )
    try:
        probe = resolved / ".백업쓰기확인"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        raise BackupError(f"그 폴더에 쓸 수 없습니다: {exc}") from exc
    return str(resolved)


def _state_path() -> Path:
    return get_settings().logs_dir / STATE_FILE


def _read_state() -> dict[str, Any]:
    try:
        return json.loads(_state_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_state(data: dict[str, Any]) -> None:
    try:
        get_settings().logs_dir.mkdir(parents=True, exist_ok=True)
        _state_path().write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _files(directory: Path) -> list[Path]:
    """이 도구가 만든 백업만. 폴더에 다른 파일이 있어도 건드리지 않는다."""
    if not directory.is_dir():
        return []
    return sorted(
        (item for item in directory.glob(f"{PREFIX}*.zip") if item.is_file()),
        key=lambda item: item.name,
    )


def _settings_values() -> tuple[str, int, int]:
    from . import settings as settings_service

    data = settings_service.load()
    return (
        str(data.get("backup_dir") or "").strip(),
        int(data.get("backup_keep") or 10),
        int(data.get("backup_every_hours") or 24),
    )


def run(conn: sqlite3.Connection, reason: str = "manual") -> dict[str, Any]:
    """지금 한 벌 내보낸다."""
    from .export import backup_all

    directory, keep, _ = _settings_values()
    if not directory:
        raise BackupError("백업 폴더가 정해져 있지 않습니다. 설정에서 먼저 지정해 주세요.")
    target_dir = Path(directory)
    if not target_dir.is_dir():
        message = f"백업 폴더를 찾을 수 없습니다: {directory}"
        _write_state({"at": datetime.now().isoformat(timespec="seconds"), "ok": False,
                      "reason": reason, "error": message})
        raise BackupError(message)

    _, content = backup_all(conn)
    target = target_dir / f"{PREFIX}{datetime.now().strftime(STAMP)}.zip"
    counter = 2
    while target.exists():
        target = target_dir / f"{PREFIX}{datetime.now().strftime(STAMP)}-{counter}.zip"
        counter += 1
    try:
        target.write_bytes(content)
    except OSError as exc:
        message = f"백업을 쓰지 못했습니다: {exc}"
        _write_state({"at": datetime.now().isoformat(timespec="seconds"), "ok": False,
                      "reason": reason, "error": message})
        raise BackupError(message) from exc

    # 오래된 것부터 버린다. 최근 것을 남기는 편이 언제나 쓸모 있다.
    for stale in _files(target_dir)[:-keep] if keep > 0 else []:
        stale.unlink(missing_ok=True)

    _write_state({"at": datetime.now().isoformat(timespec="seconds"), "ok": True,
                  "reason": reason, "file": target.name, "bytes": len(content)})
    return {"file": target.name, "bytes": len(content), "directory": str(target_dir)}


def due(now: datetime | None = None) -> bool:
    """지금 백업할 때가 됐나. 마지막 백업 **파일**의 시각을 기준으로 본다."""
    directory, _, every_hours = _settings_values()
    if not directory or every_hours <= 0:
        return False
    files = _files(Path(directory))
    if not files:
        return True  # 한 번도 안 했다
    try:
        last = datetime.fromtimestamp(files[-1].stat().st_mtime)
    except OSError:
        return True
    return (now or datetime.now()) - last >= _hours(every_hours)


def _hours(count: int):
    from datetime import timedelta

    return timedelta(hours=count)


def maybe_run(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """때가 됐으면 백업한다. **실패해도 프로그램을 멈추지 않는다.**"""
    try:
        if not due():
            return None
        return run(conn, reason="auto")
    except (BackupError, OSError):
        return None


def status() -> dict[str, Any]:
    """설정 화면에 세우는 현황."""
    directory, keep, every_hours = _settings_values()
    files = _files(Path(directory)) if directory else []
    items = []
    for item in reversed(files[-10:]):
        try:
            stat = item.stat()
        except OSError:
            continue
        items.append(
            {
                "name": item.name,
                "size_bytes": stat.st_size,
                "at": datetime.fromtimestamp(stat.st_mtime).isoformat(sep=" ", timespec="seconds"),
            }
        )
    state = _read_state()
    return {
        "directory": directory,
        "enabled": bool(directory),
        "keep": keep,
        "every_hours": every_hours,
        "count": len(files),
        "total_bytes": sum(item["size_bytes"] for item in items),
        "recent": items,
        "last": state or None,
        "reachable": bool(directory) and Path(directory).is_dir(),
    }
