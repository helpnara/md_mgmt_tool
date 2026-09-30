"""접수 사전점검 체크리스트 (TODO 155).

다섯 분류 · 열 항목 · 항목마다 단계별 점수 — 기본은 **100점 만점**이다. 한 번 매기고 끝나는 점수가
아니라 인터뷰를 거치며 **오르는 점수**라, 바꿔 저장할 때마다 검토 기록에 한 줄을 남긴다.

항목 목록은 설정에서 고친다. 그래서 매길 때 **그때의 항목 이름 · 고른 단계 · 점수 · 만점을 함께**
접수 문서에 적는다(스냅샷). 합계는 적힌 점수로 낸다 — 뒤에 항목이 바뀌어도 이미 매긴 점수는 흔들리지
않고, 화면은 *지금 항목과 다른 기준으로 매긴 점수* 라고 알린다. 만점이 100 이 아니면 100점으로 환산한다.

**다 매기기 전에는 점수가 없다.** 세 항목만 매긴 30점과 다 매긴 30점이 풀에서 같아 보이면 견줄 수 없다.
"""
from __future__ import annotations

from typing import Any

# 사용자가 준 표 그대로 (2026-09-30). 분류 · 항목 · [(단계, 점수), …]
DEFAULT_ITEMS: list[dict[str, Any]] = [
    {"group": "필요성", "item": "경영층 지시사항 여부 · 사업부 빅픽처/로드맵 연계 여부",
     "choices": [["근거 명확", 10], ["일부 반영", 7], ["없음", 2]]},
    {"group": "수익성", "item": "기대효과 산출",
     "choices": [["정량적 효과", 10], ["정성적 효과", 7], ["미제시", 2]]},
    {"group": "구체성", "item": "R&R 수립 및 유관부서 협의 여부",
     "choices": [["수립 완료", 10], ["수립 중", 7], ["미수립", 2]]},
    {"group": "구체성", "item": "수행 계획(WBS) 수립 여부",
     "choices": [["수립 완료", 10], ["수립 중", 7], ["미수립", 2]]},
    {"group": "구체성", "item": "활용방안 수립 여부(계획, 관리부서, 일정 등)",
     "choices": [["수립 완료", 10], ["수립 중", 7], ["미수립", 2]]},
    {"group": "데이터", "item": "X, Y 인자 명확성",
     "choices": [["명확하게 제시", 10], ["추가 확인 필요", 5], ["미제시", 2]]},
    {"group": "데이터", "item": "데이터 명세서 유무(테이블, 컬럼명, 저장기간 등)",
     "choices": [["있음", 10], ["불충분", 5], ["없음", 2]]},
    {"group": "데이터", "item": "연계 시스템 현황 검토 여부(수집 리스크, 일관성, 적용 대상 시스템)",
     "choices": [["검토 반영", 10], ["검토 중", 5], ["미검토", 2]]},
    {"group": "기술성", "item": "설비/기술 사양 검증 여부",
     "choices": [["기 적용-검증 완료", 10], ["기 적용-검증 중", 5], ["초도 적용", 2]]},
    {"group": "기술성", "item": "동일/유사 과제 수행 여부 검토",
     "choices": [["검토 완료", 10], ["검토 중", 5], ["미검토", 2]]},
]
DEFAULT_THRESHOLDS: list[int] = [80, 60]  # 이상이면 착수 권장 / 이상이면 보완 필요 / 그 아래 보류 검토
BANDS = [("go", "착수 권장"), ("fix", "보완 필요"), ("hold", "보류 검토")]

MAX_ITEMS = 30
MAX_TEXT = 80
MAX_NOTE = 200


# ── 정의 (설정) ─────────────────────────────────────────────────────────────

def definition() -> list[dict[str, Any]]:
    """지금의 항목 목록. 정한 적이 없거나 깨졌으면 기본 목록."""
    from . import settings as settings_service

    stored = settings_service.load().get("precheck_items")
    if isinstance(stored, list) and stored:
        try:
            return validate_items(stored)
        except ValueError:
            pass
    return [dict(item, choices=[list(c) for c in item["choices"]]) for item in DEFAULT_ITEMS]


def thresholds() -> list[int]:
    from . import settings as settings_service

    stored = settings_service.load().get("precheck_thresholds")
    try:
        return validate_thresholds(stored)
    except ValueError:
        return list(DEFAULT_THRESHOLDS)


def to_lines(items: list[dict[str, Any]]) -> str:
    """설정 칸에 보일 글 — 한 줄에 한 항목: `분류 | 항목 | 단계=점수, 단계=점수 …`."""
    return "\n".join(
        f"{item['group']} | {item['item']} | " + ", ".join(f"{label}={score}" for label, score in item["choices"])
        for item in items
    )


def parse_lines(text: str) -> list[dict[str, Any]]:
    """설정 칸의 글을 항목 목록으로. 틀린 줄은 **몇 번째 줄인지** 말해 준다."""
    items = []
    for number, raw in enumerate(str(text).splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 3:
            raise ValueError(f"{number}번째 줄: `분류 | 항목 | 단계=점수, …` 모양이어야 합니다.")
        group, item, choices_text = parts
        choices = []
        for chunk in choices_text.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            if "=" not in chunk:
                raise ValueError(f"{number}번째 줄: '{chunk}' 에 점수가 없습니다 (예: 수립 완료=10).")
            label, score = (piece.strip() for piece in chunk.rsplit("=", 1))
            try:
                choices.append([label, int(score)])
            except ValueError as exc:
                raise ValueError(f"{number}번째 줄: '{score}' 는 점수(정수)가 아닙니다.") from exc
        items.append({"group": group, "item": item, "choices": choices})
    return validate_items(items)


def validate_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, str):
        return parse_lines(value)
    if not isinstance(value, list):
        raise ValueError("사전점검 항목 형식이 올바르지 않습니다.")
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in value:
        group = " ".join(str(raw.get("group") or "").split())
        item = " ".join(str(raw.get("item") or "").split())
        if not group or not item:
            raise ValueError("분류와 항목 이름은 비울 수 없습니다.")
        if len(group) > MAX_TEXT or len(item) > MAX_TEXT:
            raise ValueError(f"'{item[:12]}…' — 이름은 {MAX_TEXT}자 이하로 적어 주세요.")
        if (group, item) in seen:
            raise ValueError(f"'{group} | {item}' 이 두 번 있습니다.")
        seen.add((group, item))
        choices = []
        labels: set[str] = set()
        for choice in raw.get("choices") or []:
            label, score = " ".join(str(choice[0]).split()), int(choice[1])
            if not label or label in labels:
                raise ValueError(f"'{item[:12]}…' — 단계 이름이 비었거나 겹칩니다.")
            if not 0 <= score <= 100:
                raise ValueError(f"'{item[:12]}…' — 점수는 0~100 사이로 적어 주세요.")
            labels.add(label)
            choices.append([label, score])
        if len(choices) < 2:
            raise ValueError(f"'{item[:12]}…' — 단계는 둘 이상이어야 합니다.")
        out.append({"group": group, "item": item, "choices": choices})
    if not out:
        raise ValueError("항목이 하나도 없습니다 — 비우려면 [기본 목록으로] 를 누르세요.")
    if len(out) > MAX_ITEMS:
        raise ValueError(f"항목은 {MAX_ITEMS}개까지입니다.")
    return out


def validate_thresholds(value: Any) -> list[int]:
    if value is None:
        raise ValueError("기준이 없습니다.")
    high, low = (int(v) for v in list(value)[:2])
    if not 0 < low <= high <= 100:
        raise ValueError("기준은 0 < 보완 필요 ≤ 착수 권장 ≤ 100 이어야 합니다.")
    return [high, low]


# ── 계산 ────────────────────────────────────────────────────────────────────

def _key(group: str, item: str) -> str:
    return f"{group}␟{item}"


def summarize(stored: Any, current: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """접수 문서의 스냅샷을 화면이 쓸 모양으로. 점수는 **적힌 값**으로만 낸다."""
    current = current if current is not None else definition()
    snapshot = stored if isinstance(stored, dict) else {}
    answers = [a for a in snapshot.get("items") or [] if isinstance(a, dict) and a.get("choice")]
    total_items = int(snapshot.get("total_items") or len(current))
    raw = sum(int(a.get("score") or 0) for a in answers)
    maximum = sum(int(a.get("max") or 0) for a in answers)
    complete = bool(answers) and len(answers) >= total_items
    score = round(raw * 100 / maximum) if complete and maximum else None

    # 지금 항목과 같은 기준인가 — 항목·단계·점수 가운데 하나라도 다르면 알린다
    now = {_key(i["group"], i["item"]): {c[0]: c[1] for c in i["choices"]} for i in current}
    stale = bool(answers) and (
        len(now) != total_items
        or any(now.get(_key(a["group"], a["item"]), {}).get(a["choice"]) != a.get("score") for a in answers)
    )
    groups: dict[str, dict[str, int]] = {}
    for item in current:
        entry = groups.setdefault(item["group"], {"score": 0, "max": 0, "rated": 0, "count": 0})
        entry["count"] += 1
        entry["max"] += max(c[1] for c in item["choices"])
    for answer in answers:
        entry = groups.setdefault(answer["group"], {"score": 0, "max": 0, "rated": 0, "count": 0})
        entry["score"] += int(answer.get("score") or 0)
        entry["rated"] += 1
    return {
        "on": snapshot.get("on"),
        "items": answers,
        "rated": len(answers),
        "total_items": total_items,
        "raw": raw,
        "max": maximum,
        "score": score,
        "band": band(score),
        "stale": stale,
        "groups": [{"group": name, **values} for name, values in groups.items()],
    }


def band(score: int | None, limits: list[int] | None = None) -> dict[str, str] | None:
    if score is None:
        return None
    high, low = limits or thresholds()
    key, label = BANDS[0] if score >= high else BANDS[1] if score >= low else BANDS[2]
    return {"key": key, "label": label}


def build_snapshot(answers: list[dict[str, Any]], today: str) -> dict[str, Any]:
    """화면이 보낸 답을 **지금 정의**로 채점해 적을 모양으로. 없는 항목·단계는 거절한다."""
    current = definition()
    by_key = {_key(i["group"], i["item"]): i for i in current}
    items = []
    for answer in answers:
        group, item = str(answer.get("group") or ""), str(answer.get("item") or "")
        choice = str(answer.get("choice") or "").strip()
        note = " ".join(str(answer.get("note") or "").split())[:MAX_NOTE] or None
        if not choice:
            continue
        definition_item = by_key.get(_key(group, item))
        if definition_item is None:
            raise ValueError(f"'{item[:16]}' 은(는) 지금 체크리스트에 없는 항목입니다. 화면을 새로 고쳐 주세요.")
        scores = {c[0]: c[1] for c in definition_item["choices"]}
        if choice not in scores:
            raise ValueError(f"'{item[:16]}' 에 '{choice}' 단계가 없습니다.")
        items.append({
            "group": group, "item": item, "choice": choice, "score": scores[choice],
            "max": max(scores.values()), "note": note,
        })
    return {"on": today, "total_items": len(current), "items": items}


def describe_change(before: dict[str, Any], after: dict[str, Any]) -> tuple[str, str]:
    """검토 기록에 남길 한 줄의 제목과 본문 — *(사전점검) 62 → 78점* 과 바뀐 항목."""
    def label(summary: dict[str, Any]) -> str:
        if summary["score"] is not None:
            return f"{summary['score']}점"
        return f"평가 중 {summary['rated']}/{summary['total_items']}" if summary["rated"] else "미평가"

    title = f"(사전점검) {label(before)} → {label(after)}"
    old = {_key(a["group"], a["item"]): a for a in before["items"]}
    lines = []
    for answer in after["items"]:
        prev = old.pop(_key(answer["group"], answer["item"]), None)
        if prev is None:
            lines.append(f"- {answer['group']} · {answer['item']}: **{answer['choice']}**({answer['score']})")
        elif prev.get("choice") != answer["choice"]:
            lines.append(f"- {answer['group']} · {answer['item']}: {prev.get('choice')} → **{answer['choice']}**")
        elif (prev.get("note") or "") != (answer.get("note") or ""):
            lines.append(f"- {answer['group']} · {answer['item']}: 근거 — {answer.get('note') or '(지움)'}")
    for gone in old.values():
        lines.append(f"- {gone['group']} · {gone['item']}: {gone.get('choice')} → (평가 지움)")
    body = "\n".join(lines) if lines else "바뀐 항목이 없다."
    return title, body + "\n"
