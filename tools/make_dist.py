"""배포본 ZIP 만들기.

사내 PC 는 인터넷이 막혀 있고 Node.js 도 없다. 그래서 배포본에는 두 가지가 미리 들어간다.

  · `frontend/dist`  — 빌드된 화면 (Node.js 없이 실행되도록)
  · `vendor/`        — 파이썬 패키지 wheel (PyPI 없이 설치되도록)

**`vendor/` 는 파이썬 버전을 탄다.** Pillow · pydantic-core · PyYAML · watchdog 이
버전마다 파일이 다르기 때문이다. 그래서 ZIP 이름에 대상 버전을 적는다 —
받는 사람이 `python --version` 과 맞춰 볼 수 있어야 한다.

    python tools/make_dist.py                 # 기본: 파이썬 3.14 · win_amd64
    python tools/make_dist.py --python 3.13
    python tools/make_dist.py --no-vendor     # wheel 없이 (인터넷 되는 PC 용)

담을 파일은 **git 이 추적하는 것**으로 정한다 (`git archive`). 손으로 목록을 관리하면
언젠가 빠뜨리고, vault·.venv·__pycache__ 가 딸려 들어가는 사고도 이 방식이면 없다.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "dist"
NAME = "과제이력관리"


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=ROOT, check=True, **kwargs)


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def export_tree(target: Path) -> None:
    """git 이 추적하는 파일만 꺼낸다. vault·.venv·__pycache__ 가 딸려 갈 일이 없다."""
    target.mkdir(parents=True, exist_ok=True)
    archive = target.parent / "tree.tar"
    run(["git", "archive", "--format=tar", "-o", str(archive), "HEAD"])
    shutil.unpack_archive(str(archive), str(target), format="tar")
    archive.unlink()


def fetch_wheels(target: Path, python_version: str, platform: str) -> int:
    """대상 파이썬·플랫폼용 wheel 을 모은다. 여기(빌드 PC)는 인터넷이 되어야 한다."""
    target.mkdir(parents=True, exist_ok=True)
    run([
        sys.executable, "-m", "pip", "download",
        "--dest", str(target),
        "--only-binary=:all:",
        "--platform", platform,
        "--python-version", python_version,
        "--implementation", "cp",
        "-r", str(ROOT / "backend" / "requirements.txt"),
    ], stdout=subprocess.DEVNULL)
    return len(list(target.glob("*.whl")))


def write_build_info(target: Path, python_version: str, platform: str, wheels: int) -> None:
    """무엇을 받았는지 한 장으로. 문의가 왔을 때 '어느 배포본인가'가 먼저 필요하다."""
    (target / "배포본-정보.txt").write_text(
        "\n".join([
            f"과제 이력 관리 도구 — 배포본",
            "",
            f"만든 날      {date.today().isoformat()}",
            f"소스 버전    {git('rev-parse', '--short', 'HEAD')} ({git('rev-parse', '--abbrev-ref', 'HEAD')})",
            f"대상 파이썬  {python_version} ({platform})" if wheels else "대상 파이썬  제한 없음 (vendor 미포함)",
            f"동봉 패키지  {wheels}개" if wheels else "동봉 패키지  없음 — 설치 시 인터넷이 필요합니다",
            "",
            "설치 방법",
            "  1. 이 폴더를 원하는 위치에 풀어 둔다",
            "  2. setup.bat 을 더블클릭한다",
            "  3. run.bat 을 더블클릭한다",
            "",
            "주의",
            "  · vendor 폴더는 위에 적힌 파이썬 버전 전용입니다.",
            "    명령 프롬프트에서 python --version 이 다르면 setup.bat 이",
            "    인터넷 설치로 넘어갑니다.",
            "  · 업데이트할 때는 기존 폴더 위에 덮어쓰면 됩니다.",
            "    이 배포본에는 vault 폴더가 없으므로 작성한 데이터는 그대로 남습니다.",
            "",
            "자세한 설명은 README.md 를 보세요.",
            "",
        ]),
        encoding="utf-8",
    )


def make_zip(source: Path, zip_path: Path, top: str) -> None:
    """압축을 풀면 폴더 하나가 나오게 한다 — 바탕화면에 파일이 쏟아지지 않도록."""
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, Path(top) / path.relative_to(source))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default="3.14", help="사내 PC 의 파이썬 버전 (기본 3.14)")
    parser.add_argument("--platform", default="win_amd64")
    parser.add_argument("--no-vendor", action="store_true", help="wheel 을 담지 않는다")
    args = parser.parse_args()

    if subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                      capture_output=True, text=True).stdout.strip():
        print("[주의] 커밋하지 않은 변경이 있습니다. 배포본에는 **커밋된 내용만** 담깁니다.")

    dist = (ROOT / "frontend" / "dist" / "index.html")
    if not dist.exists():
        print("[오류] frontend/dist 가 없습니다. frontend 에서 npm run build 를 먼저 하세요.")
        return 1

    stage = OUT_DIR / "_stage"
    if stage.exists():
        shutil.rmtree(stage)
    payload = stage / NAME
    export_tree(payload)

    wheels = 0
    if not args.no_vendor:
        print(f"파이썬 {args.python} ({args.platform}) 용 패키지를 모읍니다...")
        wheels = fetch_wheels(payload / "vendor", args.python, args.platform)
        print(f"  wheel {wheels}개")

    write_build_info(payload, args.python, args.platform, wheels)

    stamp = date.today().strftime("%Y%m%d")
    suffix = f"py{args.python}-win64" if wheels else "no-vendor"
    zip_path = OUT_DIR / f"{NAME}-{stamp}-{suffix}.zip"
    if zip_path.exists():
        zip_path.unlink()
    make_zip(payload, zip_path, NAME)
    shutil.rmtree(stage)

    size = zip_path.stat().st_size / 1024 / 1024
    print(f"\n만들었습니다: {zip_path.relative_to(ROOT)}  ({size:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
