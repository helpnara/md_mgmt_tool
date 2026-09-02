from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import deps
from .api import attachments, dashboard, entries, export, meta, projects, reports, search, settings, trash
from .config import REPO_ROOT, get_settings
from .vault.paths import safe_join
from .vault.indexer import reindex_all

FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.ensure_dirs()
    conn, rebuilt = deps.setup()
    if rebuilt:
        print("\n  프로그램이 새 버전으로 바뀌어 검색 색인을 다시 만듭니다.")
        print("  (색인은 md 파일에서 다시 만들어지므로 작성한 내용은 그대로입니다)")
    # 외부 편집기로 바뀐 내용을 기동 시점에 반영한다.
    indexed, problems = reindex_all(conn)
    if problems:
        print(f"\n  [주의] 읽지 못한 파일 {len(problems)}건 — front matter를 확인하세요:")
        for item in problems[:10]:
            print(f"    - {item.rel_path}: {item.reason}")
    print(f"  과제 {indexed}건을 읽었습니다.")
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
app.include_router(dashboard.router)
app.include_router(projects.router)
app.include_router(entries.router)
app.include_router(attachments.router)
app.include_router(reports.router)
app.include_router(search.router)
app.include_router(export.router)
app.include_router(settings.router)
app.include_router(trash.router)

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
