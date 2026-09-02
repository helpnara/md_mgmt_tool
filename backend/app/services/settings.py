"""도구 설정.

지금은 팀장 한 명이 쓰므로 '작성자'를 설정에서 한 번 정해 두고 쓴다.
나중에 로그인이 생기면, 이 값 대신 로그인한 사용자를 작성자로 넘기면 된다.
(그래서 API는 요청마다 작성자를 직접 지정하는 길도 열어 둔다)
"""
from __future__ import annotations

import json
from typing import Any

from ..config import get_settings

FILENAME = "settings.json"
DEFAULTS: dict[str, Any] = {"author": ""}


def _path():
    return get_settings().vault_dir / FILENAME


def load() -> dict[str, Any]:
    path = _path()
    if not path.exists():
        return dict(DEFAULTS)
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # 설정 파일이 깨졌다고 도구가 멈출 이유는 없다.
        return dict(DEFAULTS)
    return {**DEFAULTS, **{key: stored.get(key, value) for key, value in DEFAULTS.items()}}


def save(updates: dict[str, Any]) -> dict[str, Any]:
    current = load()
    for key in DEFAULTS:
        if key in updates and updates[key] is not None:
            current[key] = str(updates[key]).strip()
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return current


def current_author(explicit: str | None = None) -> str:
    """요청이 작성자를 지정했으면 그것을, 아니면 설정값을 쓴다.

    로그인이 생기면 explicit 자리에 로그인 사용자가 들어온다.
    """
    if explicit and explicit.strip():
        return explicit.strip()
    return load()["author"]
