"""과제 번호 일괄 변경.

팀 코드를 나중에 정하면 이미 만든 과제(`2026-001`)와 새 과제(`2026-소재-001`)의
번호 형태가 갈린다. 여기서 지키는 것은 셋이다.
  · 연도와 일련번호는 그대로 두고 가운데 코드만 바꾼다
  · 파일(front matter · 폴더명)이 먼저 바뀌고 색인이 그것을 따라온다
  · 번호가 겹치는 일은 없다
"""
from __future__ import annotations

from app.services.renumber import split_id


def make(client, title):
    response = client.post("/api/projects", json={"title": title, "status": "in_progress"})
    assert response.status_code == 201, response.text
    return response.json()


def set_code(client, code):
    assert client.put("/api/settings", json={"project_code": code}).status_code == 200


def test_split_id_reads_both_shapes():
    assert split_id("2026-001") == ("2026", "", "001")
    assert split_id("2026-소재-001") == ("2026", "소재", "001")
    # 규칙에 없는 번호는 건드리지 않기 위해 None 을 돌려준다.
    assert split_id("임시과제") is None
    assert split_id("과제-001") is None


def test_preview_keeps_year_and_sequence(client):
    make(client, "첫 과제")
    make(client, "둘째 과제")

    plan = client.post(
        "/api/settings/project-code/renumber/preview", json={"code": "선강DX개발팀"}
    ).json()
    assert [(item["id"], item["new_id"]) for item in plan["changes"]] == [
        ("2026-001", "2026-선강DX개발팀-001"),
        ("2026-002", "2026-선강DX개발팀-002"),
    ]
    assert plan["changes"][0]["new_dir_name"].startswith("2026-선강DX개발팀-001-")


def test_preview_changes_nothing_on_disk(client):
    make(client, "과제")
    client.post("/api/settings/project-code/renumber/preview", json={"code": "소재"})
    assert [row["id"] for row in client.get("/api/projects").json()] == ["2026-001"]


def test_renumber_rewrites_id_folder_and_index(client, vault_dir):
    project = make(client, "소재 개발")
    client.post(f"/api/projects/{project['id']}/entries", json={"date": "2026-09-01", "body": "진행"})

    result = client.post("/api/settings/project-code/renumber", json={"code": "선강DX개발팀"}).json()
    assert [item["new_id"] for item in result["changed"]] == ["2026-선강DX개발팀-001"]

    # 1) 색인
    rows = client.get("/api/projects").json()
    assert [row["id"] for row in rows] == ["2026-선강DX개발팀-001"]
    # 2) 폴더 이름
    folders = [path.name for path in (vault_dir / "projects").iterdir()]
    assert folders == ["2026-선강DX개발팀-001-소재-개발"]
    # 3) 문서 안의 id — 파일이 원본이므로 여기가 맞아야 한다
    text = (vault_dir / "projects" / folders[0] / "index.md").read_text(encoding="utf-8")
    assert "id: 2026-선강DX개발팀-001" in text
    # 4) 딸린 기록도 새 id 를 따라온다
    assert len(client.get("/api/projects/2026-선강DX개발팀-001/entries").json()) == 1


def test_settings_code_follows_so_the_next_project_matches(client):
    make(client, "과제")
    client.post("/api/settings/project-code/renumber", json={"code": "소재"})

    assert client.get("/api/settings").json()["project_code"] == "소재"
    # 다음에 만드는 과제가 또 어긋나면 일괄 변경을 한 의미가 없다.
    assert make(client, "다음 과제")["id"] == "2026-소재-002"


def test_projects_already_matching_are_left_alone(client):
    set_code(client, "소재")
    make(client, "이미 맞는 과제")

    plan = client.post("/api/settings/project-code/renumber/preview", json={"code": "소재"}).json()
    assert plan["changes"] == []
    assert plan["skipped"][0]["skip"] == "이미 맞습니다."


def test_a_taken_number_is_pushed_to_the_next_free_one(client):
    """예전 번호와 새 코드 번호가 같은 자리에 있으면 겹친다. 겹치게 두지 않는다."""
    set_code(client, "소재")
    make(client, "새 체계 과제")       # 2026-소재-001
    set_code(client, "")
    make(client, "옛 체계 과제")       # 2026-001

    plan = client.post("/api/settings/project-code/renumber/preview", json={"code": "소재"}).json()
    change = plan["changes"][0]
    assert change["id"] == "2026-001"
    assert change["new_id"] == "2026-소재-002"
    # 번호가 밀린 건은 표시해 둔다 — 이미 보고에 적힌 번호일 수 있다.
    assert change["renumbered"] is True

    client.post("/api/settings/project-code/renumber", json={"code": "소재"})
    assert sorted(row["id"] for row in client.get("/api/projects").json()) == [
        "2026-소재-001",
        "2026-소재-002",
    ]


def test_a_code_of_only_digits_is_refused(client):
    make(client, "과제")
    response = client.post("/api/settings/project-code/renumber/preview", json={"code": "12"})
    assert response.status_code == 400
    assert "숫자" in response.json()["detail"]


def test_clearing_the_code_takes_numbers_back_to_the_plain_shape(client):
    set_code(client, "소재")
    make(client, "과제")

    result = client.post("/api/settings/project-code/renumber", json={"code": ""}).json()
    assert [item["new_id"] for item in result["changed"]] == ["2026-001"]


def test_running_twice_changes_nothing_the_second_time(client):
    make(client, "과제")
    client.post("/api/settings/project-code/renumber", json={"code": "소재"})
    again = client.post("/api/settings/project-code/renumber", json={"code": "소재"}).json()
    assert again["changed"] == []


# ── 팀 코드가 폴더 이름으로 안전한가 ─────────────────────────────────────────
#
# 코드는 **그대로 폴더 이름에 들어간다** (2026-소재-001-제목). 과제명은 슬러그로
# 다듬어지지만 코드는 다듬지 않으므로, 여기서 막지 않으면 윈도우에서 폴더를 만들지 못한다.

import pytest


@pytest.mark.parametrize("code", ['소재:개발', '소재*', '소재?', '소재"', '소재<개발', '소재|팀',
                                  '소재/개발', '소재\\개발', '소재 개발', '소재\t개발'])
def test_windows_forbidden_characters_are_refused(client, code):
    response = client.put("/api/settings", json={"project_code": code})
    assert response.status_code == 400, (code, response.text)
    assert "쓸 수 없는 문자" in response.json()["detail"] or "공백" in response.json()["detail"]


def test_a_code_ending_in_a_dot_is_refused(client):
    """윈도우 탐색기가 끝의 점을 잘라 내, 폴더 이름과 설정이 어긋난다."""
    assert client.put("/api/settings", json={"project_code": "소재."}).status_code == 400
    assert client.put("/api/settings", json={"project_code": ".."}).status_code == 400


def test_a_very_long_code_is_refused(client):
    """폴더 이름이 길어지면 윈도우 260자 경로 제한에 걸린다."""
    assert client.put("/api/settings", json={"project_code": "부" * 40}).status_code == 400
    assert client.put("/api/settings", json={"project_code": "부" * 20}).status_code == 200


def test_ordinary_codes_still_pass(client):
    for code in ["소재", "선강DX개발팀", "R&D", "소재-개발", "Team_1", "소재.개발"]:
        assert client.put("/api/settings", json={"project_code": code}).status_code == 200, code


def test_the_renumber_preview_refuses_a_bad_code_too(client):
    """저장은 막아 놓고 일괄 변경만 뚫리면 소용이 없다."""
    client.post("/api/projects", json={"title": "과제"})
    response = client.post("/api/settings/project-code/renumber/preview", json={"code": "소재:개발"})
    assert response.status_code == 400
    response = client.post("/api/settings/project-code/renumber", json={"code": "소재*"})
    assert response.status_code == 400


# ── 보관함 과제도 함께 바꾼다 (TODO 60) ──────────────────────────────────────
#
# 보관함 항목은 색인에 없어 번호 변경에서 빠졌다. 그대로 두면 되돌렸을 때 옛 번호로
# 살아나, 목록에 두 형태가 섞여 일괄 변경을 한 의미가 사라진다.
# 2026-09-04 사용자가 "(나) 함께 바꾼다" 로 결정.

def test_a_trashed_project_is_renumbered_too(client):
    trashed = make(client, "보관할 과제")
    make(client, "남길 과제")
    assert client.post(f"/api/projects/{trashed['id']}/archive").status_code in (200, 204)

    plan = client.post("/api/settings/project-code/renumber/preview", json={"code": "소재"}).json()
    assert [(item["id"], item["new_id"]) for item in plan["trashed"]] == [
        ("2026-001", "2026-소재-001")
    ]

    result = client.post("/api/settings/project-code/renumber", json={"code": "소재"}).json()
    assert [item["new_id"] for item in result["trashed"]] == ["2026-소재-001"]


def test_restoring_after_a_renumber_comes_back_with_the_new_number(client):
    """되돌린 과제만 옛 번호로 남으면 목록에 두 형태가 섞인다."""
    trashed = make(client, "보관할 과제")
    make(client, "남길 과제")
    client.post(f"/api/projects/{trashed['id']}/archive")
    client.post("/api/settings/project-code/renumber", json={"code": "소재"})

    name = client.get("/api/trash").json()[0]["trash_name"]
    assert client.post(f"/api/trash/{name}/restore").status_code == 200

    ids = sorted(row["id"] for row in client.get("/api/projects").json())
    assert ids == ["2026-소재-001", "2026-소재-002"]


def test_a_trashed_number_is_not_handed_to_someone_else(client):
    """보관함 과제가 쓰고 있는 번호를 다른 과제에 주면, 되돌릴 때 폴더가 서로를 덮는다."""
    trashed = make(client, "보관할 과제")   # 2026-001
    client.post(f"/api/projects/{trashed['id']}/archive")
    set_code(client, "소재")
    make(client, "새 과제")                 # 2026-소재-001 — 보관함 것과 같은 번호가 된다
    set_code(client, "")

    plan = client.post("/api/settings/project-code/renumber/preview", json={"code": "소재"}).json()
    # 보관함의 2026-001 은 이미 쓰이고 있는 2026-소재-001 을 피해 뒤로 밀려야 한다.
    assert plan["trashed"] == [] or plan["trashed"][0]["new_id"] != "2026-소재-001"


def test_the_trash_record_points_at_the_new_folder(client, vault_dir):
    """폴더 이름만 바꾸고 되돌아갈 자리를 안 고치면, 되돌린 뒤 둘이 어긋난다."""
    trashed = make(client, "보관할 과제")
    client.post(f"/api/projects/{trashed['id']}/archive")
    result = client.post("/api/settings/project-code/renumber", json={"code": "소재"}).json()
    assert result["trash_paths_updated"] >= 1

    manifest = (vault_dir / ".trash" / "manifest.jsonl").read_text(encoding="utf-8")
    assert "2026-소재-001" in manifest


def test_a_project_with_no_index_file_is_skipped_quietly(client, vault_dir):
    """보관함에는 진행일지·보고만 들어 있는 항목도 있다. 과제가 아닌 것은 건드리지 않는다."""
    make(client, "살아 있는 과제")
    stray = vault_dir / ".trash" / "보고-2026-09-01-20260901120000"
    stray.mkdir(parents=True, exist_ok=True)
    (stray / "report.md").write_text("---\ntitle: 보고\n---\n\n내용\n", encoding="utf-8")

    result = client.post("/api/settings/project-code/renumber", json={"code": "소재"}).json()
    assert result["trashed"] == []
    assert (stray / "report.md").exists()
