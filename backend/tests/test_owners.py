"""과제 담당자 (한 명부터 여러 명까지)."""
from __future__ import annotations


def test_single_and_multiple_owners_are_stored_in_the_file(client, vault_dir):
    solo = client.post("/api/projects", json={"title": "단독 과제", "owners": ["권경락"]}).json()
    team = client.post(
        "/api/projects", json={"title": "공동 과제", "owners": ["권경락", "홍길동", "김철수"]}
    ).json()

    assert solo["owners"] == ["권경락"]
    assert team["owners"] == ["권경락", "홍길동", "김철수"]  # 입력 순서를 유지한다

    raw = (vault_dir / "projects" / f"{team['id']}-공동-과제" / "index.md").read_text(encoding="utf-8")
    assert "owners:\n- 권경락\n- 홍길동\n- 김철수" in raw


def test_owner_list_accepts_comma_separated_text(client):
    project = client.post(
        "/api/projects", json={"title": "쉼표 입력", "owners": ["권경락, 홍길동 , 권경락"]}
    ).json()
    # 쉼표로 적어도 나눠 받고, 중복은 정리한다.
    assert project["owners"] == ["권경락", "홍길동"]


def test_owners_can_be_changed_and_cleared(client):
    project = client.post("/api/projects", json={"title": "담당 변경", "owners": ["권경락"]}).json()
    updated = client.patch(f"/api/projects/{project['id']}", json={"owners": ["홍길동", "이영희"]}).json()
    assert updated["owners"] == ["홍길동", "이영희"]

    cleared = client.patch(f"/api/projects/{project['id']}", json={"owners": []}).json()
    assert cleared["owners"] == []


def test_projects_can_be_filtered_by_owner(client):
    first = client.post("/api/projects", json={"title": "A 과제", "owners": ["권경락", "홍길동"]}).json()
    second = client.post("/api/projects", json={"title": "B 과제", "owners": ["홍길동"]}).json()
    client.post("/api/projects", json={"title": "C 과제"})

    mine = [item["id"] for item in client.get("/api/projects", params={"owner": "권경락"}).json()]
    assert mine == [first["id"]]

    shared = {item["id"] for item in client.get("/api/projects", params={"owner": "홍길동"}).json()}
    assert shared == {first["id"], second["id"]}


def test_owner_list_is_offered_for_input_and_filtering(client):
    client.post("/api/projects", json={"title": "A", "owners": ["권경락", "홍길동"]})
    client.post("/api/projects", json={"title": "B", "owners": ["홍길동"]})
    assert client.get("/api/meta").json()["owners"] == ["권경락", "홍길동"]


def test_legacy_single_owner_field_is_read_and_migrated(client, vault_dir):
    """예전 문서의 owner(단수) 표기도 읽어야 한다."""
    project = client.post("/api/projects", json={"title": "구버전 문서"}).json()
    path = vault_dir / "projects" / f"{project['id']}-구버전-문서" / "index.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("owners: []", "owner: 권경락"), encoding="utf-8"
    )

    client.post("/api/reindex")
    assert client.get(f"/api/projects/{project['id']}").json()["owners"] == ["권경락"]

    # 이후 수정하면 owners(복수)로 옮겨 적는다.
    client.patch(f"/api/projects/{project['id']}", json={"owners": ["권경락", "홍길동"]})
    raw = path.read_text(encoding="utf-8")
    assert "owners:" in raw and "owner:" not in raw.replace("owners:", "")
