"""전배·퇴사한 담당자 (TODO 122).

명부에서 **지우지 않고** 떠난 날을 적는다. 그 한 칸이 홈 알림·목록 거르기·넘기기를 모두 연다.
"""
from __future__ import annotations


def setup(client):
    client.put("/api/people", json={"people": [
        {"name": "권경락"},
        {"name": "홍길동", "left_on": "2026-09-30", "left_reason": "전배"},
    ]})
    live = client.post("/api/projects", json={
        "title": "진행 중 과제", "status": "in_progress", "owners": ["홍길동", "권경락"]}).json()
    done = client.post("/api/projects", json={
        "title": "끝난 과제", "status": "done", "owners": ["홍길동"]}).json()
    return live["id"], done["id"]


def test_roster_keeps_the_person_and_records_the_date(client):
    setup(client)
    people = {p["name"]: p for p in client.get("/api/people").json()["people"]}
    assert people["홍길동"]["left_on"] == "2026-09-30"
    assert people["홍길동"]["left_reason"] == "전배"
    # 지우지 않으므로 "명부에 없는 이름" 으로 잡히지 않는다.
    assert client.get("/api/people").json()["unregistered"] == []
    # 아직 끝나지 않은 과제가 몇 건인지 명부 화면이 바로 안다.
    assert people["홍길동"]["unfinished"] == 1
    assert people["권경락"]["unfinished"] == 1


def test_meta_separates_people_who_left(client):
    setup(client)
    meta = client.get("/api/meta").json()
    assert "홍길동" in meta["people"]  # 명부에는 남는다
    assert [p["name"] for p in meta["people_left"]] == ["홍길동"]


def test_home_asks_for_a_replacement_only_for_unfinished_work(client):
    live, _ = setup(client)
    week = client.get("/api/home").json()["this_week"]
    assert week["owner_gaps_total"] == 1
    assert [item["id"] for item in week["owner_gaps"]] == [live]
    assert week["owner_gaps"][0]["owner"] == "홍길동"
    assert week["owner_gaps"][0]["left_reason"] == "전배"


def test_the_number_matches_what_the_list_filters(client):
    live, _ = setup(client)
    week = client.get("/api/home").json()["this_week"]
    listed = client.get("/api/projects", params={"owner_left": "1"}).json()
    assert [p["id"] for p in listed] == [live]
    assert len(listed) == week["owner_gaps_total"]


def test_no_one_has_left_means_nothing_to_show(client):
    client.put("/api/people", json={"people": [{"name": "권경락"}]})
    client.post("/api/projects", json={"title": "과제", "owners": ["권경락"]})
    assert client.get("/api/home").json()["this_week"]["owner_gaps_total"] == 0
    assert client.get("/api/projects", params={"owner_left": "1"}).json() == []


def test_handover_moves_unfinished_work_and_leaves_history_alone(client):
    live, done = setup(client)
    result = client.post("/api/people/handover", json={"old": "홍길동", "new": "김현우"}).json()
    assert result["count"] == 1 and result["changed"] == [live]

    assert client.get(f"/api/projects/{live}").json()["owners"] == ["김현우", "권경락"]
    # 끝난 과제는 그대로 — 그때 그 사람이 한 것은 사실이다.
    assert client.get(f"/api/projects/{done}").json()["owners"] == ["홍길동"]
    # 명부도 그대로. 넘기기는 표기 통일이 아니다.
    names = [p["name"] for p in client.get("/api/people").json()["people"]]
    assert "홍길동" in names
    assert client.get("/api/home").json()["this_week"]["owner_gaps_total"] == 0


def test_handover_can_include_finished_work_when_asked(client):
    _, done = setup(client)
    client.post("/api/people/handover",
                json={"old": "홍길동", "new": "김현우", "include_finished": True})
    assert client.get(f"/api/projects/{done}").json()["owners"] == ["김현우"]


def test_handover_refuses_empty_or_same_names(client):
    setup(client)
    assert client.post("/api/people/handover", json={"old": "홍길동", "new": ""}).status_code == 400
    assert client.post("/api/people/handover", json={"old": "홍길동", "new": "홍길동"}).status_code == 400


def test_bad_left_on_is_treated_as_still_here(client):
    """손으로 고친 settings.json 대비 — 날짜가 아니면 비운 것으로 본다."""
    client.put("/api/people", json={"people": [{"name": "홍길동", "left_on": "작년"}]})
    assert client.get("/api/people").json()["people"][0]["left_on"] == ""
    assert client.get("/api/meta").json()["people_left"] == []
