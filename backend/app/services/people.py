"""담당자 명부와 표기 통일."""
from __future__ import annotations

import sqlite3
from typing import Any

from pathlib import Path

from ..config import FINISHED_STATUSES, get_settings
from ..vault import markdown as md
from ..vault import paths, versions
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


def _swap(names: list[str], old: str, new: str | None) -> list[str]:
    """이름 목록에서 old → new (`new=None` 이면 뺀다). 새 이름이 이미 있으면 겹쳐 남기지 않는다."""
    out: list[str] = []
    for name in names:
        name = str(name).strip()
        if name == old:
            if new is None:
                continue
            name = new
        if name and name not in out:
            out.append(name)
    return out


def _replace_in_projects(
    conn: sqlite3.Connection, project_ids: list[str], old: str, new: str | None
) -> list[str]:
    """과제 파일의 담당자 이름을 바꾼다(또는 `new=None` 이면 뺀다). **파일이 원본이다.**

    TODO 214 D9 — 유관부서 담당자(`partners[].people`)도 함께 바꾼다. 담당 · 유관부서 어느 쪽이든 바뀐 과제의 번호를 돌려준다.
    """
    return [project_id for project_id, _, _ in _rename_in_projects(conn, project_ids, old, new)]


def _rename_in_projects(
    conn: sqlite3.Connection, project_ids: list[str], old: str, new: str | None
) -> list[tuple[str, bool, bool]]:
    """과제마다 (번호, 담당이 바뀌었나, 유관부서가 바뀌었나). 바뀐 것이 없는 과제는 파일을 건드리지 않는다."""
    from .projects import normalize_partners

    out: list[tuple[str, bool, bool]] = []
    for project_id in project_ids:
        directory = project_dir(conn, project_id)
        index_md = directory / "index.md"
        doc = md.load(index_md)
        owners = doc.meta.get("owners") or []
        if isinstance(owners, str):
            owners = [owners]
        owners = [str(name).strip() for name in owners]
        new_owners = _swap(owners, old, new)
        owners_changed = old in owners
        partners = normalize_partners(doc.meta.get("partners"))
        partners_changed = any(old in row["people"] for row in partners)
        if not owners_changed and not partners_changed:
            continue
        if owners_changed:
            doc.meta["owners"] = new_owners
        if partners_changed:
            # 넘기기(new=None 은 쓰지 않음)든 통일이든 팀 줄은 그대로, 사람만 바꾼다
            doc.meta["partners"] = [{**row, "people": _swap(row["people"], old, new)} for row in partners]
        doc.meta["updated_at"] = now_iso()
        md.save(index_md, doc)
        index_project(conn, directory)
        out.append((project_id, owners_changed, partners_changed))
    return out


def _projects_naming(conn: sqlite3.Connection, name: str, include_finished: bool = True) -> list[str]:
    """그 이름이 담당 또는 유관부서 담당으로 들어간 과제의 번호."""
    sql = ("SELECT p.id AS id FROM project p WHERE p.id IN ("
           " SELECT project_id FROM project_owner WHERE name = ?"
           " UNION SELECT project_id FROM project_partner WHERE person = ?)")
    params: list[Any] = [name, name]
    if not include_finished:
        sql += f" AND p.status NOT IN ({','.join('?' for _ in FINISHED_STATUSES)})"
        params.extend(FINISHED_STATUSES)
    return [row["id"] for row in conn.execute(sql + " ORDER BY p.id", params)]


def _rename_person_records(conn: sqlite3.Connection, table: str, old: str, new: str) -> int:
    """역량 · 면담 기록의 `person` 을 바꾸고 파일을 새 이름의 폴더로 옮긴다 (TODO 214 D9). 옮길 자리에 같은 이름이 있으면 옆에.

    사람 폴더가 이미 있으면 그 안으로 합친다. 비게 된 옛 폴더는 지운다.
    """
    from . import activities as activities_service
    from . import meetings as meetings_service

    vault = get_settings().vault_dir
    person_dir = activities_service.person_dir if table == "activity" else meetings_service.person_dir
    rows = conn.execute(f"SELECT rel_path FROM {table} WHERE person = ? ORDER BY rel_path", (old,)).fetchall()
    emptied: set[Path] = set()
    for row in rows:
        path = paths.safe_join(vault, row["rel_path"])
        doc = md.load(path)
        doc.meta["person"] = new
        doc.meta["updated_at"] = now_iso()
        md.save(path, doc)
        directory = person_dir(new)
        if path.parent != directory:
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / path.name
            if target.exists():
                target = paths.unique_path(directory, path.stem, path.suffix)
            paths.move(path, target)
            versions.follow(path, target)
            emptied.add(path.parent)
    for folder in emptied:
        # people/<옛 이름>/activities → people/<옛 이름> 순으로, 비었을 때만
        for candidate in (folder, folder.parent):
            try:
                candidate.rmdir()
            except OSError:
                break
    return len(rows)


def _rename_intake_leaders(conn: sqlite3.Connection, old: str, new: str, *, pool_only: bool) -> int:
    """접수의 과제리더(요청자) 이름 (TODO 214 D9). 넘기기는 풀에 있는(판정 전) 접수만 — 닫힌 접수는 그때의 기록이다."""
    from ..config import INTAKE_POOL_STATUSES
    from . import intakes as intakes_service

    sql, params = "SELECT id FROM intake WHERE leader = ?", [old]
    if pool_only:
        sql += f" AND status IN ({','.join('?' for _ in INTAKE_POOL_STATUSES)})"
        params.extend(INTAKE_POOL_STATUSES)
    count = 0
    for row in conn.execute(sql + " ORDER BY id", params).fetchall():
        directory = intakes_service.intake_dir(conn, row["id"])
        request = directory / intakes_service.REQUEST_FILE
        doc = md.load(request)
        doc.meta["leader"] = new
        doc.meta["updated_at"] = now_iso()
        md.save(request, doc)
        intakes_service.index_intake(conn, directory)
        count += 1
    return count


def _names(old: str, new: str, empty_message: str) -> tuple[str, str]:
    """옛 이름은 그대로(손으로 고친 이상한 표기를 고치려고 부르는 자리다), 새 이름은 명부 규칙으로 (TODO 214 F6)."""
    old, new = (old or "").strip(), (new or "").strip()
    if not old or not new:
        raise ValueError(empty_message)
    if old == new:
        raise ValueError("두 이름이 같습니다.")
    return old, settings_service.person_name(new)


def handover(
    conn: sqlite3.Connection, old: str, new: str, *, include_finished: bool = False
) -> dict[str, Any]:
    """담당자를 넘긴다 — 전배·퇴사로 빠진 사람의 과제를 다른 사람에게 (TODO 122).

    `rename_owner`(표기 통일)와 **뜻이 다르다.** 저쪽은 같은 사람의 이름을 바로잡는 것이라
    명부의 이름까지 바꾸지만, 이쪽은 **다른 사람에게 일을 넘기는 것**이다. 그래서

    * 명부는 건드리지 않는다 — 떠난 사람은 떠난 사람으로 남는다.
    * **끝난 과제는 기본으로 손대지 않는다.** 그때 그 사람이 한 것은 사실이고,
      바꾸면 지난 보고·지난해 팀원별 성과와 어긋난다.
    * TODO 214 D9 — 담당뿐 아니라 **유관부서 담당 · 풀에 있는 접수의 과제리더**도 넘긴다(남은 일).
      역량 · 면담 기록은 넘기지 않는다 — 그 사람의 지난 이력이지 일감이 아니다.
    """
    old, new = _names(old, new, "넘길 사람과 받을 사람을 모두 고르세요.")
    targets = _projects_naming(conn, old, include_finished)
    changes = _rename_in_projects(conn, targets, old, new)
    intakes = _rename_intake_leaders(conn, old, new, pool_only=True)
    conn.commit()
    changed = [project_id for project_id, _, _ in changes]
    return {"changed": changed, "count": len(changed), "old": old, "new": new,
            "include_finished": include_finished,
            "counts": {"owners": sum(1 for _, o, _ in changes if o), "partners": sum(1 for _, _, p in changes if p),
                       "activities": 0, "meetings": 0, "intakes": intakes}}


def rename_owner(conn: sqlite3.Connection, old: str, new: str) -> dict[str, Any]:
    """사람 표기를 한 번에 바꾼다. **파일이 원본이므로 파일부터 고친다.**

    `권 경락` → `권경락` 처럼 이미 쌓인 흔들림을 정리하는 데 쓴다.
    TODO 214 D9 — 담당 · 유관부서 담당 · 역량 기록 · 면담 기록(파일 이름과 폴더까지) · 접수 과제리더 · 명부.
    작성자 · 등록자(author · created_by)는 그때의 사실이라 두고, 끝난 과제도 바꾼다(같은 사람의 표기이므로).
    """
    from ..vault.indexer import index_activities, index_meetings

    old, new = _names(old, new, "바꿀 이름과 새 이름을 모두 입력하세요.")
    changes = _rename_in_projects(conn, _projects_naming(conn, old), old, new)
    activities = _rename_person_records(conn, "activity", old, new)
    meetings = _rename_person_records(conn, "meeting", old, new)
    if activities:
        index_activities(conn)
    if meetings:
        index_meetings(conn)
    intakes = _rename_intake_leaders(conn, old, new, pool_only=False)

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
    changed = [project_id for project_id, _, _ in changes]
    return {"changed": changed, "count": len(changed), "old": old, "new": new,
            "counts": {"owners": sum(1 for _, o, _ in changes if o), "partners": sum(1 for _, _, p in changes if p),
                       "activities": activities, "meetings": meetings, "intakes": intakes}}
