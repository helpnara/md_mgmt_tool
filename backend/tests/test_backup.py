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


def test_same_day_backups_collapse_to_one(client, tmp_path):
    """하루에 여러 번 돌려도 그날 한 벌만 남는다 (TODO 119).

    "하루 한 벌" 이라야 개수를 보고 기간을 셀 수 있다. 손으로 여러 번 돌린 날이
    주·월 자리를 차지해 오래된 백업을 밀어내서도 안 된다.
    """
    make(client)
    target = tmp_path / "백업"
    target.mkdir()
    use_folder(client, target)

    for _ in range(5):
        client.post("/api/settings/backup/run")

    files = sorted(target.glob("*.zip"))
    assert len(files) == 1
    # 남는 것은 그날의 **마지막** 백업이다.
    assert files[0].stat().st_size > 0


def test_tiers_cover_months_with_few_files(client, tmp_path):
    """일 7 · 주 4 · 월 6 — 같은 개수로 훨씬 긴 기간을 덮는다 (TODO 119)."""
    target = tmp_path / "백업"
    target.mkdir()
    today = datetime(2026, 9, 16, 3, 0)
    made = []
    for days_ago in range(179, -1, -1):
        stamp = (today - timedelta(days=days_ago)).strftime(backup.STAMP)
        path = target / f"{backup.PREFIX}{stamp}.zip"
        path.write_bytes(b"x")
        made.append(path)

    keeping = backup.keep_set(made, backup.Keep(7, 4, 6))
    assert len(keeping) == 17
    names = sorted(item.name for item in keeping)
    # 반년 전까지 닿는다. 예전 방식(최근 10개)이라면 열흘이 전부였다.
    assert names[0] < f"{backup.PREFIX}20260601"
    assert names[-1].startswith(f"{backup.PREFIX}20260916")
    assert len(backup.keep_set(made, backup.Keep(10, 0, 0))) == 10


def test_files_we_did_not_name_are_never_dropped(client, tmp_path):
    """사람이 이름을 바꿔 둔 백업은 판단하지 않는다 — 지우는 쪽이 조심스러워야 한다."""
    target = tmp_path / "백업"
    target.mkdir()
    mine = target / f"{backup.PREFIX}20260916-0300.zip"
    odd = target / f"{backup.PREFIX}배포전-보관용.zip"
    for item in (mine, odd):
        item.write_bytes(b"x")
    keeping = backup.keep_set([mine, odd], backup.Keep(1, 0, 0))
    assert odd in keeping and mine in keeping


def test_status_counts_every_file_not_just_the_listed_ones(client, tmp_path):
    """총 용량은 **전체 기준**이다 (TODO 119). 예전에는 화면에 세우는 몇 개만 더했다."""
    target = tmp_path / "백업"
    target.mkdir()
    today = datetime(2026, 9, 16, 3, 0)
    for days_ago in range(12):
        stamp = (today - timedelta(days=days_ago)).strftime(backup.STAMP)
        (target / f"{backup.PREFIX}{stamp}.zip").write_bytes(b"x" * 1000)
    use_folder(client, target)

    status = client.get("/api/settings/backup/status").json()
    assert status["count"] == 12
    assert status["total_bytes"] == 12000  # 세우는 줄(5개) 이 아니라 전부
    assert len(status["recent"]) == backup.RECENT_LIMIT
    # 되돌릴 수 있는 범위 — 개수보다 이 날짜가 백업의 뜻이다.
    assert status["oldest"] == "2026-09-05"
    assert status["keep"] == status["keep_daily"] + status["keep_weekly"] + status["keep_monthly"]


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
