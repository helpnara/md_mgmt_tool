"""오류 기록.

지금까지 뭔가 잘못되면 흔적이 남지 않았다. 여기서 지키는 것은 넷이다.
  · 실패한 동작은 사유와 함께 남는다
  · 성공한 동작은 파일에 쌓이지 않는다 (직전 맥락으로만 쓴다)
  · 과제 내용은 담지 않는다
  · 기록에 실패해도 사용자의 동작을 막지 않는다
"""
from __future__ import annotations

import json

from app.services import errorlog


def logs_dir(vault_dir):
    return vault_dir / ".logs"


def entries(vault_dir):
    files = sorted(logs_dir(vault_dir).glob("error-*.log"))
    lines = [line for path in files for line in path.read_text(encoding="utf-8").splitlines()]
    return [json.loads(line) for line in lines if line.strip()]


def test_nothing_is_written_while_everything_works(client, vault_dir):
    client.get("/api/dashboard")
    client.post("/api/projects", json={"title": "과제", "status": "in_progress"})
    assert entries(vault_dir) == []


def test_a_refused_request_is_recorded_with_its_reason(client, vault_dir):
    """숫자만으로 된 팀 코드는 거절된다(400). 무엇을 하다 왜 막혔는지 남아야 한다."""
    client.put("/api/settings", json={"project_code": "12"})

    logged = entries(vault_dir)
    assert len(logged) == 1
    assert logged[0]["action"] == "PUT /api/settings"
    assert logged[0]["status"] == 400
    assert "숫자" in logged[0]["detail"]


def test_a_missing_thing_is_not_an_error_worth_keeping(client, vault_dir):
    """404 는 흔하고 대개 문제가 아니다. 기록이 이런 줄로 차면 정작 볼 것을 못 본다."""
    assert client.get("/api/reports/9999").status_code == 404
    assert entries(vault_dir) == []


def test_the_three_actions_before_the_failure_come_along(client, vault_dir):
    """오류만 남기면 '왜 그 상태가 됐는지'를 알 수 없다."""
    client.get("/api/meta")
    client.get("/api/dashboard")
    client.get("/api/projects")
    client.put("/api/settings", json={"project_code": "99"})

    trail = entries(vault_dir)[0]["trail"]
    assert trail == ["GET /api/meta", "GET /api/dashboard", "GET /api/projects"]


def test_the_trail_keeps_only_the_last_three(client, vault_dir):
    for _ in range(6):
        client.get("/api/dashboard")
    client.put("/api/settings", json={"project_code": "7"})
    assert len(entries(vault_dir)[0]["trail"]) <= errorlog.TRAIL


def test_project_content_never_reaches_the_log(client, vault_dir):
    """이 파일 하나를 그대로 전달해 원인을 물을 수 있어야 한다. 내용이 담기면 못 한다."""
    client.post("/api/projects", json={"title": "대외비 소재 과제", "status": "in_progress"})
    client.put("/api/settings", json={"project_code": "1"})

    text = json.dumps(entries(vault_dir), ensure_ascii=False)
    assert "대외비" not in text


def test_recent_shows_the_newest_first(client):
    for code in ("1", "22", "333"):
        client.put("/api/settings", json={"project_code": code})

    items = client.get("/api/errors").json()["items"]
    assert len(items) == 3
    assert [item["at"] for item in items] == sorted((item["at"] for item in items), reverse=True)


def test_clearing_makes_room_to_reproduce_a_problem(client, vault_dir):
    client.put("/api/settings", json={"project_code": "1"})
    assert client.delete("/api/errors").json()["removed_files"] == 1
    assert client.get("/api/errors").json()["items"] == []
    # 비운 뒤에 난 것은 다시 남는다.
    client.put("/api/settings", json={"project_code": "2"})
    assert len(client.get("/api/errors").json()["items"]) == 1


def test_old_months_are_dropped(client, vault_dir):
    stale = logs_dir(vault_dir) / "error-2020-01.log"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text('{"at": "2020-01-01T00:00:00", "action": "옛날 것"}\n', encoding="utf-8")

    client.put("/api/settings", json={"project_code": "1"})  # 기록이 일어나면 정리도 함께
    assert not stale.exists()


def test_a_broken_line_does_not_hide_the_rest(client, vault_dir):
    client.put("/api/settings", json={"project_code": "1"})
    path = sorted(logs_dir(vault_dir).glob("error-*.log"))[0]
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{깨진 줄\n")
    client.put("/api/settings", json={"project_code": "2"})

    assert len(client.get("/api/errors").json()["items"]) == 2


def test_a_log_that_cannot_be_written_does_not_break_the_request(client, vault_dir, monkeypatch):
    """오류를 적다가 나는 오류 때문에 사용자의 동작이 막히면 본말이 뒤바뀐다."""
    def explode(*args, **kwargs):
        raise OSError("디스크 없음")

    monkeypatch.setattr("pathlib.Path.open", explode)
    # 거절 자체는 정상적으로 400 으로 돌아와야 한다.
    assert client.put("/api/settings", json={"project_code": "1"}).status_code == 400
