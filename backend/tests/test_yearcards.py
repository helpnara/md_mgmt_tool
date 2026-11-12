"""연말 회고 카드 (TODO 285) — 사람 · 과제는 지어낸 것이다(`test_contributions.team`)."""
from __future__ import annotations

from tests.test_contributions import team  # noqa: F401


def test_card_defaults_from_year_and_saves_message(team):  # noqa: F811
    owner, pid = team["owner"], team["shared"]
    owner.put(f"/api/projects/{pid}/contributions/가팀원", json={"did": "- 판정 기준 정리", "result": "재검 월 30 → 12건", "praise": "끝까지 챙겨 줘서 고마워요"})
    owner.patch(f"/api/projects/{pid}", json={"status": "done", "completed_at": "2026-10-01"})
    data = owner.get("/api/yearcards/card", params={"name": "가팀원", "year": "2026"}).json()
    assert data["chosen"] == [pid] and data["picked"][0]["result"].startswith("재검") and data["picked"][0]["praise"]
    assert "감사 편지" in data["missing"] and data["saved"] is False
    saved = owner.put("/api/yearcards/card", params={"name": "가팀원", "year": "2026"},
                      json={"message": "올 한 해 고마웠어요.", "headline": "끝까지 챙긴 한 해", "projects": [pid, "없는-과제"]}).json()
    assert saved["saved"] and saved["message"] == "올 한 해 고마웠어요." and saved["chosen"] == [pid] and saved["missing"] == []
    listing = owner.get("/api/yearcards", params={"year": "2026"}).json()
    row = next(p for p in listing["people"] if p["name"] == "가팀원")
    assert row["has_message"] and row["picked"] == 1
    printed = owner.get("/api/yearcards/cards", params={"year": "2026", "names": "가팀원,나팀원"}).json()["cards"]
    assert [c["name"] for c in printed] == ["가팀원", "나팀원"]


def test_message_limit_and_private(team):  # noqa: F811
    owner, member, viewer = team["owner"], team["member"], team["viewer"]
    too_long = owner.put("/api/yearcards/card", params={"name": "가팀원", "year": "2026"}, json={"message": "가" * 401})
    assert too_long.status_code == 400 and "400자" in too_long.json()["detail"]
    assert member.get("/api/yearcards", params={"year": "2026"}).status_code == 403          # 팀원 PC 에는 막힘
    assert viewer.get("/api/yearcards/card", params={"name": "가팀원", "year": "2026"}).status_code == 403
    assert owner.get("/api/yearcards", params={"year": "26"}).status_code == 422
