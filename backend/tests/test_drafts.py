"""쓰다 만 글 — 데이터 폴더 임시 보관 (TODO 170).

브라우저 안 보관은 창 · 프로필 · 주소마다 따로라, 창 하나를 닫고 다른 창에서 열면 "작성 중이던 기록 있음" 이 안 떴다(v7 B-6).
데이터 폴더에 두면 어느 창에서든 같은 글이 돌아오고, 홈이 모아 보여 줄 수 있다.
"""


def test_put_get_list_and_drop(client, vault_dir):
    project = client.post("/api/projects", json={"title": "쓰다 만 과제"}).json()
    key = f"entry:new-{project['id']}"
    content = {"date": "2026-09-30", "title": "쓰던 제목", "body": "쓰던 본문", "tags": ""}
    assert client.put(f"/api/drafts/{key}", json={"content": content}).status_code == 200

    assert client.get(f"/api/drafts/{key}").json()["content"] == content
    # 이 PC 의 데이터 폴더에 파일로 남는다
    assert (vault_dir / ".drafts").is_dir() and list((vault_dir / ".drafts").glob("*.json"))

    items = client.get("/api/drafts").json()["items"]
    assert [item["key"] for item in items] == [key]
    assert items[0]["label"] == "새 진행일지" and project["title"] in items[0]["where"]
    assert items[0]["link"] == f"#/projects/{project['id']}?draft=entry-new"
    assert "content" not in items[0]  # 목록에는 글을 싣지 않는다

    assert client.delete(f"/api/drafts/{key}").status_code == 204
    assert client.get(f"/api/drafts/{key}").json()["content"] is None
    assert client.get("/api/drafts").json()["items"] == []


def test_every_editor_kind_is_described(client):
    project = client.post("/api/projects", json={"title": "과제"}).json()
    entry = client.post(f"/api/projects/{project['id']}/entries",
                        json={"date": "2026-09-01", "title": "첫 기록", "body": "b"}).json()
    report = client.post(f"/api/projects/{project['id']}/reports/draft", json={}).json()
    intake = client.post("/api/intakes", json={"title": "요청"}).json()
    for key in (f"entry:{entry['id']}", f"overview:{project['id']}", f"report:{report['id']}", f"intake:{intake['id']}"):
        assert client.put(f"/api/drafts/{key}", json={"content": "글"}).status_code == 200
    described = {item["key"]: item for item in client.get("/api/drafts").json()["items"]}
    assert described[f"entry:{entry['id']}"]["label"] == "진행일지 고치기 — 첫 기록"
    assert described[f"entry:{entry['id']}"]["link"].endswith(f"?draft=entry-{entry['id']}")
    assert described[f"overview:{project['id']}"]["link"].endswith("?draft=overview")
    assert described[f"report:{report['id']}"]["link"].endswith(f"?report={report['id']}")
    assert described[f"intake:{intake['id']}"]["link"] == f"#/intakes/{intake['id']}?draft=body"
    assert not any(item["missing"] for item in described.values())


def test_draft_of_a_deleted_project_is_listed_as_missing(client):
    project = client.post("/api/projects", json={"title": "지울 과제"}).json()
    client.put(f"/api/drafts/overview:{project['id']}", json={"content": "글"})
    client.post(f"/api/projects/{project['id']}/archive")
    item = client.get("/api/drafts").json()["items"][0]
    assert item["missing"] is True  # 홈이 [버리기] 만 보인다


def test_keys_that_could_escape_the_folder_are_refused(client):
    for key in ("../x", "entry:..", "overview:a/b", "foo:1", "entry:new-" + "가" * 200):
        assert client.put(f"/api/drafts/{key}", json={"content": "x"}).status_code in (400, 404, 405)
    assert client.get("/api/drafts").json()["items"] == []
