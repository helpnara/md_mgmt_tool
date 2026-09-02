"""진행일지·보고 서식(설정)과 삭제 보관함.

보관함의 핵심은 "되돌릴 수 있는가" 하나다. 옮기는 것만으로는 부족하고,
어디서 왔는지를 남겨야 되돌리기가 성립한다.
"""
from __future__ import annotations


def make(client, **kwargs):
    payload = {"title": "서식 과제"}
    payload.update(kwargs)
    response = client.post("/api/projects", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ── 진행일지 서식 ─────────────────────────────────────

def test_entry_template_falls_back_to_the_built_in_default(client):
    project = make(client)
    detail = client.get(f"/api/projects/{project['id']}").json()
    assert detail["entry_template"] == "## 내용\n\n## 진행\n\n## 계획\n"


def test_entry_template_per_project_type(client):
    client.put(
        "/api/settings",
        json={"entry_templates": {"": "공통 서식", "rnd": "## 시험 조건\n\n## 결과"}},
    )
    rnd = make(client, title="연구 과제", type="rnd")
    other = make(client, title="투자 과제", type="investment")

    assert "## 시험 조건" in client.get(f"/api/projects/{rnd['id']}").json()["entry_template"]
    # 속성별 서식이 없으면 공통 서식으로 내려온다.
    assert client.get(f"/api/projects/{other['id']}").json()["entry_template"] == "공통 서식"


def test_clearing_a_template_returns_to_the_default(client):
    client.put("/api/settings", json={"entry_templates": {"": "잠깐 쓰던 서식"}})
    client.put("/api/settings", json={"entry_templates": {"": "   "}})
    project = make(client)
    assert client.get(f"/api/projects/{project['id']}").json()["entry_template"].startswith("## 내용")


# ── 보고 초안 서식 ────────────────────────────────────

def test_report_template_from_settings(client):
    client.put("/api/settings", json={"report_template": "# 주간\n\n{summary}\n\n## 협조 요청"})
    project = make(client)
    client.post(f"/api/projects/{project['id']}/entries", json={"date": "2026-09-01", "body": "진행"})

    draft = client.post(f"/api/projects/{project['id']}/reports/draft", json={}).json()
    assert draft["body"].startswith("# 주간")
    assert "## 협조 요청" in draft["body"]


def test_report_template_without_summary_is_ignored(client):
    """{summary} 가 없으면 진행 내용이 통째로 사라진다. 그런 서식은 쓰지 않는다."""
    client.put("/api/settings", json={"report_template": "# 제목만 있는 서식"})
    project = make(client)
    client.post(
        f"/api/projects/{project['id']}/entries",
        json={"date": "2026-09-01", "body": "빠지면 안 되는 진행 내용"},
    )

    draft = client.post(f"/api/projects/{project['id']}/reports/draft", json={}).json()
    assert "## 보고 요약" in draft["body"]  # 기본 서식으로 돌아간다
    assert "빠지면 안 되는 진행 내용" in draft["body"]


def test_settings_keeps_untouched_fields(client):
    client.put("/api/settings", json={"author": "권경락"})
    client.put("/api/settings", json={"report_template": "{summary}"})
    settings = client.get("/api/settings").json()
    assert settings["author"] == "권경락"
    assert settings["report_template"] == "{summary}"


# ── 삭제 보관함 ───────────────────────────────────────

def test_deleted_entry_can_be_restored(client):
    project = make(client, title="복구 과제")
    entry = client.post(
        f"/api/projects/{project['id']}/entries",
        json={"date": "2026-09-01", "title": "지울 기록", "body": "내용"},
    ).json()
    client.delete(f"/api/entries/{entry['id']}")
    assert client.get(f"/api/projects/{project['id']}/entries").json() == []

    item = client.get("/api/trash").json()[0]
    assert item["kind"] == "entry"
    assert item["restorable"] is True
    assert "지울 기록" in item["label"]

    client.post(f"/api/trash/{item['trash_name']}/restore")
    entries = client.get(f"/api/projects/{project['id']}/entries").json()
    assert [e["title"] for e in entries] == ["지울 기록"]
    assert client.get("/api/trash").json() == []


def test_archived_project_can_be_restored(client):
    project = make(client, title="보관할 과제")
    client.post(f"/api/projects/{project['id']}/archive")
    assert client.get("/api/projects").json() == []

    item = client.get("/api/trash").json()[0]
    assert item["kind"] == "project"
    client.post(f"/api/trash/{item['trash_name']}/restore")
    assert [p["title"] for p in client.get("/api/projects").json()] == ["보관할 과제"]


def test_deleted_attachment_can_be_restored(client):
    project = make(client, title="첨부 복구")
    entry = client.post(
        f"/api/projects/{project['id']}/entries", json={"date": "2026-09-01", "body": "내용"}
    ).json()
    saved = client.post(
        f"/api/entries/{entry['id']}/attachments",
        files={"file": ("자료.txt", b"hello", "text/plain")},
    ).json()
    client.delete(f"/api/attachments/{saved['id']}")
    assert client.get(f"/api/projects/{project['id']}/attachments").json()["items"] == []

    item = next(i for i in client.get("/api/trash").json() if i["kind"] == "attachment")
    client.post(f"/api/trash/{item['trash_name']}/restore")
    names = [
        i["orig_name"] for i in client.get(f"/api/projects/{project['id']}/attachments").json()["items"]
    ]
    assert names == ["자료.txt"]


def test_restore_does_not_overwrite_something_at_the_same_place(client):
    """지운 자리에 같은 이름의 새 기록이 생겼을 수 있다. 덮어쓰지 않는다."""
    project = make(client, title="덮어쓰기 방지")
    first = client.post(
        f"/api/projects/{project['id']}/entries",
        json={"date": "2026-09-01", "title": "같은 이름", "body": "먼저"},
    ).json()
    client.delete(f"/api/entries/{first['id']}")
    client.post(
        f"/api/projects/{project['id']}/entries",
        json={"date": "2026-09-01", "title": "같은 이름", "body": "나중"},
    )

    item = client.get("/api/trash").json()[0]
    client.post(f"/api/trash/{item['trash_name']}/restore")
    bodies = [e["body"] for e in client.get(f"/api/projects/{project['id']}/entries").json()]
    assert sorted(bodies) == ["나중", "먼저"]


def test_restore_rejects_paths_outside_the_trash(client, vault_dir):
    """보관함 밖을 가리키는 이름은 거부한다.

    대부분은 주소 단계에서 걸러지지만(`..` 는 클라이언트가 정규화해 405), 그것에
    기대지 않고 서비스 자체가 막는지 직접 확인한다.
    """
    import pytest

    from app import deps
    from app.services import trash as svc

    for name in ("..", "../settings.json", "a/b", ""):
        assert client.post(f"/api/trash/{name}/restore").status_code in (400, 404, 405)

    (vault_dir / "settings.json").write_text("{}", encoding="utf-8")
    conn = deps._conn
    for name in ("..", "../settings.json", "logs/x.md"):
        with pytest.raises(svc.RestoreError):
            svc.restore(conn, name)
    # 막았으니 vault 안의 파일은 그대로 있어야 한다.
    assert (vault_dir / "settings.json").exists()


def test_unknown_trash_item_is_a_clear_error(client):
    response = client.post("/api/trash/없는항목/restore")
    assert response.status_code == 400
    assert "찾을 수 없습니다" in response.json()["detail"]


# ── 보고 시점 마커 ────────────────────────────────────

def test_entry_knows_which_frozen_report_covered_it(client):
    project = make(client, title="마커 과제")
    old = client.post(
        f"/api/projects/{project['id']}/entries", json={"date": "2026-08-01", "body": "예전"}
    ).json()
    report = client.post(f"/api/projects/{project['id']}/reports/draft", json={}).json()

    # 확정 전에는 아직 보고한 것이 아니다.
    assert client.get(f"/api/entries/{old['id']}").json()["reported_on"] is None

    client.post(f"/api/reports/{report['id']}/freeze")
    assert client.get(f"/api/entries/{old['id']}").json()["reported_on"] == report["report_date"]

    # 보고 뒤에 쓴 기록은 아직 미보고다.
    fresh = client.post(
        f"/api/projects/{project['id']}/entries", json={"date": "2026-09-02", "body": "이후"}
    ).json()
    assert client.get(f"/api/entries/{fresh['id']}").json()["reported_on"] is None
