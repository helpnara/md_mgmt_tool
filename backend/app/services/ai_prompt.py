"""AI 요약 프롬프트 만들기 (TODO 71 · T14 (가)안).

**이 도구는 AI 를 부르지 않는다.** 인터넷이 차단된 사내 PC 에서 돌기 때문이기도 하고,
과제 내용을 어디로 보낼지는 사람이 정할 일이기 때문이기도 하다
(vault 를 git 저장소로 두지 않기로 한 것과 같은 판단).

여기서 하는 일은 하나다 — **붙여넣기 좋은 글 한 덩이를 만들어 준다.**
사용자가 사내에서 승인된 AI 도구에 붙여넣고, 나온 요약을 보고 본문에 옮긴다.
나가는 것이 없으니 정책 승인이 필요 없고, 사내 AI 도구가 무엇으로 바뀌어도 그대로 쓴다.

앞뒤에 붙는 글은 **설정에서 사용자가 정한다.** 회사마다 보고처마다 원하는 말투가
다르므로 코드에 굳혀 두면 안 된다. 비워 두면 아래 기본 지시문을 쓴다.
"""
from __future__ import annotations

import sqlite3

# 비워 두었을 때 쓰는 기본 지시문. 사용자가 자기 프롬프트를 넣으면 그것이 이긴다.
DEFAULT_PREFIX = """아래는 한 과제의 지난 보고 이후 진행 내용입니다.
주간 보고용으로 3~5줄로 요약해 주세요.

규칙
- 원문에 있는 사실만 씁니다. 없는 수치나 판단을 만들어 내지 마세요
- 수치가 있으면 반드시 남깁니다
- "~함", "~예정" 체로 씁니다
- 마지막 줄에 다음 계획을 한 줄로 넣습니다"""

# 뒤에 붙는 글은 기본값을 두지 않는다. 필요한 사람만 채운다.
DEFAULT_SUFFIX = ""

SEPARATOR = "--- 진행 내용 ---"


def build(conn: sqlite3.Connection, report_id: int) -> str:
    """보고 문서 하나를 AI 에게 넘길 글 한 덩이로 만든다.

    본문은 **마크다운 그대로** 넣는다. 평문으로 눌러 담으면 표와 목록의 구조가
    사라지는데, AI 는 마크다운을 그대로 읽는다. 잃을 것만 있고 얻을 것이 없다.
    """
    from . import settings as settings_service

    row = conn.execute(
        "SELECT r.*, p.title AS project_title FROM report r"
        " JOIN project p ON p.id = r.project_id WHERE r.id = ?",
        (report_id,),
    ).fetchone()
    if row is None:
        raise KeyError(report_id)

    facts = [
        f"과제: {row['project_title']} ({row['project_id']})",
        f"보고일: {row['report_date']}",
    ]
    if row["covers_from"]:
        facts.append(f"포함 기간: {row['covers_from']} ~ {row['covers_to']}")
    if row["audience"]:
        facts.append(f"피보고자: {row['audience']}")

    body = (row["body"] or "").strip()
    parts = [
        settings_service.ai_prompt_prefix(),
        "\n".join(facts),
        f"{SEPARATOR}\n{body}" if body else f"{SEPARATOR}\n(진행 내용이 비어 있습니다)",
        settings_service.ai_prompt_suffix(),
    ]
    return "\n\n".join(part for part in (p.strip() for p in parts) if part) + "\n"


__all__ = ["build", "DEFAULT_PREFIX", "DEFAULT_SUFFIX", "SEPARATOR"]
