"""지금 고치는 중 (TODO 317) — 누가 어떤 글을 편집기로 열어 두었나.

팀원과 함께 쓰면서 "이 글을 연 뒤 ○○ 님이 먼저 고쳤습니다" 가 가끔 났다(저장할 때 겹침을 알리는 409).
그 일이 생기기 **전에** 알리려고, 편집기가 열려 있는 동안 화면이 15초마다 "고치는 중" 을 알린다.

* 메모리에만 둔다 — 파일 · 색인에 남기지 않는다. 서버를 다시 켜면 비고, 다음 알림에서 다시 찬다.
* 45초 동안 알림이 없으면(창을 닫음 · 잠듦 · 네트워크) 저절로 사라진다.
* 대상 열쇠는 쓰다 만 글(drafts)과 같다 — `entry:<번호>` · `entry:new-<과제>` · `overview:<과제>` · `report:<번호>` · `intake:<번호>` …
  과제 화면은 `?prefix=` 로 그 과제에 걸린 것을 한 번에 본다(대상에 과제 번호가 들어 있다).
* 같은 사람의 다른 창(탭)도 따로 센다 — 내 창은 `client`(창마다 무작위 값)로 뺀다.
"""
from __future__ import annotations

import threading
import time
from typing import Any

TTL = 45.0
IDLE_RELEASE = 600.0   # 318 — 10분 동안 입력이 없으면 잠금을 내준다(편집기는 열려 있어도)
MAX_TARGETS = 2000

_lock = threading.Lock()
_items: dict[str, dict[str, dict[str, Any]]] = {}   # 대상 → 창 → {name, since, last}


def _clean(now: float) -> None:
    for target in list(_items):
        clients = _items[target]
        for client in [c for c, v in clients.items() if now - v["last"] > TTL]:
            del clients[client]
        if not clients:
            del _items[target]


def beat(target: str, client: str, name: str, idle: float = 0.0) -> list[dict[str, Any]]:
    """알림 하나 — 이 창이 이 대상을 고치는 중. 같은 대상을 고치는 **다른 창**을 돌려준다.
    `idle` 은 그 편집기에서 마지막으로 입력한 뒤 지난 초(318 — 10분이 넘으면 잠금을 내준다)."""
    now = time.time()
    with _lock:
        _clean(now)
        if target not in _items and len(_items) >= MAX_TARGETS:
            return []
        row = _items.setdefault(target, {}).setdefault(client, {"name": name, "since": now, "last": now, "idle": 0.0})
        row["last"] = now
        row["name"] = name
        row["idle"] = max(0.0, float(idle or 0))
        return _others(target, client, now)


def holder(target: str, client: str = "") -> dict[str, Any] | None:
    """318 — 이 글을 먼저 연 사람(잠금을 쥔 창). 내 창 · 10분 넘게 입력이 없는 창은 잠금을 쥐지 않는다.
    부드러운 잠금이다 — 나중 사람은 읽기 모드로 보고, [그래도 고치기]로 열 수 있다(저장 겹침은 409 가 받친다)."""
    now = time.time()
    with _lock:
        _clean(now)
        rows = sorted((_items.get(target) or {}).items(), key=lambda kv: kv[1]["since"])
        for c, v in rows:
            if c == client:
                return None            # 내가 먼저 열었다
            if v.get("idle", 0) < IDLE_RELEASE:
                return {"name": v["name"], "minutes": int((now - v["since"]) // 60), "idle_minutes": int(v.get("idle", 0) // 60)}
        return None


def leave(target: str, client: str) -> None:
    with _lock:
        clients = _items.get(target)
        if clients:
            clients.pop(client, None)
            if not clients:
                _items.pop(target, None)


def _others(target: str, client: str, now: float) -> list[dict[str, Any]]:
    return [{"name": v["name"], "minutes": int((now - v["since"]) // 60)}
            for c, v in sorted((_items.get(target) or {}).items(), key=lambda kv: kv[1]["since"]) if c != client]


def listing(prefix: str = "", client: str = "") -> list[dict[str, Any]]:
    """대상 이름에 `prefix` 가 든 것 — 과제 화면이 그 과제의 일지 · 개요 · 보고를 한 번에 본다. 내 창은 뺀다."""
    now = time.time()
    with _lock:
        _clean(now)
        out = []
        for target in sorted(_items):
            if prefix and prefix not in target:
                continue
            others = _others(target, client, now)
            if others:
                out.append({"target": target, "people": others})
        return out


def reset() -> None:
    with _lock:
        _items.clear()
