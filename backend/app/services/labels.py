"""그룹 · 과제 태그의 이름 바꾸기 · 합치기 (TODO 341 — 전수 검토 D4).

그룹과 태그는 자유 입력이라 "MES" / "mes" / "MES 고도화" 처럼 표기가 흔들리면 홈 표 · 거르기가 두 줄로 갈라졌다.
분류 넷(`classify.py`, TODO 275)처럼 **쓰는 과제 수**를 보이고, [이름 바꾸기]는 쓰는 과제 파일의 값을 함께 고친다 —
새 이름을 이미 쓰는 과제가 있으면 그대로 **합치기**. 파일부터 고치고 색인을 다시 만든다.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from ..vault import markdown as md

KINDS = ("group", "tag")
MAX_LEN = 40


def usage(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    """{"group": [{value, projects}], "tag": [...]} — 많이 쓰는 것부터."""
    groups = [{"value": row["v"], "projects": row["n"]} for row in conn.execute(
        "SELECT TRIM(grp) AS v, COUNT(*) AS n FROM project WHERE grp IS NOT NULL AND TRIM(grp) != ''"
        " GROUP BY TRIM(grp) ORDER BY n DESC, v")]
    tags = [{"value": row["v"], "projects": row["n"]} for row in conn.execute(
        "SELECT t.name AS v, COUNT(DISTINCT pt.project_id) AS n FROM project_tag pt JOIN tag t ON t.id = pt.tag_id"
        " GROUP BY t.name ORDER BY n DESC, v")]
    return {"group": groups, "tag": tags}


def _clean(text: str) -> str:
    return " ".join((text or "").split())


def rename(conn: sqlite3.Connection, kind: str, old: str, new: str) -> dict[str, Any]:
    """`kind`(group · tag)의 `old` 를 `new` 로 — 쓰는 과제 파일을 함께. new 를 이미 쓰면 합친다."""
    from .projects import now_iso, project_dir
    from ..vault.indexer import index_project

    if kind not in KINDS:
        raise ValueError("바꿀 칸이 올바르지 않습니다.")
    old, new = _clean(old), _clean(new)
    if not old or not new:
        raise ValueError("옛 이름과 새 이름을 모두 적어 주세요.")
    if old == new:
        raise ValueError("두 이름이 같습니다.")
    if len(new) > MAX_LEN:
        raise ValueError(f"새 이름이 너무 깁니다({MAX_LEN}자 이하).")
    if kind == "group":
        merged = conn.execute("SELECT 1 FROM project WHERE TRIM(grp) = ? LIMIT 1", (new,)).fetchone() is not None
        ids = [row["id"] for row in conn.execute("SELECT id FROM project WHERE TRIM(grp) = ? ORDER BY id", (old,))]
    else:
        # 태그는 대소문자 · 띄어쓰기 · # 만 다른 것을 이미 한 태그로 본다(TODO 214 D12) — 같은 열쇠로 찾는다
        from .. import schemas as rules

        old_key, new_key = rules.tag_key(old), rules.tag_key(new)
        used = {rules.tag_key(row["name"]): row["name"] for row in conn.execute(
            "SELECT DISTINCT t.name FROM tag t JOIN project_tag pt ON pt.tag_id = t.id")}
        merged = new_key != old_key and new_key in used
        ids = [row["project_id"] for row in conn.execute(
            "SELECT DISTINCT pt.project_id, t.name FROM project_tag pt JOIN tag t ON t.id = pt.tag_id ORDER BY pt.project_id")
            if rules.tag_key(row["name"]) == old_key]
        if new_key == old_key:
            # 표기만 바꾸기(mes → MES) — 색인의 태그 이름이 보이는 표기다
            for row in conn.execute("SELECT id, name FROM tag").fetchall():
                if rules.tag_key(row["name"]) == old_key:
                    conn.execute("UPDATE tag SET name = ? WHERE id = ?", (rules.clean_tag(new), row["id"]))
    changed = 0
    for project_id in ids:
        directory = project_dir(conn, project_id)
        index_md = directory / "index.md"
        doc = md.load(index_md)
        if kind == "group":
            if _clean(str(doc.meta.get("group") or "")) != old:
                continue
            doc.meta["group"] = new
        else:
            tags = [str(item) for item in (doc.meta.get("tags") or [])]
            if old_key not in [rules.tag_key(t) for t in tags]:
                continue
            out: list[str] = []
            for tag in tags:
                value = rules.clean_tag(new) if rules.tag_key(tag) == old_key else tag
                if rules.tag_key(value) not in [rules.tag_key(item) for item in out]:   # 합치면 같은 태그가 둘 — 하나만
                    out.append(value)
            doc.meta["tags"] = out
        doc.meta["updated_at"] = now_iso()
        md.save(index_md, doc)
        index_project(conn, directory)
        changed += 1
    conn.commit()
    return {"kind": kind, "old": old, "new": new, "merged": merged, "projects": changed}
