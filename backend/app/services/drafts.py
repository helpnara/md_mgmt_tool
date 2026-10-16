"""쓰다 만 글 — 임시 보관 (TODO 162 · 170).

처음(162)에는 브라우저 안(localStorage)에 두었다. 그런데 사용자가 **창 하나만 닫고 다른 창에서** 다시 열었을 때
"작성 중이던 기록 있음" 이 뜨지 않았다(v7 B-6). 브라우저 보관은 창 · 프로필 · 주소마다 따로이고, 이미 열린 화면은
다시 읽지도 않는다. 그래서 **데이터 폴더**(`.drafts/`)로 옮긴다 — 어느 창에서 열어도 같은 글이 돌아오고,
홈이 "작성 중이던 글" 을 모아 보여 줄 수 있다.

한 글 = 파일 하나(`<열쇠>.json`). 저장 · [버리기] · [취소] 때 지운다. 과제 파일이 아니므로 버전 보관 · 색인 · 검색에
들어가지 않는다. 백업에는 함께 담긴다(데이터 폴더 안이므로) — 쓰다 만 글도 잃으면 아깝다.

열쇠 모양 — 화면이 쓰는 이름 그대로:
  entry:new-<과제>   새 진행일지        entry:<번호>    기존 진행일지 고치기
  overview:<과제>    과제 개요          report:<번호>   보고 초안
  intake:<접수>      접수 요청 내용
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..vault import paths

# 화면이 만드는 열쇠만 받는다 — 경로를 벗어나는 글자(`/` `..` `\`)는 아예 들어올 수 없다.
KEY_PATTERN = re.compile(r"^(entry:new-[0-9A-Za-z가-힣_-]{1,80}|entry:\d{1,18}|overview:[0-9A-Za-z가-힣_-]{1,80}"
                         r"|report:\d{1,18}|intake:[0-9A-Za-z가-힣_-]{1,80})$")
MAX_BYTES = 2_000_000  # 쓰다 만 글 하나로는 넉넉하다. 이보다 크면 무언가 잘못 붙은 것이다.


# TODO 215 — 임시 보관 파일의 읽기 · 쓰기 · 지우기 · 목록을 **한 잠금 안에서.** 화면이 같은 열쇠를 동시에 두 번 지우거나,
# 지우는 사이 목록(GET)이 모든 파일을 열면 윈도우가 `WinError 5 액세스 거부` 를 냈다. 쓰기 줄 세우기(get_db)에는
# 넣지 않는다 — 자주 오고 다른 쓰기와 엮이지 않는다. 이 모듈 하나의 잠금이면 충분하다.
_lock = threading.RLock()
# 지우려 했지만 윈도우가 끝내 거부한 열쇠 — 지운 것으로 보고(열기 · 목록에서 숨김) 다음 목록 · 쓰기 · 지우기 때 다시 지운다.
# 파일 경로로 적는다 — 데이터 폴더가 바뀌어도(시험 · --vault) 다른 폴더의 같은 열쇠를 숨기지 않게.
_pending: set[Path] = set()


def valid_key(key: str) -> bool:
    return bool(KEY_PATTERN.match(key))


def _dir() -> Path:
    return get_settings().drafts_dir


def _file(key: str) -> Path:
    if not valid_key(key):
        raise ValueError("임시 보관 열쇠가 올바르지 않습니다.")
    return _dir() / f"{key.replace(':', '__')}.json"


def _key_of(path: Path) -> str:
    return path.stem.replace("__", ":", 1)


def _read(key: str) -> dict[str, Any] | None:
    path = _file(key)
    if path in _pending:
        return None  # 지운 것으로 본다 (TODO 215)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) and "content" in data else None


def get(key: str) -> dict[str, Any] | None:
    _file(key)  # 열쇠 검사
    with _lock:
        return _read(key)


def _retry_pending() -> None:
    """지우지 못하고 남겨 둔 것을 다시 지운다 (TODO 215). 이번에도 안 되면 다음 차례에 — 오류로 내지 않는다."""
    for path in list(_pending):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            continue
        _pending.discard(path)


def put(key: str, content: Any) -> dict[str, Any]:
    path = _file(key)
    record = {"key": key, "content": content, "updated_at": datetime.now().isoformat(timespec="seconds")}
    text = json.dumps(record, ensure_ascii=False)
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("임시 보관하기에 글이 너무 큽니다 — 저장해 주세요.")
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        # 쓰다 끊겨도 앞의 보관이 깨지지 않게 — 임시 파일에 쓰고 바꿔 끼운다(markdown.save 와 같은 방식)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            # TODO 215 — 바꿔 끼우기도 윈도우의 일시적 거부를 몇 번 다시
            paths.retry_os(os.replace, tmp, path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
        # 새로 쓴 글이 섰다 — 지우려다 남겨 둔 표지는 뗀다
        _pending.discard(path)
        _retry_pending()
    return record


def drop(key: str) -> bool:
    """지운다. **실패해도 오류로 내지 않는다** (TODO 215) — 임시 보관 지우기는 "치우는 일" 이라, 기록 저장은 이미 끝났다.

    윈도우의 일시적 거부는 몇 번 다시 시도하고, 그래도 안 되면 지운 것으로 표시해 두었다가 다음 목록 · 쓰기 · 지우기 때 다시 지운다.
    """
    path = _file(key)
    with _lock:
        try:
            paths.retry_os(path.unlink)
            removed = True
        except FileNotFoundError:
            removed = path in _pending
        except OSError:
            _pending.add(path)
            return True
        _pending.discard(path)
        _retry_pending()
        return removed


def pending_keys() -> set[str]:
    """지우려다 남겨 둔 열쇠 (시험 · 점검용)."""
    return {_key_of(path) for path in _pending}


def _describe(conn: sqlite3.Connection, key: str) -> dict[str, Any]:
    """홈의 "작성 중이던 글" 한 줄 — 무엇을(종류) · 어디에(과제 · 접수) · 어디로 가면 이어 쓰나(link)."""
    kind, _, ident = key.partition(":")
    out: dict[str, Any] = {"kind": kind, "label": "", "where": "", "link": None, "missing": False}
    if kind == "entry" and ident.startswith("new-"):
        project_id = ident[len("new-"):]
        row = conn.execute("SELECT title FROM project WHERE id = ?", (project_id,)).fetchone()
        out.update(label="새 진행일지", where=f"{project_id} {row['title']}" if row else project_id,
                   link=f"#/projects/{project_id}?draft=entry-new", missing=row is None)
    elif kind == "entry":
        row = conn.execute(
            "SELECT e.project_id, e.title, p.title AS ptitle FROM entry e JOIN project p ON p.id = e.project_id WHERE e.id = ?",
            (int(ident),),
        ).fetchone()
        out.update(label=f"진행일지 고치기 — {row['title']}" if row else "진행일지 고치기",
                   where=f"{row['project_id']} {row['ptitle']}" if row else "",
                   link=f"#/projects/{row['project_id']}?draft=entry-{ident}" if row else None, missing=row is None)
    elif kind == "overview":
        row = conn.execute("SELECT title FROM project WHERE id = ?", (ident,)).fetchone()
        out.update(label="과제 개요", where=f"{ident} {row['title']}" if row else ident,
                   link=f"#/projects/{ident}?draft=overview", missing=row is None)
    elif kind == "report":
        row = conn.execute(
            "SELECT r.project_id, r.report_date, p.title AS ptitle FROM report r JOIN project p ON p.id = r.project_id WHERE r.id = ?",
            (int(ident),),
        ).fetchone()
        out.update(label=f"보고 초안 {row['report_date']}" if row else "보고 초안",
                   where=f"{row['project_id']} {row['ptitle']}" if row else "",
                   link=f"#/projects/{row['project_id']}?report={ident}" if row else None, missing=row is None)
    elif kind == "intake":
        # 검토 기록의 임시 보관은 `intake:<접수번호>--log-<기록 이름|new>` (TODO 211 ③) — 요청 내용과 나눠 읽는다
        intake_id, _, log_name = ident.partition("--log-")
        row = conn.execute("SELECT title FROM intake WHERE id = ?", (intake_id,)).fetchone()
        out.update(label="검토 기록" if log_name else "접수 요청 내용",
                   where=f"{intake_id} {row['title']}" if row else intake_id,
                   link=f"#/intakes/{intake_id}" + ("" if log_name else "?draft=body"), missing=row is None)
    return out


def listing(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """남아 있는 임시 보관 전부 — 새 것부터. 글 내용은 싣지 않는다(목록에는 무엇 · 어디만)."""
    folder = _dir()
    records = []
    with _lock:
        _retry_pending()
        for path in folder.glob("*.json") if folder.exists() else []:
            key = _key_of(path)
            if not valid_key(key):
                continue
            record = _read(key)
            if record is not None:
                records.append((key, record))
    # 색인 조회(_describe)는 잠금 밖에서 — 파일은 이미 다 읽었다
    items = [{"key": key, "updated_at": record.get("updated_at"), **_describe(conn, key)} for key, record in records]
    items.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return items
