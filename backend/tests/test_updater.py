"""zip 을 업데이트 폴더에 두면 업데이트 (TODO 298)."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import updater
from app.config import get_settings


def _install(root: Path, name: str, files: dict[str, str]) -> None:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    (root / updater.INFO).write_text(f"느린 나이테\n\n배포본 이름  {name}\n", encoding="utf-8")
    (root / updater.MANIFEST).write_text("\n".join([*files, updater.INFO, updater.MANIFEST]) + "\n", encoding="utf-8")


def _release(folder: Path, name: str, files: dict[str, str], sha: bool = True) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.zip"
    listing = [*files, updater.INFO, updater.MANIFEST]
    with zipfile.ZipFile(path, "w") as archive:
        for rel, text in files.items():
            archive.writestr(f"{updater.TOP}/{rel}", text)
        archive.writestr(f"{updater.TOP}/{updater.INFO}", f"느린 나이테\n\n배포본 이름  {name}\n")
        archive.writestr(f"{updater.TOP}/{updater.MANIFEST}", "\n".join(listing) + "\n")
    if sha:
        (folder / f"{path.name}.sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest() + f"  {path.name}\n", encoding="utf-8")
    return path


OLD = {"run.py": "old run", "backend/app/main.py": "old main", "backend/old_only.py": "gone in new"}
NEW = {"run.py": "new run", "backend/app/main.py": "new main", "backend/new_only.py": "added"}


@pytest.fixture
def install(tmp_path):
    root = tmp_path / "느린나이테"
    _install(root, "느린나이테-20261110-v1", OLD)
    (root / "vault" / "projects").mkdir(parents=True)
    (root / "vault" / "projects" / "a.md").write_text("내 자료", encoding="utf-8")
    (root / "data-mode.json").write_text('{"mode": "mine"}', encoding="utf-8")
    return root


def test_find_newer_and_verify(install):
    updates = install / "updates"
    _release(updates, "느린나이테-20261101-v3", NEW)
    _release(updates, "느린나이테-20261116-v6", NEW)
    broken = _release(updates, "느린나이테-20261117-v1", NEW)
    broken.write_bytes(broken.read_bytes() + b"x")          # 검사값과 어긋남
    (updates / "다른파일.zip").write_text("x")
    found = updater.candidates(install)
    assert found["current"] == "느린나이테-20261110-v1"
    assert [c["name"] for c in found["items"]] == ["느린나이테-20261117-v1", "느린나이테-20261116-v6", "느린나이테-20261101-v3"]
    assert "검사값" in found["items"][0]["problem"] and found["newest"] == "느린나이테-20261116-v6"
    assert found["items"][2]["newer"] is False
    bad = updates / "느린나이테-20261118-v1.zip"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("엉뚱한/run.py", "x")
    assert "배포본이 아닙니다" in updater.verify(bad)


def test_apply_keeps_data_and_rollback(install):
    zip_path = _release(install / "updates", "느린나이테-20261116-v6", NEW)
    updater.request(install, zip_path, by="관리자")
    result = updater.apply_pending(install, log=lambda *_: None)
    assert result["ok"] and result["from"] == "느린나이테-20261110-v1" and result["to"] == "느린나이테-20261116-v6"
    assert (install / "run.py").read_text(encoding="utf-8") == "new run" and (install / "backend/new_only.py").exists()
    assert not (install / "backend/old_only.py").exists()                     # 새 판에 없는 파일은 지운다
    assert (install / "vault/projects/a.md").read_text(encoding="utf-8") == "내 자료"   # 데이터 · 모드는 그대로
    assert (install / "data-mode.json").exists()
    assert updater.current_version(install) == "느린나이테-20261116-v6"
    assert (install / "updates" / updater.APPLIED_DIR / zip_path.name).exists() and not zip_path.exists()
    assert updater.read_state(install)["last"]["ok"] is True
    assert updater.apply_pending(install) is None                              # 예약은 한 번만
    # 되돌리기
    updater.request_rollback(install, by="run.bat --rollback")
    back = updater.apply_pending(install, log=lambda *_: None)
    assert back["ok"] and back["to"] == "느린나이테-20261110-v1"
    assert (install / "run.py").read_text(encoding="utf-8") == "old run" and (install / "backend/old_only.py").exists()
    assert not (install / "backend/new_only.py").exists() and updater.current_version(install) == "느린나이테-20261110-v1"
    assert (install / "vault/projects/a.md").exists()


def test_failed_apply_keeps_current_and_records(install):
    zip_path = _release(install / "updates", "느린나이테-20261116-v6", NEW)
    updater.request(install, zip_path)
    zip_path.write_bytes(b"not a zip")                                          # 예약 뒤 파일이 깨졌다
    result = updater.apply_pending(install, log=lambda *_: None)
    assert result["ok"] is False and result["error"]
    assert (install / "run.py").read_text(encoding="utf-8") == "old run"
    assert updater.read_state(install)["last"]["ok"] is False


def test_api_admin_only_and_request(tmp_path, monkeypatch):
    home = tmp_path / "home"
    _install(home, "느린나이테-20261110-v1", OLD)
    _release(home / "updates", "느린나이테-20261116-v6", NEW)
    monkeypatch.setenv("MD_MGMT_VAULT", str(tmp_path / "vault"))
    monkeypatch.setenv("MD_MGMT_HOME", str(home))
    monkeypatch.setenv("MD_MGMT_SHARE", "1")
    monkeypatch.delenv("MD_MGMT_CHILD", raising=False)
    get_settings.cache_clear()
    from app.main import app

    with TestClient(app, client=("127.0.0.1", 51301)) as owner, TestClient(app, client=("10.0.0.88", 51302)) as other:
        st = owner.get("/api/update").json()
        assert st["current"] == "느린나이테-20261110-v1" and st["newest"] == "느린나이테-20261116-v6" and st["supervised"] is False
        assert other.get("/api/update").status_code == 403
        assert owner.post("/api/update", json={"name": "없는판"}).status_code == 404
        done = owner.post("/api/update?wait=1", json={"name": "느린나이테-20261116-v6"}).json()
        assert done["restarting"] is False and json.loads((home / "updates" / updater.PENDING).read_text(encoding="utf-8"))["action"] == "apply"
        assert owner.post("/api/update/rollback").status_code == 400                # 아직 되돌릴 판 없음
        assert owner.put("/api/settings", json={"update_dir": str(tmp_path / "share")}).status_code == 200
        assert owner.get("/api/update").json()["folder"] == str(tmp_path / "share")
    get_settings.cache_clear()


def test_progress_stages_in_order(install):
    """TODO 300 — 적용 · 되돌리기가 단계를 차례로 알린다(화면의 진행 표시)."""
    zip_path = _release(install / "updates", "느린나이테-20261116-v6", NEW)
    updater.request(install, zip_path, by="관리자")
    assert updater.peek_pending(install)["name"] == "느린나이테-20261116-v6"
    seen: list[tuple[str, int, int]] = []
    updater.apply_pending(install, log=lambda *_: None, progress=lambda stage, done=0, total=0: seen.append((stage, done, total)))
    order = [stage for stage, _, _ in seen]
    firsts = sorted(set(order), key=order.index)
    assert firsts == ["verify", "extract", "keep", "copy", "clean"]
    assert ("copy", len(NEW), len(NEW)) in seen or any(s == "copy" and d == t and t > 0 for s, d, t in seen)
    seen.clear()
    updater.request_rollback(install, by="관리자")
    updater.apply_pending(install, log=lambda *_: None, progress=lambda stage, done=0, total=0: seen.append((stage, done, total)))
    order = [stage for stage, _, _ in seen]
    assert sorted(set(order), key=order.index) == ["restore", "clean"]


def test_progress_window_answers_while_applying():
    """TODO 300 — run.py 의 진행 창구: 진행은 JSON, 다른 /api 는 503, 화면은 기다림 쪽."""
    import importlib.util
    import socket
    import urllib.error
    import urllib.request

    spec = importlib.util.spec_from_file_location("run_main", Path(__file__).resolve().parents[2] / "run.py")
    run_main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run_main)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with run_main.ProgressWindow(["--port", str(port)], {"action": "apply", "name": "느린나이테-20261116-v6"}) as window:
        window.update("copy", 3, 10)
        with opener.open(f"http://127.0.0.1:{port}/api/update/progress", timeout=3) as response:
            body = json.load(response)
        assert body["phase"] == "applying" and body["stage"] == "copy" and body["done"] == 3 and body["to"] == "느린나이테-20261116-v6"
        for path, kind in (("/api/meta", "json"), ("/", "html")):
            with pytest.raises(urllib.error.HTTPError) as caught:
                opener.open(f"http://127.0.0.1:{port}{path}", timeout=3)
            assert caught.value.code == 503 and kind in caught.value.headers["Content-Type"]
    # 끝나면 자리를 비운다 — 새 판 서버가 같은 자리를 잡을 수 있게
    with socket.socket() as again:
        again.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)   # uvicorn 과 같이
        again.bind(("127.0.0.1", port))
        again.listen()


def test_backup_before_update_check_skip_and_space(tmp_path, monkeypatch):
    """TODO 301 — 업데이트 전 백업: 예상 크기 · 남은 공간 · 오늘 백업이면 건너뛰기, 진행은 /api/update/job."""
    home = tmp_path / "home"
    _install(home, "느린나이테-20261110-v1", OLD)
    _release(home / "updates", "느린나이테-20261116-v6", NEW)
    vault = tmp_path / "vault"
    (vault / "projects").mkdir(parents=True)
    (vault / "projects" / "a.md").write_text("내 자료" * 100, encoding="utf-8")
    backups = tmp_path / "backups"
    backups.mkdir()
    monkeypatch.setenv("MD_MGMT_VAULT", str(vault))
    monkeypatch.setenv("MD_MGMT_HOME", str(home))
    monkeypatch.delenv("MD_MGMT_SHARE", raising=False)
    monkeypatch.delenv("MD_MGMT_CHILD", raising=False)
    get_settings.cache_clear()
    from app.api import update as update_api
    from app.main import app
    from app.services import workspace

    with TestClient(app, client=("127.0.0.1", 51303)) as owner:
        first = owner.get("/api/update/check").json()
        assert first["enabled"] is False and first["today"] is None             # 백업 폴더 없음
        assert owner.post("/api/update?wait=1", json={"name": "느린나이테-20261116-v6", "backup": True}).status_code == 400
        assert owner.put("/api/settings", json={"backup_dir": str(backups)}).status_code == 200
        check = owner.get("/api/update/check").json()
        assert check["enabled"] and check["today"] is None and check["expected_bytes"] > 0 and check["enough"] is True
        # 남은 공간이 모자라면 백업하며 업데이트는 막는다
        monkeypatch.setattr(workspace, "free_bytes", lambda folder: 1)
        assert owner.get("/api/update/check").json()["enough"] is False
        refused = owner.post("/api/update?wait=1", json={"name": "느린나이테-20261116-v6", "backup": True})
        assert refused.status_code == 400 and "남은 공간" in refused.json()["detail"]
        monkeypatch.undo()
        monkeypatch.setenv("MD_MGMT_VAULT", str(vault))
        monkeypatch.setenv("MD_MGMT_HOME", str(home))
        update_api._job.clear()
        # 백업하고 업데이트 — 백업 파일이 생기고 예약에 적힌다
        done = owner.post("/api/update?wait=1", json={"name": "느린나이테-20261116-v6", "backup": True}).json()
        assert done["state"] == "scheduled" and done["data_backup"]
        assert (backups / done["data_backup"]).is_file()
        assert json.loads((home / "updates" / updater.PENDING).read_text(encoding="utf-8"))["data_backup"] == done["data_backup"]
        job = owner.get("/api/update/job").json()
        assert job["state"] == "scheduled" and job["progress"] is None
        # 이제 오늘 백업이 있다 → 건너뛰기를 고르면 새로 만들지 않는다
        assert owner.get("/api/update/check").json()["today"]["file"] == done["data_backup"]
        count = len(list(backups.glob("*.zip")))
        skipped = owner.post("/api/update?wait=1", json={"name": "느린나이테-20261116-v6", "backup": False}).json()
        assert skipped["state"] == "scheduled" and skipped["data_backup"] == "" and len(list(backups.glob("*.zip"))) == count
    update_api._job.clear()
    get_settings.cache_clear()
