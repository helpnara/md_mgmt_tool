"""과제 분류 넷(성격 · 분류 · 수행 방식 · 비용구분)의 값 정리 (TODO 275).

값은 과제 · 접수 파일에 **글자 그대로** 적힌다(config.CLASSIFICATIONS). 그래서 설정의 목록에서 이름을 고치면
이미 적힌 과제 · 접수는 옛 이름으로 남아 홈 표에 따로 한 줄로 서고, 접수 풀의 거르기 상자에서는 고를 수 없었다(전수 조사 빈틈 1).
이제 ① 값마다 **쓰는 수**(과제 · 접수 — 목록에 없는 옛 값까지)를 보이고 ② **[이름 바꾸기]** 는 쓰는 과제 · 접수의 값과 목록을 함께 고친다
— 새 이름이 이미 목록에 있으면 **합치기**(옛 값이 그 이름으로). 명부의 [다른 이름으로 통일](people.rename_owner)과 같은 결 — 파일부터 고친다.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from ..config import CLASSIFICATION_KEYS, CLASSIFICATION_LABELS
from ..vault import markdown as md
from . import settings as settings_service


def usage(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    """칸마다 [{value, projects, intakes, listed}] — 목록 순서, 그다음 목록에 없는(옛) 값."""
    lists = settings_service.classifications()
    out: dict[str, list[dict[str, Any]]] = {}
    for key in CLASSIFICATION_KEYS:
        counts: dict[str, dict[str, int]] = {}
        for table, kind in (("project", "projects"), ("intake", "intakes")):
            for row in conn.execute(f"SELECT TRIM({key}) AS v, COUNT(*) AS n FROM {table} WHERE {key} IS NOT NULL AND TRIM({key}) != '' GROUP BY TRIM({key})"):
                counts.setdefault(row["v"], {"projects": 0, "intakes": 0})[kind] = row["n"]
        listed = lists[key]
        order = [*listed, *sorted(v for v in counts if v not in listed)]
        out[key] = [{"value": v, **counts.get(v, {"projects": 0, "intakes": 0}), "listed": v in listed} for v in order]
    return out


def rename(conn: sqlite3.Connection, field: str, old: str, new: str) -> dict[str, Any]:
    """`field` 의 값 `old` 를 `new` 로 — 쓰는 과제 · 접수 파일과 설정 목록을 함께. new 가 이미 목록에 있으면 합친다."""
    from ..services.projects import now_iso, project_dir
    from ..vault.indexer import index_project
    from . import intakes as intakes_service

    if field not in CLASSIFICATION_KEYS:
        raise ValueError("바꿀 칸이 올바르지 않습니다.")
    old = " ".join((old or "").split())
    new = " ".join((new or "").split())
    if not old or not new:
        raise ValueError("옛 이름과 새 이름을 모두 적어 주세요.")
    if old == new:
        raise ValueError("두 이름이 같습니다.")
    label = CLASSIFICATION_LABELS[field]
    if len(new) > settings_service.CLASSIFICATION_MAX_LEN:
        raise ValueError(f"{label}: 새 이름이 너무 깁니다({settings_service.CLASSIFICATION_MAX_LEN}자 이하).")
    projects = 0
    for row in conn.execute(f"SELECT id FROM project WHERE TRIM({field}) = ? ORDER BY id", (old,)).fetchall():
        directory = project_dir(conn, row["id"])
        index_md = directory / "index.md"
        doc = md.load(index_md)
        if " ".join(str(doc.meta.get(field) or "").split()) != old:
            continue
        doc.meta[field] = new
        doc.meta["updated_at"] = now_iso()
        md.save(index_md, doc)
        index_project(conn, directory)
        projects += 1
    intakes = 0
    for row in conn.execute(f"SELECT id FROM intake WHERE TRIM({field}) = ? ORDER BY id", (old,)).fetchall():
        directory = intakes_service.intake_dir(conn, row["id"])
        request = directory / intakes_service.REQUEST_FILE
        doc = md.load(request)
        if " ".join(str(doc.meta.get(field) or "").split()) != old:
            continue
        doc.meta[field] = new
        doc.meta["updated_at"] = now_iso()
        md.save(request, doc)
        intakes_service.index_intake(conn, directory)
        intakes += 1
    # 목록 — 옛 이름 자리에 새 이름(이미 있으면 옛 이름만 뺀다 = 합치기). 목록에 없던 옛 값이면 목록은 그대로(새 이름이 없으면 끝에 더함)
    lists = settings_service.classifications()
    items = list(lists[field])
    merged = new in items
    if old in items:
        items = [item for item in items if item != old] if merged else [new if item == old else item for item in items]
    elif not merged:
        items.append(new)
    if items != lists[field]:
        settings_service.save({"classifications": {**lists, field: items}})
    conn.commit()
    return {"field": field, "old": old, "new": new, "merged": merged, "projects": projects, "intakes": intakes}
