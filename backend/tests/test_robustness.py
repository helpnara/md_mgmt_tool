"""전수 점검(2026-09-30)에서 찾은 서버 쪽 고장 (TODO 163 · 164 · 167).

손으로 고친 파일 · 깨진 보조 파일 · 화면이 보내지 않는 입력에서 **도구가 멈추거나 500 을 내지 않는다.**
"""
import json

from fastapi.testclient import TestClient


def _restart(vault_dir):
    """같은 데이터 폴더로 서버를 다시 켠다 — 시작 작업(색인 · 보관함 확인)을 다시 돈다."""
    from app.main import app

    return TestClient(app)


# ── 163 · 보조 파일이 깨져도 켜진다 ────────────────────────────────────────


def test_broken_trash_manifest_line_does_not_stop_startup(client, vault_dir):
    made = client.post("/api/projects", json={"title": "지울 과제"}).json()
    client.post(f"/api/projects/{made['id']}/archive")
    manifest = vault_dir / ".trash" / "manifest.jsonl"
    manifest.write_text(manifest.read_text(encoding="utf-8") + "[1]\n\"글\"\n{bad\n", encoding="utf-8")
    with _restart(vault_dir) as again:
        items = again.get("/api/trash").json()
        assert any(item.get("project_id") == made["id"] and item["restorable"] for item in items)
        assert again.post("/api/reindex").status_code == 200


def test_settings_file_that_is_a_list_falls_back_to_defaults(client, vault_dir):
    (vault_dir / "settings.json").write_text("[1, 2]", encoding="utf-8")
    with _restart(vault_dir) as again:
        settings = again.get("/api/settings").json()
        assert settings["report_weekday"] == 1
        assert settings["unreadable"] == ["*"]


def test_settings_value_with_wrong_shape_uses_default_for_that_value_only(client, vault_dir):
    (vault_dir / "settings.json").write_text(json.dumps({
        "author": "권경락", "backup_every_hours": "매일", "report_weekday": 9, "intake_stale_days": 7,
    }), encoding="utf-8")
    assert client.get("/api/settings/backup/status").status_code == 200
    settings = client.get("/api/settings").json()
    assert settings["author"] == "권경락" and settings["intake_stale_days"] == 7
    assert settings["backup_every_hours"] == 24 and settings["report_weekday"] == 1
    assert sorted(settings["unreadable"]) == ["backup_every_hours", "report_weekday"]
    # 한 번 저장하면 파일이 바로잡힌다
    client.put("/api/settings", json={"author": "권경락"})
    assert client.get("/api/settings").json()["unreadable"] == []


# ── 164 · 날짜 하나가 틀려도 과제가 사라지지 않는다 ──────────────────────────


def _set_line(path, key, value):
    lines = path.read_text(encoding="utf-8").splitlines()
    lines = [f"{key}: {value}" if line.startswith(f"{key}:") else line for line in lines]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_impossible_date_blanks_only_that_value(client, vault_dir):
    made = client.post("/api/projects", json={"title": "날짜 틀림", "due_date": "2026-03-01"}).json()
    index = next((vault_dir / "projects").glob(f"{made['id']}-*")) / "index.md"
    _set_line(index, "due_date", "2026-02-30")
    client.post("/api/reindex")

    assert made["id"] in [p["id"] for p in client.get("/api/projects").json()]
    assert client.get(f"/api/projects/{made['id']}").json()["due_date"] is None
    problems = client.get("/api/meta").json()["problems"]
    assert any("due_date" in item["reason"] and "2026-02-30" in item["reason"] for item in problems)
    # 파일은 그대로다 — 사람이 고칠 것을 도구가 지우지 않는다
    assert "due_date: 2026-02-30" in index.read_text(encoding="utf-8")


def test_fixing_the_date_in_the_tool_clears_the_warning(client, vault_dir):
    made = client.post("/api/projects", json={"title": "고칠 과제"}).json()
    index = next((vault_dir / "projects").glob(f"{made['id']}-*")) / "index.md"
    _set_line(index, "start_date", "어제")
    client.post("/api/reindex")
    assert client.get("/api/meta").json()["problems"]
    client.patch(f"/api/projects/{made['id']}", json={"start_date": "2026-09-01"})
    assert client.get("/api/meta").json()["problems"] == []


def test_bad_dates_in_entry_and_intake_are_reported_not_fatal(client, vault_dir):
    made = client.post("/api/projects", json={"title": "일지 과제"}).json()
    client.post(f"/api/projects/{made['id']}/entries", json={"date": "2026-09-01", "title": "첫", "body": "b"})
    log = next((vault_dir / "projects").glob(f"{made['id']}-*/logs/*.md"))
    _set_line(log, "date", "2026-13-01")
    intake = client.post("/api/intakes", json={"title": "접수"}).json()
    request = next((vault_dir / "intakes").glob(f"{intake['id']}-*")) / "request.md"
    _set_line(request, "received_on", "어제")
    client.post("/api/reindex")

    entries = client.get(f"/api/projects/{made['id']}/entries").json()
    assert [e["date"] for e in entries] == ["2026-09-01"]  # 파일 이름의 날짜로 선다
    assert client.get(f"/api/intakes/{intake['id']}").status_code == 200
    reasons = " ".join(item["reason"] for item in client.get("/api/meta").json()["problems"])
    assert "2026-13-01" in reasons and "어제" in reasons


# ── 167 · 화면이 보내지 않는 입력도 500 이 아니다 ─────────────────────────


def test_nan_in_body_is_a_validation_error_not_500(client):
    response = client.post("/api/people", content=b'{"name": NaN}', headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_huge_row_ids_are_rejected(client):
    for path in ("/api/entries/99999999999999999999", "/api/reports/99999999999999999999"):
        assert client.get(path).status_code == 422


def test_odd_version_paths_are_not_500(client):
    assert client.get("/api/versions", params={"path": "\x00"}).status_code == 400
    assert client.get("/api/versions", params={"path": "가" * 400}).status_code == 200
