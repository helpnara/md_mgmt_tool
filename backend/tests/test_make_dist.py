"""배포본 판 번호 (TODO 186).

`dist/` 는 git 이 무시한다. 새로 클론한 곳 · 웹 세션의 새 컨테이너에서는 비어 있어, 그것만 세면 이미 전달한
`v1` 과 같은 이름이 다시 붙었다(2026-10-01 세션을 이어받을 때 실제로 그럴 뻔했다). 저장소의 기록도 함께 센다.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def make_dist():
    spec = importlib.util.spec_from_file_location("make_dist_under_test", ROOT / "tools" / "make_dist.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path: Path, *names: str) -> Path:
    path.write_text("# 설명 줄\n" + "".join(f"{name}\n" for name in names), encoding="utf-8")
    return path


def test_a_fresh_clone_continues_from_the_record(make_dist, tmp_path):
    """빈 dist/ — 예전에는 v1 이 붙었다. 기록에 v2 까지 있으면 v3."""
    out = tmp_path / "dist"
    out.mkdir()
    releases = write(tmp_path / "releases.txt", "느린나이테-20261002-v1", "느린나이테-20261002-v2")
    assert make_dist.next_version("20261002", out, releases) == 3
    # 다른 날의 기록은 세지 않는다
    assert make_dist.next_version("20261004", out, releases) == 1


def test_local_zips_still_count(make_dist, tmp_path):
    """기록에 아직 안 적힌(커밋 전) 로컬 ZIP 도 센다. `-no-vendor` 도 같은 날의 판."""
    out = tmp_path / "dist"
    out.mkdir()
    (out / "느린나이테-20261004-v1.zip").write_bytes(b"")
    (out / "느린나이테-20261004-v3-no-vendor.zip").write_bytes(b"")
    releases = write(tmp_path / "releases.txt", "느린나이테-20261004-v2")
    assert make_dist.used_versions("20261004", out, releases) == {1, 2, 3}
    assert make_dist.next_version("20261004", out, releases) == 4


def test_recording_adds_once(make_dist, tmp_path):
    releases = tmp_path / "releases.txt"
    make_dist.record_release("느린나이테-20261004-v1", releases)  # 파일이 없어도 만든다
    make_dist.record_release("느린나이테-20261004-v1", releases)
    make_dist.record_release("느린나이테-20261004-v2", releases)
    assert make_dist.released_names(releases) == ["느린나이테-20261004-v1", "느린나이테-20261004-v2"]


def test_a_chosen_version_that_is_taken_stops_before_any_work(make_dist, tmp_path, monkeypatch, capsys):
    """--version 이 겹치면 wheel 을 모으기 전에 멈춘다. 아무것도 만들지 않는다."""
    out = tmp_path / "dist"
    out.mkdir()
    releases = write(tmp_path / "releases.txt", "느린나이테-20261004-v1")
    monkeypatch.setattr(make_dist, "OUT_DIR", out)
    monkeypatch.setattr(make_dist, "RELEASES", releases)
    monkeypatch.setattr(make_dist, "ROOT", tmp_path)
    monkeypatch.setattr(make_dist, "date", type("D", (), {"today": staticmethod(lambda: date(2026, 10, 4))}))
    called = []
    monkeypatch.setattr(make_dist, "export_tree", lambda *a: called.append("export"))
    monkeypatch.setattr(sys, "argv", ["make_dist.py", "--version", "1"])
    assert make_dist.main() == 1
    assert "이미 쓴 이름" in capsys.readouterr().out
    assert called == [] and list(out.iterdir()) == []


def test_the_repository_record_knows_what_was_delivered(make_dist, tmp_path):
    """저장소의 기록 — 2026-10-02 에는 v2 까지 전달했다. 빈 dist/ 에서도 다음은 v3."""
    empty = tmp_path / "dist"
    empty.mkdir()
    assert make_dist.next_version("20261002", empty) == 3
    assert make_dist.next_version("20261001", empty) == 9
