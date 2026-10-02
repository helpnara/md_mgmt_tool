from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import CLASSIFICATION_KEYS, FINISHED_STATUSES, STATUS_KEYS, get_settings
from ..deps import get_db
from ..vault.markdown import ExternalChangeError
from ..vault.paths import FileInUseError
from ..services import period as period_service
from ..services import projects as svc
from ..services import renumber as renumber_service
from ..services import search as search_svc
from ..services import settings as settings_service
from ..schemas import ProjectCreate, ProjectUpdate

router = APIRouter(prefix="/api/projects", tags=["projects"])

def year_clause() -> str:
    """번호의 연도(= 착수년도) — 과제목록의 [신규 착수만] 거르기가 쓴다 (TODO 181).

    연도 거르기 자체는 **수행기간**으로 바뀌었다(`period` — 다년도 과제는 해마다 보인다).
    """
    return "SUBSTR(p.id, 1, 4) = ?"


def _flip(clause: str, order: str) -> str:
    """정렬 구문의 방향을 바꾼다.

    빈 값을 뒤로 보내는 `CASE WHEN … THEN 1 ELSE 0 END` 항은 **건드리지 않는다.**
    오름차순일 때만 빈 줄이 위로 오면, 같은 열을 두 번 눌렀을 때 빈 줄이 위아래로 튀어
    예측이 안 된다. 빈 값은 어느 방향에서나 뒤에 있어야 한다.
    """
    parts = []
    for piece in _split_terms(clause):
        if piece.upper().startswith("CASE"):
            parts.append(piece)
            continue
        base = piece.removesuffix(" DESC").removesuffix(" ASC").rstrip()
        parts.append(f"{base} {'DESC' if order == 'desc' else 'ASC'}")
    return ", ".join(parts)


def _split_terms(clause: str) -> list[str]:
    """정렬 구문을 항 단위로 나눈다. **괄호 안의 쉼표는 건드리지 않는다** —
    `COALESCE(a, b)` 나 `ORDER BY x, y LIMIT 1` 같은 것이 반으로 잘리면 SQL 이 깨진다.
    """
    terms, depth, start = [], 0, 0
    for index, char in enumerate(clause):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            terms.append(clause[start:index].strip())
            start = index + 1
    terms.append(clause[start:].strip())
    return [term for term in terms if term]


SORTS = {
    "updated": "p.updated_at DESC",
    # 마지막 보고가 오래된 과제부터. 보고한 적 없는 과제가 맨 앞에 온다.
    "reported": "CASE WHEN p.last_reported_at IS NULL THEN 0 ELSE 1 END, p.last_reported_at ASC",
    "due": "CASE WHEN p.due_date IS NULL THEN 1 ELSE 0 END, p.due_date ASC",
    "title": "p.title ASC",
    "created": "p.created_at DESC",
    # 효과가 큰 과제부터. 실증효과가 있으면 그것을, 없으면 기대효과를 기준으로 본다.
    # 효과를 안 적은 과제는 맨 뒤로 보낸다 (0으로 취급하면 실제 0원 과제와 섞인다).
    "effect": (
        "CASE WHEN COALESCE(p.effect_verified, p.effect_expected) IS NULL THEN 1 ELSE 0 END,"
        " COALESCE(p.effect_verified, p.effect_expected) DESC, p.title ASC"
    ),
    # ── 열 머리글로 고르는 정렬 (TODO 57) ───────────────────────────────
    # 빈 값은 어느 방향에서나 뒤로 간다 (_flip 주석 참고).
    "id": "p.id ASC",
    # 연도를 고르면 **그 해의 상태**로 줄을 세운다 — 화면의 상태 칸이 그것을 보인다 (TODO 184).
    # 전체(연도 없음)에서는 y_status = status 다.
    "status": "p.y_status ASC, p.title ASC",
    "type": "CASE WHEN p.type IS NULL OR p.type = '' THEN 1 ELSE 0 END, p.type ASC, p.title ASC",
    "group": "CASE WHEN p.grp IS NULL OR p.grp = '' THEN 1 ELSE 0 END, p.grp ASC, p.title ASC",
    # 담당자·태그는 여러 개일 수 있다. **맨 앞 하나**를 기준으로 삼는다 —
    # 개수로 세면 "김현우"를 찾는 사람에게 아무 도움이 안 된다.
    "owner": (
        "CASE WHEN (SELECT po.name FROM project_owner po WHERE po.project_id = p.id"
        "           ORDER BY po.position, po.name LIMIT 1) IS NULL THEN 1 ELSE 0 END,"
        " (SELECT po.name FROM project_owner po WHERE po.project_id = p.id"
        "  ORDER BY po.position, po.name LIMIT 1) ASC, p.title ASC"
    ),
    "tag": (
        "CASE WHEN (SELECT t.name FROM tag t JOIN project_tag pt ON pt.tag_id = t.id"
        "           WHERE pt.project_id = p.id ORDER BY t.name LIMIT 1) IS NULL THEN 1 ELSE 0 END,"
        " (SELECT t.name FROM tag t JOIN project_tag pt ON pt.tag_id = t.id"
        "  WHERE pt.project_id = p.id ORDER BY t.name LIMIT 1) ASC, p.title ASC"
    ),
    "entries": "(SELECT COUNT(*) FROM entry e WHERE e.project_id = p.id) DESC, p.title ASC",
}


def _nature_order() -> tuple[str, list[str]]:
    """성격 열의 정렬 (TODO 159). 글자순이 아니라 **설정 목록의 순서**다 —
    연구과제/PoC → 현장적용 → 확대전개 처럼 목록 자체가 흐름이기 때문이다.
    목록에 없는 값(손으로 고친 파일)은 목록 뒤에 글자순으로, 빈 값은 어느 방향에서나 맨 뒤.

    이름은 물음표로 넘긴다 — 설정에 적힌 말에 따옴표·쉼표가 들어 있어도 SQL 이 깨지지 않는다.
    """
    names = settings_service.classifications().get("nature", [])
    when = " ".join("WHEN ? THEN %d" % index for index in range(len(names)))
    position = f"(CASE p.nature {when} ELSE {len(names)} END)" if names else "0"
    clause = (
        "CASE WHEN p.nature IS NULL OR p.nature = '' THEN 1 ELSE 0 END, "
        f"{position} ASC, p.nature ASC, p.title ASC"
    )
    return clause, list(names)


def _tags(conn: sqlite3.Connection, project_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT t.name FROM tag t JOIN project_tag pt ON pt.tag_id = t.id WHERE pt.project_id = ? ORDER BY t.name",
        (project_id,),
    ).fetchall()
    return [row["name"] for row in rows]


def _owners(conn: sqlite3.Connection, project_id: str) -> list[str]:
    return [
        row["name"]
        for row in conn.execute(
            "SELECT name FROM project_owner WHERE project_id = ? ORDER BY position, name",
            (project_id,),
        )
    ]


def _partners(conn: sqlite3.Connection, project_id: str) -> list[dict]:
    """유관부서를 팀 단위로 묶어 돌려준다 (TODO 92).

    저장은 (팀, 사람) 한 쌍이 한 줄이지만, 화면과 문서는 **팀 하나에 사람 여럿**으로 본다.
    담당자가 없는 팀은 `person` 이 빈 줄 하나로 들어 있으므로 사람 목록이 비어 나간다.
    """
    grouped: dict[str, dict] = {}
    for row in conn.execute(
        "SELECT team, person FROM project_partner WHERE project_id = ? ORDER BY position, team",
        (project_id,),
    ):
        entry = grouped.setdefault(row["team"], {"team": row["team"], "people": []})
        if row["person"]:
            entry["people"].append(row["person"])
    return list(grouped.values())


def _serialize(conn: sqlite3.Connection, row: sqlite3.Row, stages: dict[str, int] | None = None) -> dict:
    # 여러 과제를 한 번에 그릴 때는 단계를 미리 세어 넘긴다 (TODO 175)
    if stages is None:
        stages = svc.stage_map(conn)
    return {
        "id": row["id"],
        "title": row["title"],
        "status": row["status"],
        "type": row["type"],
        "group": row["grp"],
        "owners": _owners(conn, row["id"]),
        # 함께 일하는 팀과 그쪽 담당자 (TODO 92)
        "partners": _partners(conn, row["id"]),
        "start_date": row["start_date"],
        "due_date": row["due_date"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_reported_at": row["last_reported_at"],
        # 효과 금액 (억원/년). 실증효과는 과제가 끝나야 나오므로 대개 비어 있다.
        "effect_expected": row["effect_expected"],
        "effect_verified": row["effect_verified"],
        "completed_at": row["completed_at"],
        # 별도 보고가 필요 없는 과제 — 보고 대상 후보에서만 빠진다 (TODO 80).
        "no_report": bool(row["no_report"]),
        "no_effect": bool(row["no_effect"]),
        # 과제를 등록한 사람 (담당자와 다르다). 로그인이 생기면 자동으로 채워진다.
        "created_by": row["created_by"],
        # 과제 분류 넷 · 승격된 접수 번호 (TODO 136)
        **{key: row[key] for key in CLASSIFICATION_KEYS},
        "intake_id": row["intake_id"],
        # 선행 과제들 (TODO 172)
        "predecessors": svc._predecessors_of(conn, row["id"]),
        # 효과 금액을 세는 해 — 끝나는 해 (TODO 181). 목록(연도 거르기)에서만 온다.
        "effect_year": row["y_effect_year"] if "y_effect_year" in row.keys() else None,
        # 그 해의 상태 (TODO 184) — 목록(연도 거르기)에서만 온다. 2025~2026 과제를 2025 에서 보면 진행중.
        # 세고 거르는 곳(홈 · 대시보드 · [진행중] 거르기)이 모두 이것을 쓰므로 상태 칸도 이것을 보여야
        # 숫자를 눌러 나온 줄의 딱지가 그 숫자와 같다(DESIGN 5.8). `status` 는 **지금 상태** 그대로 둔다 —
        # 마감 경고 · 상세 화면 · 상태 바꾸기는 지금을 본다.
        "year_status": row["y_status"] if "y_status" in row.keys() else None,
        # 다년도 과제의 단계 — 이어진 과제가 없으면 null (TODO 175)
        "stage": stages.get(row["id"]),
        "tags": _tags(conn, row["id"]),
        "entry_count": conn.execute(
            "SELECT COUNT(*) AS n FROM entry WHERE project_id = ?", (row["id"],)
        ).fetchone()["n"],
    }


# 마감 기준 빠른 필터.
# 끝난 과제(완료·중단)는 빼 둔다 — 마감이 지났다고 경고할 이유가 없고,
# 무엇보다 대시보드가 세는 수와 이 필터가 거르는 수가 어긋나면 안 된다.
_NOT_FINISHED = f"p.status NOT IN ({','.join(repr(s) for s in FINISHED_STATUSES)})"
_UPCOMING = f"p.due_date IS NOT NULL AND p.due_date >= DATE('now', 'localtime') AND {_NOT_FINISHED}"
DUE_FILTERS = {
    "overdue": f"p.due_date IS NOT NULL AND p.due_date < DATE('now', 'localtime') AND {_NOT_FINISHED}",
    "7": f"{_UPCOMING} AND p.due_date <= DATE('now', 'localtime', '+7 day')",
    "14": f"{_UPCOMING} AND p.due_date <= DATE('now', 'localtime', '+14 day')",
    "30": f"{_UPCOMING} AND p.due_date <= DATE('now', 'localtime', '+30 day')",
}


@router.get("")
def list_projects(
    conn: sqlite3.Connection = Depends(get_db),
    status: str | None = None,
    type: str | None = None,
    group: str | None = None,
    tag: str | None = None,
    owner: str | None = None,
    partner: str | None = None,
    q: str | None = None,
    due: str | None = None,
    # 연도 — 수행기간이 그 해와 겹치는 과제 (TODO 181). 비우면 전체. 상태 · 효과 거르기도 **그 해 기준**이 된다.
    year: str | None = Query(None, pattern=r"^(\d{4})?$"),
    # 그 해에 새로 착수한 과제만 — 번호의 연도 (TODO 181). 홈의 "신규 N" 이 이리로 이어 준다.
    new: str | None = Query(None, pattern="^(1)?$"),
    # **완료일**의 연도 (TODO 104). 홈의 "올해 끝낸 과제" 가 이리로 이어 준다.
    done_year: str | None = Query(None, pattern=r"^(\d{4})?$"),
    # 완료했는데 실증효과를 안 적은 과제만 (TODO 106-C). "none" 하나만 받는다.
    verified: str | None = Query(None, pattern="^(none)?$"),
    # 효과 금액이 적힌 과제만 (TODO 124). 홈의 "기대 N건 · 실증 N건에 입력됨" 이 이리로 온다.
    effect: str | None = Query(None, pattern="^(expected|verified)?$"),
    # 효과성 관리 비대상만/빼고 (TODO 125). "none" 은 비대상만, "only" 는 대상만.
    no_effect: str | None = Query(None, pattern="^(none|only)?$"),
    # 떠난 담당자가 남아 있는 **끝나지 않은** 과제만 (TODO 122). 홈이 이리로 이어 준다.
    owner_left: str | None = Query(None, pattern="^(1)?$"),
    # 과제 분류 넷 (TODO 136). "none" 은 비어 있는 과제 — 홈의 '미지정' 줄이 쓴다.
    nature: str | None = None,
    category: str | None = None,
    delivery: str | None = None,
    cost_kind: str | None = None,
    # 접수에서 승격된 과제만("yes") / 직접 만든 과제만("no") (TODO 136)
    from_intake: str | None = Query(None, pattern="^(yes|no)?$"),
    sort: str = Query("updated"),
    # 열 머리글을 눌러 방향을 뒤집는다 (TODO 57). 정렬 키는 SORTS 가 정의한다.
    order: str | None = Query(None, pattern="^(asc|desc)$"),
) -> list[dict]:
    where, params = [], []
    # 그 해의 과제 · 그 해의 상태 · 그 해에 세는 효과 (TODO 181) — 홈 · 대시보드와 같은 모듈
    source, source_params = period_service.scope(year or None)
    if effect == "expected":
        # 홈의 분모(ee_n)와 **같은 조건**이어야 한다 — 세는 수와 거르는 수가 같아야 한다.
        where.append("COALESCE(p.y_ee, 0) > 0")
    elif effect == "verified":
        where.append("COALESCE(p.y_ev, 0) > 0")
    if no_effect == "none":
        where.append("p.no_effect = 1")  # 비대상만
    elif no_effect == "only":
        where.append("p.no_effect = 0")  # 관리 대상만
    if owner_left:
        names = [person["name"] for person in settings_service.left_people()]
        if not names:
            return []  # 떠난 사람이 없으면 조건에 맞는 과제도 없다
        marks = ",".join("?" for _ in names)
        unfinished = ",".join("?" for _ in FINISHED_STATUSES)
        where.append(
            f"p.status NOT IN ({unfinished})"
            f" AND p.id IN (SELECT po.project_id FROM project_owner po WHERE po.name IN ({marks}))"
        )
        params.extend(FINISHED_STATUSES)
        params.extend(names)
    for column, value in (("nature", nature), ("category", category),
                          ("delivery", delivery), ("cost_kind", cost_kind)):
        # 세는 곳(홈)과 거르는 곳(여기)이 같은 조건을 써야 한다 (DESIGN 5.8).
        if value == "none":
            where.append(f"(p.{column} IS NULL OR TRIM(p.{column}) = '')")
        elif value:
            where.append(f"TRIM(p.{column}) = ?")
            params.append(value)
    if from_intake == "yes":
        where.append("p.intake_id IS NOT NULL AND p.intake_id != ''")
    elif from_intake == "no":
        where.append("(p.intake_id IS NULL OR p.intake_id = '')")
    if status:
        where.append("p.y_status = ?")
        params.append(status)
    if type == "none":
        # 속성을 아직 안 정한 과제만. 대시보드의 '미지정' 칸이 이 값을 쓴다.
        where.append("(p.type IS NULL OR p.type = '')")
    elif type:
        where.append("p.type = ?")
        params.append(type)
    if partner:
        # 팀 이름으로도, 그쪽 담당자 이름으로도 걸린다 — 어느 쪽을 기억하고 있든 찾힌다.
        where.append(
            "p.id IN (SELECT pp.project_id FROM project_partner pp"
            "          WHERE pp.team = ? OR pp.person = ?)"
        )
        params.extend([partner, partner])
    if group == "none":
        # 그룹을 아직 안 정한 과제만. 홈의 그룹별 표 '미지정' 줄이 이 값을 쓴다 (TODO 90).
        # 세는 수와 거르는 수는 같아야 한다 (DESIGN 5.8).
        where.append("(p.grp IS NULL OR TRIM(p.grp) = '')")
    elif group:
        where.append("TRIM(p.grp) = ?")
        params.append(group)
    if tag:
        where.append(
            "p.id IN (SELECT pt.project_id FROM project_tag pt JOIN tag t ON t.id = pt.tag_id WHERE t.name = ?)"
        )
        params.append(tag)
    if owner == "none":
        # 담당자를 아직 안 정한 과제만. 대시보드의 '미지정' 칸이 이 값을 쓴다.
        where.append("NOT EXISTS (SELECT 1 FROM project_owner po WHERE po.project_id = p.id)")
    elif owner:
        where.append("p.id IN (SELECT po.project_id FROM project_owner po WHERE po.name = ?)")
        params.append(owner)
    if due in DUE_FILTERS:
        where.append(DUE_FILTERS[due])
    if year and new:
        where.append(year_clause())
        params.append(year)
    if done_year:
        where.append("p.status = 'done' AND SUBSTR(p.completed_at, 1, 4) = ?")
        params.append(done_year)
    if verified == "none":
        # 홈의 done_unverified 와 같은 조건 — 그 해에 끝낸 과제 중 실증 미입력 (181: 그 해의 상태)
        where.append("p.y_status = 'done' AND (p.effect_verified IS NULL OR p.effect_verified <= 0)")
    if q and q.strip():
        # 과제 본문뿐 아니라 진행일지·첨부 파일명에 걸려도 그 과제를 남긴다.
        matched = search_svc.project_ids_matching(conn, q.strip())
        if not matched:
            return []
        where.append(f"p.id IN ({','.join('?' * len(matched))})")
        params.extend(matched)

    clause = f"WHERE {' AND '.join(where)}" if where else ""
    order_params: list[str] = []
    if sort == "nature":
        clause_order, order_params = _nature_order()
    else:
        clause_order = SORTS.get(sort, SORTS["updated"])
    if order is not None:
        clause_order = _flip(clause_order, order)
    rows = conn.execute(
        f"SELECT p.* FROM {source} {clause} ORDER BY {clause_order}", [*source_params, *params, *order_params]
    ).fetchall()
    stages = svc.stage_map(conn)
    return [_serialize(conn, row, stages) for row in rows]


@router.post("", status_code=201)
def create_project(payload: ProjectCreate, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    try:
        project_id = svc.create_project(conn, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    row = conn.execute("SELECT * FROM project WHERE id = ?", (project_id,)).fetchone()
    return _serialize(conn, row)


@router.get("/next-id")
def next_id(start_date: str | None = Query(None)) -> dict:
    """이 시작일로 만들면 어떤 번호가 붙는지 (TODO 95).

    화면이 저장 전에 미리 보여 준다 — 번호의 연도가 **등록한 날이 아니라 착수년도**라는
    사실은 적어 두는 것보다 실제 번호를 보여 주는 편이 확실하다.
    `/{project_id}` 보다 **먼저** 서야 한다. 아니면 `next-id` 가 과제 번호로 잡힌다.
    """
    year = svc.project_year(start_date)
    return {"id": svc.next_project_id(year), "year": year}


@router.get("/{project_id}")
def get_project(project_id: str, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    row = conn.execute("SELECT * FROM project WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="과제를 찾을 수 없습니다.")
    data = _serialize(conn, row)
    data["body"] = row["body"]
    data["dir_name"] = row["dir_name"]
    # 개요가 서식 그대로인지 — 화면이 "아직 작성 전" 을 세운다 (TODO 106-B).
    data["overview_blank"] = svc.overview_is_blank(row["body"])
    # 마지막 진행일지의 계획 절 — 다음 할 일 (TODO 112). 표시만 한다.
    from ..services.entries import latest_plan

    data["next_plan"] = latest_plan(conn, project_id)
    # 상단 요약에 쓸 값 — 펼쳐 보지 않아도 상태를 알 수 있게 한다.
    from ..services.reports import unreported_entries

    data["unreported_entries"] = len(unreported_entries(conn, project_id))
    # 지난 보고에서 받고 아직 답하지 않은 지시 (TODO 107) — 상세 위쪽에 세운다.
    from ..services.reports import open_feedback

    data["open_feedback"] = [
        {"id": row["id"], "report_date": row["report_date"], "audience": row["audience"],
         "feedback": row["feedback"]}
        for row in open_feedback(conn, project_id)
    ]
    data["report_count"] = conn.execute(
        "SELECT COUNT(*) AS n FROM report WHERE project_id = ?", (project_id,)
    ).fetchone()["n"]
    files = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(size_bytes), 0) AS bytes FROM attachment WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    data["attachment_count"] = files["n"]
    data["attachment_bytes"] = files["bytes"]
    # 새 진행일지를 빈칸이 아니라 서식에서 시작하도록 함께 실어 보낸다.
    data["entry_template"] = settings_service.entry_template(row["type"])
    # 이 과제로 승격된 접수와, 이 과제에 병합된 접수 (TODO 136) — 과제 쪽의 역링크
    from ..services.intakes import related_to_project

    data["intakes"] = related_to_project(conn, project_id)
    # 다년도 과제의 줄기 — 앞 단계들 · 다음 단계 · 단계 번호 (TODO 172)
    data["lineage"] = svc.lineage(conn, project_id)
    return data


@router.patch("/{project_id}")
def update_project(
    project_id: str, payload: ProjectUpdate, conn: sqlite3.Connection = Depends(get_db)
) -> dict:
    try:
        svc.update_project(conn, project_id, payload.changes())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="과제를 찾을 수 없습니다.") from exc
    except ExternalChangeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileInUseError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return get_project(project_id, conn)


# ── 과제 번호의 연도를 착수년도에 맞추기 (TODO 95) ──────────────────────────
#
# **자동으로 바꾸지 않는다.** 번호는 이미 보고 자리에서 불린 이름이라, 시작일을 고쳤다고
# 소리 없이 따라 움직이면 그 편이 더 위험하다. 화면이 어긋난 사실을 알리고,
# 사용자가 눌렀을 때만 옮긴다. 미리보기와 실행을 나눈 것도 같은 이유다.

@router.get("/{project_id}/year-fix")
def year_fix_plan(project_id: str, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    try:
        return renumber_service.year_plan(conn, project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="과제를 찾을 수 없습니다.") from exc


@router.post("/{project_id}/year-fix")
def year_fix_apply(project_id: str, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    try:
        return renumber_service.year_apply(conn, project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="과제를 찾을 수 없습니다.") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileInUseError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc


@router.get("/{project_id}/clone")
def clone_draft(project_id: str, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """이 과제를 바탕으로 새 과제 (TODO 109) — **미리 채울 값만** 준다. 만들지 않는다 (TODO 173).

    화면이 이 값으로 새 과제 칸을 열고, [만들기] 가 `POST /api/projects` 를 부른다 — [취소] 하면
    아무것도 남지 않고 번호도 쓰지 않는다.
    """
    try:
        return svc.clone_draft(conn, project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="과제를 찾을 수 없습니다.") from exc


# ── 접수로 되돌리기 (TODO 171) ─────────────────────────────────────────────
# 접수를 거치지 않고 만든 과제를 풀로 — 미리보기와 실행을 나눈다(무엇이 어디로 가는지 먼저 보인다).

@router.get("/{project_id}/to-intake")
def to_intake_plan(project_id: str, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    from ..services import intakes as intakes_service

    try:
        return intakes_service.demote_plan(conn, project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="과제를 찾을 수 없습니다.") from exc


@router.post("/{project_id}/to-intake", status_code=201)
def to_intake(project_id: str, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    from ..services import intakes as intakes_service

    try:
        return {"intake_id": intakes_service.demote(conn, project_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="과제를 찾을 수 없습니다.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileInUseError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc


@router.post("/{project_id}/archive", status_code=204)
def archive_project(project_id: str, conn: sqlite3.Connection = Depends(get_db)) -> None:
    try:
        svc.archive_project(conn, project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="과제를 찾을 수 없습니다.") from exc
    except FileInUseError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc
