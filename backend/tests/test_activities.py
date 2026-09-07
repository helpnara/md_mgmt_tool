"""팀원 역량 이력 (TODO 72).

사용자가 정한 세 가지를 지키는지 본다.
  1. 기록 단위는 **사람** — 한 행사에 세 명이 가면 기록도 세 건
  2. 시간·비용은 **옵션** — 비워 두는 것이 정상이고, 채운 것만 합계에 들어간다
  3. **지나간 이력만** — 면담에서 쓸 자료이므로 공백까지 드러나야 한다
"""
from __future__ import annotations

from datetime import date, timedelta


def add(client, person="권경락", **kwargs):
    payload = {
        "person": person,
        "date": "2026-05-12",
        "kind": "education",
        "title": "열처리 공정 심화 과정",
    }
    payload.update(kwargs)
    response = client.post("/api/activities", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_one_event_three_people_makes_three_records(client, vault_dir):
    """한 행사에 세 명이 갔으면 기록도 세 건이다. 팀장이 보는 축은 사람이다."""
    for name in ("권경락", "김현우", "이수민"):
        add(client, person=name, title="스마트제조 박람회", kind="expo", date="2026-04-02")

    rows = client.get("/api/activities").json()
    assert len(rows) == 3
    assert {row["person"] for row in rows} == {"권경락", "김현우", "이수민"}
    # 사람마다 자기 폴더에 쌓인다 — 과제 폴더 밑이 아니다.
    assert (vault_dir / "people" / "권경락" / "activities").is_dir()
    assert not (vault_dir / "projects" / "권경락").exists()


def test_hours_and_cost_are_optional(client):
    """비워 두는 것이 정상이다. 채운 것만 합계에 들어간다."""
    add(client, title="비워 둔 기록")
    add(client, title="채운 기록", hours=16, cost=350000)

    person = next(p for p in client.get("/api/activities/summary").json()["people"]
                  if p["name"] == "권경락")
    assert person["count"] == 2
    assert person["hours"] == 16
    assert person["cost"] == 350000
    # 합계가 몇 건에서 나온 값인지 함께 준다 — 그러지 않으면 채운 사람만 커 보인다.
    assert person["with_hours"] == 1 and person["with_cost"] == 1


def test_a_bad_number_is_a_message_not_a_crash(client):
    response = client.post(
        "/api/activities",
        json={"person": "권경락", "title": "숫자가 아닌 시간", "hours": "열여섯"},
    )
    assert response.status_code == 400
    assert "숫자" in response.json()["detail"]


def test_people_on_the_roster_show_up_even_with_no_record(client):
    """면담 대상이 목록에서 빠지면 안 된다. 기록이 0건인 것 자체가 면담 거리다."""
    client.put("/api/people", json={"people": [{"name": "박지훈"}, {"name": "권경락"}]})
    add(client)

    people = {p["name"]: p for p in client.get("/api/activities/summary").json()["people"]}
    assert people["박지훈"]["count"] == 0
    assert people["박지훈"]["quiet"] is True
    assert people["권경락"]["quiet"] is False


def test_a_long_quiet_spell_is_flagged(client):
    """반년 넘게 아무것도 없으면 면담에서 가장 먼저 꺼낼 줄이다."""
    long_ago = (date.today() - timedelta(days=400)).isoformat()
    add(client, person="김현우", date=long_ago, title="작년 세미나", kind="seminar")

    person = next(p for p in client.get("/api/activities/summary").json()["people"]
                  if p["name"] == "김현우")
    assert person["quiet"] is True
    assert person["days_since"] >= 365


def test_summary_keeps_a_multi_year_trend(client):
    """과거 이력을 보고 내년을 이야기하는 화면이라, 한 해만 보면 쓸모가 없다."""
    add(client, date="2024-03-02", title="2024 교육")
    add(client, date="2025-06-11", title="2025 학회", kind="conference")
    add(client, date="2026-05-12", title="2026 교육")

    data = client.get("/api/activities/summary", params={"year": "2026"}).json()
    person = next(p for p in data["people"] if p["name"] == "권경락")
    assert person["count"] == 1  # 올해만 센다
    assert person["trend"] == {"2024": 1, "2025": 1, "2026": 1}  # 추이는 전체를 본다
    assert data["years"] == ["2026", "2025", "2024"]


def test_editing_moves_the_file_when_the_person_changes(client, vault_dir):
    """사람을 잘못 골랐을 때 고칠 수 있어야 한다. 파일도 따라 옮겨진다."""
    activity_id = add(client, person="권경락", title="잘못 넣은 기록")
    client.patch(f"/api/activities/{activity_id}", json={"person": "김현우"})

    rows = client.get("/api/activities").json()
    assert rows[0]["person"] == "김현우"
    assert list((vault_dir / "people" / "김현우" / "activities").glob("*.md"))
    assert not list((vault_dir / "people" / "권경락" / "activities").glob("*.md"))


def test_delete_moves_to_trash_not_oblivion(client, vault_dir):
    activity_id = add(client, title="지울 기록")
    assert client.delete(f"/api/activities/{activity_id}").status_code == 204

    assert client.get("/api/activities").json() == []
    trash = client.get("/api/trash").json()
    assert any(item["kind"] == "activity" for item in trash)


def test_records_survive_a_full_reindex(client, vault_dir):
    """색인은 파생물이다. 지워도 md 파일에서 그대로 되살아나야 한다."""
    add(client, title="살아남을 기록", hours=8)
    assert client.post("/api/reindex").status_code in (200, 201)

    rows = client.get("/api/activities").json()
    assert len(rows) == 1 and rows[0]["title"] == "살아남을 기록" and rows[0]["hours"] == 8


def test_filters_narrow_the_list(client):
    add(client, person="권경락", title="교육 하나", kind="education", date="2026-01-05")
    add(client, person="김현우", title="학회 하나", kind="conference", date="2025-11-20")

    assert len(client.get("/api/activities", params={"person": "권경락"}).json()) == 1
    assert len(client.get("/api/activities", params={"kind": "conference"}).json()) == 1
    assert len(client.get("/api/activities", params={"year": "2026"}).json()) == 1
    assert len(client.get("/api/activities", params={"q": "학회"}).json()) == 1


# ── 여러 명 · 기간 (TODO 74) ────────────────────────────

def test_comma_separated_names_become_one_record_each(client, vault_dir):
    """실사용에서 난 사고 — `"A,B"` 한 덩이가 사람 하나로 굳어 집계에 유령이 생겼다.

    나누는 일은 **서버에서** 한다. 화면만 고치면 API 를 직접 부르는 길로 같은 일이 다시 난다.
    """
    response = client.post(
        "/api/activities",
        json={"person": "권경락, 김현우; 이수민", "title": "스마트제조 박람회", "kind": "expo"},
    )
    assert response.status_code == 201
    assert response.json()["count"] == 3

    rows = client.get("/api/activities").json()
    assert {row["person"] for row in rows} == {"권경락", "김현우", "이수민"}
    # 사람마다 자기 폴더가 생긴다 — "권경락,김현우" 라는 폴더는 없다.
    folders = {path.name for path in (vault_dir / "people").iterdir()}
    assert folders == {"권경락", "김현우", "이수민"}


def test_the_roster_never_gets_a_glued_name(client):
    """명부에 `"A,B"` 가 들어가면 지우기 전까지 사람별 표에 남는다. 애초에 못 들어가게 한다."""
    client.post("/api/activities", json={"person": "권경락,김현우", "title": "공동 교육"})

    names = client.get("/api/meta").json()["people"]
    assert "권경락" in names and "김현우" in names
    assert not any("," in name for name in names)


def test_duplicate_and_blank_names_are_dropped(client):
    response = client.post(
        "/api/activities", json={"person": " 권경락 , ,권경락;", "title": "중복 이름"}
    )
    assert response.json()["count"] == 1
    assert len(client.get("/api/activities").json()) == 1


def test_editing_refuses_several_names(client):
    """고칠 때 나눠 주면 '고쳤는데 기록이 늘어났다' 가 된다. 막고 이유를 말한다."""
    activity_id = client.post(
        "/api/activities", json={"person": "권경락", "title": "혼자 간 교육"}
    ).json()["id"]

    response = client.patch(f"/api/activities/{activity_id}", json={"person": "권경락, 김현우"})
    assert response.status_code == 400
    assert "한 사람" in response.json()["detail"]


def test_a_multi_day_course_keeps_both_dates(client):
    """2~3일에 걸친 교육. 파일 이름과 연도 집계는 **시작일**을 따른다."""
    client.post("/api/activities", json={
        "person": "권경락", "title": "3일짜리 교육",
        "date": "2026-05-12", "end_date": "2026-05-14",
    })
    row = client.get("/api/activities").json()[0]
    assert row["date"] == "2026-05-12" and row["end_date"] == "2026-05-14"
    assert client.get("/api/activities", params={"year": "2026"}).json()


def test_one_day_course_leaves_the_end_date_empty(client):
    """같은 날짜를 두 번 적어도 기간으로 보지 않는다 — 화면이 '~' 를 괜히 붙인다."""
    client.post("/api/activities", json={
        "person": "권경락", "title": "하루 교육", "date": "2026-05-12", "end_date": "2026-05-12",
    })
    assert client.get("/api/activities").json()[0]["end_date"] is None


def test_an_end_date_before_the_start_is_refused(client):
    response = client.post("/api/activities", json={
        "person": "권경락", "title": "거꾸로", "date": "2026-05-12", "end_date": "2026-05-01",
    })
    assert response.status_code == 400
    assert "종료일" in response.json()["detail"]


def test_the_period_survives_a_reindex(client):
    client.post("/api/activities", json={
        "person": "권경락", "title": "기간 교육", "date": "2026-05-12", "end_date": "2026-05-14",
    })
    client.post("/api/reindex")
    assert client.get("/api/activities").json()[0]["end_date"] == "2026-05-14"


def test_a_new_name_is_added_to_the_roster(client):
    """명부에 없는 이름으로 기록하면 명부에 넣어 둔다 — 표기 흔들림을 막는 자리다."""
    add(client, person="새로운사람")
    assert "새로운사람" in client.get("/api/meta").json()["people"]
