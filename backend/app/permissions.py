"""팀원이 쓸 수 있는 것 — 한 곳에서 (TODO 233).

사용자 결정(2026-11-03):

* 팀원은 **본인이 담당인 과제**만 고친다 — 그중 **진행일지 · 첨부 · 과제 개요 본문** 만(②).
  상태 · 일정 · 효과 금액 · 담당자 · 속성 · 분류 · 그룹 · 번호 · 보관 · 지우기 · 보고는 팀장만(④).
* 같은 과제라도 **남이 쓴 진행일지는 보기만**(③) — 고치고 지우는 것은 본인이 쓴 것만.
* 본인 면담은 **보기만**(⑤ — 고치는 것은 팀장), 팀원역량 기록도 보기만(⑦).

규칙은 **허용 목록**이다 — 여기 없는 쓰기는 모두 403. 끝점이 늘어도 팀원에게 저절로 열리지 않는다.
담당인지 · 본인이 썼는지는 **서버가 색인에서** 본다(화면이 보낸 값을 믿지 않는다).
과제 개요 PATCH 의 "본문만" 은 몸통을 읽어야 알 수 있어 `api/projects.py` 가 한 번 더 본다(`member_fields_ok`).
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from urllib.parse import unquote

from .who import MEMBER, User

DENIED = "담당 과제의 진행일지 · 첨부 · 개요 · 자기 역할과 회고만 고칠 수 있습니다."
NOT_YOURS = "남이 쓴 진행일지는 고치거나 지울 수 없습니다 — 쓴 사람이나 팀장에게 말해 주세요."
NOT_OWNER = "담당 과제만 고칠 수 있습니다 — 이 과제의 담당자가 아닙니다."
NOT_YOUR_ROW = "자기 줄만 고칠 수 있습니다 — 다른 사람의 역할 · 회고는 그 사람이나 팀장이 고칩니다."
NOT_YOUR_EXPERIENCE = "자기 경험만 고칠 수 있습니다."
CONFIRMED_LOCKED = "확정한 경험은 팀장만 고칩니다 — 고칠 곳이 있으면 팀장에게 [구조화로 되돌림]을 부탁하세요."
PROJECT_FIELDS_DENIED = "팀원은 과제 개요 본문만 고칠 수 있습니다 — 상태 · 일정 · 효과 · 담당자 같은 칸은 팀장이 고칩니다."

# 팀원이 PATCH /api/projects/{id} 로 보낼 수 있는 칸
MEMBER_PROJECT_FIELDS = frozenset({"body", "base_updated_at"})

# (방법, 경로, 이름) — 이름은 쓰기 기록(edits)과 홈 "팀원이 고친 것" 의 말이 된다
_RULES: list[tuple[str, re.Pattern[str], str]] = [
    ("POST", re.compile(r"^/api/projects/(?P<project>[^/]+)/entries$"), "진행일지 추가"),
    ("PATCH", re.compile(r"^/api/entries/(?P<entry>\d+)$"), "진행일지 수정"),
    ("DELETE", re.compile(r"^/api/entries/(?P<entry>\d+)$"), "진행일지 삭제"),
    ("POST", re.compile(r"^/api/entries/(?P<entry>\d+)/attachments$"), "첨부 추가"),
    ("POST", re.compile(r"^/api/projects/(?P<project>[^/]+)/attachments$"), "첨부 추가"),
    ("DELETE", re.compile(r"^/api/attachments/(?P<attachment>\d+)$"), "첨부 삭제"),
    ("PATCH", re.compile(r"^/api/projects/(?P<project>[^/]+)$"), "개요 수정"),
    # 담당과 역할 · 회고 (TODO 237) — 자기 줄만(`person` 이 자기 이름)
    ("PUT", re.compile(r"^/api/projects/(?P<project>[^/]+)/contributions/(?P<person>[^/]+)$"), "역할 · 회고 수정"),
    # 팀원 보완 (TODO 262 · 5단계.md ⑦) — 자기 경험, 초안 · 구조화만. 업무 이력 파일 내보내기 기록(자기 것은 끝점이 본다)
    ("PATCH", re.compile(r"^/api/experiences/(?P<experience>E-\d{3,})$"), "경험 보완"),
    ("POST", re.compile(r"^/api/experiences/export/log$"), "업무 이력 파일 내보내기"),
]
# 쓰다 만 글 — 사람마다 따로 둔다(drafts 가 사람 폴더로 나눈다). 쓰기 기록에는 남기지 않는다
_DRAFTS = re.compile(r"^/api/drafts(/[^/]+)?$")


@dataclass
class Decision:
    allowed: bool
    reason: str = ""
    action: str = ""
    project_id: str | None = None
    entry_id: int | None = None
    record: bool = True  # 쓰기 기록에 남길 것인가


def owns(conn: sqlite3.Connection, project_id: str, name: str) -> bool:
    row = conn.execute("SELECT 1 FROM project_owner WHERE project_id = ? AND name = ?", (project_id, name)).fetchone()
    return row is not None


def member_projects(conn: sqlite3.Connection, name: str) -> list[str]:
    """이 사람이 담당인 과제 번호 — 화면이 [수정] 단추를 세울 곳(`/api/me`)."""
    return [row["project_id"] for row in conn.execute(
        "SELECT po.project_id FROM project_owner po JOIN project p ON p.id = po.project_id"
        " WHERE po.name = ? ORDER BY po.project_id", (name,))]


def check(conn: sqlite3.Connection, user: User, method: str, path: str) -> Decision:
    """팀원의 쓰기 하나를 판정한다. 팀장 · 읽기는 여기 오지 않는다(미들웨어가 가른다)."""
    if user.role != MEMBER:
        return Decision(False, DENIED)
    if _DRAFTS.match(path):
        return Decision(True, record=False)
    for rule_method, pattern, action in _RULES:
        if method != rule_method:
            continue
        found = pattern.match(path)
        if not found:
            continue
        groups = found.groupdict()
        if "project" in groups:
            project_id = unquote(groups["project"])
            if not owns(conn, project_id, user.name):
                return Decision(False, NOT_OWNER)
            if "person" in groups and unquote(groups["person"]).strip() != user.name:
                return Decision(False, NOT_YOUR_ROW)
            return Decision(True, action=action, project_id=project_id)
        if "entry" in groups:
            entry_id = int(groups["entry"])
            row = conn.execute("SELECT project_id, author FROM entry WHERE id = ?", (entry_id,)).fetchone()
            if row is None:
                return Decision(True, action=action, entry_id=entry_id)  # 없으면 끝점이 404 로 답한다
            if not owns(conn, row["project_id"], user.name):
                return Decision(False, NOT_OWNER)
            if (row["author"] or "") != user.name:
                return Decision(False, NOT_YOURS)
            return Decision(True, action=action, project_id=row["project_id"], entry_id=entry_id)
        if "experience" in groups:
            row = conn.execute("SELECT person, status FROM experience WHERE id = ?", (groups["experience"],)).fetchone()
            if row is None:
                return Decision(True, action=action)            # 없으면 끝점이 404
            if row["person"] != user.name:
                return Decision(False, NOT_YOUR_EXPERIENCE)
            if row["status"] == "확정":
                return Decision(False, CONFIRMED_LOCKED)
            return Decision(True, action=action)
        if not groups:
            return Decision(True, action=action, record=False)  # 끝점이 자기 것인지 본다
        if "attachment" in groups:
            row = conn.execute(
                "SELECT a.project_id, a.entry_id, e.author FROM attachment a LEFT JOIN entry e ON e.id = a.entry_id WHERE a.id = ?",
                (int(groups["attachment"]),),
            ).fetchone()
            if row is None:
                return Decision(True, action=action)
            if not owns(conn, row["project_id"], user.name):
                return Decision(False, NOT_OWNER)
            if row["entry_id"] is not None and (row["author"] or "") != user.name:
                return Decision(False, NOT_YOURS)
            return Decision(True, action=action, project_id=row["project_id"], entry_id=row["entry_id"])
    return Decision(False, DENIED)


def action_of(method: str, path: str) -> tuple[str, str | None, int | None] | None:
    """허용 목록의 이름만 — 팀장의 쓰기를 쓰기 기록에 남길 때 (권한은 따지지 않는다)."""
    for rule_method, pattern, action in _RULES:
        found = pattern.match(path) if method == rule_method else None
        if found:
            groups = found.groupdict()
            project = unquote(groups["project"]) if groups.get("project") else None
            entry = int(groups["entry"]) if groups.get("entry") else None
            return action, project, entry
    return None


def member_fields_ok(changes: dict) -> bool:
    return set(changes) <= MEMBER_PROJECT_FIELDS


# ── 관리자(서버 PC)만 — 서버 운영 (TODO 247) ───────────────────────────────
# 팀장 PC(명부의 팀장 IP)는 팀을 맡은 일은 모두 하지만, 서버를 다루는 일은 서버 PC 에 남긴다 — 데이터 통째로 바꾸기 ·
# 서버 폴더 훑기 · 자동 백업 폴더, 그리고 **팀장 지정 · 팀장 PC 주소**(팀장 PC 에서 바꾸면 스스로 잠기거나 다른 PC 를 팀장으로 만든다).
ADMIN_ONLY_DETAIL = ("서버 PC(관리자)에서만 할 수 있습니다 — 데이터 위치 · 자동 백업 폴더 · 백업에서 되살리기 · "
                     "팀장 지정과 팀장 PC 주소는 서버를 맡은 쪽의 일입니다.")
ADMIN_ONLY_PREFIXES = ("/api/backup/restore", "/api/folders")
ADMIN_SETTINGS_KEYS = frozenset({"backup_dir", "backup_keep", "backup_keep_weekly", "backup_keep_monthly",
                                 "backup_every_hours", "backup_skip_assets"})


def admin_only(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix + "/") for prefix in ADMIN_ONLY_PREFIXES)


def settings_change_denied(changes: dict, stored: dict) -> bool:
    """팀장이 보낸 설정 저장에 **바뀐** 자동 백업 칸이 있나. 화면이 그대로 실어 보낸 같은 값은 괜찮다."""
    return any(key in changes and changes[key] != stored.get(key) for key in ADMIN_SETTINGS_KEYS)


def leader_signature(people: list[dict]) -> tuple | None:
    """명부의 팀장 줄 — 이름 · PC 주소 · 떠난 날. 팀장 PC 에서 저장한 명부는 이것이 그대로여야 한다 (TODO 247)."""
    from .who import normalize_ip

    for person in people:
        if not person.get("leader"):
            continue
        ips = []
        for raw in person.get("ips") or []:
            try:
                ips.append(normalize_ip(raw))
            except ValueError:
                ips.append(str(raw))
        return (str(person.get("name") or "").strip(), tuple(sorted(ips)), str(person.get("left_on") or "").strip())
    return None
