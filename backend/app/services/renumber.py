"""과제 번호 일괄 변경.

팀 코드를 나중에 정하면, 이미 만든 과제는 `2026-001` 인데 새로 만드는 과제만
`2026-선강DX개발팀-001` 이 된다. 한 목록에 두 형태가 섞이면 번호 체계가 무의미해진다.
그래서 **이미 있는 과제의 번호를 새 코드로 한 번에 맞추는** 길을 낸다.

원칙 셋:

1. **연도와 일련번호는 지킨다.** `2026-001` → `2026-선강DX개발팀-001`.
   번호는 이미 보고 자리에서 불린 이름이다. 바꿔야 할 것은 가운데 코드뿐이다.
2. **파일이 원본이다.** front matter 의 id 와 폴더 이름을 고치고, 색인은 다시 만든다.
   DB 의 id 를 직접 손대면 파일과 어긋난 채로 남을 수 있다.
3. **먼저 보여 주고 나서 바꾼다.** 미리보기로 무엇이 어떻게 바뀌는지 전부 확인한 뒤
   실행한다. 되돌리기 어려운 동작이라 그렇다.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from ..config import get_settings
from ..vault import markdown as md
from ..vault import paths
from ..vault.indexer import reindex_all
from . import settings as settings_service


def split_id(project_id: str) -> tuple[str, str, str] | None:
    """과제 id 를 (연도, 코드, 일련번호) 로 쪼갠다. 형태가 아니면 None.

        2026-001            → ("2026", "",     "001")
        2026-소재-001        → ("2026", "소재", "001")
    """
    parts = project_id.split("-")
    if len(parts) < 2 or not (len(parts[0]) == 4 and parts[0].isdigit()):
        return None
    for index in range(1, len(parts)):
        if parts[index].isdigit():
            return parts[0], "-".join(parts[1:index]), parts[index]
    return None


def trashed_projects() -> list[dict[str, Any]]:
    """보관함에 들어 있는 **과제** 목록.

    보관함 항목은 색인에 없어서 번호 변경에서 빠진다. 그대로 두면 되돌렸을 때
    옛 번호로 살아나 목록에 두 형태가 섞인다 (TODO 60).
    번호가 겹치지 않게 하려면 **자리를 차지하고 있다는 사실도** 알아야 한다.
    """
    settings = get_settings()
    trash = settings.trash_dir
    if not trash.is_dir():
        return []

    found = []
    for folder in sorted(trash.iterdir()):
        index_md = folder / "index.md"
        if not folder.is_dir() or not index_md.is_file():
            continue
        try:
            doc = md.load(index_md)
        except (OSError, ValueError):
            continue
        project_id = str(doc.meta.get("id") or "").strip()
        if project_id:
            found.append(
                {
                    "id": project_id,
                    "title": str(doc.meta.get("title") or folder.name),
                    "folder": folder.name,
                }
            )
    return found


def _free_id(
    wanted: str, year: str, code: str, seq: str, taken: set[str], assigned: set[str]
) -> tuple[str, bool]:
    """원하는 번호가 이미 쓰이고 있으면 뒤 번호로 민다.

    번호를 지키는 것보다 **겹치지 않는 것이 먼저다** — 겹치면 폴더가 서로를 덮는다.
    살아 있는 과제와 보관함 과제가 **같은 규칙**을 써야 되돌렸을 때도 안전하다.
    """
    if wanted not in taken and wanted not in assigned:
        return wanted, False
    number, width = int(seq), len(seq)
    while True:
        number += 1
        candidate = f"{year}-{code}-{number:0{width}d}" if code else f"{year}-{number:0{width}d}"
        if candidate not in taken and candidate not in assigned:
            return candidate, True


def plan(conn: sqlite3.Connection, code: str) -> dict[str, Any]:
    """무엇이 어떻게 바뀌는지 미리 보여 준다. 파일은 건드리지 않는다."""
    code = settings_service.validate_project_code(code)

    rows = conn.execute("SELECT id, title, dir_name FROM project ORDER BY id").fetchall()
    trashed = trashed_projects()
    items: list[dict[str, Any]] = []
    # 보관함 과제의 번호도 이미 쓰인 것으로 본다 — 되돌렸을 때 겹치면 폴더가 서로를 덮는다.
    taken = {row["id"] for row in rows} | {item["id"] for item in trashed}
    assigned: set[str] = set()

    for row in rows:
        parsed = split_id(row["id"])
        if parsed is None:
            # 손으로 지은 폴더명 등 규칙에 없는 번호. 손대지 않는다.
            items.append(
                {
                    "id": row["id"],
                    "title": row["title"],
                    "new_id": None,
                    "skip": "번호 형태가 아니라 자동으로 바꿀 수 없습니다.",
                }
            )
            continue

        year, current_code, seq = parsed
        new_id = f"{year}-{code}-{seq}" if code else f"{year}-{seq}"
        if new_id == row["id"]:
            items.append({"id": row["id"], "title": row["title"], "new_id": None, "skip": "이미 맞습니다."})
            continue

        new_id, moved = _free_id(new_id, year, code, seq, taken - {row["id"]}, assigned)
        assigned.add(new_id)
        items.append(
            {
                "id": row["id"],
                "title": row["title"],
                "new_id": new_id,
                "dir_name": row["dir_name"],
                "new_dir_name": paths.project_dir_name(new_id, row["title"]),
                # 일련번호까지 바뀐 건은 눈에 띄어야 한다. 보고에 이미 적힌 번호일 수 있다.
                "renumbered": moved,
                "skip": None,
            }
        )

    # 보관함 과제도 같은 규칙으로 바꾼다 (TODO 60 — 사용자가 "함께 바꾼다"로 결정).
    trash_changes = []
    for item in trashed:
        parsed = split_id(item["id"])
        if parsed is None:
            continue
        year, _, seq = parsed
        wanted = f"{year}-{code}-{seq}" if code else f"{year}-{seq}"
        if wanted == item["id"]:
            continue
        # 살아 있는 과제가 가져간 번호를 피한다.
        new_id, moved = _free_id(wanted, year, code, seq, taken - {item["id"]}, assigned)
        assigned.add(new_id)
        trash_changes.append({**item, "new_id": new_id, "renumbered": moved})

    return {
        "code": code,
        "total": len(items),
        "changes": [item for item in items if item["new_id"]],
        "skipped": [item for item in items if not item["new_id"]],
        "trashed": trash_changes,
    }


def apply(conn: sqlite3.Connection, code: str) -> dict[str, Any]:
    """미리보기대로 실제로 바꾼다.

    한 과제마다 (1) index.md 의 id (2) 폴더 이름 순으로 고친다. 중간에 파일이 열려 있어
    실패하면 **거기서 멈추고** 무엇까지 바뀌었는지 알려 준다. 되돌리는 것보다
    어디까지 됐는지 아는 편이 낫다 — 다시 실행하면 남은 것만 이어서 바뀐다.
    """
    settings = get_settings()
    preview = plan(conn, code)

    done: list[dict[str, str]] = []
    for item in preview["changes"]:
        directory = paths.safe_join(settings.projects_dir, item["dir_name"])
        index_md = directory / "index.md"
        if not index_md.exists():
            continue

        doc = md.load(index_md)
        doc.meta["id"] = item["new_id"]
        md.save(index_md, doc)

        target = paths.safe_join(settings.projects_dir, item["new_dir_name"])
        if target != directory:
            if target.exists():
                target = paths.unique_path(settings.projects_dir, item["new_dir_name"], "")
            try:
                paths.move(directory, target)
            except paths.FileInUseError:
                # id 는 이미 고쳤다. 색인을 다시 만들어 파일과 맞춘 뒤 사정을 알린다.
                reindex_all(conn)
                conn.commit()
                raise
        done.append({"id": item["id"], "new_id": item["new_id"], "title": item["title"]})

    # 보관함에 있는 과제도 함께 맞춘다 (TODO 60).
    #
    # 두 가지를 고친다 — 보관된 폴더 안 index.md 의 id, 그리고 되돌아갈 자리를 적어 둔
    # 보관함 기록의 경로. 하나만 고치면 되돌린 뒤에 둘이 어긋난다.
    trashed_done = []
    folder_map: dict[str, str] = {}
    for item in preview.get("trashed", []):
        folder = settings.trash_dir / item["folder"]
        index_md = folder / "index.md"
        if not index_md.is_file():
            continue
        try:
            doc = md.load(index_md)
            doc.meta["id"] = item["new_id"]
            md.save(index_md, doc)
        except (OSError, ValueError):
            continue
        folder_map[paths.project_dir_name(item["id"], item["title"])] = paths.project_dir_name(
            item["new_id"], item["title"]
        )
        trashed_done.append({"id": item["id"], "new_id": item["new_id"], "title": item["title"]})

    # 되돌아갈 자리도 새 번호로. 살아 있는 과제의 폴더 이름 변경도 함께 반영한다 —
    # 보관함에는 그 과제의 진행일지·첨부가 들어 있을 수 있다.
    for item in preview["changes"]:
        folder_map[item["dir_name"]] = item["new_dir_name"]
    from . import trash as trash_service

    rewritten = trash_service.rewrite_origins(folder_map)

    # 파일이 원본이다. 전부 옮긴 뒤 색인을 통째로 다시 만든다.
    reindex_all(conn)
    conn.commit()
    return {
        "code": preview["code"],
        "changed": done,
        "skipped": preview["skipped"],
        "trashed": trashed_done,
        "trash_paths_updated": rewritten,
    }
