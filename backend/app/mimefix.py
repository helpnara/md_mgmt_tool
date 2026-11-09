"""웹 파일 종류를 PC 설정과 상관없이 고정한다 (TODO 245).

윈도우의 파이썬은 `mimetypes` 표를 **레지스트리**(`HKEY_CLASSES_ROOT\\.js` 의 `Content Type`)로 덮어쓴다. 다른 프로그램이
이 값을 `text/plain` 으로 바꿔 둔 PC 에서는 화면 묶음(`/assets/index-*.js`)이 '일반 글' 로 나가고, 브라우저는 모듈 스크립트를
실행하지 않는다 → 오류 글도 없는 **흰 화면**. 관리자 권한 창에서는 사용자 쪽 값(HKCU)이 보이지 않아 찾기도 어렵다
(2026-11-09 새 운영 서버에서 실제로 겪음). 그래서 화면에 쓰는 파일의 종류는 프로그램이 정한다.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

# 화면 묶음 · 아이콘 · 글꼴 — vite 빌드가 내는 것과 첨부 미리보기에 흔한 것
WEB_TYPES: dict[str, str] = {
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".css": "text/css",
    ".html": "text/html",
    ".json": "application/json",
    ".map": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
}

# 브라우저가 스크립트로 받아 주는 이름들 — 이것이면 PC 설정이 "틀렸다" 고 알리지 않는다
_JS_OK = {"text/javascript", "application/javascript", "application/x-javascript"}


def ensure() -> list[tuple[str, str | None, str]]:
    """`mimetypes` 표에 WEB_TYPES 를 덮어쓴다. **브라우저가 받지 못할 값이었던 것**만 (확장자, 전 값, 새 값) 으로 돌려준다."""
    wrong: list[tuple[str, str | None, str]] = []
    for ext, kind in WEB_TYPES.items():
        before = mimetypes.guess_type("a" + ext)[0]
        if before != kind:
            if ext in (".js", ".mjs"):
                if before not in _JS_OK:
                    wrong.append((ext, before, kind))
            elif ext in (".css", ".html", ".svg"):
                wrong.append((ext, before, kind))
            mimetypes.add_type(kind, ext)
    return wrong


def media_type(path: str | Path) -> str:
    """화면 파일의 종류 — 고정 표가 먼저, 없으면 `mimetypes`, 그것도 없으면 바이트."""
    suffix = Path(path).suffix.lower()
    return WEB_TYPES.get(suffix) or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
