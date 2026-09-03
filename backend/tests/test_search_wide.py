"""상단 검색이 어디까지 찾는가 (TODO 53).

검색은 **하나로 통일한다** — 최상단 검색창 하나가 입력된 모든 것을 찾아야 한다.
예전에는 과제와 진행일지의 제목·본문만 색인해서, "전사 주요업무 보고" 로 찾으면
아무것도 안 나왔다. 보고 문서가 아예 색인 대상이 아니었기 때문이다.
"""
from __future__ import annotations


def make(client, title="과제", **kwargs):
    payload = {"title": title, "status": "in_progress"}
    payload.update(kwargs)
    response = client.post("/api/projects", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def find(client, query):
    return client.get("/api/search", params={"q": query}).json()


def test_a_report_can_be_found_by_who_it_went_to(client):
    project = make(client, "고강도 소재")
    report = client.post(
        f"/api/projects/{project['id']}/reports/draft",
        json={"report_date": "2026-08-25", "audience": "전사 주요업무 보고"},
    ).json()
    client.post(f"/api/reports/{report['id']}/freeze")

    found = find(client, "주요업무")
    assert [item["id"] for item in found["reports"]] == [report["id"]]
    assert found["reports"][0]["project_title"] == "고강도 소재"
    assert found["reports"][0]["audience"] == "전사 주요업무 보고"


def test_a_report_can_be_found_by_its_body(client):
    project = make(client)
    report = client.post(
        f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-08-25"}
    ).json()
    client.patch(f"/api/reports/{report['id']}", json={"body": "## 보고 요약\n\n인장강도 780MPa 확보\n"})

    found = find(client, "780MPa")
    assert len(found["reports"]) == 1
    assert "780MPa" in found["reports"][0]["snippet"]


def test_a_project_can_be_found_by_its_tag(client):
    make(client, "소재 개발", tags=["공정개선"])
    make(client, "다른 과제")

    found = find(client, "공정개선")
    assert [item["title"] for item in found["projects"]] == ["소재 개발"]


def test_a_project_can_be_found_by_its_owner(client):
    make(client, "권경락 과제", owners=["권경락"])
    make(client, "김현우 과제", owners=["김현우"])

    found = find(client, "김현우")
    assert [item["title"] for item in found["projects"]] == ["김현우 과제"]


def test_the_total_counts_reports_too(client):
    project = make(client, "시제품 과제")
    report = client.post(
        f"/api/projects/{project['id']}/reports/draft",
        json={"report_date": "2026-08-25", "audience": "시제품 검토회"},
    ).json()
    assert report["id"]

    found = find(client, "시제품")
    assert found["total"] == len(found["projects"]) + len(found["entries"]) \
        + len(found["reports"]) + len(found["attachments"])
    assert found["total"] >= 2  # 과제 + 보고


def test_a_deleted_report_leaves_the_index(client):
    project = make(client)
    report = client.post(
        f"/api/projects/{project['id']}/reports/draft",
        json={"report_date": "2026-08-25", "audience": "없어질 회의체"},
    ).json()
    assert len(find(client, "없어질")["reports"]) == 1

    client.delete(f"/api/reports/{report['id']}")
    assert find(client, "없어질")["reports"] == []


def test_renaming_an_owner_updates_the_index(client):
    """색인이 파일을 따라오지 않으면 검색이 조용히 옛 사실을 말한다."""
    make(client, "과제", owners=["권 경락"])
    assert len(find(client, "권 경락")["projects"]) == 1

    client.post("/api/people/rename", json={"old": "권 경락", "new": "권경락"})
    assert find(client, "권 경락")["projects"] == []
    assert len(find(client, "권경락")["projects"]) == 1


def test_the_project_list_can_be_filtered_by_a_report_word(client):
    """목록의 검색 칸도 같은 색인을 쓴다 — 보고에 걸려도 그 과제가 남아야 한다."""
    project = make(client, "소재 과제")
    client.post(
        f"/api/projects/{project['id']}/reports/draft",
        json={"report_date": "2026-08-25", "audience": "전사 주요업무 보고"},
    )
    make(client, "관련 없는 과제")

    rows = client.get("/api/projects", params={"q": "주요업무"}).json()
    assert [row["title"] for row in rows] == ["소재 과제"]


# ── 과제 목록 열 정렬 (TODO 57) ──────────────────────────────────────────────

def listed(client, **params):
    return [row["title"] for row in client.get("/api/projects", params=params).json()]


def test_a_column_sorts_both_ways(client):
    make(client, "다 과제")
    make(client, "가 과제")
    make(client, "나 과제")

    assert listed(client, sort="title", order="asc") == ["가 과제", "나 과제", "다 과제"]
    assert listed(client, sort="title", order="desc") == ["다 과제", "나 과제", "가 과제"]


def test_empty_values_stay_at_the_bottom_in_both_directions(client):
    make(client, "그룹 있는 과제", group="소재")
    make(client, "그룹 없는 과제")

    for order in ("asc", "desc"):
        assert listed(client, sort="group", order=order)[-1] == "그룹 없는 과제", order


def test_multi_valued_columns_sort_by_their_first_value(client):
    """담당자·태그는 여러 개일 수 있다. 개수로 세면 사람을 찾는 데 도움이 안 된다."""
    make(client, "김현우 과제", owners=["김현우", "권경락"])
    make(client, "권경락 과제", owners=["권경락"])
    make(client, "담당 없는 과제")

    order = listed(client, sort="owner", order="asc")
    assert order[:2] == ["권경락 과제", "김현우 과제"]
    assert order[-1] == "담당 없는 과제"


def test_without_order_the_named_sort_keeps_its_own_direction(client):
    """이름이 붙은 정렬은 저마다 방향이 있다 (효과=큰 것부터). order 를 안 주면 그대로여야 한다."""
    make(client, "효과 작은 과제", effect_expected=0.5)
    make(client, "효과 큰 과제", effect_expected=9.9)

    assert listed(client, sort="effect")[0] == "효과 큰 과제"
    # 열 머리글을 눌러 방향을 뒤집으면 그때는 바뀐다.
    assert listed(client, sort="effect", order="asc")[0] == "효과 작은 과제"


def test_an_unknown_order_is_refused(client):
    make(client, "과제")
    assert client.get("/api/projects", params={"sort": "title", "order": "위로"}).status_code == 422
