"""지금 실행 중인 배포본 알리기 (TODO 117)."""
from __future__ import annotations

from app.services import buildinfo


def test_reads_the_fields_make_dist_writes(tmp_path):
    (tmp_path / buildinfo.INFO_FILE).write_text(
        "과제 이력 관리 도구 — 배포본\n\n배포본 이름  과제이력관리-20260915-v3\n만든 날      2026-09-15\n"
        "소스 버전    4bf39b1 (claude/x)\n대상 파이썬  3.14 (win_amd64)\n",
        encoding="utf-8",
    )
    info = buildinfo.read(tmp_path)
    assert info == {"name": "과제이력관리-20260915-v3", "built": "2026-09-15", "source": "4bf39b1 (claude/x)"}


def test_missing_file_means_running_from_source(tmp_path):
    assert buildinfo.read(tmp_path) is None
    (tmp_path / buildinfo.INFO_FILE).write_text("이름 없는 파일", encoding="utf-8")
    assert buildinfo.read(tmp_path) is None


def test_meta_carries_build(client):
    meta = client.get("/api/meta").json()
    assert "build" in meta  # 시험은 저장소에서 돌므로 None


def test_index_html_is_not_cached(client):
    response = client.get("/")
    if response.headers.get("content-type", "").startswith("text/html"):
        assert "no-cache" in response.headers.get("cache-control", "")
