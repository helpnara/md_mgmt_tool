"""설치 스크립트 (윈도우 / macOS / 리눅스 공통).

setup.bat 이 이 파일을 부른다. 배치 파일에는 한글을 넣지 않는다 —
윈도우 cmd 가 .bat 을 cp949 로 읽어 UTF-8 한글이 들어가면 파싱이 깨지기 때문이다.
사용자에게 보여 줄 안내는 모두 여기(파이썬)에서 출력한다.

    python setup.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
VENDOR = ROOT / "vendor"
REQUIREMENTS = ROOT / "backend" / "requirements.txt"
MIN_PYTHON = (3, 10)


def say(message: str = "") -> None:
    """콘솔 코드페이지가 못 그리는 글자가 있어도 멈추지 않게 출력한다."""
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode("ascii", "replace").decode("ascii"))


def line() -> None:
    say("=" * 52)


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def run(command: list[str]) -> int:
    return subprocess.call(command)


def main() -> int:
    line()
    say("  과제 이력 관리 도구 — 설치")
    line()
    say()

    if sys.version_info < MIN_PYTHON:
        say(f"[오류] Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} 이상이 필요합니다.")
        say(f"       지금 실행된 버전: {sys.version.split()[0]}")
        say("       https://www.python.org/downloads/ 에서 최신 버전을 설치한 뒤,")
        say('       설치 첫 화면의 "Add python.exe to PATH" 를 체크하세요.')
        return 1

    if not REQUIREMENTS.exists():
        say(f"[오류] {REQUIREMENTS} 를 찾을 수 없습니다.")
        say("       압축을 푼 폴더 안에서 실행했는지 확인하세요.")
        return 1

    updating = venv_python().exists()
    say(f"파이썬 {sys.version.split()[0]} 을(를) 사용합니다.")
    if updating:
        say("이미 설치된 환경을 찾았습니다. 패키지를 최신 상태로 맞춥니다.")
    else:
        say("가상환경(.venv)을 만듭니다...")

    if run([sys.executable, "-m", "venv", str(VENV)]) != 0:
        say()
        say("[오류] 가상환경을 만들지 못했습니다.")
        say("       바탕화면·문서 등 쓰기 권한이 있는 폴더에서 실행해 보세요.")
        return 1

    python = str(venv_python())
    installed = False

    # 사내망에서 외부 접속(PyPI)이 막혀 있어도 되도록, 동봉된 vendor 폴더를 먼저 쓴다.
    if VENDOR.is_dir():
        say()
        say("동봉된 패키지로 설치합니다 (인터넷 불필요)...")
        installed = run(
            [python, "-m", "pip", "install", "--no-index", "--find-links", str(VENDOR),
             "-r", str(REQUIREMENTS)]
        ) == 0
        if not installed:
            say()
            say("동봉 패키지로는 설치되지 않았습니다 (파이썬 버전이 다를 수 있습니다).")
            say("인터넷 설치를 시도합니다...")

    if not installed:
        say()
        say("인터넷에서 패키지를 내려받아 설치합니다...")
        run([python, "-m", "pip", "install", "--upgrade", "pip"])
        installed = run([python, "-m", "pip", "install", "-r", str(REQUIREMENTS)]) == 0

    say()
    if not installed:
        line()
        say("[오류] 패키지 설치에 실패했습니다.")
        say()
        say("  · 사내망에서 외부 접속이 막혀 있다면, vendor 폴더가 포함된 배포본을")
        say("    인터넷이 되는 PC에서 받아 옮겨 주세요.")
        say("  · 프록시를 쓰는 사내망이라면 아래처럼 지정할 수 있습니다:")
        say("      set HTTPS_PROXY=http://프록시주소:포트")
        say("      setup.bat")
        line()
        return 1

    line()
    say("  설치가 끝났습니다. run.bat 을 실행하세요.")
    if updating:
        say("  (기존 데이터는 vault 폴더에 그대로 있습니다)")
    line()
    return 0


if __name__ == "__main__":
    sys.exit(main())
