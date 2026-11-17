"""로컬 실행 스크립트 (윈도우 / macOS / 리눅스 공통).

    python run.py            # http://127.0.0.1:8000 에서 실행
    python run.py --port 9000
    python run.py --vault D:\\과제이력   # 데이터 폴더 위치 지정

윈도우에서는 run.bat 을 더블클릭해도 된다.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
DIST = FRONTEND / "dist"
REQUIREMENTS = ROOT / "backend" / "requirements.txt"


def _safe_console() -> None:
    """콘솔 코드페이지(윈도우 cp949)가 못 그리는 글자에서 멈추지 않게 한다."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def fail(message: str) -> None:
    print(f"\n[오류] {message}\n")
    sys.exit(1)


def check_python_version() -> None:
    if sys.version_info < (3, 10):
        fail(
            f"Python 3.10 이상이 필요합니다 (현재 {sys.version.split()[0]}).\n"
            "       https://www.python.org 에서 최신 버전을 설치하세요."
        )


def check_dependencies() -> None:
    missing = []
    for module, package in (("fastapi", "fastapi"), ("uvicorn", "uvicorn[standard]"),
                            ("frontmatter", "python-frontmatter"), ("PIL", "Pillow"),
                            ("multipart", "python-multipart"), ("openpyxl", "openpyxl"),
                            ("markdown_it", "markdown-it-py")):
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    if missing:
        pip = f'"{sys.executable}" -m pip install -r "{REQUIREMENTS}"'
        fail(
            "필요한 패키지가 없습니다: "
            + ", ".join(missing)
            + f"\n       아래 명령으로 설치하세요:\n\n           {pip}\n"
        )


def build_frontend_if_needed() -> None:
    if (DIST / "index.html").exists():
        return
    npm = "npm.cmd" if os.name == "nt" else "npm"
    print("프론트엔드 빌드 결과가 없어 새로 빌드합니다 (Node.js 필요)…")
    try:
        subprocess.run([npm, "install"], cwd=FRONTEND, check=True)
        subprocess.run([npm, "run", "build"], cwd=FRONTEND, check=True)
    except (OSError, subprocess.CalledProcessError):
        fail(
            "프론트엔드를 빌드하지 못했습니다.\n"
            "       Node.js가 설치되어 있지 않다면 frontend/dist 폴더가 포함된\n"
            "       저장소 버전을 받아 주세요 (빌드 결과가 함께 커밋되어 있습니다)."
        )


def already_running(host: str, port: int) -> tuple[str | None, dict | None]:
    """그 주소를 누가 쓰고 있나 (TODO 163). (None, None) — 비어 있음, ("self", 메타) — 이 도구, ("other", None) — 다른 프로그램.

    두 번 켜면 두 번째가 영어 오류(address already in use)를 내고 닫혔는데, 그 전에 **같은 데이터
    폴더로 시작 작업(색인·백업 확인)을 한 번 더** 돌았다. 켜기 전에 물어본다. 회사 PC 의 프록시
    설정이 127.0.0.1 요청을 가로채지 않도록 프록시를 끄고 묻는다.

    메타를 함께 돌려준다 (TODO 206 ㉗) — 먼저 켠 창이 공유 모드인지(`share`)를 두 번 묻지 않고 알 수 있게.
    """
    import json
    import socket
    import urllib.request

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        if probe.connect_ex((host, port)) != 0:
            return None, None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://{host}:{port}/api/meta", timeout=3) as response:
            data = json.load(response)
        if isinstance(data, dict) and "statuses" in data:
            return "self", data
        return "other", None
    except Exception:
        return "other", None


RESTART_CODE = 3   # 앱이 "다시 켜 주세요" 로 끝날 때(업데이트 · TODO 298)

# 기다림 쪽 (TODO 300 · 302) — `<meta refresh>` 는 쓰지 않는다: 이 도구의 주소는 늘 `#/…` 가 붙어 있어 브라우저가
# "같은 쪽 안 이동" 으로 보고 다시 읽지 않았다(v82 — "업데이트가 끝나도 원래 화면이 열리지 않아"). 스크립트가 2초마다
# 서버에 묻고, 진짜 서버가 답하면 `location.reload()` — 새 판이 켜지는 사이(연결 안 됨)도 쪽은 그대로 두고 계속 묻는다.
_WAIT_PAGE = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>느린 나이테 — 업데이트 중</title></head><body style="font-family:sans-serif;padding:40px;color:#333">
<h2>업데이트를 적용하고 있습니다</h2><p id="m">잠시 뒤 저절로 다시 열립니다.</p>
<noscript><p>끝나면 F5 를 눌러 다시 여세요.</p></noscript>
<script>
(function () {
  var started = Date.now();
  function tick() {
    fetch("/api/meta", { cache: "no-store" }).then(function (r) {
      if (r.ok) { location.reload(); return; }
      setTimeout(tick, 2000);
    }).catch(function () {
      document.getElementById("m").textContent = "새 판을 켜는 중입니다 — 잠시 뒤 저절로 다시 열립니다.";
      setTimeout(tick, 2000);
    });
    if (Date.now() - started > 180000) document.getElementById("m").textContent = "오래 걸립니다 — 서버 PC 의 run.bat 창을 확인하세요.";
  }
  setTimeout(tick, 2000);
})();
</script></body></html>"""


class ProgressWindow:
    """적용하는 동안 같은 주소에서 진행만 알려 주는 작은 창구 (TODO 300).

    서버가 꺼진 사이라 화면이 물어볼 곳이 없었다 — 콘솔만 보며 기다렸다. 앱을 읽지 않고(표준 라이브러리만)
    `GET /api/update/progress` 에 지금 단계를 답한다. 다른 주소는 "업데이트 중" 쪽(3초마다 새로 고침).
    자리를 못 잡으면(다른 프로그램 등) 조용히 건너뛴다 — 적용은 그대로 한다.
    """

    def __init__(self, argv: list[str], pending: dict) -> None:
        import time

        self.state = {"phase": "applying", "action": pending.get("action", "apply"), "to": pending.get("name", ""),
                      "stage": "start", "done": 0, "total": 0, "started": time.time()}
        self.server = None
        host, port = "127.0.0.1", 8000
        for index, arg in enumerate(argv):
            nxt = argv[index + 1] if index + 1 < len(argv) else ""
            if arg == "--port" and nxt.isdigit():
                port = int(nxt)
            elif arg.startswith("--port="):
                port = int(arg.split("=", 1)[1])
            elif arg == "--host" and nxt:
                host = nxt
            elif arg == "--share":
                host = "0.0.0.0"
        self.address = (host, port)

    def update(self, stage: str, done: int = 0, total: int = 0) -> None:
        self.state.update({"stage": stage, "done": done, "total": total})

    def __enter__(self) -> "ProgressWindow":
        import json
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        window = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path.split("?")[0] == "/api/update/progress":
                    body, kind, code = json.dumps(window.state, ensure_ascii=False).encode("utf-8"), "application/json", 200
                elif self.path.startswith("/api/"):
                    body, kind, code = json.dumps({"detail": "업데이트를 적용하는 중입니다 — 잠시 뒤 다시 해 주세요."},
                                                  ensure_ascii=False).encode("utf-8"), "application/json", 503
                else:
                    body, kind, code = _WAIT_PAGE.encode("utf-8"), "text/html", 503
                self.send_response(code)
                self.send_header("Content-Type", f"{kind}; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Update", "applying")       # 열려 있던 화면이 알아보고 덮개를 띄운다(TODO 302)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args) -> None:  # 콘솔을 어지럽히지 않는다
                return

        try:
            ThreadingHTTPServer.allow_reuse_address = os.name != "nt"   # 윈도우에서는 같은 자리 겹쳐 잡기를 막는다
            self.server = ThreadingHTTPServer(self.address, Handler)
            self.server.daemon_threads = True
            threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True).start()
        except OSError:
            self.server = None
        return self

    def __exit__(self, *exc) -> None:
        import time

        if self.server is None:
            return
        # 화면이 "끝" 을 한 번은 보게 잠깐 더 열어 둔 뒤 자리를 비운다(새 판 서버가 같은 자리를 잡는다)
        self.update("start")
        time.sleep(1.2)
        self.server.shutdown()
        self.server.server_close()


def supervise() -> None:
    """업데이트를 맡는 바깥 고리 (TODO 298).

    서버는 자식 프로세스로 띄운다. 서버가 "다시 켜 주세요"(코드 3)로 끝나면 — 관리자가 [이 판으로 업데이트]를 눌렀다 —
    예약된 적용을 **앱을 읽기 전에** 하고 새 파일로 다시 띄운다. 돌고 있는 서버가 자기 파일을 바꾸지 않고,
    run.bat 도 바꾸지 않는다(실행 중인 배치 파일을 바꾸면 cmd 가 엉뚱한 줄을 읽는다).
    """
    _safe_console()
    sys.path.insert(0, str(ROOT / "backend"))
    from app import updater

    argv = [a for a in sys.argv[1:] if a != "--rollback"]
    if "--rollback" in sys.argv[1:]:
        try:
            updater.request_rollback(ROOT, by="run.bat --rollback")
            print("\n  이전 판으로 되돌립니다.")
        except updater.UpdateError as exc:
            print(f"\n  [오류] {exc}\n")
    first = True
    while True:
        # 302 — 켤 때마다(그리고 업데이트 뒤 다시 켤 때마다) 업데이트 폴더 정리. 예전에는 예약이 있을 때만 불려 켤 때 정리가 돌지 않았다
        try:
            updater.tidy(ROOT, log=print)
        except Exception as exc:  # noqa: BLE001 — 정리 실패로 켜지지 않으면 안 된다
            print(f"  [알림] 업데이트 폴더를 정리하지 못했습니다 — {exc}")
        pending = updater.peek_pending(ROOT)
        result = None
        if pending:
            with ProgressWindow(argv, pending) as window:
                result = updater.apply_pending(ROOT, progress=window.update)
                if result and not result.get("ok"):
                    window.state["error"] = result.get("error", "")   # 화면에 "지금 판으로 켭니다" 와 까닭을
        if result and result.get("ok"):
            print(f"  업데이트: {result.get('from', '')} → {result.get('to', '')}")
        env = {**os.environ, "MD_MGMT_CHILD": "1"}
        args = argv if first else [*argv, "--no-browser"]
        try:
            code = subprocess.call([sys.executable, str(ROOT / "run.py"), *args], env=env)
        except KeyboardInterrupt:
            return
        if code != RESTART_CODE:
            sys.exit(code)
        first = False
        print("\n  다시 켭니다 — 업데이트를 적용합니다...\n")


def main() -> None:
    if not os.environ.get("MD_MGMT_CHILD"):
        supervise()
        return
    _safe_console()
    parser = argparse.ArgumentParser(description="느린 나이테 — 과제 이력 관리 도구")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--vault", help="데이터 폴더 (기본: 이 폴더 아래 vault)")
    parser.add_argument("--rollback", action="store_true", help="이전 판으로 되돌린다(업데이트 뒤 문제가 있을 때 — TODO 298)")
    parser.add_argument("--no-browser", action="store_true", help="브라우저를 열지 않는다")
    parser.add_argument("--share", action="store_true",
                        help="팀원이 읽기 전용으로 볼 수 있게 바깥에 연다 (이 PC 에서는 지금처럼 쓸 수 있다)")
    args = parser.parse_args()
    if args.share:
        # 바깥에 열면서 같은 순간 읽기 전용 규칙을 켠다 (TODO 191 · 192) — 둘이 따로 켜지지 않게
        args.host = "0.0.0.0"
        os.environ["MD_MGMT_SHARE"] = "1"

    # 윈도우 콘솔의 기본 인코딩(cp949)에서도 한글이 깨지지 않게 한다.
    os.environ.setdefault("PYTHONUTF8", "1")
    if args.vault:
        os.environ["MD_MGMT_VAULT"] = str(Path(args.vault).expanduser().resolve())

    check_python_version()
    check_dependencies()

    # 브라우저와 "이미 켜져 있나" 검사는 늘 127.0.0.1 로 — 0.0.0.0 은 듣는 주소지 가는 주소가 아니다
    # (윈도우에서는 0.0.0.0 으로 접속이 되지 않아 늘 "안 켜져 있다" 로 읽혔다, TODO 192)
    local = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    url = f"http://{local}:{args.port}"
    running, running_meta = already_running(local, args.port)
    if running == "self" and args.share and not (running_meta or {}).get("share"):
        # TODO 206 ㉗ — 평소 창(127.0.0.1 전용)이 켜진 채 --share 로 또 켜면 "이미 켜져 있습니다" 로 끝나,
        # 공유가 안 켜졌는데 켜진 줄 알았다. 먼저 켠 창이 공유 모드가 아니면 그렇다고 말하고 멈춘다.
        print("\n  [오류] 이미 켜져 있지만 공유 모드가 아닙니다 — 먼저 켠 창을 닫고 run.bat --share 로 다시 켜세요.\n")
        sys.exit(1)
    if running == "self":
        print(f"\n  이미 켜져 있습니다 — 브라우저만 엽니다: {url}")
        print("  (먼저 켠 창을 닫으면 도구가 꺼집니다)\n")
        if not args.no_browser:
            webbrowser.open(url)
        return
    if running == "other":
        print(f"\n  [오류] {args.port}번 자리를 다른 프로그램이 쓰고 있습니다.")
        print(f"  다른 번호로 켜 보세요:  run.bat --port {args.port + 1}\n")
        sys.exit(1)

    build_frontend_if_needed()

    sys.path.insert(0, str(ROOT / "backend"))
    import uvicorn

    from app.config import get_settings

    settings = get_settings()
    try:
        settings.ensure_dirs()
    except OSError as exc:
        # TODO 206 ㉝ — `--vault E:\…` 의 USB 가 빠져 있으면 영어 traceback 만 났다. 어느 경로인지 한글로.
        # config.ensure_dirs 가 경로와 까닭을 한글로 적어 보낸다. 없으면 여기서 경로만이라도.
        fail(
            f"{exc.strerror or f'데이터 폴더를 만들거나 쓸 수 없습니다: {exc.filename or settings.vault_dir}'}\n"
            "       다른 폴더를 쓰려면:  run.bat --vault <폴더>"
        )
    print(f"\n  데이터 폴더 : {settings.vault_dir}")
    print(f"  주소        : {url}")
    if args.share:
        import socket

        print(f"  공유 주소   : http://{socket.gethostname()}:{args.port}  (팀원은 읽기만 — 이 PC 에서는 그대로 쓸 수 있습니다)")
        print("               처음 켤 때 윈도우 방화벽이 물으면 [허용] 을 누르세요.")
    print("  종료        : Ctrl+C\n")

    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    uvicorn.run("app.main:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
