"""전체 백업 진행 표시(TODO 266) · 작업 파일 자리와 남은 자리(TODO 267).

267 — 데이터를 네트워크 드라이브에 두어도 큰 작업 파일을 서버 PC 의 %TEMP%(C:)에 써서 "No space left on device" 가 났다.
"""
from __future__ import annotations

import io
import time
import zipfile

import pytest

from app.config import get_settings
from app.services import backup_jobs, export, workspace


@pytest.fixture(autouse=True)
def _fresh_jobs():
    backup_jobs.reset_for_tests()
    yield
    backup_jobs.reset_for_tests()


def _wait(client, job_id, until=("done", "error", "cancelled"), seconds=10.0):
    end = time.time() + seconds
    while time.time() < end:
        state = client.get(f"/api/backup/jobs/{job_id}").json()
        if state["state"] in until:
            return state
        time.sleep(0.05)
    raise AssertionError("백업 작업이 끝나지 않았다")


def _seed(client):
    project = client.post("/api/projects", json={"title": "백업 시험 과제"}).json()
    client.post(f"/api/projects/{project['id']}/attachments", files={"file": ("자료.txt", b"x" * 5000, "text/plain")})
    return project


# ── 266 — 뒤에서 만들고 진행을 보인다 ─────────────────────────────────────────
def test_estimate_and_job_roundtrip(client):
    _seed(client)
    full, docs = client.get("/api/backup/estimate").json(), client.get("/api/backup/estimate", params={"assets": "none"}).json()
    assert full["files"] > docs["files"] and full["assets_bytes"] >= 5000 and docs["assets_bytes"] == 0
    assert full["work_dir"].endswith(".work")
    job = client.post("/api/backup/jobs", json={"assets": True}).json()
    assert job["state"] == "running" and job["files_total"] == full["files"]
    done = _wait(client, job["id"])
    assert done["state"] == "done" and done["files_done"] == done["files_total"] and done["size"] > 0
    assert client.get("/api/backup/jobs/current").json()["job"]["id"] == job["id"]       # 다른 화면에 갔다 와도
    got = client.get(f"/api/backup/jobs/{job['id']}/file")
    assert got.status_code == 200 and "attachment" in got.headers["content-disposition"]
    names = zipfile.ZipFile(io.BytesIO(got.content)).namelist()
    assert any(n.startswith("projects/") for n in names) and not any(n.startswith(".work/") for n in names)
    assert client.get(f"/api/backup/jobs/{job['id']}").status_code == 404              # 받은 뒤 지운다
    assert not list((get_settings().vault_dir / ".work" / "backup").glob("*.zip"))


def _slow(monkeypatch):
    real = export.write_backup_all

    def slow(destination, assets=True, progress=None):
        def step(*args):
            time.sleep(0.05)
            return progress(*args) if progress else True
        for i in range(200):
            if step(i + 1, 200, i + 1, 200) is False:
                raise export.BackupCancelled()
        return real(destination, assets)

    monkeypatch.setattr(export, "write_backup_all", slow)


def test_one_job_at_a_time_and_cancel(client, monkeypatch):
    _seed(client)
    _slow(monkeypatch)
    first = client.post("/api/backup/jobs", json={"assets": True}).json()
    again = client.post("/api/backup/jobs", json={"assets": False}).json()
    assert again["id"] == first["id"]                                                     # 한 번에 하나
    time.sleep(0.2)
    mid = client.get(f"/api/backup/jobs/{first['id']}").json()
    assert 0 < mid["files_done"] < mid["files_total"] and mid["eta"] is not None
    client.post(f"/api/backup/jobs/{first['id']}/cancel")
    assert _wait(client, first["id"])["state"] == "cancelled"
    assert not list((get_settings().vault_dir / ".work" / "backup").glob("*"))           # 만들던 파일도 지운다
    assert client.get(f"/api/backup/jobs/{first['id']}/file").status_code == 404


# ── 267 — 작업 파일 자리 · 남은 자리 ───────────────────────────────────────────
def test_low_space_is_507_with_place_and_sizes(client, monkeypatch):
    _seed(client)
    monkeypatch.setattr(workspace, "free_bytes", lambda folder: 1024)
    started = client.post("/api/backup/jobs", json={"assets": True})
    assert started.status_code == 507 and ".work" in started.json()["detail"] and "남은 자리" in started.json()["detail"]
    legacy = client.get("/api/backup")
    assert legacy.status_code == 507                                                      # 예전 링크도 500 이 아니라
    up = client.post("/api/backup/restore/inspect", content=b"PK" + b"0" * 1000,
                     headers={"content-type": "application/zip", "x-filename": "x.zip"})
    assert up.status_code == 507 and "올린 백업 받기" in up.json()["detail"]


def test_restore_upload_goes_to_vault_work_dir_as_raw_body(client):
    _seed(client)
    backup = client.get("/api/backup").content
    report = client.post("/api/backup/restore/inspect", content=backup,
                         headers={"content-type": "application/zip", "x-filename": "%EB%B0%B1%EC%97%85.zip"}).json()
    assert report["ok"] is True and report["token"]
    saved = list((get_settings().vault_dir / ".work" / "restore-upload").glob("*.zip"))
    assert [p.stem for p in saved] == [report["token"]]
    # 예전 모양(multipart)도 받는다
    old = client.post("/api/backup/restore/inspect", files={"file": ("백업.zip", backup, "application/zip")}).json()
    assert old["ok"] is True


def test_work_dir_not_in_backup_and_cleaned_on_start(client):
    folder = workspace.work_dir("backup")
    (folder / "남은것.zip").write_bytes(b"x")
    names = [name for _p, name in export._vault_files(get_settings().vault_dir, True)]
    assert not any(n.startswith(".work") for n in names)
    assert workspace.clean_stale(everything=True) == 1 and not (folder / "남은것.zip").exists()


def test_health_shows_workspace(client):
    data = client.get("/api/health").json()
    assert data["workspace"]["work_dir"].endswith(".work") and "free_bytes" in data["workspace"]
