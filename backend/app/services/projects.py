"""과제 생성·수정. 파일을 먼저 쓰고 인덱스를 갱신한다."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import CLASSIFICATION_KEYS, DEFAULT_STATUS, STATUS_KEYS, get_settings
from ..vault import markdown as md
from ..vault import versions
from ..vault import paths
from ..vault.indexer import index_project
from . import activities as activities_service
from . import settings as settings_service
from . import trash as trash_service

# 카드 제목이 "과제 개요"이므로 본문은 같은 제목을 반복하지 않는다.
# 각 항목이 무엇을 적는 자리인지 괄호로 안내하고, 사용자는 그 줄을 지우고 쓰면 된다.
# 안내 문구는 인용문(>)으로 넣는다. 화면에서 흐리게 보여 실제 내용과 구분되고,
# 사용자는 그 줄을 지우고 쓰면 된다.
INDEX_TEMPLATE = """## 배경

> 왜 이 과제를 하는지 — 문제 상황, 요청 배경 (이 줄을 지우고 작성하세요)

## 목표

> 무엇을 달성하면 끝인지 — 가능하면 수치로 (성과지표: KPI · 현수준 · 목표)

## 추진내용

> 과제 범위 · 적용 대상 · 단계별 추진계획 · 유관부서 협의

## 산출물

> 과제가 끝났을 때 남기는 결과물 — 예: 평가 보고서, 시제품, 측정 데이터, 특허 초안

## 정성적 효과

> 숫자로 표현하기 어려운 효과 — 품질 향상, 리스크 저감, 기술 확보, 대응 속도 등
> 근거 자료(엑셀·PPT)는 아래 [파일 첨부]로 붙이고 여기에 링크하면 된다

## 효과 산출 근거

> 위 기대효과 금액이 어떤 계산에서 나왔는지 — 단가 × 물량 × 개선율, 가정, 출처
> 근거 없는 숫자는 보고 자리에서 방어하지 못한다

## 활용 방안 및 향후 계획

> 결과를 어디에 어떻게 쓰는지, 끝난 뒤 이어질 일

## 관련 링크

> 참고할 사내 위키·공유 폴더 주소, 관련 과제 번호 등
"""

# 예전 서식들 (TODO 136 에서 섹션 둘을 더하기 전). 그 서식 그대로인 개요도 **아직 작성 전**으로
# 알아봐야 한다 — 서식을 바꿨다고 이미 만든 과제들이 갑자기 "작성됨" 이 되면 안 된다 (106-B).
LEGACY_INDEX_TEMPLATES = (
    """## 배경

> 왜 이 과제를 하는지 — 문제 상황, 요청 배경 (이 줄을 지우고 작성하세요)

## 목표

> 무엇을 달성하면 끝인지 — 가능하면 수치로

## 산출물

> 과제가 끝났을 때 남기는 결과물 — 예: 평가 보고서, 시제품, 측정 데이터, 특허 초안

## 정성적 효과

> 숫자로 표현하기 어려운 효과 — 품질 향상, 리스크 저감, 기술 확보, 대응 속도 등
> 근거 자료(엑셀·PPT)는 아래 [파일 첨부]로 붙이고 여기에 링크하면 된다

## 효과 산출 근거

> 위 기대효과 금액이 어떤 계산에서 나왔는지 — 단가 × 물량 × 개선율, 가정, 출처
> 근거 없는 숫자는 보고 자리에서 방어하지 못한다

## 관련 링크

> 참고할 사내 위키·공유 폴더 주소, 관련 과제 번호 등
""",
)

META_ORDER = [
    "id", "title", "status", "type",
    # 과제 분류 넷 (TODO 136) — 속성 바로 뒤. 파일을 열었을 때 한 덩이로 읽힌다.
    "nature", "category", "delivery", "cost_kind",
    "group", "tags", "owners",
    "start_date", "due_date", "completed_at", "effect_expected", "effect_verified",
    "no_report", "no_effect", "partners",
    # 이 과제가 어느 접수에서 승격됐는가 (TODO 136). 직접 만든 과제는 비어 있다.
    "intake_id",
    # 선행 과제 — 다년도 과제의 앞 단계 번호들 (TODO 172). 1단계면 비어 있다. 여럿일 수 있다.
    "predecessors",
    "created_by", "created_at", "updated_at",
]

# 상태가 이것이 되는 순간 완료일이 남는다 (TODO 104).
DONE_STATUS = "done"


# 효과 금액의 소수 자릿수. 단위가 **억원/년** 이므로 둘째 자리는 100만 원이다.
# 한 자리(=천만 원)로는 1억 2,500만 원짜리 효과를 적을 수 없다 (TODO 76).
EFFECT_DECIMALS = 2


def normalize_effect(value: object) -> float | None:
    """효과 금액(억원/년)을 숫자로 맞춘다. 비우는 것은 정상이다.

    실증효과는 과제가 끝나야 나오므로 진행 중에는 대부분 비어 있다.

    **여기서 소수 둘째 자리로 자른다.** 파일이 진실의 원천이므로, 화면이 두 자리로
    보여 준다면 파일에도 두 자리만 있어야 한다. 그러지 않으면 API 로 넣은 `1.234` 가
    화면에는 `1.23` 으로 보이면서 파일에는 그대로 남아 둘이 어긋난다.
    """
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"효과 금액은 숫자여야 합니다: {value!r}") from exc
    if number < 0:
        raise ValueError("효과 금액은 0보다 작을 수 없습니다.")
    return round(number, EFFECT_DECIMALS)


def normalize_label(value: object) -> str | None:
    """분류 넷의 값 (TODO 136). 글자 그대로 두되 앞뒤·겹친 공백만 정리한다.

    **목록에 있는지는 따지지 않는다.** 목록은 설정에서 바뀌는데, 바뀔 때마다 예전 값을
    가진 과제를 저장할 수 없게 되면 안 된다. 화면은 목록에서 고르게 하고, 파일은 무엇이든 받는다.
    """
    text = " ".join(str(value or "").split())
    return text[:40] or None


def normalize_owners(value: object) -> list[str]:
    """담당자는 한 명일 수도, 여러 명일 수도 있다. 쉼표로 적어도 받아 준다."""
    if not value:
        return []
    items = [value] if isinstance(value, str) else [str(item) for item in value]
    # 한 칸에 "권경락, 홍길동" 처럼 적어 보내도 나눠 받는다.
    raw = [part for item in items for part in item.split(",")]
    seen: list[str] = []
    for name in (item.strip() for item in raw):
        if name and name not in seen:
            seen.append(name)
    return seen


def normalize_partners(value: object) -> list[dict]:
    """유관부서와 그 담당자 (TODO 92).

    `[{"team": "설비기술팀", "people": "김철수, 박민수"}, …]` 을 받아
    `[{"team": "설비기술팀", "people": ["김철수", "박민수"]}, …]` 으로 맞춘다.

    **사람 이름을 나누는 일은 여기(서버)에서 한다.** 화면만 고치면 API 를 직접 부르는
    길로 `"김철수,박민수"` 한 덩이가 사람 하나로 굳는다 — 역량 이력에서 실제로 겪은
    사고다 (TODO 74). 팀 이름은 나누지 않는다. 부서명에 쉼표가 들어갈 수 있고,
    무엇보다 **팀은 줄마다 하나**라는 것이 이 구조의 약속이다.

    담당자가 비어 있어도 줄은 남긴다 — 팀은 정해졌는데 사람은 나중에 정해지는 일이 흔하다.
    """
    if not value:
        return []
    rows = value if isinstance(value, list) else [value]
    out: list[dict] = []
    seen: dict[str, dict] = {}
    for row in rows:
        if isinstance(row, str):
            team, people = row, []
        elif isinstance(row, dict):
            team = str(row.get("team") or "").strip()
            people = activities_service.split_people(
                row.get("people") if isinstance(row.get("people"), str) else None
            ) or [
                name
                for name in (str(item).strip() for item in (row.get("people") or []))
                if name
            ]
        else:
            continue
        team = str(team).strip()
        if not team:
            continue
        # 같은 팀을 두 줄로 적었으면 한 줄로 합친다 — 표와 검색에서 두 번 세지 않는다.
        if team in seen:
            for name in people:
                if name not in seen[team]["people"]:
                    seen[team]["people"].append(name)
            continue
        entry = {"team": team, "people": list(dict.fromkeys(people))}
        seen[team] = entry
        out.append(entry)
    return out


def now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def project_year(start_date: str | None = None) -> int:
    """과제 번호에 쓸 연도 — **착수년도**다 (TODO 95).

    지난해에 한 과제를 올해 뒤늦게 등록하는 일이 실제로 있다. 그때 번호가 `2026-…` 으로
    붙으면 그 과제는 홈·대시보드·목록에서 전부 올해 것으로 세인다 — 연도를 가르는 기준이
    **과제 번호 앞 네 자리**이기 때문이다 (DESIGN 5.8). 그래서 **등록한 날이 아니라
    시작일**을 본다.

    시작일을 비워 두면 올해다 — 지금 착수하는 과제라고 보는 것이 가장 흔한 경우다.
    """
    text = (start_date or "").strip()
    if len(text) >= 4 and text[:4].isdigit():
        year = int(text[:4])
        # 오타로 `0025-01-01` 같은 값이 들어오면 없는 연도의 번호가 생긴다. 그때는 올해로.
        if 1900 <= year <= 2999:
            return year
    return datetime.now().year


def next_project_id(year: int | None = None, code: str | None = None) -> str:
    """다음 과제 번호.

    팀 코드를 비워 두면 `2026-001`, `소재` 를 넣으면 `2026-소재-001` 이 된다.
    일련번호는 **코드별로 따로 센다** — 팀마다 자기 번호를 갖는 편이 자연스럽고,
    코드가 다르면 번호가 같아도 과제 번호는 겹치지 않는다.
    연도는 **착수년도**다 (`project_year`) — 등록한 날이 아니다.

    **이미 만든 과제의 번호는 바꾸지 않는다.** 번호는 식별자라 섞여도 되고,
    바꾸면 폴더명과 문서 안의 링크가 모두 흔들린다.
    (시작일을 잘못 적어 연도가 어긋난 과제만은 사용자가 눌러서 옮긴다 — `renumber.year_*`)
    """
    settings = get_settings()
    settings.ensure_dirs()
    year = year or datetime.now().year
    if code is None:
        code = settings_service.project_code()
    prefix = f"{year}-{code}-" if code else f"{year}-"

    # 번호는 한 번 쓰면 다시 쓰지 않는다 — 삭제 보관함에 간 과제의 번호도 센다 (TODO 146).
    names = [child.name for child in settings.projects_dir.iterdir() if child.is_dir()]
    names += list(trash_service.used_folder_names("projects"))
    return f"{prefix}{max_sequence(names, prefix) + 1:03d}"


def max_sequence(names: list[str], prefix: str) -> int:
    """`prefix` 로 시작하는 이름들의 가장 큰 일련번호. 없으면 0."""
    used = 0
    for name in names:
        if not name.startswith(prefix):
            continue
        seq = name[len(prefix):].split("-")[0]
        if seq.isdigit():
            used = max(used, int(seq))
    return used


def project_dir(conn: sqlite3.Connection, project_id: str) -> Path:
    row = conn.execute("SELECT dir_name FROM project WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise KeyError(project_id)
    return paths.safe_join(get_settings().projects_dir, row["dir_name"])


def create_project(conn: sqlite3.Connection, data: dict[str, Any]) -> str:
    settings = get_settings()
    settings.ensure_dirs()
    title = (data.get("title") or "").strip()
    if not title:
        raise ValueError("과제명을 입력하세요.")

    status = data.get("status") or DEFAULT_STATUS
    if status not in STATUS_KEYS:
        raise ValueError(f"알 수 없는 상태: {status}")

    project_type = data.get("type") or None
    if project_type and project_type not in settings_service.type_keys():
        raise ValueError(f"알 수 없는 속성: {project_type}")
    # 선행 과제 (TODO 172) — 폴더를 만들기 전에 본다(거절하면 빈 폴더가 남지 않게).
    # 새 과제는 아직 번호가 없으므로 고리가 생길 수 없다. 있는 과제인지만 본다.
    predecessors = check_predecessors(conn, None, data.get("predecessors"))

    # 번호의 연도는 **등록한 날이 아니라 착수년도**다 (TODO 95).
    project_id = next_project_id(project_year(data.get("start_date")))
    dir_name = paths.project_dir_name(project_id, title)
    directory = paths.safe_join(settings.projects_dir, dir_name)
    (directory / "logs").mkdir(parents=True, exist_ok=True)
    (directory / "assets").mkdir(parents=True, exist_ok=True)
    (directory / "reports").mkdir(parents=True, exist_ok=True)

    stamp = now_iso()
    meta = {
        "id": project_id,
        "title": title,
        "status": status,
        "type": project_type,
        "group": data.get("group") or None,
        "tags": data.get("tags") or [],
        "owners": normalize_owners(data.get("owners") or data.get("owner")),
        # 유관부서와 그 담당자. 팀 하나에 사람 여럿, 팀도 여럿일 수 있다 (TODO 92).
        "partners": normalize_partners(data.get("partners")),
        "start_date": data.get("start_date") or None,
        "due_date": data.get("due_date") or None,
        # 완료 상태로 등록하면 완료일이 곧 등록일이다 — 지난 과제를 뒤늦게 넣을 때는
        # 폼에서 손으로 고친다 (TODO 104).
        "completed_at": normalize_day(data.get("completed_at"))
        or (date_today() if status == DONE_STATUS else None),
        "effect_expected": normalize_effect(data.get("effect_expected")),
        "effect_verified": normalize_effect(data.get("effect_verified")),
        # 과제 분류 넷 (TODO 136). 주로 스마트과제에서 쓴다 — 다른 과제는 비어 있어도 된다.
        **{key: normalize_label(data.get(key)) for key in CLASSIFICATION_KEYS},
        # 접수에서 승격된 과제면 그 접수 번호 (TODO 136)
        "intake_id": (str(data.get("intake_id") or "").strip() or None),
        "predecessors": predecessors,
        # 단순 현황 관리를 과제로 세운 경우가 있다. 그런 과제는 보고 대상 후보에서 뺀다
        # — 매주 "이건 보고 안 해도 되는데" 를 눈으로 걸러 내지 않아도 되게 (TODO 80).
        "no_report": bool(data.get("no_report")),
        # 효과 금액으로 관리하지 않는 과제 (TODO 125)
        "no_effect": bool(data.get("no_effect")),
        # 담당자(누가 하는가)와 다른, "누가 등록했는가". 소급이 안 되므로 지금부터 남긴다.
        # 로그인이 생기면 이 자리에 로그인 사용자가 들어온다.
        "created_by": settings_service.current_author(data.get("created_by")) or None,
        "created_at": stamp,
        "updated_at": stamp,
    }
    md.save(directory / "index.md", md.MarkdownDoc(meta, data.get("body") or INDEX_TEMPLATE))
    index_project(conn, directory)
    conn.commit()
    return project_id


def overview_is_blank(body: str | None) -> bool:
    """개요가 아직 서식 그대로인가 (TODO 106-B).

    서식 그대로인 개요는 화면에서 진짜 내용처럼 보이고, 검색 발췌에도 안내 문장이
    본문인 양 실린다. 공백·줄바꿈 차이는 무시한다 — 저장하며 끝의 개행이 흔들린다.
    """
    def squash(text: str | None) -> str:
        return " ".join((text or "").split())

    text = squash(body)
    return text == "" or any(
        text == squash(template) for template in (INDEX_TEMPLATE, *LEGACY_INDEX_TEMPLATES)
    )


def date_today() -> str:
    return datetime.now().date().isoformat()


def normalize_day(value: object) -> str | None:
    """`YYYY-MM-DD` 만 받는다. 비우면 None — "모른다" 를 "0000-00-00" 으로 적지 않는다."""
    text = str(value or "").strip()
    if not text:
        return None
    return paths.validate_date(text, text)


# 상태 변경 기록에 붙는 태그. 화면이 이 태그로 알아보고 흐리게 세운다.
STATUS_CHANGE_TAG = "상태변경"


def _log_status_change(directory: Path, old: str, new: str) -> None:
    """상태가 바뀔 때 진행일지에 한 줄 (TODO 105).

    "이 과제 언제 보류됐지?" 에 답할 자리가 없었다. 기록은 사람이 쓴 진행일지와 같은
    폴더에 같은 형식으로 남는다 — 별도 표를 두면 타임라인에서 안 보이고 검색도 안 된다.
    **실패해도 상태 변경 자체를 막지 않는다.** 이력을 남기려다 본 작업이 막히면 본말이
    뒤바뀐다.
    """
    from ..config import STATUS_LABELS

    log_system_line(
        directory,
        f"(상태) {STATUS_LABELS.get(old, old)} → {STATUS_LABELS.get(new, new)}",
        f"상태를 **{STATUS_LABELS.get(old, old)}** 에서 **{STATUS_LABELS.get(new, new)}** 로 바꿨다.\n",
    )


def log_system_line(directory: Path, title: str, body: str) -> None:
    """도구가 남기는 진행일지 한 줄 — 상태 변경(105)·접수 연결(145). 사람이 쓴 기록과 같은 자리·같은
    형식이고, `상태변경` 태그라 타임라인에서 흐리게 서며 미보고 분량에 세지 않는다.
    **실패해도 본 작업을 막지 않는다.**
    """
    from . import entries as entries_service

    try:
        today = date_today()
        logs_dir = directory / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        target = paths.unique_path(logs_dir, entries_service.entry_stem(today, title), ".md")
        stamp = now_iso()
        meta = {
            "date": today,
            "title": title,
            "author": settings_service.current_author(None) or None,
            "tags": [STATUS_CHANGE_TAG],
            "attachments": [],
            "created_at": stamp,
            "updated_at": stamp,
        }
        md.save(target, md.MarkdownDoc(meta, body))
    except OSError:
        pass


def check_predecessors(conn: sqlite3.Connection, project_id: str | None, value: object) -> list[str]:
    """선행 과제 번호들을 받는다 (TODO 172). 비우면 [].

    * 여럿일 수 있다 — 앞 단계의 과제 둘을 이어받는 과제가 있다.
    * 있는 과제여야 한다 — 없는 번호를 적어 두면 위쪽 줄이 늘 "찾을 수 없음" 이 된다.
    * 자기 자신이나 **자기의 후속 과제**를 선행으로 둘 수 없다 — 고리가 생기면 단계를 셀 수 없다.
    """
    if value is None or value == "":
        return []
    items = value if isinstance(value, list) else str(value).split(",")
    out: list[str] = []
    for item in items:
        # 화면이 "2025-003 고강도 소재" 처럼 이름까지 보내도 번호만 쓴다
        text = str(item or "").strip().split()[0] if str(item or "").strip() else ""
        if not text or text in out:
            continue
        if project_id is not None and text == project_id:
            raise ValueError("자기 자신을 선행 과제로 둘 수 없습니다.")
        if conn.execute("SELECT 1 FROM project WHERE id = ?", (text,)).fetchone() is None:
            raise ValueError(f"선행 과제 {text} 를 찾을 수 없습니다.")
        if project_id is not None and project_id in _ancestors(conn, text):
            raise ValueError(f"{text} 는 이 과제의 후속 과제라 선행 과제로 둘 수 없습니다.")
        out.append(text)
    return out


def _predecessors_of(conn: sqlite3.Connection, project_id: str) -> list[str]:
    return [row[0] for row in conn.execute(
        "SELECT predecessor_id FROM project_predecessor WHERE project_id = ? ORDER BY predecessor_id", (project_id,)
    ).fetchall()]


def _successors_of(conn: sqlite3.Connection, project_id: str) -> list[str]:
    return [row[0] for row in conn.execute(
        "SELECT project_id FROM project_predecessor WHERE predecessor_id = ? ORDER BY project_id", (project_id,)
    ).fetchall()]


def _ancestors(conn: sqlite3.Connection, project_id: str) -> set[str]:
    """이 과제의 앞 단계 전부(선행의 선행 …)."""
    seen: set[str] = set()
    stack = _predecessors_of(conn, project_id)
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(_predecessors_of(conn, current))
    return seen


def stage_map(conn: sqlite3.Connection) -> dict[str, int]:
    """선행으로 이어진 과제마다 몇 단계인가 (TODO 175) — 과제명 뒤의 단계 띠가 쓴다.

    이어진 과제가 없는 과제는 **빠진다**(띠를 붙이지 않는다). 규칙은 줄기(172)와 같다 — 가장 긴 선행 길 + 1.
    표 한 번을 읽어 모두 센다: 과제목록처럼 여러 과제를 그릴 때 과제마다 따로 묻지 않게.
    """
    preds: dict[str, list[str]] = {}
    linked: set[str] = set()
    for row in conn.execute("SELECT project_id, predecessor_id FROM project_predecessor"):
        preds.setdefault(row["project_id"], []).append(row["predecessor_id"])
        linked.update((row["project_id"], row["predecessor_id"]))
    if not linked:
        return {}
    present = {row["id"] for row in conn.execute("SELECT id FROM project")}
    stage: dict[str, int] = {}

    def depth(node: str, trail: frozenset[str]) -> int:
        if node in stage:
            return stage[node]
        if node in trail or node not in present:
            return 1
        value = 1 + max((depth(p, trail | {node}) for p in preds.get(node, [])), default=0)
        stage[node] = value
        return value

    return {node: depth(node, frozenset()) for node in linked if node in present}


LINEAGE_LIMIT = 60  # 한 줄기에 이보다 많으면 무언가 잘못 이어진 것이다 — 화면이 무거워지지 않게 끊는다


def lineage(conn: sqlite3.Connection, project_id: str) -> dict[str, Any]:
    """다년도 과제의 줄기 (TODO 172) — 선행 · 후속으로 이어진 과제 **전부**를 단계별로.

    한 단계에 과제가 여럿일 수 있고(1단계 둘을 이어받는 2단계), 선행도 여럿일 수 있다.
    단계는 **선행을 따라 가장 길게 거슬러 올라간 길이 + 1** — 1단계 과제와 2단계 과제를 함께 이어받으면 3단계.
    선행이 보관함에 있거나 지워졌으면 그 자리에 `missing` 으로 남긴다 — 줄기가 끊겼다는 사실도 보여야 한다.
    """
    # 이어진 과제를 모두 모은다(선행 · 후속 양쪽으로)
    nodes: dict[str, dict[str, Any]] = {}
    queue = [project_id]
    while queue and len(nodes) < LINEAGE_LIMIT:
        current = queue.pop(0)
        if current in nodes:
            continue
        row = conn.execute(
            "SELECT id, title, status, start_date, due_date, completed_at FROM project WHERE id = ?", (current,)
        ).fetchone()
        # 기간의 끝 — 끝난 과제는 끝낸 날, 아니면 마감일 (과제 상세의 단계 칸이 연도를 적는다, TODO 176)
        nodes[current] = (
            {
                "id": row["id"], "title": row["title"], "status": row["status"], "start_date": row["start_date"],
                "end_date": (row["completed_at"] if row["status"] == DONE_STATUS and row["completed_at"] else row["due_date"]),
                "missing": False,
            }
            if row else {"id": current, "title": None, "status": None, "start_date": None, "end_date": None, "missing": True}
        )
        if row is None:
            continue  # 찾을 수 없는 과제 너머로는 가지 않는다
        queue.extend(_predecessors_of(conn, current))
        queue.extend(_successors_of(conn, current))
    if len(nodes) <= 1:
        return {"stage": None, "stages": [], "predecessors": [], "successors": []}

    # 단계 — 가장 긴 선행 길이 + 1 (고리는 막아 두었지만, 손으로 고친 파일에 대비해 깊이를 끊는다)
    stage: dict[str, int] = {}

    def depth(node: str, trail: frozenset[str]) -> int:
        if node in stage:
            return stage[node]
        if node in trail or nodes[node]["missing"]:
            return 1
        preds = [p for p in _predecessors_of(conn, node) if p in nodes]
        value = 1 + max((depth(p, trail | {node}) for p in preds), default=0)
        stage[node] = value
        return value

    for node in nodes:
        depth(node, frozenset())
    grouped: dict[int, list[dict[str, Any]]] = {}
    for node, info in nodes.items():
        grouped.setdefault(stage.get(node, 1), []).append({**info, "here": node == project_id})
    return {
        "stage": stage.get(project_id),
        "stages": [
            {"stage": number, "items": sorted(items, key=lambda item: (item["start_date"] or "9999", item["id"]))}
            for number, items in sorted(grouped.items())
        ],
        "predecessors": _predecessors_of(conn, project_id),
        "successors": _successors_of(conn, project_id),
    }


def rewrite_project_refs(conn: sqlite3.Connection, mapping: dict[str, str]) -> int:
    """과제 번호가 바뀌었을 때 **다른 파일이 적어 둔 그 번호**를 고친다 (TODO 172).

    번호 일괄 변경 · 연도 맞추기가 과제 자신의 id 와 폴더만 바꿔, 후속 과제의 `predecessors` 와 접수의
    `project_id` · `merged_into` · `demoted_from` 이 옛 번호를 가리킨 채 남았다(접수 링크는 136 부터 있던 틈).
    """
    if not mapping:
        return 0
    settings = get_settings()
    changed = 0
    for path in settings.projects_dir.glob("*/index.md"):
        try:
            doc = md.load(path)
        except Exception:  # 읽지 못하는 파일은 색인이 따로 알린다
            continue
        old = doc.meta.get("predecessors")
        if not isinstance(old, list) or not any(str(item) in mapping for item in old):
            continue
        doc.meta["predecessors"] = [mapping.get(str(item), str(item)) for item in old]
        md.save(path, doc)
        changed += 1
    for path in settings.intakes_dir.glob("*/request.md"):
        try:
            doc = md.load(path)
        except Exception:
            continue
        updates = {key: mapping[str(doc.meta.get(key))]
                   for key in ("project_id", "merged_into", "demoted_from") if str(doc.meta.get(key) or "") in mapping}
        if not updates:
            continue
        doc.meta.update(updates)
        md.save(path, doc)
        changed += 1
    return changed


def update_project(conn: sqlite3.Connection, project_id: str, updates: dict[str, Any]) -> None:
    directory = project_dir(conn, project_id)
    index_md = directory / "index.md"
    known = conn.execute("SELECT file_mtime FROM project WHERE id = ?", (project_id,)).fetchone()
    md.ensure_unchanged(index_md, known["file_mtime"] if known else None)
    doc = md.load(index_md)

    if "status" in updates and updates["status"] not in STATUS_KEYS:
        raise ValueError(f"알 수 없는 상태: {updates['status']}")
    if updates.get("type") and updates["type"] not in settings_service.type_keys():
        raise ValueError(f"알 수 없는 속성: {updates['type']}")

    body = updates.pop("body", None)
    for field in ("effect_expected", "effect_verified"):
        if field in updates:
            updates[field] = normalize_effect(updates[field])
    if "no_report" in updates:
        updates["no_report"] = bool(updates["no_report"])
    if "no_effect" in updates:
        updates["no_effect"] = bool(updates["no_effect"])
    if "partners" in updates:
        updates["partners"] = normalize_partners(updates["partners"])
    for key in CLASSIFICATION_KEYS:
        if key in updates:
            updates[key] = normalize_label(updates[key])
    # 승격으로 붙은 접수 번호는 화면에서 고치지 않는다 — 양쪽 링크가 어긋난다.
    updates.pop("intake_id", None)
    if "predecessors" in updates:
        updates["predecessors"] = check_predecessors(conn, project_id, updates["predecessors"])
    if "owners" in updates or "owner" in updates:
        updates["owners"] = normalize_owners(updates.pop("owners", None) or updates.pop("owner", None))
    if "completed_at" in updates:
        updates["completed_at"] = normalize_day(updates["completed_at"])
    changes = {k: v for k, v in updates.items() if k in META_ORDER or k == "group"}
    # 예전 문서의 owner(단수) 키가 남아 있으면 owners로 옮겨 적는다.
    if "owners" in changes and "owner" in doc.meta:
        doc.meta.pop("owner")

    # ── 완료일 (TODO 104) ── 상태가 완료가 되는 순간 남기고, 완료에서 벗어나면 비운다.
    # 손으로 적은 완료일이 함께 오면 그것이 이긴다.
    old_status = str(doc.meta.get("status") or "")
    new_status = str(changes.get("status") or old_status)
    if new_status == DONE_STATUS and old_status != DONE_STATUS and not changes.get("completed_at"):
        changes["completed_at"] = doc.meta.get("completed_at") or date_today()
    if new_status != DONE_STATUS and old_status == DONE_STATUS and "completed_at" not in changes:
        changes["completed_at"] = None

    meta = md.merge_meta(doc.meta, changes)
    meta["updated_at"] = now_iso()
    md.save(index_md, md.MarkdownDoc(meta, body if body is not None else doc.body))

    # ── 상태 변경 이력 (TODO 105) ── 진행일지에 한 줄 남긴다. 파일이 원본이라는 원칙에
    # 맞고, 타임라인에 그대로 보이며, 다음 보고 초안에 "이 기간에 보류됐음" 이 저절로 든다.
    if new_status != old_status and old_status:
        _log_status_change(directory, old_status, new_status)

    new_title = meta.get("title")
    if new_title:
        expected = paths.project_dir_name(project_id, str(new_title))
        if expected != directory.name:
            target = paths.safe_join(get_settings().projects_dir, expected)
            if target.exists():  # 남아 있던 폴더와 겹치면 뒤에 번호를 붙인다
                target = paths.unique_path(get_settings().projects_dir, expected, "")
            paths.move(directory, target)
            versions.follow(directory, target)  # 이전 버전도 따라온다 (TODO 142)
            directory = target

    index_project(conn, directory)
    conn.commit()


def clone_draft(conn: sqlite3.Connection, source_id: str) -> dict[str, Any]:
    """이 과제를 바탕으로 새 과제 — **미리 채울 값만** 돌려준다 (TODO 109 · 173).

    해마다 도는 과제("2025년 수명평가 표준화" → "2026년 …")는 속성·그룹·담당자·유관부서가
    같다. 지금까지는 처음부터 다시 쳤다. **가져오는 것**은 그 정보와 개요 본문이고,
    **가져오지 않는 것**은 진행일지·보고·첨부·효과 금액·날짜다 — 새 과제의 이력은 비어
    있어야 하고, 효과와 기간은 새로 정할 일이다. 원래 과제를 **선행 과제**로 이어(172) 두 과제가
    한 줄기임이 파일과 상세 위쪽에 보이게 한다.

    여기서는 **만들지 않는다**(173). 처음(109)에는 누르는 순간 만들고 수정 칸을 열었는데, 그 칸의
    [취소]가 만든 과제를 지우지 않아 "취소했는데 과제가 생겼다" — 게다가 번호는 다시 쓰지 않으므로(146)
    취소할 때마다 그해 번호가 하나씩 비었다. 화면이 이 값으로 새 과제 칸을 채우고, [만들기]가
    보통의 과제 만들기(`POST /api/projects`)를 부른다.
    """
    row = conn.execute("SELECT * FROM project WHERE id = ?", (source_id,)).fetchone()
    if row is None:
        raise KeyError(source_id)
    doc = md.load(project_dir(conn, source_id) / "index.md")
    meta = doc.meta
    return {
        "title": str(meta.get("title") or row["title"]),
        "status": "planned",
        "type": meta.get("type"),
        "group": meta.get("group"),
        "tags": list(meta.get("tags") or []),
        "owners": list(meta.get("owners") or []),
        "partners": normalize_partners(meta.get("partners")),
        "no_report": bool(meta.get("no_report")),
        "no_effect": bool(meta.get("no_effect")),
        # 같은 줄기의 과제라 분류도 같다 (TODO 136). 접수 번호는 넘기지 않는다.
        **{key: meta.get(key) for key in CLASSIFICATION_KEYS},
        # 다음 단계 과제 — 원래 과제를 선행으로 잇는다 (TODO 172). 칸에서 뺄 수 있다.
        "predecessors": [source_id],
        "body": doc.body or "",
    }


def clone_project(conn: sqlite3.Connection, source_id: str) -> str:
    """미리 채운 값 그대로 만든다 — 시험과 손으로 부르는 길을 위해 남긴다."""
    return create_project(conn, clone_draft(conn, source_id))


def archive_project(conn: sqlite3.Connection, project_id: str) -> None:
    """삭제하지 않고 .trash/ 로 옮긴다."""
    settings = get_settings()
    directory = project_dir(conn, project_id)
    settings.trash_dir.mkdir(parents=True, exist_ok=True)
    target = paths.unique_path(settings.trash_dir, f"{directory.name}-{datetime.now():%Y%m%d%H%M%S}", "")
    row = conn.execute("SELECT title FROM project WHERE id = ?", (project_id,)).fetchone()
    paths.move(directory, target)
    trash_service.record(
        "project",
        label=f"{project_id} {row['title'] if row else directory.name}",
        moved_to=target,
        origin=directory,
        project_id=project_id,
    )
    conn.execute("DELETE FROM project WHERE id = ?", (project_id,))
    conn.execute("DELETE FROM search_fts WHERE project_id = ?", (project_id,))
    # 이 과제로 착수·병합된 접수는 풀로 돌아간다 — 미아가 되지 않게 (TODO 145)
    from . import intakes as intakes_service

    intakes_service.detach_from_project(conn, project_id, row["title"] if row else directory.name)
    conn.commit()
