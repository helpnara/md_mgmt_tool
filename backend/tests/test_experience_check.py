"""경험 블록 검사 · 기간 읽기 (TODO 256 · 데이터모델 4절 · 1단계.md 4절 ④)."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.experience.check import check, confirm_ready, is_experience_id
from app.experience.parse import parse
from app.experience.period import parse_period

FIXTURES = Path(__file__).parent / "fixtures" / "experience"


def one(*lines: str):
    return parse("\n".join(("형식: slow-way-experience/0.1",) + lines)).blocks[0]


def codes(problems, level=None):
    return [p.code for p in problems if level is None or p.level == level]


# ── 기간 (④) ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text,start,end", [
    ("2026-03 ~ 2026-09", "2026-03", "2026-09"),
    ("2016 ~ 2017", "2016", "2017"),
    ("2026.03-2026.09", "2026-03", "2026-09"),
    ("2026/3 ~ 2026/11", "2026-03", "2026-11"),
    ("2026년 3월 ~ 9월", "2026-03", "2026-09"),
    ("2026년 3월 ~ 2027년 1월", "2026-03", "2027-01"),
    ("2025.04 2025.10", "2025-04", "2025-10"),          # 물결표 없음
    ("2024-02 ~ 현재", "2024-02", ""),
    ("2024-02 ~ 진행 중", "2024-02", ""),
    ("2026-06", "2026-06", "2026-06"),                  # 한 시점
    ("2026-2027", "2026", "2027"),                      # 2026-20 으로 읽지 않는다
    ("", "", ""),
])
def test_period_shapes(text, start, end):
    got_start, got_end, warnings = parse_period(text)
    assert (got_start, got_end) == (start, end) and warnings == []


@pytest.mark.parametrize("text,word", [("작년쯤", "읽지 못했"), ("2026-13 ~ 2026-14", "1 ~ 12"), ("2026-09 ~ 2026-03", "앞섭니다"), ("2024 ~ 2025 ~ 2026", "3개")])
def test_period_warnings(text, word):
    assert any(word in warning for warning in parse_period(text)[2])


# ── 상태별 검사 ───────────────────────────────────────────────────────────────
def test_unknown_status_is_an_error():
    assert codes(check(one("제목: 가"), "보류")) == ["status"]


def test_draft_needs_only_a_title():
    assert codes(check(one("제목: 가"), "초안"), "오류") == []
    assert codes(check(one("제목:"), "초안"), "오류") == ["title"]


def test_structured_needs_kind_and_kind_has_two_values():
    assert "kind" in codes(check(one("제목: 가"), "구조화"), "오류")
    assert "kind" in codes(check(one("제목: 가", "구분: 사내"), "구조화"), "오류")
    assert codes(check(one("제목: 가", "구분: 업무 외"), "구조화"), "오류") == []


def test_warnings_carry_period_quant_bad_lines_unknown_keys():
    b = parse((FIXTURES / "broken.md").read_text(encoding="utf-8")).blocks[0]
    problems = check(b, "구조화")
    assert codes(problems, "오류") == []
    assert {"quant", "baseline_ask", "bad_line", "unknown_key"} <= set(codes(problems, "경고"))
    assert "period" not in codes(problems)          # "2025.04 2025.10" 은 읽힌다


def test_unreadable_period_is_x07_material():
    assert any("X-07" in p.message for p in check(one("제목: 가", "구분: 업무", "기간: 작년쯤"), "구조화"))


def test_format_version_warning():
    b = parse("형식: slow-way-experience/0.2\n제목: 가\n구분: 업무").blocks[0]
    assert codes(check(b, "구조화"), "경고") == ["version"]


# ── 확정 조건 1 ~ 4 ──────────────────────────────────────────────────────────
READY = ("제목: 가", "역할: 본인이 정리", "구분: 업무", "상황: 편차가 컸다", "행동:", "- 기준 정리",
         "결과_정량:", "- 재검 | 줄어듦 | 기준: 기존 대비 | 시점: 2026", "확인_필요:", "-")


def test_ready_block_can_be_confirmed():
    b = one(*READY)
    assert confirm_ready(b, "홍길동") == [] and codes(check(b, "확정", "홍길동"), "오류") == []


def test_condition1_person_role_kind_title():
    reasons = confirm_ready(one(*READY))
    assert reasons and reasons[0].startswith("1.") and "사람" in reasons[0]


def test_condition2_two_of_situation_action_result():
    reasons = confirm_ready(one("제목: 가", "역할: 본인", "구분: 업무", "상황: 있음"), "홍길동")
    assert any(r.startswith("2.") for r in reasons)


def test_condition3_open_questions_block_confirmation():
    b = one(*READY[:-1], "- 값이 얼마였나")
    assert any(r.startswith("3.") for r in confirm_ready(b, "홍길동"))


def test_condition4_unknown_baseline_kind_blocks_confirmation():
    b = one(*[line.replace("기준: 기존 대비", "기준: 기준 없음") for line in READY])
    assert any(r.startswith("4.") and "재검" in r for r in confirm_ready(b, "홍길동"))


def test_experience_id_shape():
    assert is_experience_id("E-001") and is_experience_id("E-1024")
    assert not is_experience_id("E-01") and not is_experience_id("e-001") and not is_experience_id("E-001?")
