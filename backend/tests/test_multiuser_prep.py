"""여러 사람이 쓰게 될 때를 위한 사전 준비.

기준은 하나다 — **나중에 넣으면 그 전 데이터가 빈칸으로 남는가.**
빈칸으로 남는 것만 지금 한다. 서버·로그인·권한은 나중에 해도 데이터가 상하지 않는다.
"""
from __future__ import annotations


def make(client, **kwargs):
    payload = {"title": "준비 과제"}
    payload.update(kwargs)
    response = client.post("/api/projects", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ── 38-3. 과제 생성자 ─────────────────────────────────

def test_creator_comes_from_the_author_setting(client, vault_dir):
    client.put("/api/settings", json={"author": "권경락"})
    project = make(client, title="생성자 기록")
    assert project["created_by"] == "권경락"

    raw = (vault_dir / "projects" / f"{project['id']}-생성자-기록" / "index.md").read_text(
        encoding="utf-8"
    )
    assert "created_by: 권경락" in raw


def test_creator_is_separate_from_owners(client):
    """담당자는 '누가 하는가', 생성자는 '누가 등록했는가'. 서로 다르다."""
    client.put("/api/settings", json={"author": "권경락"})
    project = make(client, title="남의 과제 등록", owners=["김현우", "박서준"])
    assert project["created_by"] == "권경락"
    assert project["owners"] == ["김현우", "박서준"]


def test_creator_can_be_given_explicitly(client):
    """로그인이 생기면 이 자리에 로그인 사용자가 들어온다."""
    client.put("/api/settings", json={"author": "설정값"})
    assert make(client, created_by="요청값")["created_by"] == "요청값"


def test_creator_is_empty_when_no_author_is_set(client):
    """작성자를 아직 안 정했어도 과제 등록은 막지 않는다."""
    assert make(client, title="작성자 없음")["created_by"] is None


def test_creator_survives_reindex(client):
    client.put("/api/settings", json={"author": "권경락"})
    project = make(client, title="색인 후에도")
    client.post("/api/reindex")
    assert client.get(f"/api/projects/{project['id']}").json()["created_by"] == "권경락"


# ── 38-1. 과제 번호 체계 ──────────────────────────────

def test_number_keeps_its_current_shape_when_no_team_code(client):
    assert make(client, title="첫 과제")["id"].endswith("-001")
    assert make(client, title="둘째 과제")["id"].endswith("-002")


def test_team_code_goes_into_the_number(client):
    client.put("/api/settings", json={"project_code": "소재"})
    project = make(client, title="코드 붙은 과제")
    year = project["id"].split("-")[0]
    assert project["id"] == f"{year}-소재-001"


def test_old_numbers_are_left_alone_when_the_code_changes(client):
    """이미 만든 번호는 바꾸지 않는다. 바꾸면 폴더명과 링크가 모두 흔들린다."""
    before = make(client, title="코드 전")
    client.put("/api/settings", json={"project_code": "소재"})
    after = make(client, title="코드 후")

    assert client.get(f"/api/projects/{before['id']}").json()["id"] == before["id"]
    assert "소재" not in before["id"]
    assert "소재" in after["id"]
    # 두 형태가 섞여 있어도 목록에 다 나온다.
    assert {p["id"] for p in client.get("/api/projects").json()} == {before["id"], after["id"]}


def test_sequence_is_counted_per_code(client):
    make(client, title="코드 없이 하나")
    client.put("/api/settings", json={"project_code": "소재"})
    first = make(client, title="소재 하나")
    second = make(client, title="소재 둘")
    assert first["id"].endswith("-001")  # 코드별로 따로 센다
    assert second["id"].endswith("-002")


def test_numeric_only_team_code_is_rejected(client):
    """숫자만으로 된 코드는 일련번호와 구분되지 않는다."""
    response = client.put("/api/settings", json={"project_code": "01"})
    assert response.status_code == 400


def test_both_number_shapes_are_read_from_folder_names(client):
    from app.vault.indexer import project_id_from_dir_name as parse

    assert parse("2026-001-제목") == "2026-001"
    assert parse("2026-소재-001-제목") == "2026-소재-001"
    assert parse("2026-001-2차-시험") == "2026-001"  # 제목이 숫자로 시작해도
    assert parse("알수없는폴더") == "알수없는폴더"


# ── 38-2. 담당자 명부 ─────────────────────────────────

def test_registry_starts_empty_and_accepts_people(client):
    assert client.get("/api/people").json()["people"] == []
    client.put(
        "/api/people",
        json={"people": [{"name": "권경락"}, {"name": "김현우", "employee_id": "12345"}]},
    )
    people = client.get("/api/people").json()["people"]
    assert [p["name"] for p in people] == ["권경락", "김현우"]
    # 사번·계정은 지금 비어 있는 것이 정상이다 — 로그인이 생길 때 채운다.
    assert people[0]["employee_id"] == ""
    assert people[1]["account"] == ""


def test_registry_shows_names_used_but_not_registered(client):
    """명부에 없는데 쓰이고 있는 이름 — 오타이거나, 명부에 넣어야 할 사람이다."""
    client.put("/api/people", json={"people": [{"name": "권경락"}]})
    make(client, title="흔들린 표기", owners=["권 경락", "권경락"])

    data = client.get("/api/people").json()
    assert [p["name"] for p in data["unregistered"]] == ["권 경락"]
    assert [p["used"] for p in data["people"]] == [1]


def test_adding_a_name_on_the_spot(client):
    """화면에서 "명부에 없는 이름입니다 — 추가할까요?" 에 예를 눌렀을 때."""
    client.post("/api/people", json={"name": "새 사람"})
    assert [p["name"] for p in client.get("/api/people").json()["people"]] == ["새 사람"]
    # 두 번 눌러도 겹쳐 쌓이지 않는다.
    client.post("/api/people", json={"name": "새 사람"})
    assert len(client.get("/api/people").json()["people"]) == 1


def test_rename_fixes_the_files_not_just_the_index(client, vault_dir):
    """파일이 원본이므로 파일부터 고친다."""
    project = make(client, title="표기 통일", owners=["권 경락", "김현우"])
    result = client.post("/api/people/rename", json={"old": "권 경락", "new": "권경락"}).json()
    assert result["count"] == 1

    assert client.get(f"/api/projects/{project['id']}").json()["owners"] == ["권경락", "김현우"]
    raw = (vault_dir / "projects" / f"{project['id']}-표기-통일" / "index.md").read_text(
        encoding="utf-8"
    )
    assert "권 경락" not in raw
    assert "권경락" in raw


def test_rename_does_not_leave_a_duplicate(client):
    """한 과제에 두 표기가 함께 있으면 합쳐진다."""
    project = make(client, title="둘 다 있음", owners=["권 경락", "권경락"])
    client.post("/api/people/rename", json={"old": "권 경락", "new": "권경락"})
    assert client.get(f"/api/projects/{project['id']}").json()["owners"] == ["권경락"]


def test_rename_also_updates_the_registry(client):
    client.put("/api/people", json={"people": [{"name": "권 경락", "employee_id": "12345"}]})
    client.post("/api/people/rename", json={"old": "권 경락", "new": "권경락"})
    people = client.get("/api/people").json()["people"]
    assert people[0]["name"] == "권경락"
    assert people[0]["employee_id"] == "12345"  # 사번은 따라간다


def test_rename_rejects_empty_or_identical_names(client):
    assert client.post("/api/people/rename", json={"old": "", "new": "x"}).status_code == 400
    assert client.post("/api/people/rename", json={"old": "x", "new": "x"}).status_code == 400
