"""지금 실행 중인 배포본이 무엇인가 (TODO 117).

`tools/make_dist.py` 가 배포본 맨 위에 `배포본-정보.txt` 를 남긴다. 그것을 읽어 화면에
보여 준다 — "덮어썼는데 새 기능이 없다" 는 문의에 가장 먼저 필요한 것이 *지금 무엇이
돌고 있는가* 다. 저장소에서 바로 실행하면 파일이 없고, 그때는 그렇다고 말한다.
"""
from __future__ import annotations

from pathlib import Path

from ..config import REPO_ROOT

INFO_FILE = "배포본-정보.txt"


def read(root: Path = REPO_ROOT) -> dict[str, str] | None:
    path = root / INFO_FILE
    if not path.is_file():
        return None
    fields: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            for key, label in (("name", "배포본 이름"), ("built", "만든 날"), ("source", "소스 버전")):
                if line.startswith(label):
                    fields[key] = line[len(label):].strip()
    except OSError:
        return None
    return fields if fields.get("name") else None
