"""체험 자료 · 내 자료 모드 (TODO 295).

사용자(2026-11-17): *"체험자료로 돌려보기로 연습할 수 있게 하다가 내 자료로 시작하기로 모드를 바꿔서 사용할 수 있게"*.

* 폴더 둘 — 체험 = 프로그램 옆 `demo-vault/`, 내 자료 = `vault/`(또는 고른 폴더). 모드는 프로그램 폴더의 `data-mode.json`.
  설정 · 명부 · 색인 · 기록 · 백업 폴더 지정이 모두 데이터 폴더 안이라 **두 자료는 섞이지 않는다**. 체험 → 내 자료로 옮기는 길은 두지 않는다.
* 바꾸기 — 모드 파일을 쓰고, 설정 기억을 비우고(`get_settings.cache_clear`), 색인을 그 폴더로 다시 연 뒤 다시 읽는다. 체험 폴더가 비었으면
  체험 자료를 만든다(오늘 날짜 기준). 오래 걸리므로 뒤에서 하고 화면은 `status()` 로 진행을 본다.
* `--vault` 로 켠 서버(지금 쓰는 팀 · 시험)는 모드가 고정 — 바꾸기를 받지 않는다.
"""
from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path
from typing import Any

from ..config import DEMO_DIR, MODE_FILE, get_settings, program_home, read_mode

MODES = ("demo", "mine")
# 체험 자료를 만드는 앱 안 손님만 "바꾸는 중" 을 지나간다 — 이 실행에서만 쓰는 값(바깥에서 맞힐 수 없게)
SEED_HEADER = "x-demo-seed"
_SEED_TOKEN = __import__("secrets").token_hex(16)


def seed_token() -> str:
    return _SEED_TOKEN
_lock = threading.Lock()
_job: dict[str, Any] = {"running": False, "target": "", "stage": "", "done": 0, "total": 0, "error": "", "finished": ""}


class ModeError(ValueError):
    pass


def demo_dir() -> Path:
    return program_home() / DEMO_DIR


def mine_dir() -> Path:
    mine = str(read_mode().get("mine_dir") or "").strip()
    return Path(mine).expanduser().resolve() if mine else program_home() / "vault"


def has_data(folder: Path) -> bool:
    """과제 · 접수 · 사람 중 하나라도 있으면 쓰던 폴더다(설정 파일만 있는 것은 빈 폴더로 본다)."""
    for name in ("projects", "intakes", "people"):
        sub = folder / name
        try:
            if sub.is_dir() and any(sub.iterdir()):
                return True
        except OSError:
            continue
    return False


def need_choice() -> bool:
    """처음 켰을 때 고르기 화면 — 모드를 정한 적 없고, 고정도 아니고, 내 자료 폴더가 비어 있을 때만(지금 쓰는 팀은 묻지 않는다)."""
    settings = get_settings()
    if settings.mode_fixed or (program_home() / MODE_FILE).exists():
        return False
    return not has_data(mine_dir())


def switching() -> bool:
    """바꾸는 중인가 — 그동안 다른 요청은 미들웨어가 "바꾸는 중" 으로 답한다(TODO 297)."""
    with _lock:
        return bool(_job["running"])


def status() -> dict[str, Any]:
    settings = get_settings()
    with _lock:
        job = dict(_job)
    return {"mode": settings.mode, "fixed": settings.mode_fixed, "vault": str(settings.vault_dir),
            "mine_dir": str(mine_dir()), "demo_ready": has_data(demo_dir()), "choose": need_choice(), "job": job}


def _write_mode(mode: str, mine: str | None) -> None:
    data = read_mode()
    data["mode"] = mode
    if mine is not None:
        data["mine_dir"] = mine
    path = program_home() / MODE_FILE
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def reopen() -> int:
    """지금 모드의 폴더로 다시 연다 — 설정 기억 · 색인 연결 · 읽기 캐시 · 사람 기억을 새로."""
    from .. import deps, readcache, who
    from ..db import reset_index
    from ..vault.indexer import reindex_all

    get_settings.cache_clear()
    settings = get_settings()
    settings.ensure_dirs()
    conn = deps.swap()          # 297 — 닫고 여는 사이의 빈틈 없이 바꿔 끼운다
    reset_index(conn)
    indexed, _problems = reindex_all(conn)
    conn.commit()
    readcache.bump()
    who.forget()
    return indexed


def _stage(name: str, done: int = 0, total: int = 0) -> None:
    with _lock:
        _job.update({"stage": name, "done": done, "total": total})


def _run(target: str, mine: str | None, reset: bool) -> None:
    from datetime import datetime

    try:
        _stage("바꾸는 중")
        if target == "demo" and reset:
            shutil.rmtree(demo_dir(), ignore_errors=True)
        _write_mode(target, mine)
        _stage("다시 읽는 중")
        reopen()
        if target == "demo" and not has_data(demo_dir()):
            from . import demo_seed

            demo_seed.build(progress=lambda done, total, label: _stage(f"체험 자료 만드는 중 — {label}", done, total))
            _stage("다시 읽는 중")
            reopen()
        with _lock:
            _job.update({"running": False, "stage": "끝", "finished": datetime.now().isoformat(timespec="seconds")})
    except Exception as exc:  # noqa: BLE001 — 어떤 실패든 화면에 남긴다
        with _lock:
            _job.update({"running": False, "stage": "실패", "error": f"{type(exc).__name__}: {exc}"})


def start(target: str, mine: str | None = None, reset: bool = False, wait: bool = False) -> dict[str, Any]:
    if target not in MODES:
        raise ModeError("모드는 demo(체험) · mine(내 자료) 중 하나입니다.")
    if get_settings().mode_fixed:
        raise ModeError("이 서버는 데이터 폴더를 정해 켰습니다(run.bat --vault) — 모드를 바꿀 수 없습니다.")
    if mine is not None:
        mine = mine.strip()
        if mine:
            folder = Path(mine).expanduser()
            if not folder.is_absolute():
                raise ModeError("내 자료 폴더는 전체 경로로 적어 주세요(예: D:\\과제이력).")
            if folder.resolve() == demo_dir().resolve():
                raise ModeError("체험 폴더는 내 자료 폴더로 쓸 수 없습니다.")
            mine = str(folder.resolve())
    with _lock:
        if _job["running"]:
            raise ModeError("바꾸는 중입니다 — 끝난 뒤 다시 해 주세요.")
        _job.update({"running": True, "target": target, "stage": "시작", "done": 0, "total": 0, "error": "", "finished": ""})
    if wait:
        _run(target, mine, reset)
    else:
        threading.Thread(target=_run, args=(target, mine, reset), daemon=True).start()
    return status()
