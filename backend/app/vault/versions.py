"""이전 버전 보관 — 안쪽 안전망.

`.trash` 는 **파일을 지웠을 때**를 막아 준다. 그런데 실무에서 더 자주 나는 사고는
**내용을 잘못 고쳐 저장한 것**이다. 지금까지는 그걸 되돌릴 방법이 없었다.

그래서 문서를 덮어쓰기 **직전에 지금 내용을 한 벌 남긴다.**

    vault/.versions/projects/2026-001-소재/logs/2026-09-01-시험.md/2026-09-03_142205.md

폴더 구조를 그대로 흉내 낸 이유는, **탐색기로 열어도 무엇인지 알 수 있어야** 하기
때문이다. 이 도구의 자료는 전부 사람이 읽을 수 있는 파일이고, 안전망도 같아야 한다.
파일 하나가 통째로 복사되므로 되돌리기는 "그 파일을 도로 쓰기"일 뿐이다.

밖으로 나가는 것은 없다. 폴더 하나가 늘 뿐이다.
"""
from __future__ import annotations

import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..config import get_settings

# 파일 이름에 쓸 시각. 윈도우가 콜론을 못 쓰므로 `_` 와 숫자만 쓴다.
STAMP_FORMAT = "%Y-%m-%d_%H%M%S"
# 기본 보관 기간 (2026-09-02 사용자 확정). 설정에서 조절한다.
DEFAULT_KEEP_DAYS = 365
# 한 문서가 가질 수 있는 최대 버전 수. 같은 문서를 하루에 수십 번 고쳐도
# 폴더가 무한정 늘지 않게 한다. 넘으면 오래된 것부터 버린다.
MAX_PER_DOCUMENT = 200


def _vault_relative(path: Path) -> str | None:
    """vault 안의 문서면 상대경로를, 밖이면 None."""
    settings = get_settings()
    try:
        return path.resolve().relative_to(settings.vault_dir.resolve()).as_posix()
    except ValueError:
        return None


def _bucket(rel_path: str) -> Path:
    return get_settings().vault_dir / ".versions" / rel_path


def _meaningful(text: str) -> str:
    """`updated_at` 만 다른 두 벌은 같은 문서로 본다.

    저장할 때마다 이 값이 바뀌므로, 이것까지 따지면 **아무것도 안 고치고 저장 단추만
    눌러도** 버전이 하나 쌓인다. 되돌릴 거리가 없는 버전은 목록만 흐린다.
    """
    return "\n".join(line for line in text.splitlines() if not line.startswith("updated_at:"))


def keep(path: Path, new_text: str | None = None) -> None:
    """덮어쓰기 직전의 내용을 남긴다.

    `new_text` 를 주면 **정말로 바뀌는지 먼저 본다.** 바뀌는 것이 없으면 남기지 않는다.

    **실패해도 저장 자체를 막지 않는다.** 안전망을 만들다가 본 작업이 멈추면
    본말이 뒤바뀐다 (오류 기록과 같은 원칙).
    """
    try:
        if not path.is_file():
            return  # 새로 만드는 파일 — 남길 이전 내용이 없다
        rel = _vault_relative(path)
        # .versions 안의 파일을 또 보관하면 끝이 없다. .trash 도 이미 원본이 남아 있다.
        if rel is None or rel.startswith((".versions/", ".trash/", ".index/", ".logs/")):
            return

        current = path.read_text(encoding="utf-8")
        # 저장해도 달라지는 것이 없으면 버전을 남길 이유가 없다.
        if new_text is not None and _meaningful(current) == _meaningful(new_text):
            return

        bucket = _bucket(rel)
        bucket.mkdir(parents=True, exist_ok=True)
        existing = _stamps(bucket)
        # 직전 버전과도 같으면 남기지 않는다 (바깥에서 파일을 되돌려 놓은 경우 등).
        if existing:
            last = (bucket / f"{existing[-1]}.md").read_text(encoding="utf-8")
            if _meaningful(last) == _meaningful(current):
                return

        target = _free_name(bucket)
        target.write_text(current, encoding="utf-8")
        _prune(bucket)
    except (OSError, ValueError):
        pass


def _free_name(bucket: Path) -> Path:
    """같은 초에 여러 번 저장했을 때 덮어쓰지 않도록 뒤에 번호를 붙인다.

    번호는 시각 뒤에 오므로 이름순 정렬이 곧 시간순이다 (`…29` < `…29-2` < `…29-3`).
    """
    stamp = datetime.now().strftime(STAMP_FORMAT)
    target = bucket / f"{stamp}.md"
    counter = 2
    while target.exists():
        target = bucket / f"{stamp}-{counter}.md"
        counter += 1
    return target


def _stamps(bucket: Path) -> list[str]:
    """오래된 것부터 정렬한 버전 이름. 이름이 곧 시각이라 문자열 정렬로 충분하다."""
    if not bucket.is_dir():
        return []
    return sorted(item.stem for item in bucket.glob("*.md") if item.is_file())


def _prune(bucket: Path) -> None:
    settings = get_settings()
    keep_days = getattr(settings, "version_keep_days", DEFAULT_KEEP_DAYS)
    cutoff = (datetime.now() - timedelta(days=keep_days)).strftime(STAMP_FORMAT)
    stamps = _stamps(bucket)
    doomed = [s for s in stamps if s < cutoff]
    if len(stamps) - len(doomed) > MAX_PER_DOCUMENT:
        doomed = stamps[: len(stamps) - MAX_PER_DOCUMENT]
    for stamp in doomed:
        (bucket / f"{stamp}.md").unlink(missing_ok=True)


def _readable(stamp: str) -> str:
    """`2026-09-03_142205` → `2026-09-03 14:22:05`"""
    parts = stamp.split("-")
    try:
        when = datetime.strptime("-".join(parts[:3]), STAMP_FORMAT).isoformat(sep=" ")
    except ValueError:
        return stamp
    # 같은 초에 여러 벌이 남았으면 번호를 함께 보인다. 시각만 보이면 목록에서
    # 똑같은 줄이 여러 개로 보여 어느 것을 되돌리는지 알 수 없다.
    return f"{when} ({parts[3]})" if len(parts) > 3 else when


def list_for(rel_path: str) -> list[dict[str, Any]]:
    """한 문서의 이전 버전. **새 것부터.**"""
    bucket = _bucket(rel_path)
    items = []
    for stamp in reversed(_stamps(bucket)):
        file = bucket / f"{stamp}.md"
        try:
            items.append(
                {
                    "stamp": stamp,
                    "saved_at": _readable(stamp),
                    "size_bytes": file.stat().st_size,
                }
            )
        except OSError:
            continue
    return items


class VersionError(Exception):
    """되돌릴 수 없는 경우 — 이유를 그대로 화면에 보여 준다."""


def _version_file(rel_path: str, stamp: str) -> Path:
    # stamp 는 사용자가 보낸 값이다. 보관 폴더 밖을 가리키지 못하게 한다.
    if "/" in stamp or "\\" in stamp or stamp in ("", ".", ".."):
        raise VersionError("잘못된 버전입니다.")
    file = _bucket(rel_path) / f"{stamp}.md"
    if not file.is_file():
        raise VersionError("그 버전을 찾을 수 없습니다. 보관 기간이 지났을 수 있습니다.")
    return file


def read(rel_path: str, stamp: str) -> str:
    return _version_file(rel_path, stamp).read_text(encoding="utf-8")


def restore(conn, rel_path: str, stamp: str) -> dict[str, Any]:
    """그 버전의 내용을 원래 자리에 도로 쓴다.

    되돌리기도 **하나의 저장**이라, 지금 내용이 먼저 버전으로 남는다.
    즉 되돌린 것이 잘못이었어도 다시 되돌릴 수 있다.
    """
    from ..vault import paths
    from ..vault.indexer import index_project, reindex_all

    settings = get_settings()
    text = read(rel_path, stamp)
    target = paths.safe_join(settings.vault_dir, rel_path)
    if not target.is_file():
        raise VersionError("되돌릴 원본 문서가 없습니다. 문서가 지워졌거나 옮겨졌습니다.")

    keep(target)  # 지금 내용을 잃지 않는다
    target.write_text(text, encoding="utf-8")

    # 과제 폴더 안이면 그 과제만, 아니면 통째로 다시 읽는다.
    parts = rel_path.split("/")
    if len(parts) >= 2 and parts[0] == "projects":
        index_project(conn, settings.projects_dir / parts[1])
    else:
        reindex_all(conn)
    conn.commit()
    return {"rel_path": rel_path, "restored_from": _readable(stamp)}


def overview() -> dict[str, Any]:
    """설정 화면에 세우는 요약 — 몇 벌이 얼마나 자리를 쓰고 있나."""
    root = get_settings().vault_dir / ".versions"
    count = 0
    total = 0
    documents = 0
    if root.is_dir():
        # 보관 폴더 이름이 `…시험.md` 처럼 .md 로 끝나므로, 파일만 세도록 걸러야 한다.
        for file in root.rglob("*.md"):
            if not file.is_file():
                continue
            try:
                total += file.stat().st_size
            except OSError:
                continue
            count += 1
        documents = sum(
            1 for item in root.rglob("*")
            if item.is_dir() and any(child.is_file() for child in item.glob("*.md"))
        )
    return {
        "versions": count,
        "documents": documents,
        "total_bytes": total,
        "keep_days": getattr(get_settings(), "version_keep_days", DEFAULT_KEEP_DAYS),
    }


def forget(rel_path: str) -> int:
    """한 문서의 보관본을 모두 지운다. 되돌릴 일이 없다고 판단했을 때."""
    bucket = _bucket(rel_path)
    if not bucket.is_dir():
        return 0
    removed = len(_stamps(bucket))
    shutil.rmtree(bucket, ignore_errors=True)
    return removed
