"""오늘 날짜 — 날짜 규칙이 모두 여기서 '오늘' 을 읽는다 (TODO 219).

보고 날짜 ±365일 · 확정은 1주 앞까지 · 미래 기록 거부 같은 규칙이 '오늘' 에 기대는데, 시험은 2026년 날짜를
글자 그대로 쓴다. 실제 오늘을 읽으면 2027년 가을쯤부터 멀쩡한 시험이 깨진다. 시험은 `MD_MGMT_TODAY`
(`YYYY-MM-DD`)로 오늘을 고정하고, 프로그램은 그 값이 없으니 실제 오늘을 쓴다.

과제 · 기록에 남기는 시각(`created_at` · `updated_at` · 상태 이력)도 `now()` 로 — 날짜가 오늘과 어긋나면
"마지막으로 고친 해" · "보고 뒤에 쌓인 기록" 같은 셈이 시험에서 흔들린다.
오류 기록 · 공유 접속 기록 · 백업 주기 · 보관함 · 이전 버전의 파일 이름처럼 **실제로 흐른 시각**이 뜻인 곳은
이 시계를 쓰지 않는다.
"""
from __future__ import annotations

import os
from datetime import date, datetime

ENV = "MD_MGMT_TODAY"


def today() -> date:
    fixed = os.environ.get(ENV, "").strip()
    if fixed:
        try:
            return date.fromisoformat(fixed)
        except ValueError:
            pass  # 잘못 적은 값으로 프로그램이 멈추면 안 된다 — 실제 오늘로
    return date.today()


def now() -> datetime:
    """기록에 남기는 시각 — 날짜는 `today()`, 시각은 실제 (이 PC 의 시간대가 붙은 값)."""
    real = datetime.now().astimezone()
    day = today()
    if day == real.date():
        return real
    return real.replace(year=day.year, month=day.month, day=day.day)
