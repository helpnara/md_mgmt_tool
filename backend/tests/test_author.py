"""작성자 — 지금은 설정에서 정한 사용자, 나중에는 로그인한 사용자."""
from __future__ import annotations


def test_author_defaults_to_empty_until_it_is_set(client):
    assert client.get("/api/settings").json()["author"] == ""

    project = client.post("/api/projects", json={"title": "작성자 확인"}).json()
    entry = client.post(
        f"/api/projects/{project['id']}/entries", json={"title": "설정 전 기록"}
    ).json()
    assert entry["author"] is None  # 억지로 이름을 지어내지 않는다


def test_setting_an_author_stamps_new_entries(client, vault_dir):
    saved = client.put("/api/settings", json={"author": "권경락"}).json()
    assert saved["author"] == "권경락"
    assert (vault_dir / "settings.json").exists()

    project = client.post("/api/projects", json={"title": "작성자 확인"}).json()
    entry = client.post(
        f"/api/projects/{project['id']}/entries", json={"date": "2026-09-03", "title": "기록"}
    ).json()
    assert entry["author"] == "권경락"

    raw = (
        vault_dir / "projects" / f"{project['id']}-작성자-확인" / entry["rel_path"]
    ).read_text(encoding="utf-8")
    assert "author: 권경락" in raw  # 파일만 봐도 누가 썼는지 알 수 있다


def test_request_can_override_the_setting(client):
    """로그인이 생기면 로그인한 사용자가 이 자리로 들어온다."""
    client.put("/api/settings", json={"author": "권경락"})
    project = client.post("/api/projects", json={"title": "대리 작성"}).json()
    entry = client.post(
        f"/api/projects/{project['id']}/entries", json={"title": "기록", "author": "홍길동"}
    ).json()
    assert entry["author"] == "홍길동"


def test_editing_does_not_steal_authorship(client):
    """다른 사람이 쓴 기록을 고쳐도 작성자가 바뀌면 안 된다."""
    client.put("/api/settings", json={"author": "홍길동"})
    project = client.post("/api/projects", json={"title": "작성자 유지"}).json()
    entry = client.post(f"/api/projects/{project['id']}/entries", json={"title": "기록"}).json()

    client.put("/api/settings", json={"author": "권경락"})
    updated = client.patch(f"/api/entries/{entry['id']}", json={"body": "내가 고친 내용"}).json()
    assert updated["author"] == "홍길동"


def test_reports_record_who_wrote_them(client):
    client.put("/api/settings", json={"author": "권경락"})
    project = client.post("/api/projects", json={"title": "보고 작성자"}).json()
    client.post(f"/api/projects/{project['id']}/entries", json={"title": "기록"})
    report = client.post(
        f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-09-08"}
    ).json()
    assert report["author"] == "권경락"


def test_author_survives_reindex(client):
    client.put("/api/settings", json={"author": "권경락"})
    project = client.post("/api/projects", json={"title": "재인덱싱"}).json()
    entry = client.post(f"/api/projects/{project['id']}/entries", json={"title": "기록"}).json()

    client.post("/api/reindex")
    assert client.get(f"/api/entries/{entry['id']}").json()["author"] == "권경락"


def test_broken_settings_file_does_not_stop_the_tool(client, vault_dir):
    (vault_dir / "settings.json").write_text("{ 깨진 파일", encoding="utf-8")
    assert client.get("/api/settings").json()["author"] == ""
    project = client.post("/api/projects", json={"title": "설정 깨짐"}).json()
    assert client.post(f"/api/projects/{project['id']}/entries", json={"title": "기록"}).status_code == 201
