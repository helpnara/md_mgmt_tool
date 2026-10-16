"""vault 스캔 → SQLite 인덱스 갱신.

파일이 진실의 원천이므로 인덱스는 항상 파일을 보고 다시 만든다.
외부 편집기(Obsidian 등)로 고친 내용도 이 경로로 반영된다.
"""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path
from typing import Any, NamedTuple

from ..config import LEGACY_STATUS_MAP, STATUS_KEYS, STATUS_LABELS, get_settings, normalize_status
from ..services import settings as settings_service
from .. import schemas as rules
from . import markdown as md


class IndexProblem(NamedTuple):
    """읽지 못한 파일. 사용자에게 알려 주고 나머지는 계속 인덱싱한다."""

    rel_path: str
    reason: str


# 마지막으로 온 vault 를 훑었을 때의 문제 (TODO 164). 켤 때의 검은 창과 [다시 읽기] 에서만 보이면
# 사용자는 모른다 — 홈·과제목록이 늘 보이는 자리에 띄운다(api/meta 의 `problems`).
LAST_PROBLEMS: list[IndexProblem] = []


def _as_date(meta: dict, key: str, rel_path: str, problems: list[IndexProblem] | None) -> str | None:
    """날짜 칸. 읽을 수 없는 값이면 **그 값만** 비우고 알린다 (TODO 164).

    전에는 `2026-02-30` 하나로 파일 전체를 못 읽어 과제가 목록 · 홈 · 보고대상에서 통째로 사라졌다.
    파일은 그대로 둔다 — 사람이 고치면 다음 [다시 읽기] 에서 돌아온다.
    """
    value = meta.get(key)
    if value is None or value == "":
        return None
    if isinstance(value, (date_cls, datetime)):
        return _as_str(value)
    text = str(value).strip()
    try:
        day = date_cls.fromisoformat(text[:10])
        if len(text) >= 10 and text[4] == "-" and text[7] == "-":
            if problems is not None and not rules.DAY_MIN_YEAR <= day.year <= rules.DAY_MAX_YEAR:
                # 값은 그대로 보이되 알린다 (TODO 214 D5 · D18) — 9999 년 하나가 "최근 갱신" 을 고정했다
                problems.append(IndexProblem(rel_path, f"{key} 값({text})이 {rules.DAY_MIN_YEAR}~{rules.DAY_MAX_YEAR}년 밖입니다 — 오타인지 확인한 뒤 [다시 읽기]"))
            return text
    except ValueError:
        pass
    if problems is not None:
        problems.append(IndexProblem(rel_path, f"{key} 값({text})을 날짜로 읽지 못해 이 값 없이 보입니다 — 파일을 고친 뒤 [다시 읽기]"))
    return None


def _load_doc(path: Path, root: Path, problems: list[IndexProblem] | None) -> md.MarkdownDoc | None:
    """front matter가 깨진 파일 하나 때문에 전체 인덱싱이 멈추지 않게 한다."""
    try:
        return md.load(path)
    except Exception as exc:  # YAML 오류, 인코딩 오류 등 무엇이든
        if problems is not None:
            reason = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
            problems.append(IndexProblem(path.relative_to(root).as_posix(), reason))
        return None


def _as_str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (date_cls,)):
        return value.isoformat()
    return str(value)


def _as_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


def _as_bool(value: object) -> bool:
    """손으로 고친 파일에 `true` / `"예"` / `1` 무엇이 들어와도 뜻대로 읽는다."""
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "yes", "y", "1", "예"}


def _as_effect(value: object) -> float | None:
    """효과 금액(억원/년). 손으로 고친 파일에 숫자가 아닌 값이 들어와도 색인을 멈추지 않는다."""
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _checked_effect(meta: dict, key: str, rel_path: str, problems: list[IndexProblem] | None) -> float | None:
    """효과 금액 칸 (TODO 214 D18) — 숫자가 아니거나 음수 · 무한대 · API 상한(`schemas.NUMBER_MAX`)을 넘으면
    **그 값 없이** 보이고 알린다. 예전에는 말없이 버렸다(1e300 은 합계를 넘쳐 500 이 될 뻔했다)."""
    value = meta.get(key)
    if value is None or value == "":
        return None
    reason = None
    number = None
    if isinstance(value, bool):
        reason = "숫자가 아닙니다"
    else:
        try:
            number = float(value)
        except (TypeError, ValueError):
            reason = "숫자가 아닙니다"
        else:
            if number != number or number in (float("inf"), float("-inf")):
                reason = "무한대 · NaN 입니다"
            elif number < 0:
                reason = "0보다 작습니다"
            elif number > rules.NUMBER_MAX:
                reason = f"너무 큽니다(최대 {rules.NUMBER_MAX:,.0f})"
    if reason is None:
        return number
    if problems is not None:
        problems.append(IndexProblem(
            rel_path, f"{key} 값({str(value)[:40]})이 {reason} — 이 값 없이 보입니다. 파일을 고친 뒤 [다시 읽기]"))
    return None


def _name_day(name: str) -> str | None:
    """파일 · 폴더 이름 앞 열 자리가 실제 날짜면 그 날짜 (TODO 214 F7)."""
    head = name[:10]
    if len(head) == 10 and head[4] == "-" and head[7] == "-":
        try:
            return date_cls.fromisoformat(head).isoformat()
        except ValueError:
            return None
    return None


def _day_or_mtime(
    meta: dict, key: str, path: Path, name: str, rel_path: str, problems: list[IndexProblem] | None
) -> str:
    """날짜 칸 → 이름의 날짜 → **파일 수정일** 순으로 (TODO 214 F7 · D18).

    예전에는 이름이 날짜로 시작하지 않으면 `notes.md` 같은 글자가 날짜 자리에 들어가 정렬 · 연도 거르기가 틀어졌다.
    """
    day = _as_date(meta, key, rel_path, problems) or _name_day(name)
    if day:
        return day
    fallback = datetime.fromtimestamp(path.stat().st_mtime).date().isoformat()
    if problems is not None:
        problems.append(IndexProblem(
            rel_path, f"{key} 를 머리 정보에서도 파일 이름에서도 읽지 못해 파일 수정일({fallback})로 보입니다 — "
            f"머리 정보에 {key}: 2026-03-01 처럼 적은 뒤 [다시 읽기]"))
    return fallback


def _sync_tags(conn: sqlite3.Connection, table: str, column: str, owner_id: Any, tags: list[str]) -> None:
    """태그를 잇는다. 대소문자 · 띄어쓰기 · 앞의 `#` 만 다른 태그는 **같은 태그**로 — 먼저 있던 표기로 보인다
    (TODO 214 D12). 파일은 고치지 않는다(다음 저장 때 맞춰진다)."""
    conn.execute(f"DELETE FROM {table} WHERE {column} = ?", (owner_id,))
    if not tags:
        return
    known: dict[str, int] = {}
    for row in conn.execute("SELECT id, name FROM tag ORDER BY id"):
        known.setdefault(rules.tag_key(row["name"]), row["id"])
    for name in tags:
        key = rules.tag_key(name)
        if not key:
            continue
        tag_id = known.get(key)
        if tag_id is None:
            spelled = rules.clean_tag(name)
            conn.execute("INSERT OR IGNORE INTO tag(name) VALUES (?)", (spelled,))
            tag_id = conn.execute("SELECT id FROM tag WHERE name = ?", (spelled,)).fetchone()["id"]
            known[key] = tag_id
        conn.execute(
            f"INSERT OR IGNORE INTO {table}({column}, tag_id) VALUES (?, ?)",
            (owner_id, tag_id),
        )


def _sync_owners(conn: sqlite3.Connection, project_id: str, owners: list[str]) -> None:
    conn.execute("DELETE FROM project_owner WHERE project_id = ?", (project_id,))
    for position, name in enumerate(owners):
        conn.execute(
            "INSERT OR IGNORE INTO project_owner(project_id, name, position) VALUES (?, ?, ?)",
            (project_id, name, position),
        )


def _sync_predecessors(conn: sqlite3.Connection, project_id: str, predecessors: list[str]) -> None:
    """선행 과제 (TODO 172) — 여럿일 수 있다. 자기 자신은 건너뛴다(손으로 고친 파일)."""
    conn.execute("DELETE FROM project_predecessor WHERE project_id = ?", (project_id,))
    for predecessor in predecessors:
        if predecessor and predecessor != project_id:
            conn.execute(
                "INSERT OR IGNORE INTO project_predecessor(project_id, predecessor_id) VALUES (?, ?)",
                (project_id, predecessor),
            )


def _sync_partners(conn: sqlite3.Connection, project_id: str, partners: list[dict]) -> None:
    """유관부서 (TODO 92). (팀, 사람) 한 쌍이 한 줄이다.

    담당자가 비어 있는 팀은 `person = ''` 한 줄로 남긴다 — 팀만 정해진 상태도 사실이라
    검색과 필터에서 찾을 수 있어야 한다.
    """
    conn.execute("DELETE FROM project_partner WHERE project_id = ?", (project_id,))
    position = 0
    for row in partners:
        team = str(row.get("team") or "").strip()
        if not team:
            continue
        people = [str(name).strip() for name in (row.get("people") or [])]
        for person in people or [""]:
            conn.execute(
                "INSERT OR IGNORE INTO project_partner(project_id, team, person, position)"
                " VALUES (?, ?, ?, ?)",
                (project_id, team, person, position),
            )
            position += 1


def _as_partners(value: object) -> list[dict]:
    """front matter 의 `partners` 를 읽는다. 손으로 고친 문서도 삼키지 않는다."""
    if not isinstance(value, list):
        return []
    out = []
    for row in value:
        if isinstance(row, dict):
            team = _as_str(row.get("team"))
            if team:
                out.append({"team": team, "people": _as_list(row.get("people"))})
        elif isinstance(row, str) and row.strip():
            # 팀 이름만 적어 둔 줄도 받아 준다.
            out.append({"team": row.strip(), "people": []})
    return out


def _index_entries(
    conn: sqlite3.Connection,
    project_id: str,
    project_dir: Path,
    problems: list[IndexProblem] | None = None,
) -> str | None:
    """진행일지를 인덱싱하고 가장 최근 수정 시각을 돌려준다."""
    logs_dir = project_dir / "logs"
    seen: list[str] = []
    latest: str | None = None
    for path in sorted(logs_dir.glob("*.md")) if logs_dir.exists() else []:
        doc = _load_doc(path, project_dir.parent.parent, problems)
        if doc is None:
            # 깨진 파일은 건너뛰되 인덱스에서 지우지는 않는다 (직전 내용을 유지).
            seen.append(path.relative_to(project_dir).as_posix())
            continue
        rel_path = path.relative_to(project_dir).as_posix()
        # 날짜 → 파일 이름의 날짜 → 파일 수정일 (TODO 214 F7)
        entry_date = _day_or_mtime(
            doc.meta, "date", path, path.name, path.relative_to(project_dir.parent.parent).as_posix(), problems
        )
        title = _as_str(doc.meta.get("title")) or path.stem
        updated_at = _as_str(doc.meta.get("updated_at"))
        conn.execute(
            """
            INSERT INTO entry(project_id, rel_path, date, title, author, body,
                              created_at, updated_at, file_mtime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, rel_path) DO UPDATE SET
              date=excluded.date, title=excluded.title, author=excluded.author, body=excluded.body,
              created_at=excluded.created_at, updated_at=excluded.updated_at,
              file_mtime=excluded.file_mtime
            """,
            (
                project_id,
                rel_path,
                entry_date,
                title,
                _as_str(doc.meta.get("author")),
                doc.body,
                _as_str(doc.meta.get("created_at")),
                updated_at,
                path.stat().st_mtime,
            ),
        )
        row = conn.execute(
            "SELECT id FROM entry WHERE project_id = ? AND rel_path = ?", (project_id, rel_path)
        ).fetchone()
        _sync_tags(conn, "entry_tag", "entry_id", row["id"], _as_list(doc.meta.get("tags")))
        seen.append(rel_path)
        for candidate in (updated_at, entry_date):
            if candidate and (latest is None or candidate > latest):
                latest = candidate

    placeholders = ",".join("?" * len(seen))
    if seen:
        conn.execute(
            f"DELETE FROM entry WHERE project_id = ? AND rel_path NOT IN ({placeholders})",
            (project_id, *seen),
        )
    else:
        conn.execute("DELETE FROM entry WHERE project_id = ?", (project_id,))
    return latest


def project_id_from_dir_name(dir_name: str) -> str:
    """폴더명에서 과제 id 를 얻는다. 두 형태를 모두 읽는다.

        2026-001-제목        →  2026-001
        2026-소재-001-제목    →  2026-소재-001

    규칙: 맨 앞 네 자리 연도로 시작하고, 그 뒤 **처음 나오는 숫자 토막**이 일련번호다.
    그 사이에 있는 것이 팀 코드다. (팀 코드는 숫자만으로 지을 수 없게 막아 두었다 —
    그래야 일련번호와 헷갈리지 않는다)

    이 함수는 front matter 의 id 를 못 읽었을 때만 쓰는 예비 수단이다.
    """
    parts = dir_name.split("-")
    if len(parts) < 2 or not (len(parts[0]) == 4 and parts[0].isdigit()):
        return dir_name
    for index in range(1, len(parts)):
        if parts[index].isdigit():
            return "-".join(parts[: index + 1])
    return dir_name


def _starts_with_bom(path: Path) -> bool:
    """파일 맨 앞 세 바이트가 UTF-8 BOM 인가 (TODO 198)."""
    try:
        with path.open("rb") as handle:
            return handle.read(3) == b"\xef\xbb\xbf"
    except OSError:
        return False


def refresh_problems(prefix: str, found: list[IndexProblem]) -> None:
    """폴더 하나를 다시 읽었을 때 그 폴더의 문제만 바꿔 끼운다 (TODO 164) — 도구에서 날짜를 고쳐
    저장하면 경고가 바로 사라지고, [다시 읽기] 를 기다리지 않는다."""
    LAST_PROBLEMS[:] = [item for item in LAST_PROBLEMS if not item.rel_path.startswith(prefix)] + found


def index_project(
    conn: sqlite3.Connection, project_dir: Path, problems: list[IndexProblem] | None = None
) -> str | None:
    """과제 폴더 하나를 인덱싱한다. 반환값은 과제 id."""
    if problems is None:
        local: list[IndexProblem] = []
        result = index_project(conn, project_dir, local)
        if result:
            local.extend(predecessor_problems(conn, [result]))  # TODO 214 D18
        refresh_problems(f"projects/{project_dir.name}/", local)
        return result
    index_md = project_dir / "index.md"
    if not index_md.exists():
        return None

    doc = _load_doc(index_md, project_dir.parent.parent, problems)
    if doc is None:
        # 개요 문서를 못 읽으면 이 과제는 이번 회차에 건드리지 않는다.
        return project_id_from_dir_name(project_dir.name)
    rel_index = index_md.relative_to(project_dir.parent.parent).as_posix()
    # TODO 198 — 머리 정보(front matter)가 없거나 못 읽은 index.md 는 **빈 과제로 색인하지 않는다.**
    # 전에는 제목 = 폴더명 · 담당 · 날짜 · 효과가 모두 빈 과제로 조용히 올라가, 상태 하나만 바꿔도
    # 저장이 원래 front matter 를 본문 글자로 밀어냈다. 알리고, 직전에 색인한 내용은 그대로 둔다.
    if not doc.meta:
        problems.append(IndexProblem(
            rel_index,
            "index.md 의 머리 정보(front matter)를 읽지 못해 이번 색인에서 건너뜁니다 — "
            "파일 맨 앞의 BOM 또는 `---` 를 확인하세요",
        ))
        return project_id_from_dir_name(project_dir.name)
    if _starts_with_bom(index_md):
        # 읽기는 했다(markdown.loads 가 BOM 을 뗀다). 다만 다른 도구는 못 읽을 수 있으니 알려 둔다 —
        # 이 도구로 한 번 저장하면 BOM 없이 다시 쓰여 사라진다.
        problems.append(IndexProblem(
            rel_index,
            "index.md 맨 앞에 BOM(바이트 순서 표식)이 있습니다 — 이번에는 읽었지만 다른 프로그램은 머리 정보를 "
            "못 읽을 수 있습니다. 메모장 대신 UTF-8(BOM 없음)로 저장하거나, 이 도구에서 한 번 저장하면 사라집니다",
        ))
    project_id = _as_str(doc.meta.get("id")) or project_id_from_dir_name(project_dir.name)
    if project_id != project_id_from_dir_name(project_dir.name):
        # TODO 199 — 손으로 고친 `id:`. 색인은 파일의 번호를 따르되(파일이 진실), 폴더 이름과 어긋난 사실은 알린다 —
        # 조용히 넘기면 탐색기의 폴더와 화면의 번호가 서로 다른 채로 남는다.
        problems.append(IndexProblem(
            rel_index,
            f"index.md 의 번호(id: {project_id})가 폴더 이름({project_dir.name})과 다릅니다 — 파일의 id 를 되돌리거나 "
            "폴더 이름을 번호에 맞춰 주세요(설정 → 과제 번호 체계)",
        ))
    # owners(복수)가 우선이고, 예전 문서의 owner(단수)도 그대로 읽는다.
    owners = _as_list(doc.meta.get("owners")) or _as_list(doc.meta.get("owner"))
    # 예전에 상태로 쓰이던 '기획보고' 같은 값은 상태+속성으로 나눠 읽는다.
    raw_status = _as_str(doc.meta.get("status"))
    status, implied_type = normalize_status(raw_status)
    if raw_status and raw_status not in STATUS_KEYS and raw_status not in LEGACY_STATUS_MAP:
        # 모르는 상태값 — 말없이 진행중으로 읽었다 (TODO 214 D18). 그렇게 보이되 알린다.
        problems.append(IndexProblem(
            rel_index,
            f"상태 값({raw_status})을 알 수 없어 '{STATUS_LABELS[status]}'으로 보입니다 — "
            f"{', '.join(STATUS_KEYS)} 중 하나로 고친 뒤 [다시 읽기]",
        ))
    project_type = _as_str(doc.meta.get("type")) or implied_type
    # 설정에 없는 속성은 색인에서만 비운다 — **파일은 그대로 둔다** (TODO 100).
    # 설정을 되돌리면 다음 색인에서 그대로 살아난다. 비워 보인다는 사실은 알린다 (TODO 214 D18).
    if project_type and project_type not in settings_service.type_keys():
        problems.append(IndexProblem(
            rel_index,
            f"속성 값({project_type})이 설정의 과제 속성 목록에 없어 '미지정'으로 보입니다 — "
            "설정에 되돌리거나 파일을 고친 뒤 [다시 읽기]",
        ))
        project_type = None
    elif project_type not in settings_service.type_keys():
        project_type = None
    updated_at = _as_str(doc.meta.get("updated_at"))
    start_date = _as_date(doc.meta, "start_date", rel_index, problems)
    due_date = _as_date(doc.meta, "due_date", rel_index, problems)
    completed_at = _as_date(doc.meta, "completed_at", rel_index, problems)
    if start_date and due_date and due_date[:10] < start_date[:10]:
        # 기간이 거꾸로 — 화면 · API 로는 만들 수 없다. 손으로 고친 파일 (TODO 214 D18)
        problems.append(IndexProblem(
            rel_index, f"마감일({due_date})이 시작일({start_date})보다 빠릅니다 — 파일을 고친 뒤 [다시 읽기]"))
    if status == "done" and not completed_at:
        problems.append(IndexProblem(
            rel_index, "완료인데 완료일(completed_at)이 없습니다 — 완료한 해에 세지 못합니다. "
            "완료일을 적은 뒤 [다시 읽기] (이 도구에서 한 번 저장하면 오늘로 채워집니다)"))

    # TODO 199 — index.md 의 `id:` 를 손으로 고치면 같은 폴더의 옛 줄이 남아 `dir_name UNIQUE` 에 걸려
    # 재색인이 500, 재시작은 IntegrityError 로 안 켜졌다. 같은 폴더를 가리키는 다른 번호의 줄을 먼저 비운다
    # (딸린 진행일지 · 보고 · 첨부 줄은 CASCADE 로 따라 지워지고 아래에서 새 번호로 다시 색인된다).
    conn.execute("DELETE FROM project WHERE dir_name = ? AND id <> ?", (project_dir.name, project_id))

    conn.execute(
        """
        INSERT INTO project(id, dir_name, title, status, type, grp, owner, start_date, due_date,
                            effect_expected, effect_verified, no_report, no_effect, created_by,
                            completed_at, nature, category, delivery, cost_kind, intake_id,
                            created_at, updated_at, body, file_mtime)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          dir_name=excluded.dir_name, title=excluded.title, status=excluded.status,
          type=excluded.type, grp=excluded.grp, owner=excluded.owner, start_date=excluded.start_date,
          due_date=excluded.due_date,
          effect_expected=excluded.effect_expected, effect_verified=excluded.effect_verified,
          no_report=excluded.no_report,
          no_effect=excluded.no_effect,
          created_by=excluded.created_by, completed_at=excluded.completed_at,
          nature=excluded.nature, category=excluded.category, delivery=excluded.delivery,
          cost_kind=excluded.cost_kind, intake_id=excluded.intake_id,
          created_at=excluded.created_at,
          updated_at=excluded.updated_at, body=excluded.body, file_mtime=excluded.file_mtime
        """,
        (
            project_id,
            project_dir.name,
            _as_str(doc.meta.get("title")) or project_dir.name,
            status,
            project_type,
            _as_str(doc.meta.get("group")),
            ", ".join(owners) or None,
            start_date,
            due_date,
            _checked_effect(doc.meta, "effect_expected", rel_index, problems),  # TODO 214 D18
            _checked_effect(doc.meta, "effect_verified", rel_index, problems),
            1 if _as_bool(doc.meta.get("no_report")) else 0,
            1 if _as_bool(doc.meta.get("no_effect")) else 0,
            _as_str(doc.meta.get("created_by")),
            completed_at,
            _as_str(doc.meta.get("nature")),
            _as_str(doc.meta.get("category")),
            _as_str(doc.meta.get("delivery")),
            _as_str(doc.meta.get("cost_kind")),
            _as_str(doc.meta.get("intake_id")),
            _as_str(doc.meta.get("created_at")),
            updated_at,
            doc.body,
            index_md.stat().st_mtime,
        ),
    )
    _sync_tags(conn, "project_tag", "project_id", project_id, _as_list(doc.meta.get("tags")))
    _sync_owners(conn, project_id, owners)
    _sync_partners(conn, project_id, _as_partners(doc.meta.get("partners")))
    _sync_predecessors(conn, project_id, _as_list(doc.meta.get("predecessors")))

    latest_entry = _index_entries(conn, project_id, project_dir, problems)
    if latest_entry and (updated_at is None or latest_entry > updated_at):
        conn.execute("UPDATE project SET updated_at = ? WHERE id = ?", (latest_entry, project_id))

    _index_reports(conn, project_id, project_dir, problems)
    _index_attachments(conn, project_id, project_dir)
    _rebuild_search(conn, project_id)
    return project_id


def _index_reports(
    conn: sqlite3.Connection,
    project_id: str,
    project_dir: Path,
    problems: list[IndexProblem] | None = None,
) -> None:
    """reports/<날짜>/report.md 를 인덱싱하고, 포함된 진행일지를 연결한다."""
    reports_dir = project_dir / "reports"
    seen: list[str] = []
    for path in sorted(reports_dir.glob("*/report.md")) if reports_dir.exists() else []:
        doc = _load_doc(path, project_dir.parent.parent, problems)
        if doc is None:
            seen.append(path.relative_to(project_dir).as_posix())
            continue
        rel_path = path.relative_to(project_dir).as_posix()
        # 문제의 경로는 **데이터 폴더 기준**이어야 저장할 때 `refresh_problems` 가 지운다 — 과제 폴더 기준이라
        # 저장할 때마다 같은 문제가 하나씩 늘었다 (TODO 214 F4). 날짜는 머리 정보 → 폴더 이름 → 파일 수정일 (F7).
        report_date = _day_or_mtime(
            doc.meta, "report_date", path, path.parent.name, path.relative_to(project_dir.parent.parent).as_posix(), problems
        )
        conn.execute(
            """
            INSERT INTO report(project_id, report_date, title, rel_path, covers_from, covers_to,
                               author, body, frozen_at, report_type, audience,
                               feedback, feedback_done, file_mtime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, rel_path) DO UPDATE SET
              report_date=excluded.report_date, title=excluded.title,
              covers_from=excluded.covers_from, covers_to=excluded.covers_to,
              author=excluded.author,
              body=excluded.body, frozen_at=excluded.frozen_at,
              report_type=excluded.report_type, audience=excluded.audience,
              feedback=excluded.feedback, feedback_done=excluded.feedback_done,
              file_mtime=excluded.file_mtime
            """,
            (
                project_id,
                report_date,
                _as_str(doc.meta.get("title")) or f"{report_date} 보고",
                rel_path,
                _as_str(doc.meta.get("covers_from")),
                _as_str(doc.meta.get("covers_to")),
                _as_str(doc.meta.get("author")),
                doc.body,
                _as_str(doc.meta.get("frozen_at")),
                _as_str(doc.meta.get("report_type")),
                _as_str(doc.meta.get("audience")),
                _as_str(doc.meta.get("feedback")),
                _as_str(doc.meta.get("feedback_done")),
                path.stat().st_mtime,
            ),
        )
        report_row = conn.execute(
            "SELECT id FROM report WHERE project_id = ? AND rel_path = ?", (project_id, rel_path)
        ).fetchone()

        # 보고가 담은 진행일지 연결 — '미보고 분량' 계산의 근거가 된다.
        conn.execute("DELETE FROM report_entry WHERE report_id = ?", (report_row["id"],))
        for entry_rel in _as_list(doc.meta.get("covered_entries")):
            entry = conn.execute(
                "SELECT id FROM entry WHERE project_id = ? AND rel_path = ?", (project_id, entry_rel)
            ).fetchone()
            if entry:
                conn.execute(
                    "INSERT OR IGNORE INTO report_entry(report_id, entry_id) VALUES (?, ?)",
                    (report_row["id"], entry["id"]),
                )
        seen.append(rel_path)

    if seen:
        placeholders = ",".join("?" * len(seen))
        conn.execute(
            f"DELETE FROM report WHERE project_id = ? AND rel_path NOT IN ({placeholders})",
            (project_id, *seen),
        )
    else:
        conn.execute("DELETE FROM report WHERE project_id = ?", (project_id,))

    latest = conn.execute(
        "SELECT MAX(report_date) AS last FROM report WHERE project_id = ? AND frozen_at IS NOT NULL",
        (project_id,),
    ).fetchone()
    conn.execute(
        "UPDATE project SET last_reported_at = ? WHERE id = ?", (latest["last"], project_id)
    )


def _index_attachments(conn: sqlite3.Connection, project_id: str, project_dir: Path) -> None:
    """assets/ 아래 실제 파일을 인덱싱하고, 본문에서 참조하는 일지와 연결한다.

    외부에서 파일을 직접 넣어 둔 경우에도 목록에 잡히게 하기 위함이다.
    """
    from ..services.attachments import ENTRY_DOC_DIR, guess_mime, referenced_paths  # 순환 참조 방지

    entries = conn.execute(
        "SELECT id, rel_path, body FROM entry WHERE project_id = ?", (project_id,)
    ).fetchall()
    owner_of: dict[str, int] = {}
    for entry in entries:
        for ref in referenced_paths([(entry["body"] or "", ENTRY_DOC_DIR)]):
            owner_of.setdefault(ref, entry["id"])

    # 진행일지 첨부(assets/)와 보고 자료(reports/<날짜>/assets/)를 모두 훑는다.
    candidates: list[Path] = []
    for directory in (project_dir / "assets", project_dir / "reports"):
        if directory.exists():
            candidates.extend(sorted(directory.rglob("*")))

    seen: list[str] = []
    for path in candidates:
        if not path.is_file() or path.suffix == ".md":
            continue
        rel_path = path.relative_to(project_dir).as_posix()
        size = path.stat().st_size
        known = conn.execute(
            "SELECT id, size_bytes, sha256 FROM attachment WHERE project_id = ? AND rel_path = ?",
            (project_id, rel_path),
        ).fetchone()
        # 크기가 그대로면 해시를 다시 계산하지 않는다 (대용량 파일 대비).
        if known and known["size_bytes"] == size and known["sha256"]:
            digest = known["sha256"]
        else:
            digest = _sha256_of(path)
        conn.execute(
            """
            INSERT INTO attachment(project_id, entry_id, rel_path, orig_name, mime, size_bytes,
                                   sha256, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, rel_path) DO UPDATE SET
              entry_id=COALESCE(excluded.entry_id, attachment.entry_id),
              mime=excluded.mime, size_bytes=excluded.size_bytes, sha256=excluded.sha256
            """,
            (
                project_id,
                owner_of.get(rel_path),
                rel_path,
                path.name.split("-", 1)[-1] if path.name[:3].isdigit() else path.name,
                guess_mime(path.name, None),
                size,
                digest,
                datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
            ),
        )
        seen.append(rel_path)

    if seen:
        placeholders = ",".join("?" * len(seen))
        conn.execute(
            f"DELETE FROM attachment WHERE project_id = ? AND rel_path NOT IN ({placeholders})",
            (project_id, *seen),
        )
    else:
        conn.execute("DELETE FROM attachment WHERE project_id = ?", (project_id,))


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rebuild_search(conn: sqlite3.Connection, project_id: str) -> None:
    """검색 색인을 이 과제 몫만 다시 만든다.

    색인에 넣는 것은 **사람이 검색창에 칠 만한 것 전부**다 (TODO 53).
    예전에는 과제와 진행일지의 제목·본문만 넣어서, "전사 주요업무 보고" 로 찾으면
    아무것도 안 나왔다 — 보고 문서가 아예 색인 대상이 아니었기 때문이다.

    태그·담당자는 과제의 본문 뒤에 덧붙인다. 따로 갈래를 만들 만큼 긴 글이 아니고,
    "권경락" 으로 찾으면 그 사람이 맡은 과제가 나오는 것이 자연스럽다.
    """
    conn.execute("DELETE FROM search_fts WHERE project_id = ?", (project_id,))
    project = conn.execute("SELECT title, body FROM project WHERE id = ?", (project_id,)).fetchone()
    if project:
        extras = [row["name"] for row in conn.execute(
            "SELECT name FROM project_owner WHERE project_id = ?", (project_id,)
        )]
        extras += [row["name"] for row in conn.execute(
            "SELECT t.name FROM tag t JOIN project_tag pt ON pt.tag_id = t.id"
            " WHERE pt.project_id = ?", (project_id,)
        )]
        # 유관부서와 그 담당자 (TODO 92). "설비기술팀" 이나 "김철수" 로 찾으면
        # 함께 일하는 과제가 나와야 한다 — 담당자로 찾는 것과 같은 이치다.
        for row in conn.execute(
            "SELECT team, person FROM project_partner WHERE project_id = ?", (project_id,)
        ):
            extras.append(row["team"])
            if row["person"]:
                extras.append(row["person"])
        body = "\n".join([project["body"] or "", *extras])
        conn.execute(
            "INSERT INTO search_fts(kind, ref_id, project_id, title, body) VALUES ('project', ?, ?, ?, ?)",
            (project_id, project_id, project["title"], body),
        )
    for row in conn.execute("SELECT id, title, body FROM entry WHERE project_id = ?", (project_id,)):
        conn.execute(
            "INSERT INTO search_fts(kind, ref_id, project_id, title, body) VALUES ('entry', ?, ?, ?, ?)",
            (str(row["id"]), project_id, row["title"], row["body"] or ""),
        )
    # 보고 문서. 피보고자("전사 주요업무 보고")로 찾는 일이 잦아 제목 쪽에 함께 넣는다.
    for row in conn.execute(
        "SELECT id, title, body, audience, report_date FROM report WHERE project_id = ?", (project_id,)
    ):
        title = " ".join(filter(None, [row["report_date"], row["title"], row["audience"]]))
        conn.execute(
            "INSERT INTO search_fts(kind, ref_id, project_id, title, body) VALUES ('report', ?, ?, ?, ?)",
            (str(row["id"]), project_id, title, row["body"] or ""),
        )


def _as_number(value: Any) -> float | None:
    """시간·비용. 손으로 고친 파일에 숫자가 아닌 값이 들어와도 색인을 멈추지 않는다."""
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def index_activities(
    conn: sqlite3.Connection, problems: list[IndexProblem] | None = None
) -> int:
    """팀원 역량 이력을 색인한다 (TODO 72).

    **사람은 폴더명이 아니라 front matter 의 `person` 으로 정한다.** 폴더명은 읽기 좋으라고
    붙인 것이지 식별자가 아니다 — 이름을 바꿔 폴더를 못 옮겨도 기록이 미아가 되지 않는다.
    """
    from ..config import ACTIVITY_KIND_KEYS, DEFAULT_ACTIVITY_KIND

    settings = get_settings()
    root = settings.vault_dir
    seen: list[str] = []
    for path in sorted(settings.people_dir.glob("*/activities/*.md")):
        doc = _load_doc(path, root, problems)
        rel_path = path.relative_to(root).as_posix()
        if doc is None:
            seen.append(rel_path)  # 깨진 파일은 건너뛰되 색인에서 지우지는 않는다
            continue
        person = _as_str(doc.meta.get("person")) or path.parent.parent.name
        kind = _as_str(doc.meta.get("kind")) or DEFAULT_ACTIVITY_KIND
        if kind not in ACTIVITY_KIND_KEYS:
            # 모르는 구분은 기본 구분으로 보이되 알린다 (TODO 214 D18)
            if problems is not None:
                problems.append(IndexProblem(
                    rel_path, f"구분(kind) 값({kind})을 알 수 없어 '{DEFAULT_ACTIVITY_KIND}' 로 보입니다 — 파일을 고친 뒤 [다시 읽기]"))
            kind = DEFAULT_ACTIVITY_KIND
        # 날짜가 아닌 값은 이름의 날짜 → 파일 수정일로 보이고 알린다 (TODO 214 D18)
        activity_date = _day_or_mtime(doc.meta, "date", path, path.name, rel_path, problems)
        conn.execute(
            """
            INSERT INTO activity(person, rel_path, date, end_date, kind, title, host, place,
                                 hours, cost, takeaway, link, body, author,
                                 created_at, updated_at, file_mtime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rel_path) DO UPDATE SET
              person=excluded.person, date=excluded.date, end_date=excluded.end_date,
              kind=excluded.kind,
              title=excluded.title, host=excluded.host, place=excluded.place,
              hours=excluded.hours, cost=excluded.cost, takeaway=excluded.takeaway,
              link=excluded.link, body=excluded.body, author=excluded.author,
              created_at=excluded.created_at, updated_at=excluded.updated_at,
              file_mtime=excluded.file_mtime
            """,
            (
                person,
                rel_path,
                activity_date,
                _as_date(doc.meta, "end_date", rel_path, problems),
                kind,
                _as_str(doc.meta.get("title")) or path.stem,
                _as_str(doc.meta.get("host")),
                _as_str(doc.meta.get("place")),
                _as_number(doc.meta.get("hours")),
                _as_number(doc.meta.get("cost")),
                _as_str(doc.meta.get("takeaway")),
                _as_str(doc.meta.get("link")),
                doc.body,
                _as_str(doc.meta.get("author")),
                _as_str(doc.meta.get("created_at")),
                _as_str(doc.meta.get("updated_at")),
                path.stat().st_mtime,
            ),
        )
        seen.append(rel_path)

    if seen:
        placeholders = ",".join("?" * len(seen))
        conn.execute(f"DELETE FROM activity WHERE rel_path NOT IN ({placeholders})", tuple(seen))
    else:
        conn.execute("DELETE FROM activity")
    return len(seen)


def index_meetings(
    conn: sqlite3.Connection, problems: list[IndexProblem] | None = None
) -> int:
    """팀원 면담을 색인한다 (TODO 182). 사람은 front matter 의 `person` (역량 이력과 같은 규칙)."""
    import json

    settings = get_settings()
    root = settings.vault_dir
    seen: list[str] = []
    for path in sorted(settings.people_dir.glob("*/meetings/*.md")):
        doc = _load_doc(path, root, problems)
        rel_path = path.relative_to(root).as_posix()
        if doc is None:
            seen.append(rel_path)
            continue
        raw = doc.meta.get("followups")
        followups = []
        for item in raw if isinstance(raw, list) else []:
            if isinstance(item, dict) and _as_str(item.get("text")):
                followups.append({"text": _as_str(item.get("text")), "done": _as_str(item.get("done"))})
            elif isinstance(item, str) and item.strip():
                followups.append({"text": item.strip(), "done": None})
        conn.execute(
            """
            INSERT INTO meeting(person, rel_path, date, kind, summary, followups, open_followups,
                                next_date, body, author, created_at, updated_at, file_mtime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rel_path) DO UPDATE SET
              person=excluded.person, date=excluded.date, kind=excluded.kind, summary=excluded.summary,
              followups=excluded.followups, open_followups=excluded.open_followups,
              next_date=excluded.next_date, body=excluded.body, author=excluded.author,
              created_at=excluded.created_at, updated_at=excluded.updated_at, file_mtime=excluded.file_mtime
            """,
            (
                _as_str(doc.meta.get("person")) or path.parent.parent.name,
                rel_path,
                _day_or_mtime(doc.meta, "date", path, path.name, rel_path, problems),  # TODO 214 D18
                _as_str(doc.meta.get("kind")),
                _as_str(doc.meta.get("summary")),
                json.dumps(followups, ensure_ascii=False),
                sum(1 for item in followups if not item["done"]),
                _as_date(doc.meta, "next_date", rel_path, problems),
                doc.body,
                _as_str(doc.meta.get("author")),
                _as_str(doc.meta.get("created_at")),
                _as_str(doc.meta.get("updated_at")),
                path.stat().st_mtime,
            ),
        )
        seen.append(rel_path)
    if seen:
        placeholders = ",".join("?" * len(seen))
        conn.execute(f"DELETE FROM meeting WHERE rel_path NOT IN ({placeholders})", tuple(seen))
    else:
        conn.execute("DELETE FROM meeting")
    return len(seen)


def predecessor_problems(conn: sqlite3.Connection, project_ids: list[str] | None = None) -> list[IndexProblem]:
    """선행 과제 번호가 없는 과제를 가리키거나 고리를 이루면 알린다 (TODO 214 D18).

    화면 · API 로는 둘 다 만들 수 없다 — 손으로 고친 파일이거나, 선행 과제가 보관함으로 갔다. 파일은 그대로 둔다
    (선행이 보관함에서 돌아오면 다시 이어진다). 다른 과제를 다 읽은 뒤에 따져야 하므로 [다시 읽기]는 끝에서 한 번,
    저장은 그 과제 하나만 따진다.
    """
    preds: dict[str, list[str]] = {}
    for row in conn.execute("SELECT project_id, predecessor_id FROM project_predecessor ORDER BY project_id, predecessor_id"):
        preds.setdefault(row["project_id"], []).append(row["predecessor_id"])
    present = {row["id"]: row["dir_name"] for row in conn.execute("SELECT id, dir_name FROM project")}
    out: list[IndexProblem] = []
    for project_id in project_ids if project_ids is not None else sorted(preds):
        if project_id not in present or project_id not in preds:
            continue
        rel = f"projects/{present[project_id]}/index.md"
        for pred in preds[project_id]:
            if pred not in present:
                out.append(IndexProblem(
                    rel, f"선행 과제 {pred} 를 찾을 수 없습니다 — 삭제 보관함에 있거나 번호가 바뀌었습니다. "
                    "되살리거나 선행 과제 칸에서 빼 주세요"))
        # 고리 — 선행을 따라가다 자기에게 돌아오는가
        seen: set[str] = set()
        stack = list(preds[project_id])
        while stack:
            current = stack.pop()
            if current == project_id:
                out.append(IndexProblem(
                    rel, "선행 과제가 고리를 이룹니다(따라가면 이 과제로 돌아옵니다) — 단계를 셀 수 없습니다. "
                    "고리의 한 곳에서 선행 과제를 빼 주세요"))
                break
            if current in seen:
                continue
            seen.add(current)
            stack.extend(preds.get(current, []))
    return out


def reindex_all(conn: sqlite3.Connection) -> tuple[int, list[IndexProblem]]:
    """vault 전체 재인덱싱. DB를 지운 뒤에도 이것만 돌리면 복구된다.

    파일 하나가 깨져 있어도 나머지는 정상적으로 인덱싱하고, 문제 파일 목록을 함께 돌려준다.
    """
    settings = get_settings()
    settings.ensure_dirs()
    # 아무 데도 안 붙은 태그를 걷는다 — 같은 태그로 합칠 때(TODO 214 D12) 예전 표기가 먼저 잡히지 않게
    conn.execute(
        "DELETE FROM tag WHERE NOT EXISTS (SELECT 1 FROM project_tag pt WHERE pt.tag_id = tag.id)"
        " AND NOT EXISTS (SELECT 1 FROM entry_tag et WHERE et.tag_id = tag.id)"
    )
    problems: list[IndexProblem] = []
    found: list[str] = []
    seen: dict[str, str] = {}
    for project_dir in sorted(settings.projects_dir.iterdir()):
        if not project_dir.is_dir() or project_dir.name.startswith("."):
            continue
        if not (project_dir / "index.md").exists():
            # TODO 203 — index.md 가 없는 폴더는 목록에 안 보인다. 예전엔 말없이 넘어가서, 옛 폴더로 되살아난 기록 ·
            # 거절된 과제가 남긴 빈 폴더가 "어디에도 없는" 채로 쌓였다. 알린다.
            has_files = any(path.is_file() for path in project_dir.rglob("*"))
            problems.append(IndexProblem(
                f"projects/{project_dir.name}",
                "index.md 가 없는 과제 폴더라 목록에 보이지 않습니다 — "
                + ("안의 파일을 맞는 과제 폴더로 옮기거나, 과제 폴더가 아니면 데이터 폴더 밖으로 옮겨 주세요."
                   if has_files else "비어 있는 폴더이니 지워도 됩니다."),
            ))
            continue
        try:
            project_id = index_project(conn, project_dir, problems)
        except (sqlite3.Error, ValueError, KeyError, TypeError, OSError) as exc:
            # TODO 199 — 폴더 하나의 사고(손으로 고친 값 · 잠긴 파일 · 색인 충돌)가 재색인 전체를 500 으로,
            # 기동을 크래시로 끝내지 않는다. 그 폴더만 알리고 다음 폴더로 간다. 색인에 있던 줄은 그대로 둔다.
            problems.append(IndexProblem(
                f"projects/{project_dir.name}",
                f"이 폴더를 색인하지 못해 건너뜁니다 — {type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}".rstrip(" :—"),
            ))
            project_id = project_id_from_dir_name(project_dir.name)
        if project_id:
            # 같은 번호의 폴더가 둘이면 색인에는 하나만 남는다 — 조용히 버리지 않고 알린다 (TODO 146)
            if project_id in seen:
                problems.append(IndexProblem(
                    f"projects/{project_dir.name}",
                    f"같은 번호 {project_id} 의 과제 폴더가 둘입니다({seen[project_id]}). 목록에는 하나만 "
                    "보입니다 — 한쪽의 번호를 바꿔 주세요(설정 → 과제 번호 체계).",
                ))
            seen[project_id] = project_dir.name
            found.append(project_id)

    if found:
        placeholders = ",".join("?" * len(found))
        conn.execute(f"DELETE FROM project WHERE id NOT IN ({placeholders})", tuple(found))
    else:
        conn.execute("DELETE FROM project")
    # 선행 과제 — 모든 과제를 읽은 뒤에 따진다 (TODO 214 D18)
    problems.extend(predecessor_problems(conn))

    # 역량 이력은 과제와 이어지지 않으므로 따로 훑는다 (TODO 72).
    index_activities(conn, problems)
    # 팀원 면담 (TODO 182)
    index_meetings(conn, problems)
    # 접수 풀도 따로 훑는다 (TODO 136)
    from ..services.intakes import reindex_intakes

    reindex_intakes(conn, problems)
    # 보관함에 간 과제를 가리키는 접수는 풀로 (TODO 145 — 이 규칙 전에 지운 것까지)
    from ..services.intakes import detach_orphans

    detach_orphans(conn)
    conn.commit()
    LAST_PROBLEMS[:] = problems
    return len(found), problems
