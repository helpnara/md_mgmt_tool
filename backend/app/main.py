from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import deps
from .api import attachments, entries, meta, projects, reports, search
from .config import REPO_ROOT, get_settings
from .vault.paths import safe_join
from .vault.indexer import reindex_all

FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.ensure_dirs()
    conn = deps.setup()
    # 외부 편집기로 바뀐 내용을 기동 시점에 반영한다.
    reindex_all(conn)
    yield
    deps.teardown()


app = FastAPI(title="과제 이력 관리 도구", version="0.1.0", lifespan=lifespan)

# 로컬 개발 시 Vite 개발 서버(5173)에서 API를 호출할 수 있게 한다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meta.router)
app.include_router(projects.router)
app.include_router(entries.router)
app.include_router(attachments.router)
app.include_router(reports.router)
app.include_router(search.router)

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str) -> FileResponse:
        # 빌드 결과 밖을 가리키는 경로는 무시하고 SPA 진입점을 돌려준다.
        try:
            candidate = safe_join(FRONTEND_DIST, full_path) if full_path else None
        except ValueError:
            candidate = None
        if candidate is not None and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
