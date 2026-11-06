"""팀원 입장 — 내 할 일 · 일지 알림 · 보고 횟수 · 팀장의 인정 한 줄 (TODO 242). 시험의 오늘은 2026-10-20."""
from __future__ import annotations

from app.vault import markdown as md
from tests.test_contributions import _index_md, team  # noqa: F401 — 팀장 · 팀원(가팀원) · 읽기 셋


def _row(client, pid, name):
    return {r["name"]: r for r in client.get(f"/api/projects/{pid}").json()["contributions"]}[name]


def test_praise_is_written_by_leader_and_seen_only_by_that_person(team):  # noqa: F811
    owner, member, viewer, pid = team["owner"], team["member"], team["viewer"], team["shared"]
    url = f"/api/projects/{pid}/contributions/"
    assert owner.put(url + "가팀원", json={"praise": "현장 설득이 결정적이었음"}).status_code == 200
    owner.put(url + "나팀원", json={"praise": "모델 학습을 꼼꼼히"})
    assert _row(owner, pid, "가팀원")["praise"] == "현장 설득이 결정적이었음"
    assert _row(owner, pid, "가팀원")["praise_at"] == "2026-10-20"
    assert _row(member, pid, "가팀원")["praise"] == "현장 설득이 결정적이었음"  # 본인
    assert _row(member, pid, "나팀원")["praise"] == ""  # 남의 것은 빼고 준다
    assert _row(viewer, pid, "가팀원")["praise"] == ""  # 읽기 전용
    history = viewer.get("/api/person-history", params={"name": "가팀원"}).json()
    assert all(item["praise"] == "" for item in history["projects"])
    mine = member.get("/api/person-history", params={"name": "가팀원"}).json()
    assert mine["projects"][0]["praise"] == "현장 설득이 결정적이었음"
    # 팀원은 적지 못한다 · 한 줄 · 200자
    denied = member.put(url + "가팀원", json={"praise": "스스로 칭찬"})
    assert denied.status_code == 403 and "팀장" in denied.json()["detail"]
    assert owner.put(url + "가팀원", json={"praise": "두\n줄"}).status_code == 400
    assert owner.put(url + "가팀원", json={"praise": "가" * 201}).status_code == 400
    # 파일에는 남고, 내보내기에는 없다
    assert md.load(_index_md(pid)).meta["contributions"][0]["praise"] == "현장 설득이 결정적이었음"
    assert "현장 설득" not in owner.get(f"/api/projects/{pid}/export?format=md").text


def test_my_work_lists_my_projects_stale_logs_retro_and_praise(team):  # noqa: F811
    owner, member, viewer, pid = team["owner"], team["member"], team["viewer"], team["shared"]
    other = owner.post("/api/projects", json={"title": "나팀원만 과제", "owners": ["나팀원"], "status": "in_progress"}).json()["id"]
    soon = owner.post("/api/projects", json={"title": "곧 마감", "owners": ["가팀원"], "status": "planned",
                                              "start_date": "2026-10-01", "due_date": "2026-10-25"}).json()
    work = member.get("/api/projects/my-work").json()
    ids = [item["id"] for item in work["projects"]]
    assert pid in ids and other not in ids
    upcoming = next(item for item in work["projects"] if item["id"] == soon["id"])
    assert upcoming["days_left"] == 5 and upcoming["stale"] is False  # 예정 과제는 일지 알림을 하지 않는다
    shared = next(item for item in work["projects"] if item["id"] == pid)
    assert shared["stale"] is True and shared["last_entry"] is None and shared["days_since_entry"] > 14  # 시작일부터 센다
    assert ids[0] == pid  # 일지가 필요한 것이 먼저
    # 일지를 쓰면 알림이 내려간다
    member.post(f"/api/projects/{pid}/entries", json={"date": "2026-10-19", "title": "이번 주"})
    shared = next(item for item in member.get("/api/projects/my-work").json()["projects"] if item["id"] == pid)
    assert shared["stale"] is False and shared["days_since_entry"] == 1
    # 끝난 과제는 회고를 적을 과제로, 인정 한 줄은 새것으로
    owner.patch(f"/api/projects/{pid}", json={"status": "done"})
    owner.put(f"/api/projects/{pid}/contributions/가팀원", json={"praise": "끝까지 챙김"})
    work = member.get("/api/projects/my-work").json()
    assert pid not in [item["id"] for item in work["projects"]]
    assert [item["id"] for item in work["retro_due"]] == [pid]
    assert work["praises"][0]["praise"] == "끝까지 챙김" and work["praises"][0]["new"] is True
    assert viewer.get("/api/projects/my-work").json()["projects"] == []


def test_history_counts_reports_of_my_projects(team):  # noqa: F811
    owner, member, pid = team["owner"], team["member"], team["shared"]
    for day in ("2026-03-10", "2026-06-15"):
        draft = owner.post(f"/api/projects/{pid}/reports/draft", json={"report_date": day}).json()
        assert owner.post(f"/api/reports/{draft['id']}/freeze").status_code == 200
    owner.post(f"/api/projects/{pid}/reports/draft", json={"report_date": "2026-09-01"})  # 확정하지 않은 것은 세지 않는다
    data = member.get("/api/person-history", params={"name": "가팀원"}).json()
    assert data["summary"]["reports_this_year"] == 2 and data["summary"]["reports_last_year"] == 0
    assert data["projects"][0]["reports"] == 2
