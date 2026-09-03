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

# 빈 문자열이면 코드에 있는 기본 서식을 쓴다. 사용자가 채우면 그것이 우선한다.
# 진행일지 서식은 과제 속성마다 다를 수 있어 사전으로 둔다 ("" 키가 공통 서식).
DEFAULTS: dict[str, Any] = {
    "author": "",
    "entry_templates": {},
    "report_template": "",
    # 담당자 명부. 표기 흔들림(권경락 / 권 경락)을 막고, 나중에 계정을 붙일 자리다.
    # [{"name": "권경락", "employee_id": "", "account": ""}]
    "people": [],
    # 과제 번호의 팀·부문 코드. 비우면 2026-001, "소재" 를 넣으면 2026-소재-001.
    # 여러 팀장이 함께 쓰게 될 때 번호가 겹치지 않게 하는 자리다.
    "project_code": "",
    # 주간 보고를 하는 요일 (0=월 … 6=일). 팀마다 다르다.
    # 이 값 하나가 보고 예정일·리마인더·초안 기본 날짜를 모두 정한다.
    "report_weekday": 1,
}
# 문자열로 다루는 항목. 나머지는 형태를 그대로 지킨다.
_TEXT_KEYS = ("author", "report_template", "project_code")


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
        if key not in updates or updates[key] is None:
            continue
        if key in _TEXT_KEYS:
            current[key] = str(updates[key]).strip()
        elif key == "people":
            current[key] = normalize_people(updates[key])
        elif key == "report_weekday":
            current[key] = validate_report_weekday(updates[key])
        elif key == "entry_templates":
            # 빈 서식은 저장하지 않는다 — 비우면 "기본 서식으로 되돌린다"는 뜻이다.
            current[key] = {
                str(k): str(v) for k, v in dict(updates[key]).items() if str(v).strip()
            }
        else:
            current[key] = updates[key]
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


def entry_template(project_type: str | None) -> str:
    """진행일지 기본 서식.

    과제 속성별 서식이 있으면 그것을, 없으면 공통 서식을, 그것도 없으면
    코드에 든 기본값을 쓴다. 빈칸에서 시작하면 무엇을 적을지부터 고민하게 된다.
    """
    from ..config import DEFAULT_ENTRY_TEMPLATE

    templates = load()["entry_templates"]
    for key in (project_type or "", ""):
        text = str(templates.get(key, "")).strip()
        if text:
            return text
    return DEFAULT_ENTRY_TEMPLATE


def report_template() -> str:
    """보고 초안 서식. `{summary}` 자리에 미보고 진행일지가 들어간다."""
    from ..services.reports import DRAFT_TEMPLATE

    text = load()["report_template"].strip()
    # {summary} 가 없으면 진행 내용이 통째로 사라진다. 그런 서식은 쓰지 않는다.
    return text if "{summary}" in text else DRAFT_TEMPLATE


# ── 담당자 명부 ───────────────────────────────────────

def normalize_people(value: object) -> list[dict[str, str]]:
    """명부를 정리한다. 이름이 비었거나 겹치는 줄은 버린다.

    사번·계정 칸은 지금 비어 있는 것이 정상이다 — 로그인이 생길 때 채운다.
    """
    people: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in value or []:
        item = raw if isinstance(raw, dict) else {"name": raw}
        name = str(item.get("name", "")).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        people.append(
            {
                "name": name,
                "employee_id": str(item.get("employee_id", "")).strip(),
                "account": str(item.get("account", "")).strip(),
            }
        )
    people.sort(key=lambda person: person["name"])
    return people


def people() -> list[dict[str, str]]:
    return normalize_people(load()["people"])


def known_names() -> list[str]:
    return [person["name"] for person in people()]


def add_person(name: str) -> list[dict[str, str]]:
    """명부에 없는 이름을 그 자리에서 추가한다 (화면에서 물어본 뒤 부른다)."""
    name = (name or "").strip()
    if not name:
        raise ValueError("이름을 입력하세요.")
    current = people()
    if any(person["name"] == name for person in current):
        return current
    current.append({"name": name, "employee_id": "", "account": ""})
    return save({"people": current})["people"]


# ── 과제 번호 코드 ────────────────────────────────────

def project_code() -> str:
    """과제 번호에 넣을 팀·부문 코드. 비어 있으면 번호는 지금 형태 그대로다."""
    return str(load()["project_code"]).strip()


def validate_project_code(code: str) -> str:
    """숫자만으로 된 코드는 받지 않는다 — 일련번호와 구분되지 않는다."""
    code = (code or "").strip()
    if not code:
        return ""
    if code.isdigit():
        raise ValueError("팀 코드는 숫자만으로 지을 수 없습니다. 일련번호와 구분되지 않습니다.")
    if any(ch in code for ch in "/\\ \t"):
        raise ValueError("팀 코드에 공백이나 경로 문자를 넣을 수 없습니다.")
    return code


# ── 주간 보고 요일 ────────────────────────────────────

WEEKDAY_LABELS = ("월", "화", "수", "목", "금", "토", "일")


def report_weekday() -> int:
    """주간 보고를 하는 요일 (0=월 … 6=일). 값이 깨져 있으면 기본값으로 돌린다."""
    try:
        return validate_report_weekday(load()["report_weekday"])
    except ValueError:
        return int(DEFAULTS["report_weekday"])


def validate_report_weekday(value: object) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("보고 요일은 0(월)부터 6(일) 사이의 숫자여야 합니다.") from exc
    if not 0 <= number <= 6:
        raise ValueError("보고 요일은 0(월)부터 6(일) 사이여야 합니다.")
    return number
