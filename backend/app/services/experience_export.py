"""팀원별 업무 이력 파일 (TODO 262 · 253 의 5단계 — docs/팀원이력정리/5단계.md).

한 사람의 확정 경험을 `.md` 하나로. 형식은 설계 원본 `docs/spec/context_file.md` 2절(`slow-way-career-context` 0.2),
만드는 규칙은 원본 `docs/07_EXPORT_DESIGN.md` 3 · 4절 — 빈 칸 줄은 빼고(역할 · 구분 · 상태는 늘), 최근 경험부터,
같은 시작 월은 번호 순, **같은 데이터 · 같은 옵션 = 같은 파일**(내보낸 때 줄 빼고).

* 활용 프롬프트(개인 문서 작성용)는 만들지 않는다 — 파일만 건넨다(README 1절 · 238 ④ · 5단계.md ①).
* 효과 금액(과제 전체 금액 — 2단계 초안)은 **기본으로 뺀다**(③). 초안은 어떤 옵션에도 안 들어간다(④).
* 익명화는 만든 최종 글에 — 치환표(설정 `anonymize_rules`) · 긴 것부터 · 부분 문자열 · 영문은 단어 경계 · 근거 ID 와 과제 번호는 보호(원본 07 5절).
* 미리보기는 서버가 만든 글 그대로가 저장 · 복사된다. 이 모듈은 **아무것도 쓰지 않는다**(기록만 `log`).
"""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from .. import clock
from ..config import get_settings
from ..experience import skills as skill_rules
from ..vault import paths
from . import buildinfo
from . import experiences as exp
from . import settings as settings_service

FORMAT = "slow-way-career-context"
VERSION = "0.2"
SIZE_WARN = 100_000
SIZE_SPLIT = 300_000
MONEY_BASELINE = "과제 전체 금액(본인 몫 아님)"
MONEY_QUESTION = "과제 효과 금액 중 본인이 기여한 몫"
KINDS = ("회사", "조직", "인명", "제품", "공정", "고객", "기관", "기타")
DEFAULT_PATTERNS = [{"kind": "기타", "regex": r"10-\d{7}", "to": "특허 등록번호"}]

GUIDE = [
    "이 문서는 사내 과제 관리 도구에 기록하고 팀장이 검토한 업무 이력이다.",
    "여기에 없는 성과, 수치, 역할, 직위를 만들지 않는다.",
    "수치는 문서에 적힌 값과 비교 기준만 사용한다. \"기준 없음\"으로 표시된 수치는 비교 표현(개선, 단축, 증가)을 붙이지 않는다.",
    "추정이 필요하면 문장을 만들지 말고 사용자에게 질문한다.",
    "요청받은 문서 형식을 따르되, 각 문장은 아래 경험 ID 중 하나에 근거해야 한다. 결과물에는 근거 ID를 괄호로 남긴다. 예: (E-001)",
    "\"확인 필요\" 항목에 적힌 내용은 미확정이다. 그 내용을 단정하는 문장을 쓰지 않는다.",
]
IDS_LINE = 4


# ── 옵션 ──────────────────────────────────────────────────────────────────────

def options(raw: dict[str, Any]) -> dict[str, Any]:
    scope = raw.get("scope") or "all"
    if scope not in ("all", "period", "pick"):
        raise exp.ExperienceError("범위는 전체 · 기간 · 선택 중 하나입니다.")
    start = (raw.get("start") or "").strip()[:7]
    end = (raw.get("end") or "").strip()[:7]
    if scope == "period" and not (start or end):
        raise exp.ExperienceError("기간 범위는 시작이나 끝 하나는 있어야 합니다(2025-01 처럼).")
    ids = [i for i in (raw.get("ids") or []) if exp.ID_PATTERN.match(i)]
    if scope == "pick" and not ids:
        raise exp.ExperienceError("고른 경험이 없습니다.")
    flag = lambda name, default: bool(raw.get(name)) if raw.get(name) is not None else default  # noqa: E731
    return {"scope": scope, "start": start, "end": end, "ids": ids, "structured": flag("structured", False),
            "ids_in": flag("ids_in", True), "money": flag("money", False), "anonymize": flag("anonymize", False)}


def _scope_label(opt: dict[str, Any], count: int) -> str:
    if opt["scope"] == "period":
        return f"기간 {opt['start'] or '처음'}~{opt['end'] or '현재'}"
    if opt["scope"] == "pick":
        return f"선택 {count}건"
    return "전체"


# ── 고르기 (원본 07 3절) ──────────────────────────────────────────────────────

def _select(items: list[dict[str, Any]], opt: dict[str, Any], warnings: list[str]) -> list[dict[str, Any]]:
    statuses = {"확정", "구조화"} if opt["structured"] else {"확정"}
    out = []
    no_period = 0
    for item in items:
        if item["status"] not in statuses:
            continue
        if opt["scope"] == "pick" and item["id"] not in opt["ids"]:
            continue
        if opt["scope"] == "period":
            if not item["start"]:
                no_period += 1
                continue
            last = item["end"] or "9999-12"
            if (opt["end"] and item["start"] > opt["end"]) or (opt["start"] and last < opt["start"]):
                continue
        out.append(item)
    if no_period:
        warnings.append(f"기간이 비어 있어 뺀 경험 {no_period}건 — 기간 범위에는 들어가지 않습니다")
    out.sort(key=lambda i: (i["start"] or "0000-00", -int(i["id"][2:])), reverse=True)
    return out


def _strip_money(item: dict[str, Any]) -> dict[str, Any]:
    return {**item, "quants": [q for q in item["quants"] if q.get("baseline") != MONEY_BASELINE],
            "open_questions": [q for q in item["open_questions"] if MONEY_QUESTION not in q]}


# ── 쓰기 (원본 스펙 2절 · 07 4절) ─────────────────────────────────────────────

def _period(item: dict[str, Any]) -> str:
    if not item["start"]:
        return ""
    return f"{item['start']} ~ {item['end'] or '현재'}"


def _cell(text: str) -> str:
    return " ".join(str(text or "").replace("|", "/").split())


def _block(item: dict[str, Any], ids_in: bool, dictionary_axes: dict[tuple[str, str], str]) -> list[str]:
    head = f"## [{item['id']}] {item['title']}" if ids_in else f"## {item['title']}"
    lines = [head, ""]
    facts = [("기간", _period(item)), ("과제", item["project"]), ("소속", item["affiliation"]),
             ("역할", item["role"] or "(비어 있음)"), ("구분", item["kind"] or "(비어 있음)"), ("상태", item["status"]),
             ("도구", ", ".join(item["tools"]))]
    lines += [f"- {label}: {value}" for label, value in facts if value]
    sections: list[tuple[str, list[str]]] = [
        ("상황", [item["situation"]] if item["situation"] else []),
        ("목표", [item["goal"]] if item["goal"] else []),
        ("행동", [f"- {a}" for a in item["actions"]]),
    ]
    result = [f"- 정량: {_cell(q['metric'])} | {_cell(q.get('value'))} | 기준: {_cell(q.get('baseline') or '기준 없음')} | 시점: {_cell(q.get('when'))}"
              for q in item["quants"]]
    if item["result_qual"]:
        result.append(f"- 정성: {' '.join(item['result_qual'].split())}")
    if item["impact"]:
        result.append(f"- 비즈니스 영향: {item['impact']}")
    sections.append(("결과", result))
    by_axis: dict[str, list[str]] = {}
    for skill in item["skills"]:
        by_axis.setdefault(skill.get("axis") or "기술", []).append(skill["name"])
    sections.append(("역량", [f"- {axis}: {', '.join(by_axis[axis])}" for axis in skill_rules.AXES if by_axis.get(axis)]))
    lesson = item["lesson"] + (f" ({item['lesson_source']})" if item["lesson_source"] and item["lesson"] else "")
    sections.append(("교훈", [lesson] if item["lesson"] else []))
    sections.append(("증빙", [f"- {e.get('type')} · {e.get('text')}" + (f" ({e['year']})" if e.get("year") else "") for e in item["evidences"]]))
    sections.append(("확인 필요", [f"- {q}" for q in item["open_questions"]]))
    for title, body in sections:
        if body:
            lines += ["", f"### {title}", ""] + body
    return lines


def _table(head: list[str], rows: list[list[str]]) -> list[str]:
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]


def render(conn: sqlite3.Connection, person: str, opt: dict[str, Any], today: str | None = None) -> dict[str, Any]:
    from .person_history import history

    warnings: list[str] = []
    every = [exp.get_row(conn, row) for row in conn.execute("SELECT * FROM experience WHERE person = ?", (person,))]
    chosen = _select(every, opt, warnings)
    if not opt["money"]:
        chosen = [_strip_money(i) for i in chosen]
    dictionary = settings_service.skill_dictionary()
    known = {(d["axis"], d["name"]) for d in dictionary}
    ref = (lambda item: item["id"]) if opt["ids_in"] else (lambda item: item["title"])  # noqa: E731
    structured = sum(1 for i in chosen if i["status"] == "구조화")
    if structured:
        warnings.append(f"확정되지 않은 경험 {structured}건이 들어갑니다(구조화)")
    if opt["money"] and any(q.get("baseline") == MONEY_BASELINE for i in chosen for q in i["quants"]):
        warnings.append("효과 금액(과제 전체 금액 — 본인 몫 아님)이 들어갑니다")
    found = exp.consistency(conn, person, every)
    open_warn = [i["id"] for i in chosen if any(not w["acknowledged"] for w in found.get(i["id"], []))]
    if open_warn:
        warnings.append(f"정합성 경고가 남은 경험 {len(open_warn)}건이 들어갑니다({', '.join(open_warn)})")
    # 머리 정보
    build = (buildinfo.read() or {}).get("name", "느린나이테")
    today = today or clock.today().isoformat()
    front = ["---", f"format: {FORMAT}", f"version: {VERSION}", f"exported_at: {today}", f"owner: {person}",
             f"scope: {_scope_label(opt, len(chosen))}", f"status_included: {'확정+구조화' if opt['structured'] else '확정'}",
             f"anonymized: {'true' if opt['anonymize'] else 'false'}", f"experience_count: {len(chosen)}", f"app: {build}", "---", ""]
    guide = [g for n, g in enumerate(GUIDE) if opt["ids_in"] or n != IDS_LINE]
    body = ["# 사용 안내 (AI에게)", ""] + [f"- {g}" for g in guide] + [""]
    # 프로필
    hist = history(conn, person)
    used_projects = [i["project"] for i in chosen if i["project"]]
    projects = [p for p in hist["projects"] if p["id"] in used_projects]
    starts = sorted(i["start"] for i in chosen if i["start"])
    profile = [f"- 이름: {person}", f"- 맡은 과제: {hist['summary']['projects']}건(주관 {hist['summary']['lead']})"]
    if starts:
        latest_end = "현재" if any(not i["end"] for i in chosen if i["start"]) else max(i["end"] for i in chosen if i["end"])
        profile.append(f"- 이 파일의 기간: {starts[0]} ~ {latest_end}")
    for kind in ("특허", "수상"):
        names = sorted({e["text"] + (f" ({e['year']})" if e.get("year") else "") for i in chosen for e in i["evidences"] if e.get("type") == kind})
        if names:
            profile.append(f"- {kind}: {'; '.join(names)}")
    body += ["# 프로필", ""] + profile + [""]
    if projects:
        rows = [[p["id"], p["title"], f"{(p['from'] or '')[:7] or '?'} ~ {(p['to'] or '')[:7] or '현재'}", " · ".join(x for x in (p["role"], p["part"]) if x)]
                for p in sorted(projects, key=lambda p: p["id"], reverse=True)]
        body += ["# 과제", ""] + _table(["번호", "과제명", "담당 기간", "역할"], rows) + [""]
    body += ["# 경험", ""]
    for item in chosen:
        body += _block(item, opt["ids_in"], {}) + [""]
    # 역량 색인
    index: dict[tuple[str, str], list[str]] = {}
    for item in chosen:
        for skill in item["skills"]:
            index.setdefault((skill.get("axis") or "기술", skill["name"]), []).append(ref(item))
    order = lambda pair: (skill_rules.AXES.index(pair[0][0]) if pair[0][0] in skill_rules.AXES else 9, -len(pair[1]), pair[0][1])  # noqa: E731
    in_dict = sorted(((k, v) for k, v in index.items() if k in known), key=order)
    outside = sorted(((k, v) for k, v in index.items() if k not in known), key=order)
    if index:
        body += ["# 역량 색인", ""] + _table(["축", "역량", "관련 경험"], [[a, n, ", ".join(v)] for (a, n), v in in_dict])
        if outside:
            body += ["", "사전에 없는 태그: " + "; ".join(f"{n} ({', '.join(v)})" for (_, n), v in outside)]
        body += [""]
    tools: dict[str, list[str]] = {}
    for item in chosen:
        for tool in item["tools"]:
            tools.setdefault(tool, []).append(ref(item))
    if tools:
        body += ["# 기술 · 도구", ""] + _table(["도구", "관련 경험"], [[t, ", ".join(v)] for t, v in sorted(tools.items(), key=lambda p: (-len(p[1]), p[0]))]) + [""]
    quants = [[q["metric"], q.get("value", ""), q.get("baseline", "") if q.get("baseline_kind") == "비교" else "기준 없음", q.get("when", ""), ref(i)]
              for i in chosen for q in i["quants"]]
    if quants:
        body += ["# 정량 성과 목록", ""] + _table(["지표", "값", "비교 기준", "시점", "경험"], quants) + [""]
    text = "\n".join(front + body).rstrip() + "\n"
    replaced: dict[str, int] = {}
    if opt["anonymize"]:
        text, replaced, leftover = anonymize(conn, person, text, [p["id"] for p in projects] + [i["project"] for i in chosen if i["project"]])
        warnings += leftover
    if len(text) > SIZE_SPLIT:
        warnings.append(f"파일이 아주 큽니다({len(text):,}자) — 기간으로 나눠 내보내세요")
    elif len(text) > SIZE_WARN:
        warnings.append(f"파일이 큽니다({len(text):,}자) — 본문 붙여넣기로는 잘릴 수 있습니다. 범위를 줄이거나 파일 첨부로 쓰세요")
    if not chosen:
        warnings.append("들어갈 경험이 없습니다 — 확정한 경험이 있는지, 범위를 확인하세요")
    owner = "익명" if opt["anonymize"] else person
    stamp = today.replace("-", "")
    scope_part = {"all": "전체", "period": f"{opt['start'] or '처음'}-{opt['end'] or '현재'}", "pick": f"선택{len(chosen)}"}[opt["scope"]]
    filename = paths.windows_safe_filename(f"업무이력_{owner}_{scope_part}_{stamp}.md".replace(" ", "-"))
    axis_counts = {axis: sum(1 for (a, _), v in index.items() if a == axis) for axis in skill_rules.AXES}
    top = [n for (_, n), _v in sorted(index.items(), key=lambda p: -len(p[1]))[:5]]
    return {
        "text": text, "filename": filename, "chars": len(text), "warnings": warnings, "options": opt,
        "summary": {"experiences": len(chosen), "confirmed": len(chosen) - structured, "structured": structured,
                    "period": f"{starts[0]} ~ {'현재' if any(not i['end'] for i in chosen if i['start']) else max((i['end'] for i in chosen if i['end']), default='')}" if starts else "",
                    "projects": len(projects), "axes": axis_counts, "top_skills": top,
                    "quants": len(quants), "quants_compared": sum(1 for q in quants if q[2] != "기준 없음"),
                    "replaced": replaced},
        "ids": [i["id"] for i in chosen],
    }


# ── 익명화 (원본 07 5절) ──────────────────────────────────────────────────────

def anonymize_rules() -> dict[str, list[dict[str, str]]]:
    stored = settings_service.load().get("anonymize_rules")
    if isinstance(stored, dict):
        return {"rules": list(stored.get("rules") or []), "patterns": list(stored.get("patterns") or DEFAULT_PATTERNS)}
    return {"rules": [], "patterns": list(DEFAULT_PATTERNS)}


def validate_rules(value: Any) -> dict[str, list[dict[str, str]]] | None:
    """설정 `anonymize_rules` 의 모양 — {rules: [{kind, from, to}], patterns: [{kind, regex, to}]}. 빈 것은 null."""
    if value is None or value == {} or value == []:
        return None
    if not isinstance(value, dict):
        raise ValueError("치환표 모양이 다릅니다.")
    rules, patterns = [], []
    for raw in value.get("rules") or []:
        source, target = " ".join(str(raw.get("from") or "").split()), " ".join(str(raw.get("to") or "").split())
        kind = str(raw.get("kind") or "기타")
        if not source:
            continue
        if not target or len(source) > 80 or len(target) > 40 or kind not in KINDS:
            raise ValueError(f"치환 규칙을 확인하세요: {source[:20]} → {target[:20] or '(빈칸)'}")
        rules.append({"kind": kind, "from": source, "to": target})
    for raw in value.get("patterns") or []:
        regex = str(raw.get("regex") or "")
        try:
            re.compile(regex)
        except re.error as error:
            raise ValueError(f"정규식을 읽지 못했습니다: {regex[:30]} ({error})") from error
        if regex:
            patterns.append({"kind": str(raw.get("kind") or "기타"), "regex": regex, "to": str(raw.get("to") or "")[:40]})
    if len(rules) > 300:
        raise ValueError("치환 규칙은 300개까지입니다.")
    return {"rules": rules, "patterns": patterns}


_PROTECT = re.compile(r"E-\d{3,}")


def anonymize(conn: sqlite3.Connection, person: str, text: str, project_ids: list[str]) -> tuple[str, dict[str, int], list[str]]:
    """최종 글에 치환표 적용 — (글, 종류별 횟수, 경고). 근거 ID · 과제 번호는 보호한다."""
    table = anonymize_rules()
    kept: list[str] = []

    def hide(match: re.Match[str]) -> str:
        kept.append(match.group(0))
        return f"\x00{len(kept) - 1}\x00"

    protect = [re.escape(p) for p in sorted(set(project_ids), key=len, reverse=True) if p]
    pattern = re.compile("|".join([_PROTECT.pattern, *protect])) if protect else _PROTECT
    text = pattern.sub(hide, text)
    text = re.sub(r"^owner: .*$", "owner: 익명", text, count=1, flags=re.M)
    text = re.sub(r"^- 이름: .*$", "- 이름: 익명", text, count=1, flags=re.M)
    counts: dict[str, int] = {}
    for rule in sorted(table["rules"], key=lambda r: -len(r["from"])):
        source = rule["from"]
        regex = re.compile(rf"(?<![A-Za-z0-9]){re.escape(source)}(?![A-Za-z0-9])", re.I) if source.isascii() else re.compile(re.escape(source))
        text, n = regex.subn(rule["to"], text)
        if n:
            counts[rule["kind"]] = counts.get(rule["kind"], 0) + n
    for rule in table["patterns"]:
        text, n = re.subn(rule["regex"], rule["to"], text)
        if n:
            counts[rule["kind"]] = counts.get(rule["kind"], 0) + n
    text = re.sub(r"\x00(\d+)\x00", lambda m: kept[int(m.group(1))], text)
    # 잔존 검사 — 대소문자 · 가운데 공백 차이까지(원본 07 5.4)
    warnings = []
    flat = text.lower()
    left = [r["from"] for r in table["rules"] if r["from"].lower() in flat]
    if left:
        warnings.append(f"치환표의 이름이 남아 있습니다: {', '.join(left[:5])}")
    if person in text:
        warnings.append(f"본인 이름({person})이 남아 있습니다 — 치환표에 넣으세요(예: {person} → 본인)")
    missing = [c["text"] for c in candidates(conn, person) if not c["in_rules"] and c["text"] in text]
    if missing:
        warnings.append(f"치환하지 않은 후보 {len(missing)}개: {', '.join(missing[:5])}{' …' if len(missing) > 5 else ''}")
    return text, counts, warnings


def candidates(conn: sqlite3.Connection, person: str) -> list[dict[str, Any]]:
    """익명화 후보 — 명부의 사람 이름 · 과제의 유관부서 · 맡은 과제명. 사람이 고른다(고객사 · 공정명은 못 찾는다)."""
    from .person_history import history

    rules = {r["from"] for r in anonymize_rules()["rules"]}
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(kind: str, text: str, suggest: str) -> None:
        text = " ".join((text or "").split())
        if len(text) < 2 or text in seen:
            return
        seen.add(text)
        out.append({"kind": kind, "text": text, "suggest": suggest, "in_rules": text in rules})

    others = 0
    for entry in settings_service.people():
        name = entry.get("name") or ""
        if name == person:
            add("인명", name, "본인")
        else:
            others += 1
            add("인명", name, f"동료 {chr(64 + min(others, 26))}")
    owned = [p["id"] for p in history(conn, person)["projects"]]
    depts = 0
    for row in conn.execute(f"SELECT DISTINCT team FROM project_partner WHERE project_id IN ({','.join('?' * len(owned)) or 'NULL'})", owned):
        depts += 1
        add("조직", row["team"], f"유관부서 {depts}")
    for p in history(conn, person)["projects"]:
        add("기타", p["title"], "")
    return out


# ── 기록 ──────────────────────────────────────────────────────────────────────

def _log_path():
    return get_settings().logs_dir / "experience-exports.jsonl"


def log(person: str, by: str, role: str, opt: dict[str, Any], count: int, chars: int, how: str) -> None:
    """내보내기 기록 한 줄 — 누가 · 언제 · 누구의 · 범위 · 옵션. **파일 내용은 남기지 않는다**(5단계.md ⑧)."""
    path = _log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"at": exp.now_iso(), "by": by, "role": role, "person": person, "how": how, "count": count, "chars": chars,
           "options": {k: opt[k] for k in ("scope", "start", "end", "structured", "ids_in", "money", "anonymize")}}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def log_rows(person: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    path = _log_path()
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if person is None or row.get("person") == person:
            rows.append(row)
    return list(reversed(rows))[:limit]
