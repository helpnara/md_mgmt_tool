"""통합 검색.

FTS5 trigram은 3글자 이상에서만 매칭되므로, 짧은 질의는 LIKE로 처리한다.
한국어는 형태소 분석 없이도 부분 문자열 검색이면 대부분 충분하다.
"""
from __future__ import annotations

import sqlite3

SNIPPET_RADIUS = 70
MIN_FTS_LENGTH = 3

# 종류마다 따로 상한을 둔다.
#
# 예전에는 셋을 합쳐 60개였다. 그래서 흔한 낱말로 찾으면 진행일지가 자리를 다 먹고
# **제목이 딱 맞는 과제가 밀려날 수** 있었다. 종류를 나누면 그런 일이 없다.
KIND_LIMITS = {"project": 30, "entry": 40, "report": 30}
ATTACHMENT_LIMIT = 20


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


def _refs_for(
    conn: sqlite3.Connection, query: str, kind: str, limit: int
) -> tuple[list[str], bool]:
    """한 종류의 ref_id 목록과 **잘렸는지 여부**.

    상한보다 하나 더 읽어 본다. 하나가 더 있으면 잘린 것이다 — 그래야 화면이
    "N건" 이 아니라 "N건 이상" 이라고 말할 수 있다.
    """
    if len(query) >= MIN_FTS_LENGTH:
        try:
            rows = conn.execute(
                "SELECT ref_id FROM search_fts WHERE search_fts MATCH ? AND kind = ? LIMIT ?",
                (_fts_query(query), kind, limit + 1),
            ).fetchall()
            return [row["ref_id"] for row in rows[:limit]], len(rows) > limit
        except sqlite3.OperationalError:
            pass  # trigram 미지원 등 — LIKE로 물러난다

    pattern = f"%{query}%"
    sql = {
        "project": "SELECT id AS ref_id FROM project WHERE title LIKE ? OR body LIKE ?",
        "entry": "SELECT CAST(id AS TEXT) AS ref_id FROM entry WHERE title LIKE ? OR body LIKE ?",
        "report": (
            "SELECT CAST(id AS TEXT) AS ref_id FROM report"
            " WHERE title LIKE ? OR body LIKE ? OR audience LIKE ?"
        ),
    }[kind]
    params = [pattern] * (3 if kind == "report" else 2)
    rows = conn.execute(f"{sql} LIMIT ?", (*params, limit + 1)).fetchall()
    return [row["ref_id"] for row in rows[:limit]], len(rows) > limit


def search(conn: sqlite3.Connection, query: str, limit: int | None = None) -> dict:
    """통합 검색. 종류마다 상한이 따로 있고, **잘렸으면 잘렸다고 알린다.**

    `limit` 은 목록 거르기(`project_ids_matching`)처럼 더 많이 필요할 때만 준다.
    """
    query = (query or "").strip()
    if not query:
        return {
            "query": "", "projects": [], "entries": [], "reports": [], "attachments": [],
            "total": 0, "truncated": {},
        }

    # 상한을 통째로 올려 받는 경우(목록 거르기)를 위해 값으로 넘긴다.
    # 모듈 전역을 고치면 그 뒤의 모든 검색이 함께 바뀐다.
    caps = {kind: (limit or KIND_LIMITS[kind]) for kind in KIND_LIMITS}
    attachment_cap = limit or ATTACHMENT_LIMIT

    project_ids, projects_cut = _refs_for(conn, query, "project", caps["project"])
    entry_refs, entries_cut = _refs_for(conn, query, "entry", caps["entry"])
    report_refs, reports_cut = _refs_for(conn, query, "report", caps["report"])
    entry_ids = [int(ref) for ref in entry_refs]
    report_ids = [int(ref) for ref in report_refs]

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
            (f"%{query}%", attachment_cap + 1),
        )
    ]
    attachments_cut = len(attachments) > attachment_cap
    attachments = attachments[:attachment_cap]

    return {
        "query": query,
        "projects": projects,
        "entries": entries,
        "reports": reports,
        "attachments": attachments,
        "total": len(projects) + len(entries) + len(reports) + len(attachments),
        # 어느 갈래가 잘렸는지. 화면이 "N건" 대신 "N건 이상" 이라고 말하는 근거다.
        "truncated": {
            "projects": projects_cut,
            "entries": entries_cut,
            "reports": reports_cut,
            "attachments": attachments_cut,
        },
    }


def project_ids_matching(conn: sqlite3.Connection, query: str) -> list[str]:
    """검색어에 걸리는 과제 id 목록 (본문·진행일지·보고·첨부 파일명 모두 대상)."""
    result = search(conn, query, limit=500)
    ids = {item["id"] for item in result["projects"]}
    ids.update(item["project_id"] for item in result["entries"])
    ids.update(item["project_id"] for item in result["reports"])
    ids.update(item["project_id"] for item in result["attachments"])
    return sorted(ids)
