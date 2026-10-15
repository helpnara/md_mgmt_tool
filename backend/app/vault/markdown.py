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


class _TolerantLoader(yaml.SafeLoader):
    """날짜처럼 생겼지만 없는 날짜(`2026-02-30`)를 **글자로** 읽는 YAML 읽개 (TODO 164).

    기본 읽개는 그런 값에서 예외를 던져 **파일 전체**를 못 읽었다 — 날짜 하나를 잘못 적으면 과제가
    목록에서 통째로 사라졌다. 글자로 받아 두면 색인이 그 값만 비우고 알린다(indexer._as_date).
    """


def _tolerant_timestamp(loader: yaml.SafeLoader, node: yaml.Node) -> Any:
    try:
        return yaml.constructor.SafeConstructor.construct_yaml_timestamp(loader, node)
    except ValueError:
        return loader.construct_scalar(node)


_TolerantLoader.add_constructor("tag:yaml.org,2002:timestamp", _tolerant_timestamp)


class _TolerantHandler(frontmatter.YAMLHandler):
    def load(self, fm: str, **kwargs: object) -> Any:
        return yaml.load(fm, Loader=_TolerantLoader)  # noqa: S506 — SafeLoader 를 이어받았다


# 메모장이 UTF-8 로 저장하면 파일 맨 앞에 붙는 바이트 순서 표식 (TODO 198).
BOM = "\ufeff"


def strip_bom(text: str) -> str:
    """맨 앞의 BOM 을 뗀다 (TODO 198). `frontmatter` 는 `\ufeff---` 를 front matter 로 보지 않아,
    BOM 하나로 과제의 머리 정보가 통째로 본문 글자가 됐다."""
    return text[1:] if text.startswith(BOM) else text


def has_front_matter(text: str) -> bool:
    """파일 글자가 front matter 로 시작하는가 (BOM 은 무시)."""
    return strip_bom(text).startswith("---")


def loads(text: str) -> MarkdownDoc:
    post = frontmatter.loads(strip_bom(text), handler=_TolerantHandler())
    metadata = post.metadata if isinstance(post.metadata, dict) else {}
    return MarkdownDoc(dict(metadata), post.content)


def load(path: Path) -> MarkdownDoc:
    return loads(path.read_text(encoding="utf-8"))


def dumps(doc: MarkdownDoc) -> str:
    body = doc.body.strip("\n")
    if not doc.meta:
        return body + "\n"
    return f"---\n{_dump_yaml(doc.meta)}\n---\n\n{body}\n"


def save(path: Path, doc: MarkdownDoc) -> None:
    """원자적 저장. 쓰다가 중단돼도 기존 파일이 깨지지 않는다.

    덮어쓰기 전에 지금 내용을 한 벌 남긴다 (versions.py). 문서를 쓰는 길이
    이 함수 하나로 모이므로, 여기에 걸어 두면 진행일지·개요·보고가 모두 지켜진다.
    """
    from . import versions
    from .paths import FileInUseError

    # TODO 198 — 머리 정보를 못 읽은 문서를 그대로 저장하면 파일의 front matter 전체가 본문 글자로
    # 밀려난다(BOM 붙은 index.md 에서 실제로 일어났다). 비어 있는 meta 로 front matter 가 있는
    # 파일을 덮어쓰려 하면 거부한다 — 파일이 진실의 원천이라 지우는 쪽이 아니라 쓰는 쪽을 막는다.
    if not doc.meta and path.is_file():
        try:
            current = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            current = ""
        if has_front_matter(current):
            raise ValueError(
                f"{path.name} 의 머리 정보(front matter)를 읽지 못해 저장하지 않았습니다 — "
                "파일 맨 앞의 BOM 또는 `---` 를 확인한 뒤 [다시 읽기]를 눌러 주세요."
            )

    text = dumps(doc)
    try:
        versions.keep(path, text)
    except Exception:
        # 안전망 때문에 본 작업이 멈추면 본말이 뒤바뀐다. keep 안에도 방어가 있지만,
        # 나중에 그 안이 바뀌더라도 저장만은 반드시 되도록 여기서 한 번 더 막는다.
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(tmp_name, path)
        except PermissionError as exc:
            # TODO 200 — 윈도우에서 다른 프로그램(엑셀 · 뷰어 · 편집기)이 md 를 잡고 있으면 덮어쓰기가
            # 거부된다. 500 이 아니라 "무엇을 닫아야 하는지" 로 — 옮기기(paths.move)와 같은 안내다.
            raise FileInUseError(
                f"'{path.name}' 을(를) 다른 프로그램이 사용 중이라 저장할 수 없습니다. "
                "파일을 연 프로그램(엑셀·뷰어·편집기 등)을 닫고 다시 시도하세요."
            ) from exc
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
