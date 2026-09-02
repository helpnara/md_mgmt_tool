from __future__ import annotations


def seed(client):
    first = client.post(
        "/api/projects",
        json={"title": "리튬전지 수명평가", "group": "차세대전지", "tags": ["수명평가"], "due_date": "2026-09-05"},
    ).json()
    client.post(
        f"/api/projects/{first['id']}/entries",
        json={"date": "2026-09-03", "title": "1차 측정", "body": "B안의 용량 유지율이 98.2%로 가장 높았다."},
    )
    second = client.post(
        "/api/projects",
        json={"title": "양극재 스케일업", "group": "소재", "due_date": "2030-01-01"},
    ).json()
    client.post(
        f"/api/projects/{second['id']}/entries",
        json={"date": "2026-08-28", "title": "파일럿 조건", "body": "소성 온도 조건을 정리했다."},
    )
    return first, second


def test_search_finds_entry_body(client):
    first, _ = seed(client)
    result = client.get("/api/search", params={"q": "용량 유지율"}).json()
    assert result["total"] >= 1
    hit = result["entries"][0]
    assert hit["project_id"] == first["id"]
    assert hit["title"] == "1차 측정"
    assert "98.2%" in hit["snippet"]


def test_search_finds_project_title(client):
    first, _ = seed(client)
    result = client.get("/api/search", params={"q": "리튬전지"}).json()
    assert [item["id"] for item in result["projects"]] == [first["id"]]


def test_short_query_still_works(client):
    """trigram은 3글자 미만을 못 찾으므로 LIKE로 물러나야 한다."""
    seed(client)
    result = client.get("/api/search", params={"q": "B안"}).json()
    assert result["total"] >= 1


def test_search_finds_attachment_filename(client):
    first, _ = seed(client)
    entry_id = client.get(f"/api/projects/{first['id']}/entries").json()[0]["id"]
    client.post(
        f"/api/entries/{entry_id}/attachments",
        files={"file": ("사이클_원시데이터.xlsx", b"PK\x03\x04", "application/octet-stream")},
    )
    result = client.get("/api/search", params={"q": "원시데이터"}).json()
    assert [item["orig_name"] for item in result["attachments"]] == ["사이클_원시데이터.xlsx"]


def test_empty_query_returns_nothing(client):
    seed(client)
    assert client.get("/api/search", params={"q": "  "}).json()["total"] == 0


def test_project_list_filters_by_search_including_entries(client):
    first, _ = seed(client)
    ids = [item["id"] for item in client.get("/api/projects", params={"q": "소성 온도"}).json()]
    assert ids and first["id"] not in ids

    ids = [item["id"] for item in client.get("/api/projects", params={"q": "유지율"}).json()]
    assert ids == [first["id"]]


def test_project_list_due_filters(client):
    """마감이 지난 과제와 곧 닥치는 과제를 오늘 기준으로 골라낸다."""
    from datetime import date, timedelta

    first, second = seed(client)
    client.patch(f"/api/projects/{first['id']}", json={"due_date": "2020-01-01"})
    soon_date = (date.today() + timedelta(days=10)).isoformat()
    third = client.post("/api/projects", json={"title": "곧 마감", "due_date": soon_date}).json()

    overdue = [item["id"] for item in client.get("/api/projects", params={"due": "overdue"}).json()]
    assert overdue == [first["id"]]

    # '30일 이내'는 앞으로 30일이라는 뜻이다. 이미 지난 과제는 여기 섞이지 않는다
    # (그쪽은 '기한 초과'가 따로 맡는다). 대시보드가 세는 수와 어긋나면 안 되기 때문.
    soon = [item["id"] for item in client.get("/api/projects", params={"due": "30"}).json()]
    assert soon == [third["id"]]

    # 2030년 마감인 과제는 어느 쪽에도 걸리지 않는다.
    assert second["id"] not in overdue + soon


def test_finished_projects_drop_out_of_due_filters(client):
    """끝난 과제는 마감이 지났어도 경고 대상이 아니다."""
    late = client.post(
        "/api/projects", json={"title": "늦은 과제", "status": "in_progress", "due_date": "2020-01-01"}
    ).json()
    client.post("/api/projects", json={"title": "끝난 과제", "status": "done", "due_date": "2020-01-01"})
    client.post("/api/projects", json={"title": "중단한 과제", "status": "dropped", "due_date": "2020-01-01"})

    overdue = [item["id"] for item in client.get("/api/projects", params={"due": "overdue"}).json()]
    assert overdue == [late["id"]]
