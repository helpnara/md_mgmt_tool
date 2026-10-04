"""배포본 ZIP 만들기.

사내 PC 는 인터넷이 막혀 있고 Node.js 도 없다. 그래서 배포본에는 두 가지가 미리 들어간다.

  · `frontend/dist`  — 빌드된 화면 (Node.js 없이 실행되도록)
  · `vendor/`        — 파이썬 패키지 wheel (PyPI 없이 설치되도록)

**`vendor/` 는 파이썬 버전을 탄다.** Pillow · pydantic-core · PyYAML · watchdog 이
버전마다 파일이 다르기 때문이다. 대상 버전은 ZIP 안의 `배포본-정보.txt` 에 적어 둔다 —
받는 사람이 `python --version` 과 맞춰 볼 수 있어야 한다.

이름은 `느린나이테-20260909-v1.zip` 꼴이다. **같은 날 다시 만들면 판 번호가 오른다** —
예전에는 날짜까지만 적어서 그날의 앞 배포본을 말없이 덮었고, "어제 받은 그것" 과
"방금 받은 그것" 을 이름으로 구분할 수 없었다.

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
NAME = "느린나이테"
# 만든 배포본 이름의 기록 (TODO 186). `dist/` 는 git 이 무시하므로 새 클론 · 웹 세션의 새 컨테이너에서는 비어 있다 —
# 그것만 세면 이미 전달한 `v1` 과 같은 이름이 다시 붙는다. 이 파일은 **저장소에 커밋**되어 어디서 만들어도 번호가 이어진다.
RELEASES = ROOT / "tools" / "releases.txt"


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


def place_icon(target: Path) -> None:
    """나이테 아이콘을 배포본 맨 위에 한 장 둔다.

    `frontend/public` 안에도 같은 파일이 있지만, 바탕화면 바로가기를 손으로 만들 때
    받는 사람이 찾아 들어가야 한다. 맨 위에 있으면 [속성 → 아이콘 변경]에서 바로 고른다.
    setup.py 가 만드는 바로가기도 이 파일을 본다.
    """
    source = ROOT / "frontend" / "public" / "favicon.ico"
    if source.is_file():
        shutil.copy2(source, target / f"{NAME}.ico")


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


def released_names(releases: Path | None = None) -> list[str]:
    """기록에 적힌 배포본 이름들. `#` 로 시작하는 줄과 빈 줄은 설명이다."""
    path = releases or RELEASES
    if not path.is_file():
        return []
    return [
        line.strip() for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def used_versions(stamp: str, out_dir: Path | None = None, releases: Path | None = None) -> set[int]:
    """그날 이미 쓴 판 번호 — **이 PC 의 `dist/`** 와 **저장소의 기록**(TODO 186) 둘 다에서."""
    head = f"{NAME}-{stamp}-v"
    names = [path.stem for path in (out_dir or OUT_DIR).glob(f"{head}*.zip")]
    names += [name for name in released_names(releases) if name.startswith(head)]
    used: set[int] = set()
    for name in names:
        # `-v2` 도 `-v2-no-vendor` 도 같은 날의 판이다. 번호는 하나로 센다.
        number = name[len(head):].split("-")[0]
        if number.isdigit():
            used.add(int(number))
    return used


def next_version(stamp: str, out_dir: Path | None = None, releases: Path | None = None) -> int:
    """그날의 다음 판 번호 (`…-20260909-v3.zip` → 4).

    예전에는 이름이 날짜까지라, **같은 날 다시 만들면 앞의 것을 말없이 덮었다.**
    하루에 두세 번 고쳐 내보내는 일이 실제로 있고, 그때 "어제 받은 그것" 과
    "방금 받은 그것" 을 파일 이름으로 구분할 수 없었다.

    그다음에는 `dist/` 만 세어, 새 환경에서는 이미 전달한 번호를 다시 붙였다(TODO 186) — 기록도 함께 센다.
    """
    return max(used_versions(stamp, out_dir, releases), default=0) + 1


def record_release(name: str, releases: Path | None = None) -> None:
    """만든 배포본 이름을 기록 끝에 더한다. 커밋해야 다른 곳에서도 번호가 이어진다."""
    path = releases or RELEASES
    if name in released_names(path):
        return
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if text and not text.endswith("\n"):
        text += "\n"
    path.write_text(text + name + "\n", encoding="utf-8")


def write_build_info(
    target: Path, name: str, python_version: str, platform: str, wheels: int
) -> None:
    """무엇을 받았는지 한 장으로. 문의가 왔을 때 '어느 배포본인가'가 먼저 필요하다.

    **파이썬·플랫폼은 이름에서 빠졌으므로 여기에 남는다** — 이름은 날짜와 판 번호만
    담고(느린나이테-20260909-v1), 무엇을 위한 배포본인지는 이 파일이 말한다.
    """
    (target / "배포본-정보.txt").write_text(
        "\n".join([
            "느린 나이테 — 과제 이력 관리 도구 · 배포본",
            "",
            f"배포본 이름  {name}",
            f"만든 날      {date.today().isoformat()}",
            f"소스 버전    {git('rev-parse', '--short', 'HEAD')} ({git('rev-parse', '--abbrev-ref', 'HEAD')})",
            f"대상 파이썬  {python_version} ({platform})" if wheels else "대상 파이썬  제한 없음 (vendor 미포함)",
            f"동봉 패키지  {wheels}개" if wheels else "동봉 패키지  없음 — 설치 시 인터넷이 필요합니다",
            "",
            "설치 방법",
            "  1. 이 폴더를 원하는 위치에 풀어 둔다",
            "  2. setup.bat 을 더블클릭한다",
            "     (윈도우라면 바탕화면에 [느린 나이테] 바로가기가 생깁니다)",
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
    parser.add_argument("--version", type=int, help="판 번호를 직접 정한다 — 그날 이미 쓴 번호면 멈춘다 (TODO 186)")
    args = parser.parse_args()

    # 이름부터 정한다 — wheel 을 한참 모은 뒤에 번호가 겹친다고 멈추면 시간만 버린다
    stamp = date.today().strftime("%Y%m%d")
    used = used_versions(stamp)
    if args.version is not None:
        if args.version < 1:
            print("[오류] --version 은 1 이상이어야 합니다.")
            return 1
        if args.version in used:
            print(f"[오류] {NAME}-{stamp}-v{args.version} 은 이미 쓴 이름입니다"
                  f" (dist/ 또는 {RELEASES.relative_to(ROOT)}). 다른 번호를 고르거나 --version 을 빼세요.")
            return 1
        version = args.version
    else:
        version = max(used, default=0) + 1

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
    place_icon(payload)

    wheels = 0
    if not args.no_vendor:
        print(f"파이썬 {args.python} ({args.platform}) 용 패키지를 모읍니다...")
        wheels = fetch_wheels(payload / "vendor", args.python, args.platform)
        print(f"  wheel {wheels}개")

    write_build_info(payload, f"{NAME}-{stamp}-v{version}", args.python, args.platform, wheels)

    # vendor 없는 배포본은 이름으로 구분되어야 한다 — 받는 쪽에서 열어 보기 전에는
    # 알 수 없고, 인터넷이 안 되는 PC 에서 설치가 막힌다.
    tail = "" if wheels else "-no-vendor"
    zip_path = OUT_DIR / f"{NAME}-{stamp}-v{version}{tail}.zip"
    make_zip(payload, zip_path, NAME)
    shutil.rmtree(stage)

    record_release(f"{NAME}-{stamp}-v{version}")

    size = zip_path.stat().st_size / 1024 / 1024
    print(f"\n만들었습니다: {zip_path.relative_to(ROOT)}  ({size:.1f} MB)")
    print(f"{RELEASES.relative_to(ROOT)} 에 이름을 적었습니다 — **커밋 · 푸시**해야 다른 곳에서도 판 번호가 이어집니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
