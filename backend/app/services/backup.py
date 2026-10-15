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
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, NamedTuple

from ..config import get_settings

PREFIX = "과제이력-백업-"
STAMP = "%Y%m%d-%H%M"
STATE_FILE = "backup-state.json"
# 화면에 세우는 줄 수. 나머지는 접어 둔다 (TODO 119).
RECENT_LIMIT = 5
# 쓰는 중인 백업의 꼬리표 (TODO 202 ⑤). 다 쓴 뒤에만 `.zip` 으로 이름을 바꾼다 — 디스크가 차거나
# 네트워크가 끊겨 중간에 멈추면 잘린 zip 이 `.zip` 이름으로 남아, `due()` 가 24시간 다시 안 하고
# 회전이 멀쩡한 옛 백업을 밀어냈다.
PART_SUFFIX = ".part"
# 수동 백업(설정 화면)과 자동 백업이 겹치지 않게 (TODO 202).
_run_lock = threading.Lock()


class Keep(NamedTuple):
    """몇 벌을 남기나 — 일 · 주 · 월 (TODO 119)."""

    daily: int
    weekly: int
    monthly: int

    @property
    def total(self) -> int:
        return self.daily + self.weekly + self.monthly


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
    path = _state_path()
    tmp = path.with_name(path.name + ".tmp")
    try:
        get_settings().logs_dir.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)  # TODO 202 — 쓰다 멈춰도 지난 기록은 남는다
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _fail(reason: str, message: str) -> None:
    _write_state({"at": datetime.now().isoformat(timespec="seconds"), "ok": False,
                  "reason": reason, "error": message})


def _files(directory: Path) -> list[Path]:
    """이 도구가 만든 백업만. 폴더에 다른 파일이 있어도 건드리지 않는다.

    **다 쓴 `.zip` 만** 센다 — 쓰는 중이거나 쓰다 멈춘 `.zip.part` 는 백업이 아니다 (TODO 202 ⑤).
    """
    if not directory.is_dir():
        return []
    return sorted(
        (item for item in directory.glob(f"{PREFIX}*.zip")
         if item.is_file() and item.name.endswith(".zip")),
        key=lambda item: item.name,
    )


def _settings_values() -> tuple[str, Keep, int]:
    from . import settings as settings_service

    data = settings_service.load()
    return (
        str(data.get("backup_dir") or "").strip(),
        Keep(
            daily=max(1, int(data.get("backup_keep") or 7)),
            weekly=max(0, int(data.get("backup_keep_weekly") or 0)),
            monthly=max(0, int(data.get("backup_keep_monthly") or 0)),
        ),
        int(data.get("backup_every_hours") or 24),
    )


def _stamp_of(path: Path) -> datetime | None:
    """파일 이름에 박힌 시각. 이름이 곧 시각이라 파일 시각보다 믿을 만하다."""
    text = path.name[len(PREFIX):].split(".")[0]
    try:
        return datetime.strptime(text[: len(("20260916-1230"))], STAMP)
    except ValueError:
        return None


def keep_set(files: list[Path], keep: Keep) -> set[Path]:
    """남길 파일을 고른다 — 일 · 주 · 월 세 층 (TODO 119).

    **하루에 한 벌**만 후보로 삼는다. 같은 날 여러 번 백업하면 그날의 마지막 것만 남는다 —
    "하루 한 벌" 이라야 개수를 보고 기간을 셀 수 있고, 손으로 여러 번 돌린 날이 주·월 자리를
    차지해 오래된 백업을 밀어내는 일도 없다.

    그다음 최근 것부터 층을 채운다 — 일 `daily` 벌, 그 앞은 주마다 한 벌 `weekly` 주,
    그 앞은 달마다 한 벌 `monthly` 달.

    이름을 읽지 못하는 파일(사람이 손으로 바꾼 것 등)은 **건드리지 않는다.**
    지우는 쪽이 조심스러워야 한다.
    """
    keeping: set[Path] = set()
    candidates: list[tuple[datetime, Path]] = []
    seen_day: set[str] = set()

    for path in reversed(files):  # 최근 것부터
        when = _stamp_of(path)
        if when is None:
            keeping.add(path)  # 우리가 만든 이름이 아니다 — 판단하지 않는다
            continue
        day = when.date().isoformat()
        if day in seen_day:
            continue  # 같은 날 더 이른 백업
        seen_day.add(day)
        candidates.append((when, path))

    seen_week: set[tuple[int, int]] = set()
    seen_month: set[tuple[int, int]] = set()
    daily_left = keep.daily
    for when, path in candidates:
        if daily_left > 0:
            daily_left -= 1
            keeping.add(path)
            continue
        week = when.isocalendar()[:2]
        if len(seen_week) < keep.weekly and week not in seen_week:
            seen_week.add(week)
            keeping.add(path)
            continue
        month = (when.year, when.month)
        if len(seen_month) < keep.monthly and month not in seen_month:
            seen_month.add(month)
            keeping.add(path)
    return keeping


def _skip_assets() -> bool:
    """설정의 「첨부 제외 백업」 (TODO 197 ③). 켜면 자동 · 수동 백업이 `assets/` 를 뺀다."""
    from . import settings as settings_service

    try:
        return bool(settings_service.load().get("backup_skip_assets", False))
    except Exception:  # 설정을 못 읽어도 백업은 한다 — 통째로가 안전한 쪽이다
        return False


def run(conn: sqlite3.Connection, reason: str = "manual") -> dict[str, Any]:
    """지금 한 벌 내보낸다."""
    with _run_lock:
        return _run_locked(reason)


def _run_locked(reason: str) -> dict[str, Any]:
    from .export import write_backup_all

    directory, keep, _ = _settings_values()
    if not directory:
        raise BackupError("백업 폴더가 정해져 있지 않습니다. 설정에서 먼저 지정해 주세요.")
    target_dir = Path(directory)
    if not target_dir.is_dir():
        message = f"백업 폴더를 찾을 수 없습니다: {directory}"
        _fail(reason, message)
        raise BackupError(message)

    # 지난번에 쓰다 멈춘 조각은 치운다 — 잠금 안이라 지금 쓰는 것은 없다 (TODO 202 ⑤)
    for stale in target_dir.glob(f"{PREFIX}*.zip{PART_SUFFIX}"):
        try:
            stale.unlink()
        except OSError:
            pass

    skip_assets = _skip_assets()
    target = target_dir / f"{PREFIX}{datetime.now().strftime(STAMP)}.zip"
    counter = 2
    while target.exists():
        target = target_dir / f"{PREFIX}{datetime.now().strftime(STAMP)}-{counter}.zip"
        counter += 1
    part = target.with_name(target.name + PART_SUFFIX)

    # `.part` 에 흘려 쓰고(메모리에 올리지 않는다 — TODO 202 ⑬) 다 쓴 뒤에만 `.zip` 으로 바꾼다 (⑤).
    # 어떤 예외든(MemoryError 포함) 조각을 지우고 실패를 기록한다 — 설정 화면이 그것을 보여 준다.
    try:
        write_backup_all(part, assets=not skip_assets)
        os.replace(part, target)
    except Exception as exc:
        _discard(part)
        if isinstance(exc, OSError):
            message = f"백업을 쓰지 못했습니다: {exc}"
        else:
            message = f"백업을 만들지 못했습니다 ({type(exc).__name__}): {exc}".rstrip(": ")
        _fail(reason, message)
        raise BackupError(message) from exc
    except BaseException:
        _discard(part)
        raise
    size = target.stat().st_size

    # 층을 나눠 남기고 나머지를 버린다 (TODO 119).
    files = _files(target_dir)
    keeping = keep_set(files, keep)
    for stale in files:
        if stale not in keeping:
            stale.unlink(missing_ok=True)

    state: dict[str, Any] = {"at": datetime.now().isoformat(timespec="seconds"), "ok": True,
                             "reason": reason, "file": target.name, "bytes": size}
    if skip_assets:
        state["skip_assets"] = True
    _write_state(state)
    return {"file": target.name, "bytes": size, "directory": str(target_dir), "skip_assets": skip_assets}


def _discard(part: Path) -> None:
    try:
        part.unlink(missing_ok=True)
    except OSError:
        pass


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
    except BackupError:
        return None  # run 이 이미 실패를 기록했다
    except Exception as exc:
        # 어떤 예외든 설정 화면에 남긴다 (TODO 202 ⑬) — 예전에는 루프가 조용히 삼켜 실패 기록조차 없었다.
        _fail("auto", f"백업을 만들지 못했습니다 ({type(exc).__name__}): {exc}".rstrip(": "))
        return None


def status() -> dict[str, Any]:
    """설정 화면에 세우는 현황."""
    directory, keep, every_hours = _settings_values()
    files = _files(Path(directory)) if directory else []

    # **총 용량은 전체 기준이다** (TODO 119). 예전에는 화면에 세우는 몇 개만 더해서,
    # 파일이 그보다 많으면 실제보다 작게 보였다 (TODO 82·103-B 와 같은 부류).
    total_bytes = 0
    for item in files:
        try:
            total_bytes += item.stat().st_size
        except OSError:
            continue
    oldest = None
    if files:
        when = _stamp_of(files[0])
        oldest = (when.date().isoformat() if when else None)

    items = []
    for item in reversed(files[-RECENT_LIMIT:]):
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
        "keep": keep.total,
        "keep_daily": keep.daily,
        "keep_weekly": keep.weekly,
        "keep_monthly": keep.monthly,
        "every_hours": every_hours,
        # 첨부 제외 백업 (TODO 197 ③)
        "skip_assets": _skip_assets(),
        "count": len(files),
        "total_bytes": total_bytes,
        # 되돌릴 수 있는 범위 — 개수보다 이 날짜가 백업의 뜻이다.
        "oldest": oldest,
        "recent": items,
        "last": state or None,
        "reachable": bool(directory) and Path(directory).is_dir(),
    }
