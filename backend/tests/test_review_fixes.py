"""사용자 관점 점검에서 나온 나머지 개선 (TODO 82·85·86·87·89·90).

하나로 묶어 둔 이유는 전부 **"화면이 적어 놓은 수가 사실과 같은가"** 라는 한 가지 질문이기
때문이다. 대시보드 규칙(DESIGN 5.8)의 연장선이다.
"""
from __future__ import annotations


def seed(client):
    """그룹·효과·역량이 골고루 있는 작은 팀."""
    client.put("/api/people", json={"people": [{"name": n} for n in ("가", "나", "다")]})
    ids = []
    for title, status, kind, group, owners, ee, ev in [
        ("가군 진행", "in_progress", "rnd", "차세대전지", ["가", "나"], 4.5, None),
        ("가군 완료", "done", "rnd", "차세대전지", ["가"], 2.0, 1.5),
        ("나군 검토", "reviewing", "smart", "소재", ["나"], None, None),
        ("무리 없음", "planned", None, "", ["다"], 1.0, None),
    ]:
        body = {"title": title, "status": status, "owners": owners, "group": group}
        if kind:
            body["type"] = kind
        if ee is not None:
            body["effect_expected"] = ee
        if ev is not None:
            body["effect_verified"] = ev
        ids.append(client.post("/api/projects", json=body).json()["id"])
    return ids


# ── TODO 82. 대시보드가 적는 수와 눌러서 나오는 수 ──────────────────────────
def test_dashboard_reports_the_total_candidate_count_not_the_truncated_one(client):
    for i in range(7):
        project = client.post("/api/projects", json={"title": f"과제 {i}"}).json()["id"]
        client.post(
            f"/api/projects/{project}/entries",
            json={"date": "2026-09-01", "title": "진행", "body": "내용"},
        )

    dashboard = client.get("/api/dashboard").json()
    everything = client.get("/api/report-candidates").json()["items"]

    # 화면에 세우는 줄은 잘려도, "N건 보기" 가 쓰는 수는 전체여야 한다.
    assert len(dashboard["candidates"]) < len(everything)
    assert dashboard["candidate_total"] == len(everything)


# ── TODO 86. 효과 금액의 분모 ────────────────────────────────────────────
def test_home_says_how_many_projects_the_effect_numbers_came_from(client):
    seed(client)
    team = client.get("/api/home").json()["team"]

    assert team["effect_expected"] == 7.5
    assert team["effect_verified"] == 1.5
    # 기대는 3건, 실증은 1건에서 나왔다. 이 분모가 없으면 화살표가 달성률로 읽힌다.
    assert team["effect_expected_projects"] == 3
    assert team["effect_verified_projects"] == 1
    assert team["total"] == 4


# ── TODO 89. 팀원별 표의 역량 이력 열 ────────────────────────────────────
def test_home_member_row_carries_that_years_activity_count(client):
    seed(client)
    client.post(
        "/api/activities",
        json={"date": "2026-05-02", "kind": "education", "person": "가, 나", "title": "공통 교육"},
    )
    client.post(
        "/api/activities",
        json={"date": "2025-05-02", "kind": "seminar", "person": "가", "title": "작년 세미나"},
    )

    members = {row["name"]: row for row in client.get("/api/home?year=2026").json()["members"]}
    assert members["가"]["activities"] == 1   # 작년 것은 안 센다
    assert members["나"]["activities"] == 1
    assert members["다"]["activities"] == 0   # 0 이면 그 자체가 면담 이야깃거리다

    # 연도를 풀면 지난해 것까지 함께 센다.
    every = {row["name"]: row for row in client.get("/api/home").json()["members"]}
    assert every["가"]["activities"] == 2


# ── TODO 90. 그룹별 표 ──────────────────────────────────────────────────
def test_group_table_counts_match_what_the_list_filters(client):
    seed(client)
    groups = client.get("/api/home").json()["groups"]
    # 많은 것부터. 미지정은 속성별 표와 같이 맨 아래에 선다.
    assert [row["label"] for row in groups] == ["차세대전지", "소재", "미지정"]

    for row in groups:
        listed = client.get("/api/projects", params={"group": row["key"]}).json()
        assert len(listed) == row["count"], f"{row['label']} 이 어긋난다"
        for status, n in row["by_status"].items():
            if not n:
                continue
            narrowed = client.get(
                "/api/projects", params={"group": row["key"], "status": status}
            ).json()
            assert len(narrowed) == n, f"{row['label']}/{status} 이 어긋난다"


def test_projects_without_a_group_are_reachable_from_the_table(client):
    seed(client)
    unset = next(row for row in client.get("/api/home").json()["groups"] if row["key"] == "none")
    assert unset["label"] == "미지정"
    assert len(client.get("/api/projects", params={"group": "none"}).json()) == unset["count"]


# ── TODO 85. 행사 수와 참여 기록 수 ──────────────────────────────────────
def test_one_event_with_three_people_counts_as_one_event(client):
    client.post(
        "/api/activities",
        json={
            "date": "2026-05-21",
            "end_date": "2026-05-23",
            "kind": "expo",
            "person": "가, 나, 다",
            "title": "InterBattery 2026",
        },
    )
    client.post(
        "/api/activities",
        json={"date": "2026-04-08", "kind": "seminar", "person": "가", "title": "혼자 간 세미나"},
    )

    team = client.get("/api/activities/summary").json()["team"]
    assert team["count"] == 4   # 참여 연인원
    assert team["events"] == 2  # 실제 행사 수
    assert team["people"] == 3

    rows = client.get("/api/activities").json()
    grouped = {row["event_key"] for row in rows}
    assert len(grouped) == 2
    # 같은 행사에 간 세 사람은 같은 열쇠를 든다 — 화면이 이것으로 접는다.
    expo = [row for row in rows if row["title"] == "InterBattery 2026"]
    assert len({row["event_key"] for row in expo}) == 1


# ── TODO 87. 한 줄 발췌 ─────────────────────────────────────────────────
def test_report_excerpt_skips_markdown_headings(client):
    project = client.post("/api/projects", json={"title": "발췌 확인"}).json()["id"]
    draft = client.post(
        f"/api/projects/{project}/reports/draft", json={"report_date": "2026-09-08"}
    ).json()
    client.patch(
        f"/api/reports/{draft['id']}",
        json={
            "body": "## 보고 요약\n\n- 인장강도 **780MPa** 확보\n\n"
            "| 구분 | 값 |\n|---|---|\n\n## 다음 계획\n\n양산성 검토"
        },
    )
    client.post(f"/api/reports/{draft['id']}/freeze")

    excerpt = client.get("/api/reports").json()[0]["excerpt"]
    # 어느 보고에나 똑같이 들어 있는 제목은 서로를 구별해 주지 못한다.
    assert "## " not in excerpt
    assert "|" not in excerpt
    assert excerpt.startswith("인장강도 780MPa 확보")
