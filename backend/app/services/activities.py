"""팀원 역량 이력 (TODO 72).

**과제가 아니다.** 교육·세미나·박람회·학회처럼 사람에게 쌓이는 기록이라
과제 폴더 밑에 두지 않고 `vault/people/<이름>/activities/` 에 따로 쌓는다.

세 가지를 사용자가 정했다 (2026-09-06).

1. **기록 단위는 사람.** 한 행사에 세 명이 가면 기록도 세 건이다.
   행사 단위로 묶으면 사람별 이력을 뽑을 때마다 풀어야 한다 — 팀장이 보는 축은 사람이다.
2. **시간·비용은 옵션.** 비워 두는 것이 정상이고, 채운 것만 합계에 들어간다.
3. **지나간 이력만.** 예정은 담지 않는다. 목적이 "내년에 어떤 교육을 받으면 좋을지"를
   면담에서 이야기하는 것이므로, 계획표가 아니라 **쌓인 실적**이 필요하다.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import ACTIVITY_KIND_KEYS, DEFAULT_ACTIVITY_KIND, get_settings
from ..vault import markdown as md
from ..vault import paths
from . import settings as settings_service

# 앞의 안내 문구는 인용문(>)으로 넣는다. 화면에서 흐리게 보여 실제 내용과 구분되고,
# 사용자는 그 줄을 지우고 쓰면 된다 (과제 개요 서식과 같은 방식).
BODY_TEMPLATE = """## 내용

> 무엇을 듣고 보았는지 — 주요 주제, 인상 깊은 발표 (이 줄을 지우고 작성하세요)

## 적용할 것

> 우리 과제나 공정에 어떻게 쓸 수 있는지
"""

META_ORDER = [
    "person", "date", "end_date", "kind", "title", "host", "place",
    "hours", "cost", "takeaway", "link", "tags",
    "author", "created_at", "updated_at",
]

# 한 행사에 여러 명이 갔을 때 이름을 나누는 기호.
#
# **이 함수가 이 화면의 안전장치다.** 나누지 않고 `"권경락,김현우"` 한 덩이로 저장하면
# 그 문자열이 사람 하나로 굳어, 집계에도 명부에도 유령이 하나 생긴다. 실제로 그렇게 됐다.
# 그래서 나누는 일은 **화면이 아니라 여기(서버)에서** 한다 — 화면만 고치면 API 를
# 직접 부르는 길로 같은 사고가 다시 난다.
_PEOPLE_SPLIT = re.compile(r"[,;\n]+")


def split_people(value: object) -> list[str]:
    """`"권경락, 김현우"` → `["권경락", "김현우"]`. 순서를 지키고 중복은 버린다."""
    names: list[str] = []
    for chunk in _PEOPLE_SPLIT.split(str(value or "")):
        name = chunk.strip()
        if name and name not in names:
            names.append(name)
    return names


def now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def person_dir(name: str) -> Path:
    """사람 폴더. 이름은 슬러그로 다듬지만, **진짜 이름은 front matter 의 `person`** 이다.

    폴더명으로 사람을 되찾지 않는 이유는 하나다 — 이름을 바꿀 때 폴더를 못 옮겨도
    기록이 미아가 되지 않아야 한다.
    """
    settings = get_settings()
    return paths.safe_join(settings.people_dir, paths.slugify(name), "activities")


def normalize_number(value: object, label: str) -> float | None:
    """시간·비용. **비우는 것이 정상이다** — 옵션으로 두기로 했다."""
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}은(는) 숫자여야 합니다: {value!r}") from exc
    if number < 0:
        raise ValueError(f"{label}은(는) 0보다 작을 수 없습니다.")
    return number


def _clean(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _validate(data: dict[str, Any]) -> dict[str, Any]:
    # 한 기록은 한 사람의 것이다. 여러 명은 create() 가 사람 수만큼 나눠 부른다.
    people = split_people(data.get("person"))
    if len(people) != 1:
        raise ValueError("누구의 기록인지 골라 주세요.")
    person = people[0]
    title = str(data.get("title") or "").strip()
    if not title:
        raise ValueError("제목을 입력하세요.")
    kind = data.get("kind") or DEFAULT_ACTIVITY_KIND
    if kind not in ACTIVITY_KIND_KEYS:
        raise ValueError(f"알 수 없는 구분: {kind}")
    start = paths.validate_date(data.get("date"))
    end_raw = str(data.get("end_date") or "").strip()
    end = paths.validate_date(end_raw) if end_raw else None
    if end:
        if end < start:
            raise ValueError("종료일이 시작일보다 빠릅니다.")
        # 하루짜리를 같은 날짜 두 번으로 적어 두면 화면이 "~" 를 괜히 붙인다.
        if end == start:
            end = None
    return {
        "person": person,
        "title": title,
        "kind": kind,
        "date": start,
        "end_date": end,
        "host": _clean(data.get("host")),
        "place": _clean(data.get("place")),
        "hours": normalize_number(data.get("hours"), "시간"),
        "cost": normalize_number(data.get("cost"), "비용"),
        "takeaway": _clean(data.get("takeaway")),
        "link": _clean(data.get("link")),
        "tags": [tag for tag in (str(t).strip() for t in (data.get("tags") or [])) if tag],
    }


def file_path(conn: sqlite3.Connection, activity_id: int) -> Path:
    row = conn.execute("SELECT rel_path FROM activity WHERE id = ?", (activity_id,)).fetchone()
    if row is None:
        raise KeyError(activity_id)
    return paths.safe_join(get_settings().vault_dir, row["rel_path"])


def create(conn: sqlite3.Connection, data: dict[str, Any]) -> list[int]:
    """기록을 만든다. **여러 명이면 사람 수만큼 만든다.**

    "권경락, 김현우" 처럼 적어도 기록은 두 건이 된다 — 기록 단위가 사람이기 때문이다.
    한 덩이로 저장하면 집계에 `"권경락,김현우"` 라는 없는 사람이 생긴다 (TODO 74).
    """
    people = split_people(data.get("person"))
    if not people:
        raise ValueError("누구의 기록인지 골라 주세요.")
    return [_create_one(conn, {**data, "person": name}) for name in people]


def _create_one(conn: sqlite3.Connection, data: dict[str, Any]) -> int:
    from ..vault.indexer import index_activities

    fields = _validate(data)
    directory = person_dir(fields["person"])
    directory.mkdir(parents=True, exist_ok=True)

    stamp = now_iso()
    meta = {
        **fields,
        "author": settings_service.current_author(data.get("author")) or None,
        "created_at": stamp,
        "updated_at": stamp,
    }
    target = paths.unique_path(
        directory, f"{fields['date']}-{paths.slugify(fields['title'])}", ".md"
    )
    md.save(target, md.MarkdownDoc(meta, data.get("body") or BODY_TEMPLATE))
    # 명부에 없는 이름이면 넣어 둔다 — 표기 흔들림을 막는 자리가 이미 있다 (TODO 38).
    settings_service.add_person(fields["person"])
    index_activities(conn)
    conn.commit()
    rel = target.relative_to(get_settings().vault_dir).as_posix()
    row = conn.execute("SELECT id FROM activity WHERE rel_path = ?", (rel,)).fetchone()
    return row["id"]


def update(conn: sqlite3.Connection, activity_id: int, updates: dict[str, Any]) -> None:
    from ..vault.indexer import index_activities

    # 고칠 때는 한 명만 받는다. 여기서 나눠 새 기록을 만들어 주면 "고쳤는데 늘어났다"가 된다.
    if "person" in updates and len(split_people(updates["person"])) > 1:
        raise ValueError(
            "한 기록은 한 사람의 것입니다. 여러 명은 [기록 추가]에서 한 번에 넣으세요."
        )
    path = file_path(conn, activity_id)
    doc = md.load(path)
    merged = {**doc.meta, **{k: v for k, v in updates.items() if k != "body"}}
    fields = _validate(merged)

    meta = md.merge_meta(doc.meta, fields)
    meta["updated_at"] = now_iso()
    body = updates.get("body")
    md.save(path, md.MarkdownDoc(meta, doc.body if body is None else body))

    # 사람이나 날짜·제목이 바뀌면 파일이 있어야 할 자리도 바뀐다.
    directory = person_dir(fields["person"])
    directory.mkdir(parents=True, exist_ok=True)
    wanted = f"{fields['date']}-{paths.slugify(fields['title'])}.md"
    if path.parent != directory or path.name != wanted:
        target = directory / wanted
        if target.exists() and target != path:
            target = paths.unique_path(directory, target.stem, ".md")
        paths.move(path, target)

    index_activities(conn)
    conn.commit()


def delete(conn: sqlite3.Connection, activity_id: int) -> None:
    """지우지 않고 .trash/ 로 옮긴다 (과제·진행일지와 같은 방식)."""
    from ..vault.indexer import index_activities
    from . import trash as trash_service

    settings = get_settings()
    path = file_path(conn, activity_id)
    row = conn.execute(
        "SELECT person, date, title FROM activity WHERE id = ?", (activity_id,)
    ).fetchone()
    settings.trash_dir.mkdir(parents=True, exist_ok=True)
    target = paths.unique_path(
        settings.trash_dir, f"{path.stem}-{datetime.now():%Y%m%d%H%M%S}", ".md"
    )
    paths.move(path, target)
    trash_service.record(
        "activity",
        label=f"{row['person']} · {row['date']} {row['title']}" if row else path.stem,
        moved_to=target,
        origin=path,
        project_id=None,
    )
    index_activities(conn)
    conn.commit()


# ── 읽기 ──────────────────────────────────────────────────────────────

def _row(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "person": row["person"],
        "date": row["date"],
        "end_date": row["end_date"],
        "kind": row["kind"],
        "title": row["title"],
        "host": row["host"],
        "place": row["place"],
        "hours": row["hours"],
        "cost": row["cost"],
        "takeaway": row["takeaway"],
        "link": row["link"],
        "body": row["body"],
        "author": row["author"],
        "updated_at": row["updated_at"],
        "tags": [],
    }


def listing(
    conn: sqlite3.Connection,
    person: str | None = None,
    kind: str | None = None,
    year: str | None = None,
    q: str | None = None,
) -> list[dict]:
    sql = "SELECT * FROM activity WHERE 1=1"
    params: list = []
    if person:
        sql += " AND person = ?"
        params.append(person)
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    if year:
        sql += " AND SUBSTR(date, 1, 4) = ?"
        params.append(year)
    if q:
        # 몇 백 건 규모라 LIKE 로 충분하다. 전문 검색 색인까지 끌어들이지 않는다.
        sql += " AND (title LIKE ? OR host LIKE ? OR place LIKE ? OR takeaway LIKE ? OR body LIKE ?)"
        params.extend([f"%{q}%"] * 5)
    sql += " ORDER BY date DESC, id DESC"
    return [_row(conn, row) for row in conn.execute(sql, params)]


def years(conn: sqlite3.Connection) -> list[str]:
    return [
        row["y"]
        for row in conn.execute(
            "SELECT DISTINCT SUBSTR(date, 1, 4) AS y FROM activity ORDER BY y DESC"
        )
    ]


# 면담에서 "요즘 뜸하네요" 라고 말할 수 있는 경계. 반년이다.
QUIET_DAYS = 180
# 추이 막대에 세우는 해의 수
TREND_YEARS = 4


def summary(conn: sqlite3.Connection, year: str | None = None) -> dict:
    """사람별 요약. **면담 자료로 쓰는 것이 목적**이라 공백까지 함께 낸다."""
    today = date_cls.today()
    available = years(conn)
    trend_years = available[:TREND_YEARS][::-1]

    # 명부에 있는 사람은 기록이 없어도 줄을 세운다 — 면담 대상이 빠지면 안 된다.
    names: list[str] = list(settings_service.known_names())
    for row in conn.execute("SELECT DISTINCT person FROM activity ORDER BY person"):
        if row["person"] not in names:
            names.append(row["person"])

    people = []
    for name in names:
        clause = " AND SUBSTR(date, 1, 4) = ?" if year else ""
        params = [name, year] if year else [name]
        row = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(hours), 0) AS hours,"
            "       COALESCE(SUM(cost), 0) AS cost,"
            "       SUM(CASE WHEN hours IS NOT NULL THEN 1 ELSE 0 END) AS with_hours,"
            "       SUM(CASE WHEN cost IS NOT NULL THEN 1 ELSE 0 END) AS with_cost"
            f" FROM activity WHERE person = ?{clause}",
            params,
        ).fetchone()
        by_kind = {
            r["kind"]: r["n"]
            for r in conn.execute(
                f"SELECT kind, COUNT(*) AS n FROM activity WHERE person = ?{clause} GROUP BY kind",
                params,
            )
        }
        trend = {
            r["y"]: r["n"]
            for r in conn.execute(
                "SELECT SUBSTR(date, 1, 4) AS y, COUNT(*) AS n FROM activity"
                " WHERE person = ? GROUP BY y",
                (name,),
            )
        }
        last = conn.execute(
            "SELECT MAX(date) AS d FROM activity WHERE person = ?", (name,)
        ).fetchone()["d"]
        days_since = None
        if last:
            try:
                days_since = (today - date_cls.fromisoformat(last)).days
            except ValueError:
                days_since = None
        people.append(
            {
                "name": name,
                "count": row["n"],
                "hours": round(row["hours"] or 0, 1),
                "cost": round(row["cost"] or 0),
                # 옵션 칸이라 "합계가 몇 건에서 나온 값인가"를 함께 준다.
                # 그러지 않으면 채운 사람만 비용이 큰 것처럼 보인다.
                "with_hours": row["with_hours"] or 0,
                "with_cost": row["with_cost"] or 0,
                "by_kind": by_kind,
                "trend": {y: trend.get(y, 0) for y in trend_years},
                "last_date": last,
                "days_since": days_since,
                # 면담에서 가장 먼저 꺼낼 줄 — 그 해에 아무것도 없거나 오래 뜸한 사람
                "quiet": row["n"] == 0 or (days_since is not None and days_since >= QUIET_DAYS),
            }
        )
    people.sort(key=lambda item: (-item["count"], item["name"]))

    clause = " WHERE SUBSTR(date, 1, 4) = ?" if year else ""
    params = [year] if year else []
    team = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(hours), 0) AS hours, COALESCE(SUM(cost), 0) AS cost,"
        "       COUNT(DISTINCT person) AS people"
        f" FROM activity{clause}",
        params,
    ).fetchone()

    return {
        "year": year,
        "years": available,
        "trend_years": trend_years,
        "quiet_days": QUIET_DAYS,
        "team": {
            "count": team["n"],
            "hours": round(team["hours"] or 0, 1),
            "cost": round(team["cost"] or 0),
            "people": team["people"],
        },
        "people": people,
    }


__all__ = ["create", "update", "delete", "listing", "summary", "years", "BODY_TEMPLATE"]
