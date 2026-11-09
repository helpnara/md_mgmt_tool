"""경험의 기간 읽기 (TODO 256 · 1단계.md 4절 ④).

AI 응답의 `기간:` 은 모양이 여럿이다 — `2026-03 ~ 2026-09` · `2016 ~ 2017` · `2026.03-2026.09` · `2026년 3월 ~ 9월` ·
물결표 없이 `2025.04 2025.10` · 끝이 `현재`. 허용한 모양만 `YYYY-MM`(달을 모르면 `YYYY`) 두 끝으로 읽고,
못 읽으면 원문을 그대로 두고 경고를 낸다(정합성 X-07 의 재료).
"""
from __future__ import annotations

import re

# 연 + (구분자 + 달)? — 달은 1 ~ 2자리이고 바로 뒤에 숫자가 오지 않아야 한다("2026-2027" 을 2026-20 으로 읽지 않게)
_YEAR_MONTH = re.compile(r"(?<!\d)(\d{4})(?:\s*(?:[-./]|년)\s*(\d{1,2})(?!\d)\s*월?)?")
# 연 없이 달만 — "2026년 3월 ~ 9월" 의 뒤쪽
_MONTH_ONLY = re.compile(r"(?<![\d.\-/])(\d{1,2})\s*월")
_OPEN_END = re.compile(r"현재|진행\s*중|지금|재직\s*중")


def _token(year: str, month: str | None) -> tuple[str | None, str | None]:
    if month is None:
        return year, None
    m = int(month)
    if not 1 <= m <= 12:
        return None, f"달이 1 ~ 12 밖입니다: {month}"
    return f"{year}-{m:02d}", None


def parse_period(text: str | None) -> tuple[str, str, list[str]]:
    """`(시작, 끝, 경고들)`. 비었으면 둘 다 빈 글. 끝이 `현재` 면 끝은 빈 글(진행 중)."""
    raw = (text or "").strip()
    if not raw:
        return "", "", []
    warnings: list[str] = []
    found: list[tuple[int, str]] = []
    taken: list[tuple[int, int]] = []
    for match in _YEAR_MONTH.finditer(raw):
        value, problem = _token(match.group(1), match.group(2))
        if problem:
            warnings.append(problem)
        if value:
            found.append((match.start(), value))
            taken.append(match.span())
    for match in _MONTH_ONLY.finditer(raw):
        if any(a <= match.start() < b for a, b in taken):
            continue
        before = [value for at, value in found if at < match.start()]
        if not before:
            continue
        value, problem = _token(before[-1][:4], match.group(1))
        if problem:
            warnings.append(problem)
        if value:
            found.append((match.start(), value))
    found.sort()
    values = [value for _, value in found]
    open_end = bool(_OPEN_END.search(raw))
    if not values:
        return "", "", warnings + [f"기간을 읽지 못했습니다: {raw}"]
    if len(values) > 2:
        warnings.append(f"기간에 날짜가 {len(values)}개 있습니다 — 처음과 끝만 씁니다: {raw}")
    start = values[0]
    end = "" if open_end else (values[-1] if len(values) > 1 else "")
    # 날짜 글자를 뺀 나머지에 구분자가 있나 — "2026-06" 의 하이픈은 날짜의 일부라 구분자가 아니다
    rest = raw
    for a, b in sorted(taken, reverse=True):
        rest = rest[:a] + " " + rest[b:]
    if len(values) == 1 and not open_end and not re.search(r"[~∼〜–—-]|부터", rest):
        end = start  # 한 시점 — "2024-05" 하나만이면 시작 = 끝
    if end and end[:7] < start[:7]:
        warnings.append(f"끝이 시작보다 앞섭니다: {raw}")
    return start, end, warnings
