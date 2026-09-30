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


def already_running(host: str, port: int) -> str | None:
    """그 주소를 누가 쓰고 있나 (TODO 163). None — 비어 있음, "self" — 이 도구, "other" — 다른 프로그램.

    두 번 켜면 두 번째가 영어 오류(address already in use)를 내고 닫혔는데, 그 전에 **같은 데이터
    폴더로 시작 작업(색인·백업 확인)을 한 번 더** 돌았다. 켜기 전에 물어본다. 회사 PC 의 프록시
    설정이 127.0.0.1 요청을 가로채지 않도록 프록시를 끄고 묻는다.
    """
    import json
    import socket
    import urllib.request

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        if probe.connect_ex((host, port)) != 0:
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://{host}:{port}/api/meta", timeout=3) as response:
            data = json.load(response)
        return "self" if isinstance(data, dict) and "statuses" in data else "other"
    except Exception:
        return "other"


def main() -> None:
    _safe_console()
    parser = argparse.ArgumentParser(description="느린 나이테 — 과제 이력 관리 도구")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--vault", help="데이터 폴더 (기본: 이 폴더 아래 vault)")
    parser.add_argument("--no-browser", action="store_true", help="브라우저를 열지 않는다")
    args = parser.parse_args()

    # 윈도우 콘솔의 기본 인코딩(cp949)에서도 한글이 깨지지 않게 한다.
    os.environ.setdefault("PYTHONUTF8", "1")
    if args.vault:
        os.environ["MD_MGMT_VAULT"] = str(Path(args.vault).expanduser().resolve())

    check_python_version()
    check_dependencies()

    url = f"http://{args.host}:{args.port}"
    running = already_running(args.host, args.port)
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
    settings.ensure_dirs()
    print(f"\n  데이터 폴더 : {settings.vault_dir}")
    print(f"  주소        : {url}")
    print("  종료        : Ctrl+C\n")

    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    uvicorn.run("app.main:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
