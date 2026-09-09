"""보고 뒤에 받은 지시사항 (TODO 107).

보고를 하면 지시나 질문이 돌아오는데, 확정된 보고는 잠겨 있어 적을 자리가 없었다.
그리고 다음 보고 때 그 지시에 답했는지는 팀장 머릿속에만 있었다.
"""
from __future__ import annotations

from datetime import date


def make(client, title, **extra):
    return client.post("/api/projects", json={"title": title, **extra}).json()


def frozen_report(client, project_id, report_date="2026-08-25"):
    draft = client.post(f"/api/projects/{project_id}/reports/draft", json={"report_date": report_date}).json()
    client.post(f"/api/reports/{draft['id']}/freeze")
    return draft["id"]


def test_feedback_can_be_written_on_a_frozen_report(client):
    project = make(client, "과제")
    rid = frozen_report(client, project["id"])
    # 본문은 잠겨 있다.
    assert client.patch(f"/api/reports/{rid}", json={"body": "고침"}).status_code == 409
    # 지시사항은 쓸 수 있다.
    saved = client.patch(f"/api/reports/{rid}", json={"feedback": "원가 다시 보고"}).json()
    assert saved["feedback"] == "원가 다시 보고"
    assert saved["feedback_done"] is None
    assert saved["frozen"] is True


def test_feedback_is_kept_in_the_file(client, vault_dir):
    project = make(client, "과제")
    rid = frozen_report(client, project["id"])
    client.patch(f"/api/reports/{rid}", json={"feedback": "협력사 일정 확인"})
    report = client.get(f"/api/reports/{rid}").json()
    text = (vault_dir / "projects" / f"{project['id']}-과제" / report["rel_path"]).read_text(encoding="utf-8")
    assert "feedback: 협력사 일정 확인" in text


def test_the_project_lists_unanswered_feedback(client):
    project = make(client, "과제")
    rid = frozen_report(client, project["id"])
    assert client.get(f"/api/projects/{project['id']}").json()["open_feedback"] == []
    client.patch(f"/api/reports/{rid}", json={"feedback": "원가 다시 보고"})
    pending = client.get(f"/api/projects/{project['id']}").json()["open_feedback"]
    assert [item["feedback"] for item in pending] == ["원가 다시 보고"]
    assert pending[0]["id"] == rid


def test_the_next_draft_starts_with_the_open_feedback(client):
    project = make(client, "과제")
    rid = frozen_report(client, project["id"], "2026-08-25")
    client.patch(f"/api/reports/{rid}", json={"feedback": "원가 다시 보고"})

    nxt = client.post(f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-09-01"}).json()
    body = client.get(f"/api/reports/{nxt['id']}").json()["body"]
    assert body.startswith("## 지난 보고 지시사항")
    assert "2026-08-25" in body and "원가 다시 보고" in body
    # 그 뒤에 여느 초안과 같은 뼈대가 이어진다.
    assert "## 보고 요약" in body


def test_marking_done_takes_it_out_of_the_next_draft(client):
    project = make(client, "과제")
    rid = frozen_report(client, project["id"], "2026-08-25")
    client.patch(f"/api/reports/{rid}", json={"feedback": "원가 다시 보고"})
    done = client.post(f"/api/reports/{rid}/feedback-done", json={"done": True}).json()
    assert done["feedback_done"] == date.today().isoformat()
    assert client.get(f"/api/projects/{project['id']}").json()["open_feedback"] == []

    nxt = client.post(f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-09-01"}).json()
    assert "지난 보고 지시사항" not in client.get(f"/api/reports/{nxt['id']}").json()["body"]

    # 되돌릴 수 있다 — 답한 줄 알았는데 아니었을 때.
    back = client.post(f"/api/reports/{rid}/feedback-done", json={"done": False}).json()
    assert back["feedback_done"] is None


def test_history_can_filter_to_unanswered_feedback(client):
    project = make(client, "과제")
    a = frozen_report(client, project["id"], "2026-08-11")
    b = frozen_report(client, project["id"], "2026-08-18")
    frozen_report(client, project["id"], "2026-08-25")
    client.patch(f"/api/reports/{a}", json={"feedback": "첫 지시"})
    client.patch(f"/api/reports/{b}", json={"feedback": "둘째 지시"})
    client.post(f"/api/reports/{b}/feedback-done", json={"done": True})

    ids = [row["id"] for row in client.get("/api/reports", params={"feedback": "open"}).json()]
    assert ids == [a]


def test_a_draft_with_feedback_text_is_not_an_open_instruction(client):
    # 초안에 적어 둔 것은 아직 보고한 것이 아니다 — 확정된 보고의 지시만 센다.
    project = make(client, "과제")
    draft = client.post(f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-08-25"}).json()
    client.patch(f"/api/reports/{draft['id']}", json={"feedback": "아직 초안"})
    assert client.get(f"/api/projects/{project['id']}").json()["open_feedback"] == []


def test_several_open_instructions_all_come_along_oldest_first(client):
    project = make(client, "과제")
    a = frozen_report(client, project["id"], "2026-08-11")
    b = frozen_report(client, project["id"], "2026-08-18")
    client.patch(f"/api/reports/{b}", json={"feedback": "둘째"})
    client.patch(f"/api/reports/{a}", json={"feedback": "첫째"})
    nxt = client.post(f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-09-01"}).json()
    body = client.get(f"/api/reports/{nxt['id']}").json()["body"]
    assert body.index("첫째") < body.index("둘째")
