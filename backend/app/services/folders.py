"""폴더 고르기 — 경로를 손으로 치지 않게 (TODO 97).

자동 백업 폴더는 지금까지 `D:\\백업\\과제이력` 처럼 **전체 경로를 직접 치는** 칸이었다.
오타 한 글자면 "그런 폴더가 없습니다" 가 뜨고, 공유 폴더 주소는 길어서 더 자주 틀린다.

**왜 브라우저의 폴더 선택 창을 쓰지 않는가.** 웹 페이지는 고른 폴더의 *실제 경로*를 받을
수 없다. `<input webkitdirectory>` 도 File System Access API 도 상대 이름이나 손잡이만
줄 뿐, `D:\\백업` 이라는 문자열은 끝내 주지 않는다 — 보안상 그렇게 만들어져 있다.
그래서 **서버가 폴더 목록을 주고, 화면에서 눌러 들어가는** 방식으로 만든다.
이 도구는 본인 PC에서 127.0.0.1 로만 도는 프로그램이므로, 서버가 곧 그 PC다.

내주는 것은 **폴더 이름뿐**이다. 파일은 세지도 보여 주지도 않는다.
"""
from __future__ import annotations

import os
import string
from pathlib import Path
from typing import Any

# 한 번에 돌려주는 하위 폴더 수. 윈도우 `C:\Windows\WinSxS` 처럼 수만 개짜리 폴더가 있어
# 그대로 실으면 화면이 멈춘다. 넘치면 넘쳤다고 말하고 찾기 칸으로 좁히게 한다.
LIMIT = 300


class FolderError(Exception):
    """폴더를 열 수 없는 이유 — 그대로 화면에 보여 준다."""


def _hidden(entry: os.DirEntry) -> bool:
    """숨김 폴더인가. 목록을 어지럽히기만 하는 것들을 접어 둔다."""
    if entry.name.startswith("."):
        return True
    try:
        # 윈도우의 숨김·시스템 속성 (FILE_ATTRIBUTE_HIDDEN 2 · SYSTEM 4)
        return bool(entry.stat(follow_symlinks=False).st_file_attributes & 0x6)
    except (AttributeError, OSError):
        return False


def _writable(path: Path) -> bool:
    """그 폴더에 쓸 수 있나. 백업 폴더는 쓸 수 있어야 뜻이 있다."""
    return os.access(path, os.W_OK)


def roots() -> list[dict[str, str]]:
    """처음에 세우는 자리 — 윈도우면 드라이브, 그 밖에는 최상위.

    자주 쓰는 자리(홈·바탕화면·문서)를 앞에 놓는다. 백업 폴더는 대개 다른 드라이브나
    공유 폴더지만, 처음 켠 사람에게 빈 화면을 주지 않는 편이 낫다.
    """
    found: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(label: str, path: Path) -> None:
        try:
            if not path.is_dir():
                return
        except OSError:
            return
        key = str(path)
        if key in seen:
            return
        seen.add(key)
        found.append({"name": label, "path": key})

    home = Path.home()
    add("내 폴더", home)
    for label, name in (("바탕화면", "Desktop"), ("문서", "Documents")):
        add(label, home / name)

    if os.name == "nt":
        for letter in string.ascii_uppercase:
            add(f"{letter}: 드라이브", Path(f"{letter}:\\"))
    else:
        add("/", Path("/"))
    return found


def listing(raw: str | None) -> dict[str, Any]:
    """그 폴더 아래의 **폴더들**. 비우면 처음 자리(드라이브 등)를 준다."""
    text = (raw or "").strip()
    if not text:
        return {"path": "", "parent": None, "writable": False, "folders": roots(), "truncated": False}

    path = Path(text).expanduser()
    if not path.is_absolute():
        raise FolderError("전체 경로로 적어 주세요. (예: D:\\백업)")
    if not path.exists():
        raise FolderError(f"그런 폴더가 없습니다: {path}")
    if not path.is_dir():
        raise FolderError("폴더가 아니라 파일을 가리키고 있습니다.")

    folders: list[dict[str, str]] = []
    truncated = False
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                try:
                    if not entry.is_dir(follow_symlinks=False) or _hidden(entry):
                        continue
                except OSError:
                    # 권한이 없거나 연결이 끊긴 항목 — 그것 때문에 목록 전체를 버리지 않는다.
                    continue
                if len(folders) >= LIMIT:
                    truncated = True
                    break
                folders.append({"name": entry.name, "path": str(Path(entry.path))})
    except PermissionError as exc:
        raise FolderError(f"그 폴더를 볼 권한이 없습니다: {exc.filename or path}") from exc
    except OSError as exc:
        raise FolderError(f"그 폴더를 열 수 없습니다: {exc}") from exc

    folders.sort(key=lambda item: item["name"].lower())
    # 드라이브 루트(`C:\`)의 parent 는 자기 자신이다. 그때는 처음 자리로 올려 보낸다.
    parent = str(path.parent) if path.parent != path else ""
    return {
        "path": str(path),
        "parent": parent,
        "writable": _writable(path),
        "folders": folders,
        "truncated": truncated,
    }


def create(raw_parent: str, name: str) -> str:
    """고른 자리 아래에 폴더 하나를 만든다. 탐색기를 따로 열지 않아도 되게 한다."""
    name = (name or "").strip()
    if not name:
        raise FolderError("만들 폴더 이름을 적어 주세요.")
    # 경로 구분자와 윈도우가 막는 글자를 미리 걸러 낸다 — 위로 거슬러 올라가지 못하게.
    if any(ch in name for ch in '\\/:*?"<>|') or name in {".", ".."}:
        raise FolderError('폴더 이름에 \\ / : * ? " < > | 는 쓸 수 없습니다.')

    parent = Path((raw_parent or "").strip()).expanduser()
    if not parent.is_absolute() or not parent.is_dir():
        raise FolderError("먼저 폴더를 고르고 그 아래에 만들어 주세요.")

    target = parent / name
    if target.exists():
        raise FolderError(f"이미 있는 이름입니다: {name}")
    try:
        target.mkdir()
    except OSError as exc:
        raise FolderError(f"폴더를 만들지 못했습니다: {exc}") from exc
    return str(target)
