"""연도를 고르면 무엇이 "그 해의 과제" 인가 (TODO 181).

**수행기간이 그 해와 겹치는 과제 모두** — 2026.01 ~ 2027.12 과제는 2026 에도 2027 에도 하나씩 센다.
처음에는(95 · 104) 과제 번호의 연도(= 착수년도)로만 갈라, 다년도 과제가 이듬해 화면에서 사라졌다.
번호 규칙은 그대로다 — 번호는 이름이고, 이 모듈은 **세고 거르는** 기준만 정한다.

홈 · 과제목록 위 대시보드 · 과제목록 거르기 · 보고이력의 과제 × 월 표가 **모두 이 모듈 하나를 쓴다** — 세는 곳과
거르는 곳이 어긋나면 숫자를 눌렀을 때 다른 수가 나온다(DESIGN 5.8). 178 에서 단계 셈을 하나로 모은 것과 같은 이유다.

| | 처음 | 끝 |
|---|---|---|
| 끝나지 않은 과제 | 시작일, 없으면 번호의 연도 | 마감일과 **올해** 중 늦은 쪽 — 마감이 지났는데 아직 하고 있으면 올해에도 보인다 |
| 완료 | 〃 | 완료일, 없으면 마감일, 그도 없으면 처음 |
| 중단 | 〃 | 마감일과 마지막으로 고친 해 중 이른 쪽(그만둔 날을 따로 적지 않는다) |

끝이 처음보다 앞서면(잘못 적은 날짜) 처음으로 본다 — 어느 해에서도 사라지지 않게.

**그 해의 상태** — 과제가 *그 해 뒤에* 끝났거나 그만뒀으면, 그 해에는 아직 진행 중이었다(진행중으로 센다). 그래서
지난해를 고르면 "완료" 는 **그 해에 끝낸 과제**만이다(사용자 결정 ②). 올해를 고르면 지금 상태와 같다.

**효과 금액은 한 해에만** — 기대효과와 실증효과를 **같은 해**, 과제가 **끝나는 해**(완료했으면 완료년도, 아니면 마감년도)에
센다(사용자 결정 ① — "매년 계획 대비 실적을 점검하기 때문에 기대효과와 실증효과를 같은 해에"). 과제 수는 해마다 세도
금액은 겹치지 않는다.

**신규** — 번호의 연도가 그 해인 과제(그 해에 착수). 연간 계획 · 성과 보고의 "신규 착수 N건"(사용자 결정 ③).
"""
from __future__ import annotations

import sqlite3
from datetime import date


def _this_year() -> str:
    return str(date.today().year)


def _y(column: str) -> str:
    """날짜 칸의 연도 네 자리(비면 NULL). 색인이 날짜를 검사해 두므로(164) 앞 네 자리는 연도다."""
    return f"NULLIF(SUBSTR({column}, 1, 4), '')"


def start_year(a: str = "p") -> str:
    return f"COALESCE({_y(f'{a}.start_date')}, SUBSTR({a}.id, 1, 4))"


def end_year(a: str = "p") -> str:
    s = start_year(a)
    due = _y(f"{a}.due_date")
    upd = _y(f"{a}.updated_at")
    return (
        f"MAX({s}, CASE"
        f" WHEN {a}.status = 'done' THEN COALESCE({_y(f'{a}.completed_at')}, {due}, {s})"
        f" WHEN {a}.status = 'dropped' THEN MIN(COALESCE({due}, {upd}, {s}), COALESCE({upd}, {due}, {s}))"
        f" ELSE MAX(COALESCE({due}, {s}), '{_this_year()}') END)"
    )


def effect_year(a: str = "p") -> str:
    """효과 금액을 세는 해 — 끝나는 해(완료했으면 완료년도, 아니면 마감년도)."""
    s = start_year(a)
    due = _y(f"{a}.due_date")
    return (
        f"MAX({s}, CASE WHEN {a}.status = 'done' THEN COALESCE({_y(f'{a}.completed_at')}, {due}, {s})"
        f" ELSE COALESCE({due}, {s}) END)"
    )


def scope(year: str | None, alias: str = "p") -> tuple[str, list]:
    """FROM 에 그대로 넣는 "그 해의 과제" — `project` 의 칸 전부에 넷을 더한다.

    * `y_status` — 그 해의 상태(그 해 뒤에 끝났으면 진행중)
    * `y_ee` · `y_ev` — 그 해에 세는 기대 · 실증효과(끝나는 해가 아니면 NULL)
    * `y_new` — 그 해에 착수했는가(번호의 연도)
    * `y_effect_year` — 효과 금액을 세는 해(과제목록의 합계 줄이 그 해 것만 더한다)

    연도가 없으면(전체) 모든 과제, 상태 · 금액은 그대로.
    """
    if not year:
        return (
            "(SELECT q.*, q.status AS y_status, q.effect_expected AS y_ee, q.effect_verified AS y_ev,"
            f" 0 AS y_new, {effect_year('q')} AS y_effect_year FROM project q) {alias}",
            [],
        )
    sql = (
        "(SELECT q.*,"
        f" CASE WHEN q.status IN ('done', 'dropped') AND {end_year('q')} > ? THEN 'in_progress' ELSE q.status END AS y_status,"
        f" CASE WHEN {effect_year('q')} = ? THEN q.effect_expected END AS y_ee,"
        f" CASE WHEN {effect_year('q')} = ? THEN q.effect_verified END AS y_ev,"
        " (SUBSTR(q.id, 1, 4) = ?) AS y_new,"
        f" {effect_year('q')} AS y_effect_year"
        f" FROM project q WHERE {start_year('q')} <= ? AND {end_year('q')} >= ?) {alias}"
    )
    return sql, [year] * 6


def overlap(year: str | None, alias: str = "p") -> tuple[str, list]:
    """WHERE 에 붙이는 조건(` AND …`) — 이미 `project` 를 직접 읽는 질의를 위해."""
    if not year:
        return "", []
    return f" AND {start_year(alias)} <= ? AND {end_year(alias)} >= ?", [year, year]


def years(conn: sqlite3.Connection) -> list[str]:
    """고를 수 있는 해 — 과제의 수행기간이 걸친 해 전부와 올해, 최근 것부터.

    번호에 있는 해만 세우면 2026~2027 과제의 2027 을 고를 수 없었다.
    """
    row = conn.execute(f"SELECT MIN({start_year('p')}) AS lo, MAX({end_year('p')}) AS hi FROM project p").fetchone()
    if not row or row["lo"] is None:
        return []  # 과제가 없다 — 홈이 "처음 켰을 때" 화면을 세우는 근거다
    found: set[str] = set()
    if str(row["lo"]).isdigit() and str(row["hi"]).isdigit():
        lo, hi = int(row["lo"]), int(row["hi"])
        if hi - lo <= 50:  # 손으로 잘못 적은 연도 하나로 목록이 수백 줄이 되지 않게
            found.update(str(year) for year in range(lo, hi + 1))
        else:
            found.update({str(lo), str(hi)})
    return sorted(found, reverse=True)
