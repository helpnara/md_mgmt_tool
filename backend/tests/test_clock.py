"""시험의 '오늘' 은 고정이다 (TODO 219).

시험은 2026년 날짜를 글자 그대로 쓴다. 날짜 규칙(보고 날짜 ±365일 · 확정은 1주 앞까지 · 미래 기록 거부)이
실제 오늘을 읽으면 해가 갈수록 멀쩡한 시험이 깨진다. 규칙은 모두 `app.clock.today()` 에서 오늘을 읽는다.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from app import clock
from tests.conftest import FIXED_TODAY

APP = Path(__file__).resolve().parents[1] / "app"
# 실제로 흐른 시각이 뜻인 곳 — 오류 기록(달마다 파일) · 공유 접속 기록
REAL_TIME = {"clock.py", "errorlog.py", "share.py"}


def test_tests_run_on_the_fixed_day():
    assert clock.today() == date.fromisoformat(FIXED_TODAY)


def test_the_program_uses_the_real_day_without_the_setting(monkeypatch):
    monkeypatch.delenv(clock.ENV)
    assert clock.today() == date.today()


def test_a_bad_setting_falls_back_to_the_real_day(monkeypatch):
    monkeypatch.setenv(clock.ENV, "내일")
    assert clock.today() == date.today()


def test_date_rules_read_today_from_the_clock():
    """새로 `date.today()` 를 쓰면 그 규칙만 실제 오늘을 읽어 시험이 다시 날짜에 묶인다."""
    found = []
    for path in APP.rglob("*.py"):
        if path.name in REAL_TIME:
            continue
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), 1):
            if re.search(r"(?<![\w.])(date|date_cls)\.today\(\)|datetime\.now\(\)\.(year|date\(\))", line):
                found.append(f"{path.relative_to(APP)}:{number}: {line.strip()}")
    assert found == [], "clock.today() 를 쓰세요:\n" + "\n".join(found)


def test_report_date_rule_follows_the_clock(client, monkeypatch):
    """규칙이 정말 시계를 따른다 — 오늘을 2028년으로 옮기면 2026년 보고 날짜는 ±365일 밖이다."""
    project = client.post("/api/projects", json={"title": "시계 확인"}).json()
    client.post(f"/api/projects/{project['id']}/entries", json={"date": "2026-10-01", "body": "진행"})
    ok = client.post(f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-10-19"})
    assert ok.status_code == 201, ok.text
    monkeypatch.setenv(clock.ENV, "2028-06-01")
    late = client.post(f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-10-20"})
    assert late.status_code == 400, late.text


def test_sql_reads_today_from_the_clock_too():
    """SQL 의 `DATE('now')` 도 실제 오늘이다 — 219 가 놓쳐, 실제 날짜가 이틀 지나자 '곧 마감' 시험이 깨졌다 (TODO 220).
    질의는 연결에 심어 둔 `app_today()` 를 쓴다."""
    found = []
    for path in APP.rglob("*.py"):
        if path.name in REAL_TIME:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue  # 설명 글
            if re.search(r"""(?i)\b(date|datetime|julianday|strftime)\s*\([^)]*['"]now['"]""", line):
                found.append(f"{path.relative_to(APP)}:{number}: {line.strip()}")
    assert found == [], "app_today() 를 쓰세요:\n" + "\n".join(found)


def test_sql_today_follows_the_clock(db, monkeypatch):
    assert db.execute("SELECT app_today()").fetchone()[0] == FIXED_TODAY
    monkeypatch.setenv(clock.ENV, "2028-06-01")
    assert db.execute("SELECT DATE(app_today(), '+7 day')").fetchone()[0] == "2028-06-08"
