"""해마다 남기는 팀 역량 기록 (TODO 292 G).

팀 역량 화면은 그때그때 계산한다 — 경험을 고치거나 사람이 떠나면 "작년 말 우리 팀" 의 그림이 사라진다.
[올해 기록 남기기]가 그 순간의 요약을 `team/snapshots/<해>.md` 에 고정한다(사람이 읽는 표 + 비교용 값은 머리 정보).

* 남기는 것 — 사람 · 역량마다 가진 사람 · 보유 기술(층) · 혼자만 가진 것 · 목표 대비 · 축별 경험 수. 경험 내용은 담지 않는다.
* 저절로 — 해가 바뀐 뒤 1 ~ 2월에 팀 역량을 처음 열 때 지난해 기록이 없으면 한 벌(`auto: true`).
* 비교 — 지난해 기록 ↔ 지금: 사람 · 역량 · 보유 기술의 가진 사람 수, 혼자만 가진 것의 풀림 · 새로 생김.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from .. import clock
from ..config import get_settings
from ..vault import markdown as md

AUTO_MONTHS = (1, 2)
LIST_MAX = 12


def folder() -> Path:
    return get_settings().vault_dir / "team" / "snapshots"


def _path(year: str) -> Path:
    if not re.fullmatch(r"\d{4}", str(year or "")):
        raise ValueError("해는 네 자리 숫자입니다.")
    return folder() / f"{year}.md"


def _data(view: dict[str, Any]) -> dict[str, Any]:
    """팀 역량 화면의 값 → 기록에 남길 값(이름 · 수만)."""
    return {
        "period": view.get("period"),
        "people": [p["name"] for p in view.get("people", [])],
        "skills": [{"axis": r["axis"], "name": r["name"], "group": r.get("group") or "", "holders": sorted(r["cells"]),
                    "experiences": r["experiences"]} for r in view.get("skills", []) if r.get("holders")],
        "tools": [{"layer": layer["layer"], "name": t["name"], "holders": list(t["people"])}
                  for layer in view.get("stack", []) for t in layer["tools"]],
        "only_one": [{"kind": o["kind"], "name": o["name"], "person": o["person"]} for o in view.get("only_one", [])],
        "targets": [{"kind": t.get("kind"), "name": t.get("name"), "want": t.get("want"), "have": t.get("have")} for t in view.get("targets", [])],
        "shape": [{"axis": s.get("axis"), "experiences": s.get("experiences"), "held": s.get("held")} for s in view.get("shape", [])],
    }


def _body(year: str, data: dict[str, Any], saved_at: str, auto: bool) -> str:
    lines = [f"# {year} 팀 역량 기록", "",
             f"> {saved_at[:16].replace('T', ' ')} 에 {'저절로 ' if auto else ''}남김 — 그때의 그림입니다. 경험이 고쳐져도 바뀌지 않습니다.", "",
             f"## 사람 {len(data['people'])}명", "", ", ".join(data["people"]) or "(없음)", "",
             "## 역량 — 가진 사람", "", "| 축 | 역량 | 가진 사람 | 경험 |", "|---|---|---|---|"]
    for r in sorted(data["skills"], key=lambda r: (r["axis"], -len(r["holders"]), r["name"])):
        lines.append(f"| {r['axis']} | {r['name']} | {', '.join(r['holders'])} | {r['experiences']} |")
    lines += ["", "## 보유 기술(도구)", "", "| 층 | 보유 기술 | 쓴 사람 |", "|---|---|---|"]
    for t in data["tools"]:
        lines.append(f"| {t['layer']} | {t['name']} | {', '.join(t['holders'])} |")
    lines += ["", f"## 혼자만 가진 것 {len(data['only_one'])}개", ""]
    lines += [f"- {o['kind']} · {o['name']} — {o['person']}" for o in data["only_one"]] or ["(없음)"]
    if data["targets"]:
        lines += ["", "## 목표 대비", "", "| 구분 | 목표 | 목표 사람 수 | 그때 |", "|---|---|---|---|"]
        lines += [f"| {t['kind']} | {t['name']} | {t['want']} | {t['have']} |" for t in data["targets"]]
    lines += ["", "*팀장이 팀의 득과 실을 판단하는 자료입니다 — 평가 · 다른 사람과의 비교에 쓰지 않습니다.*", ""]
    return "\n".join(lines)


def save(conn: sqlite3.Connection, year: str | None = None, auto: bool = False, by: str = "") -> dict[str, Any]:
    from . import team_skills

    year = year or str(clock.today().year)
    path = _path(year)
    view = team_skills.overview(conn, "3y")
    data = _data(view)
    saved_at = clock.now().isoformat(timespec="seconds")
    meta = {"year": year, "saved_at": saved_at, "auto": auto, "by": by, "data": data}
    path.parent.mkdir(parents=True, exist_ok=True)
    md.save(path, md.MarkdownDoc(meta, _body(year, data, saved_at, auto)))   # 같은 해를 다시 남기면 이전 것은 이전 버전에
    return {"year": year, "saved_at": saved_at, "auto": auto}


def read(year: str) -> dict[str, Any] | None:
    path = _path(year)
    if not path.is_file():
        return None
    doc = md.load(path)
    meta = doc.meta or {}
    return {"year": str(meta.get("year") or year), "saved_at": str(meta.get("saved_at") or ""), "auto": bool(meta.get("auto")),
            "by": str(meta.get("by") or ""), "data": meta.get("data") or {}, "body": doc.body}


def listing() -> list[dict[str, Any]]:
    out = []
    for path in sorted(folder().glob("*.md"), reverse=True) if folder().is_dir() else []:
        if not re.fullmatch(r"\d{4}", path.stem):
            continue
        try:
            item = read(path.stem)
        except Exception:  # noqa: BLE001 — 손으로 고쳐 깨진 기록 하나로 목록이 막히지 않게
            continue
        if item:
            out.append({"year": item["year"], "saved_at": item["saved_at"], "auto": item["auto"]})
    return out


def ensure_last_year(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """해가 바뀐 뒤 1 ~ 2월 — 지난해 기록이 없고 팀 자료가 있으면 저절로 한 벌. 이미 있거나 철이 아니면 None."""
    today = clock.today()
    if today.month not in AUTO_MONTHS:
        return None
    last = str(today.year - 1)
    if _path(last).is_file():
        return None
    has = conn.execute("SELECT 1 FROM experience WHERE status IN ('구조화', '확정') LIMIT 1").fetchone()
    if not has:
        return None
    return save(conn, last, auto=True, by="저절로")


def compare(old: dict[str, Any], view: dict[str, Any]) -> dict[str, Any]:
    """기록(그때) ↔ 지금 — 가진 사람 수로 견준다(경험 수가 아니라)."""
    now = _data(view)

    def diff(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> dict[str, Any]:
        b = {r["name"]: len(r["holders"]) for r in before}
        a = {r["name"]: len(r["holders"]) for r in after}
        new = sorted(n for n in a if n not in b)
        lost = sorted(n for n in b if n not in a)
        up = sorted(({"name": n, "last": b[n], "this": a[n]} for n in a if n in b and a[n] > b[n]), key=lambda r: (r["last"] - r["this"], r["name"]))
        down = sorted(({"name": n, "last": b[n], "this": a[n]} for n in a if n in b and a[n] < b[n]), key=lambda r: (r["this"] - r["last"], r["name"]))
        return {"new": new[:LIST_MAX * 2], "lost": lost[:LIST_MAX], "up": up[:LIST_MAX], "down": down[:LIST_MAX],
                "counts": {"new": len(new), "lost": len(lost), "up": len(up), "down": len(down)}}

    data = old.get("data") or {}
    before_one = {(o["kind"], o["name"]) for o in data.get("only_one", [])}
    after_one = {(o["kind"], o["name"]) for o in now["only_one"]}
    before_people, after_people = set(data.get("people", [])), set(now["people"])
    return {
        "year": old.get("year"), "saved_at": old.get("saved_at"), "auto": old.get("auto"),
        "people": {"last": len(before_people), "this": len(after_people),
                   "joined": sorted(after_people - before_people), "left": sorted(before_people - after_people)},
        "skills": diff(data.get("skills", []), now["skills"]),
        "tools": diff(data.get("tools", []), now["tools"]),
        "only_one": {"last": len(before_one), "this": len(after_one),
                     "resolved": sorted(f"{k} · {n}" for k, n in before_one - after_one),
                     "new": sorted(f"{k} · {n}" for k, n in after_one - before_one)},
    }


def last_year_compare(view: dict[str, Any]) -> dict[str, Any] | None:
    """지난해(없으면 그 앞의 가장 가까운 해) 기록 ↔ 지금. 올해 기록은 견주지 않는다(같은 해)."""
    this_year = int(view.get("year") or clock.today().year)
    for item in listing():
        if int(item["year"]) < this_year:
            old = read(item["year"])
            return compare(old, view) if old else None
    return None

