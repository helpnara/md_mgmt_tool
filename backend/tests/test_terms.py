"""사내에 맞지 않는 용어가 다시 들어오지 않게 (TODO 238 ④).

사용자: 사내 시스템에 구직 서류를 떠올리게 하는 말은 맞지 않는다 — 화면 · 도움말 · 코드 주석 · 배포본에 들어가는 문서에서 모두 뺐다.
낱말 목록은 이 파일에도 글자로 남기지 않는다(글자 번호로만 적는다 — 이 파일도 배포본에 들어간다).
바꿔 쓸 말은 "개인 업무 이력 · 성과 정리".
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
def _word(*codes: int) -> str:
    return "".join(map(chr, codes))


BANNED = [
    _word(0xC774, 0xB825, 0xC11C),  # 구직 서류 이름 하나
    _word(0xACBD, 0xB825),  # 다른 하나의 앞 두 글자 — 비슷한 말까지 걸린다
    _word(0xCEE4, 0xB9AC, 0xC5B4),  # 같은 뜻의 외래어
]
PLACES = [
    ("README.md", "*"),
    ("docs", "**/*.md"),
    ("backend/app", "**/*.py"),
    ("backend/tests", "**/*.py"),
    ("frontend/src", "**/*.ts"),
    ("frontend/src", "**/*.tsx"),
    ("frontend/src", "**/*.css"),
    ("frontend/dist", "**/*.js"),
    ("frontend/dist", "**/*.html"),
    ("tools", "**/*.py"),
    ("tests/ui", "**/*.mjs"),
]


def _files():
    for base, pattern in PLACES:
        root = REPO / base
        if root.is_file():
            yield root
            continue
        if root.is_dir():
            yield from (path for path in root.glob(pattern) if path.is_file())


def test_no_job_hunting_terms_anywhere_shipped():
    found = []
    for path in _files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if any(word in line for word in BANNED):
                found.append(f"{path.relative_to(REPO)}:{number}")
    assert not found, "사내에 맞지 않는 용어가 다시 들어왔습니다 — '업무 이력 · 성과 정리' 로 바꿔 주세요: " + ", ".join(found[:20])
