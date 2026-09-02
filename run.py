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


def main() -> None:
    _safe_console()
    parser = argparse.ArgumentParser(description="과제 이력 관리 도구")
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
    build_frontend_if_needed()

    sys.path.insert(0, str(ROOT / "backend"))
    import uvicorn

    from app.config import get_settings

    settings = get_settings()
    settings.ensure_dirs()
    url = f"http://{args.host}:{args.port}"
    print(f"\n  데이터 폴더 : {settings.vault_dir}")
    print(f"  주소        : {url}")
    print("  종료        : Ctrl+C\n")

    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    uvicorn.run("app.main:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
