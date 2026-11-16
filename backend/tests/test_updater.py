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
        done = owner.post("/api/update", json={"name": "느린나이테-20261116-v6"}).json()
        assert done["restarting"] is False and json.loads((home / "updates" / updater.PENDING).read_text(encoding="utf-8"))["action"] == "apply"
        assert owner.post("/api/update/rollback").status_code == 400                # 아직 되돌릴 판 없음
        assert owner.put("/api/settings", json={"update_dir": str(tmp_path / "share")}).status_code == 200
        assert owner.get("/api/update").json()["folder"] == str(tmp_path / "share")
    get_settings.cache_clear()
