from __future__ import annotations

import re
import sqlite3
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from ..deps import get_db
from ..services import export as svc

router = APIRouter(prefix="/api", tags=["export"])


def _attachment(content: bytes | str, filename: str, media_type: str) -> Response:
    # 한글 파일명은 RFC 5987 형식으로 보내되, 그것을 모르는 도구(curl -OJ 등)를 위해
    # ASCII 대체 이름도 함께 넣는다.
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "-", filename).strip("-") or "export"
    disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
    body = content.encode("utf-8") if isinstance(content, str) else content
    return Response(content=body, media_type=media_type, headers={"Content-Disposition": disposition})


@router.get("/projects/{project_id}/export")
def export_project(
    project_id: str,
    format: str = Query("zip", pattern="^(md|zip|html|backup)$"),
    assets: str = Query("zip", pattern="^(zip|inline|link)$"),
    include_reports_full: bool = False,
    conn: sqlite3.Connection = Depends(get_db),
) -> Response:
    """과제 이력을 한 덩어리로 내보낸다.

    - md   : 마크다운 한 파일 (assets=inline이면 이미지를 파일 안에 심는다)
    - zip  : 병합 마크다운 + 참조된 첨부 (압축을 풀면 링크가 그대로 살아 있다)
    - html : 이미지까지 담긴 단일 HTML
    - backup: 과제 폴더 원본 구조 그대로
    """
    try:
        if format == "zip":
            filename, content = svc.export_zip(conn, project_id, include_reports_full)
            return _attachment(content, filename, "application/zip")
        if format == "backup":
            filename, content = svc.backup_zip(conn, project_id)
            return _attachment(content, filename, "application/zip")
        if format == "html":
            filename, text = svc.export_html(conn, project_id, include_reports_full)
            return _attachment(text, filename, "text/html; charset=utf-8")

        filename, text, _ = svc.merged_markdown(conn, project_id, assets, include_reports_full)
        return _attachment(text, filename, "text/markdown; charset=utf-8")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="과제를 찾을 수 없습니다.") from exc
