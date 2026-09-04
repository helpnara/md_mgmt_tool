"""자동 백업 — 바깥쪽 안전망 (T21).

`.versions` 는 잘못 고쳤을 때를 막아 주지만 **vault 안에 있다.** PC가 고장 나거나
폴더가 통째로 사라지면 함께 없어진다. 그래서 밖으로 한 벌을 내보내는 길이 필요하다.

여기서 지키는 것은 넷이다.
  · 정한 폴더에 실제로 파일이 생긴다
  · 백업이 다음 백업에 담기지 않는다 (눈덩이 방지)
  · 오래된 것부터 버리되 최근 것은 남는다
  · 백업이 실패해도 프로그램은 멈추지 않는다
"""
from __future__ import annotations

import zipfile
from datetime import datetime, timedelta

from app.services import backup


def make(client, title="소재 개발"):
    response = client.post("/api/projects", json={"title": title, "status": "in_progress"})
    assert response.status_code == 201, response.text
    return response.json()


def use_folder(client, path):
    return client.put("/api/settings", json={"backup_dir": str(path)})


def test_backup_is_off_until_a_folder_is_chosen(client):
    data = client.get("/api/settings/backup/status").json()
    assert data["enabled"] is False and data["directory"] == ""
    assert client.post("/api/settings/backup/run").status_code == 400


def test_a_backup_lands_in_the_chosen_folder(client, tmp_path):
    make(client, "리튬전지 수명평가")
    target = tmp_path / "백업"
    target.mkdir()
    assert use_folder(client, target).status_code == 200

    result = client.post("/api/settings/backup/run").json()
    files = list(target.glob("*.zip"))
    assert len(files) == 1 and files[0].name == result["file"]

    # 실제로 자료가 들어 있어야 한다 — 빈 zip 은 백업이 아니다.
    with zipfile.ZipFile(files[0]) as archive:
        names = archive.namelist()
    assert any("리튬전지" in name for name in names), names
    assert any(name.endswith("index.md") for name in names)


def test_the_index_and_trash_are_left_out(client, tmp_path):
    """다시 만들 수 있는 것과 버린 것까지 담으면 백업만 무거워진다."""
    project = make(client)
    client.post(f"/api/projects/{project['id']}/archive")
    target = tmp_path / "백업"
    target.mkdir()
    use_folder(client, target)
    client.post("/api/settings/backup/run")

    with zipfile.ZipFile(next(target.glob("*.zip"))) as archive:
        names = archive.namelist()
    assert not any(name.startswith(".index/") for name in names)
    assert not any(name.startswith(".trash/") for name in names)


def test_a_folder_inside_the_vault_is_refused(client, vault_dir):
    """백업이 다음 백업에 담기면 눈덩이처럼 커진다."""
    inside = vault_dir / "백업"
    inside.mkdir(parents=True, exist_ok=True)
    response = use_folder(client, inside)
    assert response.status_code == 400
    assert "데이터 폴더 안" in response.json()["detail"]
    assert use_folder(client, vault_dir).status_code == 400


def test_a_missing_folder_says_so(client, tmp_path):
    response = use_folder(client, tmp_path / "없는폴더")
    assert response.status_code == 400
    assert "없습니다" in response.json()["detail"]


def test_a_relative_path_is_refused(client):
    response = client.put("/api/settings", json={"backup_dir": "백업"})
    assert response.status_code == 400
    assert "전체 경로" in response.json()["detail"]


def test_clearing_the_folder_turns_it_off(client, tmp_path):
    target = tmp_path / "백업"
    target.mkdir()
    use_folder(client, target)
    assert client.put("/api/settings", json={"backup_dir": ""}).status_code == 200
    assert client.get("/api/settings/backup/status").json()["enabled"] is False


def test_old_backups_are_dropped_newest_kept(client, tmp_path):
    make(client)
    target = tmp_path / "백업"
    target.mkdir()
    use_folder(client, target)
    client.put("/api/settings", json={"backup_keep": 3})

    for _ in range(5):
        client.post("/api/settings/backup/run")

    files = sorted(target.glob("*.zip"))
    assert len(files) == 3
    # 최근 것이 남아야 한다 — 오래된 것을 남기면 쓸모가 없다.
    newest = max(files, key=lambda item: item.stat().st_mtime)
    assert newest in files


def test_other_files_in_the_folder_are_not_touched(client, tmp_path):
    """공유 폴더를 백업 위치로 잡을 수 있다. 남의 파일을 지우면 안 된다."""
    make(client)
    target = tmp_path / "백업"
    target.mkdir()
    (target / "회의록.docx").write_text("남의 파일", encoding="utf-8")
    use_folder(client, target)
    client.put("/api/settings", json={"backup_keep": 1})
    for _ in range(3):
        client.post("/api/settings/backup/run")

    assert (target / "회의록.docx").exists()


def test_it_knows_when_the_next_one_is_due(client, tmp_path):
    make(client)
    target = tmp_path / "백업"
    target.mkdir()
    use_folder(client, target)

    assert backup.due() is True  # 한 번도 안 했다
    client.post("/api/settings/backup/run")
    assert backup.due() is False
    # 주기가 지나면 다시 때가 된다.
    assert backup.due(datetime.now() + timedelta(hours=25)) is True


def test_an_unreachable_folder_does_not_crash_the_loop(client, tmp_path):
    """네트워크 드라이브가 끊긴 상황. 프로그램이 멈추면 안 된다."""
    make(client)
    target = tmp_path / "백업"
    target.mkdir()
    use_folder(client, target)
    target.rmdir()  # 드라이브가 사라졌다

    from app import deps

    assert backup.maybe_run(deps._conn) is None  # 조용히 넘어간다
    response = client.post("/api/settings/backup/run")
    assert response.status_code == 400
    assert "찾을 수 없습니다" in response.json()["detail"]
    # 무슨 일이 있었는지는 남아야 한다.
    assert client.get("/api/settings/backup/status").json()["last"]["ok"] is False


def test_the_status_shows_what_is_there(client, tmp_path):
    make(client)
    target = tmp_path / "백업"
    target.mkdir()
    use_folder(client, target)
    client.post("/api/settings/backup/run")

    data = client.get("/api/settings/backup/status").json()
    assert data["enabled"] and data["reachable"] and data["count"] == 1
    assert data["total_bytes"] > 0
    assert data["last"]["ok"] is True
    assert len(data["recent"]) == 1 and data["recent"][0]["name"].startswith("과제이력-백업-")


def test_the_keep_count_must_make_sense(client):
    for bad in (0, -1, "많이", 1000):
        assert client.put("/api/settings", json={"backup_keep": bad}).status_code in (400, 422), bad
    assert client.put("/api/settings", json={"backup_keep": 5}).status_code == 200
