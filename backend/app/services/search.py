"""통합 검색.

FTS5 trigram은 3글자 이상에서만 매칭되므로, 짧은 질의는 LIKE로 처리한다.
한국어는 형태소 분석 없이도 부분 문자열 검색이면 대부분 충분하다.
"""
from __future__ import annotations

import sqlite3

SNIPPET_RADIUS = 70
MIN_FTS_LENGTH = 3


def _fts_query(text: str) -> str:
    """FTS5 문법 문자를 그대로 검색어로 다루기 위해 통째로 인용한다."""
    return '"' + text.replace('"', '""') + '"'


def make_snippet(body: str, query: str) -> str:
    body = (body or "").replace("\n", " ").strip()
    if not body:
        return ""
    position = body.lower().find(query.lower())
    if position < 0:
        return body[: SNIPPET_RADIUS * 2] + ("…" if len(body) > SNIPPET_RADIUS * 2 else "")
    start = max(0, position - SNIPPET_RADIUS)
    end = min(len(body), position + len(query) + SNIPPET_RADIUS)
    return ("…" if start > 0 else "") + body[start:end] + ("…" if end < len(body) else "")


def _matching_refs(conn: sqlite3.Connection, query: str, limit: int) -> list[tuple[str, str]]:
    """(kind, ref_id) 목록. FTS를 쓸 수 있으면 FTS로, 아니면 LIKE로 찾는다."""
    if len(query) >= MIN_FTS_LENGTH:
        try:
            rows = conn.execute(
                "SELECT kind, ref_id FROM search_fts WHERE search_fts MATCH ? LIMIT ?",
                (_fts_query(query), limit),
            ).fetchall()
            return [(row["kind"], row["ref_id"]) for row in rows]
        except sqlite3.OperationalError:
            pass  # trigram 미지원 등 — LIKE로 물러난다

    pattern = f"%{query}%"
    rows = conn.execute(
        """
        SELECT 'project' AS kind, id AS ref_id FROM project
         WHERE title LIKE ? OR body LIKE ?
        UNION ALL
        SELECT 'entry' AS kind, CAST(id AS TEXT) AS ref_id FROM entry
         WHERE title LIKE ? OR body LIKE ?
        UNION ALL
        SELECT 'report' AS kind, CAST(id AS TEXT) AS ref_id FROM report
         WHERE title LIKE ? OR body LIKE ? OR audience LIKE ?
        LIMIT ?
        """,
        (pattern, pattern, pattern, pattern, pattern, pattern, pattern, limit),
    ).fetchall()
    return [(row["kind"], row["ref_id"]) for row in rows]


def search(conn: sqlite3.Connection, query: str, limit: int = 60) -> dict:
    query = (query or "").strip()
    if not query:
        return {"query": "", "projects": [], "entries": [], "reports": [], "attachments": [], "total": 0}

    refs = _matching_refs(conn, query, limit)
    project_ids = [ref for kind, ref in refs if kind == "project"]
    entry_ids = [int(ref) for kind, ref in refs if kind == "entry"]
    report_ids = [int(ref) for kind, ref in refs if kind == "report"]

    projects = []
    if project_ids:
        placeholders = ",".join("?" * len(project_ids))
        for row in conn.execute(
            f"SELECT id, title, status, grp, body, updated_at FROM project WHERE id IN ({placeholders})",
            project_ids,
        ):
            projects.append(
                {
                    "id": row["id"],
                    "title": row["title"],
                    "status": row["status"],
                    "group": row["grp"],
                    "updated_at": row["updated_at"],
                    "snippet": make_snippet(row["body"], query),
                }
            )

    entries = []
    if entry_ids:
        placeholders = ",".join("?" * len(entry_ids))
        for row in conn.execute(
            f"""
            SELECT e.id, e.project_id, e.date, e.title, e.body, p.title AS project_title
              FROM entry e JOIN project p ON p.id = e.project_id
             WHERE e.id IN ({placeholders})
             ORDER BY e.date DESC
            """,
            entry_ids,
        ):
            entries.append(
                {
                    "id": row["id"],
                    "project_id": row["project_id"],
                    "project_title": row["project_title"],
                    "date": row["date"],
                    "title": row["title"],
                    "snippet": make_snippet(row["body"], query),
                }
            )

    # 보고 문서. "그 회의체에 뭘 보고했더라" 를 상단 검색 하나로 답한다 (TODO 53).
    reports = []
    if report_ids:
        placeholders = ",".join("?" * len(report_ids))
        for row in conn.execute(
            f"""
            SELECT r.id, r.project_id, r.report_date, r.title, r.audience, r.body, r.frozen_at,
                   p.title AS project_title
              FROM report r JOIN project p ON p.id = r.project_id
             WHERE r.id IN ({placeholders})
             ORDER BY r.report_date DESC, r.id DESC
            """,
            report_ids,
        ):
            reports.append(
                {
                    "id": row["id"],
                    "project_id": row["project_id"],
                    "project_title": row["project_title"],
                    "report_date": row["report_date"],
                    "title": row["title"],
                    "audience": row["audience"],
                    "frozen": bool(row["frozen_at"]),
                    "snippet": make_snippet(row["body"], query),
                }
            )

    # 첨부는 본문이 없으므로 파일명으로만 찾는다.
    attachments = [
        {
            "id": row["id"],
            "project_id": row["project_id"],
            "project_title": row["project_title"],
            "orig_name": row["orig_name"],
            "rel_path": row["rel_path"],
            "size_bytes": row["size_bytes"],
        }
        for row in conn.execute(
            """
            SELECT a.id, a.project_id, a.orig_name, a.rel_path, a.size_bytes, p.title AS project_title
              FROM attachment a JOIN project p ON p.id = a.project_id
             WHERE a.orig_name LIKE ?
             ORDER BY a.rel_path LIMIT ?
            """,
            (f"%{query}%", limit),
        )
    ]

    return {
        "query": query,
        "projects": projects,
        "entries": entries,
        "reports": reports,
        "attachments": attachments,
        "total": len(projects) + len(entries) + len(reports) + len(attachments),
    }


def project_ids_matching(conn: sqlite3.Connection, query: str) -> list[str]:
    """검색어에 걸리는 과제 id 목록 (본문·진행일지·보고·첨부 파일명 모두 대상)."""
    result = search(conn, query, limit=500)
    ids = {item["id"] for item in result["projects"]}
    ids.update(item["project_id"] for item in result["entries"])
    ids.update(item["project_id"] for item in result["reports"])
    ids.update(item["project_id"] for item in result["attachments"])
    return sorted(ids)
