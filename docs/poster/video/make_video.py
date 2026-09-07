"""AX 성과공유회 소개 영상 만들기 (약 1분 30초, 소리 없음).

**만드는 방법** — 자막 카드와 실제 화면 녹화를 번갈아 잇는다.

  카드(정지) → 화면(녹화) → 카드 → 화면 …

화면은 **진짜로 도구를 움직여 찍은 것**이다(Playwright 녹화). 그림을 이어 붙인
슬라이드가 아니라 실제 동작이라, "된다"는 말을 따로 하지 않아도 된다.

소리는 넣지 않는다. 발표장에서 말로 설명하거나 자막만으로 보게 하는 편이 낫고,
사내 배포에서 음성 파일이 끼면 검토가 한 단계 늘어난다.

    python docs/poster/video/make_video.py                 # 1920x1200 (16:10)
    python docs/poster/video/make_video.py --ratio 16:9    # 1920x1080

준비물: ffmpeg, node + playwright, 그리고 데모 자료가 들어 있는 서버.
녹화 파일(clips/*.webm)이 이미 있으면 --skip-record 로 자막만 다시 만든다.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLIPS = HERE / "clips"
BUILD = HERE / "_build"
CHROMIUM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

RATIOS = {"16:10": (1920, 1200), "16:9": (1920, 1080)}

# (카드 머리말, 제목, 설명, 이어 붙일 녹화 파일, 카드가 머무는 초)
SCENES = [
    ("2026 사내 AX 성과공유회",
     "개발을 <span class='accent'>기다리지</span> 않았다",
     "개발 리소스 없이 <b>엿새</b> 만에 만든 팀 과제관리 · 보고지원 시스템",
     None, 3.6),
    ("무엇이 문제였나",
     "과제는 흩어지고<br>보고는 <span class='accent'>기억에</span> 기댔다",
     "메모 · 메일 · 엑셀에 나뉜 이력, 매주 <b>무엇을 보고할지</b> 판단할 근거가 없었습니다",
     None, 4.2),
    ("① 한 화면에서 보는 팀 현황",
     "올해 우리 팀이<br>무엇을 했는가",
     "연도별 현황과 <b>팀원별 성과</b>를 한 화면에서 봅니다. 모든 숫자는 눌러서 그 목록으로 이어집니다",
     "01-home.webm", 3.4),
    ("② 데이터로 고르는 보고 대상",
     "이번 주에<br>무엇을 보고할까",
     "마지막 보고 후 <b>경과일</b>과 <b>미보고 분량</b>으로 순서를 매겨 후보를 세웁니다",
     "02-candidates.webm", 3.4),
    ("③ 보고 초안 자동 생성",
     "지난 보고 이후만<br>모아서 초안으로",
     "단추 하나로 초안이 만들어지고, 확정하면 그 시점 문서가 <b>스냅샷으로 고정</b>됩니다",
     "03-draft.webm", 3.4),
    ("④ 남는 것은 사실",
     "언제 무엇을<br>보고했는가",
     "과제 × 월 표로 한 해 보고 이력을 봅니다. 칸을 누르면 그때 보고한 문서가 그대로 열립니다",
     "04-history.webm", 3.4),
    ("⑤ 사람도 함께",
     "팀원 역량 이력",
     "교육 · 세미나 참여를 <b>사람 기준</b>으로 쌓아 면담 자료로 씁니다",
     "05-skills.webm", 3.2),
    ("얼마나 아꼈나",
     "외주 <span class='accent'>2.3억</span> → 실제 <span class='good'>313만 원</span>",
     "363 기능점수 · 약 19 M/M 추정. 실제는 <b>1명이 엿새, 약 1/74</b>",
     None, 4.4),
    ("무엇이 남았나",
     "만들 사람이<br>매일 쓸 사람이면",
     "<b>요구정의도, 검수도, 재작업도 없습니다</b><br>선강DX개발팀 · 권경락",
     None, 4.6),
]


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True)


def render_cards(width: int, height: int) -> list[Path]:
    """자막 카드를 PNG 로 굽는다. 브라우저로 찍어 포스터·썸네일과 글꼴이 같다."""
    template = (HERE / "card.html").read_text(encoding="utf-8")
    pages, paths = [], []
    for index, (step, title, body, _, _) in enumerate(SCENES):
        html = (
            template.replace("__STEP__", step).replace("__TITLE__", title).replace("__BODY__", body)
            .replace("width: 1920px; height: 1200px", f"width: {width}px; height: {height}px")
        )
        source = BUILD / f"card{index:02d}.html"
        source.write_text(html, encoding="utf-8")
        out = BUILD / f"card{index:02d}.png"
        pages.append((source, out))
        paths.append(out)

    script = BUILD / "_cards.mjs"
    shots = "\n".join(
        f'  await page.goto("file://{src}", {{ waitUntil: "networkidle" }});\n'
        f'  await page.screenshot({{ path: "{dst}" }});'
        for src, dst in pages
    )
    script.write_text(
        'import { createRequire } from "node:module";\n'
        "const require = createRequire(import.meta.url);\n"
        'let pw; for (const n of ["playwright", "/opt/node22/lib/node_modules/playwright"]) '
        "{ try { pw = require(n); break; } catch {} }\n"
        f'const browser = await pw.chromium.launch({{ executablePath: "{CHROMIUM}" }});\n'
        f"const page = await browser.newPage({{ viewport: {{ width: {width}, height: {height} }} }});\n"
        f"{shots}\n"
        "await browser.close();\n",
        encoding="utf-8",
    )
    run(["node", str(script)])
    return paths


def build(width: int, height: int, out: Path) -> None:
    """카드(정지)와 화면(녹화)을 번갈아 이어 붙인다."""
    parts: list[Path] = []
    for index, (_, _, _, clip, seconds) in enumerate(SCENES):
        card = BUILD / f"card{index:02d}.png"
        piece = BUILD / f"part{index:02d}a.mp4"
        # 카드는 정지 화면이다. 앞뒤로 짧게 페이드만 준다 —
        # zoompan 으로 천천히 확대해 봤더니 `-loop 1` 입력마다 d 프레임을 뱉어
        # 3.6초짜리가 37MB 로 부풀었다. 움직임의 값어치보다 비용이 크다.
        fade = 0.4
        run([
            "ffmpeg", "-y", "-loop", "1", "-t", str(seconds), "-i", str(card),
            "-vf", (
                f"fade=t=in:st=0:d={fade},"
                f"fade=t=out:st={seconds - fade:.2f}:d={fade},"
                "format=yuv420p"
            ),
            "-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "22",
            "-tune", "stillimage", str(piece),
        ])
        parts.append(piece)

        if clip:
            piece = BUILD / f"part{index:02d}b.mp4"
            # 녹화는 1440x900 이다. 화면 비율을 지킨 채 가운데 두고 남는 자리는 배경색으로.
            run([
                "ffmpeg", "-y", "-i", str(CLIPS / clip),
                "-vf", (
                    f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                    f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x0f2a47,"
                    "format=yuv420p"
                ),
                "-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-an", str(piece),
            ])
            parts.append(piece)

    listing = BUILD / "parts.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in parts), encoding="utf-8")
    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(out),
    ])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ratio", choices=sorted(RATIOS), default="16:10")
    args = parser.parse_args()

    if not CLIPS.exists() or not any(CLIPS.glob("*.webm")):
        print("[오류] clips/*.webm 이 없습니다. record.mjs 로 화면을 먼저 녹화하세요.")
        return 1

    width, height = RATIOS[args.ratio]
    BUILD.mkdir(parents=True, exist_ok=True)
    print(f"자막 카드를 굽습니다 ({width}x{height})...")
    render_cards(width, height)

    out = HERE / f"AX성과공유회_소개영상_{args.ratio.replace(':', '-')}.mp4"
    print("이어 붙입니다...")
    build(width, height, out)

    length = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(out)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    size = out.stat().st_size / 1024 / 1024
    print(f"\n만들었습니다: {out.name}  ({width}x{height}, {float(length):.0f}초, {size:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
