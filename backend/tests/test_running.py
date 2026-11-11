"""오래 걸리는 일의 진행 (TODO 268) — /api/running · 과제 내보내기를 디스크에 흘려 쓰기."""
from __future__ import annotations

import io
import zipfile

import pytest

from app.config import get_settings
from app.services import running


@pytest.fixture(autouse=True)
def _fresh():
    running.reset_for_tests()
    yield
    running.reset_for_tests()


def test_report_outside_track_is_ignored_and_inside_is_listed():
    assert running.report(1, 2) is True and running.listing() == []
    with running.track("다시 읽기", "reindex"):
        running.report(3, 10, phase="과제 읽기")
        live = running.listing("reindex")
        assert live[0]["state"] == "running" and live[0]["done"] == 3 and live[0]["total"] == 10
        assert live[0]["phase"] == "과제 읽기"
    done = running.listing("reindex")[0]
    assert done["state"] == "done" and done["eta"] is None                 # 끝난 일은 잠시 남는다
    assert running.listing("other") == []


def test_error_is_marked():
    with pytest.raises(ValueError), running.track("지금 백업", "backup-run"):
        raise ValueError("x")
    assert running.listing("backup-run")[0]["state"] == "error"


def test_reindex_endpoint_reports_projects(client):
    client.post("/api/projects", json={"title": "가"})
    client.post("/api/projects", json={"title": "나"})
    assert client.post("/api/reindex").status_code == 200
    tasks = client.get("/api/running", params={"key": "reindex"}).json()["tasks"]
    assert tasks and tasks[-1]["state"] == "done" and tasks[-1]["total"] >= 2 and tasks[-1]["phase"] == "과제 읽기"


def test_project_export_zip_streams_from_disk_and_cleans_up(client):
    project = client.post("/api/projects", json={"title": "내보낼 과제"}).json()
    client.post(f"/api/projects/{project['id']}/attachments", files={"file": ("자료.txt", b"x" * 3000, "text/plain")})
    for fmt in ("zip", "backup"):
        got = client.get(f"/api/projects/{project['id']}/export", params={"format": fmt, "job": f"j{fmt}"})
        assert got.status_code == 200 and "attachment" in got.headers["content-disposition"]
        names = zipfile.ZipFile(io.BytesIO(got.content)).namelist()
        if fmt == "backup":                                  # 원본 폴더 그대로 — 첨부까지
            assert any(n.endswith("자료.txt") for n in names)
        else:                                                # 병합 md + 본문이 가리킨 첨부
            assert any(n.endswith(".md") for n in names)
        task = client.get("/api/running", params={"key": f"j{fmt}"}).json()["tasks"][-1]
        assert task["state"] == "done"
        if fmt == "backup":
            assert task["phase"] == "zip 만들기" and task["bytes_total"] >= 3000
    assert not list((get_settings().vault_dir / ".work" / "export").glob("*"))   # 보낸 뒤 지웠다
    md = client.get(f"/api/projects/{project['id']}/export", params={"format": "md", "job": "jmd"})
    assert md.status_code == 200 and client.get("/api/running", params={"key": "jmd"}).json()["tasks"][-1]["state"] == "done"


def test_backup_run_reports_bytes(client, tmp_path):
    client.post("/api/projects", json={"title": "가"})
    target = tmp_path / "백업"
    target.mkdir()
    client.put("/api/settings", json={"backup_dir": str(target)})
    assert client.post("/api/settings/backup/run").status_code == 200
    task = client.get("/api/running", params={"key": "backup-run"}).json()["tasks"][-1]
    assert task["state"] == "done" and task["phase"] == "zip 만들기" and task["total"] > 0
