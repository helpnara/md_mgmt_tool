from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.vault import markdown as md
from app.vault import paths


def test_frontmatter_roundtrip_preserves_order_and_hangul(tmp_path):
    meta = {"id": "2026-001", "title": "리튬전지 수명평가", "tags": ["수명평가", "셀설계"]}
    path = tmp_path / "index.md"
    md.save(path, md.MarkdownDoc(meta, "## 과제 개요\n내용"))

    raw = path.read_text(encoding="utf-8")
    assert "리튬전지 수명평가" in raw  # 한글이 이스케이프되지 않는다
    assert raw.index("id:") < raw.index("title:") < raw.index("tags:")

    doc = md.load(path)
    assert doc.meta == meta
    assert doc.body.strip() == "## 과제 개요\n내용"


def test_save_is_atomic_and_leaves_no_temp_files(tmp_path):
    path = tmp_path / "a.md"
    md.save(path, md.MarkdownDoc({"title": "x"}, "body"))
    md.save(path, md.MarkdownDoc({"title": "y"}, "body2"))
    assert [p.name for p in tmp_path.iterdir()] == ["a.md"]


def test_slugify_keeps_hangul_and_drops_unsafe_characters():
    assert paths.slugify("리튬전지 수명평가") == "리튬전지-수명평가"
    assert paths.slugify("a/b:c*?") == "abc"
    assert paths.slugify("   ") == "untitled"


def test_safe_join_rejects_escape(tmp_path):
    import pytest

    paths.safe_join(tmp_path, "ok", "file.md")
    with pytest.raises(ValueError):
        paths.safe_join(tmp_path, "..", "outside.md")
