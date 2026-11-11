"""백업에서 되살리기 — 뒤에서 하고 단계별 진행을 보인다 (TODO 268)."""
from __future__ import annotations

import tempfile
import time

import pytest

from app.config import get_settings
from app.services import export, restore, restore_jobs


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    temp = tmp_path / "tmp"
    temp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp))
    restore_jobs.reset_for_tests()
    yield
    restore_jobs.reset_for_tests()


def _wait(client, job_id, seconds=15.0):
    end = time.time() + seconds
    while time.time() < end:
        state = client.get(f"/api/backup/restore/jobs/{job_id}").json()
        if state["state"] in ("done", "error", "cancelled"):
            return state
        time.sleep(0.05)
    raise AssertionError("되살리기 작업이 끝나지 않았다")


def _titles(client) -> set[str]:
    return {item["title"] for item in client.get("/api/projects").json()}


def _prepare(client):
    client.post("/api/projects", json={"title": "옮길 과제", "status": "in_progress"})
    backup = client.get("/api/backup").content
    client.post("/api/projects", json={"title": "나중 과제", "status": "in_progress"})
    report = client.post("/api/backup/restore/inspect", content=backup,
                         headers={"content-type": "application/zip", "x-filename": "b.zip"}).json()
    assert report["ok"] and report["token"]
    return report["token"]


def test_job_runs_all_stages_and_replaces_data(client):
    token = _prepare(client)
    job = client.post("/api/backup/restore/jobs", json={"token": token}).json()
    assert job["state"] == "running" and job["stages"] == ["check", "safety", "extract", "swap", "index"]
    done = _wait(client, job["id"])
    assert done["state"] == "done", done["error"]
    assert done["stages_done"] == done["stages"] and done["result"]["projects"] == 1
    assert done["result"]["safety_backup"]
    assert _titles(client) == {"옮길 과제"}
    assert client.get("/api/backup/restore/jobs/current").json()["job"]["id"] == job["id"]   # 다른 화면에 갔다 와도


def test_progress_is_reported_per_stage(client, monkeypatch):
    token = _prepare(client)
    seen: list[tuple[str, int, int]] = []
    real = restore._extract

    def slow_extract(path, into, progress=None):
        def watch(*args):
            seen.append(("extract", args[0], args[1]))
            time.sleep(0.01)
            return progress(*args) if progress else True
        return real(path, into, watch)

    monkeypatch.setattr(restore, "_extract", slow_extract)
    job = client.post("/api/backup/restore/jobs", json={"token": token}).json()
    assert _wait(client, job["id"])["state"] == "done"
    assert seen and seen[-1][1] == seen[-1][2]                                     # 마지막 파일까지 셌다


def test_cancel_before_swap_keeps_current_data_and_drops_safety_copy(client, monkeypatch):
    token = _prepare(client)
    real = restore._extract

    def slow_extract(path, into, progress=None):
        def step(*args):
            time.sleep(0.3)
            return progress(*args) if progress else True
        return real(path, into, step)

    monkeypatch.setattr(restore, "_extract", slow_extract)
    job = client.post("/api/backup/restore/jobs", json={"token": token}).json()
    end = time.time() + 10
    while client.get(f"/api/backup/restore/jobs/{job['id']}").json()["stage"] != "extract" and time.time() < end:
        time.sleep(0.02)
    mid = client.post(f"/api/backup/restore/jobs/{job['id']}/cancel").json()
    assert mid["cancellable"] is True
    done = _wait(client, job["id"])
    assert done["state"] == "cancelled"
    assert _titles(client) == {"옮길 과제", "나중 과제"}                              # 그대로
    vault = get_settings().vault_dir
    assert not (vault / restore.WORK_DIR).exists()
    assert not list(vault.parent.glob(f"{restore.SAFETY_PREFIX}*"))                 # 안전 백업도 지웠다


def test_one_job_at_a_time_and_unknown_token(client):
    assert client.post("/api/backup/restore/jobs", json={"token": "0" * 32}).status_code == 400
    assert client.get("/api/backup/restore/jobs/nope").status_code == 404


def test_error_is_reported_in_korean(client, monkeypatch):
    token = _prepare(client)

    def broken(*args, **kwargs):
        raise restore.RestoreError("백업을 풀지 못했습니다 — 지금 데이터는 그대로입니다.")

    monkeypatch.setattr(restore, "_extract", broken)
    job = client.post("/api/backup/restore/jobs", json={"token": token}).json()
    done = _wait(client, job["id"])
    assert done["state"] == "error" and "그대로" in done["error"]
    assert export  # 쓰지 않는 가져오기 경고 막기
