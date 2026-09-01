"""front matter가 있는 마크다운 파일 읽기/쓰기.

원칙: 파일이 진실의 원천이므로, 도구가 파일을 다시 쓸 때 사람이 손으로 넣은
키와 순서를 최대한 보존한다.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import frontmatter
import yaml


class MarkdownDoc:
    def __init__(self, meta: dict[str, Any], body: str):
        self.meta = meta
        self.body = body


def _dump_yaml(meta: dict[str, Any]) -> str:
    return yaml.safe_dump(
        meta,
        allow_unicode=True,       # 한글을 이스케이프하지 않는다
        sort_keys=False,          # 작성한 키 순서를 유지한다
        default_flow_style=False,
    ).rstrip("\n")


def loads(text: str) -> MarkdownDoc:
    post = frontmatter.loads(text)
    return MarkdownDoc(dict(post.metadata), post.content)


def load(path: Path) -> MarkdownDoc:
    return loads(path.read_text(encoding="utf-8"))


def dumps(doc: MarkdownDoc) -> str:
    body = doc.body.strip("\n")
    if not doc.meta:
        return body + "\n"
    return f"---\n{_dump_yaml(doc.meta)}\n---\n\n{body}\n"


def save(path: Path, doc: MarkdownDoc) -> None:
    """원자적 저장. 쓰다가 중단돼도 기존 파일이 깨지지 않는다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = dumps(doc)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


class ExternalChangeError(RuntimeError):
    """도구 밖에서 파일이 바뀐 뒤 덮어쓰려 할 때."""


def ensure_unchanged(path: Path, known_mtime: float | None) -> None:
    """마지막으로 읽어 둔 시각과 파일의 현재 수정 시각을 비교한다.

    옵시디언·탐색기로 같은 파일을 고쳤다면 그 내용을 말없이 덮어쓰지 않는다.
    """
    if known_mtime is None or not path.exists():
        return
    # 파일시스템마다 시각 정밀도가 달라 1초 여유를 둔다 (FAT32 등).
    if abs(path.stat().st_mtime - known_mtime) > 1.0:
        raise ExternalChangeError(
            f"{path.name} 파일이 이 도구 밖에서 수정되었습니다. "
            "[다시 읽기]로 최신 내용을 불러온 뒤 다시 저장하세요."
        )


def merge_meta(existing: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    """기존 키 순서를 유지한 채 값만 갱신하고, 새 키는 뒤에 붙인다."""
    merged = dict(existing)
    for key, value in updates.items():
        merged[key] = value
    return merged
