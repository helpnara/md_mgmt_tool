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

# 읽기(GET)여도 바깥에는 열지 않는 끝점 — 앞부분이 맞으면 막는다
BLOCKED_PREFIXES = (
    "/api/folders", "/api/backup", "/api/settings", "/api/errors", "/api/trash",
    "/api/versions", "/api/drafts", "/api/linkfix", "/api/health", "/api/people",
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
    return client is None or client.host not in LOCAL_HOSTS


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
