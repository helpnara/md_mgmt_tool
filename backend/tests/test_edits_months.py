"""팀원이 고친 것 — 기간이 두 달을 넘어도 가운데 달 · 해 넘김을 빠뜨리지 않는다 (TODO 327)."""
from __future__ import annotations

import json
from datetime import datetime

from app import clock
from app.config import get_settings
from app.services import edits


def _write(month: str, at: str) -> None:
    path = get_settings().logs_dir / f"edits-{month}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": at, "name": "가팀원", "role": "member", "action": "진행일지 추가",
                                 "project_id": None, "entry_id": None}, ensure_ascii=False) + "\n")


def test_months_between_crosses_the_year():
    assert edits._months_between(datetime(2026, 12, 20), datetime(2027, 3, 1)) == ["2026-12", "2027-01", "2027-02", "2027-03"]


def test_lines_read_every_month_in_between(client, monkeypatch):
    for month, at in (("2026-12", "2026-12-31T09:00:00"), ("2027-01", "2027-01-15T09:00:00"),
                      ("2027-02", "2027-02-10T09:00:00"), ("2027-03", "2027-03-01T08:00:00")):
        _write(month, at)
    monkeypatch.setattr(clock, "now", lambda: datetime(2027, 3, 1, 12, 0, 0))
    got = sorted(item["at"][:7] for item in edits._lines(datetime(2026, 12, 30)))
    assert got == ["2026-12", "2027-01", "2027-02", "2027-03"]
