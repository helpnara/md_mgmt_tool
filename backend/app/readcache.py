"""무거운 읽기의 답을 잠깐 나눠 쓴다 (TODO 190).

열 사람이 같은 순간 첫 화면을 열면 홈 · 대시보드 · 과제목록을 **열 번** 계산했다 — 답은 열 번 다 같은데. 한 프로세스에서는 그 계산이
GIL 을 두고 줄을 서서, 과제마다 묻던 질의를 묶은 뒤에도 10명 p95 가 3초였다. 여기서는 같은 요청의 답을 **한 번 계산해 모두에게** 준다.

* 무엇을: 목록 · 집계 끝점(`CACHEABLE`) 의 GET. 과제 하나 · 기록 하나처럼 가벼운 것은 그냥 계산한다.
* 언제까지: **쓰기가 한 번이라도 지나가면 전부 버린다**(미들웨어가 쓰기 요청이 끝날 때 판을 올린다) — 그래서 "저장했는데 홈이 옛날" 은 없다.
  오늘 날짜에 기대는 값(마감 임박 · 경과일)을 위해 **5초**도 넘기지 않는다.
* 열쇠: 경로 + 물음표 뒤 + 읽기 전용인가(바깥에는 다른 답을 주는 끝점이 있다 — meta · 팀원역량 요약).
"""
from __future__ import annotations

import threading
import time

CACHEABLE = frozenset({
    "/api/home", "/api/dashboard", "/api/projects", "/api/report-candidates", "/api/meta", "/api/roadmap",
    "/api/activities/summary", "/api/intakes", "/api/reports",
})
TTL_SECONDS = 5.0

_lock = threading.Lock()
_version = 0
_entries: dict[tuple, tuple[int, float, int, bytes, dict[str, str]]] = {}


def version() -> int:
    return _version


def bump() -> None:
    """쓰기가 지나갔다 — 들고 있던 답은 전부 옛것이다."""
    global _version
    with _lock:
        _version += 1
        _entries.clear()


def cacheable(path: str) -> bool:
    return path in CACHEABLE


def get(key: tuple):
    now = time.monotonic()
    with _lock:
        found = _entries.get(key)
        if found is None:
            return None
        ver, at, status, body, headers = found
        if ver != _version or now - at > TTL_SECONDS:
            _entries.pop(key, None)
            return None
        return status, body, headers


def put(key: tuple, ver: int, status: int, body: bytes, headers: dict[str, str]) -> None:
    with _lock:
        if ver == _version:  # 계산하는 동안 쓰기가 지나갔으면 넣지 않는다
            _entries[key] = (ver, time.monotonic(), status, body, headers)


def stats() -> dict[str, int]:
    with _lock:
        return {"version": _version, "entries": len(_entries)}
