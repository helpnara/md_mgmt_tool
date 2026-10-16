from __future__ import annotations

import math as _math
import re as _re
from datetime import date as _date
from typing import Any

from pydantic import BaseModel, Field

from .vault.paths import InvalidDateError


class PartnerIn(BaseModel):
    """유관부서 한 줄 (TODO 92).

    `people` 은 `"김철수, 박민수"` 한 칸으로 와도 되고 목록으로 와도 된다 —
    나누는 일은 서비스가 맡는다(normalize_partners). 화면만 고쳐서는 API 를 직접
    부르는 길로 같은 사고가 다시 나기 때문이다 (TODO 74).
    """

    team: str
    people: list[str] | str = Field(default_factory=list)


class ProjectCreate(BaseModel):
    title: str
    status: str | None = None
    type: str | None = None
    group: str | None = None
    owners: list[str] = Field(default_factory=list)
    # 함께 일하는 팀과 그쪽 담당자. 팀도 여럿, 팀마다 사람도 여럿일 수 있다.
    partners: list[PartnerIn] = Field(default_factory=list)
    start_date: str | None = None
    due_date: str | None = None
    # 완료일 (TODO 104). 완료 상태로 만들면 오늘이 기본, 지난 과제면 손으로 적는다.
    completed_at: str | None = None
    # 과제 효과 (억원/년). 기대효과는 착수 시, 실증효과는 끝난 뒤 채운다.
    effect_expected: float | None = None
    effect_verified: float | None = None
    # 별도 보고가 필요 없는 과제 (단순 현황 관리). 보고 대상 후보에서만 빠진다.
    no_report: bool = False
    # 효과 금액으로 관리하지 않는 과제 (TODO 125)
    no_effect: bool = False
    # 비우면 설정의 작성자를 쓴다 (로그인이 생기면 로그인 사용자).
    created_by: str | None = None
    tags: list[str] = Field(default_factory=list)
    body: str | None = None
    # 과제 분류 넷 (TODO 136) — 성격 · 분류 · 수행 방식 · 비용구분
    nature: str | None = None
    category: str | None = None
    delivery: str | None = None
    cost_kind: str | None = None
    # 선행 과제 번호들 — 다년도 과제의 앞 단계, 여럿일 수 있다 (TODO 172)
    predecessors: list[str] = Field(default_factory=list)


class ProjectUpdate(BaseModel):
    title: str | None = None
    status: str | None = None
    type: str | None = None
    group: str | None = None
    owners: list[str] | None = None
    partners: list[PartnerIn] | None = None
    start_date: str | None = None
    due_date: str | None = None
    completed_at: str | None = None
    effect_expected: float | None = None
    effect_verified: float | None = None
    no_report: bool | None = None
    no_effect: bool | None = None
    tags: list[str] | None = None
    body: str | None = None
    nature: str | None = None
    category: str | None = None
    delivery: str | None = None
    cost_kind: str | None = None
    # 선행 과제들 (TODO 172). [] 을 보내면 모두 끊는다.
    predecessors: list[str] | None = None

    def changes(self) -> dict[str, Any]:
        # 보내지 않은 항목만 건너뛴다. 보낸 값이 null 이면 그 항목을 비우겠다는 뜻이다
        # (효과 금액을 지우려면 이 구분이 반드시 필요하다).
        return self.model_dump(exclude_unset=True)


class EntryCreate(BaseModel):
    date: str | None = None
    title: str | None = None
    body: str | None = None
    author: str | None = None  # 비우면 설정의 작성자를 쓴다
    tags: list[str] = Field(default_factory=list)


class EntryUpdate(BaseModel):
    date: str | None = None
    title: str | None = None
    body: str | None = None
    tags: list[str] | None = None

    def changes(self) -> dict[str, Any]:
        return {k: v for k, v in self.model_dump().items() if v is not None}


# ══ 입력 검증 — 한 곳 (TODO 205) ════════════════════════════════════════════════
#
# 날짜 · 기간 · 제목 · 숫자 · 목록 · 이름의 규칙이 서비스마다 조금씩 달랐다. `start_date: "2026-13-01"` 이
# 201 로 받아져 **파일에 원문이 남고** 재색인마다 경고가 났는데, 같은 요청의 `completed_at` 은 400 이었다.
# 생성 · 수정 · 승격이 모두 여기 규칙을 부른다. 거절은 ValueError(날짜는 InvalidDateError) — 라우터가 400 으로 돌린다.
# 모델 단의 pydantic 검사(422)가 아니라 서비스가 부르는 함수로 둔 것은 승격처럼 **서비스끼리 부르는 길**도
# 같은 규칙을 거치게 하려는 것이다.

# 화면에 보이는 칸 이름. 400 문구와 422 처리기(main.py)가 함께 쓴다.
FIELD_LABELS: dict[str, str] = {
    "title": "과제명",
    "status": "상태",
    "type": "속성",
    "group": "그룹",
    "owners": "담당자",
    "partners": "유관부서",
    "team": "팀",
    "start_date": "시작일",
    "due_date": "마감일",
    "completed_at": "완료일",
    "effect_expected": "기대효과",
    "effect_verified": "실증효과",
    "effect_request": "요청 효과",
    "effect": "효과 금액",
    "no_report": "보고 제외",
    "no_effect": "효과 관리 안 함",
    "tags": "태그",
    "body": "본문",
    "predecessors": "선행 과제",
    "date": "날짜",
    "entry_title": "진행일지 제목",
    "report_date": "보고일",
    "audience": "피보고자",
    "created_by": "등록자",
    "end_date": "종료일",
    "next_date": "다음 면담일",
    "received_on": "접수일",
    "decided_on": "판정일",
    "left_on": "떠난 날",
    "left_reason": "떠난 사유",
    "person": "사람",
    "people": "명부",
    "name": "이름",
    "author": "작성자",
    "hours": "시간",
    "cost": "비용",
    "kind": "구분",
    "summary": "한 줄 요약",
    "followups": "하기로 한 것",
    "report_weekday": "보고 요일",
    "precheck_thresholds": "사전점검 기준",
    "precheck_items": "사전점검 항목",
    "project_types": "과제 속성",
    "types": "과제 속성",
    "key": "열쇠",
    "label": "이름",
    "backup_dir": "백업 폴더",
    "backup_keep": "일 단위로 남길 백업 수",
    "backup_keep_weekly": "주 단위로 남길 백업 수",
    "backup_keep_monthly": "달 단위로 남길 백업 수",
    "backup_every_hours": "백업 주기(시간)",
    "backup_skip_assets": "백업에서 첨부 빼기",
    "intake_stale_days": "묵힘 기준일",
    "meeting_cycle_days": "면담 주기",
    "meeting_kinds": "면담 구분",
    "classifications": "분류 목록",
    "entry_templates": "진행일지 서식",
    "project_code": "팀 코드",
    "priority": "중요도",
    "leader": "요청자",
    "leader_team": "요청 팀",
    "picked": "후보",
    "nature": "성격",
    "category": "분류",
    "delivery": "수행 방식",
    "cost_kind": "비용구분",
}


def field_label(field: str) -> str:
    return FIELD_LABELS.get(field, field)


def josa(word: str, pair: str = "은는") -> str:
    """받침에 맞는 조사 — `시작일은` · `마감일은` · `날짜는`. 한글이 아니면 앞쪽(은/이)."""
    last = (word or " ")[-1]
    if "가" <= last <= "힣":
        has_final = (ord(last) - 0xAC00) % 28 != 0
        return word + (pair[0] if has_final else pair[1])
    return word + pair[0]


def _shown(value: object) -> str:
    text = str(value)
    return text if len(text) <= 40 else text[:40] + "…"


# 숫자 넷-둘-둘. `date.fromisoformat` 만으로는 `20260101` · `2026-W01` 까지 받아 버린다(3.11).
_DAY_SHAPE = _re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


# 받는 날짜의 연도 (TODO 214 D5) — `9999-12-31` 진행일지 하나가 "최근 갱신" 을 영영 고정했고, `0025-01-01` 은
# 없는 연도의 번호를 만들 뻔했다. 모든 날짜 칸이 이 함수를 거치므로 한 곳에서 막는다.
DAY_MIN_YEAR = 2000
DAY_MAX_YEAR = 2100


def strict_day(value: object, field: str, *, default: str | None = None) -> str | None:
    """`YYYY-MM-DD` 의 **실제 있는 날**만 (TODO 205 ⑯), 연도는 2000~2100 (TODO 214 D5).

    `2026-13-01` · `2026/01/01` · `2026-02-30` · `2026-1-1` · `2026-01-01T00:00:00` 은 400 — 파일에 원문을 적지 않는다.
    비우면(None · "" · 공백) `default` — 비울 수 있는 칸은 None, 진행일지처럼 오늘이 기본인 칸은 오늘.
    """
    if value is None:
        return default
    if isinstance(value, _date) and not hasattr(value, "hour"):
        return _in_range(value, field, value.isoformat())
    text = str(value).strip()
    if not text:
        return default
    if _DAY_SHAPE.fullmatch(text):
        try:
            day = _date.fromisoformat(text)
        except ValueError:
            pass
        else:
            return _in_range(day, field, text)
    raise InvalidDateError(f"{josa(field_label(field))} 2026-03-01 처럼 적어 주세요 (받은 값: {_shown(text)})")


def _in_range(day: _date, field: str, text: str) -> str:
    if not DAY_MIN_YEAR <= day.year <= DAY_MAX_YEAR:
        raise InvalidDateError(
            f"{josa(field_label(field))} {DAY_MIN_YEAR}~{DAY_MAX_YEAR}년 사이여야 합니다 (받은 값: {_shown(text)})"
        )
    return day.isoformat()


def check_period(start: object, end: object, start_field: str, end_field: str) -> None:
    """기간이 거꾸로면 400 — 시작 ≤ 끝 (TODO 205 ㉞). 한쪽이라도 비면 따지지 않는다."""
    if start and end and str(end) < str(start):
        raise ValueError(
            f"{josa(field_label(end_field), '이가')} {field_label(start_field)}보다 빠릅니다 ({start} → {end})."
        )


def clean_text(value: object) -> str:
    """앞뒤 공백을 걷는다. 공백뿐이면 빈 글 (TODO 205 ⑰ ⑱)."""
    return str(value if value is not None else "").strip()


def require_title(value: object, message: str = "과제명을 입력하세요.") -> str:
    """제목은 비울 수 없다 — 생성과 수정이 같은 규칙 (TODO 205 ⑱). 공백뿐인 것도 빈 것이다."""
    title = clean_text(value)
    if not title:
        raise ValueError(message)
    return title


# ── 길이 · 한 줄 (TODO 214 D14) ─────────────────────────────────────────────
# 과제명은 제한이 없고 접수는 200자에서 말없이 잘랐다 — 화면마다 달랐다. 같은 상한을 둔다.
# 이미 있는 긴 값은 **그 칸을 고칠 때만** 따진다(다른 칸을 저장하다 막히지 않게) — 부르는 쪽이 정한다.
TITLE_MAX = 100
GROUP_MAX = 40
BODY_MAX = 2_000_000

# 제어문자 — 제목 · 그룹은 줄바꿈 · 탭도 받지 않는다. 본문은 줄바꿈 · 탭(과 \r \v \f)만 받는다.
_CONTROL = _re.compile(r"[\x00-\x1f\x7f]")
_BODY_CONTROL = _re.compile(r"[\x00-\x08\x0e-\x1f\x7f]")


def one_line(value: object, field: str, maximum: int) -> str:
    """한 줄 글 — 앞뒤 공백을 걷고, 줄바꿈 · 제어문자는 400, `maximum` 자를 넘으면 400 (TODO 214 D14)."""
    text = clean_text(value)
    if _CONTROL.search(text):
        raise ValueError(f"{field_label(field)}에는 줄바꿈 · 제어문자를 넣을 수 없습니다.")
    if len(text) > maximum:
        raise ValueError(f"{josa(field_label(field))} {maximum}자까지입니다 (지금 {len(text)}자).")
    return text


def check_body(value: object, field: str = "body") -> str | None:
    """본문 — 2,000,000자까지, 줄바꿈 · 탭 밖의 제어문자(NUL 등)는 400 (TODO 214 D14). None 은 그대로."""
    if value is None:
        return None
    text = str(value)
    if len(text) > BODY_MAX:
        raise ValueError(f"{josa(field_label(field))} {BODY_MAX:,}자까지입니다 (지금 {len(text):,}자).")
    if _BODY_CONTROL.search(text):
        raise ValueError(f"{field_label(field)}에 쓸 수 없는 제어문자가 들어 있습니다.")
    return text


def clean_tag(value: object) -> str:
    """태그 하나의 표기 (TODO 214 D12) — 앞의 `#` 를 떼고 겹친 공백을 하나로."""
    return " ".join(str(value or "").strip().lstrip("#").split())


def tag_key(value: object) -> str:
    """같은 태그인가를 가르는 열쇠 (TODO 214 D12) — 대소문자 · 띄어쓰기 · 앞의 `#` 를 무시한다."""
    return "".join(clean_tag(value).split()).casefold()


# 효과 금액의 위쪽 한계 (억원/년). 100조 원/년 — 이보다 크면 단위를 잘못 적은 것이다. 합계가 무한대로
# 넘쳐 JSON 으로 못 적는 일(500)도 이 선에서 막힌다 (TODO 205 ㉞).
NUMBER_MAX = 1_000_000.0


def finite_number(value: object, field: str, *, maximum: float | None = NUMBER_MAX) -> float | None:
    """숫자 칸. 비우면 None, NaN · 무한대 · 음수 · 지나치게 큰 값은 400 (TODO 205 ㉞).

    NaN 이 그대로 파일에 `.nan` 으로 적혀 다시 읽을 때마다 어긋났다.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{josa(field_label(field))} 숫자로 적어 주세요 (받은 값: {value})")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{josa(field_label(field))} 숫자로 적어 주세요 (받은 값: {_shown(value)})") from exc
    if not _math.isfinite(number):
        raise ValueError(f"{josa(field_label(field))} 숫자로 적어 주세요 — 무한대 · NaN 은 받지 않습니다.")
    if number < 0:
        raise ValueError(f"{josa(field_label(field))} 0보다 작을 수 없습니다.")
    if maximum is not None and number > maximum:
        raise ValueError(f"{josa(field_label(field), '이가')} 너무 큽니다 (최대 {maximum:,.0f}) — 단위를 확인하세요.")
    return number


def split_list(value: object) -> list[str]:
    """담당자 · 태그 — **같은 규칙** (TODO 205 ㉞). 쉼표로 나누고, 앞뒤·겹친 공백을 정리하고, 빈 것과 겹친 것은 버린다(순서 유지).

    예전에는 담당자는 쉼표를 나누고 태그는 안 나눠, `"a, b"` 가 담당자로는 둘 · 태그로는 하나였다.
    화면(ProjectForm · EntryEditor · IntakeForm)은 이미 쉼표로 나눠 보내므로 그대로 맞는다.
    """
    if not value:
        return []
    items = [value] if isinstance(value, str) else list(value) if isinstance(value, (list, tuple)) else [value]
    out: list[str] = []
    for item in items:
        if item is None:
            continue
        for part in str(item).split(","):
            text = " ".join(part.split())
            if text and text not in out:
                out.append(text)
    return out


_NAME_FORBIDDEN = ("/", "\\", "..")


def plain_name(value: object, field: str = "person") -> str:
    """사람 이름 하나 — 경로 기호(`/` `\\` `..`)와 줄바꿈은 받지 않는다 (TODO 205 ㉞).

    면담 `person: "../x"` 가 `people/x/` 폴더로 들어가고 이름은 `../x` 로 남았다.
    """
    name = clean_text(value)
    if any(mark in name for mark in _NAME_FORBIDDEN) or any(ch in name for ch in "\r\n\t\x00"):
        raise ValueError(f"{field_label(field)} 이름에는 / \\ .. 와 줄바꿈을 쓸 수 없습니다 (받은 값: {_shown(name)})")
    return name


AUTHOR_MAX = 40


def clean_author(value: object) -> str:
    """작성자 — 줄바꿈 없이 40자까지, 앞뒤 공백은 걷는다 (TODO 205 ㉞). 비우는 것은 된다."""
    text = clean_text(value)
    if "\n" in text or "\r" in text:
        raise ValueError("작성자에는 줄바꿈을 넣을 수 없습니다.")
    if len(text) > AUTHOR_MAX:
        raise ValueError(f"작성자는 {AUTHOR_MAX}자까지입니다.")
    return text
