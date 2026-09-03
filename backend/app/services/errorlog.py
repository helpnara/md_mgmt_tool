"""오류 기록.

지금까지는 뭔가 잘못되면 **흔적이 남지 않았다.** 검은 창이 닫히면 끝이고, 화면에는
"요청에 실패했습니다" 한 줄만 떴다. 나중에 "어제 저장이 한 번 안 됐는데" 라고 해도
확인할 것이 없었다.

그래서 실패한 요청을 파일에 한 줄씩 남긴다.

**무엇을 남기는가** — 실패한 동작과 **그 직전 동작 3개**.
오류만 남기면 "왜 그 상태가 됐는지"를 알 수 없고, 모든 동작을 남기면 파일이 커지는 데다
나중에 여러 사람이 쓸 때 "누가 무엇을 봤는지"가 기록으로 남는다. 그 사이를 택했다.

**무엇을 남기지 않는가** — 본문·제목·첨부 내용 같은 **과제 내용은 담지 않는다.**
남기는 것은 동작(`PATCH /api/reports/3`)과 오류 종류뿐이다. 그래야 이 파일 하나를
그대로 전달해 원인을 물을 수 있다.

파일 형식은 JSONL 이다. 덧붙이기만 하면 되고, 중간에 프로그램이 멈춰도 앞선 줄은
멀쩡하며, 한 줄이 깨져도 그 줄만 건너뛰면 된다 (.trash/manifest.jsonl 과 같은 이유).
"""
from __future__ import annotations

import json
from collections import deque
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ..config import get_settings

# 오류 한 건에 함께 남기는 직전 동작 수.
TRAIL = 3
# 화면에 세우는 최근 오류 수.
RECENT_LIMIT = 20
# 보관 개월 수. 지난 기록은 원인 추적에 쓸모가 없고 파일만 늘린다.
KEEP_MONTHS = 3

# 오류로 볼 응답 상태. 404(없는 것을 찾음)와 401·403 은 흔하고 대개 문제가 아니라 뺀다.
RECORDED_4XX = frozenset({400, 409, 422, 423, 507})

# 최근 동작 꼬리. 요청마다 갱신되고 오류가 날 때만 함께 적힌다.
_trail: deque[str] = deque(maxlen=TRAIL)


def note(action: str) -> None:
    """동작 하나를 꼬리에 남긴다. 파일에 쓰지는 않는다."""
    _trail.append(action)


def clear_trail() -> None:
    _trail.clear()


def should_record(status: int) -> bool:
    return status >= 500 or status in RECORDED_4XX


def _path_for(when: date) -> Path:
    return get_settings().logs_dir / f"error-{when:%Y-%m}.log"


def record(
    *,
    action: str,
    status: int | None = None,
    error: str | None = None,
    detail: str | None = None,
) -> None:
    """오류 한 건을 남긴다. **기록에 실패해도 프로그램을 멈추지 않는다.**

    오류를 적다가 나는 오류 때문에 사용자의 동작이 막히면 본말이 뒤바뀐다.
    """
    try:
        settings = get_settings()
        settings.logs_dir.mkdir(parents=True, exist_ok=True)
        entry: dict[str, Any] = {
            "at": datetime.now().isoformat(timespec="seconds"),
            "action": action,
            "status": status,
            "error": error,
            # 화면에 그대로 보이는 문구다. 너무 길면 읽기 어렵다.
            "detail": (detail or "")[:500] or None,
            # 실패한 동작 자신은 빼고, 그 앞의 것만.
            "trail": [item for item in _trail if item != action][-TRAIL:],
        }
        with _path_for(date.today()).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        _prune()
    except (OSError, ValueError, TypeError):
        pass


def _prune() -> None:
    """보관 개월이 지난 파일을 지운다."""
    settings = get_settings()
    today = date.today()
    cutoff = f"{today.year * 12 + today.month - KEEP_MONTHS:06d}"
    for path in settings.logs_dir.glob("error-*.log"):
        stem = path.stem.removeprefix("error-")
        try:
            year, month = (int(part) for part in stem.split("-"))
        except ValueError:
            continue
        if f"{year * 12 + month:06d}" < cutoff:
            path.unlink(missing_ok=True)


def recent(limit: int = RECENT_LIMIT) -> list[dict[str, Any]]:
    """최근 오류. 새 것부터.

    이번 달과 지난달 파일만 읽는다 — 화면에서 보는 것은 늘 최근 몇 건이고,
    기록이 쌓였다고 읽는 시간이 길어지면 안 된다.
    """
    settings = get_settings()
    if not settings.logs_dir.exists():
        return []

    files = sorted(settings.logs_dir.glob("error-*.log"), reverse=True)[:2]
    items: list[dict[str, Any]] = []
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # 깨진 줄 하나가 나머지를 못 보게 만들면 안 된다
            if len(items) >= limit:
                return items
    return items


def clear() -> int:
    """기록을 모두 지운다. "지금부터 다시 해 볼게" 를 위한 자리다."""
    settings = get_settings()
    if not settings.logs_dir.exists():
        return 0
    removed = 0
    for path in settings.logs_dir.glob("error-*.log"):
        path.unlink(missing_ok=True)
        removed += 1
    clear_trail()
    return removed
