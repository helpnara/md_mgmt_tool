"""담당자 명부와 표기 통일."""
from __future__ import annotations

import sqlite3
from typing import Any

from ..vault import markdown as md
from ..vault.indexer import index_project
from . import settings as settings_service
from .projects import now_iso, project_dir


def overview(conn: sqlite3.Connection) -> dict[str, Any]:
    """명부와, 실제로 과제에 쓰이고 있는 이름을 함께 돌려준다.

    둘을 나란히 보여야 "명부에 없는데 쓰이고 있는 이름"이 눈에 띈다.
    그것이 표기 흔들림이 숨어 있는 자리다.
    """
    registered = settings_service.people()
    names = {person["name"] for person in registered}

    used = {
        row["name"]: row["n"]
        for row in conn.execute(
            "SELECT name, COUNT(*) AS n FROM project_owner GROUP BY name ORDER BY n DESC, name"
        )
    }
    return {
        "people": [{**person, "used": used.get(person["name"], 0)} for person in registered],
        # 명부에 없는데 과제에 쓰이고 있는 이름. 오타이거나, 명부에 넣어야 할 사람이다.
        "unregistered": [
            {"name": name, "used": count} for name, count in used.items() if name not in names
        ],
    }


def rename_owner(conn: sqlite3.Connection, old: str, new: str) -> dict[str, Any]:
    """담당자 표기를 한 번에 바꾼다. **파일이 원본이므로 파일부터 고친다.**

    `권 경락` → `권경락` 처럼 이미 쌓인 흔들림을 정리하는 데 쓴다.
    """
    old, new = (old or "").strip(), (new or "").strip()
    if not old or not new:
        raise ValueError("바꿀 이름과 새 이름을 모두 입력하세요.")
    if old == new:
        raise ValueError("두 이름이 같습니다.")

    targets = [
        row["project_id"]
        for row in conn.execute(
            "SELECT DISTINCT project_id FROM project_owner WHERE name = ? ORDER BY project_id",
            (old,),
        )
    ]

    changed = []
    for project_id in targets:
        directory = project_dir(conn, project_id)
        index_md = directory / "index.md"
        doc = md.load(index_md)
        owners = doc.meta.get("owners") or []
        if isinstance(owners, str):
            owners = [owners]
        # 새 이름이 이미 있으면 중복으로 남기지 않는다.
        renamed: list[str] = []
        for name in owners:
            name = new if str(name).strip() == old else str(name).strip()
            if name and name not in renamed:
                renamed.append(name)
        doc.meta["owners"] = renamed
        doc.meta["updated_at"] = now_iso()
        md.save(index_md, doc)
        index_project(conn, directory)
        changed.append(project_id)

    # 명부에서도 이름을 바꾼다 (사번·계정은 그대로 따라간다).
    registered = settings_service.people()
    if any(person["name"] == old for person in registered):
        merged: list[dict[str, str]] = []
        for person in registered:
            if person["name"] == old:
                person = {**person, "name": new}
            if not any(existing["name"] == person["name"] for existing in merged):
                merged.append(person)
        settings_service.save({"people": merged})

    conn.commit()
    return {"changed": changed, "count": len(changed), "old": old, "new": new}
