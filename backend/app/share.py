"""읽기 전용 공유 모드 (TODO 191 · 192).

`run.py --share` 로 켜면 바깥(0.0.0.0)에 열리면서 **같은 순간** 이 규칙이 켜진다 — 둘이 따로 켜지지 않는다.
서버에는 "누가 보내는가" 를 보는 곳이 없었다. 127.0.0.1 이 유일한 울타리였고, 바깥에 열면 그 울타리가 사라진다.
그래서 막는 기준은 "누구" 가 아니라 **"어디서"** 다 — 서버 PC 안(127.0.0.1)에서 온 요청은 지금처럼 전부,
바깥에서 온 요청은 **읽기만**. 로그인 · 사용자 개념 없이도 안전하다(그것은 2단계, 로드맵-확산단계 3.3).

* GET · HEAD · OPTIONS 만 통과. 나머지 53개 쓰기 끝점은 403 — "읽기 전용으로 공유 중입니다".
* 읽기여도 보여 주면 안 되는 것은 403: 서버 PC 의 폴더 목록(folders) · vault 전체 zip(backup) · 설정(백업 경로 · 명부) ·
  오류 기록 · 삭제 보관함 · 이전 버전 · 남이 쓰다 만 글(drafts) · 깨진 링크 · health(폴더 경로) · 명부(people — 사번 칸).
* 면담 기록은 **빈 목록** — 있는지조차 보이지 않게 (182: 팀장 본인만). 팀원역량 요약의 면담 칸도 비운다.
* 바깥에서 온 요청은 주소 · 시각 · 끝점 · 결과만 하루 파일로 남긴다(`.logs/access-<날짜>.jsonl`). 누가 무엇을 봤는지의 내용은 적지 않는다.
  설정 → 점검이 "오늘 N명" 을 보인다.
* **주인 PC 는 자기 주소 어느 것으로 열어도 주인이다** (TODO 206 ㉖). 127.0.0.1 · ::1 · localhost 뿐 아니라 서버의
  자기 인터페이스 IP(PC 이름으로 안내한 공유 주소 `http://PC이름:8000` 을 서버 PC 에서 열면 LAN IP 로 들어온다)도
  LOCAL 로 본다. 그 전에는 주인이 안내된 공유 주소로 열면 403 이었고 "쓰려면 127.0.0.1" 규칙이 필요했다.
* `/openapi.json` · `/docs` · `/redoc` 도 바깥에는 403 (TODO 206 ㉘) — 끝점 전체와 스키마 필드명(`backup_dir` · `employee_id`)이 보인다.
"""
from __future__ import annotations

import json
import os
import socket
import threading
from datetime import date, datetime
from typing import Any

from fastapi import Request

from .config import get_settings

LOCAL_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "testclient"})

# 서버 자신의 주소들 (TODO 206 ㉖). 처음 물을 때 한 번 구해 둔다 — None 이면 아직 안 구함. 시험이 바꿔 끼운다.
_own_addresses: frozenset[str] | None = None


def _strip_scope(address: str) -> str:
    """`fe80::1%eth0` → `fe80::1`, `::ffff:192.168.0.10` → `192.168.0.10`."""
    address = address.split("%", 1)[0]
    if address.lower().startswith("::ffff:") and address.count(".") == 3:
        address = address[7:]
    return address


def _detect_own_addresses() -> frozenset[str]:
    """이 PC 의 IPv4 · IPv6 주소들. 어느 한 길이 막혀도(오프라인 · 이름 풀이 실패) 나머지로 간다."""
    found: set[str] = set()
    try:
        host = socket.gethostname()
        found.add(host.lower())
        for info in socket.getaddrinfo(host, None):
            found.add(_strip_scope(str(info[4][0])))
    except (OSError, UnicodeError):
        pass
    # UDP 는 보내지 않아도 connect 로 "어느 주소로 나가는가" 를 알 수 있다 — 주 LAN IP 를 얻는 흔한 방법
    for family, target in ((socket.AF_INET, ("10.255.255.255", 1)), (socket.AF_INET6, ("2001:db8::1", 1))):
        try:
            with socket.socket(family, socket.SOCK_DGRAM) as probe:
                probe.connect(target)
                found.add(_strip_scope(str(probe.getsockname()[0])))
        except (OSError, UnicodeError):
            pass
    return frozenset(address for address in found if address)


def own_addresses() -> frozenset[str]:
    global _own_addresses
    if _own_addresses is None:
        _own_addresses = _detect_own_addresses()
    return _own_addresses


def is_local_host(host: str | None) -> bool:
    """서버 PC 안에서 온 주소인가 — 루프백이거나 서버 자신의 인터페이스 주소 (TODO 206 ㉖)."""
    if not host:
        return False
    address = _strip_scope(host)
    return host in LOCAL_HOSTS or address in LOCAL_HOSTS or address.lower() in own_addresses()

# 읽기(GET)여도 바깥에는 열지 않는 끝점 — 앞부분이 맞으면 막는다
BLOCKED_PREFIXES = (
    "/api/folders", "/api/backup", "/api/settings", "/api/errors", "/api/trash",
    "/api/versions", "/api/drafts", "/api/maintenance", "/api/health", "/api/people",  # maintenance = 링크 점검 (TODO 220)
    # API 문서 — 끝점 전체 · 스키마 필드명이 보인다 (TODO 206 ㉘)
    "/openapi.json", "/docs", "/redoc",
)
# 빈 결과로 답하는 끝점 — 화면이 오류 대신 "없음" 을 보이게
EMPTY_RESPONSES: dict[str, dict[str, Any]] = {
    "/api/meetings": {"items": [], "open_followups": []},
}
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
READONLY_DETAIL = "읽기 전용으로 공유 중입니다. 고치려면 서버 PC 에서 여세요."


def enabled() -> bool:
    return os.environ.get("MD_MGMT_SHARE") == "1"


def is_remote(request: Request) -> bool:
    """바깥에서 온 요청인가. 공유를 켜지 않았으면 언제나 아니다. 보낸 쪽을 모르면(클라이언트 정보 없음) 바깥으로 본다."""
    if not enabled():
        return False
    client = request.client
    return client is None or not is_local_host(client.host)


def blocked_path(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix + "/") or path.startswith(prefix + "?") for prefix in BLOCKED_PREFIXES)


def share_url(port: int | None) -> str:
    """팀원에게 알려 줄 주소 — IP 는 바뀔 수 있으니 PC 이름으로."""
    return f"http://{socket.gethostname()}:{port or 8000}"


# ── 접속 기록 — 바깥에서 온 요청만, 내용 없이 ────────────────────────────────
_lock = threading.Lock()
_today: dict[str, Any] = {"date": None, "ips": set(), "requests": 0}


def record_access(ip: str, method: str, path: str, status: int) -> None:
    today = date.today().isoformat()
    line = json.dumps({"at": datetime.now().isoformat(timespec="seconds"), "ip": ip, "method": method,
                       "path": path.split("?")[0], "status": status}, ensure_ascii=False)
    with _lock:
        if _today["date"] != today:
            _today.update({"date": today, "ips": set(), "requests": 0})
        _today["ips"].add(ip)
        _today["requests"] += 1
        try:
            logs = get_settings().logs_dir
            logs.mkdir(parents=True, exist_ok=True)
            with (logs / f"access-{today}.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            pass  # 기록에 실패해도 서비스를 멈추지 않는다 (errorlog 와 같은 원칙)


def visitors_today() -> dict[str, int]:
    with _lock:
        if _today["date"] != date.today().isoformat():
            return {"visitors": 0, "requests": 0}
        return {"visitors": len(_today["ips"]), "requests": _today["requests"]}
