"""경험 응답 파서 실험 도구 (TODO 256 · 지속 개선).

AI 서비스가 돌려준 **실제 응답** 을 넣으면 파서가 어떻게 읽었는지 요약한다 — 블록 수 · 못 읽은 줄 · 미분류 키 · 경고 · 규칙 12 질문.
응답 원문은 **저장하지 않는다**(실제 업무 이력이 담겨 사내 저장소에 두지 않는다 — docs/팀원이력정리/README 6절). 화면에 요약만 낸다.

    python tools/experience_probe.py 응답.md [응답2.md …]      파일
    python tools/experience_probe.py -                          붙여 넣기(Ctrl+D · 윈도우는 Ctrl+Z 엔터로 끝)
    python tools/experience_probe.py --mask 응답.md             값을 가리고 모양만(남에게 보여 줄 때)

새로운 모양을 만나면 — ① 그 모양을 **지어낸 자료**로 재현해 backend/tests/fixtures/experience/ 에 넣고
② 시험이 실패하는 것을 본 뒤 ③ 규칙을 고치고 ④ docs/팀원이력정리/실험기록.md 에 한 줄(관찰 · 고친 것)을 남긴다.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.experience.check import check  # noqa: E402
from app.experience.parse import parse  # noqa: E402


def _mask(text: str) -> str:
    return "" if not text else f"<{len(text)}자>"


def report(name: str, text: str, mask: bool = False) -> int:
    result = parse(text)
    show = _mask if mask else (lambda t: t)
    print(f"\n━━ {name} — 블록 {len(result.blocks)} · 펜스 {'있음' if result.found_fence else '없음'}"
          f" · 지운 표식 {result.stripped_markers} · 제어 문자 {result.stripped_controls} · 블록 밖 글 {result.outside_lines}줄")
    if result.notice:
        print(f"   ⚠ {result.notice}")
    if result.duplicates:
        print(f"   중복 후보 {result.duplicates}")
    issues = 0
    for b in result.blocks:
        problems = check(b, "구조화")
        filled = sum(1 for key, value in b.fields.items() if key != "형식" and value) + sum(1 for v in b.lists.values() if v)
        print(f" [{b.index}] {show(b.get('제목'))} · 채운 칸 {filled} · 정량 {len(b.quants)}"
              + (f" · 이어짐 {b.continues}" if b.continues else ""))
        for p in problems:
            issues += 1
            message = p.message if not mask else p.message.split(":")[0]
            print(f"     {'✗' if p.level == '오류' else '·'} {p.code}: {message}")
        for q in b.quants:
            print(f"     정량 {show(q.metric)} | 기준 {show(q.baseline)} → {q.baseline_kind}{' (물을 것)' if q.ask else ''}")
    return issues


def main(argv: list[str]) -> int:
    mask = "--mask" in argv
    paths = [a for a in argv if a != "--mask"] or ["-"]
    total = 0
    for path in paths:
        text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
        total += report("붙여 넣은 응답" if path == "-" else Path(path).name, text, mask)
    print(f"\n알릴 것 모두 {total}건")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
