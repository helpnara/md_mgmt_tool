"""팀원별 경험 (TODO 257 · 253 의 2단계 — 설계는 docs/팀원이력정리/데이터모델.md · 2단계.md).

면담(182)과 같은 모양이다 — 사람 폴더 안(`people/<이름>/experiences/E-nnn.md`) · 머리 정보 Markdown · 다시 만들 수 있는 색인 ·
보관함 · 이전 버전 · 이름 바로잡기를 따라감. 통합 검색 · 과제 내보내기 · AI 프롬프트에는 넣지 않는다.

* **번호**는 `E-001` 부터 데이터 폴더 전체에 하나의 줄. 지운 번호도 다시 쓰지 않는다(보관함 기록까지 본다 — 접수 번호 146 과 같은 규칙).
  파일 이름 = 번호라 고쳐도 · 사람이 바뀌어도 이름은 그대로다.
* **2단계의 상태는 초안뿐**이다(2단계.md ③) — 구조화는 3단계(AI 응답 되받기), 확정은 4단계(정합성과 함께).
* 저장 전 검사는 1단계 `app.experience.check` 를 그대로 쓴다 — 같은 규칙이 두 곳에 생기지 않게.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .. import clock
from ..config import get_settings
from ..experience import consistency as consistency_rules
from ..experience import skills as skill_rules
from ..experience import tools as tool_rules
from ..experience.check import check as check_block
from ..experience.check import confirm_ready
from ..experience.parse import ParsedBlock, Quant
from ..experience.period import parse_period
from ..vault import markdown as md
from ..vault import paths
from ..vault import versions
from . import settings as settings_service


def now_iso() -> str:
    """고친 때 — 마이크로초까지. 같은 초에 두 번 고쳐도 먼저 고친 사람 알림(409)이 가려진다."""
    return clock.now().isoformat(timespec="microseconds")

STATUSES = ("초안", "구조화", "확정")
STAGE2_STATUSES = ("초안",)        # 2단계에서 만들고 고칠 수 있는 상태
KINDS = ("업무", "업무 외")
AXES = ("기술", "업무", "리더십", "문제해결")
BASELINE_KINDS = ("비교", "집계", "조건", "미확인")
EVIDENCE_TYPES = ("특허", "수상", "발표", "문서", "링크", "이미지")
SOURCES = ("담당", "응답", "직접", "분해")
SECTIONS = ("상황", "목표", "행동", "결과", "교훈", "확인 필요")
META_ORDER = ["id", "person", "title", "project", "project_text", "affiliation", "start", "end", "role", "kind", "status",
              "impact", "lesson_source", "skills", "tools", "quants", "evidences", "related", "materials", "source",
              "acknowledged", "confirmed_at", "confirmed_by", "edited_by_member_at",
              "created_at", "updated_at", "created_by", "schema"]
TITLE_MAX = 120
TEXT_MAX = 4000
LIST_MAX = 40
ID_PATTERN = re.compile(r"^E-(\d{3,})$")


class ExperienceError(ValueError):
    """사람에게 보일 말을 담은 입력 오류 — 끝점이 400 으로 돌린다."""


class ConflictError(ExperienceError):
    """먼저 고친 사람이 있다 — 409."""


# ── 자리 · 번호 ────────────────────────────────────────────────────────────────

def person_dir(name: str) -> Path:
    return paths.safe_join(get_settings().people_dir, paths.slugify(name), "experiences")


def _number(text: str) -> int:
    match = ID_PATTERN.match(text or "")
    return int(match.group(1)) if match else 0


def next_id() -> str:
    """다음 번호 — 모든 사람의 `experiences/E-*.md` 와 보관함에 간 경험의 번호 중 가장 큰 것 + 1."""
    from . import trash as trash_service

    settings = get_settings()
    used = [_number(path.stem) for path in settings.people_dir.glob("*/experiences/E-*.md")]
    used += [_number(name) for name in trash_service.used_experience_ids()]
    return f"E-{max(used, default=0) + 1:03d}"


def file_path(conn: sqlite3.Connection, experience_id: str) -> Path:
    row = conn.execute("SELECT rel_path FROM experience WHERE id = ?", (experience_id,)).fetchone()
    if not row:
        raise KeyError(experience_id)
    return paths.safe_join(get_settings().vault_dir, row["rel_path"])


# ── 값 다듬기 ─────────────────────────────────────────────────────────────────

def _text(value: object, label: str, limit: int = TEXT_MAX) -> str:
    text = "" if value is None else str(value).strip()
    if len(text) > limit:
        raise ExperienceError(f"{label}은(는) {limit}자까지입니다.")
    return text


def _lines(value: object, label: str) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, list) else str(value).splitlines()
    out = [re.sub(r"^[-•·*]\s*", "", str(item)).strip() for item in items]
    out = [item for item in out if item]
    if len(out) > LIST_MAX:
        raise ExperienceError(f"{label}은(는) {LIST_MAX}줄까지입니다.")
    return [_text(item, label, 500) for item in out]


def _month(value: object, label: str) -> str:
    text = _text(value, label, 20)
    if not text:
        return ""
    start, _, warnings = parse_period(text)
    if not start or warnings:
        raise ExperienceError(f"{label}은(는) 2026-03 처럼 적어 주세요.")
    return start


def _quants(value: object) -> list[dict[str, str]]:
    out = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        metric = _text(item.get("metric"), "지표", 200)
        if not metric:
            continue
        baseline = _text(item.get("baseline"), "기준", 200) or "기준 없음"
        kind = _text(item.get("baseline_kind"), "기준 종류", 10) or "미확인"
        if kind not in BASELINE_KINDS:
            raise ExperienceError(f"기준 종류는 {' · '.join(BASELINE_KINDS)} 중 하나입니다.")
        out.append({"metric": metric, "value": _text(item.get("value"), "값", 200), "baseline": baseline,
                    "baseline_kind": kind, "when": _text(item.get("when"), "시점", 40)})
    return out[:LIST_MAX]


def _skills(value: object) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in value if isinstance(value, list) else []:
        if isinstance(item, dict):
            axis, name = _text(item.get("axis"), "축", 10) or "기술", _text(item.get("name"), "역량 태그", 60)
        else:
            axis, name = "기술", _text(item, "역량 태그", 60)
        if not name:
            continue
        if axis not in AXES:
            raise ExperienceError(f"역량 축은 {' · '.join(AXES)} 중 하나입니다.")
        if not any(s["axis"] == axis and s["name"] == name for s in out):
            out.append({"axis": axis, "name": name})
    return out[:LIST_MAX]


def _evidences(value: object) -> list[dict[str, str]]:
    out = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        text = _text(item.get("text"), "증빙", 300)
        if not text:
            continue
        kind = _text(item.get("type"), "증빙 종류", 10) or "문서"
        if kind not in EVIDENCE_TYPES:
            raise ExperienceError(f"증빙 종류는 {' · '.join(EVIDENCE_TYPES)} 중 하나입니다.")
        out.append({"type": kind, "text": text, "year": _text(item.get("year"), "연도", 4), "file": _text(item.get("file"), "파일", 300)})
    return out[:LIST_MAX]


def clean(data: dict[str, Any], stored: dict[str, Any] | None = None, opened: tuple[str, ...] = STAGE2_STATUSES) -> dict[str, Any]:
    """들어온 값을 저장할 모양으로. 바뀌지 않는 칸(id · 사람 · 만든 때 · 출처)은 stored 를 따른다.
    `opened` — 이 길로 바꿀 수 있는 상태. 고치기(PATCH)는 초안만, 응답 되받기(3단계)는 구조화까지."""
    base = stored or {}
    merged = {**base, **data}
    status = _text(merged.get("status"), "상태", 10) or "초안"
    if status not in STATUSES:
        raise ExperienceError(f"상태는 {' · '.join(STATUSES)} 중 하나입니다.")
    if status not in opened and status != base.get("status"):
        raise ExperienceError("구조화는 [AI 로 정리](응답 되받기)로만, 확정은 정합성 검사와 함께(4단계)에서 엽니다.")
    kind = _text(merged.get("kind"), "구분", 10)
    if kind and kind not in KINDS:
        raise ExperienceError(f"구분은 {' · '.join(KINDS)} 중 하나입니다.")
    source = _text(merged.get("source"), "출처", 10) or "직접"
    if source not in SOURCES:
        raise ExperienceError(f"출처는 {' · '.join(SOURCES)} 중 하나입니다.")
    person = " ".join(_text(base.get("person") or merged.get("person"), "사람", 40).split())
    if not person:
        raise ExperienceError("사람이 비어 있습니다.")
    title = _text(merged.get("title"), "제목", TITLE_MAX)
    if not title:
        raise ExperienceError("제목이 비어 있습니다.")
    start, end = _month(merged.get("start"), "시작"), _month(merged.get("end"), "끝")
    if start and end and end < start:
        raise ExperienceError("끝이 시작보다 앞섭니다.")
    return {
        "person": person, "title": title,
        "project": _text(merged.get("project"), "과제 번호", 60), "project_text": _text(merged.get("project_text"), "과제", 200),
        "affiliation": _text(merged.get("affiliation"), "소속", 100),
        "start": start, "end": end, "role": _text(merged.get("role"), "역할", 500), "kind": kind, "status": status,
        "situation": _text(merged.get("situation"), "상황"), "goal": _text(merged.get("goal"), "목표"),
        "actions": _lines(merged.get("actions"), "행동"), "result_qual": _text(merged.get("result_qual"), "결과"),
        "impact": _text(merged.get("impact"), "영향", 500), "lesson": _text(merged.get("lesson"), "교훈"),
        "lesson_source": _text(merged.get("lesson_source"), "교훈 출처", 100),
        "open_questions": _lines(merged.get("open_questions"), "확인 필요"),
        # 역량 사전에 맞춘다(4단계.md 2절) — 동의어는 대표 이름 · 사전의 축으로, 못 맞추면 그대로.
        # 261 — 팀의 기술 · 도구 목록에 있는 이름(Python · SQL …)은 역량이 아니라 도구 칸으로
        **_skills_and_tools(merged),
        "quants": _quants(merged.get("quants")),
        "evidences": _evidences(merged.get("evidences")),
        "related": [item for item in _lines(merged.get("related"), "관련 경험") if ID_PATTERN.match(item)],
        "materials": _lines(merged.get("materials"), "재료"), "source": source,
        # 4단계(TODO 260) — 끝점(확정 · 확인함)만 바꾼다. 고치기(PATCH)로는 들어오지 않는다
        "acknowledged": _acks(merged.get("acknowledged")),
        "confirmed_at": _text(merged.get("confirmed_at"), "확정한 때", 40) if status == "확정" else "",
        "confirmed_by": _text(merged.get("confirmed_by"), "확정한 사람", 40) if status == "확정" else "",
        "edited_by_member_at": _text(merged.get("edited_by_member_at"), "팀원이 고친 때", 40),
    }


def team_tools() -> set[str]:
    """보유 기술로 보는 이름의 열쇠(TODO 273) — **보유 기술 사전**(설정)의 대표 이름 · 다른 이름.
    예전(261)에는 담당과 역할의 기술 · 도구 칸에 누가 적은 적 있는 이름 전부였다 — 그 칸에 적힌 역량 이름까지 도구로 넘어갔다."""
    return set(tool_rules.index(settings_service.tool_dictionary()))


def used_tool_names(conn: sqlite3.Connection) -> dict[str, int]:
    """과제(담당과 역할)와 경험에 실제로 적힌 보유 기술 이름 → 쓴 횟수. 사전 카드의 "쓰는 곳" · [쓰인 이름 불러오기]."""
    from .. import schemas as rules

    counts: dict[str, int] = {}
    for row in conn.execute("SELECT skills FROM project_contribution WHERE skills IS NOT NULL AND skills != ''"):
        for name in rules.split_list(row["skills"]):
            counts[name] = counts.get(name, 0) + 1
    for path in sorted(get_settings().people_dir.glob("*/experiences/E-*.md")):
        try:
            item = read_file(path)
        except Exception:  # noqa: BLE001 — 읽지 못하는 파일은 색인 문제 목록이 알린다
            continue
        for name in item.get("tools") or []:
            counts[name] = counts.get(name, 0) + 1
    return counts


def _skills_and_tools(merged: dict[str, Any]) -> dict[str, Any]:
    """역량 태그는 역량 사전에, 보유 기술은 보유 기술 사전에 맞춘다(273).
    역량 칸에 들어온 이름이 **보유 기술 사전에 있으면** 보유 기술 칸으로 옮긴다 — 역량 사전의 (옛) 동의어보다 먼저."""
    dictionary = settings_service.skill_dictionary()
    tool_dictionary = settings_service.tool_dictionary()
    tool_index = tool_rules.index(tool_dictionary)
    tools = list(_lines(merged.get("tools"), "도구"))
    kept = []
    for skill in _skills(merged.get("skills")):
        if skill_rules.key(skill["name"]) in tool_index:
            tools.append(skill["name"])
        else:
            kept.append(skill)
    skills = skill_rules.match(kept, dictionary)
    tools = tool_rules.normalize(tools, tool_dictionary)
    return {"skills": skills, "tools": [_text(t, "도구", 60) for t in tools][:LIST_MAX]}


def _acks(value: object) -> list[dict[str, str]]:
    out = []
    for item in value if isinstance(value, list) else []:
        if isinstance(item, dict) and item.get("code"):
            out.append({k: str(item.get(k) or "") for k in ("code", "key", "at", "by")})
    return out[:200]


# ── 1단계 검사로 잇기 ─────────────────────────────────────────────────────────

def as_block(item: dict[str, Any]) -> ParsedBlock:
    """저장된 경험 → 1단계의 블록 모양. 검사(`check` · `confirm_ready`)를 그대로 쓰려고."""
    period = item.get("start") or ""
    if item.get("end"):
        period = f"{period} ~ {item['end']}" if period else item["end"]
    block = ParsedBlock(index=0, version="0.1")
    block.fields.update({"제목": item.get("title", ""), "기간": period, "역할": item.get("role", ""), "구분": item.get("kind", ""),
                         "상황": item.get("situation", ""), "목표": item.get("goal", ""), "결과_정성": item.get("result_qual", ""),
                         "비즈니스_영향": item.get("impact", ""), "교훈": item.get("lesson", "")})
    block.lists.update({"행동": list(item.get("actions") or []), "증빙": [e["text"] for e in item.get("evidences") or []],
                        "확인_필요": list(item.get("open_questions") or [])})
    block.quants = [Quant(metric=q["metric"], value=q.get("value", ""), baseline=q.get("baseline", ""), when=q.get("when", ""),
                          baseline_kind=q.get("baseline_kind", "미확인"),
                          ask=q.get("baseline_kind") in ("집계", "조건")) for q in item.get("quants") or []]
    return block


def problems_of(item: dict[str, Any]) -> list[dict[str, str]]:
    return [{"code": p.code, "field": p.field, "message": p.message, "level": p.level}
            for p in check_block(as_block(item), item.get("status") or "초안", item.get("person", ""))]


# ── 파일 ──────────────────────────────────────────────────────────────────────

def _body(fields: dict[str, Any]) -> str:
    parts = []
    for heading in SECTIONS:
        if heading == "상황":
            text = fields["situation"]
        elif heading == "목표":
            text = fields["goal"]
        elif heading == "행동":
            text = "\n".join(f"- {line}" for line in fields["actions"])
        elif heading == "결과":
            text = fields["result_qual"]
        elif heading == "교훈":
            text = fields["lesson"]
        else:
            text = "\n".join(f"- {line}" for line in fields["open_questions"])
        parts.append(f"## {heading}\n\n{text}".rstrip() + "\n")
    return "\n".join(parts)


def _sections(body: str) -> dict[str, str]:
    found: dict[str, list[str]] = {}
    current = None
    for line in (body or "").splitlines():
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match and match.group(1) in SECTIONS:
            current = match.group(1)
            found[current] = []
        elif current:
            found[current].append(line)
    return {key: "\n".join(value).strip() for key, value in found.items()}


def _meta(experience_id: str, fields: dict[str, Any], stamps: dict[str, str]) -> dict[str, Any]:
    meta = {"id": experience_id, **{k: v for k, v in fields.items() if k not in ("situation", "goal", "actions", "result_qual", "lesson", "open_questions")},
            **stamps, "schema": 1}
    return {key: meta[key] for key in META_ORDER if key in meta and meta[key] not in ("", None)}


def read_file(path: Path) -> dict[str, Any]:
    """파일 → 경험 한 건(색인 · 화면이 쓰는 모양). 본문 절이 원본, 머리 정보는 짧은 값."""
    doc = md.load(path)
    meta, sec = doc.meta, _sections(doc.body)
    as_list = lambda text: [re.sub(r"^[-•·*]\s*", "", line).strip() for line in (text or "").splitlines() if line.strip()]  # noqa: E731
    return {
        "id": str(meta.get("id") or path.stem), "person": str(meta.get("person") or ""), "title": str(meta.get("title") or ""),
        "project": str(meta.get("project") or ""), "project_text": str(meta.get("project_text") or ""),
        "affiliation": str(meta.get("affiliation") or ""), "start": str(meta.get("start") or ""), "end": str(meta.get("end") or ""),
        "role": str(meta.get("role") or ""), "kind": str(meta.get("kind") or ""), "status": str(meta.get("status") or "초안"),
        "situation": sec.get("상황", ""), "goal": sec.get("목표", ""), "actions": as_list(sec.get("행동")),
        "result_qual": sec.get("결과", ""), "impact": str(meta.get("impact") or ""), "lesson": sec.get("교훈", ""),
        "lesson_source": str(meta.get("lesson_source") or ""), "open_questions": as_list(sec.get("확인 필요")),
        "skills": meta.get("skills") or [], "tools": [str(t) for t in meta.get("tools") or []],
        "quants": meta.get("quants") or [], "evidences": meta.get("evidences") or [],
        "related": meta.get("related") or [], "materials": meta.get("materials") or [], "source": str(meta.get("source") or ""),
        "acknowledged": meta.get("acknowledged") or [], "confirmed_at": str(meta.get("confirmed_at") or ""),
        "confirmed_by": str(meta.get("confirmed_by") or ""), "edited_by_member_at": str(meta.get("edited_by_member_at") or ""),
        "created_at": str(meta.get("created_at") or ""), "updated_at": str(meta.get("updated_at") or ""),
        "created_by": str(meta.get("created_by") or ""),
    }


def _write(path: Path, experience_id: str, fields: dict[str, Any], stamps: dict[str, str]) -> None:
    md.save(path, md.MarkdownDoc(_meta(experience_id, fields, stamps), _body(fields)))


# ── 쓰기 ──────────────────────────────────────────────────────────────────────

def create(conn: sqlite3.Connection, data: dict[str, Any], status: str = "초안") -> str:
    """새 경험. 상태는 초안 — 응답 되받기(3단계)만 `구조화` 로 만든다."""
    fields = clean({**data, "status": status}, opened=(status,))
    experience_id = next_id()
    directory = person_dir(fields["person"])
    directory.mkdir(parents=True, exist_ok=True)
    stamp = now_iso()
    _write(directory / f"{experience_id}.md", experience_id, fields,
           {"created_at": stamp, "updated_at": stamp, "created_by": settings_service.current_author(data.get("created_by")) or ""})
    reindex(conn)
    conn.commit()
    return experience_id


def update(conn: sqlite3.Connection, experience_id: str, updates: dict[str, Any], member: bool = False) -> dict[str, Any]:
    """고치기. 팀원 보완(member — 5단계.md ⑦)은 상태를 바꾸지 못하고, 고친 때를 `edited_by_member_at` 에 남긴다."""
    path = file_path(conn, experience_id)
    stored = read_file(path)
    if member:
        if stored["status"] == "확정":
            raise ExperienceError("확정한 경험은 팀장만 고칩니다.")
        updates = {k: v for k, v in updates.items() if k != "status"}
    base = updates.pop("base_updated_at", None)
    if base and base != stored["updated_at"]:
        raise ConflictError("그사이 다른 곳에서 이 경험을 고쳤습니다 — 새로 불러온 뒤 다시 고쳐 주세요.")
    fields = clean({k: v for k, v in updates.items()
                    if k not in ("id", "person", "source", "created_at", "created_by", "acknowledged", "confirmed_at", "confirmed_by",
                                 "edited_by_member_at")}, stored)
    if member:
        fields["edited_by_member_at"] = now_iso()
    _write(path, experience_id, fields,
           {"created_at": stored["created_at"], "updated_at": now_iso(), "created_by": stored["created_by"]})
    reindex(conn)
    conn.commit()
    return get(conn, experience_id)


def replace(conn: sqlite3.Connection, experience_id: str, fields: dict[str, Any], status: str) -> None:
    """응답 되받기의 "이어서" — 합친 칸 전부로 다시 쓴다(만든 때 · 만든 사람 · 출처는 그대로). 커밋은 부르는 쪽."""
    path = file_path(conn, experience_id)
    stored = read_file(path)
    cleaned = clean({**{k: v for k, v in fields.items() if k not in ("id", "person", "source", "created_at", "created_by")},
                     "status": status}, stored, opened=(status,))
    _write(path, experience_id, cleaned,
           {"created_at": stored["created_at"], "updated_at": now_iso(), "created_by": stored["created_by"]})
    reindex(conn)


def delete(conn: sqlite3.Connection, experience_id: str) -> None:
    """지우지 않고 보관함으로(면담과 같다). 번호는 다시 쓰지 않는다."""
    from . import trash as trash_service

    settings = get_settings()
    path = file_path(conn, experience_id)
    row = conn.execute("SELECT person, title FROM experience WHERE id = ?", (experience_id,)).fetchone()
    settings.trash_dir.mkdir(parents=True, exist_ok=True)
    target = paths.unique_path(settings.trash_dir, f"{experience_id}-{datetime.now():%Y%m%d%H%M%S}", ".md")
    paths.move(path, target)
    trash_service.record("experience", label=f"{experience_id} {row['person']} · {row['title']}" if row else experience_id,
                         moved_to=target, origin=path, project_id=None)
    reindex(conn)
    conn.commit()


def move_person(conn: sqlite3.Connection, old: str, new: str) -> int:
    """이름 바로잡기(214 D9)를 따라간다 — 파일의 `person` 을 바꾸고 새 이름의 폴더로. 번호(파일 이름)는 그대로."""
    rows = conn.execute("SELECT rel_path FROM experience WHERE person = ?", (old,)).fetchall()
    vault = get_settings().vault_dir
    emptied: set[Path] = set()
    for row in rows:
        path = paths.safe_join(vault, row["rel_path"])
        doc = md.load(path)
        doc.meta["person"] = new
        doc.meta["updated_at"] = now_iso()
        md.save(path, doc)
        directory = person_dir(new)
        if path.parent != directory:
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / path.name
            paths.move(path, target)
            versions.follow(path, target)
            emptied.add(path.parent)
    from .experience_import import move_responses

    move_responses(old, new)   # 응답 원문(3단계)도 함께 — 남으면 옛 폴더가 지워지지 않는다
    for folder in emptied:
        for candidate in (folder, folder.parent):
            try:
                candidate.rmdir()
            except OSError:
                break
    if rows:
        reindex(conn)
    return len(rows)


def rewrite_project_refs(mapping: dict[str, str]) -> int:
    """과제 번호가 바뀌면(renumber) 경험이 적어 둔 번호도 바꾼다(2단계.md ⑧)."""
    changed = 0
    for path in get_settings().people_dir.glob("*/experiences/E-*.md"):
        try:
            doc = md.load(path)
        except Exception:
            continue
        old = str(doc.meta.get("project") or "")
        if old in mapping and mapping[old] != old:
            doc.meta["project"] = mapping[old]
            md.save(path, doc)
            changed += 1
    return changed


# ── 담당과 역할에서 초안 (데이터모델 6절 · 2단계.md 5절) ─────────────────────────

_HAS_NUMBER = re.compile(r"\d")


def _won(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:g}억원/년"


def draft_fields(conn: sqlite3.Connection, person: str, project_id: str) -> dict[str, Any]:
    """그 사람 · 그 과제의 담당과 역할 · 회고 · 과제 개요 · 효과 금액 → 경험 초안의 칸. 저장하지 않는다."""
    from .person_history import history

    item = next((p for p in history(conn, person)["projects"] if p["id"] == project_id), None)
    if item is None:
        raise ExperienceError(f"{person} 님이 맡은 과제가 아닙니다: {project_id}")
    questions: list[str] = []
    results: list[str] = []
    for line in [item["result"], item["outcome"]] + [f"{m['date']} {m['text']}" for m in item["milestones"]]:
        for piece in (line or "").splitlines():
            piece = re.sub(r"^[-•·*]\s*", "", piece).strip()
            if not piece:
                continue
            results.append(piece)
            # 2단계.md ⑤ — 숫자는 정량으로 옮기지 않고 기준을 묻는다(기준 없는 숫자가 성과처럼 굳지 않게)
            if _HAS_NUMBER.search(re.sub(r"^\d{4}-\d{2}-\d{2}\s*", "", piece)):
                questions.append(f"‘{piece[:40]}’ 의 비교 기준은 무엇인가요?")
    quants = []
    # 효과 금액 — 사내 시스템이라 가져온다(사용자, 2026-11-10). 과제 전체의 금액이라 본인 몫을 묻는다
    end_year = (item["to"] or "")[:4] or ""
    for label, value in (("과제 기대효과", item["effect_expected"]), ("과제 실증효과", item["effect_verified"])):
        if value:
            quants.append({"metric": label, "value": _won(value), "baseline": "과제 전체 금액(본인 몫 아님)",
                           "baseline_kind": "집계", "when": end_year})
    if quants:
        questions.append("과제 효과 금액 중 본인이 기여한 몫은 얼마인가요?")
    role = " · ".join(part for part in (item["role"], item["part"]) if part)
    return {
        "person": person, "title": item["title"], "project": project_id,
        # 끝 — 담당이 끝났거나 과제가 끝났으면 그날(지금 맡고 있어도 끝난 과제면 끝이 있다), 아니면 진행 중
        "start": (item["from"] or "")[:7], "end": (item["to"] or "")[:7],
        "role": role, "kind": "업무", "situation": item["context"]["background"], "goal": item["context"]["goal"],
        "actions": [re.sub(r"^[-•·*]\s*", "", line).strip() for line in (item["did"] or "").splitlines() if line.strip()],
        "result_qual": "\n".join(results), "open_questions": questions, "quants": quants,
        # 261 — 기술 · 도구는 역량 태그가 아니라 도구 칸으로
        "tools": list(item["skills"]),
        "materials": [f"entry:{entry['id']} {entry['date']} {entry['title']}" for entry in item["star_entries"]],
        "source": "담당",
    }


def has_retro(conn: sqlite3.Connection, person: str, project_id: str) -> bool:
    row = conn.execute("SELECT did, result FROM project_contribution WHERE name = ? AND project_id = ?", (person, project_id)).fetchone()
    return bool(row and ((row["did"] or "").strip() or (row["result"] or "").strip()))


def create_drafts(conn: sqlite3.Connection, person: str, project_ids: list[str]) -> dict[str, Any]:
    """과제마다 초안 하나. 그 사람 · 그 과제의 경험이 이미 있으면 건너뛴다(한 과제에 여럿은 [+ 새 경험]으로)."""
    made, skipped = [], []
    for project_id in project_ids:
        exists = conn.execute("SELECT id FROM experience WHERE person = ? AND project_id = ?", (person, project_id)).fetchone()
        if exists:
            skipped.append({"project": project_id, "reason": f"이미 있음({exists['id']})"})
            continue
        made.append(create(conn, draft_fields(conn, person, project_id)))
    return {"made": made, "skipped": skipped}


# ── 읽기 · 색인 ───────────────────────────────────────────────────────────────

def _summary_row(row: sqlite3.Row, project_titles: dict[str, str]) -> dict[str, Any]:
    return {
        "id": row["id"], "person": row["person"], "title": row["title"], "project": row["project_id"] or "",
        "project_title": project_titles.get(row["project_id"] or "", ""),
        "project_gone": bool(row["project_id"]) and row["project_id"] not in project_titles,
        "start": row["start"] or "", "end": row["end"] or "", "status": row["status"], "open_count": row["open_count"],
        "source": row["source"] or "", "updated_at": row["updated_at"] or "",
    }


def listing(conn: sqlite3.Connection, person: str) -> dict[str, Any]:
    titles = {r["id"]: r["title"] for r in conn.execute("SELECT id, title FROM project")}
    rows = conn.execute("SELECT * FROM experience WHERE person = ? ORDER BY COALESCE(start, '') DESC, id DESC", (person,)).fetchall()
    full = {row["id"]: get_row(conn, row) for row in rows}
    found = consistency(conn, person, list(full.values()))
    items = []
    for row in rows:
        summary = _summary_row(row, titles)
        open_warnings = [w for w in found.get(row["id"], []) if not w["acknowledged"]]
        summary["warn_count"] = sum(1 for p in problems_of(full[row["id"]]) if p["level"] == "경고") + len(open_warnings)
        items.append(summary)
    counts = {status: sum(1 for item in items if item["status"] == status) for status in STATUSES}
    # 사람별 역량 칩(4단계.md ⑩) — 축 · 이름 · 경험 수 · 사전에 있나
    known = {(d["axis"], d["name"]) for d in settings_service.skill_dictionary()}
    tally: dict[tuple[str, str], int] = {}
    for item in full.values():
        for skill in item["skills"] if isinstance(item["skills"], list) else []:
            if isinstance(skill, dict) and skill.get("name"):
                mark = (skill.get("axis") or "기술", skill["name"])
                tally[mark] = tally.get(mark, 0) + 1
    skills = [{"axis": axis, "name": name, "count": count, "known": (axis, name) in known}
              for (axis, name), count in sorted(tally.items(), key=lambda pair: (AXES.index(pair[0][0]) if pair[0][0] in AXES else 9, -pair[1], pair[0][1]))]
    return {"items": items, "counts": counts, "total": len(items), "skills": skills,
            "tools": tool_summary(conn, person, list(full.values()))}


def tool_summary(conn: sqlite3.Connection, person: str, items: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """한 사람의 보유 기술 요약(TODO 273) — 과제(담당과 역할)와 경험을 합쳐 이름마다 과제 수 · 경험 수 · 마지막으로 쓴 해 · 사전에 있나.
    `items` 가 None 이면 과제만(경험을 볼 수 없는 화면)."""
    from .. import schemas as rules

    dictionary = settings_service.tool_dictionary()
    known = set(tool_rules.index(dictionary))
    rows: dict[str, dict[str, Any]] = {}

    def add(name: str, kind: str, year: str) -> None:
        row = rows.setdefault(skill_rules.key(name), {"name": name, "projects": 0, "experiences": 0, "last": ""})
        row[kind] += 1
        if year and year > row["last"]:
            row["last"] = year

    this_year = str(clock.today().year)
    for row in conn.execute(
            "SELECT c.skills, c.from_date, c.to_date, c.current, p.start_date, p.due_date FROM project_contribution c"
            " JOIN project p ON p.id = c.project_id WHERE c.name = ? AND c.skills IS NOT NULL AND c.skills != ''", (person,)):
        year = (row["to_date"] or "")[:4] or (this_year if row["current"] else (row["due_date"] or row["from_date"] or row["start_date"] or "")[:4])
        for name in tool_rules.normalize(rules.split_list(row["skills"]), dictionary):
            add(name, "projects", min(year, this_year) if year else "")
    for item in items or []:
        year = (item.get("end") or "")[:4] or ((this_year if item.get("start") else ""))
        for name in tool_rules.normalize(item.get("tools") or [], dictionary):
            add(name, "experiences", min(year, this_year) if year else "")
    out = [{**row, "known": skill_rules.key(row["name"]) in known} for row in rows.values()]
    return sorted(out, key=lambda r: (-(r["projects"] + r["experiences"]), r["name"]))


def tool_notes(item: dict[str, Any]) -> list[str]:
    """확정 전에 알릴 것(TODO 273 — 막지 않는다): 보유 기술이 비었거나, 글에 사전의 이름이 있는데 칸에 없다."""
    dictionary = settings_service.tool_dictionary()
    have = {skill_rules.key(name) for name in tool_rules.normalize(item.get("tools") or [], dictionary)}
    text = "\n".join([item.get("role") or "", item.get("situation") or "", *(item.get("actions") or []), item.get("result_qual") or ""])
    missing = [name for name in tool_rules.mentioned(text, dictionary) if skill_rules.key(name) not in have]
    notes = []
    if missing:
        notes.append(f"글에 나오는 보유 기술이 칸에 없습니다 — {', '.join(missing[:8])}")
    elif not have:
        notes.append("보유 기술이 비어 있습니다 — 이 일에 쓴 언어 · 소프트웨어 · 장비가 있으면 적어 주세요(없으면 그대로 둡니다).")
    return notes


def rematch_tools(conn: sqlite3.Connection) -> dict[str, Any]:
    """[사전에 다시 맞추기](TODO 273) — 보유 기술 사전을 고친 뒤 모든 경험의 보유 기술 · 역량 태그와 과제 색인을 지금 사전으로."""
    from ..vault.indexer import reindex_all

    changed = _rewrite_skills(conn, sorted(get_settings().people_dir.glob("*/experiences/E-*.md")), lambda skills: skills)
    reindex_all(conn)
    conn.commit()
    return {"changed": changed}


# ── 정합성 · 확정 (4단계.md 3 · 4절) ─────────────────────────────────────────────

def _spans(conn: sqlite3.Connection, person: str) -> dict[str, tuple[str, str]]:
    from .person_history import history

    return {p["id"]: ((p["from"] or "")[:7], (p["to"] or "")[:7]) for p in history(conn, person)["projects"]}


def consistency(conn: sqlite3.Connection, person: str, items: list[dict[str, Any]] | None = None) -> dict[str, list[dict[str, Any]]]:
    """그 사람의 경험끼리 정합성 경고 — 경험 번호 → [{code, key, message, label, acknowledged, ack_at, ack_by}]."""
    if items is None:
        items = [get_row(conn, row) for row in conn.execute("SELECT * FROM experience WHERE person = ?", (person,))]
    found = consistency_rules.check_person(items, _spans(conn, person))
    out: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        acks = {(a.get("code"), a.get("key")): a for a in item.get("acknowledged") or [] if isinstance(a, dict)}
        rows = []
        for warning in found.get(item["id"], []):
            ack = acks.get((warning.code, warning.key))
            rows.append({**warning.as_dict(), "acknowledged": bool(ack), "ack_at": (ack or {}).get("at", ""), "ack_by": (ack or {}).get("by", "")})
        out[item["id"]] = rows
    return out


def confirm_missing(item: dict[str, Any], warnings: list[dict[str, Any]]) -> list[str]:
    """확정 조건 다섯(원본 4절 · FR-E6) 중 못 맞춘 것 — 1 ~ 4 는 1단계 `confirm_ready`, 5 = 정합성 경고를 모두 [확인함]."""
    missing = confirm_ready(as_block(item), item["person"])
    left = [w for w in warnings if not w["acknowledged"]]
    if left:
        missing.append(f"5. 정합성 경고 {len(left)}건 — 고치거나 [확인함]으로 넘깁니다")
    return missing


def _set_status(conn: sqlite3.Connection, experience_id: str, status: str, extra: dict[str, Any]) -> dict[str, Any]:
    path = file_path(conn, experience_id)
    stored = read_file(path)
    fields = clean({**stored, **extra, "status": status}, stored, opened=(status,))
    _write(path, experience_id, fields, {"created_at": stored["created_at"], "updated_at": now_iso(), "created_by": stored["created_by"]})
    reindex(conn)
    conn.commit()
    return get(conn, experience_id)


def confirm(conn: sqlite3.Connection, experience_id: str, by: str = "") -> dict[str, Any]:
    """[확정하기] — 조건 다섯을 서버가 다시 본다(화면을 믿지 않는다). 초안에서도 조건만 맞으면 된다(4단계.md ⑥)."""
    item = get(conn, experience_id)
    if item["status"] == "확정":
        raise ExperienceError("이미 확정한 경험입니다.")
    if item["confirm_missing"]:
        raise ExperienceError("확정하려면 아래가 남았습니다: " + " / ".join(item["confirm_missing"]))
    who = by or settings_service.current_author(None) or ""
    # 팀장이 확정하면 "팀원이 고침" 표시는 검토를 마친 것으로 지운다(이전 버전에 남음)
    return _set_status(conn, experience_id, "확정", {"confirmed_at": now_iso(), "confirmed_by": who, "edited_by_member_at": ""})


def unconfirm(conn: sqlite3.Connection, experience_id: str) -> dict[str, Any]:
    """[구조화로 되돌림] — 확정한 때 · 사람은 지운다(이전 버전에 남는다)."""
    if get(conn, experience_id)["status"] != "확정":
        raise ExperienceError("확정한 경험만 되돌립니다.")
    return _set_status(conn, experience_id, "구조화", {"confirmed_at": "", "confirmed_by": ""})


def acknowledge(conn: sqlite3.Connection, experience_id: str, code: str, key: str, by: str = "") -> dict[str, Any]:
    """정합성 경고 하나를 [확인함] — 지금 있는 경고에만(누가 · 언제를 남긴다, 원본 FR-F2)."""
    item = get(conn, experience_id)
    if not any(w["code"] == code and w["key"] == key for w in item["consistency"]):
        raise ExperienceError("그 경고는 지금 없습니다 — 새로 불러온 뒤 다시 하세요.")
    acks = [a for a in item["acknowledged"] if not (a.get("code") == code and a.get("key") == key)]
    acks.append({"code": code, "key": key, "at": now_iso(), "by": by or settings_service.current_author(None) or ""})
    return _set_status(conn, experience_id, item["status"], {"acknowledged": acks})


# ── 역량 사전 — 합치기 · 다시 맞추기 (4단계.md 2절) ────────────────────────────

def skill_usage(conn: sqlite3.Connection) -> dict[str, int]:
    return {f"{r['axis']}|{r['name']}": r["n"] for r in conn.execute(
        "SELECT axis, name, COUNT(DISTINCT experience_id) AS n FROM experience_skill GROUP BY axis, name")}


def _rewrite_skills(conn: sqlite3.Connection, paths_: list[Path], change) -> list[str]:
    changed = []
    for path in paths_:
        stored = read_file(path)
        skills = change(list(stored["skills"]))
        fields = clean({**stored, "skills": skills}, stored, opened=(stored["status"],))
        if fields["skills"] == stored["skills"] and fields["tools"] == stored["tools"]:
            continue
        _write(path, stored["id"], fields, {"created_at": stored["created_at"], "updated_at": now_iso(), "created_by": stored["created_by"]})
        changed.append(stored["id"])
    return changed


def merge_skill(conn: sqlite3.Connection, source: dict[str, str], target: dict[str, str]) -> dict[str, Any]:
    """사전의 한 역량을 다른 역량으로 합친다 — 경험의 태그를 바꾸고, 옛 이름은 대상의 동의어로 남긴다."""
    src = (str(source.get("axis") or ""), " ".join(str(source.get("name") or "").split()))
    dst = (str(target.get("axis") or ""), " ".join(str(target.get("name") or "").split()))
    if not src[1] or not dst[1] or src == dst or dst[0] not in AXES:
        raise ExperienceError("합칠 역량 둘을 골라 주세요.")
    dictionary = settings_service.skill_dictionary()
    if not any((d["axis"], d["name"]) == dst for d in dictionary):
        raise ExperienceError(f"사전에 없는 역량으로는 합치지 않습니다: {dst[1]}")
    out = []
    for entry in dictionary:
        if (entry["axis"], entry["name"]) == src:
            continue
        if (entry["axis"], entry["name"]) == dst:
            entry = {**entry, "aliases": list(dict.fromkeys([*entry.get("aliases", []), src[1]]))}
        out.append(entry)
    settings_service.save({"skill_dictionary": out})
    changed = _rewrite_skills(conn, sorted(get_settings().people_dir.glob("*/experiences/E-*.md")),
                              lambda skills: [{"axis": dst[0], "name": dst[1]} if (s.get("axis"), s.get("name")) == src else s for s in skills])
    reindex(conn)
    conn.commit()
    return {"changed": changed}


def rename_skill_tags(conn: sqlite3.Connection, source: dict[str, str], target: dict[str, str]) -> dict[str, Any]:
    """사전에서 이름 · 축을 고친 역량(TODO 275) — 쓰는 경험의 태그를 새 이름 · 축으로. 사전은 이미 저장돼 있어야 한다."""
    src = (str(source.get("axis") or ""), " ".join(str(source.get("name") or "").split()))
    dst = (str(target.get("axis") or ""), " ".join(str(target.get("name") or "").split()))
    if not src[1] or not dst[1] or dst[0] not in AXES:
        raise ExperienceError("바꿀 역량 둘을 골라 주세요.")
    if src == dst:
        return {"changed": []}
    if not any((d["axis"], d["name"]) == dst for d in settings_service.skill_dictionary()):
        raise ExperienceError(f"사전에 없는 역량으로는 바꾸지 않습니다: {dst[1]}")
    changed = _rewrite_skills(conn, sorted(get_settings().people_dir.glob("*/experiences/E-*.md")),
                              lambda skills: [{"axis": dst[0], "name": dst[1]} if (s.get("axis"), s.get("name")) == src else s for s in skills])
    reindex(conn)
    conn.commit()
    return {"changed": changed}


def rematch_person(conn: sqlite3.Connection, person: str) -> dict[str, Any]:
    """[사전에 다시 맞추기] — 그 사람의 경험 태그를 지금 사전으로 다시 맞춘다(사전을 고친 뒤)."""
    paths_ = [paths.safe_join(get_settings().vault_dir, r["rel_path"]) for r in conn.execute(
        "SELECT rel_path FROM experience WHERE person = ?", (person,))]
    changed = _rewrite_skills(conn, paths_, lambda skills: skill_rules.match(skills, settings_service.skill_dictionary()))
    reindex(conn)
    conn.commit()
    return {"changed": changed}


def get_row(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    return read_file(paths.safe_join(get_settings().vault_dir, row["rel_path"]))


def get(conn: sqlite3.Connection, experience_id: str) -> dict[str, Any]:
    item = read_file(file_path(conn, experience_id))
    project = conn.execute("SELECT title FROM project WHERE id = ?", (item["project"],)).fetchone() if item["project"] else None
    warnings = consistency(conn, item["person"]).get(item["id"], [])
    return {**item, "project_title": project["title"] if project else "", "project_gone": bool(item["project"]) and not project,
            "problems": problems_of(item),
            "consistency": warnings,
            "skills_unknown": skill_rules.unknown(item["skills"], settings_service.skill_dictionary()),
            "tool_notes": tool_notes(item) if item["status"] != "확정" else [],
            "confirm_missing": confirm_missing(item, warnings)}


def reindex(conn: sqlite3.Connection, problems: list | None = None) -> int:
    """사람 폴더의 경험을 색인한다(시작 · [다시 읽기] · 쓸 때마다). 번호가 겹치면 먼저 읽은 것만 — 알린다."""
    from ..vault.indexer import IndexProblem

    settings = get_settings()
    root = settings.vault_dir
    conn.execute("DELETE FROM experience_skill")
    conn.execute("DELETE FROM experience_quant")
    conn.execute("DELETE FROM experience")
    count = 0
    for path in sorted(settings.people_dir.glob("*/experiences/E-*.md")):
        rel = path.relative_to(root).as_posix()
        try:
            item = read_file(path)
        except Exception as exc:  # 못 읽는 파일은 알리고 건너뛴다(다른 색인과 같다)
            if problems is not None:
                problems.append(IndexProblem(rel, f"경험 파일을 읽지 못했습니다: {exc}"))
            continue
        if conn.execute("SELECT 1 FROM experience WHERE id = ?", (item["id"],)).fetchone():
            if problems is not None:
                problems.append(IndexProblem(rel, f"같은 번호 {item['id']} 의 경험 파일이 둘입니다 — 하나만 보입니다."))
            continue
        conn.execute(
            "INSERT INTO experience(id, person, rel_path, title, project_id, project_text, start, end, role, kind, status,"
            " situation, goal, actions, result_qual, impact, lesson, lesson_source, open_questions, open_count, source,"
            " created_at, updated_at, created_by, file_mtime) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (item["id"], item["person"] or path.parent.parent.name, rel, item["title"] or item["id"], item["project"] or None,
             item["project_text"], item["start"], item["end"], item["role"], item["kind"], item["status"], item["situation"],
             item["goal"], json.dumps(item["actions"], ensure_ascii=False), item["result_qual"], item["impact"], item["lesson"],
             item["lesson_source"], json.dumps(item["open_questions"], ensure_ascii=False), len(item["open_questions"]),
             item["source"], item["created_at"], item["updated_at"], item["created_by"], path.stat().st_mtime),
        )
        for position, quant in enumerate(item["quants"] if isinstance(item["quants"], list) else []):
            if isinstance(quant, dict):
                conn.execute("INSERT INTO experience_quant VALUES (?,?,?,?,?,?,?)",
                             (item["id"], position, quant.get("metric"), quant.get("value"), quant.get("baseline"),
                              quant.get("baseline_kind"), quant.get("when")))
        for skill in item["skills"] if isinstance(item["skills"], list) else []:
            if isinstance(skill, dict) and skill.get("name"):
                conn.execute("INSERT INTO experience_skill VALUES (?,?,?)", (item["id"], skill.get("axis"), skill["name"]))
        count += 1
    return count
