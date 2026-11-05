"""두 사람이 같은 글을 고칠 때 — 나중 저장이 말없이 이기지 않게 (TODO 233 R7 · 로드맵 3.3 의 5).

예전의 막이(`markdown.ensure_unchanged`)는 **색인에 적힌 파일 시각**과 비교해 옵시디언 · 탐색기로 고친 것만 잡았다.
두 사람이 브라우저로 같은 글을 열어 두고 차례로 저장하면 앞 사람의 저장이 색인 시각도 새로 고쳐, 나중 사람이 말없이 덮었다.
그래서 화면이 **연 때의 최근 수정 시각**(`base_updated_at`)을 보내고, 그 뒤 바뀌었으면 409 로 돌려보낸다 — 잠그지 않고 알린다(로드맵 3.6).
"""
from __future__ import annotations

from fastapi import HTTPException

from . import edits


def check(base: str | None, current: str | None, project_id: str | None, entry_id: int | None) -> None:
    if not base or not current or base == current:
        return
    who = edits.last_editor(project_id, entry_id, base)
    at = current[11:16] if len(current) >= 16 else current
    by = f"{who} 님이 " if who else "다른 곳에서 "
    raise HTTPException(
        status_code=409,
        detail=f"이 글을 연 뒤 {by}{at} 에 먼저 고쳤습니다. 내가 쓴 글을 복사해 두고 [새로 열기]로 다시 연 뒤 합쳐 주세요.",
    )
