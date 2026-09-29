"""지우고 되돌릴 때 — 번호와 접수 연결 (TODO 145 · 146).

지키는 약속:
  * 번호는 한 번 쓰면 다시 쓰지 않는다 — 삭제 보관함에 간 과제·접수의 번호도 센다 (146)
  * 되돌리면 같은 번호가 둘이 되는 경우는 막고 까닭을 말한다 (기존 자료)
  * 다시 읽을 때 같은 번호의 폴더가 둘이면 알린다
  * 과제를 지우면 그 과제로 착수·병합된 접수는 묻지 않고 풀(검토중)로, 흔적은 검토 기록 한 줄 (145)
  * 보관함에서 과제를 되돌리면 접수가 **아직 풀에 있을 때만** 다시 잇는다
  * 그 사이 다시 승격·반려됐으면 잇지 않고 과제 쪽 접수 표지를 뗀다 — 접수 하나에 착수 과제 하나
"""
from __future__ import annotations

import shutil


def _trash_name(client, kind: str, number: str) -> str:
    items = client.get("/api/trash").json()
    items = items["items"] if isinstance(items, dict) else items
    if kind == "project":
        return next(x["trash_name"] for x in items if x["kind"] == "project" and x["project_id"] == number)
    return next(x["trash_name"] for x in items if x["kind"] == kind and x["label"].startswith(number))


def test_deleted_project_number_is_not_reused(client):
    a = client.post("/api/projects", json={"title": "에이"}).json()["id"]
    client.post(f"/api/projects/{a}/archive")
    b = client.post("/api/projects", json={"title": "비"}).json()["id"]
    assert a != b
    assert client.post(f"/api/trash/{_trash_name(client, 'project', a)}/restore").status_code == 200
    assert sorted(p["id"] for p in client.get("/api/projects").json()) == sorted([a, b])


def test_deleted_intake_number_is_not_reused(client):
    a = client.post("/api/intakes", json={"title": "가"}).json()["id"]
    client.post(f"/api/intakes/{a}/archive")
    b = client.post("/api/intakes", json={"title": "나"}).json()["id"]
    assert a != b
    assert client.get("/api/intakes/next-id").json()["id"] not in (a, b)


def test_restore_refuses_duplicate_number_from_old_data(client, vault_dir):
    """이 규칙 전에 이미 같은 번호를 받은 과제가 있으면 되돌리지 않는다 — 한쪽이 목록에서 사라진다."""
    vault = vault_dir
    a = client.post("/api/projects", json={"title": "에이"}).json()["id"]
    client.post(f"/api/projects/{a}/archive")
    name = _trash_name(client, "project", a)
    # 예전 규칙대로 같은 번호의 새 과제가 생긴 상태를 손으로 만든다
    trashed = vault / ".trash" / name
    same = vault / "projects" / f"{a}-비"
    shutil.copytree(trashed, same)
    text = (same / "index.md").read_text(encoding="utf-8").replace("title: 에이", "title: 비")
    (same / "index.md").write_text(text, encoding="utf-8")
    client.post("/api/reindex")
    response = client.post(f"/api/trash/{name}/restore")
    assert response.status_code in (400, 409), response.text
    assert "같은 번호" in response.text


def test_reindex_reports_two_folders_with_one_number(client, vault_dir):
    vault = vault_dir
    a = client.post("/api/projects", json={"title": "에이"}).json()["id"]
    src = next((vault / "projects").iterdir())
    shutil.copytree(src, vault / "projects" / f"{a}-복사본")
    result = client.post("/api/reindex").json()
    assert any("같은 번호" in item["reason"] for item in result["problems"])


def _promoted(client, title="미아 시험"):
    iid = client.post("/api/intakes", json={"title": title}).json()["id"]
    pid = client.post(f"/api/intakes/{iid}/promote", json={"owners": ["권경락"]}).json()["project_id"]
    return iid, pid


def test_deleting_project_returns_intake_to_pool(client):
    iid, pid = _promoted(client)
    client.post(f"/api/projects/{pid}/archive")
    intake = client.get(f"/api/intakes/{iid}").json()
    assert intake["status"] == "reviewing"
    assert intake["project_id"] is None
    assert intake["in_pool"] is True
    assert pid in intake["logs"][0]["body"]
    # 흔적은 판정 줄 하나 — 사람이 쓴 검토 기록 수는 늘지 않는다
    assert intake["log_count"] == 0


def test_deleting_merge_target_returns_intake_to_pool(client):
    pid = client.post("/api/projects", json={"title": "흡수한 과제"}).json()["id"]
    iid = client.post("/api/intakes", json={"title": "같은 요청"}).json()["id"]
    client.post(f"/api/intakes/{iid}/status", json={"status": "merged", "merged_into": pid})
    client.post(f"/api/projects/{pid}/archive")
    assert client.get(f"/api/intakes/{iid}").json()["status"] == "reviewing"
    client.post(f"/api/trash/{_trash_name(client, 'project', pid)}/restore")
    intake = client.get(f"/api/intakes/{iid}").json()
    assert (intake["status"], intake["merged_into"]) == ("merged", pid)


def test_restore_relinks_when_intake_still_in_pool(client):
    iid, pid = _promoted(client)
    client.post(f"/api/projects/{pid}/archive")
    client.post(f"/api/trash/{_trash_name(client, 'project', pid)}/restore")
    intake = client.get(f"/api/intakes/{iid}").json()
    assert (intake["status"], intake["project_id"]) == ("started", pid)
    assert client.get(f"/api/projects/{pid}").json()["intake_id"] == iid


def test_restore_after_repromotion_detaches_old_project(client):
    """① 승격 A → ② A 삭제 → ③ 다시 승격 B → ④ A 되돌림: 접수는 B, A 는 직접 등록."""
    iid, a = _promoted(client)
    client.post(f"/api/projects/{a}/archive")
    b = client.post(f"/api/intakes/{iid}/promote", json={}).json()["project_id"]
    assert b != a
    assert client.post(f"/api/trash/{_trash_name(client, 'project', a)}/restore").status_code == 200
    intake = client.get(f"/api/intakes/{iid}").json()
    assert (intake["status"], intake["project_id"]) == ("started", b)
    assert client.get(f"/api/projects/{a}").json()["intake_id"] is None
    assert client.get(f"/api/projects/{b}").json()["intake_id"] == iid
    assert [p["id"] for p in client.get("/api/projects", params={"from_intake": "yes"}).json()] == [b]
    # 양쪽에 한 줄
    entries = client.get(f"/api/projects/{a}/entries").json()
    assert any("연결을 떼었다" in e["title"] for e in entries)
    assert any("잇지 않음" in log["title"] for log in intake["logs"])


def test_restore_after_rejection_detaches(client):
    iid, pid = _promoted(client)
    client.post(f"/api/projects/{pid}/archive")
    client.post(f"/api/intakes/{iid}/status", json={"status": "rejected", "note": "올해는 안 한다"})
    client.post(f"/api/trash/{_trash_name(client, 'project', pid)}/restore")
    assert client.get(f"/api/intakes/{iid}").json()["status"] == "rejected"
    assert client.get(f"/api/projects/{pid}").json()["intake_id"] is None


def test_orphans_from_before_the_rule_return_to_pool_on_reindex(client, monkeypatch):
    from app.services import intakes

    iid, pid = _promoted(client)
    monkeypatch.setattr(intakes, "detach_from_project", lambda *args, **kwargs: [])  # 예전 동작
    client.post(f"/api/projects/{pid}/archive")
    assert client.get(f"/api/intakes/{iid}").json()["status"] == "started"
    monkeypatch.undo()
    client.post("/api/reindex")
    assert client.get(f"/api/intakes/{iid}").json()["status"] == "reviewing"
