"""지금 고치는 중 (TODO 317) — 메모리 알림 · 다른 창만 · 시간 지나면 사라짐 · 팀원 PC 도 알림."""
from __future__ import annotations

from app.services import presence
from tests.test_contributions import team  # noqa: F401


def test_beat_others_leave_and_expire(team, monkeypatch):  # noqa: F811
    owner, member, pid = team["owner"], team["member"], team["shared"]
    presence.reset()
    target = f"overview:{pid}"
    assert owner.post("/api/presence/beat", json={"target": target, "client": "owner-1"}).json()["others"] == []
    got = member.post("/api/presence/beat", json={"target": target, "client": "member-1"}).json()["others"]
    assert [o["name"] for o in got] == ["팀장"]                       # 팀원 PC 가 보면 팀장이 고치는 중
    assert [o["name"] for o in owner.post("/api/presence/beat", json={"target": target, "client": "owner-1"}).json()["others"]] == ["가팀원"]
    items = owner.get("/api/presence", params={"prefix": pid, "client": "owner-1"}).json()["items"]
    assert items == [{"target": target, "people": [{"name": "가팀원", "minutes": 0}]}]
    member.post("/api/presence/leave", json={"target": target, "client": "member-1"})
    assert owner.get("/api/presence", params={"prefix": pid, "client": "owner-1"}).json()["items"] == []
    # 45초 알림이 없으면 사라진다
    member.post("/api/presence/beat", json={"target": target, "client": "member-1"})
    import time as real_time
    later = real_time.time() + presence.TTL + 1
    monkeypatch.setattr(presence.time, "time", lambda: later)
    assert presence.listing(pid, "owner-1") == []
    # 읽기 전용 PC 는 알릴 수 없다(고치지 못하므로)
    assert team["viewer"].post("/api/presence/beat", json={"target": target, "client": "viewer-1"}).status_code in (403, 404)
