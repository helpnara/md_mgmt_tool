"""담당과 역할 — 사람마다의 역할 · 맡은 부분 · 담당 기간 · 회고 세 줄 (TODO 237).

팀원이 나중에 본인의 업무 이력 · 성과를 정리할 때 쓰는 재료다. 업무 이력 한 줄은 **과제 · 기간 · 내 역할 · 내가 한 일 · 성과**인데,
담당자 명단만으로는 역할도 기간도 한 일도 알 수 없다. 화면 · 내보내기는 나중에 붙여도 되지만 **기록은 지금부터 쌓지
않으면 되살릴 수 없다** — 그래서 먼저 쌓는다.

* 자리 — 과제 `index.md` 머리 정보의 `contributions` (사람마다 한 줄). **파일이 원본**, 색인은 `project_contribution`.
* 담당 기간은 **저절로** — 담당자를 더하면 그날부터, 빼면 그날까지(`follow_owners`). 넘기기(122)도 같다.
* 기록이 없는 담당자(예전 과제)는 **시작일부터**로 읽는다(`derived`). 파일에는 누가 무엇을 고칠 때 처음 적힌다 —
  모든 과제 파일에 같은 줄을 미리 적어 두지 않는다.
* 이 모듈은 머리 정보만 다룬다(색인 · 서비스 양쪽이 쓴다 — 서로를 불러오지 않게 여기 따로 둔다).
"""
from __future__ import annotations

from datetime import date as _date
from typing import Any

from . import schemas as rules

ROLES = ("주관", "참여", "지원")
RETRO_KEYS = ("problem", "did", "result")
TEXT_KEYS = ("role", "part", *RETRO_KEYS)
PART_MAX = 100
# 기술 · 도구 (TODO 239 ②) — 태그와 같은 쉼표 규칙, 하나에 30자 · 10개까지
SKILL_MAX = 30
SKILLS_MAX = 10
RETRO_MAX = 1000
OUTCOME_MAX = 200

LABELS = {
    "role": "역할", "part": "맡은 부분", "from": "담당 시작", "to": "담당 끝",
    "problem": "무엇이 문제였나", "did": "내가 한 일", "result": "결과", "outcome": "그 밖의 성과",
    "skills": "기술 · 도구",
}


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _day(value: object) -> str | None:
    if isinstance(value, _date):
        return value.isoformat()
    text = _text(value)[:10]
    try:
        return _date.fromisoformat(text).isoformat() if text else None
    except ValueError:
        return None


def _row(raw: dict[str, Any]) -> dict[str, Any] | None:
    name = " ".join(_text(raw.get("name")).split())
    if not name:
        return None
    role = _text(raw.get("role"))
    return {
        "name": name,
        "role": role if role in ROLES else "",
        "part": _text(raw.get("part")),
        "from": _day(raw.get("from")),
        "to": _day(raw.get("to")),
        **{key: _text(raw.get(key)) for key in RETRO_KEYS},
        "skills": rules.split_list(raw.get("skills"))[:SKILLS_MAX],
    }


def stored(meta: dict[str, Any]) -> list[dict[str, Any]]:
    """파일에 적힌 줄만 — 손으로 고친 이상한 줄(이름 없음 · 목록 아님)은 건너뛴다. 같은 이름은 앞의 것."""
    value = meta.get("contributions")
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    for raw in value:
        row = _row(raw) if isinstance(raw, dict) else None
        if row and all(existing["name"] != row["name"] for existing in out):
            out.append(row)
    return out


def owners_of(meta: dict[str, Any]) -> list[str]:
    return rules.split_list(meta.get("owners") or meta.get("owner"))


def read(meta: dict[str, Any]) -> list[dict[str, Any]]:
    """화면 · 색인에 보일 줄 — 지금 담당이 먼저(담당 순서대로), 그 뒤에 예전 담당(시작이 이른 순).

    기록이 없는 담당자는 **시작일부터** 한 줄을 만들어 `derived: True` 로 보낸다.
    """
    rows = {row["name"]: {**row, "derived": False} for row in stored(meta)}
    start = _day(meta.get("start_date"))
    owners = owners_of(meta)
    current = []
    for name in owners:
        row = rows.pop(name, None) or {**_blank(name), "from": start, "derived": True}
        current.append({**row, "current": True})
    former = sorted(rows.values(), key=lambda row: (row["from"] or "", row["name"]))
    return current + [{**row, "current": False} for row in former]


def _blank(name: str) -> dict[str, Any]:
    return {"name": name, "role": "", "part": "", "from": None, "to": None, **{key: "" for key in RETRO_KEYS}, "skills": []}


def materialize(meta: dict[str, Any]) -> list[dict[str, Any]]:
    """파일에 적을 줄 — 저장된 줄에 기록 없는 담당자(시작일부터)를 더한다."""
    return [{key: value for key, value in row.items() if key not in ("derived", "current")} for row in read(meta)]


def to_meta(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """머리 정보에 적는 모양 — 빈 칸은 적지 않는다(파일을 열었을 때 읽기 쉽게)."""
    out = []
    for row in rows:
        item: dict[str, Any] = {"name": row["name"]}
        for key in ("role", "part", "skills", "from", "to", *RETRO_KEYS):
            if row.get(key):
                item[key] = row[key]
        out.append(item)
    return out


def has_retro(row: dict[str, Any]) -> bool:
    return any(row.get(key) for key in RETRO_KEYS)


def follow_owners(meta: dict[str, Any], new_owners: list[str], today: str) -> list[dict[str, Any]] | None:
    """담당자가 바뀌면 담당 기간을 따라 적는다. 바뀐 것이 없으면 None(파일을 건드리지 않는다).

    * 새로 든 사람 — 예전에 있던 사람이면 끝 날짜를 지우고(다시 맡음), 처음이면 오늘부터(과제가 아직 시작 전이면 시작일부터).
    * 빠진 사람 — 오늘까지. 과제 시작 전에 빠졌고 적어 둔 것(역할 · 회고)이 없으면 줄을 지운다 — 일한 적이 없다.
    """
    old_owners = owners_of(meta)
    if old_owners == new_owners:
        return None
    if set(old_owners) == set(new_owners):
        # 순서만 바뀌었다 — 기간은 그대로, 보이는 순서는 owners 가 정한다
        return None
    rows = {row["name"]: row for row in materialize(meta)}
    start = _day(meta.get("start_date"))
    for name in new_owners:
        if name in old_owners:
            continue
        if name in rows:
            rows[name]["to"] = None
        else:
            begin = start if start and start > today else today
            rows[name] = {**_blank(name), "from": begin}
    for name in old_owners:
        if name in new_owners or name not in rows:
            continue
        row = rows[name]
        begun = (row["from"] or "") <= today if row["from"] else True
        if not begun and not row["role"] and not row["part"] and not row.get("skills") and not has_retro(row):
            rows.pop(name)
            continue
        row["to"] = today if begun else row["from"]
    return list(rows.values())


def rename(meta: dict[str, Any], old: str, new: str) -> list[dict[str, Any]] | None:
    """같은 사람의 표기를 바로잡는다(rename_owner) — 줄의 이름만 바꾼다. 새 이름 줄이 이미 있으면 빈 칸을 옛 줄로 채운다."""
    rows = stored(meta)
    if not any(row["name"] == old for row in rows):
        return None
    target = next((row for row in rows if row["name"] == new), None)
    out = []
    for row in rows:
        if row["name"] != old:
            out.append(row)
        elif target is None:
            out.append({**row, "name": new})
        else:
            for key, value in row.items():
                if key != "name" and value and not target.get(key):
                    target[key] = value
    return out


def check_update(row: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    """한 사람 줄을 고칠 값 — 규칙에 어긋나면 ValueError(400). 보낸 칸만 바꾼다."""
    out = dict(row)
    if "role" in data:
        role = _text(data["role"])
        if role and role not in ROLES:
            raise ValueError(f"역할은 {' · '.join(ROLES)} 중 하나이거나 비워 두세요 (받은 값: {role[:20]})")
        out["role"] = role
    if "part" in data:
        out["part"] = rules.one_line(data["part"], LABELS["part"], PART_MAX)
    for key in ("from", "to"):
        if key in data:
            out[key] = rules.strict_day(data[key], LABELS[key])
    if out.get("from") and out.get("to") and out["to"] < out["from"]:
        raise ValueError(f"담당 끝({out['to']})이 담당 시작({out['from']})보다 빠릅니다.")
    if "skills" in data:
        out["skills"] = clean_skills(data["skills"])
    for key in RETRO_KEYS:
        if key in data:
            text = rules.check_body(_text(data[key]), LABELS[key]) or ""
            if len(text) > RETRO_MAX:
                raise ValueError(f"{LABELS[key]}는 {RETRO_MAX}자까지입니다 (지금 {len(text)}자).")
            out[key] = text
    return out


def clean_outcome(value: object) -> str | None:
    """금액 아닌 성과 한 줄 (A4) — 비우면 None."""
    text = rules.one_line(value, LABELS["outcome"], OUTCOME_MAX)
    return text or None


def clean_skills(value: object) -> list[str]:
    """기술 · 도구 (TODO 239 ②) — 쉼표로 나누고(태그와 같은 규칙), 하나에 30자 · 10개까지. 넘치면 400."""
    items = rules.split_list(value)
    for item in items:
        rules.one_line(item, LABELS["skills"], SKILL_MAX)
    if len(items) > SKILLS_MAX:
        raise ValueError(f"기술 · 도구는 {SKILLS_MAX}개까지입니다 (지금 {len(items)}개).")
    return items
