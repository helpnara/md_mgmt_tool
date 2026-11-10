"""정합성 검사 (TODO 260 · 253 의 4단계 — docs/팀원이력정리/4단계.md 3절).

설계 원본 `docs/04_DATA_MODEL.md` 8절(X-01 ~ X-09)을 이 도구에 맞춰 — **같은 사람의 경험끼리** 본다(4단계.md ④).
X-01 · X-06 · X-09 는 입사 전 이력을 다룰 때. R-07(역할 주체)은 원본 FR-C10 — 원본은 확정을 막지만 여기서는 경고로(⑤).

**경고만** 낸다. 저장은 막지 않고 확정만 막는다(원본 FR-F1). 경고마다 `key` 가 있어 [확인함] 이 그 내용에만 붙는다 —
내용(상대 경험 · 연도 · 담당 기간)이 바뀌면 key 가 바뀌어 다시 묻는다.
파일 · DB 를 모른다 — 부르는 쪽이 경험 목록과 담당 기간을 준다.
"""
from __future__ import annotations

import difflib
import hashlib
import re
from dataclasses import dataclass
from typing import Any, Iterable

CODES = {
    "X-02": "담당 기간 밖",
    "X-03": "기간 밖의 연도",
    "X-04": "같은 증빙의 다른 이름",
    "X-05": "특허가 둘 이상에",
    "X-07": "기간 없음",
    "X-08": "중복 후보",
    "R-07": "역할의 본인 몫",
}
SELF_WORDS = ("본인", "직접", "내가", "제가", "혼자", "단독")
_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
TITLE_SIMILAR = 0.8      # 1단계 규칙 14 ⑤ 와 같은 기준
EVIDENCE_SIMILAR = 0.6


@dataclass
class Warning:
    code: str
    key: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "key": self.key, "message": self.message, "label": CODES.get(self.code, self.code)}


def _short(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def _norm(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", (text or "").lower())


def role_ok(role: str) -> bool:
    return bool(role) and any(word in role for word in SELF_WORDS)


def _years(item: dict[str, Any]) -> tuple[int | None, int | None]:
    start = int(item["start"][:4]) if item.get("start") else None
    end = int(item["end"][:4]) if item.get("end") else None
    return start, end


def check_person(items: Iterable[dict[str, Any]], spans: dict[str, tuple[str, str]]) -> dict[str, list[Warning]]:
    """경험 번호 → 경고. `spans` = 과제 번호 → (담당 시작 YYYY-MM, 담당 끝 YYYY-MM 또는 "")."""
    items = list(items)
    out: dict[str, list[Warning]] = {item["id"]: [] for item in items}
    for item in items:
        warnings = out[item["id"]]
        start, end = item.get("start") or "", item.get("end") or ""
        # X-07 — 기간이 비어 연도를 정할 수 없다
        if not start:
            warnings.append(Warning("X-07", "", "기간(시작)이 비어 있어 언제의 경험인지 정할 수 없습니다"))
        # X-02 — 경험 기간이 그 과제의 담당 기간 밖
        span = spans.get(item.get("project") or "")
        if span and start:
            begin, finish = span
            outside = (begin and start < begin) or (finish and (end or start) > finish)
            if outside:
                warnings.append(Warning("X-02", f"{item['project']}:{begin}~{finish}:{start}~{end}",
                                        f"경험 기간({start} ~ {end or '진행 중'})이 과제 {item['project']} 의 담당 기간"
                                        f"({begin or '?'} ~ {finish or '지금'}) 밖입니다"))
        # X-03 — 행동 · 증빙의 연도가 경험 기간 밖
        first, last = _years(item)
        if first:
            found = {int(y) for line in item.get("actions") or [] for y in _YEAR.findall(line)}
            found |= {int(e["year"]) for e in item.get("evidences") or [] if str(e.get("year") or "").isdigit()}
            stray = sorted(y for y in found if y < first or (last and y > last))
            if stray:
                warnings.append(Warning("X-03", ",".join(map(str, stray)),
                                        f"행동 · 증빙의 연도 {', '.join(map(str, stray))} 이(가) 경험 기간"
                                        f"({first} ~ {last or '진행 중'}) 밖입니다"))
        # R-07 — 역할에 본인 몫이 드러나지 않는다
        if not role_ok(item.get("role") or ""):
            warnings.append(Warning("R-07", _short(item.get("role") or ""),
                                    "역할에 본인이 한 일과 다른 주체(팀원 · 외부 · AI 도구)가 한 일의 구분이 없습니다"))
    # 둘씩 보는 검사 — X-04 · X-05 · X-08
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            _pair(a, b, out)
    return out


def _pair(a: dict[str, Any], b: dict[str, Any], out: dict[str, list[Warning]]) -> None:
    def both(code: str, key: str, message: str) -> None:
        out[a["id"]].append(Warning(code, f"{b['id']}:{key}", message.replace("{other}", b["id"])))
        out[b["id"]].append(Warning(code, f"{a['id']}:{key}", message.replace("{other}", a["id"])))

    # X-08 — 제목이 비슷하거나, 기간이 같고 정량 값이 같다
    ta, tb = _norm(a.get("title") or ""), _norm(b.get("title") or "")
    similar = bool(ta and tb) and (ta == tb or difflib.SequenceMatcher(None, ta, tb).ratio() >= TITLE_SIMILAR)
    values_a = {q.get("value") for q in a.get("quants") or [] if q.get("value")}
    values_b = {q.get("value") for q in b.get("quants") or [] if q.get("value")}
    same_value = (a.get("start"), a.get("end")) == (b.get("start"), b.get("end")) and bool(values_a & values_b)
    if similar or same_value:
        both("X-08", "dup", "{other} 과(와) 같은 경험일 수 있습니다(" + ("제목이 비슷함" if similar else "기간 · 정량 값이 같음") + ")")
    for ea in a.get("evidences") or []:
        for eb in b.get("evidences") or []:
            na, nb = _norm(ea.get("text") or ""), _norm(eb.get("text") or "")
            if not na or not nb:
                continue
            # X-05 — 같은 특허가 경험 둘 이상에
            if ea.get("type") == "특허" and eb.get("type") == "특허" and na == nb:
                both("X-05", f"patent:{_short(na)}", f"특허 ‘{ea['text'][:30]}’ 이(가) {{other}} 에도 붙어 있습니다 — 특허는 보통 경험 하나")
            # X-04 — 같은 해 · 같은 종류인데 이름만 다르다
            elif (ea.get("type") == eb.get("type") and ea.get("year") and ea.get("year") == eb.get("year") and na != nb
                  and difflib.SequenceMatcher(None, na, nb).ratio() >= EVIDENCE_SIMILAR):
                both("X-04", f"ev:{_short(na + '|' + nb if na < nb else nb + '|' + na)}",
                     f"같은 해({ea['year']}) {ea.get('type')} ‘{ea['text'][:20]}’ 와 {{other}} 의 ‘{eb['text'][:20]}’ — 같은 것의 다른 이름인가요?")
