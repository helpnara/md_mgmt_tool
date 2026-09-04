from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import (http_exception_handler,
                                        request_validation_exception_handler)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import deps
from .api import (attachments, dashboard, entries, errors, export, meta, people, projects,
                  reports, search, settings, trash, versions)
from .services import errorlog
from .config import REPO_ROOT, get_settings
from .vault.paths import safe_join
from .vault.indexer import reindex_all

FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.ensure_dirs()
    # 지난 실행의 동작 꼬리가 이번 실행의 오류에 붙으면 맥락이 아니라 잡음이다.
    errorlog.clear_trail()
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

@app.middleware("http")
async def record_failures(request: Request, call_next):
    """실패한 요청을 파일에 남긴다 (services/errorlog.py).

    화면에는 "요청에 실패했습니다" 한 줄만 뜨고 끝이라, 나중에 원인을 물어볼 근거가
    아무것도 남지 않았다. 여기서 동작과 오류 종류만 남긴다 — 과제 내용은 담지 않는다.

    HTTPException(409·507 …)은 아래 처리기가 사유까지 함께 남기므로 여기서는 세지 않는다.
    여기 걸리는 것은 **아무도 잡지 않은 예외**, 곧 진짜 고장이다.
    """
    action = f"{request.method} {request.url.path}"
    try:
        response = await call_next(request)
    except Exception as exc:
        errorlog.record(action=action, status=500, error=type(exc).__name__, detail=str(exc))
        raise
    if response.status_code < 400:
        # 성공한 동작은 파일에 쓰지 않고 꼬리에만 남긴다 — 오류가 날 때 함께 적히는 맥락이다.
        errorlog.note(action)
    return response


@app.exception_handler(StarletteHTTPException)
async def record_http_error(request: Request, exc: StarletteHTTPException):
    """의도해서 돌려보낸 오류(파일이 열려 있음, 저장 공간 부족 …)를 사유까지 남긴다."""
    if errorlog.should_record(exc.status_code):
        errorlog.record(
            action=f"{request.method} {request.url.path}",
            status=exc.status_code,
            error="HTTPException",
            detail=str(exc.detail),
        )
    return await http_exception_handler(request, exc)


@app.exception_handler(RequestValidationError)
async def record_validation_error(request: Request, exc: RequestValidationError):
    """화면이 서버가 받지 못하는 값을 보낸 경우 — 대개 화면 쪽 결함이라 남길 값이 있다."""
    errorlog.record(
        action=f"{request.method} {request.url.path}",
        status=422,
        error="RequestValidationError",
        detail=str(exc.errors())[:500],
    )
    return await request_validation_exception_handler(request, exc)


app.include_router(meta.router)
app.include_router(dashboard.router)
app.include_router(projects.router)
app.include_router(entries.router)
app.include_router(attachments.router)
app.include_router(reports.router)
app.include_router(search.router)
app.include_router(export.router)
app.include_router(settings.router)
app.include_router(people.router)
app.include_router(trash.router)
app.include_router(errors.router)
app.include_router(versions.router)

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
