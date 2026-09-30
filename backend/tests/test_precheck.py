"""접수 사전점검 체크리스트 (TODO 155).

지키는 약속:
  * 기본은 사용자가 준 다섯 분류 · 열 항목 — 100점 만점
  * 다 매기기 전에는 점수가 없다(평가 중 N/10) — 풀에서 견줄 수 없는 수를 만들지 않는다
  * 서버가 **지금의 체크리스트로** 채점해 그때의 이름·단계·점수·만점을 함께 적는다
  * 바꿔 저장할 때마다 검토 기록에 한 줄 — 사람이 쓴 기록 수에는 세지 않는다
  * 판정이 난 접수는 고칠 수 없다
  * 설정에서 항목을 바꾸면 이미 매긴 점수는 그대로, "다른 기준" 이라고 알린다. 만점이 100 이 아니면 환산
"""
from __future__ import annotations


def _items(client):
    return client.get("/api/meta").json()["precheck"]["items"]


def _answers(items, pick=0, count=None, note=None):
    rows = items if count is None else items[:count]
    return [{"group": i["group"], "item": i["item"], "choice": i["choices"][pick][0], "note": note} for i in rows]


def _intake(client, title="점검 대상"):
    return client.post("/api/intakes", json={"title": title}).json()["id"]


def test_default_checklist_is_the_given_table(client):
    meta = client.get("/api/meta").json()["precheck"]
    assert len(meta["items"]) == 10 and meta["max"] == 100
    assert [g for g in dict.fromkeys(i["group"] for i in meta["items"])] == ["필요성", "수익성", "구체성", "데이터", "기술성"]
    assert meta["thresholds"] == [80, 60]


def test_partial_has_no_score_and_full_scores(client):
    iid = _intake(client)
    items = _items(client)
    part = client.put(f"/api/intakes/{iid}/precheck", json={"items": _answers(items, count=7)}).json()["precheck"]
    assert (part["score"], part["rated"], part["total_items"]) == (None, 7, 10)
    row = client.get("/api/intakes").json()["items"][0]
    assert row["precheck_score"] is None and row["precheck_rated"] == 7

    full = client.put(f"/api/intakes/{iid}/precheck", json={"items": _answers(items, pick=1)}).json()
    # 7·7·7·7·7 + 5·5·5 + 5·5 = 35 + 15 + 10 = 60
    assert full["precheck"]["score"] == 60
    assert full["precheck"]["band"]["key"] == "fix"
    assert {g["group"]: g["score"] for g in full["precheck"]["groups"]} == {
        "필요성": 7, "수익성": 7, "구체성": 21, "데이터": 15, "기술성": 10}
    # 기록에 한 줄 — 사람이 쓴 검토 기록 수에는 세지 않는다
    titles = [log["title"] for log in full["logs"]]
    assert titles[0] == "(사전점검) 평가 중 7/10 → 60점"
    assert full["log_count"] == 0


def test_same_answers_do_not_log_again(client):
    iid = _intake(client)
    items = _answers(_items(client))
    client.put(f"/api/intakes/{iid}/precheck", json={"items": items})
    again = client.put(f"/api/intakes/{iid}/precheck", json={"items": items}).json()
    assert len([log for log in again["logs"] if log["title"].startswith("(사전점검)")]) == 1


def test_note_and_unknown_choice(client):
    iid = _intake(client)
    items = _items(client)
    saved = client.put(f"/api/intakes/{iid}/precheck", json={"items": _answers(items, note="9/12 회의")}).json()
    assert saved["precheck"]["items"][0]["note"] == "9/12 회의"
    bad = [{"group": items[0]["group"], "item": items[0]["item"], "choice": "없는 단계"}]
    response = client.put(f"/api/intakes/{iid}/precheck", json={"items": bad})
    assert response.status_code == 400


def test_closed_intake_cannot_be_rescored(client):
    iid = _intake(client)
    client.put(f"/api/intakes/{iid}/precheck", json={"items": _answers(_items(client))})
    client.post(f"/api/intakes/{iid}/status", json={"status": "rejected", "note": "올해는 안 한다"})
    response = client.put(f"/api/intakes/{iid}/precheck", json={"items": _answers(_items(client), pick=2)})
    assert response.status_code == 409
    assert client.get(f"/api/intakes/{iid}").json()["precheck"]["score"] == 100


def test_changed_checklist_keeps_old_score_and_normalizes(client):
    iid = _intake(client)
    client.put(f"/api/intakes/{iid}/precheck", json={"items": _answers(_items(client))})
    lines = "필요성 | 가 | 상=5, 하=1\n수익성 | 나 | 상=5, 하=1"
    assert client.put("/api/settings", json={"precheck_items": lines}).status_code == 200
    old = client.get(f"/api/intakes/{iid}").json()["precheck"]
    assert old["score"] == 100 and old["stale"] is True
    other = _intake(client, "새 기준")
    new = client.put(f"/api/intakes/{other}/precheck",
                     json={"items": [{"group": "필요성", "item": "가", "choice": "상"},
                                     {"group": "수익성", "item": "나", "choice": "하"}]}).json()["precheck"]
    assert (new["raw"], new["max"], new["score"]) == (6, 10, 60)   # 10점 만점 → 100점 환산
    # 빈 글은 기본 목록으로
    client.put("/api/settings", json={"precheck_items": ""})
    assert len(_items(client)) == 10


def test_settings_validation_and_thresholds(client):
    response = client.put("/api/settings", json={"precheck_items": "필요성 | 가 | 상"})
    assert response.status_code == 400 and "점수가 없습니다" in response.json()["detail"]
    assert client.put("/api/settings", json={"precheck_thresholds": [50, 70]}).status_code == 400
    assert client.put("/api/settings", json={"precheck_thresholds": [90, 70]}).status_code == 200
    iid = _intake(client)
    band = client.put(f"/api/intakes/{iid}/precheck", json={"items": _answers(_items(client), pick=1)}).json()
    assert band["precheck"]["band"]["key"] == "hold"   # 60 < 70


def test_pool_sort_and_project_link(client):
    items = _items(client)
    low, high, none = _intake(client, "낮음"), _intake(client, "높음"), _intake(client, "없음")
    client.put(f"/api/intakes/{low}/precheck", json={"items": _answers(items, pick=2)})
    client.put(f"/api/intakes/{high}/precheck", json={"items": _answers(items, pick=0)})
    titles = lambda **q: [row["title"] for row in client.get("/api/intakes", params=q).json()["items"]]
    assert titles(sort="precheck") == ["높음", "낮음", "없음"]
    assert titles(sort="precheck", order="asc") == ["낮음", "높음", "없음"]
    pid = client.post(f"/api/intakes/{high}/promote", json={}).json()["project_id"]
    link = client.get(f"/api/projects/{pid}").json()["intakes"][0]
    assert link["precheck_score"] == 100
