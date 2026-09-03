"""메인 상단 대시보드.

대시보드가 세는 수와, 그 수를 눌렀을 때 목록이 거르는 수는 반드시 같아야 한다.
어긋나면 "기한 초과 1건"을 눌렀는데 2건이 나오는 꼴이 된다.
"""
from __future__ import annotations

from datetime import date, timedelta


def make(client, **kwargs):
    payload = {"title": "기본 과제", "status": "in_progress"}
    payload.update(kwargs)
    response = client.post("/api/projects", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def day(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


def test_empty_vault_has_nothing_to_show(client):
    data = client.get("/api/dashboard").json()
    assert data["total"] == 0
    assert data["statuses"] == []
    assert data["types"] == []
    assert data["candidates"] == []


def test_counts_by_status_and_type(client):
    make(client, title="진행 하나", status="in_progress", type="rnd")
    make(client, title="진행 둘", status="in_progress", type="smart")
    make(client, title="검토", status="reviewing", type="rnd")
    make(client, title="속성 없음", status="planned")

    data = client.get("/api/dashboard").json()
    assert data["total"] == 4
    assert {item["key"]: item["count"] for item in data["statuses"]} == {
        "planned": 1,
        "reviewing": 1,
        "in_progress": 2,
    }
    assert {item["key"]: item["count"] for item in data["types"]} == {
        "rnd": 2,
        "smart": 1,
        "none": 1,
    }
    # 0건인 상태는 아예 보내지 않는다. 빈 칸이 늘면 눈이 갈 곳을 잃는다.
    assert all(item["count"] > 0 for item in data["statuses"] + data["types"])


def test_counts_by_owner(client):
    make(client, title="혼자", owners=["권경락"])
    make(client, title="둘이", owners=["권경락", "김현우"])
    make(client, title="김현우 것", owners=["김현우"])
    make(client, title="담당 없음")

    owners = client.get("/api/dashboard").json()["owners"]
    # 많이 맡은 사람부터, 같으면 이름순. 담당이 없는 과제는 '미지정'으로 맨 뒤에.
    assert owners == [
        {"key": "권경락", "label": "권경락", "count": 2},
        {"key": "김현우", "label": "김현우", "count": 2},
        {"key": "none", "label": "미지정", "count": 1},
    ]


def test_owner_counts_may_exceed_total(client):
    """한 과제에 담당자가 여러 명이면 담당 칩의 합은 전체보다 크다."""
    make(client, title="셋이", owners=["권경락", "김현우", "박서준"])

    data = client.get("/api/dashboard").json()
    assert data["total"] == 1
    assert sum(item["count"] for item in data["owners"]) == 3


def test_unassigned_owner_is_left_out_when_everyone_has_one(client):
    make(client, title="담당 있음", owners=["권경락"])
    assert [item["key"] for item in client.get("/api/dashboard").json()["owners"]] == ["권경락"]


def test_finished_projects_are_not_counted_as_overdue(client):
    make(client, title="늦은 과제", status="in_progress", due_date=day(-3))
    make(client, title="끝난 과제", status="done", due_date=day(-10))
    make(client, title="중단한 과제", status="dropped", due_date=day(-10))
    # 보류는 멈춰 있을 뿐 끝난 것이 아니라서 그대로 센다.
    make(client, title="보류 과제", status="on_hold", due_date=day(-1))

    assert client.get("/api/dashboard").json()["overdue"] == 2


def test_due_soon_counts_only_the_days_ahead(client):
    make(client, title="내일", status="in_progress", due_date=day(1))
    make(client, title="오늘", status="in_progress", due_date=day(0))
    make(client, title="여드레 뒤", status="in_progress", due_date=day(8))
    make(client, title="이미 지남", status="in_progress", due_date=day(-1))

    data = client.get("/api/dashboard").json()
    assert data["due_soon_days"] == 7
    assert data["due_soon"] == 2  # 오늘 · 내일
    assert data["overdue"] == 1


def test_numbers_match_what_the_list_filters(client):
    """대시보드의 각 수를 눌렀을 때 목록이 그만큼 걸러져야 한다."""
    make(client, title="늦은 진행", status="in_progress", due_date=day(-2), type="rnd",
         owners=["권경락"])
    make(client, title="끝난 늦은 과제", status="done", due_date=day(-9), type="rnd",
         owners=["권경락", "김현우"])
    make(client, title="곧 마감", status="reviewing", due_date=day(2), owners=["김현우"])
    make(client, title="속성 없음", status="planned")

    data = client.get("/api/dashboard").json()

    def listed(**params) -> int:
        return len(client.get("/api/projects", params=params).json())

    assert listed(due="overdue") == data["overdue"]
    assert listed(due=str(data["due_soon_days"])) == data["due_soon"]
    for item in data["statuses"]:
        assert listed(status=item["key"]) == item["count"], item
    for item in data["types"]:
        assert listed(type=item["key"]) == item["count"], item
    for item in data["owners"]:
        assert listed(owner=item["key"]) == item["count"], item


def test_candidates_are_capped_and_ordered(client):
    for index in range(8):
        project = make(client, title=f"과제 {index}", status="in_progress")
        # 미보고 진행일지가 많을수록 앞에 와야 한다.
        for day_index in range(index):
            client.post(
                f"/api/projects/{project['id']}/entries",
                json={"date": day(-day_index - 1), "body": "진행"},
            )

    data = client.get("/api/dashboard").json()
    assert len(data["candidates"]) == 5  # 주간 회의에서 훑을 만큼만
    # 모두 보고한 적이 없으므로, 미보고가 많은 쪽이 앞에 온다 (기본 순서의 3번째 기준).
    backlog = [item["unreported_entries"] for item in data["candidates"]]
    assert backlog == sorted(backlog, reverse=True)
    assert data["candidates"][0]["unreported_entries"] == 7

    assert len(client.get("/api/dashboard", params={"limit": 3}).json()["candidates"]) == 3


def test_candidate_carries_what_the_row_shows(client):
    project = make(client, title="속성 있는 과제", status="in_progress", type="smart")
    client.post(f"/api/projects/{project['id']}/entries", json={"date": day(-1), "body": "진행"})

    item = client.get("/api/dashboard").json()["candidates"][0]
    assert item["id"] == project["id"]
    assert item["type"] == "smart"
    assert item["never_reported"] is True
    assert item["unreported_entries"] == 1
