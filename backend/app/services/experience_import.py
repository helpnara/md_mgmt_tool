"""응답 되받기 (TODO 258 · 253 의 3단계 — 설계는 docs/팀원이력정리/3단계.md).

경험 정리 프롬프트 → (사람이 사내 AI 에 붙여 넣고) → 응답 붙여넣기 → 미리보기 → 저장.
앱은 AI 를 부르지 않는다(71). 프롬프트는 **먼저 보여 주고** 복사한다.

* 프롬프트의 바탕은 설계 원본 `docs/prompts/structure_entry.md` v0.1.1(규칙 1 ~ 8 · 출력 형식) — 기록은 244 STAR 정리 프롬프트와 같은 묶음.
  **넣지 않는 것** — 팀원 이름 · 효과 금액(3단계.md ⑤ — 밖으로 나가는 글) · 면담.
* 응답 원문은 [읽기] 하는 순간 `people/<이름>/experiences/responses/YYYY-MM-DD-nn.md` 에 남긴다(블록 0개여도 — 파서 규칙 15 · 원본 FR-B3).
  고치지 않는다. [더 붙여넣기] 는 같은 파일에 덧붙인다.
* 저장은 **서버가 원문을 다시 읽어서** 한다 — 화면이 보낸 블록 값을 믿지 않는다. 화면은 블록 번호 · 저장 방법 · 과제 · 칸 고르기만 보낸다.
* 이어서 저장할 때 칸이 부딪히면(3단계.md ④) 기본은 **사람이 고친 적 없는 경험이면 AI 값, 고쳤으면 기존 값**(원본 FR-C7).
  확인 필요 · 역량 태그 · 정량 · 증빙 · 재료는 합친다 — 초안의 효과 금액 · "본인 몫" 질문이 남는다.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from .. import clock
from ..experience.check import check as check_block
from ..experience.parse import ParsedBlock, ParseResult, parse
from ..experience.period import parse_period
from ..vault import markdown as md
from ..vault import paths
from . import experiences as exp
from . import settings as settings_service

ACTIONS = ("새로", "이어서", "버림")
RESPONSE_MAX = 300_000          # 붙여넣기 한 번의 글자 수 — 사내 AI 응답 여러 개를 이어도 넉넉하다
RECENT_MAX = 20                 # 프롬프트의 기존 경험 목록(원본 FR-C1)
NAME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{2,}$")
APPEND_MARK = "\n\n--- 이어 붙인 응답 ---\n\n"
ROLE_SUBJECT_WARNING = "본인이 한 일과 다른 주체가 한 일을 구분해 주세요"
_SELF_WORDS = ("본인", "직접", "내가", "제가", "혼자", "단독")

# 칸 비교에 쓰는 칸 — (경험 칸, 보이는 이름). 기간은 시작 · 끝을 한 칸으로 본다
COMPARE_FIELDS = (
    ("title", "제목"), ("period", "기간"), ("role", "역할"), ("kind", "구분"), ("situation", "상황"), ("goal", "목표"),
    ("actions", "행동"), ("result_qual", "결과(정성)"), ("impact", "영향"), ("lesson", "교훈"), ("affiliation", "소속"),
)


# ── 프롬프트 (3단계.md 2절) ──────────────────────────────────────────────────

PROMPT_HEAD = """[역할]
당신은 제조 · 데이터 분석 업무를 잘 아는 업무 성과 정리 코치입니다.
아래 [기록]은 사내 과제 관리 도구에 한 사람이 남긴 과제 기록입니다. 이 사람이 겪은 일을 경험 블록으로 정리해 주세요.

[규칙]
1. 기록에 있는 사실만 씁니다. 없는 상황 · 행동 · 결과 · 수치를 만들지 않습니다. 빈 칸은 비워 두고 "확인_필요"에 질문으로 적습니다.
2. 질문은 "없음"이 정상 답변일 수 있는 열린 질문으로 씁니다. (좋음: "이 일의 결과를 보여 주는 수치가 있는가?" / 나쁨: "몇 % 개선됐는가?")
3. 질문은 블록마다 3개 이내. 결과 · 수치 · 본인 역할 순으로 중요합니다.
4. 수치는 기록에 있는 것만. 비교 기준이 없으면 "기준 없음"이라고 쓰고 "개선 · 단축 · 증가"를 붙이지 않습니다.
5. 역량은 아래 [역량 목록]에 있는 이름을 우선 씁니다. 목록에 없으면 새 이름을 쓰되 "확인_필요"에 "새 역량: …"으로 적습니다.
6. 아래 [기존 경험 목록] 중 이 기록이 이어지는 경험이 있으면 "이어짐: E-nnn"을 적습니다. 새 경험이면 "이어짐: 없음". 확실하지 않으면 "이어짐: E-nnn?" 처럼 물음표를 붙입니다.
7. "교훈"은 기록에 교훈 · 원칙 · 느낀 점이 적혀 있을 때만 채웁니다.
8. "역할"에는 본인이 직접 한 일과 다른 주체(팀원, 외부 기업, AI 도구)가 한 일을 구분해 적습니다. 기록에 주체가 없으면 "확인_필요"에 "본인이 직접 수행했는지"를 적습니다.
9. 과제 하나에서 경험이 여럿이면 블록도 여럿입니다. 블록 하나에 경험 하나.
10. 사람 이름 · 부서명 · 라인 번호 · 사내 시스템명은 일반화합니다(예: "냉연 2라인" → "냉연 공정 라인"). 금액은 쓰지 않습니다.

[출력 형식]
- 아래 모양의 블록만 출력합니다. 블록 밖에 설명을 쓰지 않습니다.
- 블록은 반드시 ```slow-way 로 시작하고 ``` 로 끝냅니다.
- 키는 아래 이름만 쓰고, 값이 없어도 키를 빼지 않습니다.
- 목록 키(행동, 결과_정량, 증빙, 확인_필요)는 다음 줄부터 "- "로 시작하는 항목을 나열합니다.
- 결과_정량 항목은 "지표 | 값 | 기준: … | 시점: …" 네 칸을 | 로 나눕니다.
- 회사 · 조직 · 직위는 지금 회사의 과제면 비워 둡니다.

```slow-way
형식: slow-way-experience/0.1
이어짐:
제목:
기간: YYYY-MM ~ YYYY-MM
회사:
조직:
직위:
역할:
구분: 업무
상황:
목표:
행동:
-
결과_정량:
- 지표 | 값 | 기준: | 시점:
결과_정성:
비즈니스_영향:
역량_기술:
역량_업무:
역량_리더십:
역량_문제해결:
교훈:
증빙:
-
확인_필요:
-
```
"""


def _period(item: dict[str, Any]) -> str:
    start = (item.get("from") or "")[:7]
    end = (item.get("to") or "")[:7]
    if item.get("status") == "dropped" and not item.get("to"):
        return f"{start or '?'} ~ 중단"
    return f"{start or '?'} ~ {end or '지금'}"


def record_text(item: dict[str, Any], index: int) -> str:
    """과제 하나의 기록 — 244 STAR 정리 프롬프트(화면 `refinePrompt`)와 같은 칸 · 같은 순서. 과제 번호를 함께 적는다."""
    lines = [f"## 과제 {index}. {item['title']} ({item['id']})",
             f"- 기간: {_period(item)}{' (완료)' if item['status'] == 'done' else ''}"]
    context = item.get("context") or {}
    if context.get("background"):
        lines.append(f"- 배경: {context['background']}")
    if context.get("goal"):
        lines.append(f"- 목표: {context['goal']}")
    if item.get("role"):
        lines.append(f"- 역할: {item['role']}")
    if item.get("part"):
        lines.append(f"- 맡은 부분: {item['part']}")
    if item.get("skills"):
        lines.append(f"- 기술 · 도구: {', '.join(item['skills'])}")
    if item.get("milestones"):
        lines.append("- 중간 성과:")
        lines += [f"  - {m['date']} {m['text']}" for m in item["milestones"]]
    if item.get("star_entries"):
        lines.append("- 성과 후보 일지:")
        lines += [f"  - {e['date']} {e['title']}{(' — ' + e['first_line']) if e.get('first_line') else ''}"
                  for e in item["star_entries"]]
    for key, label in (("did", "내가 한 일"), ("result", "결과")):
        text = (item.get(key) or "").strip()
        if not text:
            continue
        if "\n" in text:
            lines.append(f"- {label}:")
            for row in (r.strip() for r in text.splitlines()):
                if row:
                    lines.append(f"  {row if row.startswith('- ') else '- ' + row}")
        else:
            lines.append(f"- {label}: {text}")
    if item.get("outcome"):
        lines.append(f"- 그 밖의 성과: {item['outcome']}")
    return "\n".join(lines)


def _structured_projects(conn: sqlite3.Connection, person: str) -> set[str]:
    return {r["project_id"] for r in conn.execute(
        "SELECT DISTINCT project_id FROM experience WHERE person = ? AND status IN ('구조화', '확정') AND project_id IS NOT NULL",
        (person,))}


def choices(conn: sqlite3.Connection, person: str) -> list[dict[str, Any]]:
    """고를 수 있는 과제 — 그 사람이 맡은 과제 전부. `default` = 회고가 있고 아직 구조화 · 확정 경험이 없는 과제."""
    from .person_history import history

    structured = _structured_projects(conn, person)
    out = []
    for item in history(conn, person)["projects"]:
        retro = bool((item["did"] or "").strip() or (item["result"] or "").strip())
        out.append({"id": item["id"], "title": item["title"], "period": _period(item), "retro": retro,
                    "structured": item["id"] in structured, "default": retro and item["id"] not in structured})
    return out


def build_prompt(conn: sqlite3.Connection, person: str, project_ids: list[str] | None) -> dict[str, Any]:
    """경험 정리 프롬프트. 과제를 고르지 않으면(None) 기본 과제. 과제 수는 막지 않는다(사용자 2026-11-10 — 사내 AI 한도 없음)."""
    from .person_history import history

    projects = {item["id"]: item for item in history(conn, person)["projects"]}
    listed = choices(conn, person)
    chosen = [c["id"] for c in listed if c["default"]] if project_ids is None else list(dict.fromkeys(project_ids))
    for project_id in chosen:
        if project_id not in projects:
            raise exp.ExperienceError(f"{person} 님이 맡은 과제가 아닙니다: {project_id}")
    recent = conn.execute(
        "SELECT id, title, start, end, project_id FROM experience WHERE person = ? ORDER BY updated_at DESC, id DESC LIMIT ?",
        (person, RECENT_MAX)).fetchall()
    skills: dict[str, list[str]] = {}
    for row in conn.execute(
            "SELECT DISTINCT s.axis, s.name FROM experience_skill s JOIN experience e ON e.id = s.experience_id"
            " WHERE e.person = ? ORDER BY s.axis, s.name", (person,)):
        skills.setdefault(row["axis"] or "기술", []).append(row["name"])
    parts = [PROMPT_HEAD, "[역량 목록]"]
    parts += [f"- {axis}: {', '.join(skills[axis])}" for axis in exp.AXES if skills.get(axis)] or ["(아직 없음)"]
    parts += ["", f"[기존 경험 목록] (최근 {RECENT_MAX}건: 번호 | 제목 | 기간 | 과제)"]
    parts += [f"- {r['id']} | {r['title']} | {r['start'] or '?'} ~ {r['end'] or '?'} | {r['project_id'] or '-'}" for r in recent] or ["(없음)"]
    parts += ["", "[기록]"]
    parts += [record_text(projects[pid], index) + "\n" for index, pid in enumerate(chosen, start=1)] or ["(고른 과제가 없습니다)"]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(parts)).rstrip() + "\n"
    return {"person": person, "text": text if chosen else "", "chars": len(text) if chosen else 0, "projects": chosen,
            "existing": len(recent), "choices": listed}


# ── 응답 원문 (3단계.md 3절) ──────────────────────────────────────────────────

def responses_dir(person: str) -> Path:
    return exp.person_dir(person) / "responses"


def _response_path(person: str, name: str) -> Path:
    if not NAME_PATTERN.match(name or ""):
        raise KeyError(name)
    path = responses_dir(person) / f"{name}.md"
    if not path.exists():
        raise KeyError(name)
    return path


def _new_response_path(person: str) -> Path:
    directory = responses_dir(person)
    directory.mkdir(parents=True, exist_ok=True)
    day = clock.today().isoformat()
    numbers = [int(p.stem.rsplit("-", 1)[1]) for p in directory.glob(f"{day}-*.md") if NAME_PATTERN.match(p.stem)]
    return directory / f"{day}-{max(numbers, default=0) + 1:02d}.md"


def response_ref(name: str) -> str:
    """경험의 재료 칸에 적는 응답 원문 — 화면이 링크로 바꾼다."""
    return f"response:{name}"


def read_response_file(person: str, name: str) -> dict[str, Any]:
    doc = md.load(_response_path(person, name))
    meta = doc.meta
    return {"name": name, "person": str(meta.get("person") or person), "created_at": str(meta.get("created_at") or ""),
            "created_by": str(meta.get("created_by") or ""), "projects": meta.get("projects") or [],
            "blocks": meta.get("blocks") or 0, "saved": meta.get("saved") or [], "text": doc.body}


# ── 블록 → 경험 칸 (3단계.md 5절) ─────────────────────────────────────────────

def _cut(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _split_names(text: str) -> list[str]:
    return [name.strip() for name in re.split(r"[,，、·/]", text or "") if name.strip()]


def block_fields(block: ParsedBlock) -> dict[str, Any]:
    """읽은 블록 → 경험 칸(저장 전 모양). 칸 길이는 저장 한도에 맞춰 자른다 — 긴 응답 하나로 저장 전체가 막히지 않게."""
    start, end, _ = parse_period(block.get("기간"))
    questions = list(block.lists.get("확인_필요") or [])
    kind = block.get("구분")
    if kind and kind not in exp.KINDS:
        questions.append(f"구분 ‘{_cut(kind, 20)}’ — 업무 · 업무 외 중 무엇인가요?")
        kind = ""
    for key, value in block.unknown.items():   # 원본 규칙 6 — 모르는 키는 버리지 않는다
        questions.append(_cut(f"AI 가 더 적은 칸 — {key}: {value}", 500))
    skills = [{"axis": axis, "name": _cut(name, 60)}
              for axis in exp.AXES for name in _split_names(block.get(f"역량_{axis}"))]
    quants = [{"metric": _cut(q.metric, 200), "value": _cut(q.value, 200), "baseline": _cut(q.baseline, 200) or "기준 없음",
               "baseline_kind": q.baseline_kind if q.baseline_kind in exp.BASELINE_KINDS else "미확인", "when": _cut(q.when, 40)}
              for q in block.quants if q.metric.strip()]
    affiliation = " · ".join(part for part in (block.get("회사"), block.get("조직"), block.get("직위")) if part)
    return {
        "title": _cut(block.get("제목"), exp.TITLE_MAX) or f"이름 없는 경험 (블록 {block.index + 1})",
        "start": start or "", "end": end or "", "role": _cut(block.get("역할"), 500), "kind": kind,
        "situation": _cut(block.get("상황"), exp.TEXT_MAX), "goal": _cut(block.get("목표"), exp.TEXT_MAX),
        "actions": [_cut(line, 500) for line in block.lists.get("행동") or []][: exp.LIST_MAX],
        "result_qual": _cut(block.get("결과_정성"), exp.TEXT_MAX), "impact": _cut(block.get("비즈니스_영향"), 500),
        "lesson": _cut(block.get("교훈"), exp.TEXT_MAX), "lesson_source": _cut(block.lesson_source, 100),
        "open_questions": [_cut(q, 500) for q in questions][: exp.LIST_MAX], "skills": skills[: exp.LIST_MAX],
        "quants": quants[: exp.LIST_MAX], "affiliation": _cut(affiliation, 100),
        "evidences": [{"type": "문서", "text": _cut(text, 300), "year": "", "file": ""} for text in block.lists.get("증빙") or []][: exp.LIST_MAX],
    }


def role_warning(role: str) -> str:
    """원본 FR-C10 — 역할이 비었거나 본인 몫이 드러나지 않으면 묻는다(저장은 막지 않는다)."""
    return "" if role and any(word in role for word in _SELF_WORDS) else ROLE_SUBJECT_WARNING


def _value(item: dict[str, Any], key: str) -> str:
    if key == "period":
        return f"{item.get('start') or ''} ~ {item.get('end') or ''}" if (item.get("start") or item.get("end")) else ""
    value = item.get(key)
    if isinstance(value, list):
        return "\n".join(str(v) for v in value)
    return str(value or "")


def touched(item: dict[str, Any]) -> bool:
    """사람이 고친 적이 있나 — 만든 뒤 고친 때가 바뀌었거나, 사람이 직접 쓴 경험."""
    return item.get("source") == "직접" or (item.get("updated_at") or "") != (item.get("created_at") or "")


def compare(old: dict[str, Any], new: dict[str, Any]) -> list[dict[str, Any]]:
    """둘 다 값이 있고 다른 칸 — 화면이 나란히 보이고 고르게 한다. `default` 는 3단계.md ④."""
    default = "old" if touched(old) else "new"
    return [{"field": key, "label": label, "old": _value(old, key), "new": _value(new, key), "default": default}
            for key, label in COMPARE_FIELDS
            if _value(old, key).strip() and _value(new, key).strip() and _value(old, key).strip() != _value(new, key).strip()]


def _union(old: list, new: list, key=lambda x: x) -> list:
    out, seen = [], set()
    for item in list(old or []) + list(new or []):
        mark = key(item)
        if mark in seen:
            continue
        seen.add(mark)
        out.append(item)
    return out[: exp.LIST_MAX]


def merge(old: dict[str, Any], new: dict[str, Any], choose: dict[str, str] | None = None) -> dict[str, Any]:
    """이어서 저장 — 빈 칸은 채우고, 부딪히는 칸은 고른 쪽(없으면 기본), 목록 칸 몇은 합친다."""
    choose = choose or {}
    default = "old" if touched(old) else "new"
    out = dict(old)
    for key, _ in COMPARE_FIELDS:
        names = ("start", "end") if key == "period" else (key,)
        old_text, new_text = _value(old, key).strip(), _value(new, key).strip()
        if not new_text:
            continue
        if not old_text or old_text == new_text or choose.get(key, default) == "new":
            for name in names:
                out[name] = new.get(name)
    if (out.get("lesson") or "") == (new.get("lesson") or "") and new.get("lesson_source"):
        out["lesson_source"] = new["lesson_source"]
    out["open_questions"] = _union(old.get("open_questions"), new.get("open_questions"))
    out["skills"] = _union(old.get("skills"), new.get("skills"), key=lambda s: (s.get("axis"), s.get("name")))
    out["quants"] = _union(old.get("quants"), new.get("quants"), key=lambda q: (q.get("metric"), q.get("value")))
    out["evidences"] = _union(old.get("evidences"), new.get("evidences"), key=lambda e: (e.get("type"), e.get("text")))
    out["materials"] = _union(old.get("materials"), new.get("materials"))
    return out


# ── 미리보기 (3단계.md 6절 ③) ─────────────────────────────────────────────────

def _person_items(conn: sqlite3.Connection, person: str) -> dict[str, dict[str, Any]]:
    return {row["id"]: exp.get_row(conn, row) for row in conn.execute(
        "SELECT * FROM experience WHERE person = ? ORDER BY id", (person,))}


def _guess_project(fields: dict[str, Any], target: dict[str, Any] | None, projects: list[str], titles: dict[str, str]) -> str:
    """정할 것 ② — 이어짐 경험의 과제 → 고른 과제가 하나면 그것 → 제목이 과제명과 닮은 것 → 빈칸."""
    if target and target.get("project"):
        return target["project"]
    if len(projects) == 1:
        return projects[0]
    title = re.sub(r"\s+", "", fields["title"])
    for pid in projects:
        name = re.sub(r"\s+", "", titles.get(pid, ""))
        if name and (name in title or title in name):
            return pid
    return ""


def _default_target(block: ParsedBlock, project: str, items: dict[str, dict[str, Any]]) -> tuple[str, str]:
    """정할 것 ③ — (저장 방법, 대상). 확실한 이어짐 → 그 경험 / 같은 과제의 담당 초안 하나 → 그 초안 / 그 밖 새 경험."""
    sure = block.continues if block.continues and not block.continues.endswith("?") else None
    if sure and sure in items and items[sure]["status"] != "확정":
        return "이어서", sure
    drafts = [i for i in items.values() if i["project"] == project and i["source"] == "담당" and i["status"] == "초안"] if project else []
    if len(drafts) == 1:
        return "이어서", drafts[0]["id"]
    return "새로", ""


def preview(conn: sqlite3.Connection, person: str, name: str, result: ParseResult, projects: list[str]) -> dict[str, Any]:
    titles = {r["id"]: r["title"] for r in conn.execute("SELECT id, title FROM project")}
    items = _person_items(conn, person)
    owned = [c["id"] for c in choices(conn, person)]
    blocks = []
    for block in result.blocks:
        fields = block_fields(block)
        suggested = (block.continues or "").rstrip("?")
        project = _guess_project(fields, items.get(suggested), projects, titles)
        action, target = _default_target(block, project, items)
        warnings = [{"code": p.code, "message": p.message} for p in check_block(block, "구조화", person) if p.level != "정보"]
        role_note = role_warning(fields["role"])
        if role_note:
            warnings.append({"code": "role_subject", "message": role_note})
        blocks.append({
            "index": block.index, "first_line": block.first_line, "fields": fields,
            "continues": block.continues or "", "continues_known": bool(suggested and suggested in items),
            "project": project, "action": action, "target": target,
            "counts": {"open": len(fields["open_questions"]), "quant": len(fields["quants"]), "skill": len(fields["skills"]),
                       "action": len(fields["actions"])},
            "warnings": warnings,
            "bad_lines": [{"line": b.line, "text": b.text, "reason": b.reason} for b in block.bad_lines],
            "unknown": list(block.unknown),
        })
    targets = [{"id": i["id"], "title": i["title"], "project": i["project"], "status": i["status"], "source": i["source"],
                "touched": touched(i), **{key: _value(i, key) for key, _ in COMPARE_FIELDS}}
               for i in items.values() if i["status"] != "확정"]
    return {
        "response": name, "person": person, "projects": projects,
        "blocks": blocks, "notice": result.notice, "found_fence": result.found_fence,
        "duplicates": [list(pair) for pair in result.duplicates], "outside_lines": result.outside_lines,
        "stripped_markers": result.stripped_markers, "stripped_controls": result.stripped_controls,
        "chars": len(result.raw), "lines": len(result.raw.splitlines()),
        "bad_count": sum(len(b["bad_lines"]) for b in blocks), "unknown_count": sum(len(b["unknown"]) for b in blocks),
        "targets": targets, "project_choices": [{"id": pid, "title": titles.get(pid, "")} for pid in owned],
    }


def read(conn: sqlite3.Connection, person: str, text: str, projects: list[str] | None, append_to: str | None = None) -> dict[str, Any]:
    """[읽기] — 원문을 먼저 남기고(블록 0개여도) 미리보기를 돌려준다. **경험은 하나도 바꾸지 않는다.**"""
    text = (text or "").replace("\r\n", "\n")
    if not text.strip():
        raise exp.ExperienceError("붙여 넣은 응답이 비어 있습니다.")
    if len(text) > RESPONSE_MAX:
        raise exp.ExperienceError(f"응답은 한 번에 {RESPONSE_MAX:,}자까지입니다.")
    projects = list(dict.fromkeys(projects or []))
    if append_to:
        path = _response_path(person, append_to)
        doc = md.load(path)
        doc.body = doc.body.rstrip("\n") + APPEND_MARK + text.strip("\n") + "\n"
        projects = list(dict.fromkeys([*(doc.meta.get("projects") or []), *projects]))
    else:
        path = _new_response_path(person)
        stamp = exp.now_iso()
        doc = md.MarkdownDoc({"person": person, "created_at": stamp,
                              "created_by": settings_service.current_author(None) or ""}, text.strip("\n") + "\n")
    result = parse(doc.body)
    doc.meta.update({"projects": projects, "blocks": len(result.blocks), "updated_at": exp.now_iso()})
    doc.meta.setdefault("saved", [])
    md.save(path, doc)
    return preview(conn, person, path.stem, result, projects)


def summary(conn: sqlite3.Connection, person: str, name: str) -> dict[str, Any]:
    """[실험 요약 복사] (3단계.md 8절) — 값 없이 모양만. `tools/experience_probe.py --mask` 와 같은 결."""
    stored = read_response_file(person, name)
    result = parse(stored["text"])
    prompt_chars = build_prompt(conn, person, stored["projects"])["chars"] if stored["projects"] else 0
    lines = [f"[실험 요약] 응답 {name} · 과제 {len(stored['projects'])}개 · 프롬프트 {prompt_chars:,}자 · 응답 {len(result.raw):,}자",
             f"블록 {len(result.blocks)} · 펜스 {'있음' if result.found_fence else '없음'} · 블록 밖 줄 {result.outside_lines}"
             f" · 인용 표식 {result.stripped_markers} · 제어 문자 {result.stripped_controls} · 중복 후보 {len(result.duplicates)}"]
    if result.notice:
        lines.append(f"안내: {result.notice}")
    for block in result.blocks:
        filled = sum(1 for value in block.fields.values() if value)
        problems = sorted({p.code for p in check_block(block, "구조화", person) if p.level != "정보"})
        role = role_warning(block.get("역할"))
        lines.append(
            f"- 블록 {block.index + 1}: 채운 칸 {filled} · 행동 {len(block.lists.get('행동') or [])}"
            f" · 정량 {len(block.quants)} · 확인 필요 {len(block.lists.get('확인_필요') or [])}"
            f" · 이어짐 {'물음표' if (block.continues or '').endswith('?') else ('있음' if block.continues else '없음')}"
            f" · 못 읽은 줄 {len(block.bad_lines)}{' (' + ', '.join(sorted({b.reason for b in block.bad_lines})) + ')' if block.bad_lines else ''}"
            f" · 미분류 키 {', '.join(block.unknown) or '없음'} · 경고 {', '.join(problems + (['role_subject'] if role else [])) or '없음'}")
    return {"text": "\n".join(lines) + "\n"}


# ── 저장 (3단계.md 6절 ③) ─────────────────────────────────────────────────────

def save(conn: sqlite3.Connection, person: str, name: str, decisions: list[dict[str, Any]]) -> dict[str, Any]:
    """블록마다 새로 · 이어서 · 버림. 블록은 원문을 다시 읽어서 — 화면의 값은 믿지 않는다. 상태는 `구조화`."""
    path = _response_path(person, name)
    doc = md.load(path)
    result = parse(doc.body)
    owned = {c["id"] for c in choices(conn, person)}
    ref = response_ref(name)
    plan = []
    for decision in decisions:
        index = decision.get("index")
        if not isinstance(index, int) or not 0 <= index < len(result.blocks):
            raise exp.ExperienceError(f"그런 블록이 없습니다: {index}")
        action = decision.get("action") or "새로"
        if action not in ACTIONS:
            raise exp.ExperienceError(f"저장 방법은 {' · '.join(ACTIONS)} 중 하나입니다.")
        project = (decision.get("project") or "").strip()
        if project and project not in owned:
            raise exp.ExperienceError(f"{person} 님이 맡은 과제가 아닙니다: {project}")
        target = None
        if action == "이어서":
            try:
                target = exp.read_file(exp.file_path(conn, decision.get("target") or ""))
            except KeyError as error:
                raise exp.ExperienceError(f"이어 붙일 경험이 없습니다: {decision.get('target')}") from error
            if target["person"] != person:
                raise exp.ExperienceError("다른 사람의 경험에는 이어 붙이지 않습니다.")
            if target["status"] == "확정":
                raise exp.ExperienceError(f"확정한 경험({target['id']})에는 이어 붙이지 않습니다 — 새 경험으로 저장하세요.")
        plan.append((result.blocks[index], action, project, target, decision.get("choose") or {}))
    made, merged, dropped = [], [], 0
    seen_targets: set[str] = set()
    for block, action, project, target, choose in plan:
        if action == "버림":
            dropped += 1
            continue
        fields = {**block_fields(block), "project": project, "materials": [ref]}
        if action == "새로":
            made.append(exp.create(conn, {**fields, "person": person, "source": "응답"}, status="구조화"))
            continue
        if target["id"] in seen_targets:   # 한 응답의 두 블록이 같은 경험에 — 앞 블록이 바꾼 것을 다시 읽는다
            target = exp.read_file(exp.file_path(conn, target["id"]))
        seen_targets.add(target["id"])
        joined = merge(target, fields, choose)
        joined["project"] = project or target["project"]
        exp.replace(conn, target["id"], joined, status="구조화")
        merged.append(target["id"])
    doc.meta["saved"] = list(dict.fromkeys([*(doc.meta.get("saved") or []), *made, *merged]))
    md.save(path, doc)
    conn.commit()
    return {"made": made, "merged": merged, "dropped": dropped}


def move_responses(old: str, new: str) -> int:
    """이름 바로잡기 — 응답 원문 폴더도 새 이름의 사람 폴더로(경험 파일과 함께). 같은 이름이 있으면 번호를 붙인다."""
    source = responses_dir(old)
    if not source.is_dir():
        return 0
    target_dir = responses_dir(new)
    target_dir.mkdir(parents=True, exist_ok=True)
    moved = 0
    for path in sorted(source.glob("*.md")):
        doc = md.load(path)
        doc.meta["person"] = new
        md.save(path, doc)
        target = target_dir / path.name
        if target.exists():
            target = paths.unique_path(target_dir, path.stem, ".md")
        paths.move(path, target)
        moved += 1
    for folder in (source, source.parent, source.parent.parent):
        try:
            folder.rmdir()
        except OSError:
            break
    return moved
