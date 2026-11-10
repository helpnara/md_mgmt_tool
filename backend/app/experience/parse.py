"""AI 응답 → 경험 블록 (TODO 256 · 파서 규칙 1 ~ 15 + 1단계.md 4절 ① ~ ⑧).

규칙의 원본은 느린 길 설계 저장소 `docs/spec/context_file.md` 3.3(v0.2), 이 저장소의 판은 `docs/팀원이력정리/응답형식.md` 3절.
번호는 그 규칙 번호다. ① ~ ⑧ 은 원본이 비워 둔 곳을 1단계에서 정한 것(`1단계.md` 4절) — 원본에 v0.3 으로 돌려 적는다.

**줄 단위로 읽는다**(규칙 5) — 한국어 값에 콜론 · 따옴표 · `#` 이 흔해 YAML · JSON 으로는 깨진다.
**규칙마다 단계 이름**(`PARSE_STEPS`)을 붙였다 — 시험이 하나씩 꺼서 "끄면 결과가 달라지는지" 본다(시험이 규칙을 실제로 보는지).
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field

FORMAT_NAME = "slow-way-experience"

# 원본 3.1 의 키 21(형식 포함) + 이어짐(규칙 9)
KEYS = (
    "형식", "제목", "기간", "회사", "조직", "직위", "역할", "구분", "상황", "목표", "행동",
    "결과_정량", "결과_정성", "비즈니스_영향", "역량_기술", "역량_업무", "역량_리더십", "역량_문제해결",
    "교훈", "증빙", "확인_필요", "이어짐",
    "과제",   # 선택 키(원본 스펙 v0.3 3.2) — 사내 과제 기록으로 만든 프롬프트일 때 `과제: <과제 번호>`
)
LIST_KEYS = ("행동", "결과_정량", "증빙", "확인_필요")
SCALAR_KEYS = tuple(key for key in KEYS if key not in LIST_KEYS)

# 규칙 8 — 빈 값으로 볼 표기
EMPTY_MARKS = ("", "-", "해당 없음", "해당없음", "미상", "없음", "확인 필요", "확인필요")
# 규칙 12 — 기준이 없다는 표기
NO_BASELINE = ("", "-", "기준 없음", "기준없음", "미상", "없음")

PARSE_STEPS = (
    "strip_markers",      # 규칙 3 — 줄 끝 인용 표식
    "strip_control",      # 규칙 4 — U+FFFC 같은 제어 · 치환 문자(줄머리면 글머리표로 되돌린다)
    "fence_end",          # ① — 펜스가 열렸으면 닫는 펜스에서 블록 끝
    "trailing_prose",     # ① — 빈 줄 뒤 키도 목록도 아닌 줄에서 블록 끝(블록 뒤 설명 글)
    "continuation",       # ② — 키도 목록도 아닌 줄은 위 칸에 이어 붙임
    "key_guard",          # ③ — 알려진 키 또는 짧은 낱말만 키("참고: …" 오인 방지)
    "key_normalize",      # 규칙 6 — 공백 · 밑줄 무시
    "list_under_scalar",  # 규칙 7 — 한 줄 키 아래 목록
    "empty_values",       # 규칙 8 — 빈 값 표기
    "quant_prefix",       # 규칙 11 — "기준:" · "시점:" 접두어
    "baseline_empty",     # 규칙 12 — 기준 없음 정규화
    "lesson_source",      # ⑥ — 교훈 끝 출처 표시를 따로
    "duplicates",         # 규칙 14 · ⑤ — 중복 후보
)

NO_BLOCK_NOTICE = "형식 블록이 없습니다. 프롬프트를 다시 붙여 넣으세요."

_MARKER = re.compile(r"\s*\[span_\d+\]\((?:start|end)_span\)")
_FORMAT_LINE = re.compile(r"^`*\s*형식\s*[:：]\s*" + FORMAT_NAME + r"/(\d+\.\d+)\s*`*$")
_FENCE_OPEN = re.compile(r"^```+\s*slow-way\s*$")
_FENCE_ANY = re.compile(r"^```")
_KEY_LINE = re.compile(r"^([^:：]{1,40})[:：](.*)$")
_PUNCT = re.compile(r"[.,!?()\[\]{}'\"“”‘’「」『』<>/\\|~]")
_LIST_ITEM = re.compile(r"^(?:[-•·*]\s+|-$)")
_CONTINUES = re.compile(r"^(E-\d{3,}\??)$")
_LESSON_SOURCE = re.compile(r"\s*[(（]([^()（）]{1,40})[)）]\s*$")

# ⑧ — 기준 종류 추정 낱말. 확정은 4단계 화면에서 팀장이 한다
_KIND_WORDS = (
    ("비교", ("대비", "기존", "전년", "이전", "→", "비교", "보다")),
    ("집계", ("누적", "연간", "총", "정원", "건수", "합계", "월간", "평균")),
    ("조건", ("가정", "조건", "환산", "주간", "격주", "개월", "기간")),
)


@dataclass
class Quant:
    """정량 성과 한 줄 — 지표 · 값 · 기준 · 시점. 값은 글로 둔다(숫자로 읽지 않는다)."""
    metric: str
    value: str = ""
    baseline: str = ""
    when: str = ""
    baseline_kind: str = "미확인"   # 비교 · 집계 · 조건 · 미확인 — 추정
    ask: bool = False               # 규칙 12 — 확정 화면에서 "비교 기준인가?" 를 물을 것
    raw: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class BadLine:
    """규칙 13 — 못 읽은 줄. 줄 번호는 응답 전체에서 1부터."""
    line: int
    text: str
    reason: str


@dataclass
class ParsedBlock:
    index: int                                              # 응답 안 순서(0부터)
    version: str = ""                                       # 형식 줄의 판("0.1")
    fields: dict[str, str] = field(default_factory=dict)    # 한 줄 키 — 빈 값 정규화 뒤
    lists: dict[str, list[str]] = field(default_factory=dict)  # 행동 · 증빙 · 확인_필요(빈 항목은 뺀다)
    quants: list[Quant] = field(default_factory=list)
    continues: str | None = None                            # "E-027" · "E-027?" · None
    lesson_source: str = ""                                 # ⑥ 교훈 끝 출처 표시
    unknown: dict[str, str] = field(default_factory=dict)   # 미분류 키(규칙 6)
    raw_values: dict[str, str] = field(default_factory=dict)  # 빈 값으로 바꾼 칸의 원래 표기(규칙 8)
    bad_lines: list[BadLine] = field(default_factory=list)
    first_line: int = 0                                     # 형식 줄의 줄 번호

    def get(self, key: str) -> str:
        return self.fields.get(key, "")


@dataclass
class ParseResult:
    blocks: list[ParsedBlock]
    found_fence: bool
    stripped_markers: int              # 규칙 3 — 지운 인용 표식 수
    stripped_controls: int             # 규칙 4 — 지운 제어 문자 수
    duplicates: list[tuple[int, int]]  # 규칙 14 — 중복 후보 쌍(블록 index)
    outside_lines: int                 # ① — 블록 밖으로 본 글 줄 수(무시)
    notice: str                        # 규칙 2 — 블록이 없을 때 안내
    raw: str                           # 규칙 15 — 응답 원문 전체(저장은 2단계)


def normalize_key(text: str, normalize: bool = True) -> str:
    """규칙 6 — 공백 · 밑줄을 지우고 비교한다. `결과 정량` = `결과_정량`."""
    text = text.strip()
    return re.sub(r"[\s_]+", "", text) if normalize else text


_KEY_INDEX = {normalize_key(key): key for key in KEYS}


def _is_empty(value: str) -> bool:
    return value.strip() in EMPTY_MARKS


def guess_baseline_kind(baseline: str) -> str:
    """⑧ — 기준 칸의 낱말로 기준 종류를 추정한다. "기준 없음" · 빈 칸은 미확인."""
    text = (baseline or "").strip()
    if text in NO_BASELINE:
        return "미확인"
    for kind, words in _KIND_WORDS:
        if any(word in text for word in words):
            return kind
    return "미확인"


def _clean_lines(text: str, steps: tuple[str, ...]) -> tuple[list[str], int, int]:
    markers = controls = 0
    out: list[str] = []
    for line in text.splitlines():
        if "strip_markers" in steps:
            line, count = _MARKER.subn("", line)
            markers += count
        if "strip_control" in steps:
            stripped = line.lstrip()
            if stripped.startswith("￼"):
                # 글머리표가 U+FFFC 로 깨져 온다 — 줄머리면 목록 표시로 되돌린다
                line = line[: len(line) - len(stripped)] + "- " + stripped[1:].lstrip()
                controls += 1
            kept = []
            for char in line:
                if char in "\t":
                    kept.append(" ")
                elif char == "￼" or char == "�" or unicodedata.category(char) in ("Cc", "Cf"):
                    controls += 1
                else:
                    kept.append(char)
            line = "".join(kept)
        out.append(line)
    return out, markers, controls


def _key_of(stripped: str, steps: tuple[str, ...]) -> tuple[str | None, str | None, str]:
    """(알려진 키, 미분류 키 이름, 값). 키 줄이 아니면 (None, None, "")."""
    if _LIST_ITEM.match(stripped):
        return None, None, ""
    match = _KEY_LINE.match(stripped)
    if not match:
        return None, None, ""
    name, value = match.group(1).strip(), match.group(2).strip()
    known = _KEY_INDEX.get(normalize_key(name, "key_normalize" in steps))
    if known:
        return known, None, value
    if "key_guard" in steps:
        short = len(name) <= 8 and name.count(" ") <= 1 and not _PUNCT.search(name)
        if not short:
            return None, None, ""
    return None, name, value


def _block_ranges(lines: list[str], steps: tuple[str, ...]) -> tuple[list[tuple[int, int, bool]], int]:
    """(시작, 끝(포함 안 함), 펜스 안인가) 목록과 블록 밖 글 줄 수."""
    starts = [i for i, line in enumerate(lines) if _FORMAT_LINE.match(line.strip())]
    ranges: list[tuple[int, int, bool]] = []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        prev = next((lines[i].strip() for i in range(start - 1, -1, -1) if lines[i].strip()), "")
        fenced = bool(_FENCE_OPEN.match(prev))
        stop = end
        blank = False
        for i in range(start + 1, end):
            stripped = lines[i].strip()
            if "fence_end" in steps and _FENCE_ANY.match(stripped):
                stop = i
                break
            if not stripped:
                blank = True
                continue
            if "trailing_prose" in steps and blank and not fenced:
                known, unknown, _ = _key_of(stripped, steps)
                if not known and unknown is None and not _LIST_ITEM.match(stripped):
                    stop = i
                    break
            blank = False
        ranges.append((start, stop, fenced))
    inside = {i for a, b, _ in ranges for i in range(a, b)}
    outside = sum(1 for i, line in enumerate(lines) if line.strip() and i not in inside and not _FENCE_ANY.match(line.strip()))
    return ranges, max(outside, 0)


def _split_quant(item: str, steps: tuple[str, ...]) -> Quant:
    """규칙 10 · 11 · 12 — `지표 | 값 | 기준: … | 시점: …`."""
    parts = [part.strip() for part in item.split("|")]
    quant = Quant(metric=item.strip(), raw=item)
    if len(parts) >= 4:
        quant.metric, quant.value, quant.baseline, quant.when = parts[0], parts[1], parts[2], " | ".join(parts[3:])
    elif len(parts) == 3:
        quant.metric, quant.value, quant.baseline = parts
    else:
        quant.warnings.append("칸이 둘 이하입니다 — 지표 · 값 · 기준 · 시점을 | 로 나눠 주세요")
    if "quant_prefix" in steps:
        quant.baseline = re.sub(r"^기준\s*[:：]\s*", "", quant.baseline)
        quant.when = re.sub(r"^시점\s*[:：]\s*", "", quant.when)
    if "empty_values" in steps:
        # 실험 1회차 — 원본 예시의 "시점: 확인 필요". 정량의 값 · 시점 칸에도 규칙 8 을 적용한다(원문은 raw 에)
        quant.value = "" if _is_empty(quant.value) else quant.value
        quant.when = "" if _is_empty(quant.when) else quant.when
    if len(parts) >= 3 and "baseline_empty" in steps and quant.baseline.strip() in NO_BASELINE:
        quant.baseline = "기준 없음"
    quant.baseline_kind = guess_baseline_kind(quant.baseline)
    quant.ask = quant.baseline_kind in ("집계", "조건")
    return quant


def _title_key(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", text or "")


def _duplicates(blocks: list[ParsedBlock]) -> list[tuple[int, int]]:
    """규칙 14 · ⑤ — 제목이 같거나 유사도 0.8 이상, 또는 기간이 같고 정량 값 하나가 같으면 중복 후보."""
    pairs: list[tuple[int, int]] = []
    for i, a in enumerate(blocks):
        for b in blocks[i + 1:]:
            ta, tb = _title_key(a.get("제목")), _title_key(b.get("제목"))
            same_title = bool(ta) and (ta == tb or difflib.SequenceMatcher(None, ta, tb).ratio() >= 0.8)
            values_a = {q.value for q in a.quants if q.value}
            same_value = bool(a.get("기간")) and a.get("기간") == b.get("기간") and bool(values_a & {q.value for q in b.quants if q.value})
            if same_title or same_value:
                pairs.append((a.index, b.index))
    return pairs


def _read_block(index: int, lines: list[str], start: int, stop: int, steps: tuple[str, ...]) -> ParsedBlock:
    match = _FORMAT_LINE.match(lines[start].strip())
    block = ParsedBlock(index=index, version=match.group(1) if match else "", first_line=start + 1)
    block.fields["형식"] = f"{FORMAT_NAME}/{block.version}"
    scalar_lists: dict[str, list[str]] = {}
    current: tuple[str, str] | None = None     # ("known" | "unknown", 키)
    blank = False
    for i in range(start + 1, stop):
        line_no, stripped = i + 1, lines[i].strip()
        if not stripped:
            blank = True
            continue
        if _FENCE_ANY.match(stripped):
            blank = False
            continue
        known, unknown, value = _key_of(stripped, steps)
        if known:
            current = ("known", known)
            if known in LIST_KEYS:
                block.lists.setdefault(known, [])
                if value:
                    block.lists[known].append(value)
            else:
                block.fields[known] = value
        elif unknown is not None:
            current = ("unknown", unknown)
            block.unknown[unknown] = value
        elif _LIST_ITEM.match(stripped):
            item = re.sub(r"^[-•·*]\s*", "", stripped)
            if current and current[0] == "known" and current[1] in LIST_KEYS:
                block.lists[current[1]].append(item)
            elif current and current[0] == "known" and "list_under_scalar" in steps:
                scalar_lists.setdefault(current[1], []).append(item)
            else:
                block.bad_lines.append(BadLine(line_no, lines[i], "칸 이름 없이 온 목록"))
        else:
            if current and "continuation" in steps and not blank:
                kind, key = current
                if kind == "unknown":
                    block.unknown[key] = (block.unknown[key] + " " + stripped).strip()
                elif key in LIST_KEYS and block.lists.get(key):
                    block.lists[key][-1] = block.lists[key][-1] + " " + stripped
                elif key in LIST_KEYS:
                    block.lists[key].append(stripped)
                elif key in scalar_lists:
                    scalar_lists[key][-1] = scalar_lists[key][-1] + " " + stripped
                else:
                    block.fields[key] = (block.fields.get(key, "") + " " + stripped).strip()
            else:
                block.bad_lines.append(BadLine(line_no, lines[i], "칸 이름도 목록도 아닌 줄"))
        blank = False

    # 규칙 7 — 한 줄 키 아래 목록은 줄바꿈으로 잇는다
    for key, items in scalar_lists.items():
        head = block.fields.get(key, "")
        kept = [item for item in items if not ("empty_values" in steps and _is_empty(item))]
        joined = "\n".join(([head] if head and not ("empty_values" in steps and _is_empty(head)) else []) + kept)
        if "empty_values" in steps and not kept and (not head or _is_empty(head)):
            block.raw_values[key] = "\n".join([head] + items).strip()
            joined = ""
        block.fields[key] = joined

    # 규칙 8 — 빈 값 표기
    if "empty_values" in steps:
        for key, value in list(block.fields.items()):
            if key != "형식" and _is_empty(value) and value.strip():
                block.raw_values[key] = value
                block.fields[key] = ""
        for key, items in block.lists.items():
            gone = [item or "-" for item in items if _is_empty(item)]
            if gone:
                block.raw_values[key] = "\n".join(gone)
                block.lists[key] = [item for item in items if not _is_empty(item)]

    # 규칙 9 — 이어짐
    nxt = block.fields.pop("이어짐", "").strip()
    match = _CONTINUES.match(nxt)
    block.continues = match.group(1) if match else None
    if nxt and not match and not _is_empty(nxt):
        block.bad_lines.append(BadLine(block.first_line, f"이어짐: {nxt}", "이어짐은 E-nnn · E-nnn? · 없음 중 하나"))

    # 규칙 10 ~ 12 — 정량 성과
    block.quants = [_split_quant(item, steps) for item in block.lists.pop("결과_정량", [])]

    # ⑥ — 교훈 끝의 출처 표시를 따로(원문은 그대로 둔다)
    if "lesson_source" in steps:
        found = _LESSON_SOURCE.search(block.get("교훈"))
        if found:
            block.lesson_source = found.group(1).strip()

    for key in SCALAR_KEYS:
        if key != "이어짐":
            block.fields.setdefault(key, "")
    for key in LIST_KEYS:
        if key != "결과_정량":
            block.lists.setdefault(key, [])
    return block


def parse(text: str, steps: tuple[str, ...] = PARSE_STEPS) -> ParseResult:
    """AI 응답 글 전체 → 경험 블록들. 못 읽은 줄은 그 블록의 `bad_lines` 에 남고 나머지는 채운다(규칙 13)."""
    raw = text or ""
    lines, markers, controls = _clean_lines(raw, steps)
    found_fence = any(_FENCE_OPEN.match(line.strip()) for line in lines)
    ranges, outside = _block_ranges(lines, steps)
    blocks = [_read_block(n, lines, start, stop, steps) for n, (start, stop, _) in enumerate(ranges)]
    return ParseResult(
        blocks=blocks,
        found_fence=found_fence,
        stripped_markers=markers,
        stripped_controls=controls,
        duplicates=_duplicates(blocks) if "duplicates" in steps else [],
        outside_lines=outside,
        notice="" if blocks else NO_BLOCK_NOTICE,
        raw=raw,
    )
