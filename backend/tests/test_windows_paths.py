"""윈도우 파일시스템 규칙 (리눅스에서 돌려도 규칙 자체를 검증한다)."""
from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.attachments import safe_filename
from app.vault import paths


def test_forbidden_characters_are_removed():
    assert safe_filename('측정<>:"/\\|?*결과.png') == "측정결과.png"


def test_reserved_device_names_are_avoided():
    assert safe_filename("CON.txt") == "CON_.txt"
    assert safe_filename("com1.xlsx") == "com1_.xlsx"  # 대소문자 무관하게 예약어다
    assert paths.slugify("NUL") == "NUL_"
    assert safe_filename("CONTROL.txt") == "CONTROL.txt"  # 예약어로 시작할 뿐이면 그대로 둔다


def test_trailing_dots_and_spaces_are_trimmed():
    # 윈도우 탐색기는 끝의 점·공백을 잘라 버려 파일을 못 찾게 된다.
    assert safe_filename("보고서.png . ") == "보고서.png"
    assert paths.slugify("과제명 .") == "과제명"


def test_long_names_are_shortened_but_keep_extension():
    name = safe_filename("가" * 200 + ".xlsx")
    assert len(name) <= paths.MAX_FILENAME_LEN
    assert name.endswith(".xlsx")


def test_decomposed_hangul_is_normalized():
    """맥에서 복사해 온 이름(NFD)이 윈도우에서 깨져 보이지 않게 합쳐 둔다."""
    decomposed = "한글"  # '한글'의 자모 분리 형태
    assert paths.slugify(decomposed) == "한글"
    assert safe_filename(f"{decomposed}.png") == "한글.png"


def test_locked_file_gives_a_clear_message(tmp_path, monkeypatch):
    """윈도우에서 엑셀이 파일을 잡고 있으면 이동이 실패한다 — 500이 아니라 안내여야 한다."""
    import shutil

    import pytest

    source = tmp_path / "열려있는파일.xlsx"
    source.write_bytes(b"data")

    def refuse(*args, **kwargs):
        raise PermissionError(32, "The process cannot access the file")

    monkeypatch.setattr(shutil, "move", refuse)
    with pytest.raises(paths.FileInUseError) as caught:
        paths.move(source, tmp_path / "옮긴파일.xlsx")

    assert "열려있는파일.xlsx" in str(caught.value)
    assert "닫고 다시 시도" in str(caught.value)
