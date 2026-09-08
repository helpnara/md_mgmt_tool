"""폴더 고르기 (TODO 97).

백업 폴더를 손으로 치지 않게, 서버가 폴더 목록을 준다. 브라우저는 고른 폴더의
**실제 경로**를 주지 않으므로(보안상 그렇게 만들어져 있다) 이 길밖에 없다.

내주는 것은 **폴더 이름과 경로뿐**이다 — 파일은 세지도 보여 주지도 않는다.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture()
def outside(client, tmp_path):
    """vault 밖의 빈 폴더. `client` 가 tmp_path 안에 vault 를 만들므로 한 칸 판다."""
    folder = tmp_path / "밖"
    folder.mkdir()
    return folder


def test_the_first_place_is_drives_or_home(client):
    data = client.get("/api/folders").json()
    assert data["path"] == ""
    # 처음 자리에서는 더 올라갈 곳이 없다.
    assert data["parent"] is None
    assert len(data["folders"]) > 0
    assert all(item["path"] for item in data["folders"])


def test_only_folders_are_listed(client, outside):
    (outside / "백업").mkdir()
    (outside / "문서").mkdir()
    (outside / "메모.txt").write_text("파일은 목록에 없어야 한다", encoding="utf-8")

    data = client.get("/api/folders", params={"path": str(outside)}).json()
    assert [item["name"] for item in data["folders"]] == ["문서", "백업"]
    assert data["writable"] is True


def test_hidden_folders_are_folded_away(client, outside):
    (outside / "백업").mkdir()
    (outside / ".숨김").mkdir()
    data = client.get("/api/folders", params={"path": str(outside)}).json()
    assert [item["name"] for item in data["folders"]] == ["백업"]


def test_going_up_leads_to_the_parent(client, outside):
    child = outside / "백업" / "과제이력"
    child.mkdir(parents=True)
    data = client.get("/api/folders", params={"path": str(child)}).json()
    assert data["parent"] == str(child.parent)


def test_a_missing_folder_says_so(client, outside):
    response = client.get("/api/folders", params={"path": str(outside / "없는폴더")})
    assert response.status_code == 400
    assert "없습니다" in response.json()["detail"]


def test_a_file_is_not_a_folder(client, outside):
    note = outside / "메모.txt"
    note.write_text("파일", encoding="utf-8")
    response = client.get("/api/folders", params={"path": str(note)})
    assert response.status_code == 400
    assert "폴더가 아니라" in response.json()["detail"]


def test_a_relative_path_is_refused(client):
    response = client.get("/api/folders", params={"path": "백업"})
    assert response.status_code == 400
    assert "전체 경로" in response.json()["detail"]


def test_a_read_only_folder_is_marked(client, outside):
    if os.name == "nt" or os.geteuid() == 0:
        pytest.skip("권한 모드를 바꿔도 root 는 다 쓸 수 있어 이 시험이 뜻을 갖지 못한다")
    locked = outside / "잠긴폴더"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        data = client.get("/api/folders", params={"path": str(locked)}).json()
        # 쓸 수 없는 폴더를 백업 폴더로 고르면 저장할 때 튕긴다. 고르기 전에 알려 준다.
        assert data["writable"] is False
    finally:
        locked.chmod(0o700)


def test_a_folder_can_be_made_right_there(client, outside):
    made = client.post("/api/folders", json={"parent": str(outside), "name": "과제이력 백업"})
    assert made.status_code == 201
    path = made.json()["path"]
    assert (outside / "과제이력 백업").is_dir()
    # 만든 자리가 바로 목록에도 보인다.
    listed = client.get("/api/folders", params={"path": str(outside)}).json()
    assert [item["path"] for item in listed["folders"]] == [path]


def test_making_the_same_name_twice_says_so(client, outside):
    client.post("/api/folders", json={"parent": str(outside), "name": "백업"})
    again = client.post("/api/folders", json={"parent": str(outside), "name": "백업"})
    assert again.status_code == 400
    assert "이미 있는" in again.json()["detail"]


@pytest.mark.parametrize("name", ["..", "../위로", "위\\로", "가:나"])
def test_a_name_cannot_climb_out(client, outside, name):
    # 이름 칸으로 상위 폴더에 손대지 못하게 한다.
    response = client.post("/api/folders", json={"parent": str(outside), "name": name})
    assert response.status_code == 400
    assert list(outside.iterdir()) == []


def test_an_empty_name_says_so(client, outside):
    response = client.post("/api/folders", json={"parent": str(outside), "name": "   "})
    assert response.status_code == 400
    assert "이름을 적어" in response.json()["detail"]
