from __future__ import annotations

import asyncio
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
import anyio
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import deps
from .api import (activities, attachments, dashboard, drafts, entries, errors, export, folders, home, intakes,
                  linkfix, meetings, meta, people, projects, reports, roadmap, search, settings, trash,
                  versions)
from . import readcache, share
from .services import errorlog
from .config import REPO_ROOT, get_settings
from .vault.paths import safe_join
from .vault.indexer import reindex_all

FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
THREAD_POOL_SIZE = 64


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
    readcache.bump()
    if problems:
        print(f"\n  [주의] 읽지 못한 파일 {len(problems)}건 — front matter를 확인하세요:")
        for item in problems[:10]:
            print(f"    - {item.rel_path}: {item.reason}")
    print(f"  과제 {indexed}건을 읽었습니다.")

    # 자동 백업은 프로그램이 켜져 있는 동안에만 돈다. 사내 PC 에 상주 서비스를 두는 것보다
    # 이 편이 단순하고, 이 도구는 쓸 때 켜 두는 물건이다.
    # 동기 끝점은 스레드 풀에서 돈다. 기본 40 이면 열 명이 홈을 동시에 열 때 뒤의 가벼운 요청(메타 · 상세 · 검색)이
    # 줄을 선다 (TODO 190 실측). 넉넉히 둔다 — SQLite 읽기는 서로 막지 않는다.
    anyio.to_thread.current_default_thread_limiter().total_tokens = THREAD_POOL_SIZE
    backup_task = asyncio.create_task(_backup_loop())
    try:
        yield
    finally:
        backup_task.cancel()
        deps.teardown()


# 백업할 때가 됐는지 들여다보는 주기. 주기 자체(기본 24시간)는 설정에서 정한다.
BACKUP_CHECK_SECONDS = 30 * 60


async def _backup_loop() -> None:
    """때가 되면 백업한다. **실패해도 프로그램에 영향을 주지 않는다.**

    커넥션은 그때그때 제 것을 연다 — 요청이 쓰는 커넥션과 나눠 쓰면 서로의
    중간 상태를 보게 된다 (deps.py 주석 참고).
    """
    from .db import connect
    from .services import backup as backup_service

    def once():
        conn = connect()
        try:
            return backup_service.maybe_run(conn)
        finally:
            conn.close()

    while True:
        try:
            # 켜자마자 백업하면 기동이 느려진다. 조금 두고 본다.
            await asyncio.sleep(20)
            result = await asyncio.to_thread(once)
            if result:
                print(f"  백업을 남겼습니다: {result['file']}")
            await asyncio.sleep(BACKUP_CHECK_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception:
            # 백업이 프로그램을 멈추게 하면 본말이 뒤바뀐다.
            await asyncio.sleep(BACKUP_CHECK_SECONDS)


app = FastAPI(title="느린 나이테 — 과제 이력 관리 도구", version="0.1.0", lifespan=lifespan)

# 로컬 개발 시 Vite 개발 서버(5173)에서 API를 호출할 수 있게 한다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_inflight: dict[tuple, asyncio.Event] = {}


@app.middleware("http")
async def shared_reads(request: Request, call_next):
    """무거운 읽기의 답을 잠깐 나눠 쓴다 (TODO 190, `readcache.py`). 쓰기가 끝나면 판을 올려 전부 버린다."""
    path = request.url.path
    if request.method not in share.SAFE_METHODS:
        response = await call_next(request)
        if response.status_code < 400:
            readcache.bump()
        return response
    if request.method != "GET" or not readcache.cacheable(path) or "if-none-match" in request.headers:
        return await call_next(request)
    key = (path, request.url.query, bool(share.is_remote(request)))
    hit = readcache.get(key)
    if hit is not None:
        status, body, headers = hit
        return Response(content=body, status_code=status, headers=headers)
    # 같은 답을 동시에 계산하지 않는다 — 열 명이 같은 순간 홈을 열면 첫 사람이 계산하는 동안 아홉은 기다렸다가 그 답을 받는다.
    # (답 나눠 쓰기만으로는 **같은 순간**에 온 요청이 모두 계산했다 — 10명 p95 가 그대로 3초였다.)
    waiting = _inflight.get(key)
    if waiting is not None:
        await waiting.wait()
        hit = readcache.get(key)
        if hit is not None:
            status, body, headers = hit
            return Response(content=body, status_code=status, headers=headers)
    done = asyncio.Event()
    _inflight[key] = done
    try:
        ver = readcache.version()
        response = await call_next(request)
        if response.status_code != 200:
            return response
        chunks = [chunk async for chunk in response.body_iterator]
        body = b"".join(chunks)
        headers = {k: v for k, v in response.headers.items() if k.lower() in ("content-type", "etag")}
        readcache.put(key, ver, response.status_code, body, headers)
        return Response(content=body, status_code=response.status_code, headers=headers)
    finally:
        _inflight.pop(key, None)
        done.set()


@app.middleware("http")
async def readonly_share(request: Request, call_next):
    """읽기 전용 공유 (TODO 191). 바깥에서 온 요청은 읽기만 — 규칙은 `share.py`, 지키는 곳은 여기 하나."""
    remote = share.is_remote(request)
    request.state.readonly = remote
    if not remote:
        return await call_next(request)
    path = request.url.path
    if request.method not in share.SAFE_METHODS or share.blocked_path(path):
        response = JSONResponse({"detail": share.READONLY_DETAIL}, status_code=403)
    elif path in share.EMPTY_RESPONSES:
        response = JSONResponse(share.EMPTY_RESPONSES[path])
    else:
        response = await call_next(request)
    share.record_access(request.client.host if request.client else "?", request.method, path, response.status_code)
    return response


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
    # 받은 값(`input`)을 그대로 돌려주면 NaN · 무한대 같은 값은 JSON 으로 못 적어 **500 이 났다**
    # (TODO 167). 화면에 필요한 것은 어느 칸이 왜 틀렸는가뿐이다.
    return JSONResponse(
        status_code=422,
        content={
            "detail": [
                {"loc": [str(part) for part in error.get("loc", ())], "msg": str(error.get("msg", "")),
                 "type": str(error.get("type", ""))}
                for error in exc.errors()
            ]
        },
    )


app.include_router(meta.router)
app.include_router(dashboard.router)
app.include_router(home.router)
app.include_router(activities.router)
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
app.include_router(folders.router)
app.include_router(linkfix.router)
# 과제 접수 풀 (TODO 136) — /intake-files 도 여기 있으므로 SPA 되돌림보다 먼저 선다
app.include_router(intakes.router)
app.include_router(drafts.router)
# 다년도 과제 로드맵 (TODO 174)
app.include_router(roadmap.router)
# 팀원 면담 (TODO 182)
app.include_router(meetings.router)

if FRONTEND_DIST.exists():
    @app.get("/assets/{name}")
    def asset(name: str, request: Request):
        """화면 묶음(JS · CSS). 이름에 해시가 있어 **1년 캐시**해도 안전하고, 빌드가 `.gz` 를 함께 내므로 브라우저가 받으면
        그것을 그대로 보낸다 — 574KB 가 184KB 로, 요청마다 압축하는 CPU 없이 (TODO 190). 100명이 같은 순간 첫 화면을 열 때의 값이다."""
        try:
            path = safe_join(FRONTEND_DIST / "assets", name)
        except ValueError:
            path = None
        if path is None or not path.is_file():
            raise StarletteHTTPException(status_code=404)
        headers = {"Cache-Control": "public, max-age=31536000, immutable", "Vary": "Accept-Encoding"}
        media_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        gz = path.with_name(path.name + ".gz")
        if gz.is_file() and "gzip" in request.headers.get("accept-encoding", ""):
            headers["Content-Encoding"] = "gzip"
            return FileResponse(gz, media_type=media_type, headers=headers)
        return FileResponse(path, media_type=media_type, headers=headers)

    @app.get("/{full_path:path}")
    def spa(full_path: str) -> FileResponse:
        # 빌드 결과 밖을 가리키는 경로는 무시하고 SPA 진입점을 돌려준다.
        try:
            candidate = safe_join(FRONTEND_DIST, full_path) if full_path else None
        except ValueError:
            candidate = None
        if candidate is not None and candidate.is_file():
            return FileResponse(candidate)
        # 진입점은 캐시하지 않는다 (TODO 117). 새 배포본을 덮어써도 브라우저가 옛 index.html 을
        # 들고 있으면 옛 묶음(assets/index-<해시>.js)을 계속 부른다 — "새 기능이 안 보인다".
        # 묶음 파일은 이름에 해시가 있어 캐시해도 안전하다. 진입점만 매번 확인하게 한다.
        return FileResponse(FRONTEND_DIST / "index.html", headers={"Cache-Control": "no-cache"})
