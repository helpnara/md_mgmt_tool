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
    "created_by", "created_at", "updated_at",
]


def normalize_effect(value: object) -> float | None:
    """효과 금액(억원/년)을 숫자로 맞춘다. 비우는 것은 정상이다.

    실증효과는 과제가 끝나야 나오므로 진행 중에는 대부분 비어 있다.
    """
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"효과 금액은 숫자여야 합니다: {value!r}") from exc
    if number < 0:
        raise ValueError("효과 금액은 0보다 작을 수 없습니다.")
    return number


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
        "start_date": data.get("start_date") or None,
        "due_date": data.get("due_date") or None,
        "effect_expected": normalize_effect(data.get("effect_expected")),
        "effect_verified": normalize_effect(data.get("effect_verified")),
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
