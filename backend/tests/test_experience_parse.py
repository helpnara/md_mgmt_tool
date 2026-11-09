"""경험 응답 파서 (TODO 256 · 253 의 1단계).

규칙 번호는 `docs/팀원이력정리/응답형식.md` 3절(원본 `docs/spec/context_file.md` 3.3 v0.2), ① ~ ⑧ 은 `1단계.md` 4절.
가상 자료 다섯(`fixtures/experience/`)은 실험 01 에서 본 형식 변형을 하나씩 재현한 것 — 사람 · 과제 · 수치는 모두 지어냈다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.experience.parse import NO_BLOCK_NOTICE, PARSE_STEPS, guess_baseline_kind, normalize_key, parse

FIXTURES = Path(__file__).parent / "fixtures" / "experience"
NAMES = ("fenced", "no_fence", "span_markers", "broken", "continued")


def load(name: str) -> str:
    return (FIXTURES / f"{name}.md").read_text(encoding="utf-8")


def block(*lines: str, fence: bool = True) -> str:
    body = "\n".join(("형식: slow-way-experience/0.1",) + lines)
    return f"```slow-way\n{body}\n```" if fence else body


# ── 규칙 1 · 2 — 블록 찾기 ─────────────────────────────────────────────────────
def test_rule1_fenced_and_unfenced_blocks_are_found():
    assert len(parse(load("fenced")).blocks) == 2
    assert parse(load("fenced")).found_fence
    unfenced = parse(load("no_fence"))
    assert len(unfenced.blocks) == 2 and not unfenced.found_fence


def test_rule1_three_blocks_back_to_back_without_blank_lines():
    text = "\n".join(block(f"제목: 경험 {n}", "구분: 업무", fence=False) for n in range(3))
    result = parse(text)
    assert [b.get("제목") for b in result.blocks] == ["경험 0", "경험 1", "경험 2"]


def test_rule2_no_block_keeps_raw_and_says_so():
    text = "죄송합니다. 형식을 잘 모르겠습니다.\n제목: 이것은 블록이 아님"
    result = parse(text)
    assert result.blocks == [] and result.notice == NO_BLOCK_NOTICE and result.raw == text


# ── 규칙 3 · 4 — 전처리 ──────────────────────────────────────────────────────
def test_rule3_span_markers_are_removed_and_counted():
    result = parse(load("span_markers"))
    b = result.blocks[0]
    assert result.stripped_markers == 32
    assert b.get("제목") == "설비 점검 주기 조정"
    assert "span" not in repr(b.fields) and "span" not in repr(b.lists)


def test_rule4_broken_bullet_char_becomes_list_item_and_controls_go():
    result = parse(load("broken"))
    assert result.blocks[0].lists["행동"] == ["후보 장비 시연 일정 조율", "비교표 작성"]
    hidden = parse(block("제목: 숨은​글자", "구분: 업무"))
    assert hidden.blocks[0].get("제목") == "숨은글자" and hidden.stripped_controls == 1


# ── 규칙 5 · 6 — 키와 값 ─────────────────────────────────────────────────────
def test_rule5_colons_quotes_hashes_stay_in_values():
    b = parse(block('상황: 기준 문서: "없음" # 1차', "제목: A:B")).blocks[0]
    assert b.get("상황") == '기준 문서: "없음" # 1차' and b.get("제목") == "A:B"


def test_rule6_keys_ignore_spaces_and_underscores_unknown_kept():
    b = parse(block("결과 정량:", "- 재검 | 1건 | 기준: 기존 대비 | 시점: 2026", "확인 필요:", "- 값", "메모: 따로 적음")).blocks[0]
    assert b.quants[0].metric == "재검" and b.lists["확인_필요"] == ["값"]
    assert b.unknown == {"메모": "따로 적음"}
    assert normalize_key("역량 _ 기술") == "역량기술"


# ── 규칙 7 · 8 · 9 ────────────────────────────────────────────────────────────
def test_rule7_list_under_scalar_key_is_joined_lesson_kept_as_is():
    no_fence = parse(load("no_fence")).blocks[0]
    assert no_fence.get("교훈") == "사례를 먼저 모으면 규칙이 보인다\n현장 사람과 같이 본다"
    spans = parse(load("span_markers")).blocks[0]
    assert spans.get("결과_정성") == "점검 인력이 고장 잦은 설비에 몰렸다\n주기표가 설비팀 표준이 됨"
    fenced = parse(load("fenced")).blocks[0]
    assert fenced.get("교훈").endswith("/ 숫자보다 기준이 먼저다 (회고 2절)")


@pytest.mark.parametrize("mark", ["-", "해당 없음", "미상", "없음", "확인 필요"])
def test_rule8_empty_marks_become_empty_with_original_kept(mark):
    b = parse(block("제목: 빈 값", f"역량_리더십: {mark}", "증빙:", f"- {mark}" if mark != "-" else "-")).blocks[0]
    assert b.get("역량_리더십") == "" and b.raw_values["역량_리더십"] == mark
    assert b.lists["증빙"] == [] and b.raw_values["증빙"] == mark


def test_rule8_list_under_scalar_of_only_empty_marks():
    b = parse(load("span_markers")).blocks[0]
    assert b.get("역량_리더십") == "" and b.raw_values["역량_리더십"] == "해당 없음"


def test_rule9_continues():
    blocks = parse(load("continued")).blocks
    assert [b.continues for b in blocks] == ["E-027", "E-027?", None]
    broken = parse(load("broken")).blocks[0]
    assert broken.continues is None and any("이어짐" in bad.reason for bad in broken.bad_lines)


# ── 규칙 10 · 11 · 12 — 정량 성과 ──────────────────────────────────────────────
def test_rule10_four_three_two_cells():
    b = parse(block("결과_정량:", "- 가 | 1 | 기준: 기존 대비 | 시점: 2026", "- 나 | 2 | 기준: 기존 대비", "- 다 3건")).blocks[0]
    four, three, two = b.quants
    assert (four.metric, four.value, four.baseline, four.when) == ("가", "1", "기존 대비", "2026")
    assert (three.when, three.baseline) == ("", "기존 대비") and not three.warnings
    assert two.metric == "다 3건" and two.warnings


def test_rule11_prefixes_are_removed():
    q = parse(load("no_fence")).blocks[0].quants[0]
    assert q.baseline == "기준 없음" and q.when == "2025"


def test_rule12_no_baseline_and_ask_on_aggregates_or_conditions():
    b = parse(block("결과_정량:", "- 가 | 1 | 기준: 미상 | 시점: 2026", "- 나 | 2 |  | 시점: 2026", "- 다 | 3 | 기준: 연간 누적 | 시점: 2026")).blocks[0]
    assert [q.baseline for q in b.quants] == ["기준 없음", "기준 없음", "연간 누적"]
    assert [q.ask for q in b.quants] == [False, False, True]
    assert parse(load("broken")).blocks[0].quants[1].ask   # "시연 7주간" — 기간이 온 기준


def test_rule8_empty_marks_inside_quant_cells():
    """실험 1회차(2026-11-10) — 원본 예시의 `시점: 확인 필요` 가 글자 그대로 남았다. 정량 칸에도 빈 값 표기를 적용한다."""
    q = parse(load("no_fence")).blocks[0].quants[1]
    assert q.when == "" and "확인 필요" in q.raw


# ── 규칙 13 · 14 · 15 ─────────────────────────────────────────────────────────
def test_rule13_bad_lines_have_numbers_and_rest_is_filled():
    b = parse(load("broken")).blocks[0]
    first = b.bad_lines[0]
    assert (first.line, first.text, first.reason) == (2, "이 블록은 요약입니다", "칸 이름도 목록도 아닌 줄")
    assert b.get("제목") == "검사 장비 교체 검토" and b.get("목표") == "교체 후보 셋을 비교한다."


def test_rule14_similar_titles_and_same_period_value_are_duplicates():
    assert parse(load("continued")).duplicates == [(0, 1)]
    same_value = "\n".join(block("제목: 전혀 다른 이름", "기간: 2026-01", "결과_정량:", "- 가 | 5건 | 기준: 기존 대비") for _ in range(1)) + "\n" + \
        block("제목: 아주 딴 것", "기간: 2026-01", "결과_정량:", "- 나 | 5건 | 기준: 기존 대비")
    assert parse(same_value).duplicates == [(0, 1)]
    assert parse(load("fenced")).duplicates == []


def test_rule15_raw_response_is_returned_whole():
    text = load("fenced")
    assert parse(text).raw == text


# ── 1단계에서 정한 것 ① ~ ⑧ ──────────────────────────────────────────────────
def test_decision1_prose_after_block_is_outside():
    fenced = parse(load("fenced"))
    assert fenced.outside_lines == 2 and "필요하시면" not in repr(fenced.blocks[-1].fields)
    unfenced = parse(load("no_fence"))
    assert unfenced.outside_lines == 1 and unfenced.blocks[-1].unknown == {}


def test_decision2_wrapped_line_joins_the_key_above():
    b = parse(load("broken")).blocks[0]
    assert b.get("상황").endswith("단, 장비 선정 기준은 바뀔 수 있음: 예산 확정 전")


def test_decision3_only_known_or_short_words_are_keys():
    b = parse(load("broken")).blocks[0]
    assert b.unknown == {"참고 사항": "시연은 두 번 했음"}
    long_line = parse(block("상황: 첫 줄", "그리고 장비 선정 기준은 바뀔 수 있음: 메모")).blocks[0]
    assert long_line.unknown == {} and "메모" in long_line.get("상황")


def test_decision6_lesson_source_split_but_kept():
    b = parse(load("fenced")).blocks[0]
    assert b.lesson_source == "회고 2절" and b.get("교훈").endswith("(회고 2절)")


@pytest.mark.parametrize("baseline,kind", [
    ("기존 육안 판정 대비", "비교"), ("전년", "비교"), ("55% → 80%", "비교"),
    ("연간 누적", "집계"), ("팀 정원", "집계"), ("불량률 1% 가정", "조건"), ("격주", "조건"), ("시연 7주간", "조건"),
    ("기준 없음", "미확인"), ("", "미확인"), ("미상", "미확인"), ("현장 설명", "미확인"),
])
def test_decision8_baseline_kind_guess(baseline, kind):
    assert guess_baseline_kind(baseline) == kind


# ── 자료 다섯 — 통째로 ────────────────────────────────────────────────────────
@pytest.mark.parametrize("name,count", [("fenced", 2), ("no_fence", 2), ("span_markers", 1), ("broken", 1), ("continued", 3)])
def test_fixture_block_counts(name, count):
    assert len(parse(load(name)).blocks) == count


def test_every_block_has_every_key():
    for name in NAMES:
        for b in parse(load(name)).blocks:
            assert {"제목", "기간", "역할", "구분", "상황", "목표", "결과_정성", "교훈"} <= set(b.fields)
            assert {"행동", "증빙", "확인_필요"} <= set(b.lists)


# ── 규칙 끄기 — 단계를 하나씩 빼면 자료 다섯 중 어딘가의 결과가 달라져야 한다 ──────────
def _summary(steps):
    out = []
    for name in NAMES:
        r = parse(load(name), steps=steps)
        out.append((name, r.stripped_markers, r.stripped_controls, r.duplicates, r.outside_lines, [
            (b.fields, b.lists, [(q.metric, q.value, q.baseline, q.when, q.baseline_kind) for q in b.quants],
             b.unknown, b.raw_values, b.lesson_source, [(x.line, x.reason) for x in b.bad_lines], b.continues)
            for b in r.blocks
        ]))
    return repr(out)


@pytest.mark.parametrize("step", PARSE_STEPS)
def test_turning_a_step_off_changes_results(step):
    """끄면 달라져야 한다 — 달라지지 않으면 그 규칙을 보는 자료가 없다는 뜻이다(LESSONS 6)."""
    assert _summary(tuple(s for s in PARSE_STEPS if s != step)) != _summary(PARSE_STEPS), f"{step} 을 꺼도 그대로"
