"""AX 성과공유회 썸네일 만들기 (16:10).

포스터가 A1 세로라면 이쪽은 **목록·슬라이드에 걸리는 표지**다. 요구는 하나 —
작게 줄여도 제목과 핵심 수치가 읽혀야 한다. 그래서 담는 것을 넷으로 묶었다:
① 자리 ② 제목 ③ 한 줄 설명 ④ 수치 네 칸.

HTML 을 브라우저로 갈무리한다. 파워포인트 도형으로 짜는 것보다 여백·자간을 잡기 쉽고,
색과 글꼴이 포스터(make_poster.py)와 같은 값을 쓴다.

    python docs/poster/make_thumbnail.py            # 2560x1600 (@2x)
    python docs/poster/make_thumbnail.py --scale 1  # 1280x800
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "thumbnail.html"
# 16:10. 1280x800 을 기본 도화지로 두고 배율만 올린다 — 글자 크기를 다시 잡지 않아도 된다.
WIDTH, HEIGHT = 1280, 800
CHROMIUM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

SHOT = """
import {{ createRequire }} from "node:module";
const require = createRequire(import.meta.url);
let pw;
for (const name of ["playwright", "/opt/node22/lib/node_modules/playwright"]) {{
  try {{ pw = require(name); break; }} catch {{ /* 다음 후보 */ }}
}}
const browser = await pw.chromium.launch({{ executablePath: "{chromium}" }});
const page = await browser.newPage({{
  viewport: {{ width: {w}, height: {h} }},
  deviceScaleFactor: {scale},
}});
await page.goto("file://{source}", {{ waitUntil: "networkidle" }});
await page.waitForTimeout(400);
await page.screenshot({{ path: "{out}" }});
await browser.close();
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", type=int, default=2, help="화소 배율 (기본 2 = 2560x1600)")
    args = parser.parse_args()

    out = HERE / "AX성과공유회_썸네일_16-10.png"
    script = HERE / "_shot.mjs"
    script.write_text(
        SHOT.format(
            chromium=CHROMIUM, w=WIDTH, h=HEIGHT, scale=args.scale, source=SOURCE, out=out
        ),
        encoding="utf-8",
    )
    try:
        subprocess.run(["node", str(script)], check=True)
    finally:
        script.unlink(missing_ok=True)

    size = out.stat().st_size / 1024
    print(f"만들었습니다: {out.name}  ({WIDTH * args.scale}x{HEIGHT * args.scale}, {size:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
