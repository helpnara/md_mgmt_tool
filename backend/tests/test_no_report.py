"""별도 보고가 필요 없는 과제 (TODO 80).

단순 현황 관리를 과제로 세우는 경우가 있다. 그런 과제가 매주 보고 대상 후보에 서면
**눈으로 걸러 내는 일이 매주 생긴다.** 그것이 이 칸을 만든 이유다.

빼는 것은 **후보 목록에서뿐**이다 — 손으로 보고를 남기는 길은 그대로 열려 있다.
"""
from __future__ import annotations


def _make(client, title, **kwargs):
    payload = {"title": title, "status": "in_progress"}
    payload.update(kwargs)
    response = client.post("/api/projects", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_a_no_report_project_is_left_out_of_the_candidates(client):
    _make(client, "보고할 과제", start_date="2026-01-02")
    quiet = _make(client, "현황만 보는 과제", start_date="2026-01-02", no_report=True)

    items = client.get("/api/report-candidates").json()["items"]
    assert [item["title"] for item in items] == ["보고할 과제"]
    assert quiet["no_report"] is True


def test_the_flag_survives_the_markdown_file(client, vault_dir):
    """파일이 진실의 원천이다. 색인을 지워도 md 에서 되살아나야 한다."""
    project = _make(client, "현황 과제", no_report=True)
    raw = (vault_dir / "projects" / f"{project['id']}-현황-과제" / "index.md").read_text(
        encoding="utf-8"
    )
    assert "no_report: true" in raw

    client.post("/api/reindex")
    assert client.get(f"/api/projects/{project['id']}").json()["no_report"] is True


def test_the_flag_can_be_turned_on_and_off_later(client):
    project = _make(client, "나중에 정한 과제", start_date="2026-01-02")
    assert len(client.get("/api/report-candidates").json()["items"]) == 1

    client.patch(f"/api/projects/{project['id']}", json={"no_report": True})
    assert client.get("/api/report-candidates").json()["items"] == []

    client.patch(f"/api/projects/{project['id']}", json={"no_report": False})
    assert len(client.get("/api/report-candidates").json()["items"]) == 1


def test_a_report_can_still_be_written_by_hand(client):
    """후보에서 빼는 것뿐이다. 정말 한 번 보고할 일이 생기면 막지 않는다."""
    project = _make(client, "가끔은 보고하는 과제", no_report=True)

    draft = client.post(
        f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-09-08"}
    )
    assert draft.status_code == 201
    assert client.get(f"/api/projects/{project['id']}/reports").json()


def test_hand_written_text_in_the_file_is_read_as_a_flag(client, vault_dir):
    """외부 편집기로 `no_report: 예` 처럼 적어도 뜻대로 읽는다."""
    project = _make(client, "손으로 고친 과제", start_date="2026-01-02")
    path = vault_dir / "projects" / f"{project['id']}-손으로-고친-과제" / "index.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("no_report: false", "no_report: 예"),
        encoding="utf-8",
    )
    client.post("/api/reindex")

    assert client.get(f"/api/projects/{project['id']}").json()["no_report"] is True
    assert client.get("/api/report-candidates").json()["items"] == []
