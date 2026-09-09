from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from ..config import ACTIVITY_KINDS, COLLAPSED_STATUSES, STATUSES, get_settings
from ..deps import get_db
from ..services import home as home_service
from ..services import settings as settings_service
from ..vault.indexer import reindex_all

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {"status": "ok", "vault": str(settings.vault_dir)}


@router.get("/meta")
def meta(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    groups = [
        row["grp"]
        for row in conn.execute(
            "SELECT DISTINCT grp FROM project WHERE grp IS NOT NULL AND grp <> '' ORDER BY grp"
        )
    ]
    # 태그는 **실제로 붙어 있는 것만** 준다 (TODO 96).
    #
    # `tag` 표는 한 번 쓴 이름을 지우지 않는다 — 오타로 한 번 친 태그도, 나중에 떼어 낸
    # 태그도 그대로 남는다. 그 표를 그냥 읽으면 거르기 상자에 **골라도 0건인 항목**이 선다.
    # 자동완성용(`tags`)은 과제·진행일지 어디든 붙어 있는 것, 과제 목록의 거르기 상자용
    # (`project_tags`)은 **과제에 붙어 있는 것**이다. 진행일지에만 있는 태그로 과제를
    # 거르면 늘 0건이라, 두 자리는 같은 목록일 수 없다.
    tags = [
        row["name"]
        for row in conn.execute(
            "SELECT DISTINCT t.name FROM tag t"
            " WHERE EXISTS (SELECT 1 FROM project_tag pt WHERE pt.tag_id = t.id)"
            "    OR EXISTS (SELECT 1 FROM entry_tag et WHERE et.tag_id = t.id)"
            " ORDER BY t.name"
        )
    ]
    project_tags = [
        row["name"]
        for row in conn.execute(
            "SELECT DISTINCT t.name FROM tag t"
            " JOIN project_tag pt ON pt.tag_id = t.id ORDER BY t.name"
        )
    ]
    owners = [
        row["name"]
        for row in conn.execute("SELECT DISTINCT name FROM project_owner ORDER BY name")
    ]
    # 유관부서 (TODO 92). 지금까지 적어 둔 팀·사람을 모아 자동완성과 거르기에 쓴다.
    partner_teams = [
        row["team"]
        for row in conn.execute(
            "SELECT DISTINCT team FROM project_partner WHERE team <> '' ORDER BY team"
        )
    ]
    partner_people = [
        row["person"]
        for row in conn.execute(
            "SELECT DISTINCT person FROM project_partner WHERE person <> '' ORDER BY person"
        )
    ]
    audiences = [
        row["audience"]
        for row in conn.execute(
            "SELECT DISTINCT audience FROM report WHERE audience IS NOT NULL AND audience <> ''"
            " ORDER BY audience"
        )
    ]
    return {
        "statuses": [
            {"key": key, "label": label, "candidate": candidate, "collapsed": key in COLLAPSED_STATUSES}
            for key, label, candidate in STATUSES
        ],
        # 과제 속성은 설정에서 더하고 빼고 고칠 수 있다 (TODO 100).
        "types": settings_service.project_types(),
        # 팀원 역량 이력의 구분 (TODO 72). 과제의 속성과 다른 축이다.
        "activity_kinds": [{"key": key, "label": label} for key, label in ACTIVITY_KINDS],
        "groups": groups,
        # 과제 중 **그룹을 안 적은 것**이 있으면 [미지정] 으로 고를 수 있어야 한다.
        # 홈의 그룹별 표가 이미 그 줄을 세우고 `group=none` 으로 이어 준다 (TODO 90).
        "groups_none": conn.execute(
            "SELECT COUNT(*) AS n FROM project WHERE grp IS NULL OR TRIM(grp) = ''"
        ).fetchone()["n"] > 0,
        "tags": tags,
        # 과제 목록의 태그 거르기 상자용 — 과제에 실제로 붙어 있는 태그만.
        "project_tags": project_tags,
        # 과제가 실제로 있는 해. 거르기 상자는 이것만 세운다 — 없는 해를 고르면 0건이다.
        "years": home_service.years(conn),
        "owners": owners,
        # 유관부서 — 팀과 그쪽 담당자를 나눠 준다. 거르기는 둘 중 어느 쪽으로도 된다.
        "partner_teams": partner_teams,
        "partner_people": partner_people,
        "audiences": audiences,
        # 담당자 명부 — 자동완성이 이것을 먼저 쓰고, 없는 이름이면 화면에서 물어본다.
        "people": settings_service.known_names(),
        "project_code": settings_service.project_code(),
        "vault": str(get_settings().vault_dir),
        "report_cycle_days": get_settings().report_cycle_days,
        # 주간 보고 요일 (0=월 … 6=일). 화면이 안내 문구에 쓴다.
        "report_weekday": settings_service.report_weekday(),
    }


@router.post("/reindex")
def reindex(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    indexed, problems = reindex_all(conn)
    return {
        "indexed": indexed,
        # 읽지 못한 파일은 조용히 넘기지 않고 화면에 알린다.
        "problems": [{"path": item.rel_path, "reason": item.reason} for item in problems],
    }
