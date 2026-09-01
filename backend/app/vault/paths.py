"""vault 안의 경로 계산과 안전성 검사.

이 모듈을 거치지 않고 사용자 입력으로 경로를 만들지 않는다.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

_SLUG_STRIP = re.compile(r"[^0-9A-Za-z가-힣ㄱ-ㅎㅏ-ㅣ\s_-]+")
_SLUG_SPACE = re.compile(r"[\s_]+")
_SLUG_DASH = re.compile(r"-{2,}")
MAX_SLUG_LEN = 60
MAX_FILENAME_LEN = 90  # 윈도우 260자 경로 제한을 감안한 여유값

# 윈도우에서 파일/폴더 이름으로 쓸 수 없는 예약어 (확장자가 붙어도 금지된다)
WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _windows_safe(name: str) -> str:
    """윈도우 파일시스템 규칙을 맞춘다.

    - 이름 끝의 점과 공백은 탐색기에서 잘려 나가므로 제거한다.
    - CON, NUL 같은 예약어는 뒤에 밑줄을 붙여 피한다.
    """
    name = name.rstrip(" .")
    stem = name.split(".", 1)[0]
    if stem.upper() in WINDOWS_RESERVED:
        name = f"{stem}_{name[len(stem):]}"
    return name


class FileInUseError(RuntimeError):
    """다른 프로그램이 파일을 잡고 있어 옮기지 못할 때 (윈도우에서 흔하다)."""


def move(source: Path, target: Path) -> None:
    """파일/폴더를 옮긴다.

    윈도우에서는 엑셀·뷰어가 파일을 열어 두면 이동이 실패한다.
    500으로 터뜨리지 않고 무엇을 닫아야 하는지 알려 준다.
    """
    import shutil

    try:
        shutil.move(str(source), str(target))
    except PermissionError as exc:
        raise FileInUseError(
            f"'{source.name}' 을(를) 다른 프로그램이 사용 중이라 옮길 수 없습니다. "
            "파일을 연 프로그램(엑셀·뷰어 등)을 닫고 다시 시도하세요."
        ) from exc


class InvalidDateError(ValueError):
    """날짜 형식이 올바르지 않을 때."""


def validate_date(value: object, default: str | None = None) -> str:
    """YYYY-MM-DD 만 받아들인다.

    날짜는 파일명과 폴더명에 그대로 들어가므로, 검증하지 않으면
    "../../" 같은 값이 과제 폴더 밖에 파일을 만들 수 있다.
    """
    from datetime import date as date_cls

    if value is None or value == "":
        return default or date_cls.today().isoformat()
    if isinstance(value, date_cls):
        return value.isoformat()
    text = str(value).strip()
    try:
        return date_cls.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise InvalidDateError(f"날짜는 YYYY-MM-DD 형식이어야 합니다: {text!r}") from exc


def windows_safe_filename(name: str) -> str:
    """확장자를 가진 파일명에 윈도우 규칙을 적용한다."""
    return _windows_safe(name)


def slugify(text: str) -> str:
    """한글을 보존하는 슬러그. 파일 탐색기에서 사람이 읽을 수 있어야 한다."""
    # 자모 분리 상태(NFD)로 들어온 한글을 합쳐 둔다 (맥에서 복사해 온 이름 대비).
    slug = unicodedata.normalize("NFC", text or "")
    slug = _SLUG_STRIP.sub("", slug).strip()
    slug = _SLUG_SPACE.sub("-", slug)
    slug = _SLUG_DASH.sub("-", slug).strip("-")
    if len(slug) > MAX_SLUG_LEN:
        slug = slug[:MAX_SLUG_LEN].rstrip("-")
    return _windows_safe(slug) or "untitled"


def project_dir_name(project_id: str, title: str) -> str:
    return f"{project_id}-{slugify(title)}"


def safe_join(root: Path, *parts: str) -> Path:
    """root 밖으로 나가는 경로를 거부한다 (경로 traversal 방어)."""
    root = root.resolve()
    candidate = root.joinpath(*parts).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"vault 밖의 경로입니다: {candidate}")
    return candidate


def unique_path(directory: Path, stem: str, suffix: str) -> Path:
    """같은 이름이 있으면 -2, -3 … 을 붙여 충돌을 피한다."""
    candidate = directory / f"{stem}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = directory / f"{stem}-{counter}{suffix}"
        counter += 1
    return candidate


def next_sequence_prefix(directory: Path) -> str:
    """첨부 폴더용 3자리 순번 (001-, 002- …)."""
    used = 0
    if directory.exists():
        for child in directory.iterdir():
            head = child.name.split("-", 1)[0]
            if head.isdigit():
                used = max(used, int(head))
    return f"{used + 1:03d}"
