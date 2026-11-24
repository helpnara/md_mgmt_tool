"""부딪힘은 **그 글(줄) 자체**가 바뀌었을 때만 (TODO 325).

과제의 수정 시각은 일지 · 담당과 역할 · 상태가 바뀌어도 움직인다. 시각으로만 보면 같은 창의 내 저장에 내가 걸렸다 —
완료로 바꾼 뒤 열린 회고 양식이 409, 개요를 고치다 일지를 하나 쓰고 돌아오면 409.
"""
from __future__ import annotations


def make(client):
    client.put("/api/people", json={"people": [{"name": "권경락"}, {"name": "김현우"}]})
    project = client.post("/api/projects", json={"title": "부딪힘 시험", "status": "in_progress",
                                                 "owners": ["권경락", "김현우"], "start_date": "2026-01-05"}).json()
    return client.get(f"/api/projects/{project['id']}").json()


def row_of(project, name):
    return next(row for row in project["contributions"] if row["name"] == name)


def test_completing_then_writing_my_retro_is_not_a_conflict(client):
    opened = make(client)
    mine = row_of(opened, "권경락")
    # 완료로 바꾼다 — 과제의 수정 시각이 바뀐다
    client.patch(f"/api/projects/{opened['id']}", json={"status": "done", "completed_at": "2026-10-10"})
    # 줄의 지문을 함께 보내면 그 줄이 그대로이므로 저장된다
    ok = client.put(f"/api/projects/{opened['id']}/contributions/권경락",
                    json={"did": "한 일", "base_updated_at": opened["updated_at"], "base_rev": mine["rev"]})
    assert ok.status_code == 200, ok.text
    assert row_of(ok.json(), "권경락")["did"] == "한 일"


def test_someone_else_changing_that_row_is_still_a_conflict(client):
    opened = make(client)
    mine = row_of(opened, "권경락")
    client.put(f"/api/projects/{opened['id']}/contributions/권경락", json={"did": "다른 창에서 먼저"})
    late = client.put(f"/api/projects/{opened['id']}/contributions/권경락",
                      json={"did": "나중", "base_updated_at": opened["updated_at"], "base_rev": mine["rev"]})
    assert late.status_code == 409
    # 다른 사람의 줄이 바뀐 것은 내 줄과 상관없다
    other = client.put(f"/api/projects/{opened['id']}/contributions/김현우",
                       json={"did": "김현우 회고", "base_updated_at": opened["updated_at"], "base_rev": row_of(opened, "김현우")["rev"]})
    assert other.status_code == 200, other.text


def test_overview_survives_an_entry_written_meanwhile(client):
    opened = make(client)
    # 개요를 연 뒤 같은 과제에 일지를 쓴다 — 과제의 수정 시각이 바뀐다
    client.post(f"/api/projects/{opened['id']}/entries", json={"title": "그사이 일지", "body": "내용"})
    ok = client.patch(f"/api/projects/{opened['id']}",
                      json={"body": "새 개요", "base_updated_at": opened["updated_at"], "base_body_rev": opened["body_rev"]})
    assert ok.status_code == 200, ok.text
    # 개요 글 자체가 바뀌었으면 409
    late = client.patch(f"/api/projects/{opened['id']}",
                        json={"body": "더 늦은 개요", "base_updated_at": opened["updated_at"], "base_body_rev": opened["body_rev"]})
    assert late.status_code == 409
