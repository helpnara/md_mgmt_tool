"""통합 검색.

FTS5 trigram은 3글자 이상에서만 매칭되므로, 짧은 질의는 LIKE로 처리한다.
한국어는 형태소 분석 없이도 부분 문자열 검색이면 대부분 충분하다.

**두 길이 같은 곳을 봐야 한다.** FTS 색인에는 담당자·태그·유관부서가 본문 뒤에
덧붙어 있으므로, LIKE 쪽도 그 자리를 함께 훑는다. 그러지 않으면 "이준" 같은 두 글자
이름이 짧다는 이유만으로 안 찾힌다.
"""
from __future__ import annotations

import re
import sqlite3

from .projects import overview_is_blank, stage_map

SNIPPET_RADIUS = 70
MIN_FTS_LENGTH = 3

# 종류마다 따로 상한을 둔다.
#
# 예전에는 셋을 합쳐 60개였다. 그래서 흔한 낱말로 찾으면 진행일지가 자리를 다 먹고
# **제목이 딱 맞는 과제가 밀려날 수** 있었다. 종류를 나누면 그런 일이 없다.
KIND_LIMITS = {"project": 30, "entry": 40, "report": 30}
ATTACHMENT_LIMIT = 20
# 접수 (TODO 144). 건수가 과제보다 훨씬 적어 LIKE 로 충분하다 — FTS 색인에 넣지 않는다.
INTAKE_LIMIT = 20


def _fts_query(text: str) -> str:
    """FTS5 문법 문자를 그대로 검색어로 다루기 위해 통째로 인용한다."""
    return '"' + text.replace('"', '""') + '"'


def make_snippet(body: str, query: str) -> str:
    """검색어 둘레의 한 줄. **서식 기호는 뺀다** (TODO 103-C) — 보고 이력의 발췌와 같은 눈으로."""
    from .reports import readable_text

    body = readable_text(body)
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
    # 두 글자 이하로 찾을 때 오는 길이다. FTS 색인에는 담당자·태그·유관부서가 본문 뒤에
    # 덧붙어 있는데, 여기서 제목·본문만 훑으면 **짧은 이름은 영영 안 찾힌다** —
    # "이준" 같은 두 글자 이름이나 "구매" 같은 부서가 그렇다 (TODO 92).
    # FTS 가 보는 것과 같은 자리를 보게 맞춘다.
    sql = {
        "project": (
            "SELECT id AS ref_id FROM project p"
            " WHERE p.title LIKE ? OR p.body LIKE ?"
            "    OR EXISTS (SELECT 1 FROM project_owner po"
            "                WHERE po.project_id = p.id AND po.name LIKE ?)"
            "    OR EXISTS (SELECT 1 FROM project_tag pt JOIN tag t ON t.id = pt.tag_id"
            "                WHERE pt.project_id = p.id AND t.name LIKE ?)"
            "    OR EXISTS (SELECT 1 FROM project_partner pp"
            "                WHERE pp.project_id = p.id"
            "                  AND (pp.team LIKE ? OR pp.person LIKE ?))"
        ),
        "entry": "SELECT CAST(id AS TEXT) AS ref_id FROM entry WHERE title LIKE ? OR body LIKE ?",
        "report": (
            "SELECT CAST(id AS TEXT) AS ref_id FROM report"
            " WHERE title LIKE ? OR body LIKE ? OR audience LIKE ?"
        ),
    }[kind]
    params = [pattern] * {"project": 6, "entry": 2, "report": 3}[kind]
    rows = conn.execute(f"{sql} LIMIT ?", (*params, limit + 1)).fetchall()
    return [row["ref_id"] for row in rows[:limit]], len(rows) > limit


# ── 질의 읽기 (TODO 254 1차) ─────────────────────────────────────────────────
# 여러 낱말 = 모두 들어간 것 · "따옴표" = 한 구절 · -낱말 = 빼기 · 칸:값 = 칸 지정
FIELD_NAMES = {"담당": "owner", "담당자": "owner", "사람": "owner", "태그": "tag", "상태": "status",
               "연도": "year", "해": "year", "종류": "kind"}
KIND_WORDS = {"과제": "projects", "일지": "entries", "진행일지": "entries", "보고": "reports", "첨부": "attachments",
              "접수": "intakes", "역량": "activities", "교육": "activities", "행사": "activities", "팀원역량": "activities",
              "회고": "contributions", "역할": "contributions", "담당과역할": "contributions"}
GROUPS = ("projects", "intakes", "entries", "reports", "attachments", "contributions", "activities")
_TOKEN = re.compile(r'(-?)(?:([^\s"]+?)[:：])?"([^"]*)"|(\S+)')
BIG = 2000
ACTIVITY_LIMIT = 20
CONTRIBUTION_LIMIT = 20


def parse_query(text: str) -> dict:
    """찾는 말 → {words, excludes, fields, kinds}. 모르는 칸 이름(`x:y`)은 그냥 낱말로 본다."""
    words: list[str] = []
    excludes: list[str] = []
    fields: dict[str, list[str]] = {}
    for match in _TOKEN.finditer(text or ""):
        neg, key, quoted, bare = match.groups()
        if bare is not None:
            neg = "-" if bare.startswith("-") and len(bare) > 1 else ""
            bare = bare[1:] if neg else bare
            found = re.match(r"^([^:：]+)[:：](.+)$", bare)
            if found and found.group(1) in FIELD_NAMES:
                fields.setdefault(FIELD_NAMES[found.group(1)], []).append(found.group(2))
                continue
            token = bare
        else:
            if key and key in FIELD_NAMES:
                fields.setdefault(FIELD_NAMES[key], []).append(quoted)
                continue
            token = (f"{key}:" if key else "") + quoted
        token = token.strip()
        if token:
            (excludes if neg else words).append(token)
    kinds = [KIND_WORDS[re.sub(r"\s+", "", k)] for k in fields.get("kind", []) if re.sub(r"\s+", "", k) in KIND_WORDS]
    return {"words": words, "excludes": excludes, "fields": {k: v for k, v in fields.items() if k != "kind"}, "kinds": kinds}


def _status_codes(values: list[str]) -> set[str]:
    from ..config import STATUS_LABELS

    by_label = {label: key for key, label in STATUS_LABELS.items()}
    return {by_label.get(v, v) for v in values}


def _matching(conn: sqlite3.Connection, kind: str, words: list[str], excludes: list[str]) -> list[str]:
    """모든 낱말이 들어간 ref_id(첫 낱말의 순서) — 빼기 낱말이 든 것은 뺀다."""
    found: list[str] | None = None
    for word in words:
        refs, _ = _refs_for(conn, word, kind, BIG)
        keep = set(refs)
        found = refs if found is None else [r for r in found if r in keep]
    for word in excludes:
        drop = set(_refs_for(conn, word, kind, BIG)[0])
        found = [r for r in (found or []) if r not in drop]
    return found or []


def _project_facts(conn: sqlite3.Connection) -> dict[str, dict]:
    facts: dict[str, dict] = {}
    for row in conn.execute("SELECT id, title, status, start_date, body, updated_at FROM project"):
        facts[row["id"]] = {"title": row["title"] or "", "status": row["status"], "body": row["body"] or "",
                            "year": (row["start_date"] or row["id"])[:4], "owners": [], "tags": [],
                            "updated_at": row["updated_at"] or ""}
    for row in conn.execute("SELECT project_id, name FROM project_owner"):
        if row["project_id"] in facts:
            facts[row["project_id"]]["owners"].append(row["name"])
    for row in conn.execute("SELECT pt.project_id, t.name FROM project_tag pt JOIN tag t ON t.id = pt.tag_id"):
        if row["project_id"] in facts:
            facts[row["project_id"]]["tags"].append(row["name"])
    return facts


def _project_ok(fact: dict | None, fields: dict[str, list[str]], year: str | None = None) -> bool:
    if fact is None:
        return False
    if any(not any(v in o for o in fact["owners"]) for v in fields.get("owner", [])):
        return False
    if any(not any(v.lower() in t.lower() for t in fact["tags"]) for v in fields.get("tag", [])):
        return False
    if fields.get("status") and fact["status"] not in _status_codes(fields["status"]):
        return False
    if fields.get("year") and (year or fact["year"]) not in fields["year"]:
        return False
    return True


def _score(fact: dict, words: list[str]) -> int:
    """관련도 — 낱말마다 제목 3 · 담당 · 태그 2 · 본문 1."""
    score = 0
    for word in words:
        w = word.lower()
        if w in fact["title"].lower():
            score += 3
        if any(w in x.lower() for x in fact["owners"] + fact["tags"]):
            score += 2
        if w in fact["body"].lower():
            score += 1
    return score


def search(conn: sqlite3.Connection, query: str, limit: int | None = None, sort: str = "relevance") -> dict:
    """통합 검색. 종류마다 상한이 따로 있고, **잘렸으면 잘렸다고 알린다.**

    254 1차 — 여러 낱말은 **모두 들어간 것**, "구절", -빼기, 칸 지정(담당: · 태그: · 상태: · 연도: · 종류:).
    과제는 관련도 순(제목 > 담당 · 태그 > 본문, 같으면 최근) — `sort="recent"` 면 최근 순.
    `limit` 은 목록 거르기(`project_ids_matching`)처럼 더 많이 필요할 때만 준다.
    """
    query = (query or "").strip()
    parsed = parse_query(query)
    words, excludes, fields = parsed["words"], parsed["excludes"], parsed["fields"]
    empty = {"query": query, "parsed": parsed, "projects": [], "entries": [], "reports": [], "attachments": [],
             "intakes": [], "activities": [], "contributions": [], "total": 0, "truncated": {}}
    if not words and not fields:
        return empty
    wanted = set(parsed["kinds"] or GROUPS)
    first = words[0] if words else ""
    caps = {kind: (limit or KIND_LIMITS[kind]) for kind in KIND_LIMITS}
    facts = _project_facts(conn)
    truncated: dict[str, bool] = {}

    projects = []
    if "projects" in wanted:
        if words:
            ids = _matching(conn, "project", words, excludes)
        else:
            drop = {r for w in excludes for r in _refs_for(conn, w, "project", BIG)[0]}
            ids = [pid for pid in facts if pid not in drop]
        ids = [pid for pid in ids if _project_ok(facts.get(pid), fields)]
        ids.sort(key=lambda pid: facts[pid]["updated_at"], reverse=True)
        if sort != "recent" and words:
            ids.sort(key=lambda pid: -_score(facts[pid], words))   # 같은 점수 안에서는 최근 순이 남는다(안정 정렬)
        truncated["projects"] = len(ids) > caps["project"]
        ids = ids[: caps["project"]]
        stages = stage_map(conn) if ids else {}  # 과제명 뒤 단계 띠 (TODO 175)
        for pid in ids:
            row = conn.execute("SELECT id, title, status, grp, body, updated_at FROM project WHERE id = ?", (pid,)).fetchone()
            projects.append({
                "id": row["id"], "title": row["title"], "stage": stages.get(row["id"]), "status": row["status"],
                "group": row["grp"], "updated_at": row["updated_at"],
                # 서식 그대로인 개요는 발췌하지 않는다 — 안내 문장이 본문인 양 실린다 (TODO 106-B).
                "snippet": "" if overview_is_blank(row["body"]) else make_snippet(row["body"], first),
            })

    # 진행일지 · 보고 — 낱말이 있을 때만(칸만으로 찾으면 너무 많다)
    entries = []
    if "entries" in wanted and words:
        refs = _matching(conn, "entry", words, excludes)
        rows = []
        if refs:
            marks = ",".join("?" * len(refs))
            rows = conn.execute(
                f"SELECT e.id, e.project_id, e.date, e.title, e.body, e.author, p.title AS project_title FROM entry e"
                f" JOIN project p ON p.id = e.project_id WHERE e.id IN ({marks}) ORDER BY e.date DESC, e.id DESC",
                [int(r) for r in refs]).fetchall()
        rows = [r for r in rows if _project_ok(facts.get(r["project_id"]), {**fields, "owner": []}, (r["date"] or "")[:4])
                and all(v in (r["author"] or "") or any(v in o for o in facts[r["project_id"]]["owners"]) for v in fields.get("owner", []))]
        truncated["entries"] = len(rows) > caps["entry"]
        entries = [{"id": r["id"], "project_id": r["project_id"], "project_title": r["project_title"], "date": r["date"],
                    "title": r["title"], "snippet": make_snippet(r["body"], first)} for r in rows[: caps["entry"]]]

    # 보고 문서. "그 회의체에 뭘 보고했더라" 를 상단 검색 하나로 답한다 (TODO 53).
    reports = []
    if "reports" in wanted and words:
        refs = _matching(conn, "report", words, excludes)
        rows = []
        if refs:
            marks = ",".join("?" * len(refs))
            rows = conn.execute(
                f"SELECT r.id, r.project_id, r.report_date, r.title, r.audience, r.body, r.frozen_at, p.title AS project_title"
                f" FROM report r JOIN project p ON p.id = r.project_id WHERE r.id IN ({marks})"
                f" ORDER BY r.report_date DESC, r.id DESC", [int(r) for r in refs]).fetchall()
        rows = [r for r in rows if _project_ok(facts.get(r["project_id"]), fields, (r["report_date"] or "")[:4])]
        truncated["reports"] = len(rows) > caps["report"]
        reports = [{"id": r["id"], "project_id": r["project_id"], "project_title": r["project_title"],
                    "report_date": r["report_date"], "title": r["title"], "audience": r["audience"],
                    "frozen": bool(r["frozen_at"]), "snippet": make_snippet(r["body"], first)} for r in rows[: caps["report"]]]

    # 첨부는 본문이 없으므로 파일명으로만 찾는다(첨부 안의 글은 254 2차).
    attachments = []
    if "attachments" in wanted and words:
        cap = limit or ATTACHMENT_LIMIT
        clause = " AND ".join(["a.orig_name LIKE ?"] * len(words) + ["a.orig_name NOT LIKE ?"] * len(excludes))
        rows = conn.execute(
            f"SELECT a.id, a.project_id, a.orig_name, a.rel_path, a.size_bytes, p.title AS project_title FROM attachment a"
            f" JOIN project p ON p.id = a.project_id WHERE {clause} ORDER BY a.rel_path",
            [f"%{w}%" for w in words] + [f"%{w}%" for w in excludes]).fetchall()
        rows = [r for r in rows if _project_ok(facts.get(r["project_id"]), fields)]
        truncated["attachments"] = len(rows) > cap
        attachments = [{"id": r["id"], "project_id": r["project_id"], "project_title": r["project_title"],
                        "orig_name": r["orig_name"], "rel_path": r["rel_path"], "size_bytes": r["size_bytes"]} for r in rows[:cap]]

    intakes: list[dict] = []
    if "intakes" in wanted and words:
        intakes, truncated["intakes"] = _intakes(conn, words, excludes, fields, limit or INTAKE_LIMIT)

    # 담당과 역할 · 회고 (254 A) — 역할 · 맡은 부분 · 내가 한 일 · 결과 · 기술 · 도구
    contributions: list[dict] = []
    if "contributions" in wanted and (words or fields.get("owner")):
        contributions, truncated["contributions"] = _contributions(conn, words, excludes, fields, facts, limit or CONTRIBUTION_LIMIT)

    # 팀원역량 기록 — 교육 · 행사 (254 A)
    activities: list[dict] = []
    if "activities" in wanted and (words or fields.get("owner")):
        activities, truncated["activities"] = _activities(conn, words, excludes, fields, limit or ACTIVITY_LIMIT)

    total = len(projects) + len(entries) + len(reports) + len(attachments) + len(intakes) + len(contributions) + len(activities)
    return {**empty, "projects": projects, "entries": entries, "reports": reports, "attachments": attachments,
            "intakes": intakes, "contributions": contributions, "activities": activities, "total": total,
            # 어느 갈래가 잘렸는지. 화면이 "N건" 대신 "N건 이상" 이라고 말하는 근거다.
            "truncated": {k: bool(v) for k, v in truncated.items()}}


def _all_words(text: str, words: list[str], excludes: list[str]) -> bool:
    low = text.lower()
    return all(w.lower() in low for w in words) and not any(w.lower() in low for w in excludes)


def _intakes(conn: sqlite3.Connection, words: list[str], excludes: list[str], fields: dict, cap: int) -> tuple[list[dict], bool]:
    """접수 건 — 번호·제목·요청 본문·과제리더·소속·태그를 훑는다 (TODO 144). 낱말이 모두 들어간 것(254).

    반년 뒤 "그 요청 어떻게 됐더라" 를 찾는 길이다. 반려·이관된 것도 찾아져야 한다 —
    그래서 풀(판정 전)만이 아니라 전부를 본다.
    """
    from ..config import INTAKE_STATUS_LABELS

    out = []
    for row in conn.execute(
            "SELECT id, title, status, leader, leader_team, received_on, project_id, merged_into, body, tags"
            " FROM intake ORDER BY received_on DESC, id DESC"):
        text = " ".join(str(row[k] or "") for k in ("id", "title", "body", "leader", "leader_team", "tags"))
        if not _all_words(text, words, excludes):
            continue
        if any(v not in (row["leader"] or "") for v in fields.get("owner", [])):
            continue
        if fields.get("year") and (row["received_on"] or "")[:4] not in fields["year"]:
            continue
        out.append({
            "id": row["id"], "title": row["title"], "status": row["status"],
            "status_label": INTAKE_STATUS_LABELS.get(row["status"], row["status"]),
            "leader": row["leader"], "leader_team": row["leader_team"], "received_on": row["received_on"],
            "project_id": row["project_id"] or row["merged_into"], "snippet": make_snippet(row["body"] or "", words[0] if words else ""),
        })
    return out[:cap], len(out) > cap


def _contributions(conn, words, excludes, fields, facts, cap) -> tuple[list[dict], bool]:
    out = []
    for row in conn.execute(
            "SELECT c.project_id, c.name, c.role, c.part, c.did, c.result, c.skills, p.title AS project_title"
            " FROM project_contribution c JOIN project p ON p.id = c.project_id ORDER BY c.project_id DESC, c.name"):
        text = " ".join(str(row[k] or "") for k in ("name", "role", "part", "did", "result", "skills"))
        if not _all_words(text, words, excludes):
            continue
        if any(v not in (row["name"] or "") for v in fields.get("owner", [])):
            continue
        if not _project_ok(facts.get(row["project_id"]), {**fields, "owner": []}):
            continue
        body = "\n".join(str(row[k] or "") for k in ("did", "result", "part", "skills"))
        out.append({"project_id": row["project_id"], "project_title": row["project_title"], "name": row["name"],
                    "role": row["role"] or "", "snippet": make_snippet(body, words[0] if words else "")})
    return out[:cap], len(out) > cap


def _activities(conn, words, excludes, fields, cap) -> tuple[list[dict], bool]:
    out = []
    for row in conn.execute("SELECT id, person, date, kind, title, host, takeaway FROM activity ORDER BY date DESC, id DESC"):
        text = " ".join(str(row[k] or "") for k in ("person", "title", "host", "takeaway"))
        if not _all_words(text, words, excludes):
            continue
        if any(v not in (row["person"] or "") for v in fields.get("owner", [])):
            continue
        if fields.get("year") and (row["date"] or "")[:4] not in fields["year"]:
            continue
        out.append({"id": row["id"], "person": row["person"], "date": row["date"], "kind": row["kind"], "title": row["title"],
                    "host": row["host"] or "", "snippet": make_snippet(row["takeaway"] or "", words[0] if words else "")})
    return out[:cap], len(out) > cap


def project_ids_matching(conn: sqlite3.Connection, query: str) -> list[str]:
    """검색어에 걸리는 과제 id 목록 (본문·진행일지·보고·첨부 파일명 모두 대상)."""
    result = search(conn, query, limit=500)
    ids = {item["id"] for item in result["projects"]}
    ids.update(item["project_id"] for item in result["entries"])
    ids.update(item["project_id"] for item in result["reports"])
    ids.update(item["project_id"] for item in result["attachments"])
    return sorted(ids)
