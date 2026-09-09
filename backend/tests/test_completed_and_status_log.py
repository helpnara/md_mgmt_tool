"""완료일과 상태 변경 이력 (TODO 104 · 105) — 나중에 넣으면 그 전 자료가 빈칸으로 남는 둘."""
from __future__ import annotations

from datetime import date


def make(client, title, **extra):
    return client.post("/api/projects", json={"title": title, **extra}).json()


def today() -> str:
    return date.today().isoformat()


# ── 완료일 ───────────────────────────────────────────────────────────────────

def test_finishing_a_project_stamps_today(client):
    project = make(client, "과제")
    assert project["completed_at"] is None
    done = client.patch(f"/api/projects/{project['id']}", json={"status": "done"}).json()
    assert done["completed_at"] == today()


def test_reopening_clears_the_completion_date(client):
    project = make(client, "과제", status="done")
    assert project["completed_at"] == today()
    back = client.patch(f"/api/projects/{project['id']}", json={"status": "in_progress"}).json()
    assert back["completed_at"] is None


def test_a_hand_written_completion_date_wins(client):
    # 지난 과제를 뒤늦게 등록할 때 — 실제 끝난 날을 적을 수 있어야 한다.
    project = make(client, "지난해 과제", status="done", start_date="2025-01-01", completed_at="2025-11-30")
    assert project["completed_at"] == "2025-11-30"
    # 다른 것을 고쳐도 완료일은 그대로다 (updated_at 에 묻히지 않는다).
    again = client.patch(f"/api/projects/{project['id']}", json={"tags": ["a"]}).json()
    assert again["completed_at"] == "2025-11-30"


def test_completion_date_lives_in_the_file(client, vault_dir):
    project = make(client, "과제", status="done")
    text = (vault_dir / "projects" / f"{project['id']}-과제" / "index.md").read_text(encoding="utf-8")
    assert f"completed_at: '{today()}'" in text  # YAML 은 날짜 문자열에 따옴표를 친다


def test_a_bad_completion_date_is_refused(client):
    project = make(client, "과제")
    response = client.patch(f"/api/projects/{project['id']}", json={"status": "done", "completed_at": "어제"})
    assert response.status_code == 400


def test_home_counts_finished_by_completion_year(client):
    # 2025 번호인데 2026 에 끝냈다 — 번호 기준 완료 수에는 안 잡히지만 완료일 기준에는 잡힌다.
    late = make(client, "지난해 시작", start_date="2025-03-01")
    assert late["id"].startswith("2025-")
    client.patch(f"/api/projects/{late['id']}", json={"status": "done", "completed_at": "2026-02-02"})

    team_2026 = client.get("/api/home", params={"year": "2026"}).json()["team"]
    assert team_2026["done"] == 0
    assert team_2026["done_in_year"] == 1
    team_2025 = client.get("/api/home", params={"year": "2025"}).json()["team"]
    assert team_2025["done"] == 1
    assert team_2025["done_in_year"] == 0


def test_the_list_can_filter_by_completion_year(client):
    late = make(client, "지난해 시작", start_date="2025-03-01")
    client.patch(f"/api/projects/{late['id']}", json={"status": "done", "completed_at": "2026-02-02"})
    make(client, "올해 시작 진행중")
    listed = client.get("/api/projects", params={"done_year": "2026"}).json()
    assert [row["id"] for row in listed] == [late["id"]]
    assert client.get("/api/projects", params={"done_year": "2025"}).json() == []


# ── 상태 변경 이력 ───────────────────────────────────────────────────────────

def test_a_status_change_leaves_a_line_in_the_log(client):
    project = make(client, "과제", status="in_progress")
    client.patch(f"/api/projects/{project['id']}", json={"status": "on_hold"})
    entries = client.get(f"/api/projects/{project['id']}/entries").json()
    assert len(entries) == 1
    assert entries[0]["title"] == "(상태) 진행중 → 보류"
    assert entries[0]["tags"] == ["상태변경"]
    assert entries[0]["date"] == today()


def test_no_line_when_the_status_did_not_change(client):
    project = make(client, "과제", status="in_progress")
    client.patch(f"/api/projects/{project['id']}", json={"status": "in_progress", "tags": ["x"]})
    client.patch(f"/api/projects/{project['id']}", json={"title": "이름만"})
    assert client.get(f"/api/projects/{project['id']}/entries").json() == []


def test_the_line_is_a_real_entry_in_the_folder(client, vault_dir):
    project = make(client, "과제", status="in_progress")
    client.patch(f"/api/projects/{project['id']}", json={"status": "done"})
    logs = list((vault_dir / "projects" / f"{project['id']}-과제" / "logs").glob("*.md"))
    assert len(logs) == 1
    text = logs[0].read_text(encoding="utf-8")
    assert "tags:" in text and "상태변경" in text
    assert "진행중" in text and "완료" in text


def test_status_lines_flow_into_the_next_report_draft(client):
    # "이 기간에 보류됐음" 이 다음 보고 초안에 저절로 들어간다 — 이것이 진행일지에 남기는 이유다.
    project = make(client, "과제", status="in_progress")
    client.patch(f"/api/projects/{project['id']}", json={"status": "on_hold"})
    draft = client.post(f"/api/projects/{project['id']}/reports/draft", json={}).json()
    body = client.get(f"/api/reports/{draft['id']}").json()["body"]
    assert "(상태) 진행중 → 보류" in body


def test_each_change_is_its_own_line(client):
    project = make(client, "과제", status="planned")
    for status in ("in_progress", "on_hold", "in_progress", "done"):
        client.patch(f"/api/projects/{project['id']}", json={"status": status})
    titles = [row["title"] for row in client.get(f"/api/projects/{project['id']}/entries").json()]
    assert len(titles) == 4
    assert titles[0].startswith("(상태)")
