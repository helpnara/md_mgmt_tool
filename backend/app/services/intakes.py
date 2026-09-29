"""과제 접수 풀 (TODO 136).

팀의 업무는 **접수 → 검토 → 수행** 인데 도구는 수행부터 다루고 있었다. 앞의 두 단계 —
현업이 보낸 과제정의서를 받아 인터뷰로 다듬고, 할지 말지 정하는 일 — 는 메일함과 개인
폴더에 있었고, 반년 뒤 "그 요청 왜 안 했더라" 에 답할 근거가 남지 않았다.

**접수 건은 과제가 아니다.** 과제로 넣으면 반려될 건이 과제 번호를 먹고, 홈의 과제 수와
효과 합계에 검토도 안 한 건이 섞인다. 그래서 따로 둔다 — `vault/intakes/` 아래 요청 하나가
폴더 하나이고, 번호도 따로 간다(`R2026-소재-001`). 착수가 정해지면 **승격**해서 과제를 만든다.

    intakes/R2026-소재-001-압연-온도편차/
    ├── request.md    요청 내용 + 판정 (front matter)
    ├── logs/         인터뷰·검토 기록 — 진행일지와 같은 모양
    └── assets/       과제정의서.pptx 같은 원본 (assets/<날짜>/NNN-이름)

첨부는 과제와 **같은 경로 규칙**(`assets/<날짜>/NNN-이름`)으로 둔다. 승격할 때 assets 를
통째로 과제 폴더로 복사하면, 본문에 있던 링크가 한 글자도 안 바뀌고 그대로 살아난다.

**풀은 상태가 아니라 화면이다.** 아직 판정이 나지 않았거나 보류된 것(`INTAKE_POOL_STATUSES`)을
모아 보는 자리일 뿐이다.

**풀에 있을 때만 고친다.** 판정이 난 접수(착수·반려·이관·병합)는 그때의 기록으로 굳는다.
반려·이관·병합은 다시 풀로 되돌릴 수 있고(재검토), 착수는 되돌리지 않는다 — 과제가 이미 있다.
"""
from __future__ import annotations

import os
import re
import shutil
import sqlite3
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO

from ..config import (
    CLASSIFICATION_KEYS,
    CLASSIFIED_TYPE,
    INTAKE_POOL_STATUSES,
    INTAKE_PRIORITIES,
    INTAKE_STATUS_KEYS,
    INTAKE_STATUS_LABELS,
    get_settings,
)
from ..vault import markdown as md
from ..vault import versions
from ..vault import paths
from . import settings as settings_service
from . import trash as trash_service

# 접수 본문 서식. **섹션 제목을 과제 개요에 맞춰 두었다** — 괄호·줄표 앞의 이름이 같으면
# 승격할 때 그 자리로 그대로 넘어간다. 현업에게 보이는 이름은 괄호 안에서 친절하게 쓴다.
DEFAULT_TEMPLATE = """## 배경 (과제배경)

> 왜 이 과제가 필요한지 — 현재 문제 상황, 요청 배경

## 목표 (성과지표)

| KPI 항목 | 정의(계산식) | 현수준 | 목표 | 기대효과(억원/년) | 비용구분 |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

## 효과 산출 근거

> 기대효과 금액이 어떤 계산에서 나왔는지 — 단가 × 물량 × 개선율, 가정, 출처

## 추진내용

> 과제 범위 · 적용 대상 · 단계별 추진계획/일정 · 유관부서 협의 여부

## 활용 방안 및 향후 계획

> 결과를 어디에 어떻게 쓰는지, 끝난 뒤 이어질 일
"""

META_ORDER = [
    "id", "title", "status",
    # 과제리더와 소속. 명부에 있는 사람이면 승격할 때 담당자로, 없으면(현업) 유관부서로 간다.
    "leader", "leader_team",
    *CLASSIFICATION_KEYS,
    # 추진 기간 — 승격할 때 과제의 시작일·마감일 초기값이 된다
    "start_date", "due_date",
    # 요청자가 적은 기대효과(억원/년). **과제로 옮기지 않는다** — 승격 화면에 참고로만 보인다.
    "effect_request",
    "priority", "priority_note",
    # 풀에서 골라 둔 착수 후보 (연초·분기 계획용). 파일에 남겨야 계획 자료가 된다.
    "picked",
    "received_on", "decided_on", "decision_note",
    # 착수하면 과제 번호, 병합하면 흡수한 과제 번호
    "project_id", "merged_into",
    # 과제를 지워 착수·병합이 풀렸을 때 그 과제 번호와 관계(started/merged) — 보관함에서 과제를
    # 되돌리면 이 접수가 아직 풀에 있을 때 다시 잇는 근거다 (TODO 145)
    "detached_from", "detached_as",
    "tags", "created_by", "created_at", "updated_at",
]

REQUEST_FILE = "request.md"
# 상태 변경 줄의 태그 — 과제의 상태 변경 기록(105)과 같은 태그라 화면이 똑같이 흐리게 세운다.
STATUS_CHANGE_TAG = "상태변경"
# 판정할 때 사유를 꼭 적어야 하는 것. 반려 사유가 없으면 반년 뒤 같은 요청에 답할 수 없다.
NOTE_REQUIRED = ("rejected", "transferred", "on_hold")
_LOG_NAME = re.compile(r"^[^/\\]+\.md$")


class IntakeClosedError(ValueError):
    """판정이 난 접수를 고치려 할 때. 화면에 그대로 보여 준다."""


# ── 번호 · 폴더 ─────────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def today() -> str:
    return date_cls.today().isoformat()


def intake_year(received_on: str | None) -> int:
    text = (received_on or "").strip()
    if len(text) >= 4 and text[:4].isdigit() and 1900 <= int(text[:4]) <= 2999:
        return int(text[:4])
    return date_cls.today().year


def next_intake_id(year: int | None = None, code: str | None = None) -> str:
    """다음 접수 번호. 과제 번호와 **같은 팀 코드**(설정 한 곳)를 쓴다.

    `R2026-소재-001` — 팀 코드를 비워 두면 `R2026-001`. 일련번호는 연도·코드별로 따로 센다.
    반려돼도 번호는 그대로 남는다 — 비는 번호가 생기는 것은 접수 쪽이지 과제 쪽이 아니다.
    """
    settings = get_settings()
    settings.ensure_dirs()
    year = year or date_cls.today().year
    if code is None:
        code = settings_service.project_code()
    prefix = f"R{year}-{code}-" if code else f"R{year}-"
    # 지운 접수의 번호도 다시 쓰지 않는다 (TODO 146 — 과제 번호와 같은 규칙)
    from .projects import max_sequence

    names = [child.name for child in settings.intakes_dir.iterdir() if child.is_dir()]
    names += list(trash_service.used_folder_names("intakes"))
    return f"{prefix}{max_sequence(names, prefix) + 1:03d}"


def intake_id_from_dir_name(dir_name: str) -> str:
    """`R2026-소재-001-제목` → `R2026-소재-001`. front matter 를 못 읽을 때만 쓴다."""
    parts = dir_name.split("-")
    for index in range(1, len(parts)):
        if parts[index].isdigit():
            return "-".join(parts[: index + 1])
    return dir_name


def intake_dir(conn: sqlite3.Connection, intake_id: str) -> Path:
    row = conn.execute("SELECT dir_name FROM intake WHERE id = ?", (intake_id,)).fetchone()
    if row is None:
        raise KeyError(intake_id)
    return paths.safe_join(get_settings().intakes_dir, row["dir_name"])


def _row(conn: sqlite3.Connection, intake_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM intake WHERE id = ?", (intake_id,)).fetchone()
    if row is None:
        raise KeyError(intake_id)
    return row


def _ensure_open(row: sqlite3.Row) -> None:
    if row["status"] not in INTAKE_POOL_STATUSES:
        label = INTAKE_STATUS_LABELS.get(row["status"], row["status"])
        raise IntakeClosedError(
            f"'{label}' 으로 판정이 난 접수는 그때의 기록으로 굳어 있습니다. "
            "고치려면 먼저 [재검토]로 풀에 되돌려 주세요."
        )


# ── 값 다듬기 ───────────────────────────────────────────────────────────────

def _text(value: object, limit: int = 200) -> str | None:
    text = " ".join(str(value or "").split())
    return text[:limit] or None


def _day(value: object) -> str | None:
    text = str(value or "").strip()
    return paths.validate_date(text, text) if text else None


def _effect(value: object) -> float | None:
    from .projects import normalize_effect

    return normalize_effect(value)


def _priority(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text not in INTAKE_PRIORITIES:
        raise ValueError(f"중요도는 {' · '.join(INTAKE_PRIORITIES)} 중 하나입니다.")
    return text


def _tags(value: object) -> list[str]:
    if not value:
        return []
    items = value.split(",") if isinstance(value, str) else [str(v) for v in value]
    out: list[str] = []
    for item in (" ".join(str(i).split()) for i in items):
        if item and item not in out:
            out.append(item)
    return out


def _clean_fields(data: dict[str, Any]) -> dict[str, Any]:
    """화면에서 온 값을 파일에 적을 모양으로. 보낸 칸만 돌려준다."""
    from .projects import normalize_label

    out: dict[str, Any] = {}
    if "title" in data:
        title = _text(data.get("title"))
        if not title:
            raise ValueError("과제명을 입력하세요.")
        out["title"] = title
    for key in ("leader", "leader_team", "priority_note"):
        if key in data:
            out[key] = _text(data.get(key))
    for key in CLASSIFICATION_KEYS:
        if key in data:
            out[key] = normalize_label(data.get(key))
    for key in ("start_date", "due_date", "received_on"):
        if key in data:
            out[key] = _day(data.get(key))
    if "effect_request" in data:
        out["effect_request"] = _effect(data.get("effect_request"))
    if "priority" in data:
        out["priority"] = _priority(data.get("priority"))
    if "picked" in data:
        out["picked"] = bool(data.get("picked"))
    if "tags" in data:
        out["tags"] = _tags(data.get("tags"))
    return out


# ── 만들기 · 고치기 ─────────────────────────────────────────────────────────

def create_intake(conn: sqlite3.Connection, data: dict[str, Any]) -> str:
    settings = get_settings()
    settings.ensure_dirs()
    fields = _clean_fields({"title": data.get("title"), **data})
    received_on = fields.get("received_on") or today()
    intake_id = next_intake_id(intake_year(received_on))
    directory = paths.safe_join(settings.intakes_dir, paths.project_dir_name(intake_id, fields["title"]))
    (directory / "logs").mkdir(parents=True, exist_ok=True)
    (directory / "assets").mkdir(parents=True, exist_ok=True)

    stamp = now_iso()
    meta: dict[str, Any] = {key: None for key in META_ORDER}
    meta.update(fields)
    meta.update({
        "id": intake_id,
        "status": "received",
        "received_on": received_on,
        "picked": bool(fields.get("picked")),
        "tags": fields.get("tags") or [],
        "created_by": settings_service.current_author(data.get("created_by")) or None,
        "created_at": stamp,
        "updated_at": stamp,
    })
    body = data.get("body")
    body = body if isinstance(body, str) and body.strip() else settings_service.intake_template()
    md.save(directory / REQUEST_FILE, md.MarkdownDoc(_ordered(meta), body))
    index_intake(conn, directory)
    conn.commit()
    return intake_id


def _ordered(meta: dict[str, Any]) -> dict[str, Any]:
    """META_ORDER 순서로 적는다. 모르는 열쇠(손으로 적은 메모)는 뒤에 그대로 둔다."""
    out = {key: meta.get(key) for key in META_ORDER if key in meta}
    out.update({key: value for key, value in meta.items() if key not in out})
    return out


def update_intake(conn: sqlite3.Connection, intake_id: str, updates: dict[str, Any]) -> None:
    row = _row(conn, intake_id)
    directory = intake_dir(conn, intake_id)
    request = directory / REQUEST_FILE
    # 풀 안에서 옮기는 것(접수 ↔ 검토중)과 후보 표시는 굳은 뒤에도 막지 않을 이유가 없지만,
    # 규칙은 단순한 편이 낫다 — 굳은 접수는 [재검토] 로만 연다.
    _ensure_open(row)
    md.ensure_unchanged(request, row["file_mtime"])
    doc = md.load(request)
    body = updates.pop("body", None)
    changes = _clean_fields(updates)
    meta = md.merge_meta(doc.meta, changes)
    meta["updated_at"] = now_iso()
    md.save(request, md.MarkdownDoc(_ordered(meta), body if body is not None else doc.body))
    directory = _rename_to_title(directory, intake_id, str(meta.get("title") or row["title"]))
    index_intake(conn, directory)
    conn.commit()


def _rename_to_title(directory: Path, intake_id: str, title: str) -> Path:
    """제목을 고치면 폴더 이름도 따라간다 — 탐색기에서 보는 이름과 화면의 이름이 갈라지지 않게."""
    expected = paths.project_dir_name(intake_id, title)
    if expected == directory.name:
        return directory
    root = get_settings().intakes_dir
    target = paths.safe_join(root, expected)
    if target.exists():
        target = paths.unique_path(root, expected, "")
    paths.move(directory, target)
    versions.follow(directory, target)  # 이전 버전도 따라온다 (TODO 142)
    return target


def set_status(
    conn: sqlite3.Connection,
    intake_id: str,
    status: str,
    note: str | None = None,
    merged_into: str | None = None,
) -> None:
    """판정과 풀 안의 이동. 착수는 여기가 아니라 `promote` 로만 간다(과제가 함께 생긴다).

    **판정은 기록이지 결재가 아니다** (향후계획 7절). 회의에서 정한 것을 적을 뿐이다.
    """
    if status not in INTAKE_STATUS_KEYS:
        raise ValueError(f"알 수 없는 상태: {status}")
    if status == "started":
        raise ValueError("착수는 [착수 · 과제로 승격] 으로만 할 수 있습니다.")
    row = _row(conn, intake_id)
    old = row["status"]
    if old == "started":
        raise IntakeClosedError("이미 과제로 승격된 접수는 상태를 바꿀 수 없습니다.")
    if old == status:
        return
    note = (note or "").strip() or None
    if status in NOTE_REQUIRED and not note:
        raise ValueError(f"{INTAKE_STATUS_LABELS[status]} 사유를 적어 주세요 — 나중에 되짚을 근거가 됩니다.")
    # 판정 칸은 **지금의 판정**만 담는다. 지난 판정(보류 사유·반려 사유)은 검토 기록 줄에 남는다.
    changes: dict[str, Any] = {"status": status, "merged_into": None}
    if status in ("received", "reviewing"):
        changes.update({"decided_on": None, "decision_note": None})
    else:
        changes.update({"decided_on": today(), "decision_note": note})
    if status == "merged":
        target = (merged_into or "").strip()
        if not target or conn.execute("SELECT 1 FROM project WHERE id = ?", (target,)).fetchone() is None:
            raise ValueError("병합할 과제 번호를 골라 주세요.")
        changes["merged_into"] = target

    directory = intake_dir(conn, intake_id)
    request = directory / REQUEST_FILE
    md.ensure_unchanged(request, row["file_mtime"])
    doc = md.load(request)
    meta = md.merge_meta(doc.meta, changes)
    meta["updated_at"] = now_iso()
    md.save(request, md.MarkdownDoc(_ordered(meta), doc.body))
    extra = f"\n\n사유: {note}\n" if note else "\n"
    if status == "merged":
        extra = f"\n\n흡수한 과제: {changes['merged_into']}" + (f"\n\n사유: {note}\n" if note else "\n")
    _log_status_change(directory, old, status, extra)
    index_intake(conn, directory)
    conn.commit()


def _log_status_change(directory: Path, old: str, new: str, extra: str = "\n") -> None:
    """판정·상태 이동을 검토 기록에 한 줄 (과제의 상태 변경 기록 · TODO 105 와 같은 모양).

    **실패해도 판정 자체를 막지 않는다.** 이력을 남기려다 본 작업이 막히면 본말이 뒤바뀐다.
    """
    from .entries import entry_stem

    try:
        logs_dir = directory / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        day = today()
        title = f"(상태) {INTAKE_STATUS_LABELS.get(old, old)} → {INTAKE_STATUS_LABELS.get(new, new)}"
        target = paths.unique_path(logs_dir, entry_stem(day, title), ".md")
        stamp = now_iso()
        meta = {
            "date": day,
            "title": title,
            "author": settings_service.current_author(None) or None,
            "tags": [STATUS_CHANGE_TAG],
            "created_at": stamp,
            "updated_at": stamp,
        }
        body = (
            f"상태를 **{INTAKE_STATUS_LABELS.get(old, old)}** 에서 "
            f"**{INTAKE_STATUS_LABELS.get(new, new)}** 로 바꿨다.{extra}"
        )
        md.save(target, md.MarkdownDoc(meta, body))
    except OSError:
        pass


def archive_intake(conn: sqlite3.Connection, intake_id: str) -> None:
    """잘못 만든 접수를 보관함으로. **판정으로 닫는 것과 다르다** — 반려는 지우지 않고 남긴다.

    승격된 접수는 지우지 않는다. 과제가 그 접수를 가리키고 있다.
    """
    row = _row(conn, intake_id)
    if row["status"] == "started":
        raise IntakeClosedError("과제로 승격된 접수는 지울 수 없습니다 — 과제가 이 접수를 가리키고 있습니다.")
    settings = get_settings()
    directory = intake_dir(conn, intake_id)
    settings.trash_dir.mkdir(parents=True, exist_ok=True)
    target = paths.unique_path(settings.trash_dir, f"{directory.name}-{datetime.now():%Y%m%d%H%M%S}", "")
    paths.move(directory, target)
    trash_service.record(
        "intake", label=f"{intake_id} {row['title']}", moved_to=target, origin=directory, project_id=None
    )
    conn.execute("DELETE FROM intake WHERE id = ?", (intake_id,))
    conn.commit()


# ── 과제를 지우고 되돌릴 때 (TODO 145) ──────────────────────────────────────
#
# 원칙 — 접수 하나에 착수 과제는 **하나**이고, 누구와 이어졌는지는 **접수 쪽이 정답**이다
# (접수의 project_id). 과제의 intake_id 는 되짚어 가는 표지일 뿐이라 둘이 어긋나면 접수를 따른다.

def detach_from_project(conn: sqlite3.Connection, project_id: str, project_title: str) -> list[str]:
    """과제를 지우면 그 과제로 착수·병합된 접수를 **묻지 않고 풀로** 되돌린다 (사용자 결정).

    판정 칸은 비우고, 흔적은 검토 기록의 `상태변경` 줄 하나로 남긴다. 어느 과제에서 풀렸는지는
    `detached_from` 에 적어 둔다 — 보관함에서 과제를 되돌릴 때 다시 잇는 근거다.
    """
    rows = conn.execute(
        "SELECT id, status FROM intake WHERE (status = 'started' AND project_id = ?)"
        " OR (status = 'merged' AND merged_into = ?)",
        (project_id, project_id),
    ).fetchall()
    moved: list[str] = []
    for row in rows:
        directory = intake_dir(conn, row["id"])
        request = directory / REQUEST_FILE
        doc = md.load(request)
        relation = "started" if row["status"] == "started" else "merged"
        meta = md.merge_meta(doc.meta, {
            "status": "reviewing", "project_id": None, "merged_into": None,
            "decided_on": None, "decision_note": None,
            "detached_from": project_id, "detached_as": relation,
        })
        meta["updated_at"] = now_iso()
        md.save(request, md.MarkdownDoc(_ordered(meta), doc.body))
        what = "착수" if relation == "started" else "병합"
        _log_status_change(
            directory, row["status"], "reviewing",
            f"\n\n과제 **{project_id}** ({project_title}) 을(를) 지워 {what}을(를) 되돌렸다. 과제는 삭제 보관함에 있고, "
            "거기서 되돌리면 이 접수가 아직 풀에 있을 때 다시 이어진다.\n",
        )
        index_intake(conn, directory)
        moved.append(row["id"])
    return moved


def detach_orphans(conn: sqlite3.Connection) -> list[str]:
    """이 규칙이 생기기 전에 과제를 지워 **이미 미아가 된** 접수를 풀로 (TODO 145).

    가리키는 과제가 없고 **그 과제가 삭제 보관함에 있을 때만** — 폴더를 손으로 잠시 옮겨 둔 것까지
    풀로 돌리면 안 된다. 새로 지우는 과제와 같은 규칙(`detach_from_project`)을 쓴다.
    """
    trashed = trash_service.trashed_projects()
    if not trashed:
        return []
    live = {row["id"] for row in conn.execute("SELECT id FROM project")}
    orphans = {
        row["target"]
        for row in conn.execute(
            "SELECT CASE WHEN status = 'started' THEN project_id ELSE merged_into END AS target FROM intake"
            " WHERE status IN ('started', 'merged')"
        )
        if row["target"] and row["target"] not in live and row["target"] in trashed
    }
    moved: list[str] = []
    for project_id in sorted(orphans):
        label = trashed[project_id]
        title = label.split(" ", 1)[1] if label.startswith(project_id + " ") else label
        moved += detach_from_project(conn, project_id, title)
    return moved


def reattach_project(conn: sqlite3.Connection, project_id: str) -> dict[str, list[str]]:
    """보관함에서 과제를 되돌린 뒤 — 접수가 **아직 풀에 있을 때만** 다시 잇는다 (TODO 145).

    그 사이 다른 과제로 착수됐거나(다시 승격) 반려·이관·병합됐으면 잇지 않고, 과제 쪽의 접수 표지
    (`intake_id`)를 뗀다 — 접수 하나에 착수 과제가 둘이 되면 안 된다. 되돌리기 자체는 막지 않는다.
    양쪽에 한 줄씩 남긴다.
    """
    from . import projects as projects_service

    project = conn.execute("SELECT title, intake_id FROM project WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        return {"relinked": [], "detached": []}
    relinked: list[str] = []
    for row in conn.execute("SELECT id, status, project_id, merged_into FROM intake").fetchall():
        directory = intake_dir(conn, row["id"])
        request = directory / REQUEST_FILE
        doc = md.load(request)
        if str(doc.meta.get("detached_from") or "") != project_id:
            continue
        relation = str(doc.meta.get("detached_as") or "started")
        clear = {"detached_from": None, "detached_as": None}
        if row["status"] in INTAKE_POOL_STATUSES:
            changes = {**clear, "decided_on": today()}
            if relation == "merged":
                changes.update({"status": "merged", "merged_into": project_id})
            else:
                changes.update({"status": "started", "project_id": project_id})
            meta = md.merge_meta(doc.meta, changes)
            meta["updated_at"] = now_iso()
            md.save(request, md.MarkdownDoc(_ordered(meta), doc.body))
            _log_status_change(
                directory, row["status"], changes["status"],
                f"\n\n삭제 보관함에서 과제 **{project_id}** ({project['title']}) 을(를) 되돌려 다시 이었다.\n",
            )
            relinked.append(row["id"])
        else:
            meta = md.merge_meta(doc.meta, clear)
            md.save(request, md.MarkdownDoc(_ordered(meta), doc.body))
            now = row["project_id"] or row["merged_into"]
            _log_line(
                directory, f"(연결) 과제 {project_id} 되돌림 — 잇지 않음",
                f"삭제 보관함에서 과제 **{project_id}** ({project['title']}) 이(가) 되돌아왔지만, 이 접수는 그 사이 "
                f"**{INTAKE_STATUS_LABELS.get(row['status'], row['status'])}**"
                + (f"(→ {now})" if now else "") + " 이라 다시 잇지 않았다.\n",
            )
        index_intake(conn, directory)

    # 과제 쪽 표지 — 접수가 이 과제를 가리키지 않으면 뗀다(접수가 정답)
    detached: list[str] = []
    intake_id = project["intake_id"]
    if intake_id:
        row = conn.execute("SELECT status, project_id, merged_into FROM intake WHERE id = ?", (intake_id,)).fetchone()
        if row is None or not (row["status"] == "started" and row["project_id"] == project_id):
            directory = projects_service.project_dir(conn, project_id)
            index_md = directory / "index.md"
            doc = md.load(index_md)
            meta = md.merge_meta(doc.meta, {"intake_id": None})
            md.save(index_md, md.MarkdownDoc(meta, doc.body))
            if row is None:
                why = f"접수 {intake_id} 을(를) 찾을 수 없어"
            else:
                now = row["project_id"] or row["merged_into"]
                why = (f"접수 {intake_id} 은(는) 그 사이 **{INTAKE_STATUS_LABELS.get(row['status'], row['status'])}**"
                       + (f"(→ {now})" if now else "") + " 이라")
            projects_service.log_system_line(
                directory, f"(접수) {intake_id} 연결을 떼었다",
                f"삭제 보관함에서 되돌렸다. {why} 이 과제의 접수 연결을 떼었다 — 이제 *직접 등록* 과제로 본다. "
                "같은 일을 하는 과제가 둘이면 한쪽을 [중단]하거나 지워 주세요.\n",
            )
            from ..vault.indexer import index_project

            index_project(conn, directory)
            detached.append(intake_id)
    conn.commit()
    return {"relinked": relinked, "detached": detached}


def _log_line(directory: Path, title: str, body: str) -> None:
    """검토 기록에 도구가 남기는 한 줄 (판정 줄과 같은 태그 — 사람이 쓴 기록 수에 세지 않는다)."""
    from .entries import entry_stem

    try:
        logs_dir = directory / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        day = today()
        target = paths.unique_path(logs_dir, entry_stem(day, title), ".md")
        stamp = now_iso()
        md.save(target, md.MarkdownDoc({
            "date": day, "title": title, "author": settings_service.current_author(None) or None,
            "tags": [STATUS_CHANGE_TAG], "created_at": stamp, "updated_at": stamp,
        }, body))
    except OSError:
        pass


# ── 검토 기록 (인터뷰) ──────────────────────────────────────────────────────
#
# 진행일지와 같은 모양의 md 파일이다. 몇 건 안 되므로 색인하지 않고 파일에서 바로 읽는다.
# 파일 이름이 곧 식별자다 — `logs/2026-10-02-1차-인터뷰.md`.

def _log_path(directory: Path, name: str) -> Path:
    if not _LOG_NAME.match(name or ""):
        raise ValueError("잘못된 기록 이름입니다.")
    path = paths.safe_join(directory / "logs", name)
    if not path.is_file():
        raise KeyError(name)
    return path


def list_logs(conn: sqlite3.Connection, intake_id: str) -> list[dict[str, Any]]:
    directory = intake_dir(conn, intake_id)
    logs: list[dict[str, Any]] = []
    for path in sorted((directory / "logs").glob("*.md")):
        try:
            doc = md.load(path)
        except Exception:
            logs.append({"name": path.name, "date": path.name[:10], "title": path.stem,
                         "body": "", "author": None, "tags": [], "broken": True})
            continue
        logs.append({
            "name": path.name,
            "date": str(doc.meta.get("date") or path.name[:10]),
            "title": str(doc.meta.get("title") or path.stem),
            "author": doc.meta.get("author"),
            "tags": list(doc.meta.get("tags") or []),
            "body": doc.body,
            "updated_at": doc.meta.get("updated_at"),
            "mtime": path.stat().st_mtime,
            "broken": False,
        })
    # 최신이 위 — 과제 진행일지 타임라인과 같은 방향
    logs.sort(key=lambda item: (item["date"], item["name"]), reverse=True)
    return logs


def create_log(conn: sqlite3.Connection, intake_id: str, data: dict[str, Any]) -> str:
    from .entries import entry_stem

    row = _row(conn, intake_id)
    _ensure_open(row)
    directory = intake_dir(conn, intake_id)
    logs_dir = directory / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    day = paths.validate_date(data.get("date"))
    title = _text(data.get("title")) or "검토 기록"
    target = paths.unique_path(logs_dir, entry_stem(day, title), ".md")
    stamp = now_iso()
    meta = {
        "date": day,
        "title": title,
        "author": settings_service.current_author(data.get("author")) or None,
        "tags": _tags(data.get("tags")),
        "created_at": stamp,
        "updated_at": stamp,
    }
    md.save(target, md.MarkdownDoc(meta, str(data.get("body") or "")))
    # 기록이 늘면 목록의 "최근 검토일" 이 바뀐다
    index_intake(conn, directory)
    conn.commit()
    return target.name


def update_log(conn: sqlite3.Connection, intake_id: str, name: str, data: dict[str, Any]) -> str:
    from .entries import entry_stem

    row = _row(conn, intake_id)
    _ensure_open(row)
    directory = intake_dir(conn, intake_id)
    path = _log_path(directory, name)
    if data.get("mtime") is not None:
        md.ensure_unchanged(path, float(data["mtime"]))
    doc = md.load(path)
    changes: dict[str, Any] = {}
    if data.get("date"):
        changes["date"] = paths.validate_date(data["date"])
    if data.get("title") is not None:
        changes["title"] = _text(data["title"]) or "검토 기록"
    if data.get("tags") is not None:
        changes["tags"] = _tags(data["tags"])
    meta = md.merge_meta(doc.meta, changes)
    meta["updated_at"] = now_iso()
    body = data.get("body")
    md.save(path, md.MarkdownDoc(meta, str(body) if body is not None else doc.body))
    # 날짜·제목이 바뀌면 파일 이름도 따라간다
    expected = entry_stem(str(meta["date"]), str(meta["title"]))
    if not path.stem.startswith(expected):
        target = paths.unique_path(path.parent, expected, ".md")
        paths.move(path, target)
        versions.follow(path, target)  # 이전 버전도 따라온다 (TODO 142)
        path = target
    index_intake(conn, directory)
    conn.commit()
    return path.name


def delete_log(conn: sqlite3.Connection, intake_id: str, name: str) -> None:
    row = _row(conn, intake_id)
    _ensure_open(row)
    directory = intake_dir(conn, intake_id)
    path = _log_path(directory, name)
    trash = get_settings().trash_dir
    trash.mkdir(parents=True, exist_ok=True)
    target = paths.unique_path(trash, f"{intake_id}-{datetime.now():%Y%m%d%H%M%S}-{path.stem}", ".md")
    paths.move(path, target)
    trash_service.record("intake_log", label=f"{intake_id} {path.stem}", moved_to=target,
                         origin=path, project_id=None)
    index_intake(conn, directory)
    conn.commit()


# ── 첨부 ────────────────────────────────────────────────────────────────────

def save_attachment(
    conn: sqlite3.Connection, intake_id: str, filename: str, source: BinaryIO,
) -> dict[str, Any]:
    """`assets/<오늘>/NNN-이름` 에 둔다 — 과제와 같은 규칙이라 승격할 때 링크가 그대로 산다."""
    from .attachments import _stream_to_temp, safe_filename

    row = _row(conn, intake_id)
    _ensure_open(row)
    directory = intake_dir(conn, intake_id)
    bucket = paths.safe_join(directory, "assets", today())
    tmp_path, _, _ = _stream_to_temp(source, bucket)
    clean = safe_filename(filename)
    target = bucket / f"{paths.next_sequence_prefix(bucket)}-{clean}"
    if target.exists():
        target = paths.unique_path(bucket, target.stem, target.suffix)
    os.replace(tmp_path, target)
    index_intake(conn, directory)
    conn.commit()
    return _attachment_info(directory, target, intake_id)


def _attachment_info(directory: Path, path: Path, intake_id: str) -> dict[str, Any]:
    from urllib.parse import quote

    from .attachments import guess_mime, is_image, is_spreadsheet, markdown_link

    rel = path.relative_to(directory).as_posix()
    name = path.name.split("-", 1)[1] if path.name[:3].isdigit() and "-" in path.name else path.name
    mime = guess_mime(path.name, None)
    image = is_image(mime)
    return {
        "rel_path": rel,
        "orig_name": name,
        "mime": mime,
        "size_bytes": path.stat().st_size,
        "is_image": image,
        "url": f"/intake-files/{quote(directory.name)}/{quote(rel)}",
        # 엑셀은 그 자리에서 훑어본다 — 과제 첨부의 [내용 보기]와 같은 판 (TODO 138)
        "preview_url": (
            f"/api/intakes/{quote(intake_id)}/attachments/preview?path={quote(rel)}"
            if is_spreadsheet(mime) else None
        ),
        # 요청 본문(폴더 맨 위)과 검토 기록(logs/)은 링크 기준이 다르다
        "markdown": markdown_link(rel, name, "", image),
        "markdown_log": markdown_link(rel, name, "logs", image),
    }


def attachment_preview(conn: sqlite3.Connection, intake_id: str, rel_path: str) -> dict[str, Any]:
    """접수 첨부 엑셀의 내용 보기 (TODO 138). 판정이 난 건도 볼 수는 있다."""
    from .attachments import guess_mime, is_spreadsheet, spreadsheet_preview_path

    directory = intake_dir(conn, intake_id)
    if not rel_path.startswith("assets/"):
        raise ValueError("첨부가 아닙니다.")
    path = paths.safe_join(directory, rel_path)
    if not path.is_file():
        raise KeyError(rel_path)
    if not is_spreadsheet(guess_mime(path.name, None)):
        raise ValueError("엑셀 파일이 아닙니다.")
    return spreadsheet_preview_path(path, _attachment_info(directory, path, intake_id)["orig_name"])


def list_attachments(conn: sqlite3.Connection, intake_id: str) -> list[dict[str, Any]]:
    directory = intake_dir(conn, intake_id)
    assets = directory / "assets"
    if not assets.exists():
        return []
    return [
        _attachment_info(directory, path, intake_id)
        for path in sorted(assets.rglob("*"))
        if path.is_file() and not path.name.endswith(".part")
    ]


def delete_attachment(conn: sqlite3.Connection, intake_id: str, rel_path: str) -> None:
    row = _row(conn, intake_id)
    _ensure_open(row)
    directory = intake_dir(conn, intake_id)
    if not rel_path.startswith("assets/"):
        raise ValueError("첨부가 아닙니다.")
    path = paths.safe_join(directory, rel_path)
    if not path.is_file():
        raise KeyError(rel_path)
    trash = get_settings().trash_dir
    trash.mkdir(parents=True, exist_ok=True)
    target = paths.unique_path(trash, f"{intake_id}-{datetime.now():%Y%m%d%H%M%S}-{path.stem}", path.suffix)
    paths.move(path, target)
    trash_service.record("attachment", label=path.name, moved_to=target, origin=path, project_id=None)
    index_intake(conn, directory)
    conn.commit()


def attachment_file(dir_name: str, rel_path: str) -> Path:
    root = get_settings().intakes_dir
    directory = paths.safe_join(root, dir_name)
    return paths.safe_join(directory, rel_path)


# ── 승격 — 접수 본문을 과제 개요로 ─────────────────────────────────────────

def section_key(heading: str) -> str:
    """섹션 제목의 **괄호·줄표 앞** 이름 — 이것이 같으면 같은 섹션이다.

        "배경 (과제배경)"        → "배경"
        "추진내용 — 과제 범위…"   → "추진내용"
        "목표(성과지표)"         → "목표"
    """
    text = heading.strip().lstrip("#").strip()
    for separator in ("(", "（", "—", "–", " - ", ":", "："):
        text = text.split(separator)[0]
    return " ".join(text.split())


def split_sections(body: str | None) -> tuple[str, list[tuple[str, str]]]:
    """`## 제목` 단위로 나눈다. 첫 제목 앞의 글은 따로 돌려준다."""
    preamble: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    for line in (body or "").splitlines():
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif sections:
            sections[-1][1].append(line)
        else:
            preamble.append(line)
    return "\n".join(preamble).strip(), [(h, "\n".join(lines).strip()) for h, lines in sections]


def _squash(text: str) -> str:
    return " ".join((text or "").split())


def _is_placeholder(content: str, guide: str | None) -> bool:
    """아직 서식 그대로인가. 안내 문구(>)만 있거나, 서식의 그 섹션과 글자가 같으면 빈 섹션이다."""
    if not content.strip():
        return True
    if guide is not None and _squash(content) == _squash(guide):
        return True
    meaningful = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(">"):
            continue
        # 빈 표 줄(| | | |)과 구분선(|---|)은 내용이 아니다
        if stripped.startswith("|") and not stripped.strip("|-: ").replace("|", "").strip():
            continue
        meaningful.append(stripped)
    return not meaningful


def map_body(intake_body: str | None, intake_id: str, title: str) -> dict[str, Any]:
    """접수 본문을 과제 개요 서식에 맞춰 옮긴다 — **같은 제목끼리 옮기고 나머지는 모은다.**

    과제 개요 서식의 섹션마다 같은 이름의 접수 섹션이 있고 내용이 있으면 그 내용으로 채운다.
    짝이 없는 접수 섹션(과 첫 제목 앞의 글)은 맨 아래 `## 접수 내용` 에 모은다.
    `## 관련 링크` 에는 접수 번호를 남긴다 — 과제 쪽에서 어느 접수에서 왔는지 파일만 봐도 보이게.
    """
    from .projects import INDEX_TEMPLATE

    _, project_sections = split_sections(INDEX_TEMPLATE)
    _, template_sections = split_sections(settings_service.intake_template())
    template_guides = {section_key(h): c for h, c in template_sections}
    preamble, intake_sections = split_sections(intake_body)

    filled: dict[str, str] = {}
    used: set[int] = set()
    for p_heading, _ in project_sections:
        key = section_key(p_heading)
        for index, (i_heading, content) in enumerate(intake_sections):
            if index in used or section_key(i_heading) != key:
                continue
            used.add(index)
            if not _is_placeholder(content, template_guides.get(key)):
                filled[key] = content
            break

    leftovers = [
        (heading, content)
        for index, (heading, content) in enumerate(intake_sections)
        if index not in used and not _is_placeholder(content, template_guides.get(section_key(heading)))
    ]
    out: list[str] = []
    matched: list[str] = []
    for p_heading, guide in project_sections:
        key = section_key(p_heading)
        if key == "관련 링크":
            content = f"- 접수: {intake_id} {title}"
        elif key in filled:
            content = filled[key]
            matched.append(key)
        else:
            content = guide
        out.append(f"## {p_heading}\n\n{content}".rstrip())
    if preamble or leftovers:
        extra = []
        if preamble:
            extra.append(preamble)
        extra += [f"### {heading}\n\n{content}" for heading, content in leftovers]
        out.append("## 접수 내용\n\n> 과제 개요에 짝이 없는 접수 섹션입니다. 필요한 곳으로 옮겨 다듬어 주세요.\n\n"
                   + "\n\n".join(extra))
    return {
        "body": "\n\n".join(out) + "\n",
        "matched": matched,
        "leftover": [heading for heading, _ in leftovers] + (["(첫 제목 앞의 글)"] if preamble else []),
    }


def promotion_plan(conn: sqlite3.Connection, intake_id: str) -> dict[str, Any]:
    """승격 화면이 미리 채워 보여 줄 값. **사람이 확인하고 고친 뒤에** 승격한다.

    과제리더는 **명부로 가른다** — 명부에 있는 (떠나지 않은) 사람이면 담당자로, 없으면
    현업 사람으로 보고 유관부서 줄로 보낸다. 요청자 기대효과는 **옮기지 않는다** —
    과제 기대효과는 홈의 팀 합계로 곧장 들어가므로, 검토한 숫자만 들어가야 한다.
    """
    row = _row(conn, intake_id)
    doc = md.load(intake_dir(conn, intake_id) / REQUEST_FILE)
    leader = (row["leader"] or "").strip()
    team = (row["leader_team"] or "").strip()
    active = {person["name"] for person in settings_service.people() if not person.get("left_on")}
    leader_in_roster = bool(leader) and leader in active
    owners = [leader] if leader_in_roster else []
    partners = [] if leader_in_roster or not (leader or team) else [
        {"team": team or "(소속 미기재)", "people": [leader] if leader else []}
    ]
    mapped = map_body(doc.body, intake_id, row["title"])
    return {
        "title": row["title"],
        "type": CLASSIFIED_TYPE,
        "status": "in_progress",
        "owners": owners,
        "partners": partners,
        "leader": leader,
        "leader_team": team,
        "leader_in_roster": leader_in_roster,
        "start_date": row["start_date"],
        "due_date": row["due_date"],
        "effect_request": row["effect_request"],
        **{key: row[key] for key in CLASSIFICATION_KEYS},
        "tags": _tags(doc.meta.get("tags")),
        "body_preview": mapped["body"],
        "matched_sections": mapped["matched"],
        "leftover_sections": mapped["leftover"],
        "attachments": [item["orig_name"] for item in list_attachments(conn, intake_id)],
        "next_project_id": _preview_project_id(row["start_date"]),
    }


def _preview_project_id(start_date: str | None) -> str:
    from .projects import next_project_id, project_year

    return next_project_id(project_year(start_date))


def promote(conn: sqlite3.Connection, intake_id: str, data: dict[str, Any]) -> str:
    """접수를 과제로 승격한다 — **이때 비로소 과제 번호가 붙는다.**

    1. 과제를 만든다 (개요는 접수 본문을 같은 제목끼리 옮긴 것)
    2. 첨부를 **복사**한다 — 과제 폴더만 따로 건네도 깨지지 않게. 접수 쪽에도 원본이 남는다
    3. 접수 건을 `착수` 로 닫고 과제 번호를 적는다 — 양쪽에 링크가 남는다
    """
    from ..vault.indexer import index_project
    from . import projects as projects_service

    row = _row(conn, intake_id)
    _ensure_open(row)
    directory = intake_dir(conn, intake_id)
    doc = md.load(directory / REQUEST_FILE)
    title = _text(data.get("title")) or row["title"]
    mapped = map_body(doc.body, intake_id, title)
    project_id = projects_service.create_project(conn, {
        "title": title,
        "status": data.get("status") or "in_progress",
        "type": data.get("type") if data.get("type") is not None else CLASSIFIED_TYPE,
        "owners": data.get("owners") or [],
        "partners": data.get("partners") or [],
        "start_date": data.get("start_date"),
        "due_date": data.get("due_date"),
        # 검토한 숫자만 (요청자 추정은 옮기지 않는다)
        "effect_expected": data.get("effect_expected"),
        "tags": _tags(data.get("tags")),
        **{key: data.get(key) for key in CLASSIFICATION_KEYS},
        "intake_id": intake_id,
        "body": mapped["body"],
    })

    source_assets = directory / "assets"
    project_dir = projects_service.project_dir(conn, project_id)
    if source_assets.exists() and any(p.is_file() for p in source_assets.rglob("*")):
        shutil.copytree(source_assets, project_dir / "assets", dirs_exist_ok=True)
        index_project(conn, project_dir)

    request = directory / REQUEST_FILE
    meta = md.merge_meta(doc.meta, {
        "status": "started", "project_id": project_id, "decided_on": today(),
        "decision_note": (str(data.get("decision_note") or "").strip() or None),
    })
    meta["updated_at"] = now_iso()
    md.save(request, md.MarkdownDoc(_ordered(meta), doc.body))
    _log_status_change(directory, row["status"], "started", f"\n\n과제 {project_id} 로 승격했다.\n")
    index_intake(conn, directory)
    conn.commit()
    return project_id


# ── 색인 ────────────────────────────────────────────────────────────────────

def index_intake(conn: sqlite3.Connection, directory: Path, problems: list | None = None) -> str | None:
    """접수 폴더 하나를 색인한다. 파일이 원본이고 이 표는 목록·집계용 파생물이다."""
    from ..vault.indexer import IndexProblem, _as_bool, _as_effect, _as_list, _as_str

    request = directory / REQUEST_FILE
    if not request.exists():
        return None
    try:
        doc = md.load(request)
    except Exception as exc:
        if problems is not None:
            problems.append(IndexProblem(request.relative_to(get_settings().vault_dir).as_posix(),
                                         str(exc).splitlines()[0] if str(exc) else type(exc).__name__))
        return intake_id_from_dir_name(directory.name)
    intake_id = _as_str(doc.meta.get("id")) or intake_id_from_dir_name(directory.name)
    status = _as_str(doc.meta.get("status")) or "received"
    if status not in INTAKE_STATUS_KEYS:
        status = "received"
    # 상태 변경 줄은 사람이 한 검토가 아니다 — 기록 수와 "최근 검토일" 에서 뺀다
    human_dates: list[str] = []
    for path in sorted((directory / "logs").glob("*.md")) if (directory / "logs").exists() else []:
        try:
            log = md.load(path)
        except Exception:
            human_dates.append(path.name[:10])
            continue
        if STATUS_CHANGE_TAG in _as_list(log.meta.get("tags")):
            continue
        human_dates.append(_as_str(log.meta.get("date")) or path.name[:10])
    last_log = max(human_dates, default=None)
    assets = directory / "assets"
    attachment_count = sum(1 for p in assets.rglob("*") if p.is_file()) if assets.exists() else 0
    priority = _as_str(doc.meta.get("priority"))
    conn.execute(
        """
        INSERT INTO intake(id, dir_name, title, status, leader, leader_team,
                           nature, category, delivery, cost_kind, start_date, due_date,
                           effect_request, priority, priority_note, picked,
                           received_on, decided_on, decision_note, project_id, merged_into, tags,
                           created_by, created_at, updated_at, log_count, attachment_count,
                           last_log_date, body, file_mtime)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          dir_name=excluded.dir_name, title=excluded.title, status=excluded.status,
          leader=excluded.leader, leader_team=excluded.leader_team,
          nature=excluded.nature, category=excluded.category, delivery=excluded.delivery,
          cost_kind=excluded.cost_kind, start_date=excluded.start_date, due_date=excluded.due_date,
          effect_request=excluded.effect_request, priority=excluded.priority,
          priority_note=excluded.priority_note, picked=excluded.picked,
          received_on=excluded.received_on, decided_on=excluded.decided_on,
          decision_note=excluded.decision_note, project_id=excluded.project_id,
          merged_into=excluded.merged_into, tags=excluded.tags, created_by=excluded.created_by,
          created_at=excluded.created_at, updated_at=excluded.updated_at,
          log_count=excluded.log_count, attachment_count=excluded.attachment_count,
          last_log_date=excluded.last_log_date, body=excluded.body, file_mtime=excluded.file_mtime
        """,
        (
            intake_id,
            directory.name,
            _as_str(doc.meta.get("title")) or directory.name,
            status,
            _as_str(doc.meta.get("leader")),
            _as_str(doc.meta.get("leader_team")),
            *[_as_str(doc.meta.get(key)) for key in CLASSIFICATION_KEYS],
            _as_str(doc.meta.get("start_date")),
            _as_str(doc.meta.get("due_date")),
            _as_effect(doc.meta.get("effect_request")),
            priority if priority in INTAKE_PRIORITIES else None,
            _as_str(doc.meta.get("priority_note")),
            1 if _as_bool(doc.meta.get("picked")) else 0,
            _as_str(doc.meta.get("received_on")) or (_as_str(doc.meta.get("created_at")) or "")[:10] or None,
            _as_str(doc.meta.get("decided_on")),
            _as_str(doc.meta.get("decision_note")),
            _as_str(doc.meta.get("project_id")),
            _as_str(doc.meta.get("merged_into")),
            ", ".join(_as_list(doc.meta.get("tags"))) or None,
            _as_str(doc.meta.get("created_by")),
            _as_str(doc.meta.get("created_at")),
            _as_str(doc.meta.get("updated_at")),
            len(human_dates),
            attachment_count,
            last_log,
            doc.body,
            request.stat().st_mtime,
        ),
    )
    return intake_id


def reindex_intakes(conn: sqlite3.Connection, problems: list | None = None) -> int:
    settings = get_settings()
    settings.ensure_dirs()
    found: list[str] = []
    for directory in sorted(settings.intakes_dir.iterdir()):
        if not directory.is_dir() or directory.name.startswith("."):
            continue
        intake_id = index_intake(conn, directory, problems)
        if intake_id:
            if intake_id in found and problems is not None:  # 같은 번호가 둘 (TODO 146)
                from ..vault.indexer import IndexProblem

                problems.append(IndexProblem(
                    f"intakes/{directory.name}",
                    f"같은 번호 {intake_id} 의 접수 폴더가 둘입니다. 풀에는 하나만 보입니다.",
                ))
            found.append(intake_id)
    if found:
        marks = ",".join("?" * len(found))
        conn.execute(f"DELETE FROM intake WHERE id NOT IN ({marks})", tuple(found))
    else:
        conn.execute("DELETE FROM intake")
    return len(found)


# ── 목록 · 집계 ─────────────────────────────────────────────────────────────

def age_days(received_on: str | None) -> int | None:
    try:
        return (date_cls.today() - date_cls.fromisoformat(str(received_on)[:10])).days
    except (TypeError, ValueError):
        return None


def is_stale(row: sqlite3.Row | dict, stale_days: int | None = None) -> bool:
    """접수 후 N일 판정이 없는가. **보류는 묵힘이 아니다** — 조건을 적고 일부러 세워 둔 것이다."""
    limit = stale_days or settings_service.intake_stale_days()
    age = age_days(row["received_on"])
    return row["status"] in ("received", "reviewing") and age is not None and age > limit


def summary(conn: sqlite3.Connection, year: str | None = None) -> dict[str, Any]:
    """풀의 요약 — 대기 · 검토중 · 보류 · 묵힘, 그리고 그 해의 판정 수(참고)."""
    stale_days = settings_service.intake_stale_days()
    rows = conn.execute("SELECT status, received_on, decided_on FROM intake").fetchall()
    this_year = year or str(date_cls.today().year)
    counts = {key: 0 for key in INTAKE_STATUS_KEYS}
    decided = {key: 0 for key in ("started", "rejected", "transferred", "merged")}
    stale = 0
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
        if row["status"] in decided and str(row["decided_on"] or "")[:4] == this_year:
            decided[row["status"]] += 1
        if is_stale(row, stale_days):
            stale += 1
    return {
        "pool": sum(counts[key] for key in INTAKE_POOL_STATUSES),
        "counts": counts,
        "stale": stale,
        "stale_days": stale_days,
        "year": this_year,
        "decided": decided,
        "received_this_year": sum(1 for row in rows if str(row["received_on"] or "")[:4] == this_year),
    }


def serialize(row: sqlite3.Row, stale_days: int | None = None) -> dict[str, Any]:
    data = {key: row[key] for key in row.keys() if key not in ("body", "file_mtime")}
    data["picked"] = bool(row["picked"])
    data["tags"] = _tags(row["tags"])
    data["status_label"] = INTAKE_STATUS_LABELS.get(row["status"], row["status"])
    data["in_pool"] = row["status"] in INTAKE_POOL_STATUSES
    data["age_days"] = age_days(row["received_on"])
    data["stale"] = is_stale(row, stale_days)
    return data


def related_to_project(conn: sqlite3.Connection, project_id: str) -> list[dict[str, Any]]:
    """과제 상세에 세울 접수 — 이 과제로 승격된 것과, 이 과제에 병합된 것."""
    rows = conn.execute(
        "SELECT id, title, status, project_id, merged_into, received_on FROM intake"
        " WHERE project_id = ? OR merged_into = ? ORDER BY received_on, id",
        (project_id, project_id),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "title": row["title"],
            "status": row["status"],
            "status_label": INTAKE_STATUS_LABELS.get(row["status"], row["status"]),
            "relation": "started" if row["project_id"] == project_id else "merged",
            "received_on": row["received_on"],
        }
        for row in rows
    ]

