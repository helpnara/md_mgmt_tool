"""검색 고도화 1차 — 여러 낱말 · 구절 · 빼기 · 칸 지정 · 관련도 · 담당과 역할 · 팀원역량 (TODO 254).

과제 · 사람은 모두 지어낸 것이다.
"""
from __future__ import annotations

from app.services.search import parse_query


def _find(client, q, **extra):
    return client.get("/api/search", params={"q": q, **extra}).json()


def _seed(client):
    client.put("/api/people", json={"people": [{"name": "김민준"}, {"name": "이서연"}]})
    a = client.post("/api/projects", json={"title": "출하 검사 자동 판정", "owners": ["김민준"], "tags": ["품질"],
                                           "status": "in_progress", "start_date": "2026-02-01"}).json()["id"]
    b = client.post("/api/projects", json={"title": "설비 점검 주기", "owners": ["이서연"], "tags": ["설비"],
                                           "status": "done", "start_date": "2025-03-01",
                                           "body": "## 배경\n\n출하 검사 결과로 점검 주기를 정했다.\n"}).json()["id"]
    client.post(f"/api/projects/{a}/entries", json={"date": "2026-03-02", "title": "판정 기준 회의", "body": "불량 유형을 형태로 다시 나눔"})
    client.post(f"/api/projects/{b}/entries", json={"date": "2025-04-02", "title": "점검표 정리", "body": "불량 유형 집계 표"})
    client.put(f"/api/projects/{a}/contributions/김민준", json={"role": "주관", "did": "- 두 단계 판정 설계", "skills": ["Python"]})
    client.post("/api/activities", json={"person": "이서연", "kind": "education", "title": "품질 데이터 분석 과정",
                                         "date": "2026-05-10", "takeaway": "관리도 읽는 법"})
    return a, b


def test_parse_query_parts():
    assert parse_query('출하 "판정 기준" -설비 담당:김민준 태그:품질 상태:진행중 연도:2026 종류:일지') == {
        "words": ["출하", "판정 기준"], "excludes": ["설비"],
        "fields": {"owner": ["김민준"], "tag": ["품질"], "status": ["진행중"], "year": ["2026"]}, "kinds": ["entries"]}
    assert parse_query("모르는:칸")["words"] == ["모르는:칸"]                      # 모르는 칸 이름은 낱말
    assert parse_query('담당:"김 민준"')["fields"] == {"owner": ["김 민준"]}


def test_many_words_mean_all_and_exclude(client):
    a, b = _seed(client)
    both = [p["id"] for p in _find(client, "출하 검사")["projects"]]
    assert set(both) == {a, b}
    assert [p["id"] for p in _find(client, "출하 판정")["projects"]] == [a]              # 둘 다 든 것만
    assert [p["id"] for p in _find(client, "출하 -점검")["projects"]] == [a]             # 빼기
    assert _find(client, '"검사 결과로"')["projects"][0]["id"] == b                     # 구절


def test_relevance_puts_title_hit_first_and_recent_option(client):
    a, b = _seed(client)
    found = [p["id"] for p in _find(client, "출하 검사")["projects"]]
    assert found[0] == a                                                                 # 제목에 든 과제가 먼저(본문만 든 것보다)
    recent = [p["id"] for p in _find(client, "출하 검사", sort="recent")["projects"]]
    assert set(recent) == {a, b}
    assert client.get("/api/search", params={"q": "x", "sort": "엉뚱"}).status_code == 422


def test_field_filters(client):
    a, b = _seed(client)
    assert [p["id"] for p in _find(client, "담당:김민준")["projects"]] == [a]            # 칸만으로도 과제를 찾는다
    assert [p["id"] for p in _find(client, "태그:설비")["projects"]] == [b]
    assert [p["id"] for p in _find(client, "상태:완료")["projects"]] == [b]
    assert [p["id"] for p in _find(client, "연도:2026 담당:김민준")["projects"]] == [a]
    entries = _find(client, "불량 유형 연도:2025")["entries"]
    assert [e["project_id"] for e in entries] == [b]
    only = _find(client, "불량 종류:일지")
    assert only["projects"] == [] and len(only["entries"]) == 2


def test_contributions_and_activities_are_found(client):
    a, _ = _seed(client)
    hit = _find(client, "두 단계 판정")["contributions"]
    assert [(c["project_id"], c["name"]) for c in hit] == [(a, "김민준")]
    assert _find(client, "Python 담당:김민준")["contributions"][0]["role"] == "주관"
    act = _find(client, "관리도")["activities"]
    assert act and act[0]["person"] == "이서연" and act[0]["title"] == "품질 데이터 분석 과정"
    assert _find(client, "관리도 종류:과제")["activities"] == []
