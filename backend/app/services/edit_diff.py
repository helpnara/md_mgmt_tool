"""팀원이 고친 곳 — 고치기 전 보관본 ↔ 지금 (TODO 305).

홈 "팀원이 고친 것" 은 누가 · 언제 · 무엇(진행일지 수정 2번 …)만 알려, 실제로 어디가 바뀌었는지 보려면 글을 처음부터 읽어야 했다.
쓰기 기록에는 글 내용을 남기지 않지만(233), 파일을 고칠 때마다 **고치기 전 모습이 `.versions` 에 남는다** — 그 보관본과 지금을 줄 단위로 견준다.

* 기준 — 그 줄(같은 날 · 같은 사람 · 같은 글)의 **첫 수정 직전** 보관본 ↔ 지금. 여러 번 고친 것을 한 번에 본다.
* 진행일지 추가 — 고치기 전이 없으므로 모두 "더한 줄".
* 역할 · 회고 — 과제 파일의 담당과 역할 중 그 사람 줄만 견준다.
* 첨부 — 파일 속은 견주지 않는다(화면이 첨부 줄을 강조만).
* 보관본이 없으면(보관 기간이 지났거나 저장해도 달라진 것이 없었음) `kind="none"` — 화면은 그 자리만 강조한다.
"""
from __future__ import annotations

import difflib
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from ..config import get_settings
from ..vault import markdown as md
from ..vault import versions as versions_service
from . import edits as edits_service

STAMP = "%Y-%m-%d_%H%M%S"
# 첫 수정의 보관본은 그 수정과 거의 같은 때 남는다(저장 직전). 쓰기 기록은 저장 뒤에 남으므로 조금 앞 · 조금 뒤까지 본다
BEFORE_SLACK = timedelta(minutes=5)
AFTER_SLACK = timedelta(seconds=10)
CONTEXT = 2          # 바뀐 줄 앞뒤로 보일 같은 줄 수
MAX_LINES = 400


def _stamp_time(stamp: str) -> datetime | None:
    try:
        return datetime.strptime("-".join(stamp.split("-")[:3]), STAMP)
    except ValueError:
        return None


def _since_time(since: str) -> datetime | None:
    """`2026-11-17_142005`(실제 시각) 또는 ISO 시각."""
    if not since:
        return None
    found = _stamp_time(since)
    if found:
        return found
    try:
        return datetime.fromisoformat(since.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _base_stamp(rel: str, since: datetime) -> str | None:
    """첫 수정 직전의 보관본 — 그 수정 시각 앞뒤 가까이에 남은 것 중 **가장 이른 것**(그 뒤 것들은 같은 사람의 2번째 · 3번째 수정)."""
    stamps = [item["stamp"] for item in versions_service.list_for(rel)]           # 새 것부터
    near = [s for s in stamps if (t := _stamp_time(s)) and since - BEFORE_SLACK <= t <= since + AFTER_SLACK]
    if not near:
        return None
    # 수정 시각에 가장 가까운 것이 그 수정이 남긴 보관본이다(5분 안에 다른 저장이 있었을 수 있다)
    # 같은 초에 여러 번 저장하면 `…05` · `…05-2` 처럼 남는다 — 같은 거리면 이른 것(첫 수정의 것)
    return min(near, key=lambda s: (abs((_stamp_time(s) - since).total_seconds()), s))


def target_rel(conn: sqlite3.Connection, project_id: str | None, entry_id: int | None) -> str | None:
    """그 쓰기가 고친 파일(vault 기준) — 일지면 일지 파일, 아니면 과제 파일."""
    from . import entries as entries_service
    from . import projects as projects_service

    try:
        if entry_id:
            _row, path = entries_service.entry_path(conn, int(entry_id))
        elif project_id:
            path = projects_service.project_dir(conn, project_id) / "index.md"
        else:
            return None
        return path.resolve().relative_to(get_settings().vault_dir.resolve()).as_posix()
    except (KeyError, ValueError, OSError):
        return None


def latest_stamp(project_id: str | None, entry_id: int | None) -> str:
    """방금 쓴 저장이 남긴 보관본(그 파일의 가장 새 보관본) — 쓰기 기록에 함께 적는다(305). 시각만으로는 같은 초의 다른 저장과 구별되지 않는다."""
    from ..db import connect

    conn = connect()
    try:
        rel = target_rel(conn, project_id, entry_id)
    finally:
        conn.close()
    if not rel:
        return ""
    items = versions_service.list_for(rel)
    return items[0]["stamp"] if items else ""


def _contribution_lines(meta: dict[str, Any], person: str) -> list[str]:
    from .. import contributions

    for row in contributions.read(meta):
        if row.get("name") == person:
            out = []
            labels = (("role", "역할"), ("part", "맡은 부분"), ("from", "담당 시작"), ("to", "담당 끝"),
                      ("did", "내가 한 일"), ("result", "결과"))
            for key, label in labels:
                value = row.get(key)
                if value:
                    for i, line in enumerate(str(value).splitlines() or [""]):
                        out.append(f"{label}: {line}" if i == 0 else f"  {line}")
            skills = row.get("skills") or []
            if skills:
                out.append("보유 기술(도구): " + ", ".join(map(str, skills)))
            for mark in row.get("milestones") or []:
                if isinstance(mark, dict):
                    out.append(f"중간 성과: {mark.get('date', '')} {mark.get('text', '')}".rstrip())
            return out
    return []


def _text_of(raw: str, action: str, person: str) -> list[str]:
    try:
        doc = md.loads(raw)
    except Exception:  # noqa: BLE001 — 손으로 고쳐 깨진 파일도 통째로는 견준다
        return raw.splitlines()
    if action.startswith("역할"):
        return _contribution_lines(doc.meta, person)
    return doc.body.strip("\n").splitlines()


def _ops(before: list[str], after: list[str]) -> tuple[list[dict[str, str]], dict[str, int]]:
    """줄마다 same · add · del · old(고치기 전) · new(고친 뒤). 같은 줄이 길게 이어지면 앞뒤 CONTEXT 줄만 남기고 "gap"."""
    lines: list[dict[str, str]] = []
    counts = {"added": 0, "changed": 0, "removed": 0}
    matcher = difflib.SequenceMatcher(a=before, b=after, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            lines.extend({"op": "same", "text": t} for t in before[i1:i2])
        elif tag == "insert":
            lines.extend({"op": "add", "text": t} for t in after[j1:j2])
            counts["added"] += j2 - j1
        elif tag == "delete":
            lines.extend({"op": "del", "text": t} for t in before[i1:i2])
            counts["removed"] += i2 - i1
        else:
            lines.extend({"op": "old", "text": t} for t in before[i1:i2])
            lines.extend({"op": "new", "text": t} for t in after[j1:j2])
            counts["changed"] += max(i2 - i1, j2 - j1)
    # 같은 줄 덩어리 줄이기
    keep = [False] * len(lines)
    for index, line in enumerate(lines):
        if line["op"] != "same":
            for k in range(max(0, index - CONTEXT), min(len(lines), index + CONTEXT + 1)):
                keep[k] = True
    out: list[dict[str, str]] = []
    gap = False
    for line, wanted in zip(lines, keep):
        if wanted:
            out.append(line)
            gap = False
        elif not gap:
            out.append({"op": "gap", "text": ""})
            gap = True
    return out[:MAX_LINES], counts


def _new_entries(conn: sqlite3.Connection, project_id: str, person: str, first_at: str, last_at: str) -> list[dict[str, Any]]:
    """진행일지 추가 — 쓰기 기록에는 새 일지 번호가 없다(만들기 전에 남는 주소라). 그 사람이 그 사이에 만든 일지를 찾는다."""
    def shift(value: str, seconds: int) -> str:
        try:
            return (datetime.fromisoformat(value) + timedelta(seconds=seconds)).isoformat(timespec="seconds")
        except ValueError:
            return value
    rows = conn.execute(
        "SELECT id, title, date, body FROM entry WHERE project_id = ? AND author = ? AND created_at >= ? AND created_at <= ?"
        " ORDER BY created_at", (project_id, person, shift(first_at, -10), shift(last_at or first_at, 10))).fetchall()
    return [{"id": r["id"], "title": r["title"], "date": r["date"],
             "lines": [line for line in (r["body"] or "").splitlines() if line.strip()][:3]} for r in rows]


def diff(conn: sqlite3.Connection, project_id: str, entry_id: int | None, action: str, since: str, person: str,
         first_at: str = "", last_at: str = "", base: str = "") -> dict[str, Any]:
    from . import entries as entries_service
    from . import projects as projects_service

    when = _since_time(since)
    result: dict[str, Any] = {"kind": "none", "lines": [], "added": 0, "changed": 0, "removed": 0,
                              "base_at": "", "before": "", "others": [], "new_entries": []}
    if action == "진행일지 추가" and not entry_id:
        result["kind"] = "new"
        result["new_entries"] = _new_entries(conn, project_id, person, first_at, last_at)
        result["added"] = len(result["new_entries"])
        return result
    try:
        if entry_id:
            _row, path = entries_service.entry_path(conn, int(entry_id))
        else:
            path = projects_service.project_dir(conn, project_id) / "index.md"
    except (KeyError, ValueError):
        result["kind"] = "gone"           # 지워진 일지 · 과제
        return result
    if action.startswith("첨부"):
        result["kind"] = "files"
        return result
    try:
        current = path.read_text(encoding="utf-8")
    except OSError:
        result["kind"] = "gone"
        return result
    rel = path.resolve().relative_to(get_settings().vault_dir.resolve()).as_posix()
    after = _text_of(current, action, person)
    if action == "진행일지 추가":
        before: list[str] | None = []
        result["kind"] = "new"
    else:
        before = None
        # 첫 수정이 남긴 보관본(쓰기 기록에 적힌 것) — 옛 기록(없음)은 시각으로 찾는다
        stamp = base if base and any(item["stamp"] == base for item in versions_service.list_for(rel)) else None
        if stamp is None and when:
            stamp = _base_stamp(rel, when)
        if stamp:
            try:
                before = _text_of(versions_service.read(rel, stamp), action, person)
                result["base_at"] = versions_service._readable(stamp)
                result["kind"] = "diff"
            except versions_service.VersionError:
                before = None
    if before is not None:
        result["lines"], counts = _ops(before, after)
        result.update(counts)
        result["before"] = "\n".join(before)
    # 그 뒤 다른 사람도 같은 글을 고쳤나 — 띠에 함께
    if when:
        others = []
        for item in edits_service._lines(when - timedelta(days=1)):
            same = item.get("entry_id") == entry_id if entry_id else (item.get("project_id") == project_id and not item.get("entry_id"))
            later = (item.get("real") or "") > since if item.get("real") else str(item.get("at", "")) > since
            if same and later and item.get("name") and item.get("name") != person and item["name"] not in others:
                others.append(item["name"])
        result["others"] = others
    return result
