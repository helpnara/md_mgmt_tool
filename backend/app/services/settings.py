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
    # 과제 속성 (TODO 100). **null 이면 아직 정한 적이 없다는 뜻**이고, 그때는 코드에 든
    # 기본 여섯을 쓴다. 빈 목록 `[]` 은 "속성을 쓰지 않는다" 는 **정한 값**이라 다르다 —
    # 둘을 같게 두면 속성을 다 뺀 팀에게 다음 실행에서 여섯이 되살아난다.
    # [{"key": "smart", "label": "스마트과제"}, …]
    "project_types": None,
    # 과제 번호의 팀·부문 코드. 비우면 2026-001, "소재" 를 넣으면 2026-소재-001.
    # 여러 팀장이 함께 쓰게 될 때 번호가 겹치지 않게 하는 자리다.
    "project_code": "",
    # 주간 보고를 하는 요일 (0=월 … 6=일). 팀마다 다르다.
    # 이 값 하나가 보고 예정일·리마인더·초안 기본 날짜를 모두 정한다.
    "report_weekday": 1,
    # 자동 백업 (바깥쪽 안전망). 폴더를 비워 두면 꺼진다.
    "backup_dir": "",
    "backup_keep": 10,        # 남겨 둘 백업 개수
    "backup_every_hours": 24,  # 이 시간이 지나면 다시 백업한다
    # AI 요약 프롬프트의 앞뒤에 붙일 글 (TODO 71). 비우면 기본 지시문을 쓴다.
    # 도구가 AI 를 부르지는 않는다 — 붙여넣기 좋은 글을 만들어 줄 뿐이다.
    "ai_prompt_prefix": "",
    "ai_prompt_suffix": "",
}
# 문자열로 다루는 항목. 나머지는 형태를 그대로 지킨다.
_TEXT_KEYS = ("author", "report_template", "project_code",
              "ai_prompt_prefix", "ai_prompt_suffix")


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
        elif key == "backup_dir":
            from . import backup as backup_service

            current[key] = backup_service.validate_dir(str(updates[key] or ""))
        elif key in ("backup_keep", "backup_every_hours"):
            current[key] = _positive_int(key, updates[key])
        elif key == "project_types":
            current[key] = validate_project_types(updates[key])
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


# ── AI 요약 프롬프트 (TODO 71) ────────────────────────

def ai_prompt_prefix() -> str:
    """프롬프트 맨 앞에 붙는 글. 비워 두면 기본 지시문을 쓴다."""
    from . import ai_prompt

    return str(load()["ai_prompt_prefix"]).strip() or ai_prompt.DEFAULT_PREFIX


def ai_prompt_suffix() -> str:
    """프롬프트 맨 뒤에 붙는 글. 기본값은 없다 — 필요한 사람만 채운다."""
    from . import ai_prompt

    return str(load()["ai_prompt_suffix"]).strip() or ai_prompt.DEFAULT_SUFFIX


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


# 팀 코드는 **그대로 폴더 이름에 들어간다** (`2026-소재-001-제목`).
# 과제명은 슬러그로 다듬어지지만 코드는 다듬지 않으므로, 여기서 막지 않으면
# 윈도우에서 폴더를 아예 만들지 못하는 이름이 된다.
_CODE_FORBIDDEN = '/\\:*?"<>| \t\r\n'
MAX_CODE_LEN = 20


def validate_project_code(code: str) -> str:
    """과제 번호에 쓸 팀 코드를 검사한다.

    막는 것 넷:
      · 숫자만  — 일련번호와 구분되지 않는다
      · 윈도우가 파일 이름에 못 쓰는 문자 — 폴더를 만들 수 없다
      · 끝의 점 — 탐색기가 잘라 내 폴더 이름이 어긋난다
      · 너무 긴 것 — 폴더 이름이 길어져 윈도우 260자 경로 제한에 걸린다
    """
    code = (code or "").strip()
    if not code:
        return ""
    if code.isdigit():
        raise ValueError("팀 코드는 숫자만으로 지을 수 없습니다. 일련번호와 구분되지 않습니다.")
    bad = sorted({ch for ch in code if ch in _CODE_FORBIDDEN})
    if bad:
        shown = " ".join(repr(ch).strip("'") if ch.strip() else "공백" for ch in bad)
        raise ValueError(f"팀 코드에 쓸 수 없는 문자가 있습니다: {shown}")
    if code != code.rstrip("."):
        raise ValueError("팀 코드는 점(.)으로 끝날 수 없습니다. 윈도우에서 잘려 나갑니다.")
    if set(code) <= {"."}:
        raise ValueError("팀 코드를 점만으로 지을 수 없습니다.")
    if len(code) > MAX_CODE_LEN:
        raise ValueError(f"팀 코드는 {MAX_CODE_LEN}자 이내여야 합니다. 폴더 이름이 너무 길어집니다.")
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


def _positive_int(key: str, value: object) -> int:
    labels = {"backup_keep": "남겨 둘 백업 개수", "backup_every_hours": "백업 주기(시간)"}
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{labels.get(key, key)}는 숫자여야 합니다.") from exc
    if number < 1:
        raise ValueError(f"{labels.get(key, key)}는 1 이상이어야 합니다.")
    if number > 999:
        raise ValueError(f"{labels.get(key, key)}가 너무 큽니다.")
    return number


# ── 과제 속성 (TODO 100) ──────────────────────────────
#
# 속성은 오래 **코드에 박힌 다섯**이었다 (스마트과제·R&D·투자·기획보고·국책과제).
# 팀마다 쓰는 말이 다르고, 하나 더하려면 개발자를 불러야 했다. 설정으로 옮긴다.
#
# 다루는 규칙 셋.
#
# 1. **열쇠(key)와 이름(label)을 나눈다.** 과제 파일에 남는 것은 열쇠고, 화면에 보이는
#    것은 이름이다. 그래서 이름을 고쳐도 이미 만든 과제가 속성을 잃지 않는다.
# 2. **쓰고 있는 속성은 뺄 수 없다.** 빼면 그 과제들이 색인에서 미지정이 된다.
#    몇 건이 쓰고 있는지 말해 주고, 옮겨 놓은 뒤에 빼게 한다 (API 가 막는다).
# 3. **비워 두면 기본 여섯.** 설정 파일이 없는 vault, 예전 vault 가 그대로 열린다.

MAX_TYPE_LABEL = 20
MAX_TYPES = 24


def project_types() -> list[dict[str, str]]:
    """과제 속성 목록 — 설정에 있으면 그것, 없으면 코드의 기본값.

    **여기가 유일한 출처다.** 거르기 상자도, 대시보드 칩도, 홈의 속성별 표도,
    진행일지 서식의 속성별 갈래도 이 목록을 본다.
    """
    from ..config import PROJECT_TYPES

    stored = load().get("project_types")
    # 아직 정한 적이 없으면(null) 기본 여섯. 빈 목록은 정해서 비운 것이므로 그대로 둔다.
    if not isinstance(stored, list):
        return [{"key": key, "label": label} for key, label in PROJECT_TYPES]
    found: list[dict[str, str]] = []
    for item in stored:
        # 설정 파일을 손으로 고치다 깨졌어도 도구가 멈출 이유는 없다.
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        label = str(item.get("label") or "").strip()
        if key and label:
            found.append({"key": key, "label": label})
    return found


def type_keys() -> list[str]:
    return [item["key"] for item in project_types()]


def type_labels() -> dict[str, str]:
    return {item["key"]: item["label"] for item in project_types()}


def _type_key(label: str, taken: set[str]) -> str:
    """이름에서 열쇠를 짓는다. 한글은 그대로 두고, 겹치면 뒤 번호를 붙인다."""
    from ..vault.paths import slugify

    base = slugify(label)
    if base == "untitled":
        base = "type"
    candidate = base
    number = 1
    while candidate in taken:
        number += 1
        candidate = f"{base}-{number}"
    return candidate


def validate_project_types(items: Any) -> list[dict[str, str]]:
    """화면이 보낸 속성 목록을 다듬는다.

    새로 더한 줄은 열쇠가 비어 있다 — 이름에서 지어 붙인다.
    이미 있는 줄은 **열쇠를 그대로 둔다.** 그래야 이름만 고쳐도 과제가 속성을 잃지 않는다.
    """
    if not isinstance(items, list):
        raise ValueError("과제 속성 목록의 형태가 올바르지 않습니다.")
    if len(items) > MAX_TYPES:
        raise ValueError(f"과제 속성은 {MAX_TYPES}개까지 둘 수 있습니다.")

    found: list[dict[str, str]] = []
    keys: set[str] = set()
    labels: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("과제 속성 목록의 형태가 올바르지 않습니다.")
        label = str(item.get("label") or "").strip()
        if not label:
            raise ValueError("속성 이름을 적어 주세요. 빈 이름은 둘 수 없습니다.")
        if len(label) > MAX_TYPE_LABEL:
            raise ValueError(f"속성 이름은 {MAX_TYPE_LABEL}자 이내여야 합니다: {label}")
        if label in labels:
            raise ValueError(f"같은 이름의 속성이 둘 있습니다: {label}")
        labels.add(label)

        key = str(item.get("key") or "").strip()
        if not key:
            key = _type_key(label, keys)
        if key in keys:
            raise ValueError(f"같은 열쇠의 속성이 둘 있습니다: {key}")
        keys.add(key)
        found.append({"key": key, "label": label})
    return found
