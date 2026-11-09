"""요청마다 "지금 누구인가" — 등록한 IP 로 사람을 알아본다 (TODO 233 · 193 · 로드맵-확산단계 3.3 의 1).

로그인은 없다(사용자 결정 — 사내 IP 는 사람마다 부여 · 관리되고 입사 뒤 거의 바뀌지 않는다). 셋 중 하나다.

* **owner (관리자)** — 서버 PC 안에서 온 요청(127.0.0.1 · 서버 자신의 주소, `share.is_local_host`). 공유를 켜지 않았으면 언제나.
  처음(233)에는 "팀장 PC = 서버 PC" 라 팀장이라 불렀다. 서버를 운영 서버로 따로 두면서(247) 서버 운영까지 하는 **관리자**가 됐다.
* **leader (팀장)** — 명부에서 **팀장으로 지정한 사람(235)의 IP** 에서 온 요청 (TODO 247). 서버 운영(`permissions.ADMIN_ONLY`)을 뺀 모두.
* **member (팀원)** — 설정 → 명부에서 그 사람에게 붙인 IP 에서 온 요청. **떠난 사람은 아니다**(194).
* **viewer (읽기)** — 그 밖의 사내 PC. 지금(191)의 읽기 전용 그대로다. 가상 PC · 공용 PC 는 등록하지 않으므로 여기다(사용자 결정).

IP 는 **연결의 실제 주소만** 본다 — `X-Forwarded-For` 같은 머리글은 누구나 적어 보낼 수 있어 믿지 않는다(TODO 233 R6).
"""
from __future__ import annotations

import ipaddress
import threading
from dataclasses import dataclass

from fastapi import Request

from . import share

OWNER = "owner"
LEADER = "leader"
MEMBER = "member"
VIEWER = "viewer"


@dataclass(frozen=True)
class User:
    role: str
    name: str = ""

    @property
    def key(self) -> str:
        """답 나눠 쓰기(readcache) · 로그의 열쇠 — 팀원은 사람마다 다른 답(자기 면담)을 받는다."""
        return f"member:{self.name}" if self.role == MEMBER else self.role

    @property
    def manages(self) -> bool:
        """팀을 맡은 쪽 — 관리자(서버 PC)와 팀장(팀장 PC). 모든 과제 · 명부 · 면담 · 설정 (TODO 247)."""
        return self.role in (OWNER, LEADER)


THE_OWNER = User(OWNER)
A_VIEWER = User(VIEWER)
MAX_IPS = 5


def normalize_ip(value: object) -> str:
    """`10.1.2.31` · `::ffff:10.1.2.31` · `fe80::1%eth0` → 한 모양으로. 주소가 아니면 ValueError."""
    text = share._strip_scope(str(value or "").strip())
    try:
        return str(ipaddress.ip_address(text))
    except ValueError as exc:
        raise ValueError(f"IP 주소 모양이 아닙니다: {str(value)[:40]}") from exc


def check_ip(value: object) -> str:
    """명부에 적을 IP 하나의 검사 — 모양 · 서버 PC 자신의 주소가 아닌가."""
    ip = normalize_ip(value)
    if share.is_local_host(ip):
        raise ValueError(f"{ip} 는 서버 PC(팀장 PC) 자신의 주소입니다 — 팀원 PC 의 주소를 적어 주세요.")
    return ip


# IP → 이름. 설정 파일이 바뀌면 다시 만든다(파일 시각으로 안다) — 요청마다 설정 파일을 읽지 않게
_lock = threading.Lock()
_cache: dict[str, object] = {"stamp": None, "map": {}, "leader": ""}


def _settings_stamp() -> tuple:
    from .services import settings as settings_service

    path = settings_service._path()
    try:
        stat = path.stat()
        return (str(path), stat.st_mtime_ns, stat.st_size)
    except OSError:
        return (str(path), None, None)


def _load() -> tuple[dict[str, str], str]:
    from .services import settings as settings_service

    stamp = _settings_stamp()
    with _lock:
        if _cache["stamp"] == stamp:
            return dict(_cache["map"]), str(_cache["leader"])  # type: ignore[arg-type]
    mapping: dict[str, str] = {}
    leader = ""
    for person in settings_service.people():
        if settings_service.has_left(person):
            continue
        if person.get("leader"):
            leader = person["name"]
        for ip in person.get("ips") or []:
            mapping.setdefault(ip, person["name"])
    with _lock:
        _cache.update({"stamp": stamp, "map": mapping, "leader": leader})
    return dict(mapping), leader


def ip_map() -> dict[str, str]:
    """지금 있는 사람의 IP → 이름. 떠난 사람(떠난 날이 오늘이거나 지남)의 IP 는 넣지 않는다."""
    return _load()[0]


def forget() -> None:
    """시험 · 명부 저장 뒤 — 다음 요청이 다시 읽게."""
    with _lock:
        _cache.update({"stamp": None, "map": {}, "leader": ""})


def identify(request: Request) -> User:
    if not share.is_remote(request):
        return THE_OWNER
    client = request.client
    if client is None:
        return A_VIEWER
    try:
        ip = normalize_ip(client.host)
    except ValueError:
        return A_VIEWER
    mapping, leader = _load()
    name = mapping.get(ip)
    if not name:
        return A_VIEWER
    # 명부의 팀장이면 팀장 (TODO 247) — 팀장 PC 가 서버 PC 와 다를 때
    return User(LEADER, name) if name == leader else User(MEMBER, name)


def of(request: Request) -> User:
    """미들웨어가 정해 둔 사람. 미들웨어를 거치지 않은 길(시험의 함수 호출)이면 팀장."""
    user = getattr(request.state, "user", None)
    return user if isinstance(user, User) else THE_OWNER
