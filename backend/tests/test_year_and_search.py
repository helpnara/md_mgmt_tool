"""연도 거르기(TODO 67)와 검색 상한(TODO 66).

오래 쓰면 드러나는 두 가지다.
  · 해가 바뀌면 지난해 과제가 계속 섞인다
  · 흔한 낱말로 찾으면 결과가 조용히 잘려, 그게 전부인 줄 알게 된다
"""
from __future__ import annotations

from app.services import search as search_svc


def make(client, title, **kwargs):
    payload = {"title": title, "status": "in_progress"}
    payload.update(kwargs)
    response = client.post("/api/projects", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def with_id(client, project_id, title, status="in_progress"):
    """과제 번호를 직접 정해 만든다 (지난 연도 자료를 흉내 내려고)."""
    from app.config import get_settings
    from app.vault import markdown as md
    from app.vault import paths

    settings = get_settings()
    directory = settings.projects_dir / paths.project_dir_name(project_id, title)
    (directory / "logs").mkdir(parents=True, exist_ok=True)
    md.save(directory / "index.md", md.MarkdownDoc(
        {"id": project_id, "title": title, "status": status, "created_at": f"{project_id[:4]}-03-01"},
        "## 배경\n\n지난해 과제\n",
    ))
    client.post("/api/reindex")
    return project_id


# ── 연도 거르기 (TODO 67) ────────────────────────────────────────────────────

def test_a_year_keeps_only_that_years_projects(client):
    make(client, "올해 과제")                       # 2026-001
    with_id(client, "2025-007", "지난해 과제")
    with_id(client, "2024-003", "재작년 과제")

    listed = lambda **q: [row["title"] for row in client.get("/api/projects", params=q).json()]
    assert listed(year="2026") == ["올해 과제"]
    assert listed(year="2025") == ["지난해 과제"]
    assert sorted(listed()) == ["올해 과제", "재작년 과제", "지난해 과제"]


def test_the_year_comes_from_the_project_number(client):
    """시작일이 아니라 번호의 연도를 쓴다 — 번호는 만들 때 정해져 흔들리지 않는다."""
    make(client, "2026 번호인데 시작일은 작년", start_date="2025-01-05")
    assert len(client.get("/api/projects", params={"year": "2026"}).json()) == 1
    assert client.get("/api/projects", params={"year": "2025"}).json() == []


def test_the_dashboard_follows_the_same_year(client):
    """수와 목록이 어긋나면 'N건'을 눌렀을 때 다른 수가 나온다 (DESIGN 5.8)."""
    make(client, "올해 진행", status="in_progress")
    make(client, "올해 검토", status="reviewing")
    with_id(client, "2025-001", "지난해 진행", status="in_progress")

    data = client.get("/api/dashboard", params={"year": "2026"}).json()
    assert data["total"] == 2
    for item in data["statuses"]:
        listed = client.get("/api/projects", params={"status": item["key"], "year": "2026"}).json()
        assert len(listed) == item["count"], item


def test_the_dashboard_owner_counts_follow_the_year(client):
    make(client, "올해 과제", owners=["권경락"])
    with_id(client, "2025-001", "지난해 과제")

    owners = client.get("/api/dashboard", params={"year": "2026"}).json()["owners"]
    assert [item["key"] for item in owners] == ["권경락"]


def test_it_says_how_many_older_projects_are_still_running(client):
    """'작년 과제인데 아직 하고 있다' 는 흔하다. 숨었다는 사실은 알려 줘야 한다."""
    make(client, "올해 과제")
    with_id(client, "2025-001", "지난해에 시작해 아직 하는 과제", status="in_progress")
    with_id(client, "2025-002", "지난해에 끝난 과제", status="done")

    data = client.get("/api/dashboard", params={"year": "2026"}).json()
    assert data["other_year_active"] == 1  # 끝난 것은 세지 않는다
    assert client.get("/api/dashboard").json()["other_year_active"] == 0  # 전체 보기면 숨은 것이 없다


def test_a_bad_year_is_refused(client):
    for bad in ("올해", "26", "20266"):
        assert client.get("/api/projects", params={"year": bad}).status_code == 422, bad


# ── 검색 상한 (TODO 66) ──────────────────────────────────────────────────────

def test_search_says_when_it_had_to_cut(client):
    project = make(client, "검색 시험 과제")
    for n in range(search_svc.KIND_LIMITS["entry"] + 5):
        client.post(f"/api/projects/{project['id']}/entries",
                    json={"date": "2026-09-01", "title": f"기록 {n}", "body": "인장강도 시험"})

    found = client.get("/api/search", params={"q": "인장강도"}).json()
    assert len(found["entries"]) == search_svc.KIND_LIMITS["entry"]
    assert found["truncated"]["entries"] is True, "잘렸는데 잘렸다고 말하지 않는다"


def test_search_does_not_claim_truncation_when_everything_fits(client):
    project = make(client, "작은 과제")
    client.post(f"/api/projects/{project['id']}/entries",
                json={"date": "2026-09-01", "title": "하나뿐", "body": "인장강도 시험"})

    found = client.get("/api/search", params={"q": "인장강도"}).json()
    assert found["truncated"] == {
        "projects": False, "entries": False, "reports": False, "attachments": False
    }


def test_one_kind_cannot_crowd_out_another(client):
    """예전에는 상한이 종류 공통이라, 진행일지가 자리를 다 먹으면 과제가 밀려났다."""
    crowd = make(client, "관계없는 과제")
    for n in range(search_svc.KIND_LIMITS["entry"] + 20):
        client.post(f"/api/projects/{crowd['id']}/entries",
                    json={"date": "2026-09-01", "title": f"기록 {n}", "body": "인장강도 시험"})
    make(client, "인장강도 전용 과제")  # 제목이 딱 맞는 과제

    found = client.get("/api/search", params={"q": "인장강도"}).json()
    assert "인장강도 전용 과제" in [item["title"] for item in found["projects"]]


def test_raising_the_limit_does_not_stick(client):
    """목록 거르기는 상한을 크게 쓴다. 그 값이 이후 검색에 남으면 안 된다."""
    project = make(client, "상한 시험 과제")
    for n in range(search_svc.KIND_LIMITS["entry"] + 5):
        client.post(f"/api/projects/{project['id']}/entries",
                    json={"date": "2026-09-01", "title": f"기록 {n}", "body": "인장강도 시험"})

    client.get("/api/projects", params={"q": "인장강도"})  # 내부에서 limit=500 으로 부른다
    found = client.get("/api/search", params={"q": "인장강도"}).json()
    assert len(found["entries"]) == search_svc.KIND_LIMITS["entry"]
