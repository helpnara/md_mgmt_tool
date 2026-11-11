"""백업에서 되살리기 — 뒤에서 하고 단계별 진행을 보인다 (TODO 268).

예전에는 [되살리기]가 요청 하나였다. 첨부가 GB 면 ① 지금 데이터 먼저 백업 ② 백업 풀기 ③ 맞바꾸기 ④ 색인 다시 만들기가
끝날 때까지 화면에 "되살리는 중…" 한 줄만 있었다(사용자 2026-11-11 — v58 7번에서 막힘). 이제 전체 백업(266)과 같은 길:

* 작업 하나가 뒤에서 돌고, 화면은 1초마다 **지금 단계 · 파일 n / N · 크기 · 지난 시간 · 남은 시간**을 본다.
* 한 번에 하나. 다른 화면에 갔다 와도 이어 보인다(서버를 다시 켜면 사라진다).
* [그만두기]는 **바꾸기 전**(먼저 백업 · 풀기)에만 — 지금 데이터는 그대로, 만들던 파일은 지운다.
* 도는 동안 다른 저장은 기다린다(쓰기 차례 — `deps._write_lock`).
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from . import restore as restore_service

KEEP_DONE_SECONDS = 3600
# 단계 — 화면이 이 순서로 줄을 세운다
STAGES = ("check", "safety", "extract", "swap", "index")
CANCELLABLE = {"check", "safety", "extract"}


@dataclass
class Job:
    id: str
    token: str
    state: str = "running"            # running · done · error · cancelled
    stage: str = "check"
    stages_done: list[str] = field(default_factory=list)
    files_done: int = 0
    files_total: int = 0
    bytes_done: int = 0
    bytes_total: int = 0
    started: float = field(default_factory=time.time)
    stage_started: float = field(default_factory=time.time)
    finished: float | None = None
    error: str = ""
    result: dict[str, Any] | None = None
    cancel: bool = False

    def as_dict(self) -> dict[str, Any]:
        now = self.finished or time.time()
        stage_elapsed = max(0.0, now - self.stage_started)
        eta = None
        if self.state == "running":
            if self.bytes_total and 0 < self.bytes_done < self.bytes_total:
                eta = stage_elapsed * (self.bytes_total - self.bytes_done) / self.bytes_done
            elif not self.bytes_total and self.files_total and 0 < self.files_done < self.files_total:
                eta = stage_elapsed * (self.files_total - self.files_done) / self.files_done
        return {
            "id": self.id, "state": self.state, "stage": self.stage, "stages": list(STAGES),
            "stages_done": list(self.stages_done), "cancellable": self.state == "running" and self.stage in CANCELLABLE,
            "files_done": self.files_done, "files_total": self.files_total,
            "bytes_done": self.bytes_done, "bytes_total": self.bytes_total,
            "elapsed": round(max(0.0, now - self.started), 1), "eta": None if eta is None else round(eta, 1),
            "error": self.error, "result": self.result,
        }


_lock = threading.Lock()
_current: Job | None = None


def _expire() -> None:
    global _current
    job = _current
    if job and job.state != "running" and job.finished and time.time() - job.finished > KEEP_DONE_SECONDS:
        _current = None


def current() -> Job | None:
    with _lock:
        _expire()
        return _current


def start(token: str) -> Job:
    """새 작업 — 도는 것이 있으면 그것을 돌려준다(한 번에 하나). 올린 파일이 없으면 RestoreError."""
    global _current
    restore_service.upload_path(token)          # 없는 표면 여기서 바로 알린다
    with _lock:
        _expire()
        if _current and _current.state == "running":
            return _current
        job = Job(id=uuid.uuid4().hex, token=token)
        _current = job
    threading.Thread(target=_run, args=(job,), daemon=True).start()
    return job


def _run(job: Job) -> None:
    from .. import deps
    from ..db import connect

    def stage(name: str):
        if job.stage != name:
            if job.stage not in job.stages_done:
                job.stages_done.append(job.stage)
            job.stage = name
            job.stage_started = time.time()
            job.files_done = job.files_total = job.bytes_done = job.bytes_total = 0
        if name in CANCELLABLE and job.cancel:
            raise restore_service.Cancelled()

        def progress(files_done: int, files_total: int, bytes_done: int, bytes_total: int) -> bool:
            job.files_done, job.files_total = files_done, files_total
            job.bytes_done, job.bytes_total = bytes_done, max(bytes_total, bytes_done)
            return not (job.cancel and job.stage in CANCELLABLE)

        return progress

    # 다른 저장은 끝나기를 기다린다 — 되살리는 사이에 과제를 만들면 바꾸기 · 색인에서 사라진다
    deps._write_lock.acquire()
    conn = None
    try:
        conn = connect()
        job.result = restore_service.apply(conn, job.token, stage=stage)
        job.stages_done = list(STAGES)
        job.state = "done"
    except restore_service.Cancelled:
        job.state = "cancelled"
    except restore_service.RestoreError as exc:
        job.state = "error"
        job.error = str(exc)
    except Exception as exc:  # noqa: BLE001 — 작업이 조용히 멈추지 않게 이유를 남긴다
        job.state = "error"
        job.error = f"되살리지 못했습니다: {exc}"
    finally:
        if conn is not None:
            conn.close()
        deps._write_lock.release()
        job.finished = time.time()


def get(job_id: str) -> Job:
    job = current()
    if not job or job.id != job_id:
        raise KeyError(job_id)
    return job


def cancel(job_id: str) -> Job:
    job = get(job_id)
    if job.state == "running" and job.stage in CANCELLABLE:
        job.cancel = True
    return job


def reset_for_tests() -> None:
    global _current
    with _lock:
        _current = None
