"""도구 설정.

지금은 팀장 한 명이 쓰므로 '작성자'를 설정에서 한 번 정해 두고 쓴다.
나중에 로그인이 생기면, 이 값 대신 로그인한 사용자를 작성자로 넘기면 된다.
(그래서 API는 요청마다 작성자를 직접 지정하는 길도 열어 둔다)
"""
from __future__ import annotations

import json
import os
from typing import Any

from .. import clock
from .. import schemas as rules
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
    # 층을 나눠 남긴다 — GFS(Grandfather-Father-Son), TODO 119.
    # 하루 한 벌씩 열흘치만 남기면 **되돌릴 수 있는 범위가 열흘**이다. 2주 전에 잘못 지운
    # 것은 이미 없다. 같은 개수로 훨씬 긴 기간을 덮으려고 층을 나눈다.
    "backup_keep": 7,          # 일 단위 — 최근 며칠치를 그대로 남기나
    "backup_keep_weekly": 4,   # 주 단위 — 주마다 한 벌 (한 달)
    "backup_keep_monthly": 6,  # 월 단위 — 달마다 한 벌 (반년)
    "backup_every_hours": 24,  # 이 시간이 지나면 다시 백업한다
    # AI 요약 프롬프트의 앞뒤에 붙일 글 (TODO 71). 비우면 기본 지시문을 쓴다.
    # 도구가 AI 를 부르지는 않는다 — 붙여넣기 좋은 글을 만들어 줄 뿐이다.
    "ai_prompt_prefix": "",
    "ai_prompt_suffix": "",
    # 과제 분류 넷의 목록 (TODO 136). **null 이면 아직 정한 적이 없다** — 코드의 기본 목록을 쓴다.
    # {"nature": [...], "category": [...], "delivery": [...], "cost_kind": [...]}
    "classifications": None,
    # 접수 본문 서식 (TODO 136). 비우면 기본 서식. 섹션 제목을 과제 개요에 맞춰 두면
    # 승격할 때 그대로 넘어간다 (괄호·줄표 앞까지 비교).
    "intake_template": "",
    # 접수 후 이 날수가 지나도 판정이 없으면 홈에 알린다. 요청자에게 가장 나쁜 것은 답이 없는 것이다.
    "intake_stale_days": 14,
    # 접수 사전점검 체크리스트 (TODO 155). **null 이면 기본 목록**(사용자가 준 다섯 분류 · 열 항목).
    # [{"group": "필요성", "item": "…", "choices": [["근거 명확", 10], …]}, …]
    "precheck_items": None,
    # 점수 구간 — 이상이면 착수 권장 / 이상이면 보완 필요 / 그 아래 보류 검토
    "precheck_thresholds": [80, 60],
    # 팀원 면담의 구분 (TODO 182). **null 이면 기본 목록**(정기 · 목표 설정 · 중간 점검 · 수시 · 고충).
    "meeting_kinds": None,
    # 마지막 면담에서 이 날수가 지나면 "면담에서 먼저 볼 사람" 에 세운다 (TODO 182)
    "meeting_cycle_days": 90,
    # 백업에 첨부(assets)를 넣지 않는다 (TODO 202 · 197) — 첨부가 GB 단위면 백업이 조용히 실패했다.
    # 끄면(False, 기본) 지금처럼 전부 넣는다. 백업 서비스가 읽는다.
    "backup_skip_assets": False,
    # 효과 금액 단위 확인 기준선 (TODO 214 D4) — 억원/년. 한 칸이 이보다 크면 화면이 저장 전에 "단위를 확인하세요" 를 묻는다.
    # 0 이면 묻지 않는다. 서버는 막지 않는다(상한은 schemas.NUMBER_MAX).
    "effect_confirm_over": 100,
}
# 문자열로 다루는 항목. 나머지는 형태를 그대로 지킨다.
# 팀 코드(project_code)는 여기서 빼 저장할 때도 검사한다 (TODO 214 D16).
_TEXT_KEYS = ("author", "report_template",
              "ai_prompt_prefix", "ai_prompt_suffix", "intake_template")


def _path():
    return get_settings().vault_dir / FILENAME


# 값의 모양 (TODO 163). 손으로 고친 설정 파일의 값 하나가 모양이 다르면(`"backup_every_hours": "매일"`)
# 그 값을 쓰는 곳이 모두 넘어졌다. 읽을 때 한 번 걸러 **그 값만** 기본값으로 둔다.
_NULLABLE_SHAPES: dict[str, type] = {"project_types": list, "classifications": dict, "precheck_items": list,
                                      "meeting_kinds": list}
_POSITIVE_KEYS = ("backup_keep", "backup_every_hours", "intake_stale_days", "meeting_cycle_days")
_ZERO_OK_KEYS = ("backup_keep_weekly", "backup_keep_monthly")

# 마지막으로 읽을 때 기본값으로 바꾼 열쇠 — 설정 화면이 알린다.
_unreadable: list[str] = []


def _shape_ok(key: str, value: Any) -> bool:
    default = DEFAULTS[key]
    if key == "effect_confirm_over":
        return _confirm_over_ok(value)
    if key == "project_code":
        # TODO 214 F3 — 손으로 고친 팀 코드(`a/b`)를 그대로 쓰면 폴더가 두 단으로 생겼다. 틀리면 빈 코드로 읽고 알린다.
        if not isinstance(value, str):
            return False
        try:
            validate_project_code(value)
        except ValueError:
            return False
        return True
    if key in _NULLABLE_SHAPES:
        return value is None or isinstance(value, _NULLABLE_SHAPES[key])
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, int):
        if isinstance(value, bool) or not isinstance(value, int):
            return False
        if key == "report_weekday":
            return 0 <= value <= 6
        if key in _POSITIVE_KEYS:
            return value >= 1
        if key in _ZERO_OK_KEYS:
            return value >= 0
        return True
    if key == "precheck_thresholds":
        return (isinstance(value, list) and len(value) == 2
                and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value))
    return isinstance(value, type(default))


def load() -> dict[str, Any]:
    path = _path()
    _unreadable.clear()
    if not path.exists():
        return dict(DEFAULTS)
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # 설정 파일이 깨졌다고 도구가 멈출 이유는 없다.
        _unreadable.append("*")
        return dict(DEFAULTS)
    if not isinstance(stored, dict):
        # 목록·글이면 시작하다 멈췄다 (TODO 163)
        _unreadable.append("*")
        return dict(DEFAULTS)
    out = dict(DEFAULTS)
    for key in DEFAULTS:
        if key not in stored:
            continue
        if _shape_ok(key, stored[key]):
            out[key] = stored[key]
        else:
            _unreadable.append(key)
    return out


def unreadable_keys() -> list[str]:
    """설정 파일에서 읽지 못해 기본값을 쓰고 있는 열쇠. `"*"` 는 파일 전체."""
    load()
    return list(_unreadable)


def save(updates: dict[str, Any]) -> dict[str, Any]:
    current = load()
    for key in DEFAULTS:
        if key not in updates or updates[key] is None:
            continue
        if key == "author":
            current[key] = rules.clean_author(updates[key])  # 줄바꿈 · 40자 (TODO 205)
        elif key in _TEXT_KEYS:
            current[key] = str(updates[key]).strip()
        elif key == "people":
            # 화면 · API 로 들어온 명부는 엄격히 — 틀린 떠난 날 · 겹친 이름은 400 (TODO 205 ㉞).
            # 읽을 때(손으로 고친 파일)는 지금처럼 너그럽게 거른다(normalize_people).
            check_people(updates[key])
            current[key] = normalize_people(updates[key])
        elif key == "backup_skip_assets":
            if not isinstance(updates[key], bool):
                raise ValueError("백업에서 첨부 빼기는 예/아니오(true/false)로 보내야 합니다.")
            current[key] = updates[key]
        elif key == "report_weekday":
            current[key] = validate_report_weekday(updates[key])
        elif key == "backup_dir":
            from . import backup as backup_service

            current[key] = backup_service.validate_dir(str(updates[key] or ""))
        elif key in ("backup_keep", "backup_every_hours"):
            current[key] = _positive_int(key, updates[key])
        elif key == "effect_confirm_over":
            current[key] = validate_effect_confirm_over(updates[key])
        elif key == "project_code":
            current[key] = validate_project_code(str(updates[key]))
        elif key in ("backup_keep_weekly", "backup_keep_monthly"):
            # 층은 0 이 될 수 있다 — "주 단위는 안 쓴다" 는 뜻이다 (TODO 119).
            current[key] = _zero_or_more(key, updates[key])
        elif key == "project_types":
            current[key] = validate_project_types(updates[key])
        elif key == "classifications":
            current[key] = validate_classifications(updates[key])
        elif key in ("intake_stale_days", "meeting_cycle_days"):
            current[key] = _positive_int(key, updates[key])
        elif key == "meeting_kinds":
            current[key] = validate_meeting_kinds(updates[key])
        elif key == "precheck_items":
            from . import precheck

            # 빈 글·빈 목록은 "기본 목록으로" — 고를 것 없는 체크리스트는 체크리스트가 아니다
            value = updates[key]
            current[key] = None if (isinstance(value, (str, list)) and not value) else precheck.validate_items(value)
        elif key == "precheck_thresholds":
            from . import precheck

            current[key] = precheck.validate_thresholds(check_thresholds(updates[key]))
        elif key == "entry_templates":
            # 빈 서식은 저장하지 않는다 — 비우면 "기본 서식으로 되돌린다"는 뜻이다.
            current[key] = {
                str(k): str(v) for k, v in dict(updates[key]).items() if str(v).strip()
            }
        else:
            current[key] = updates[key]
    write_atomic(_path(), json.dumps(current, ensure_ascii=False, indent=2) + "\n")
    return current


def write_atomic(path, text: str) -> None:
    """임시 파일에 다 쓴 뒤 `os.replace` 로 바꿔 끼운다 (TODO 202 ㉓).

    통째로 `write_text` 하다 도중에 꺼지면 **반쯤 쓴 settings.json** 이 남아, 다음 실행에서 명부 · 백업 폴더 ·
    서식이 전부 기본값이 됐다. replace 는 같은 폴더 안에서 한 번에 일어난다 — 옛 파일이든 새 파일이든 온전한 것만 남는다.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with open(temp, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    except BaseException:
        try:
            temp.unlink()
        except OSError:
            pass
        raise


def check_thresholds(value: Any) -> list[float]:
    """사전점검 기준 — 숫자 둘, 0~100, [착수 권장 ≥ 보완 필요] (TODO 205 ㉞). 파이썬 내부 문구 대신 한글로."""
    shape = "사전점검 기준은 [착수 권장, 보완 필요] 두 숫자여야 합니다 (예: 80, 60)."
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(shape)
    numbers: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)) or item != item or item in (float("inf"), float("-inf")):
            raise ValueError(shape)
        if not 0 <= item <= 100:
            raise ValueError(f"사전점검 기준은 0부터 100 사이여야 합니다 (받은 값: {item}).")
        numbers.append(item)
    if numbers[0] < numbers[1]:
        raise ValueError(f"착수 권장 기준({numbers[0]})이 보완 필요 기준({numbers[1]})보다 낮을 수 없습니다.")
    return numbers


def check_people(value: Any) -> None:
    """화면 · API 로 보낸 명부의 검사 (TODO 205 ㉞). 빈 이름 줄은 지금처럼 버린다(새 줄을 비워 둔 것).

    TODO 214 — 새 이름은 사람 이름 규칙(F6) · 같은 사번 둘은 막음(D10) · 떠난 사유는 고를 수 있는 것만.
    이미 명부에 있던 이름은 규칙을 다시 따지지 않는다 — 예전 표기 하나 때문에 명부 전체를 저장 못 하면 안 된다
    ([다른 이름으로 통일] 로 고치면 된다).
    """
    if not isinstance(value, list):
        raise ValueError("명부는 목록으로 보내야 합니다.")
    stored = {person["name"] for person in normalize_people(load()["people"])}
    seen: set[str] = set()
    ids: dict[str, str] = {}
    for raw in value:
        item = raw if isinstance(raw, dict) else {"name": raw}
        name = rules.clean_text(item.get("name"))
        if not name:
            continue
        if name not in stored:
            name = person_name(name)
        if name in seen:
            raise ValueError(f"명부에 같은 이름이 둘 있습니다: {name}")
        seen.add(name)
        try:
            rules.strict_day(item.get("left_on"), "left_on")
        except ValueError as exc:
            # 예전에는 `left_on: "x"` 가 **조용히 지워졌다** — 떠난 사람이 지금 있는 사람으로 돌아갔다
            raise ValueError(f"{name}: {exc}") from exc
        reason = rules.clean_text(item.get("left_reason"))
        if reason and reason not in LEFT_REASONS:
            # 예전에는 말없이 비웠다 (TODO 214)
            raise ValueError(f"{name}: 떠난 사유는 {' · '.join(LEFT_REASONS)} 중 하나입니다 (받은 값: {reason[:20]})")
        employee_id = rules.clean_text(item.get("employee_id"))
        if employee_id:
            if employee_id in ids:
                raise ValueError(f"같은 사번({employee_id})이 두 사람에게 있습니다: {ids[employee_id]} · {name}")
            ids[employee_id] = name


# 사람 이름 하나 (TODO 214 F6 · D14) — 명부 · 면담 · 역량 · [다른 이름으로 통일] · [넘기기] 가 같은 규칙.
PERSON_NAME_MAX = 40


def person_name(value: object, field: str = "person") -> str:
    """앞뒤 공백을 걷고, 경로 기호(`/` `\\` `..`) · 줄바꿈 · 쉼표 · 40자 넘는 이름은 400.

    쉼표가 든 이름(`"가, 나"`)은 담당 · 유관부서 칸에서 두 사람으로 갈라져 한 사람으로 굳지 못한다.
    """
    name = rules.plain_name(value, field)
    if not name:
        raise ValueError("이름을 입력하세요.")
    if "," in name or ";" in name:
        raise ValueError(f"이름에는 쉼표(,)를 쓸 수 없습니다 — 한 사람씩 적어 주세요 (받은 값: {name[:40]})")
    if len(name) > PERSON_NAME_MAX:
        raise ValueError(f"이름은 {PERSON_NAME_MAX}자까지입니다 (받은 값: {name[:20]}…)")
    return name


# ── 팀원 면담 (TODO 182) ────────────────────

DEFAULT_MEETING_KINDS = ["정기", "목표 설정", "중간 점검", "수시", "고충"]


def meeting_kinds() -> list[str]:
    stored = load().get("meeting_kinds")
    return list(stored) if isinstance(stored, list) and stored else list(DEFAULT_MEETING_KINDS)


def validate_meeting_kinds(value: Any) -> list[str] | None:
    """줄바꿈 · 쉼표로 적어 보내도 받는다. 비우면 기본 목록으로(null)."""
    items = value if isinstance(value, list) else str(value or "").replace(",", "\n").splitlines()
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        if len(text) > CLASSIFICATION_MAX_LEN:
            raise ValueError(f"면담 구분은 {CLASSIFICATION_MAX_LEN}자까지입니다: {text}")
        if text not in out:
            out.append(text)
    if len(out) > CLASSIFICATION_MAX_ITEMS:
        raise ValueError(f"면담 구분은 {CLASSIFICATION_MAX_ITEMS}개까지입니다.")
    return out or None


def meeting_cycle_days() -> int:
    try:
        return max(1, int(load()["meeting_cycle_days"]))
    except (TypeError, ValueError):
        return int(DEFAULTS["meeting_cycle_days"])


def current_author(explicit: str | None = None) -> str:
    """요청이 작성자를 지정했으면 그것을, 아니면 설정값을 쓴다.

    로그인이 생기면 explicit 자리에 로그인 사용자가 들어온다.
    """
    # TODO 214 F13 — 요청이 보낸 작성자도 작성자 규칙(한 줄 · 40자)을 거친다. 틀리면 ValueError → 400
    text = rules.clean_author(explicit) if explicit else ""
    if text:
        return text
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


# ── 과제 분류 넷 · 접수 (TODO 136) ────────────────────

CLASSIFICATION_MAX_ITEMS = 20
CLASSIFICATION_MAX_LEN = 30


def classifications() -> dict[str, list[str]]:
    """분류 넷의 목록. 정한 적이 없거나 한 칸만 빠져 있으면 그 칸은 기본 목록을 쓴다."""
    from ..config import CLASSIFICATIONS

    stored = load().get("classifications")
    stored = stored if isinstance(stored, dict) else {}
    out: dict[str, list[str]] = {}
    for key, _, defaults in CLASSIFICATIONS:
        items = stored.get(key)
        out[key] = list(items) if isinstance(items, list) and items else list(defaults)
    return out


def validate_classifications(value: Any) -> dict[str, list[str]]:
    """목록을 정리한다. 한 칸에 줄바꿈으로 적어 보내도 받는다. 빈 줄·겹치는 값은 버린다.

    **빈 목록은 받지 않는다** — 고를 것이 없는 칸은 칸이 아니다. 쓰지 않을 칸이면 비워 두면
    되고(값은 선택), 목록 자체를 지우려 하면 기본 목록으로 되돌린다.
    """
    from ..config import CLASSIFICATIONS, CLASSIFICATION_LABELS

    if not isinstance(value, dict):
        raise ValueError("분류 목록 형식이 올바르지 않습니다.")
    out: dict[str, list[str]] = {}
    for key, _, defaults in CLASSIFICATIONS:
        raw = value.get(key)
        if raw is None:
            continue
        if isinstance(raw, str):
            raw = raw.splitlines()
        items: list[str] = []
        for item in raw:
            text = " ".join(str(item).split())
            if not text or text in items:
                continue
            if len(text) > CLASSIFICATION_MAX_LEN:
                raise ValueError(
                    f"{CLASSIFICATION_LABELS[key]}: '{text[:12]}…' 이 너무 깁니다 "
                    f"({CLASSIFICATION_MAX_LEN}자 이하)."
                )
            items.append(text)
        if len(items) > CLASSIFICATION_MAX_ITEMS:
            raise ValueError(
                f"{CLASSIFICATION_LABELS[key]}: 항목은 {CLASSIFICATION_MAX_ITEMS}개까지입니다."
            )
        out[key] = items or list(defaults)
    return out


def intake_template() -> str:
    """접수 본문 서식. 비워 두면 기본 서식."""
    from . import intakes

    return str(load()["intake_template"]).strip() or intakes.DEFAULT_TEMPLATE


def intake_stale_days() -> int:
    try:
        return max(1, int(load()["intake_stale_days"]))
    except (TypeError, ValueError):
        return int(DEFAULTS["intake_stale_days"])


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

    사번 칸은 지금 비어 있는 것이 정상이다 — 로그인이 생길 때 채운다.
    `account` 는 **화면에서 뺐지만**(TODO 126) 값은 그대로 읽고 쓴다 — 사내 인증 연동을
    하게 되면 칸만 되살리면 된다.
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
                # 떠난 날 (TODO 122). 비어 있으면 지금 있는 사람이다.
                # **지우지 않고 날짜를 적는다** — 그해에 그 사람이 한 일은 사실이므로
                # 명부에서 지우면 지난 성과가 "명부에 없는 이름" 이 되어 오타와 뒤섞인다.
                "left_on": _left_on(item.get("left_on")),
                "left_reason": _left_reason(item.get("left_reason")),
            }
        )
    # 떠난 사람은 아래로. 자동완성·고르기에서 지금 있는 사람이 먼저 보여야 한다.
    people.sort(key=lambda person: (has_left(person), person["name"]))
    return people


LEFT_REASONS = ("전배", "퇴사")


def _left_on(value: object) -> str:
    """떠난 날. `YYYY-MM-DD` 가 아니면 비운 것으로 본다 (손으로 고친 파일 대비)."""
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        from datetime import date

        date.fromisoformat(text)
    except ValueError:
        return ""
    return text


def _left_reason(value: object) -> str:
    text = str(value or "").strip()
    return text if text in LEFT_REASONS else ""


def people() -> list[dict[str, str]]:
    return normalize_people(load()["people"])


def has_left(person: dict[str, Any], today: str | None = None) -> bool:
    """떠났는가 (TODO 214 D8) — 떠난 날이 **오늘이거나 지났을 때만.** 미래 날짜(전배 예정)는 그날까지 지금 있는 사람이다.

    예전에는 적는 즉시 떠난 사람이 되어, 다음 달 전배 예정자가 승격 · 면담에서 엇갈렸다.
    """
    left_on = str(person.get("left_on") or "")
    if not left_on:
        return False
    from datetime import date

    return left_on <= (today or clock.today().isoformat())


def known_names(include_left: bool = True) -> list[str]:
    """명부의 이름. `include_left=False` 면 **지금 있는 사람만** (자동완성용, TODO 122)."""
    return [p["name"] for p in people() if include_left or not has_left(p)]


def active_names() -> set[str]:
    """지금 있는 사람(떠난 날이 없거나 아직 오지 않은 사람)의 이름 (TODO 214 D8)."""
    return {p["name"] for p in people() if not has_left(p)}


def left_people() -> list[dict[str, str]]:
    """떠난 사람만 — 떠난 날이 오늘이거나 지난 사람 (TODO 214 D8). 화면의 딱지와 홈의 알림이 이것을 본다."""
    return [person for person in people() if has_left(person)]


def roster_warnings(names: list[str], *, departed: bool = True) -> list[str]:
    """명부에 없는 이름 · 떠난 사람 — 막지 않고 알린다 (TODO 214 D6 · D7). 면담 · 역량 · 승격이 같은 문구."""
    roster = {person["name"]: person for person in people()}
    out: list[str] = []
    for name in names:
        person = roster.get(name)
        if person is None:
            out.append(f"명부에 없는 이름입니다: {name}")
        elif departed and has_left(person):
            out.append(f"떠난 사람입니다: {name}")
    return out


def add_person(name: str) -> list[dict[str, str]]:
    """명부에 없는 이름을 그 자리에서 추가한다 (화면에서 물어본 뒤 부른다)."""
    name = person_name(name)  # 경로 기호 · 쉼표 · 40자 (TODO 214 F6)
    current = people()
    if any(person["name"] == name for person in current):
        return current
    current.append({"name": name, "employee_id": "", "account": "", "left_on": "", "left_reason": ""})
    return save({"people": current})["people"]


# ── 과제 번호 코드 ────────────────────────────────────

def project_code() -> str:
    """과제 번호에 넣을 팀·부문 코드. 비어 있으면 번호는 지금 형태 그대로다.

    손으로 고친 설정 파일의 틀린 코드는 load() 가 빈 코드로 읽고 `unreadable` 에 적는다 (TODO 214 F3).
    """
    return str(load()["project_code"]).strip()


# 팀 코드는 **그대로 폴더 이름에 들어간다** (`2026-소재-001-제목`).
# 과제명은 슬러그로 다듬어지지만 코드는 다듬지 않으므로, 여기서 막지 않으면
# 윈도우에서 폴더를 아예 만들지 못하는 이름이 된다.
_CODE_FORBIDDEN = '/\\:*?"<>| \t\r\n'
MAX_CODE_LEN = 20


# TODO 214 D16 — 한글 · 영문 · 숫자만. `팀-2` 는 번호 분해(renumber.split_id)가 `-숫자` 를 일련번호로 잘못 읽고,
# `&` · `#` 은 임시 보관 열쇠 · 주소에서 늘 실패했다. 사용자 확인: 지금 쓰는 팀 코드에 특수문자 없음.
_CODE_SHAPE = __import__("re").compile(r"[가-힣A-Za-z0-9]+")


def validate_project_code(code: str) -> str:
    """과제 번호에 쓸 팀 코드를 검사한다 — 한글 · 영문 · 숫자 1~20자, 숫자만은 안 됨 (TODO 214 D16).

    막는 것:
      · 숫자만  — 일련번호와 구분되지 않는다
      · 한글 · 영문 · 숫자 밖의 글자 — 폴더 이름 · 번호 분해 · 주소가 깨진다
      · 너무 긴 것 — 폴더 이름이 길어져 윈도우 260자 경로 제한에 걸린다
    """
    code = (code or "").strip()
    if not code:
        return ""
    if code.isdigit():
        raise ValueError("팀 코드는 숫자만으로 지을 수 없습니다. 일련번호와 구분되지 않습니다.")
    if not _CODE_SHAPE.fullmatch(code):
        bad = sorted({ch for ch in code if not _CODE_SHAPE.fullmatch(ch)})
        shown = " ".join("공백" if not ch.strip() else ch for ch in bad)
        raise ValueError(f"팀 코드에 쓸 수 없는 문자가 있습니다: {shown} — 한글 · 영문 · 숫자만 쓸 수 있습니다.")
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


# 숫자 칸의 한글 이름 — 화면의 칸 이름과 같다 (TODO 214 F12: 묵힘 기준 · 면담 주기에 영문 키가 그대로 나왔다).
LABELS = {
    "backup_keep": "일 단위로 남길 백업 수",
    "backup_keep_weekly": "주 단위로 남길 백업 수",
    "backup_keep_monthly": "달 단위로 남길 백업 수",
    "backup_every_hours": "백업 주기(시간)",
    "intake_stale_days": "묵힘 기준일",
    "meeting_cycle_days": "면담 주기(일)",
    "effect_confirm_over": "효과 금액 확인 기준(억원/년)",
}
NUMBER_LIMIT = 999


def _label(key: str) -> str:
    return LABELS.get(key) or rules.field_label(key)


def _whole_number(key: str, value: object) -> int:
    """정수 하나. 비운 값 · 글자 · 소수는 한글 칸 이름으로 400 (TODO 214 F12)."""
    label = _label(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{josa_of(label, '을를')} 비울 수 없습니다 — 숫자를 적어 주세요.")
    if isinstance(value, bool):
        raise ValueError(f"{josa_of(label, '은는')} 숫자여야 합니다.")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{josa_of(label, '은는')} 소수 없이 정수로 적어 주세요.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{josa_of(label, '은는')} 숫자여야 합니다 (받은 값: {str(value)[:20]}).") from exc


def josa_of(word: str, pair: str) -> str:
    """괄호로 끝나는 이름(`백업 주기(시간)`)은 괄호 앞 글자로 조사를 고른다."""
    head = word.rstrip(")").rsplit("(", 1)[0] if word.endswith(")") else word
    return word + rules.josa(head, pair)[len(head):]


def _zero_or_more(key: str, value: object) -> int:
    number = _whole_number(key, value)
    if number < 0:
        raise ValueError(f"{josa_of(_label(key), '은는')} 0 이상이어야 합니다.")
    if number > NUMBER_LIMIT:
        # TODO 214 F14 — 주 · 달 단위 백업 수에 상한이 없었다(1e300 을 받았다)
        raise ValueError(f"{josa_of(_label(key), '은는')} {NUMBER_LIMIT} 이하로 적어 주세요.")
    return number


def _positive_int(key: str, value: object) -> int:
    number = _whole_number(key, value)
    if number < 1:
        # 0 은 "끔" 이 아니다 — 비우거나 0 으로 두면 이 문구 (TODO 214 F12)
        raise ValueError(f"{josa_of(_label(key), '은는')} 1 이상이어야 합니다.")
    if number > NUMBER_LIMIT:
        raise ValueError(f"{josa_of(_label(key), '은는')} {NUMBER_LIMIT} 이하로 적어 주세요.")
    return number


def _confirm_over_ok(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return value == value and 0 <= value <= rules.NUMBER_MAX


def validate_effect_confirm_over(value: object) -> float | int:
    """효과 금액 확인 기준 (TODO 214 D4) — 0 이상의 숫자(억원/년). 0 은 "묻지 않음"."""
    label = _label("effect_confirm_over")
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{josa_of(label, '을를')} 비울 수 없습니다 — 묻지 않으려면 0 을 적어 주세요.")
    if isinstance(value, bool):
        raise ValueError(f"{josa_of(label, '은는')} 숫자여야 합니다.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{josa_of(label, '은는')} 숫자여야 합니다 (받은 값: {str(value)[:20]}).") from exc
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{josa_of(label, '은는')} 숫자여야 합니다.")
    if number < 0:
        raise ValueError(f"{josa_of(label, '은는')} 0 이상이어야 합니다 (0 은 묻지 않음).")
    if number > rules.NUMBER_MAX:
        raise ValueError(f"{josa_of(label, '이가')} 너무 큽니다 (최대 {rules.NUMBER_MAX:,.0f}).")
    return int(number) if number.is_integer() else number


def effect_confirm_over() -> float | int:
    value = load()["effect_confirm_over"]
    return value if _confirm_over_ok(value) else DEFAULTS["effect_confirm_over"]


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
    # 빈 목록은 **정한 값**이다 — 속성을 아예 안 쓰는 팀(TODO 100, 사용자 결정). 205 에서 막자는 안이 나왔으나 그 결정을 따른다.
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
        # 열쇠는 과제 파일 · 주소에 그대로 들어간다 — 경로 기호 · 공백은 받지 않는다 (TODO 205 ㉞)
        if any(mark in key for mark in ("/", "\\", "..")) or any(ch.isspace() for ch in key):
            raise ValueError(f"속성 열쇠에는 / \\ .. 와 공백을 쓸 수 없습니다: {key}")
        if key in keys:
            raise ValueError(f"같은 열쇠의 속성이 둘 있습니다: {key}")
        keys.add(key)
        found.append({"key": key, "label": label})
    return found
