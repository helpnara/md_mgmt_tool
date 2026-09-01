"""사용자가 md 파일을 직접 고치다 깨뜨려도 도구가 멈추면 안 된다."""
from __future__ import annotations


def setup(client):
    project = client.post("/api/projects", json={"title": "회복 테스트"}).json()
    client.post(
        f"/api/projects/{project['id']}/entries",
        json={"date": "2026-09-03", "title": "정상 기록", "body": "정상"},
    )
    return project


def test_one_broken_file_does_not_stop_the_rest(client, vault_dir):
    project = setup(client)
    logs = vault_dir / "projects" / f"{project['id']}-회복-테스트" / "logs"
    (logs / "2026-09-05-깨진기록.md").write_text(
        "---\ntitle: [닫히지 않은 목록\ndate: 2026-09-05\n---\n\n본문\n", encoding="utf-8"
    )

    result = client.post("/api/reindex")
    assert result.status_code == 200

    body = result.json()
    assert body["indexed"] == 1
    assert len(body["problems"]) == 1
    assert "깨진기록" in body["problems"][0]["path"]
    assert body["problems"][0]["reason"]  # 무엇이 문제인지 알려 준다

    # 정상 기록은 그대로 보인다.
    titles = [item["title"] for item in client.get(f"/api/projects/{project['id']}/entries").json()]
    assert "정상 기록" in titles


def test_broken_overview_keeps_other_projects_visible(client, vault_dir):
    first = setup(client)
    second = client.post("/api/projects", json={"title": "멀쩡한 과제"}).json()

    index_md = vault_dir / "projects" / f"{first['id']}-회복-테스트" / "index.md"
    index_md.write_text("---\nstatus: [깨짐\n---\n본문\n", encoding="utf-8")

    result = client.post("/api/reindex").json()
    assert any("index.md" in item["path"] for item in result["problems"])

    ids = [item["id"] for item in client.get("/api/projects").json()]
    assert second["id"] in ids  # 멀쩡한 과제는 계속 보인다


def test_fixing_the_file_restores_it(client, vault_dir):
    project = setup(client)
    logs = vault_dir / "projects" / f"{project['id']}-회복-테스트" / "logs"
    broken = logs / "2026-09-05-복구.md"
    broken.write_text("---\ntitle: [깨짐\n---\n\n본문\n", encoding="utf-8")
    assert client.post("/api/reindex").json()["problems"]

    broken.write_text("---\ndate: 2026-09-05\ntitle: 고친 기록\n---\n\n본문\n", encoding="utf-8")
    assert client.post("/api/reindex").json()["problems"] == []
    titles = [item["title"] for item in client.get(f"/api/projects/{project['id']}/entries").json()]
    assert "고친 기록" in titles
