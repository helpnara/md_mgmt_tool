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


def test_tidy_keeps_recent_and_moves_sha(install):
    """TODO 302 — .sha256 도 적용됨으로 · 짝 잃은 .sha256 정리 · 적용됨 3판 · 되돌리기 2개 · 같은 이름은 바꿔 넣기."""
    updates = install / "updates"
    names = [f"느린나이테-2026111{d}-v1" for d in range(1, 6)]   # 11 ~ 15일, 다섯 판
    for name in names:
        zip_path = _release(updates, name, {**NEW, "run.py": f"run {name}"})
        updater.request(install, zip_path, by="관리자")
        result = updater.apply_pending(install, log=lambda *_: None)
        assert result["ok"] and result["leftover"] == []
        assert not zip_path.exists() and not (updates / (zip_path.name + ".sha256")).exists()   # zip · .sha256 둘 다 옮김
    applied = sorted(p.name for p in (updates / updater.APPLIED_DIR).iterdir())
    assert applied == sorted([f"{n}.zip" for n in names[-3:]] + [f"{n}.zip.sha256" for n in names[-3:]])
    assert len(updater._rollback_dirs(install)) == 2
    assert updater.latest_rollback(install).name.startswith(names[-2])          # 되돌리기는 바로 앞 판으로
    use = updater.usage(install)
    assert use["applied"] == 3 and use["rollback"] == 2 and use["applied_bytes"] > 0
    # 짝 잃은 .sha256 — 켤 때 정리(run.py 가 켤 때마다 tidy — test_run_py_tidies_on_every_start)
    (updates / "느린나이테-20261101-v9.zip.sha256").write_text("x", encoding="utf-8")
    assert updater.apply_pending(install) is None
    updater.tidy(install)
    assert not (updates / "느린나이테-20261101-v9.zip.sha256").exists()
    # 같은 이름이 적용됨에 있으면 바꿔 넣는다(다시 올리기)
    again = _release(updates, names[-1], {**NEW, "run.py": "again"})
    updater.request(install, again, by="관리자")
    assert updater.apply_pending(install, log=lambda *_: None)["leftover"] == []
    assert not again.exists() and (updates / updater.APPLIED_DIR / again.name).exists()


def test_shared_folder_is_left_alone(install, tmp_path):
    """TODO 302 — 공유 폴더의 zip · .sha256 은 옮기지 않는다(다른 팀장 서버도 같은 폴더를 본다)."""
    shared = tmp_path / "shared"
    shared.mkdir()
    zip_path = _release(shared, "느린나이테-20261116-v6", NEW)
    assert updater.is_local(install, shared) is False and updater.is_local(install, install / "updates") is True
    updater.request(install, zip_path, by="관리자")
    result = updater.apply_pending(install, log=lambda *_: None)
    assert result["ok"] and zip_path.exists() and (shared / (zip_path.name + ".sha256")).exists()
    assert not (shared / updater.APPLIED_DIR).exists()
    found = updater.candidates(install, str(shared))
    assert found["local"] is False and found["newest"] == ""                    # 지금 판이라 띠는 안 뜬다


def test_tidy_odd_sha_names_readonly_and_errors(install):
    """TODO 302(v82) — 내려받으며 바뀐 검사값 이름(.txt · (1) · NFD 한글) · 읽기 전용도 정리, 못 지우면 까닭을 남긴다."""
    import os
    import stat
    import unicodedata

    updates = install / "updates"
    updates.mkdir(exist_ok=True)
    odd = [
        "느린나이테-20261101-v1.zip.sha256",
        "느린나이테-20261101-v2.zip.sha256.txt",
        "느린나이테-20261101-v3.zip (1).sha256",
        unicodedata.normalize("NFD", "느린나이테-20261101-v4.zip.sha256"),
    ]
    for name in odd:
        (updates / name).write_text("x", encoding="utf-8")
    os.chmod(updates / odd[0], stat.S_IREAD)                                     # 읽기 전용
    (updates / "메모.txt").write_text("남겨 둘 것", encoding="utf-8")              # 이 도구의 것이 아니면 건드리지 않는다
    keep = _release(updates, "느린나이테-20261116-v6", NEW)                       # 짝이 있는 검사값은 남긴다
    done = updater.tidy(install)
    assert sorted(done["removed"]) == sorted(odd) and done["errors"] == []
    assert (updates / "메모.txt").exists() and keep.exists() and (updates / (keep.name + ".sha256")).exists()
    assert updater.read_state(install)["tidy"]["removed"]
    # 바뀐 이름의 검사값도 zip 과 함께 옮긴다
    (updates / (keep.name + ".sha256")).rename(updates / (keep.name + ".sha256.txt"))
    assert updater.verify(keep) == "" and updater.candidates(install)["items"][0]["has_sha"] is True
    updater.request(install, keep, by="관리자")
    result = updater.apply_pending(install, log=lambda *_: None)
    assert result["ok"] and not list(updates.glob("*.sha256*"))
    assert (updates / updater.APPLIED_DIR / (keep.name + ".sha256.txt")).exists()


def test_tidy_reports_what_it_could_not_remove(install, monkeypatch):
    (install / "updates").mkdir(exist_ok=True)
    (install / "updates" / "느린나이테-20261101-v1.zip.sha256").write_text("x", encoding="utf-8")
    monkeypatch.setattr(updater, "_remove", lambda path: "PermissionError: 다른 프로그램이 쓰는 중")
    done = updater.tidy(install)
    assert done["removed"] == [] and "PermissionError" in done["errors"][0]
    assert updater.read_state(install)["tidy"]["errors"]


def test_run_py_tidies_on_every_start(install, monkeypatch):
    """TODO 302(v82) — run.bat 을 켤 때(예약이 없어도) 정리한다. 예전에는 예약이 있을 때만 불려 켤 때 정리가 돌지 않았다."""
    import importlib.util
    import subprocess
    import sys

    spec = importlib.util.spec_from_file_location("run_start", Path(__file__).resolve().parents[2] / "run.py")
    run_main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run_main)
    (install / "updates").mkdir(exist_ok=True)
    orphan = install / "updates" / "느린나이테-20261101-v1.zip.sha256"
    orphan.write_text("x", encoding="utf-8")
    monkeypatch.setattr(run_main, "ROOT", install)
    monkeypatch.setattr(sys, "argv", ["run.py", "--port", "8999"])
    monkeypatch.setattr(subprocess, "call", lambda *a, **k: 0)                  # 서버는 띄우지 않는다
    with pytest.raises(SystemExit):
        run_main.supervise()
    assert not orphan.exists()


def test_wait_page_reloads_with_script_not_meta_refresh():
    """TODO 302(v82) — 주소에 #/ 가 있으면 meta refresh 는 다시 읽지 않는다 → 스크립트가 묻고 location.reload()."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("run_wait", Path(__file__).resolve().parents[2] / "run.py")
    run_main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run_main)
    page = run_main._WAIT_PAGE
    assert "http-equiv=\"refresh\"" not in page and "location.reload()" in page and "/api/meta" in page
    # v83 — 2초마다 무조건 묻는다(사슬이 아님) · 질문마다 제한 시간 · 갇히지 않게 단추
    assert "setInterval(ask, 2000)" in page and "AbortController" in page and "지금 다시 열기" in page


def test_after_update_the_new_run_py_takes_over(install, monkeypatch):
    """302(v83) — 적용한 뒤 바깥 고리도 새 판의 run.py 로 이어받는다(run.bat 을 다시 켜지 않아도 새 기다림 쪽 · 정리)."""
    import importlib.util
    import subprocess
    import sys

    spec = importlib.util.spec_from_file_location("run_takeover", Path(__file__).resolve().parents[2] / "run.py")
    run_main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run_main)
    zip_path = _release(install / "updates", "느린나이테-20261116-v6", NEW)
    updater.request(install, zip_path, by="관리자")
    calls = []
    monkeypatch.setattr(run_main, "ROOT", install)
    monkeypatch.setattr(run_main, "ProgressWindow", lambda argv, pending: __import__("contextlib").nullcontext(type("W", (), {"update": staticmethod(lambda *a, **k: None), "state": {}})()))
    monkeypatch.setattr(sys, "argv", ["run.py", "--share", "--port", "8999"])
    monkeypatch.setenv("MD_MGMT_CHILD", "")
    monkeypatch.setattr(subprocess, "call", lambda cmd, env=None: calls.append((cmd, dict(env or {}))) or 0)
    with pytest.raises(SystemExit):
        run_main.supervise()
    assert updater.current_version(install) == "느린나이테-20261116-v6"
    (cmd, env), = calls                                                          # 한 번 — 새 고리(서버 아님)
    assert cmd[1] == str(install / "run.py") and "MD_MGMT_CHILD" not in env and "--share" in cmd
