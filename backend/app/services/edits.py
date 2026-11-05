"""누가 무엇을 고쳤나 — 쓰기 기록 (TODO 233 ⑥ · R7).

팀원이 쓰기 시작하면 팀장은 **무엇이 바뀌었는지** 알아야 한다(홈 "팀원이 고친 것 — 최근 7일"). 두 사람이 같은 글을 고치다
부딪히면 "누가 먼저 고쳤나" 도 말해 줘야 한다(409). 그래서 진행일지 · 첨부 · 개요의 쓰기를 한 줄씩 남긴다.

* 남기는 것 — 시각 · 사람 · 역할 · 무엇(진행일지 추가 …) · 과제 번호 · 진행일지 번호. **글 내용은 남기지 않는다**(오류 기록 · 접속 기록과 같은 원칙).
* 자리 — `.logs/edits-YYYY-MM.jsonl`(달마다 한 파일). 지워도 도구는 멈추지 않는다 — 홈의 칸이 비고 409 의 "누가" 가 빠질 뿐이다.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .. import clock
from ..config import get_settings

_lock = threading.Lock()


def _file(at: datetime) -> Path:
    return get_settings().logs_dir / f"edits-{at.strftime('%Y-%m')}.jsonl"


def record(name: str, role: str, action: str, project_id: str | None, entry_id: int | None = None) -> None:
    now = clock.now()
    line = json.dumps({"at": now.isoformat(timespec="seconds"), "name": name, "role": role, "action": action,
                       "project_id": project_id, "entry_id": entry_id}, ensure_ascii=False)
    with _lock:
        try:
            path = _file(now)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            pass  # 기록에 실패해도 쓰기를 막지 않는다


def _lines(since: datetime) -> list[dict[str, Any]]:
    months = {since.strftime("%Y-%m"), clock.now().strftime("%Y-%m")}
    out: list[dict[str, Any]] = []
    for month in sorted(months):
        path = get_settings().logs_dir / f"edits-{month}.jsonl"
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for raw in text.splitlines():
            try:
                item = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict) and str(item.get("at", "")) >= since.isoformat(timespec="seconds"):
                out.append(item)
    return out


def recent(conn: sqlite3.Connection, days: int = 7, role: str | None = "member") -> list[dict[str, Any]]:
    """최근 며칠의 쓰기 — 새 것부터, 과제 이름을 붙여. 같은 사람 · 과제 · 무엇이 이어지면 한 줄로 묶어 횟수를 센다."""
    since = clock.now() - timedelta(days=days)
    # 파일은 오래된 것부터 쌓인다 — 뒤집은 뒤 시각으로 정렬하면 같은 초에 남은 것도 나중 것이 먼저 선다
    items = [item for item in reversed(_lines(since)) if role is None or item.get("role") == role]
    items.sort(key=lambda item: item.get("at", ""), reverse=True)
    titles: dict[str, str | None] = {}
    grouped: list[dict[str, Any]] = []
    for item in items:
        last = grouped[-1] if grouped else None
        if last and (last["name"], last["project_id"], last["action"]) == (item.get("name"), item.get("project_id"), item.get("action")) \
                and last["at"][:10] == str(item.get("at", ""))[:10]:
            last["count"] += 1
            continue
        project_id = item.get("project_id")
        if project_id and project_id not in titles:
            row = conn.execute("SELECT title FROM project WHERE id = ?", (project_id,)).fetchone()
            titles[project_id] = row["title"] if row else None
        grouped.append({
            "at": item.get("at", ""), "name": item.get("name", ""), "action": item.get("action", ""),
            "project_id": project_id, "project_title": titles.get(project_id) if project_id else None,
            "entry_id": item.get("entry_id"), "count": 1,
        })
    return grouped


def last_editor(project_id: str | None, entry_id: int | None, after: str) -> str | None:
    """`after`(ISO 시각) 뒤에 그 글을 고친 마지막 사람 — 409 의 "누가 먼저 고쳤나". 모르면 None."""
    try:
        since = datetime.fromisoformat(after.replace("Z", "+00:00")) - timedelta(seconds=1)
    except ValueError:
        since = clock.now() - timedelta(days=1)
    found = None
    for item in _lines(since):
        same = item.get("entry_id") == entry_id if entry_id is not None else (item.get("project_id") == project_id and item.get("entry_id") is None)
        if same:
            found = item.get("name") or found
    return found
