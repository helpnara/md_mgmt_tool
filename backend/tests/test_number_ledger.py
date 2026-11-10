"""번호 장부 — 백업에서 되살리거나 `.trash` 를 손으로 지워도 지운 번호를 다시 쓰지 않는다 (TODO 264).

예전에는 보관함 기록(`.trash/manifest.jsonl`)만 보고 셌는데, 보관함은 백업에 들어가지 않는다.
"""
from __future__ import annotations

import shutil

from app.config import get_settings
from app.services import export
from app.services import trash


def _forget_trash():
    """되살린 백업 · 비운 보관함과 같다 — `.trash` 가 통째로 없다."""
    shutil.rmtree(get_settings().trash_dir, ignore_errors=True)


def test_project_number_not_reused_after_trash_gone(client):
    first = client.post("/api/projects", json={"title": "첫 과제"}).json()["id"]
    second = client.post("/api/projects", json={"title": "둘째 과제"}).json()["id"]
    assert client.post(f"/api/projects/{second}/archive").status_code == 204
    _forget_trash()
    third = client.post("/api/projects", json={"title": "셋째 과제"}).json()["id"]
    assert third not in (first, second) and third > second


def test_intake_number_not_reused_after_trash_gone(client):
    a = client.post("/api/intakes", json={"title": "접수 하나"}).json()["id"]
    b = client.post("/api/intakes", json={"title": "접수 둘"}).json()["id"]
    assert client.post(f"/api/intakes/{b}/archive").status_code == 204
    _forget_trash()
    c = client.post("/api/intakes", json={"title": "접수 셋"}).json()["id"]
    assert c not in (a, b) and c > b


def test_experience_number_not_reused_after_trash_gone(client):
    client.put("/api/people", json={"people": [{"name": "가팀원"}]})
    client.post("/api/experiences", json={"person": "가팀원", "title": "하나"})
    client.post("/api/experiences", json={"person": "가팀원", "title": "둘"})
    assert client.delete("/api/experiences/E-002").status_code == 204
    _forget_trash()
    assert client.post("/api/experiences", json={"person": "가팀원", "title": "셋"}).json()["id"] == "E-003"


def test_old_vault_seeds_ledger_from_trash_manifest(client):
    a = client.post("/api/projects", json={"title": "옛 과제"}).json()["id"]
    b = client.post("/api/projects", json={"title": "지울 과제"}).json()["id"]
    client.post(f"/api/projects/{b}/archive")
    ledger = get_settings().vault_dir / trash.LEDGER_DIR / trash.LEDGER
    ledger.unlink()                                   # 이 기능 전에 지운 것 — 보관함 기록에만 있다
    names = trash.used_folder_names("projects")       # 읽으면서 장부로 옮겨 적는다
    assert any(name.startswith(b) for name in names)
    assert ledger.exists() and b in ledger.read_text(encoding="utf-8")
    _forget_trash()
    c = client.post("/api/projects", json={"title": "새 과제"}).json()["id"]
    assert c not in (a, b)


def test_ledger_goes_into_backup(client):
    b = client.post("/api/projects", json={"title": "지울 과제"}).json()["id"]
    client.post(f"/api/projects/{b}/archive")
    names = [name for _path, name in export._vault_files(get_settings().vault_dir, assets=True)]
    assert f"{trash.LEDGER_DIR}/{trash.LEDGER}" in names
    assert not any(name.startswith(".trash/") for name in names)          # 보관함은 여전히 빠진다
