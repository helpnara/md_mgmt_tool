"""이전 버전 보관 — 안쪽 안전망 (TODO 37-1).

`.trash` 는 **지웠을 때**를 막아 준다. 더 자주 나는 사고는 **잘못 고쳐 저장한 것**이고,
지금까지는 그걸 되돌릴 방법이 없었다. 여기서 지키는 것은 넷이다.
  · 덮어쓰기 전 내용이 남는다
  · 남기다 실패해도 저장 자체는 막지 않는다
  · 되돌리기도 하나의 저장이라, 되돌린 것을 다시 되돌릴 수 있다
  · 안전망 자신이 무한정 자라지 않는다
"""
from __future__ import annotations

from app.vault import versions


def make(client, title="소재 개발"):
    response = client.post("/api/projects", json={"title": title, "status": "in_progress"})
    assert response.status_code == 201, response.text
    # 만들기 응답에는 폴더 이름이 없다. 버전 경로를 만들려면 필요하다.
    return client.get(f"/api/projects/{response.json()['id']}").json()


def entry(client, project_id, date="2026-09-01", body="첫 내용"):
    response = client.post(f"/api/projects/{project_id}/entries",
                           json={"date": date, "title": "시험", "body": body})
    assert response.status_code == 201, response.text
    return response.json()


def entry_path(project, item):
    return f"projects/{project['dir_name']}/{item['rel_path']}"


def versions_of(client, path):
    return client.get("/api/versions", params={"path": path}).json()["items"]


def test_a_new_document_has_nothing_to_keep(client):
    project = make(client)
    item = entry(client, project["id"])
    assert versions_of(client, entry_path(project, item)) == []


def test_editing_keeps_what_was_there_before(client):
    project = make(client)
    item = entry(client, project["id"], body="처음 쓴 내용")
    client.patch(f"/api/entries/{item['id']}", json={"body": "고쳐 쓴 내용"})

    path = entry_path(project, item)
    saved = versions_of(client, path)
    assert len(saved) == 1
    text = client.get("/api/versions/content",
                      params={"path": path, "stamp": saved[0]["stamp"]}).json()["text"]
    assert "처음 쓴 내용" in text
    assert "고쳐 쓴 내용" not in text


def test_saving_the_same_thing_twice_does_not_pile_up(client):
    """저장 단추를 두 번 눌렀다고 버전이 늘 이유는 없다."""
    project = make(client)
    item = entry(client, project["id"], body="같은 내용")
    client.patch(f"/api/entries/{item['id']}", json={"body": "바꾼 내용"})
    before = len(versions_of(client, entry_path(project, item)))
    client.patch(f"/api/entries/{item['id']}", json={"body": "바꾼 내용"})
    assert len(versions_of(client, entry_path(project, item))) == before


def test_restoring_puts_the_old_text_back(client):
    project = make(client)
    item = entry(client, project["id"], body="원래 내용")
    client.patch(f"/api/entries/{item['id']}", json={"body": "실수로 지운 내용"})

    path = entry_path(project, item)
    stamp = versions_of(client, path)[0]["stamp"]
    response = client.post("/api/versions/restore", json={"path": path, "stamp": stamp})
    assert response.status_code == 200, response.text

    # 파일이 원본이므로 색인도 따라와야 한다.
    entries = client.get(f"/api/projects/{project['id']}/entries").json()
    assert "원래 내용" in entries[0]["body"]


def test_restoring_is_itself_undoable(client):
    """되돌린 것이 잘못이었어도 다시 되돌릴 수 있어야 한다."""
    project = make(client)
    item = entry(client, project["id"], body="A")
    client.patch(f"/api/entries/{item['id']}", json={"body": "B"})
    path = entry_path(project, item)

    client.post("/api/versions/restore", json={"path": path, "stamp": versions_of(client, path)[0]["stamp"]})
    saved = versions_of(client, path)
    assert len(saved) == 2  # A(고칠 때) + B(되돌릴 때)

    # 가장 새 버전이 B 여야 한다 — 되돌리기 직전의 내용.
    text = client.get("/api/versions/content",
                      params={"path": path, "stamp": saved[0]["stamp"]}).json()["text"]
    assert "B" in text


def test_the_overview_says_how_much_room_it_uses(client):
    project = make(client)
    item = entry(client, project["id"], body="처음")
    client.patch(f"/api/entries/{item['id']}", json={"body": "나중"})

    data = client.get("/api/versions/overview").json()
    assert data["versions"] == 1 and data["documents"] == 1
    assert data["total_bytes"] > 0
    assert data["keep_days"] == versions.DEFAULT_KEEP_DAYS


def test_the_overview_and_index_folders_are_never_kept(client):
    """색인·기록·보관함까지 버전을 남기면 끝이 없다."""
    make(client)
    client.put("/api/settings", json={"project_code": "12"})  # 오류 기록을 만든다
    data = client.get("/api/versions/overview").json()
    assert data["versions"] == 0


def test_the_project_overview_is_kept_too(client):
    """진행일지뿐 아니라 과제 개요(index.md)도 지켜져야 한다."""
    project = make(client)
    client.patch(f"/api/projects/{project['id']}", json={"body": "## 배경\n\n바꾼 개요\n"})
    saved = versions_of(client, f"projects/{project['dir_name']}/index.md")
    assert len(saved) == 1


def test_a_report_is_kept_too(client):
    project = make(client)
    report = client.post(f"/api/projects/{project['id']}/reports/draft",
                         json={"report_date": "2026-09-08"}).json()
    client.patch(f"/api/reports/{report['id']}", json={"body": "## 보고 요약\n\n고친 보고\n"})
    saved = versions_of(client, f"projects/{project['dir_name']}/{report['rel_path']}")
    assert len(saved) >= 1


def test_a_stamp_pointing_outside_the_folder_is_refused(client):
    project = make(client)
    item = entry(client, project["id"])
    path = entry_path(project, item)
    for bad in ("../../etc/passwd", "..", "a/b"):
        response = client.get("/api/versions/content", params={"path": path, "stamp": bad})
        assert response.status_code == 404, bad
        response = client.post("/api/versions/restore", json={"path": path, "stamp": bad})
        assert response.status_code in (400, 404), bad


def test_a_path_outside_the_vault_is_refused(client):
    response = client.post("/api/versions/restore",
                           json={"path": "../../etc/passwd", "stamp": "2026-01-01_000000"})
    assert response.status_code in (400, 404)


def test_a_missing_version_says_why(client):
    project = make(client)
    item = entry(client, project["id"])
    response = client.get("/api/versions/content",
                          params={"path": entry_path(project, item), "stamp": "2020-01-01_000000"})
    assert response.status_code == 404
    assert "보관 기간" in response.json()["detail"]


def test_old_versions_are_dropped(client, vault_dir, monkeypatch):
    project = make(client)
    item = entry(client, project["id"], body="처음")
    client.patch(f"/api/entries/{item['id']}", json={"body": "나중"})

    path = entry_path(project, item)
    bucket = vault_dir / ".versions" / path
    stale = bucket / "2020-01-01_000000.md"
    stale.write_text("아주 오래된 것", encoding="utf-8")
    assert len(versions_of(client, path)) == 2

    client.patch(f"/api/entries/{item['id']}", json={"body": "또 나중"})  # 저장하면 정리도 함께
    assert not stale.exists()


def test_a_document_keeps_at_most_a_bounded_number(client, vault_dir, monkeypatch):
    """같은 문서를 하루에 수십 번 고쳐도 폴더가 무한정 늘면 안 된다."""
    monkeypatch.setattr(versions, "MAX_PER_DOCUMENT", 3)
    project = make(client)
    item = entry(client, project["id"], body="0")
    for n in range(6):
        client.patch(f"/api/entries/{item['id']}", json={"body": f"내용 {n}"})

    assert len(versions_of(client, entry_path(project, item))) <= 3


def test_a_disk_failure_while_keeping_does_not_block_the_save(client, monkeypatch):
    """안전망을 만들다가 본 작업이 멈추면 본말이 뒤바뀐다.

    보관본을 쓰는 순간 디스크가 막힌 상황을 흉내 낸다.
    """
    project = make(client)
    item = entry(client, project["id"], body="처음")

    real_write = versions.Path.write_text

    def explode(self, *args, **kwargs):
        if ".versions" in str(self):
            raise OSError("디스크 없음")
        return real_write(self, *args, **kwargs)

    monkeypatch.setattr(versions.Path, "write_text", explode)
    response = client.patch(f"/api/entries/{item['id']}", json={"body": "그래도 저장된다"})
    assert response.status_code == 200, response.text
    assert "그래도 저장된다" in client.get(f"/api/entries/{item['id']}").json()["body"]


def test_even_an_unexpected_failure_in_keep_does_not_block_the_save(client, monkeypatch):
    """keep 안이 나중에 바뀌어 다른 예외가 나더라도 저장만은 되어야 한다."""
    project = make(client)
    item = entry(client, project["id"], body="처음")

    def explode(*args, **kwargs):
        raise RuntimeError("안전망이 고장 났다")

    monkeypatch.setattr(versions, "keep", explode)
    response = client.patch(f"/api/entries/{item['id']}", json={"body": "그래도 저장된다"})
    assert response.status_code == 200, response.text


def test_versions_saved_in_the_same_second_can_be_told_apart(client, vault_dir):
    """시각만 보이면 목록에서 똑같은 줄이 여러 개로 보여 어느 것을 고를지 알 수 없다."""
    project = make(client)
    item = entry(client, project["id"], body="처음")
    path = entry_path(project, item)
    bucket = vault_dir / ".versions" / path
    bucket.mkdir(parents=True, exist_ok=True)
    for name in ("2026-09-04_013455.md", "2026-09-04_013455-2.md", "2026-09-04_013455-3.md"):
        (bucket / name).write_text(f"내용 {name}", encoding="utf-8")

    labels = [row["saved_at"] for row in versions_of(client, path)]
    assert len(set(labels)) == 3, labels
    assert labels[-1] == "2026-09-04 01:34:55"  # 가장 오래된 것은 번호 없이
    assert "(3)" in labels[0]  # 가장 새 것


def test_the_list_is_newest_first(client):
    project = make(client)
    item = entry(client, project["id"], body="1")
    path = entry_path(project, item)
    for body in ("2", "3"):
        client.patch(f"/api/entries/{item['id']}", json={"body": body})

    items = versions_of(client, path)
    assert len(items) == 2
    # 새 것이 위 — 되돌릴 때 대개 "방금 전"을 찾는다.
    newest = client.get("/api/versions/content",
                        params={"path": path, "stamp": items[0]["stamp"]}).json()["text"]
    assert "2" in newest
