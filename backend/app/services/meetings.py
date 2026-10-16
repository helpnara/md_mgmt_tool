"""팀원 면담 (TODO 182).

역량 이력(72)은 **면담에서 꺼낼 이야깃거리**로 만들었다. 그런데 면담 자체 — 무엇을 이야기했고 무엇을 하기로 했나 — 는
남을 곳이 없었다. 이 모듈이 그 자리다.

* **역량 이력과 섞지 않는다** — 면담은 역량을 쌓은 일이 아니다. 다른 표(`meeting`) · 다른 폴더(`people/<이름>/meetings/`).
* **민감한 기록이다** — 통합 검색 · AI 요약 프롬프트 · 내보내기에 넣지 않는다. 오류 기록에도 내용은 남지 않는다(원래 규칙).
  사람 폴더 안에 따로 두는 것은, 나중에 데이터 폴더를 팀이 함께 쓰게 되면 이 폴더만 빼고 나눌 수 있게 하려는 것이다.
* **HR 시스템이 아니다** — 점수 · 등급 칸은 없다. 팀장의 메모(한 줄 요약 · 본문)와 **하기로 한 것**까지.
* **하기로 한 것**은 닫을 때까지 보인다 — 보고의 "답하지 않은 지시"(107)와 같은 모양. 다음 면담에서 꺼낼 첫 줄이다.
* 예정은 담지 않는다(역량 이력과 같은 원칙)의 예외 하나 — **다음 면담** 날짜 한 칸(선택).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path
from typing import Any

from .. import schemas as rules
from ..config import get_settings
from ..vault import markdown as md
from ..vault import paths
from ..vault import versions
from . import settings as settings_service
from .activities import now_iso, split_people

META_ORDER = ["person", "date", "kind", "summary", "followups", "next_date", "author", "created_at", "updated_at"]

FOLLOWUP_MAX = 30  # 한 면담에서 하기로 한 것 — 이보다 많으면 면담이 아니라 업무 목록이다


def person_dir(name: str) -> Path:
    return paths.safe_join(get_settings().people_dir, paths.slugify(name), "meetings")


def _clean(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _followups(value: object) -> list[dict[str, Any]]:
    """하기로 한 것. `[{"text", "done"}]` 이나 글 목록을 받는다. 빈 줄은 버린다."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("하기로 한 것은 목록이어야 합니다.")
    out: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            text = _clean(item.get("text"))
            done_raw = _clean(item.get("done"))
        else:
            text, done_raw = _clean(item), None
        if not text:
            continue
        done = rules.strict_day(done_raw, "date")  # TODO 205
        out.append({"text": text, "done": done})
    if len(out) > FOLLOWUP_MAX:
        raise ValueError(f"하기로 한 것은 {FOLLOWUP_MAX}줄까지입니다.")
    return out


def _kind(value: object, stored: object = None) -> str | None:
    """면담 구분 — 설정의 목록(비었으면 기본 목록)에 있는 것만 (TODO 214 F15). 비울 수 있다.

    이미 적힌 옛 구분(목록에서 뺀 것)은 그대로 둔다 — 고치지 않은 칸 때문에 다른 칸을 저장 못 하면 안 된다.
    """
    kind = _clean(value)
    if kind is None or kind == _clean(stored):
        return kind
    kinds = settings_service.meeting_kinds()
    if kind not in kinds:
        raise ValueError(f"면담 구분은 {' · '.join(kinds)} 중에서 골라 주세요 (받은 값: {kind[:30]}). 목록은 설정에서 고칩니다.")
    return kind


def _validate(data: dict[str, Any], stored: dict[str, Any] | None = None) -> dict[str, Any]:
    people = split_people(data.get("person"))
    if len(people) != 1:
        raise ValueError("누구와의 면담인지 한 사람을 골라 주세요.")
    # 이름에 경로 기호를 받지 않는다 (TODO 205 ㉞) — `../x` 가 `people/x/` 폴더로 들어가고 이름은 `../x` 로 남았다.
    # 이미 적힌 이름은 그대로(손으로 고친 예전 표기), 새로 적은 이름은 명부와 같은 규칙 — 쉼표 · 40자 (TODO 214 F6)
    person = rules.plain_name(people[0], "person")
    if person != _clean((stored or {}).get("person")):
        person = settings_service.person_name(person)
    kind = _kind(data.get("kind"), (stored or {}).get("kind"))
    # 날짜 — 엄격히, 비우면 오늘 · 다음 면담은 비울 수 있다 (TODO 205)
    meeting_date = rules.strict_day(data.get("date"), "date", default=date_cls.today().isoformat())
    next_date = rules.strict_day(data.get("next_date"), "next_date")
    # 같은 날도 거절 — 화면도 같은 규칙으로 저장 전에 막는다 (TODO 216)
    if next_date and next_date <= meeting_date:
        raise ValueError("다음 면담은 이 면담 뒤여야 합니다.")
    summary = _clean(data.get("summary"))
    if not summary:
        raise ValueError("한 줄 요약을 입력하세요 — 목록에서 무엇을 이야기했는지 보이는 줄입니다.")
    return {
        "person": person,
        "date": meeting_date,
        "kind": kind,
        "summary": summary,
        "followups": _followups(data.get("followups")),
        "next_date": next_date,
    }


def file_path(conn: sqlite3.Connection, meeting_id: int) -> Path:
    row = conn.execute("SELECT rel_path FROM meeting WHERE id = ?", (meeting_id,)).fetchone()
    if row is None:
        raise KeyError(meeting_id)
    return paths.safe_join(get_settings().vault_dir, row["rel_path"])


def _ordered(meta: dict[str, Any]) -> dict[str, Any]:
    return {key: meta.get(key) for key in META_ORDER if key in meta} | {
        key: value for key, value in meta.items() if key not in META_ORDER
    }


def _wanted_name(fields: dict[str, Any]) -> str:
    return f"{fields['date']}-{paths.slugify(fields['kind'] or '면담')}"


def warnings(fields: dict[str, Any]) -> list[str]:
    """막지 않는 안내 (TODO 214) — 명부에 없는 이름 · 떠난 사람(D6 · D7), 면담일이 오늘보다 뒤(D5)."""
    out = settings_service.roster_warnings([fields["person"]])
    if fields["date"] > date_cls.today().isoformat():
        out.append(f"면담일이 오늘보다 뒤입니다 ({fields['date']}) — 예정이면 '다음 면담' 칸에 적어 두는 편이 맞습니다.")
    return out


def create(conn: sqlite3.Connection, data: dict[str, Any], notes: list[str] | None = None) -> int:
    """면담 하나를 만든다. `notes` 에 목록을 넘기면 막지 않는 안내를 담는다.

    **명부에 자동으로 넣지 않는다** (TODO 214 D6) — 오타가 명부에 굳었다. 화면이 "명부에 없는 이름 — 추가할까요?" 를
    묻고 [POST /api/people] 로 넣는다.
    """
    from ..vault.indexer import index_meetings

    fields = _validate(data)
    if notes is not None:
        notes.extend(warnings(fields))
    directory = person_dir(fields["person"])
    directory.mkdir(parents=True, exist_ok=True)
    stamp = now_iso()
    meta = _ordered({
        **fields,
        "author": settings_service.current_author(data.get("author")) or None,
        "created_at": stamp,
        "updated_at": stamp,
    })
    target = paths.unique_path(directory, _wanted_name(fields), ".md")
    md.save(target, md.MarkdownDoc(meta, str(data.get("body") or "")))
    index_meetings(conn)
    conn.commit()
    rel = target.relative_to(get_settings().vault_dir).as_posix()
    return conn.execute("SELECT id FROM meeting WHERE rel_path = ?", (rel,)).fetchone()["id"]


def update(conn: sqlite3.Connection, meeting_id: int, updates: dict[str, Any], notes: list[str] | None = None) -> None:
    from ..vault.indexer import index_meetings

    path = file_path(conn, meeting_id)
    doc = md.load(path)
    merged = {**doc.meta, **{key: value for key, value in updates.items() if key != "body"}}
    fields = _validate(merged, doc.meta)
    if notes is not None:
        notes.extend(warnings(fields))
    meta = _ordered({**doc.meta, **fields, "updated_at": now_iso()})
    body = updates.get("body")
    md.save(path, md.MarkdownDoc(meta, doc.body if body is None else str(body)))

    # 사람 · 날짜 · 구분이 바뀌면 파일이 있어야 할 자리도 바뀐다
    directory = person_dir(fields["person"])
    directory.mkdir(parents=True, exist_ok=True)
    wanted = f"{_wanted_name(fields)}.md"
    if path.parent != directory or path.name != wanted:
        target = directory / wanted
        if target.exists() and target != path:
            target = paths.unique_path(directory, target.stem, ".md")
        paths.move(path, target)
        versions.follow(path, target)
    index_meetings(conn)
    conn.commit()


def delete(conn: sqlite3.Connection, meeting_id: int) -> None:
    """지우지 않고 .trash/ 로 옮긴다 — 역량 이력과 같다. 화면이 "보관함 · 이전 버전에 남는다" 를 알린다."""
    from ..vault.indexer import index_meetings
    from . import trash as trash_service

    settings = get_settings()
    path = file_path(conn, meeting_id)
    row = conn.execute("SELECT person, date, kind FROM meeting WHERE id = ?", (meeting_id,)).fetchone()
    settings.trash_dir.mkdir(parents=True, exist_ok=True)
    target = paths.unique_path(settings.trash_dir, f"{path.stem}-{datetime.now():%Y%m%d%H%M%S}", ".md")
    paths.move(path, target)
    trash_service.record(
        "meeting",
        label=f"{row['person']} · {row['date']} 면담" if row else path.stem,
        moved_to=target,
        origin=path,
        project_id=None,
    )
    index_meetings(conn)
    conn.commit()


# ── 읽기 ──────────────────────────────────────────────────────────────

def _row(row: sqlite3.Row) -> dict[str, Any]:
    try:
        followups = json.loads(row["followups"] or "[]")
    except ValueError:
        followups = []
    return {
        "id": row["id"],
        "person": row["person"],
        "date": row["date"],
        "kind": row["kind"],
        "summary": row["summary"],
        "followups": followups,
        "open_followups": row["open_followups"],
        "next_date": row["next_date"],
        "body": row["body"],
        "author": row["author"],
        "updated_at": row["updated_at"],
    }


def listing(conn: sqlite3.Connection, person: str | None = None, year: str | None = None) -> list[dict]:
    sql, params = "SELECT * FROM meeting WHERE 1=1", []
    if person:
        sql += " AND person = ?"
        params.append(person)
    if year:
        sql += " AND SUBSTR(date, 1, 4) = ?"
        params.append(year)
    sql += " ORDER BY date DESC, id DESC"
    return [_row(row) for row in conn.execute(sql, params)]


def open_followups(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """팀 전체의 아직 닫지 않은 "하기로 한 것" — 오래된 것부터."""
    out = []
    for row in conn.execute("SELECT * FROM meeting WHERE open_followups > 0 ORDER BY date, id"):
        item = _row(row)
        for index, followup in enumerate(item["followups"]):
            if not followup.get("done"):
                out.append({"meeting_id": item["id"], "index": index, "person": item["person"],
                            "date": item["date"], "text": followup.get("text")})
    return out


def by_person(conn: sqlite3.Connection, year: str | None = None) -> dict[str, dict[str, Any]]:
    """사람별 — 마지막 면담 · 그 해 면담 수 · 열린 후속 조치 · 다음 면담 · 면담할 때가 지났는가."""
    today = date_cls.today()
    cycle = settings_service.meeting_cycle_days()
    out: dict[str, dict[str, Any]] = {}
    for row in conn.execute(
        "SELECT person, MAX(date) AS last, SUM(open_followups) AS open,"
        "       SUM(CASE WHEN ? = '' OR SUBSTR(date, 1, 4) = ? THEN 1 ELSE 0 END) AS n"
        " FROM meeting GROUP BY person",
        (year or "", year or ""),
    ):
        nxt = conn.execute(
            "SELECT next_date FROM meeting WHERE person = ? ORDER BY date DESC, id DESC LIMIT 1", (row["person"],)
        ).fetchone()["next_date"]
        try:
            days = (today - date_cls.fromisoformat(row["last"])).days
        except (TypeError, ValueError):
            days = None
        overdue_next = bool(nxt and nxt < today.isoformat())
        out[row["person"]] = {
            "meetings": row["n"] or 0,
            "last_meeting": row["last"],
            "meeting_days_since": days,
            "open_followups": row["open"] or 0,
            "next_meeting": nxt,
            # 면담할 때가 지났다 — 정한 다음 면담일이 지났거나, 마지막 면담에서 주기가 지났다
            "meeting_due": overdue_next or (days is not None and days >= cycle),
        }
    return out


__all__ = ["create", "update", "delete", "listing", "open_followups", "by_person"]
