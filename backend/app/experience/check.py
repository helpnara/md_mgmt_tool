"""경험 블록 하나의 검사 (TODO 256 · 데이터모델 4절).

정합성(X-01 ~ X-08)은 다른 경험 · 담당과 역할이 있어야 해서 4단계에서 본다. 여기서는 **블록 하나만 보고** 알 수 있는 것 —
상태별로 있어야 할 칸, 값의 모양(구분 · 기간 · 이어짐 · 형식 판), 확정 조건 1 ~ 4.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .parse import ParsedBlock
from .period import parse_period

STATUSES = ("초안", "구조화", "확정")
KINDS = ("업무", "업무 외")
FORMAT_VERSIONS = ("0.1",)
_EXPERIENCE_ID = re.compile(r"^E-\d{3,}$")


@dataclass
class Problem:
    code: str       # 짧은 이름 — 시험 · 화면이 이것으로 가른다
    field: str      # 어느 칸
    message: str    # 사람에게 보일 말
    level: str      # "오류"(그 상태로 둘 수 없다) · "경고"(알리기만)


def is_experience_id(text: str) -> bool:
    """`E-nnn` — 접두어 + 0 채움 숫자 셋 이상(데이터모델 2절 · 원본 5절)."""
    return bool(_EXPERIENCE_ID.match(text or ""))


def confirm_ready(block: ParsedBlock, person: str = "") -> list[str]:
    """확정 조건 1 ~ 4 중 못 맞춘 것(데이터모델 4절). 5(정합성 경고)는 4단계에서 더한다. 비면 확정할 수 있다."""
    reasons: list[str] = []
    missing = [name for name, value in (("제목", block.get("제목")), ("사람", person), ("역할", block.get("역할")), ("구분", block.get("구분"))) if not value.strip()]
    if missing:
        reasons.append(f"1. {' · '.join(missing)} 이(가) 비어 있습니다")
    filled = sum((bool(block.get("상황").strip()), bool(block.lists.get("행동")), bool(block.quants or block.get("결과_정성").strip())))
    if filled < 2:
        reasons.append("2. 상황 · 행동 · 결과(정량 또는 정성) 중 둘 이상이 있어야 합니다")
    if block.lists.get("확인_필요"):
        reasons.append(f"3. 확인 필요가 {len(block.lists['확인_필요'])}건 남았습니다 — 답하거나 지웁니다")
    unknown = [q.metric for q in block.quants if q.baseline_kind == "미확인"]
    if unknown:
        reasons.append(f"4. 기준 종류를 정하지 않은 정량 성과: {', '.join(unknown)}")
    return reasons


def check(block: ParsedBlock, status: str = "구조화", person: str = "") -> list[Problem]:
    """그 상태로 둘 수 있는지. 오류가 하나라도 있으면 그 상태로 저장하지 않는다(2단계에서 쓴다)."""
    problems: list[Problem] = []
    if status not in STATUSES:
        return [Problem("status", "상태", f"상태는 {' · '.join(STATUSES)} 중 하나입니다: {status}", "오류")]
    if block.version and block.version not in FORMAT_VERSIONS:
        problems.append(Problem("version", "형식", f"모르는 형식 판입니다: {block.version}", "경고"))
    if not block.get("제목").strip():
        problems.append(Problem("title", "제목", "제목이 비어 있습니다", "오류"))
    kind = block.get("구분").strip()
    if kind and kind not in KINDS:
        problems.append(Problem("kind", "구분", f"구분은 {' · '.join(KINDS)} 중 하나입니다: {kind}", "오류"))
    elif not kind and status != "초안":
        problems.append(Problem("kind", "구분", "구분이 비어 있습니다", "오류"))
    start, end, warnings = parse_period(block.get("기간"))
    for warning in warnings:
        problems.append(Problem("period", "기간", warning, "경고"))
    if block.get("기간") and not start:
        problems.append(Problem("period", "기간", "기간을 읽지 못해 연도를 정할 수 없습니다(정합성 X-07)", "경고"))
    if block.continues and not is_experience_id(block.continues.rstrip("?")):
        problems.append(Problem("continues", "이어짐", f"이어짐은 E-nnn 모양입니다: {block.continues}", "오류"))
    for quant in block.quants:
        for warning in quant.warnings:
            problems.append(Problem("quant", "결과_정량", f"{quant.metric}: {warning}", "경고"))
        if quant.ask:
            problems.append(Problem("baseline_ask", "결과_정량", f"{quant.metric}: 기준 '{quant.baseline}' 이 비교 기준인가요?(규칙 12)", "경고"))
    for bad in block.bad_lines:
        problems.append(Problem("bad_line", "", f"{bad.line}번 줄 — {bad.reason}: {bad.text.strip()}", "경고"))
    if block.unknown:
        problems.append(Problem("unknown_key", "", f"모르는 칸(미분류): {', '.join(block.unknown)}", "경고"))
    if status == "확정":
        for reason in confirm_ready(block, person):
            problems.append(Problem("confirm", "", reason, "오류"))
    return problems
