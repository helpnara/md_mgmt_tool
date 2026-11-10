"""전체 백업 내려받기 — 뒤에서 만들고 진행을 보인다 (TODO 266).

예전에는 [전체 백업 내려받기]가 링크 하나였다. 서버가 zip 을 **다 만든 뒤에야** 보내기 시작해서, 첨부가 GB 면
그동안 화면에 아무 변화가 없었다(사용자 2026-11-10). 이제 두 단계:

1. **만들기** — 작업 하나가 뒤에서 zip 을 만든다(`vault/.work/backup/` — 267). 화면은 1초마다 파일 n / N · 크기 · 남은 시간을 본다.
   한 번에 하나, [그만두기], 다른 화면에 갔다 와도 이어 보인다(서버를 다시 켜면 사라진다).
2. **받기** — 다 만들면 화면이 내려받기를 시작하고(브라우저가 받기 진행을 보인다), 다 보내면 서버의 파일을 지운다.
   받지 않고 두면 한 시간 뒤 지운다.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import export as export_service
from . import workspace

KEEP_DONE_SECONDS = 3600


class Cancelled(Exception):
    pass


@dataclass
class Job:
    id: str
    assets: bool
    files_total: int
    bytes_total: int
    state: str = "running"            # running · done · error · cancelled
    files_done: int = 0
    bytes_done: int = 0
    started: float = field(default_factory=time.time)
    finished: float | None = None
    error: str = ""
    path: Path | None = None
    filename: str = ""
    size: int = 0
    cancel: bool = False

    def as_dict(self) -> dict[str, Any]:
        now = self.finished or time.time()
        elapsed = max(0.0, now - self.started)
        eta = None
        if self.state == "running" and self.bytes_done > 0 and self.bytes_total > self.bytes_done:
            eta = elapsed * (self.bytes_total - self.bytes_done) / self.bytes_done
        return {"id": self.id, "assets": self.assets, "state": self.state, "files_done": self.files_done,
                "files_total": self.files_total, "bytes_done": self.bytes_done, "bytes_total": self.bytes_total,
                "elapsed": round(elapsed, 1), "eta": None if eta is None else round(eta, 1), "error": self.error,
                "filename": self.filename, "size": self.size}


_lock = threading.Lock()
_current: Job | None = None


def estimate(assets: bool) -> dict[str, Any]:
    """담을 파일 수 · 크기(문서 · 첨부) — 시작 전에 보인다. 압축 전 크기라 zip 은 보통 이보다 작다."""
    from ..config import get_settings

    vault = get_settings().vault_dir
    docs = attach = files = 0
    for path, name in export_service._vault_files(vault, True):
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if export_service.ASSETS_DIR in name.split("/")[:-1]:
            if not assets:
                continue
            attach += size
        else:
            docs += size
        files += 1
    return {"files": files, "bytes": docs + attach, "docs_bytes": docs, "assets_bytes": attach,
            "free_bytes": workspace.free_bytes(get_settings().vault_dir), "work_dir": str(workspace.work_dir())}


def _expire() -> None:
    global _current
    job = _current
    if job and job.state != "running" and job.finished and time.time() - job.finished > KEEP_DONE_SECONDS:
        if job.path:
            job.path.unlink(missing_ok=True)
        _current = None


def current() -> Job | None:
    with _lock:
        _expire()
        return _current


def start(assets: bool) -> Job:
    """새 작업 — 만드는 중인 것이 있으면 그것을 돌려준다(한 번에 하나). 자리가 모자라면 SpaceError."""
    global _current
    with _lock:
        _expire()
        if _current and _current.state == "running":
            return _current
        if _current and _current.path:
            _current.path.unlink(missing_ok=True)
        size = estimate(assets)
        folder = workspace.work_dir("backup")
        workspace.ensure_space(folder, size["bytes"], "전체 백업 만들기")
        job = Job(id=uuid.uuid4().hex, assets=assets, files_total=size["files"], bytes_total=size["bytes"])
        job.filename = export_service.backup_all_filename(assets)
        job.path = folder / f"{job.id}.zip.part"
        _current = job
    threading.Thread(target=_run, args=(job,), daemon=True).start()
    return job


def _run(job: Job) -> None:
    def progress(files_done: int, files_total: int, bytes_done: int, bytes_total: int) -> bool:
        job.files_done, job.files_total = files_done, files_total
        job.bytes_done, job.bytes_total = bytes_done, max(bytes_total, bytes_done)
        return not job.cancel

    assert job.path is not None
    try:
        export_service.write_backup_all(job.path, assets=job.assets, progress=progress)
        done = job.path.with_name(f"{job.id}.zip")
        job.path.replace(done)
        job.path = done
        job.size = done.stat().st_size
        job.state = "done"
    except export_service.BackupCancelled:
        job.state = "cancelled"
        job.path.unlink(missing_ok=True)
    except OSError as exc:
        job.state = "error"
        job.error = str(workspace.space_error_from(exc, job.path.parent, "전체 백업")) if exc.errno == 28 else f"백업을 만들지 못했습니다: {exc}"
        job.path.unlink(missing_ok=True)
    except Exception as exc:  # noqa: BLE001 — 작업이 조용히 멈추지 않게 이유를 남긴다
        job.state = "error"
        job.error = f"백업을 만들지 못했습니다: {exc}"
        job.path.unlink(missing_ok=True)
    finally:
        job.finished = time.time()


def get(job_id: str) -> Job:
    job = current()
    if not job or job.id != job_id:
        raise KeyError(job_id)
    return job


def cancel(job_id: str) -> Job:
    job = get(job_id)
    job.cancel = True
    return job


def take(job_id: str) -> Job:
    """내려보낼 파일 — 다 만든 작업만. 보낸 뒤 지우는 것은 부르는 쪽(`release`)."""
    job = get(job_id)
    if job.state != "done" or not job.path or not job.path.is_file():
        raise KeyError(job_id)
    return job


def release(job_id: str) -> None:
    global _current
    with _lock:
        if _current and _current.id == job_id:
            if _current.path:
                _current.path.unlink(missing_ok=True)
            _current = None


def reset_for_tests() -> None:
    global _current
    with _lock:
        _current = None
