"""지금 도는 오래 걸리는 일 — 화면이 진행을 볼 수 있게 (TODO 268).

데이터가 크면(첨부 GB · 네트워크 드라이브) 요청 하나가 몇 분 걸리는 일이 있다 — [다시 읽기](색인 다시 만들기) · [지금 백업] ·
삭제 보관함 [되돌리기] · 번호 체계 [바꾸기] · 첨부 링크 [고치기] · 과제 [내보내기]. 예전에는 단추가 꺼지기만 하고 화면이 가만히 있었다.

이제 그 일을 `track(라벨, key)` 로 감싸고, 안에서 `report(n, N, 크기, 전체 크기, 단계)` 를 부른다. 화면은 요청을 보낸 뒤
`GET /api/running` 을 1초마다 보아 "과제 읽기 12 / 80 · 지난 시간 · 남은 시간" 을 보인다. 끝난 일은 1분 남겨 둔다
(내보내기처럼 링크로 받는 일은 화면이 끝났는지를 여기서 안다).

`report` 는 `track` 밖(켤 때의 색인 등)에서 부르면 아무것도 하지 않는다 — 부르는 쪽이 신경 쓰지 않아도 된다.
"""
from __future__ import annotations

import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

KEEP_SECONDS = 60


@dataclass
class Task:
    id: str
    label: str
    key: str
    thread: int
    phase: str = ""
    done: int = 0
    total: int = 0
    bytes_done: int = 0
    bytes_total: int = 0
    state: str = "running"          # running · done · error
    started: float = field(default_factory=time.time)
    phase_started: float = field(default_factory=time.time)
    finished: float | None = None

    def as_dict(self) -> dict[str, Any]:
        now = self.finished or time.time()
        spent = max(0.0, now - self.phase_started)
        eta = None
        if self.state == "running":
            if self.bytes_total and 0 < self.bytes_done < self.bytes_total:
                eta = spent * (self.bytes_total - self.bytes_done) / self.bytes_done
            elif self.total and 0 < self.done < self.total:
                eta = spent * (self.total - self.done) / self.done
        return {"id": self.id, "label": self.label, "key": self.key, "phase": self.phase, "state": self.state,
                "done": self.done, "total": self.total, "bytes_done": self.bytes_done, "bytes_total": self.bytes_total,
                "elapsed": round(max(0.0, now - self.started), 1), "eta": None if eta is None else round(eta, 1)}


_lock = threading.Lock()
_tasks: dict[str, Task] = {}
_by_thread: dict[int, list[Task]] = {}


def _sweep() -> None:
    now = time.time()
    for task_id in [t.id for t in _tasks.values() if t.finished and now - t.finished > KEEP_SECONDS]:
        _tasks.pop(task_id, None)


@contextmanager
def track(label: str, key: str = "") -> Iterator[Task]:
    """이 스레드에서 도는 일 하나. 안에서 부르는 `report` 가 이 일의 진행이 된다(겹치면 가장 안쪽)."""
    thread = threading.get_ident()
    task = Task(id=uuid.uuid4().hex, label=label, key=key or "", thread=thread)
    with _lock:
        _sweep()
        _tasks[task.id] = task
        _by_thread.setdefault(thread, []).append(task)
    try:
        yield task
        task.state = "done"
    except BaseException:
        task.state = "error"
        raise
    finally:
        task.finished = time.time()
        with _lock:
            stack = _by_thread.get(thread, [])
            if task in stack:
                stack.remove(task)
            if not stack:
                _by_thread.pop(thread, None)


def report(done: int, total: int, bytes_done: int = 0, bytes_total: int = 0, phase: str | None = None) -> bool:
    """지금 스레드의 일에 진행을 적는다. 늘 True(멈추지 않는다) — `write_backup_all(progress=)` 에 그대로 넘길 수 있다."""
    stack = _by_thread.get(threading.get_ident())
    if not stack:
        return True
    task = stack[-1]
    if phase is not None and phase != task.phase:
        task.phase = phase
        task.phase_started = time.time()
    task.done, task.total = done, total
    task.bytes_done, task.bytes_total = bytes_done, max(bytes_total, bytes_done)
    return True


def phase(name: str):
    """단계 이름을 붙인 `report` — `progress` 칸에 넘길 함수."""
    def progress(done: int, total: int, bytes_done: int = 0, bytes_total: int = 0) -> bool:
        return report(done, total, bytes_done, bytes_total, phase=name)
    return progress


def listing(key: str = "") -> list[dict[str, Any]]:
    with _lock:
        _sweep()
        tasks = sorted(_tasks.values(), key=lambda t: t.started)
    return [t.as_dict() for t in tasks if not key or t.key == key]


def reset_for_tests() -> None:
    with _lock:
        _tasks.clear()
        _by_thread.clear()
