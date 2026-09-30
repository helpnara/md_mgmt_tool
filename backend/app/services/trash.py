"""삭제 보관함.

이 도구는 아무것도 진짜로 지우지 않는다. 전부 `vault/.trash/` 로 옮길 뿐이다.
그런데 옮긴 뒤 **어디서 왔는지**를 남기지 않아, 되돌리려면 탐색기를 열고
폴더 구조를 눈으로 짚어 가며 손으로 옮겨야 했다.

그래서 옮길 때마다 `.trash/manifest.jsonl` 에 한 줄씩 적는다.
한 줄이 곧 "무엇을, 언제, 어디서 옮겼는가"이고, 되돌리기는 그 줄을 거꾸로 읽는 일이다.

파일 형식을 JSONL 로 둔 이유는 **덧붙이기만 하면 되기 때문**이다.
중간에 프로그램이 멈춰도 앞선 줄은 멀쩡하고, 한 줄이 깨져도 그 줄만 건너뛰면 된다.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..vault import paths

MANIFEST = "manifest.jsonl"

# 덧붙이기와 다시 쓰기(경로 갱신)가 겹치면 줄을 잃는다. 파일 하나를 지키는 자물쇠다.
_lock = threading.Lock()

# 되돌릴 때 무엇을 다시 읽어야 하는지가 종류마다 다르다.
KIND_LABELS = {
    "project": "과제",
    "entry": "진행일지",
    "report": "보고 문서",
    "attachment": "첨부 파일",
    "activity": "역량 이력",
    "intake": "접수",
    "intake_log": "접수 검토 기록",
}


def _manifest_path() -> Path:
    return get_settings().trash_dir / MANIFEST


def record(kind: str, *, label: str, moved_to: Path, origin: Path, project_id: str | None) -> None:
    """보관함으로 옮긴 사실을 남긴다. 실패해도 삭제 자체를 막지는 않는다."""
    settings = get_settings()
    try:
        entry = {
            "at": datetime.now().isoformat(timespec="seconds"),
            "kind": kind,
            "label": label,
            "project_id": project_id,
            "trash_name": moved_to.name,
            # vault 기준 상대경로로 적는다. vault 폴더를 통째로 옮겨도 되돌릴 수 있다.
            "origin": origin.relative_to(settings.vault_dir).as_posix(),
        }
        settings.trash_dir.mkdir(parents=True, exist_ok=True)
        with _lock:
            with _manifest_path().open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except (OSError, ValueError):
        # 기록에 실패했다고 사용자의 삭제 동작을 되돌릴 이유는 없다.
        # 이 경우 아래 list_items() 가 '복구 정보 없음' 으로 보여 준다.
        pass


def _read_manifest() -> list[dict[str, Any]]:
    path = _manifest_path()
    if not path.exists():
        return []
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue  # 깨진 줄 하나가 나머지를 못 보게 만들면 안 된다
        # 읽히기는 하는데 모양이 다른 줄(`[1]`, `"글"`)도 건너뛴다 — 한 줄 때문에
        # 도구가 켜지지 않았다 (TODO 163). 줄마다 사전이라고 믿는 곳이 여럿이다.
        if isinstance(item, dict):
            items.append(item)
    return items


def list_items() -> list[dict[str, Any]]:
    """보관함 내용. 최근에 지운 것부터.

    기록이 없는 파일(이 기능이 생기기 전에 지운 것)도 숨기지 않고 보여 준다.
    되돌리지는 못해도 무엇이 들어 있는지는 알아야 한다.
    """
    settings = get_settings()
    trash = settings.trash_dir
    if not trash.exists():
        return []

    recorded = {item.get("trash_name"): item for item in _read_manifest()}
    items = []
    for path in sorted(trash.iterdir(), key=lambda p: p.name, reverse=True):
        if path.name == MANIFEST:
            continue
        info = recorded.get(path.name)
        items.append(
            {
                "trash_name": path.name,
                "kind": info["kind"] if info else None,
                "kind_label": KIND_LABELS.get(info["kind"], "항목") if info else None,
                "label": info["label"] if info else path.name,
                "project_id": info.get("project_id") if info else None,
                "deleted_at": info["at"] if info else None,
                "origin": info.get("origin") if info else None,
                # 기록이 없으면 어디로 되돌려야 할지 알 수 없다.
                "restorable": info is not None,
                "is_folder": path.is_dir(),
            }
        )
    # 기록이 있는 것은 지운 시각 순, 없는 것은 뒤로.
    items.sort(key=lambda item: (item["deleted_at"] is None, item["deleted_at"] or ""), reverse=True)
    return items


def trashed_projects() -> dict[str, str]:
    """보관함에 간 과제의 번호 → 이름표 (TODO 145 — 이미 미아가 된 접수를 풀로 돌릴 때 쓴다)."""
    return {
        str(item["project_id"]): str(item.get("label") or item["project_id"])
        for item in _read_manifest()
        if item.get("kind") == "project" and item.get("project_id")
    }


def used_folder_names(root: str) -> set[str]:
    """보관함 기록에 남은 `projects/<폴더>` · `intakes/<폴더>` 이름 (TODO 146).

    다음 번호를 셀 때 **지운 것의 번호도 쓴 번호로** 치려고 쓴다. 남아 있는 폴더만 세면 가장 최근
    것을 지운 순간 그 번호가 빈 것으로 보여 새 과제가 같은 번호를 받고, 지운 것을 되돌리면 번호가
    둘이 된다. 진행일지·보고처럼 과제 안에서 지운 것도 그 과제 폴더 이름을 알려 준다 — 상관없다,
    어느 쪽이든 **쓰인 적 있는 번호**다.
    """
    names: set[str] = set()
    for item in _read_manifest():
        parts = str(item.get("origin") or "").split("/")
        if len(parts) >= 2 and parts[0] == root and parts[1]:
            names.add(parts[1])
    return names


class RestoreError(Exception):
    """되돌릴 수 없는 경우 — 이유를 그대로 화면에 보여 준다."""


def restore(conn: sqlite3.Connection, trash_name: str) -> dict[str, Any]:
    """보관함의 항목을 원래 자리로 되돌린다."""
    settings = get_settings()
    source = settings.trash_dir / trash_name
    # trash_name 은 사용자가 보낸 값이다. 보관함 밖을 가리키지 못하게 한다.
    if "/" in trash_name or "\\" in trash_name or trash_name in ("", ".", ".."):
        raise RestoreError("잘못된 항목입니다.")
    if not source.exists():
        raise RestoreError("보관함에서 찾을 수 없습니다. 이미 되돌렸을 수 있습니다.")

    info = next((item for item in _read_manifest() if item.get("trash_name") == trash_name), None)
    if info is None or not info.get("origin"):
        raise RestoreError(
            "어디서 지운 항목인지 기록이 없어 자동으로 되돌릴 수 없습니다. "
            "보관함 폴더에서 직접 옮겨 주세요."
        )

    _refuse_duplicate_number(conn, source, info)

    target = settings.vault_dir / info["origin"]
    if target.exists():
        # 같은 자리에 새 항목이 생겼을 수 있다. 덮어쓰지 않고 옆에 놓는다.
        target = paths.unique_path(target.parent, f"{target.stem}-복구", target.suffix)
    target.parent.mkdir(parents=True, exist_ok=True)
    paths.move(source, target)

    # 파일이 제자리로 돌아왔으니 색인을 다시 만든다.
    from ..vault.indexer import reindex_all

    reindex_all(conn)
    if info.get("kind") == "project" and info.get("project_id"):
        # 과제가 돌아왔으면 접수와의 연결을 정리한다 — 풀에 있으면 다시 잇고, 아니면 표지를 뗀다 (TODO 145)
        from . import intakes as intakes_service

        intakes_service.reattach_project(conn, str(info["project_id"]))
    conn.commit()
    return {
        "restored_to": target.relative_to(settings.vault_dir).as_posix(),
        "kind": info.get("kind"),
        "label": info.get("label"),
    }


def _refuse_duplicate_number(conn: sqlite3.Connection, source: Path, info: dict[str, Any]) -> None:
    """되돌리면 **같은 번호가 둘**이 되는 경우는 막는다 (TODO 146).

    번호를 다시 쓰지 않게 된 뒤로는 새로 생기지 않지만, 그 전에 이미 같은 번호를 받은 과제·접수가
    있을 수 있다. 되돌리면 색인은 번호가 열쇠라 **한쪽이 목록에서 사라진다** — 되돌리지 않고 까닭을 말한다.
    """
    from ..vault import markdown as md

    kind = info.get("kind")
    if kind == "project":
        document, table, noun = source / "index.md", "project", "과제"
    elif kind == "intake":
        document, table, noun = source / "request.md", "intake", "접수"
    else:
        return
    try:
        number = str(md.load(document).meta.get("id") or "").strip()
    except OSError:
        return
    if not number:
        return
    row = conn.execute(f"SELECT title FROM {table} WHERE id = ?", (number,)).fetchone()
    if row is None:
        return
    raise RestoreError(
        f"같은 번호 {number} 의 {noun}(「{row['title']}」)가 이미 있어 되돌리지 않았습니다 — 되돌리면 "
        f"둘 중 하나가 목록에서 사라집니다. 지금 있는 {noun}의 번호를 먼저 바꾼 뒤(설정 → 과제 번호 체계) "
        "다시 되돌려 주세요."
    )


def rewrite_origins(mapping: dict[str, str]) -> int:
    """보관함 기록의 원래 경로를 바꾼다.

    과제 번호를 일괄로 바꾸면 폴더 이름이 달라지는데, 보관함 기록에는 **옛 경로**가
    남아 있다. 그대로 두면 되돌렸을 때 옛 번호로 살아나, 목록에 두 형태가 섞인다
    (TODO 60 — 2026-09-04 사용자가 "함께 바꾼다" 로 결정).

    `mapping` 은 {옛 폴더명: 새 폴더명}. 바꾼 줄 수를 돌려준다.
    """
    path = _manifest_path()
    if not path.exists() or not mapping:
        return 0
    with _lock:
        return _rewrite_locked(path, mapping)


def _rewrite_locked(path: Path, mapping: dict[str, str]) -> int:
    changed = 0
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            lines.append(line)  # 깨진 줄은 그대로 둔다 — 함부로 버리지 않는다
            continue
        if not isinstance(item, dict):
            lines.append(line)
            continue
        origin = item.get("origin") or ""
        parts = origin.split("/")
        # projects/<과제폴더>/… 형태에서 가운데만 바꾼다.
        if len(parts) >= 2 and parts[0] == "projects" and parts[1] in mapping:
            parts[1] = mapping[parts[1]]
            item["origin"] = "/".join(parts)
            changed += 1
        lines.append(json.dumps(item, ensure_ascii=False))

    if changed:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changed
