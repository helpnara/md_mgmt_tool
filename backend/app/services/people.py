"""담당자 명부와 표기 통일."""
from __future__ import annotations

import sqlite3
from typing import Any

from ..config import FINISHED_STATUSES
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
    # 떠난 사람이 아직 담당으로 남아 있는 **끝나지 않은** 과제 수 (TODO 122).
    # 명부 화면에서 "이 사람은 아직 N건이 남아 있다" 를 바로 보여 준다.
    marks = ",".join("?" for _ in FINISHED_STATUSES)
    unfinished = {
        row["name"]: row["n"]
        for row in conn.execute(
            "SELECT po.name AS name, COUNT(DISTINCT po.project_id) AS n"
            " FROM project_owner po JOIN project p ON p.id = po.project_id"
            f" WHERE p.status NOT IN ({marks}) GROUP BY po.name",
            FINISHED_STATUSES,
        )
    }
    return {
        "people": [
            {
                **person,
                "used": used.get(person["name"], 0),
                "unfinished": unfinished.get(person["name"], 0),
            }
            for person in registered
        ],
        # 명부에 없는데 과제에 쓰이고 있는 이름. 오타이거나, 명부에 넣어야 할 사람이다.
        "unregistered": [
            {"name": name, "used": count} for name, count in used.items() if name not in names
        ],
    }


def _replace_in_projects(
    conn: sqlite3.Connection, project_ids: list[str], old: str, new: str | None
) -> list[str]:
    """과제 파일의 담당자 이름을 바꾼다(또는 `new=None` 이면 뺀다). **파일이 원본이다.**"""
    changed = []
    for project_id in project_ids:
        directory = project_dir(conn, project_id)
        index_md = directory / "index.md"
        doc = md.load(index_md)
        owners = doc.meta.get("owners") or []
        if isinstance(owners, str):
            owners = [owners]
        replaced: list[str] = []
        for name in owners:
            name = str(name).strip()
            if name == old:
                if new is None:
                    continue
                name = new
            # 새 이름이 이미 있으면 중복으로 남기지 않는다.
            if name and name not in replaced:
                replaced.append(name)
        doc.meta["owners"] = replaced
        doc.meta["updated_at"] = now_iso()
        md.save(index_md, doc)
        index_project(conn, directory)
        changed.append(project_id)
    return changed


def handover(
    conn: sqlite3.Connection, old: str, new: str, *, include_finished: bool = False
) -> dict[str, Any]:
    """담당자를 넘긴다 — 전배·퇴사로 빠진 사람의 과제를 다른 사람에게 (TODO 122).

    `rename_owner`(표기 통일)와 **뜻이 다르다.** 저쪽은 같은 사람의 이름을 바로잡는 것이라
    명부의 이름까지 바꾸지만, 이쪽은 **다른 사람에게 일을 넘기는 것**이다. 그래서

    * 명부는 건드리지 않는다 — 떠난 사람은 떠난 사람으로 남는다.
    * **끝난 과제는 기본으로 손대지 않는다.** 그때 그 사람이 한 것은 사실이고,
      바꾸면 지난 보고·지난해 팀원별 성과와 어긋난다.
    """
    old, new = (old or "").strip(), (new or "").strip()
    if not old or not new:
        raise ValueError("넘길 사람과 받을 사람을 모두 고르세요.")
    if old == new:
        raise ValueError("두 이름이 같습니다.")

    clause = ""
    params: list[Any] = [old]
    if not include_finished:
        marks = ",".join("?" for _ in FINISHED_STATUSES)
        clause = f" AND p.status NOT IN ({marks})"
        params.extend(FINISHED_STATUSES)
    targets = [
        row["project_id"]
        for row in conn.execute(
            "SELECT DISTINCT po.project_id AS project_id FROM project_owner po"
            f" JOIN project p ON p.id = po.project_id WHERE po.name = ?{clause}"
            " ORDER BY po.project_id",
            params,
        )
    ]
    changed = _replace_in_projects(conn, targets, old, new)
    conn.commit()
    return {"changed": changed, "count": len(changed), "old": old, "new": new,
            "include_finished": include_finished}


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
