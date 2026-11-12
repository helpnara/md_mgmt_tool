"""보유 기술 사전 (TODO 273) — 언어 · 소프트웨어 · 장비 · 플랫폼의 대표 이름과 다른 이름.

역량(무엇을 할 줄 아는가 — 행동 · 방법, 분석 기법 포함)과 보유 기술(무엇으로 했는가 — 이름만으로 "쓸 줄 안다" 가 성립하는 것)을 가른다.
예전에는 "도구인가" 를 **누군가 과제의 기술 · 도구 칸에 적은 적 있는 이름 전부**로 봤다 — 그 칸에 "회귀 분석" 을 적으면
역량 태그 "회귀 분석" 이 말없이 도구 칸으로 넘어갔다. 이제 이 사전에 있는 이름만 보유 기술로 본다.
표기도 여기서 맞춘다(파이썬 = Python). 파일 · DB 를 모른다(skills.py 와 같은 결).
"""
from __future__ import annotations

from typing import Any, Iterable

from .skills import key

NAME_MAX = 60
ALIAS_MAX = 20
DICT_MAX = 300

# (대표 이름, 다른 이름) — 제조 · 데이터 분석 팀에서 흔한 것. 설정에서 고친다.
DEFAULT_TOOLS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Python", ("파이썬",)),
    ("SQL", ()),
    ("R", ()),
    ("C#", ("C Sharp", "씨샵")),
    ("C++", ()),
    ("Java", ("자바",)),
    ("JavaScript", ("JS", "자바스크립트")),
    ("MATLAB", ("매트랩",)),
    ("Excel", ("엑셀", "MS Excel")),
    ("VBA", ("엑셀 매크로",)),
    ("Power BI", ("PowerBI", "파워 BI")),
    ("Tableau", ("태블로",)),
    ("Spotfire", ("스팟파이어",)),
    ("Minitab", ("미니탭",)),
    ("pandas", ()),
    ("scikit-learn", ("sklearn", "사이킷런")),
    ("PyTorch", ("파이토치",)),
    ("TensorFlow", ("텐서플로",)),
    ("Git", ("깃",)),
    ("GitHub Actions", ()),
    ("Docker", ("도커",)),
    ("Linux", ("리눅스",)),
    ("GPU", ()),
    ("HPC", ()),
    ("MES", ()),
    ("ERP", ()),
    ("SAP", ()),
    ("PLC", ()),
    ("RFID", ()),
    ("Teams Copilot", ("Copilot", "코파일럿")),
)
# 284 — 보유 기술의 층(기술 스택 그림의 줄). 층 이름은 사전 항목마다 글로 적는다 — 새 층 이름을 적으면 새 줄이 된다
LAYER_MAX = 20
DEFAULT_LAYERS = ("언어", "데이터", "분석/AI", "시각화", "개발/플랫폼", "설비/제어", "사내 시스템", "업무 도구")
DEFAULT_LAYER: dict[str, str] = {
    **{n: "언어" for n in ("Python", "SQL", "R", "C#", "C++", "Java", "JavaScript", "MATLAB", "VBA")},
    "pandas": "데이터",
    **{n: "분석/AI" for n in ("scikit-learn", "PyTorch", "TensorFlow", "Minitab")},
    **{n: "시각화" for n in ("Power BI", "Tableau", "Spotfire")},
    **{n: "개발/플랫폼" for n in ("Git", "GitHub Actions", "Docker", "Linux", "GPU", "HPC")},
    **{n: "설비/제어" for n in ("PLC", "RFID")},
    **{n: "사내 시스템" for n in ("MES", "ERP", "SAP")},
    **{n: "업무 도구" for n in ("Excel", "Teams Copilot")},
}
# 273 — 역량 사전(기본)의 동의어에 있던 도구 이름. 고친 역량 사전에 남아 있어도 보유 기술 사전이 먼저다
FORMER_SKILL_ALIASES = ("C#", "GPU", "HPC", "GitHub Actions", "RFID")


def default_dictionary() -> list[dict[str, Any]]:
    return [{"name": name, "aliases": list(aliases), "layer": DEFAULT_LAYER.get(name, "")} for name, aliases in DEFAULT_TOOLS]


def validate(value: Any) -> list[dict[str, Any]] | None:
    """설정 `tool_dictionary` 의 모양 — None · 빈 목록이면 기본. 이름 60자 · 같은 이름(다른 이름 포함) 없음 · 다른 이름 20개까지 · 층(284) 20자."""
    if value is None or value == []:
        return None
    if not isinstance(value, list):
        raise ValueError("보유 기술 사전은 목록이어야 합니다.")
    if len(value) > DICT_MAX:
        raise ValueError(f"보유 기술 사전은 {DICT_MAX}개까지입니다.")
    out: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError("보유 기술 사전의 항목 모양이 다릅니다.")
        name = " ".join(str(raw.get("name") or "").split())
        if not name or len(name) > NAME_MAX:
            raise ValueError(f"보유 기술 이름은 1 ~ {NAME_MAX}자입니다: {name[:20] or '(빈칸)'}")
        if key(name) in seen:
            raise ValueError(f"같은 보유 기술이 두 번 있습니다: {name} (‘{seen[key(name)]}’ 과 겹침)")
        aliases_raw = raw.get("aliases") or []
        if isinstance(aliases_raw, str):
            aliases_raw = aliases_raw.split(",")
        aliases = list(dict.fromkeys(a for a in (" ".join(str(x).split()) for x in aliases_raw) if a and key(a) != key(name)))
        if len(aliases) > ALIAS_MAX or any(len(a) > NAME_MAX for a in aliases):
            raise ValueError(f"다른 이름은 {ALIAS_MAX}개 · 각 {NAME_MAX}자까지입니다: {name}")
        for label in aliases:
            if key(label) in seen:
                raise ValueError(f"다른 이름 ‘{label}’ 이 ‘{seen[key(label)]}’ 과 겹칩니다.")
        seen[key(name)] = name
        for label in aliases:
            seen[key(label)] = name
        # 층(284) — 층 칸이 없던 옛 사전은 기본 층으로 채운다(대표 이름이 기본과 같을 때)
        layer = " ".join(str(raw.get("layer") or "").split()) if "layer" in raw else DEFAULT_LAYER.get(name, "")
        if len(layer) > LAYER_MAX:
            raise ValueError(f"층 이름은 {LAYER_MAX}자까지입니다: {name}")
        out.append({"name": name, "aliases": aliases, "layer": layer})
    return out


def index(dictionary: Iterable[dict[str, Any]]) -> dict[str, str]:
    """열쇠 → 대표 이름. 대표 이름이 다른 이름보다 먼저."""
    found: dict[str, str] = {}
    items = list(dictionary)
    for item in items:
        found.setdefault(key(item["name"]), item["name"])
    for item in items:
        for alias in item.get("aliases") or []:
            found.setdefault(key(alias), item["name"])
    return found


def normalize(names: Iterable[str], dictionary: Iterable[dict[str, Any]]) -> list[str]:
    """이름을 사전에 맞춘다 — 맞으면 대표 이름, 아니면 그대로. 같은 것은 하나로(순서 유지)."""
    table = index(dictionary)
    out: list[str] = []
    seen: set[str] = set()
    for raw in names:
        name = " ".join(str(raw or "").split())
        if not name:
            continue
        name = table.get(key(name), name)
        if key(name) not in seen:
            seen.add(key(name))
            out.append(name)
    return out


def mentioned(text: str, dictionary: Iterable[dict[str, Any]]) -> list[str]:
    """글에 나오는 사전의 보유 기술(대표 이름으로) — 확정 전 알림용. 영문 · 숫자 이름은 낱말 경계로(R 이 "ERP" 에 걸리지 않게)."""
    import re

    found: list[str] = []
    for item in dictionary:
        for label in [item["name"], *(item.get("aliases") or [])]:
            if re.fullmatch(r"[A-Za-z0-9+#.\- ]+", label):
                hit = re.search(rf"(?<![A-Za-z0-9]){re.escape(label)}(?![A-Za-z0-9+#])", text or "", re.IGNORECASE)
            else:
                hit = label in (text or "")
            if hit:
                if item["name"] not in found:
                    found.append(item["name"])
                break
    return found
