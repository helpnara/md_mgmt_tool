"""과제 생성·수정. 파일을 먼저 쓰고 인덱스를 갱신한다."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import DEFAULT_STATUS, STATUS_KEYS, TYPE_KEYS, get_settings
from ..vault import markdown as md
from ..vault import paths
from ..vault.indexer import index_project
from . import activities as activities_service
from . import settings as settings_service
from . import trash as trash_service

# 카드 제목이 "과제 개요"이므로 본문은 같은 제목을 반복하지 않는다.
# 각 항목이 무엇을 적는 자리인지 괄호로 안내하고, 사용자는 그 줄을 지우고 쓰면 된다.
# 안내 문구는 인용문(>)으로 넣는다. 화면에서 흐리게 보여 실제 내용과 구분되고,
# 사용자는 그 줄을 지우고 쓰면 된다.
INDEX_TEMPLATE = """## 배경

> 왜 이 과제를 하는지 — 문제 상황, 요청 배경 (이 줄을 지우고 작성하세요)

## 목표

> 무엇을 달성하면 끝인지 — 가능하면 수치로

## 산출물

> 과제가 끝났을 때 남기는 결과물 — 예: 평가 보고서, 시제품, 측정 데이터, 특허 초안

## 정성적 효과

> 숫자로 표현하기 어려운 효과 — 품질 향상, 리스크 저감, 기술 확보, 대응 속도 등
> 근거 자료(엑셀·PPT)는 아래 [파일 첨부]로 붙이고 여기에 링크하면 된다

## 효과 산출 근거

> 위 기대효과 금액이 어떤 계산에서 나왔는지 — 단가 × 물량 × 개선율, 가정, 출처
> 근거 없는 숫자는 보고 자리에서 방어하지 못한다

## 관련 링크

> 참고할 사내 위키·공유 폴더 주소, 관련 과제 번호 등
"""

META_ORDER = [
    "id", "title", "status", "type", "group", "tags", "owners",
    "start_date", "due_date", "effect_expected", "effect_verified",
    "no_report", "partners", "created_by", "created_at", "updated_at",
]


# 효과 금액의 소수 자릿수. 단위가 **억원/년** 이므로 둘째 자리는 100만 원이다.
# 한 자리(=천만 원)로는 1억 2,500만 원짜리 효과를 적을 수 없다 (TODO 76).
EFFECT_DECIMALS = 2


def normalize_effect(value: object) -> float | None:
    """효과 금액(억원/년)을 숫자로 맞춘다. 비우는 것은 정상이다.

    실증효과는 과제가 끝나야 나오므로 진행 중에는 대부분 비어 있다.

    **여기서 소수 둘째 자리로 자른다.** 파일이 진실의 원천이므로, 화면이 두 자리로
    보여 준다면 파일에도 두 자리만 있어야 한다. 그러지 않으면 API 로 넣은 `1.234` 가
    화면에는 `1.23` 으로 보이면서 파일에는 그대로 남아 둘이 어긋난다.
    """
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"효과 금액은 숫자여야 합니다: {value!r}") from exc
    if number < 0:
        raise ValueError("효과 금액은 0보다 작을 수 없습니다.")
    return round(number, EFFECT_DECIMALS)


def normalize_owners(value: object) -> list[str]:
    """담당자는 한 명일 수도, 여러 명일 수도 있다. 쉼표로 적어도 받아 준다."""
    if not value:
        return []
    items = [value] if isinstance(value, str) else [str(item) for item in value]
    # 한 칸에 "권경락, 홍길동" 처럼 적어 보내도 나눠 받는다.
    raw = [part for item in items for part in item.split(",")]
    seen: list[str] = []
    for name in (item.strip() for item in raw):
        if name and name not in seen:
            seen.append(name)
    return seen


def normalize_partners(value: object) -> list[dict]:
    """유관부서와 그 담당자 (TODO 92).

    `[{"team": "설비기술팀", "people": "김철수, 박민수"}, …]` 을 받아
    `[{"team": "설비기술팀", "people": ["김철수", "박민수"]}, …]` 으로 맞춘다.

    **사람 이름을 나누는 일은 여기(서버)에서 한다.** 화면만 고치면 API 를 직접 부르는
    길로 `"김철수,박민수"` 한 덩이가 사람 하나로 굳는다 — 역량 이력에서 실제로 겪은
    사고다 (TODO 74). 팀 이름은 나누지 않는다. 부서명에 쉼표가 들어갈 수 있고,
    무엇보다 **팀은 줄마다 하나**라는 것이 이 구조의 약속이다.

    담당자가 비어 있어도 줄은 남긴다 — 팀은 정해졌는데 사람은 나중에 정해지는 일이 흔하다.
    """
    if not value:
        return []
    rows = value if isinstance(value, list) else [value]
    out: list[dict] = []
    seen: dict[str, dict] = {}
    for row in rows:
        if isinstance(row, str):
            team, people = row, []
        elif isinstance(row, dict):
            team = str(row.get("team") or "").strip()
            people = activities_service.split_people(
                row.get("people") if isinstance(row.get("people"), str) else None
            ) or [
                name
                for name in (str(item).strip() for item in (row.get("people") or []))
                if name
            ]
        else:
            continue
        team = str(team).strip()
        if not team:
            continue
        # 같은 팀을 두 줄로 적었으면 한 줄로 합친다 — 표와 검색에서 두 번 세지 않는다.
        if team in seen:
            for name in people:
                if name not in seen[team]["people"]:
                    seen[team]["people"].append(name)
            continue
        entry = {"team": team, "people": list(dict.fromkeys(people))}
        seen[team] = entry
        out.append(entry)
    return out


def now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def next_project_id(year: int | None = None, code: str | None = None) -> str:
    """다음 과제 번호.

    팀 코드를 비워 두면 `2026-001`, `소재` 를 넣으면 `2026-소재-001` 이 된다.
    일련번호는 **코드별로 따로 센다** — 팀마다 자기 번호를 갖는 편이 자연스럽고,
    코드가 다르면 번호가 같아도 과제 번호는 겹치지 않는다.

    **이미 만든 과제의 번호는 바꾸지 않는다.** 번호는 식별자라 섞여도 되고,
    바꾸면 폴더명과 문서 안의 링크가 모두 흔들린다.
    """
    settings = get_settings()
    settings.ensure_dirs()
    year = year or datetime.now().year
    if code is None:
        code = settings_service.project_code()
    prefix = f"{year}-{code}-" if code else f"{year}-"

    used = 0
    for child in settings.projects_dir.iterdir():
        if not child.is_dir() or not child.name.startswith(prefix):
            continue
        seq = child.name[len(prefix):].split("-")[0]
        if seq.isdigit():
            used = max(used, int(seq))
    return f"{prefix}{used + 1:03d}"


def project_dir(conn: sqlite3.Connection, project_id: str) -> Path:
    row = conn.execute("SELECT dir_name FROM project WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise KeyError(project_id)
    return paths.safe_join(get_settings().projects_dir, row["dir_name"])


def create_project(conn: sqlite3.Connection, data: dict[str, Any]) -> str:
    settings = get_settings()
    settings.ensure_dirs()
    title = (data.get("title") or "").strip()
    if not title:
        raise ValueError("과제명을 입력하세요.")

    status = data.get("status") or DEFAULT_STATUS
    if status not in STATUS_KEYS:
        raise ValueError(f"알 수 없는 상태: {status}")

    project_type = data.get("type") or None
    if project_type and project_type not in TYPE_KEYS:
        raise ValueError(f"알 수 없는 속성: {project_type}")

    project_id = next_project_id()
    dir_name = paths.project_dir_name(project_id, title)
    directory = paths.safe_join(settings.projects_dir, dir_name)
    (directory / "logs").mkdir(parents=True, exist_ok=True)
    (directory / "assets").mkdir(parents=True, exist_ok=True)
    (directory / "reports").mkdir(parents=True, exist_ok=True)

    stamp = now_iso()
    meta = {
        "id": project_id,
        "title": title,
        "status": status,
        "type": project_type,
        "group": data.get("group") or None,
        "tags": data.get("tags") or [],
        "owners": normalize_owners(data.get("owners") or data.get("owner")),
        # 유관부서와 그 담당자. 팀 하나에 사람 여럿, 팀도 여럿일 수 있다 (TODO 92).
        "partners": normalize_partners(data.get("partners")),
        "start_date": data.get("start_date") or None,
        "due_date": data.get("due_date") or None,
        "effect_expected": normalize_effect(data.get("effect_expected")),
        "effect_verified": normalize_effect(data.get("effect_verified")),
        # 단순 현황 관리를 과제로 세운 경우가 있다. 그런 과제는 보고 대상 후보에서 뺀다
        # — 매주 "이건 보고 안 해도 되는데" 를 눈으로 걸러 내지 않아도 되게 (TODO 80).
        "no_report": bool(data.get("no_report")),
        # 담당자(누가 하는가)와 다른, "누가 등록했는가". 소급이 안 되므로 지금부터 남긴다.
        # 로그인이 생기면 이 자리에 로그인 사용자가 들어온다.
        "created_by": settings_service.current_author(data.get("created_by")) or None,
        "created_at": stamp,
        "updated_at": stamp,
    }
    md.save(directory / "index.md", md.MarkdownDoc(meta, data.get("body") or INDEX_TEMPLATE))
    index_project(conn, directory)
    conn.commit()
    return project_id


def update_project(conn: sqlite3.Connection, project_id: str, updates: dict[str, Any]) -> None:
    directory = project_dir(conn, project_id)
    index_md = directory / "index.md"
    known = conn.execute("SELECT file_mtime FROM project WHERE id = ?", (project_id,)).fetchone()
    md.ensure_unchanged(index_md, known["file_mtime"] if known else None)
    doc = md.load(index_md)

    if "status" in updates and updates["status"] not in STATUS_KEYS:
        raise ValueError(f"알 수 없는 상태: {updates['status']}")
    if updates.get("type") and updates["type"] not in TYPE_KEYS:
        raise ValueError(f"알 수 없는 속성: {updates['type']}")

    body = updates.pop("body", None)
    for field in ("effect_expected", "effect_verified"):
        if field in updates:
            updates[field] = normalize_effect(updates[field])
    if "no_report" in updates:
        updates["no_report"] = bool(updates["no_report"])
    if "partners" in updates:
        updates["partners"] = normalize_partners(updates["partners"])
    if "owners" in updates or "owner" in updates:
        updates["owners"] = normalize_owners(updates.pop("owners", None) or updates.pop("owner", None))
    changes = {k: v for k, v in updates.items() if k in META_ORDER or k == "group"}
    # 예전 문서의 owner(단수) 키가 남아 있으면 owners로 옮겨 적는다.
    if "owners" in changes and "owner" in doc.meta:
        doc.meta.pop("owner")
    meta = md.merge_meta(doc.meta, changes)
    meta["updated_at"] = now_iso()
    md.save(index_md, md.MarkdownDoc(meta, body if body is not None else doc.body))

    new_title = meta.get("title")
    if new_title:
        expected = paths.project_dir_name(project_id, str(new_title))
        if expected != directory.name:
            target = paths.safe_join(get_settings().projects_dir, expected)
            if target.exists():  # 남아 있던 폴더와 겹치면 뒤에 번호를 붙인다
                target = paths.unique_path(get_settings().projects_dir, expected, "")
            paths.move(directory, target)
            directory = target

    index_project(conn, directory)
    conn.commit()


def archive_project(conn: sqlite3.Connection, project_id: str) -> None:
    """삭제하지 않고 .trash/ 로 옮긴다."""
    settings = get_settings()
    directory = project_dir(conn, project_id)
    settings.trash_dir.mkdir(parents=True, exist_ok=True)
    target = paths.unique_path(settings.trash_dir, f"{directory.name}-{datetime.now():%Y%m%d%H%M%S}", "")
    row = conn.execute("SELECT title FROM project WHERE id = ?", (project_id,)).fetchone()
    paths.move(directory, target)
    trash_service.record(
        "project",
        label=f"{project_id} {row['title'] if row else directory.name}",
        moved_to=target,
        origin=directory,
        project_id=project_id,
    )
    conn.execute("DELETE FROM project WHERE id = ?", (project_id,))
    conn.execute("DELETE FROM search_fts WHERE project_id = ?", (project_id,))
    conn.commit()
