"""1인 팀장 전수 검토에서 잡힌 결함 (TODO 103).

화면을 돌아보다 잡힌 것들이라 하나같이 "말한 것과 보여 주는 것이 다르다" 는 부류다.
"""
from __future__ import annotations

from datetime import date, timedelta


def make(client, title, **extra):
    return client.post("/api/projects", json={"title": title, **extra}).json()


def day(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


# ── A. 확정 대기 카드는 날짜를 가리지 않는다 ──────────────────────────────────

def test_the_waiting_card_lists_drafts_from_every_report_day(client):
    project = make(client, "과제")
    old = client.post(f"/api/projects/{project['id']}/reports/draft", json={"report_date": day(-9)}).json()
    soon = client.post(f"/api/projects/{project['id']}/reports/draft", json={"report_date": day(6)}).json()

    drafts = client.get("/api/report-candidates").json()["drafts"]
    ids = [item["id"] for item in drafts]
    # 홈이 "2건" 이라 세우고 보내는 곳이다. 둘 다 있어야 하고, 오래된 것이 먼저다.
    assert ids == [old["id"], soon["id"]]
    assert drafts[0]["report_date"] == day(-9)
    assert drafts[0]["overdue_days"] == 9
    assert drafts[1]["overdue_days"] == 0


def test_home_count_and_waiting_card_agree(client):
    project = make(client, "과제")
    for offset in (-20, -13, -6, 1):
        client.post(f"/api/projects/{project['id']}/reports/draft", json={"report_date": day(offset)})
    home = client.get("/api/home").json()["this_week"]["drafts"]
    card = client.get("/api/report-candidates").json()["drafts"]
    assert home == len(card) == 4


# ── B. 오래 방치된 과제 — 자르기 전 수 ──────────────────────────────────────

def test_home_says_how_many_stale_projects_were_cut(client):
    from app.services.home import STALE_LIMIT

    # 자르는 수보다 두 건 더 — 모두 보고 이력이 없고 시작한 지 오래된 과제다.
    for index in range(STALE_LIMIT + 2):
        client.post("/api/projects", json={"title": f"방치 {index}", "start_date": day(-100)})
    week = client.get("/api/home").json()["this_week"]
    assert len(week["stale"]) == STALE_LIMIT
    assert week["stale_total"] == STALE_LIMIT + 2


def test_stale_total_is_zero_when_nothing_is_stale(client):
    make(client, "오늘 시작")
    week = client.get("/api/home").json()["this_week"]
    assert week["stale_total"] == len(week["stale"])


# ── C. 검색 발췌에 서식 기호가 없다 ─────────────────────────────────────────

def test_search_snippet_drops_markdown_marks(client):
    make(client, "발췌 시험", body="## 배경\n\n> 왜 **이 과제**를 하는지 — 요청 배경\n\n## 목표\n\n수율 3% 개선\n")
    hit = client.get("/api/search", params={"q": "수율"}).json()["projects"][0]
    assert "##" not in hit["snippet"]
    assert "**" not in hit["snippet"]
    assert ">" not in hit["snippet"]
    assert "수율 3% 개선" in hit["snippet"]


def test_search_and_history_excerpts_share_one_eye(client):
    # 같은 본문을 두 발췌가 같은 규칙으로 읽어야 한다 — 87 에서 반쪽만 고쳤던 것.
    from app.services.reports import readable_text
    from app.services.search import make_snippet

    body = "## 제목\n\n- 첫째\n- **둘째**\n\n| 표 | 무시 |\n"
    assert make_snippet(body, "둘째") == readable_text(body)
