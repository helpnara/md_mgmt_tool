"""과제 내보내기에 면담 · 팀원 역량 말고는 모두 (TODO 241)."""
from __future__ import annotations


def test_markdown_export_carries_every_project_field(client):
    client.put("/api/people", json={"people": [{"name": "가팀원"}, {"name": "나팀원"}]})
    first = client.post("/api/projects", json={"title": "1단계 수요 분석", "status": "done", "start_date": "2025-03-03",
                                               "completed_at": "2025-12-15", "owners": ["가팀원"]}).json()["id"]
    made = client.post("/api/projects", json={
        "title": "설비 데이터 자동 집계", "status": "done", "type": "smart", "start_date": "2026-03-02", "due_date": "2026-09-30",
        "completed_at": "2026-10-15", "group": "공정 데이터", "tags": ["집계", "자동화"], "owners": ["가팀원", "나팀원"],
        "partners": [{"team": "설비기술팀", "people": "김철수, 박민수"}, {"team": "품질팀"}],
        "effect_expected": 1.2, "effect_verified": 0.85, "outcome": "작업 시간 40% 단축",
        "nature": "현장적용", "category": "예측/분류모델 개발", "delivery": "현업 자체 개발", "cost_kind": "변동비",
        "predecessors": [first], "no_report": True, "created_by": "팀장",
    }).json()["id"]
    after = client.post("/api/projects", json={"title": "2단계 확대", "predecessors": [made]}).json()["id"]
    client.post(f"/api/projects/{made}/entries", json={"date": "2026-04-01", "title": "수집 범위 정리", "body": "로그 8종",
                                                       "author": "가팀원", "tags": ["범위"]})
    client.post("/api/meetings", json={"person": "가팀원", "date": "2026-05-01", "summary": "면담 내용 비밀"})
    client.post("/api/activities", json={"person": "가팀원", "date": "2026-05-10", "kind": "education", "title": "역량 교육 기록"})

    text = client.get(f"/api/projects/{made}/export?format=md").text
    for expected in [
        "## 과제 정보", "| 과제 번호 | " + made, "| 상태 | 완료 (완료일 2026-10-15) |", "| 기간 | 2026-03-02 ~ 2026-09-30 |",
        "성격: 현장적용 · 분류: 예측/분류모델 개발 · 수행 방식: 현업 자체 개발 · 비용구분: 변동비",
        "| 그룹 | 공정 데이터 |", "| 유관부서 | 설비기술팀 (김철수, 박민수) · 품질팀 |", "| 효과 (억원/년) | 기대 1.2 · 실증 0.85 |",
        "| 그 밖의 성과 | 작업 시간 40% 단축 |", f"| 선행 과제 | {first} 1단계 수요 분석 |", f"| 후속 과제 | {after} 2단계 확대 |",
        "| 보고 | 별도 보고 대상 아님 |", "| 등록 | 팀장 ·",
        "## 2026-04-01 수집 범위 정리", "> 작성: 가팀원 · 태그: 범위",
    ]:
        assert expected in text, expected
    # 면담 · 팀원 역량은 넣지 않는다
    assert "면담 내용 비밀" not in text and "역량 교육 기록" not in text
    # 빈 칸은 줄째 뺀다 · 효과 비대상은 그렇게 적는다
    bare = client.post("/api/projects", json={"title": "빈 과제", "no_effect": True}).json()["id"]
    plain = client.get(f"/api/projects/{bare}/export?format=md").text
    assert "| 유관부서 |" not in plain and "| 효과 (억원/년) | 효과 금액으로 관리하지 않는 과제 |" in plain


def test_body_headings_are_one_level_down(client):
    """본문의 제목은 한 단계 내린다 (TODO 241) — 개요 · 진행일지의 `##` 가 묶는 제목과 같은 단계가 되지 않게. 코드 블록은 그대로."""
    made = client.post("/api/projects", json={"title": "제목 단계", "body": "## 배경\n\n본문\n\n```\n## 코드 안\n```\n\n###### 맨 아래"}).json()["id"]
    client.post(f"/api/projects/{made}/entries", json={"date": "2026-04-01", "title": "일지", "body": "## 내용\n\n- 한 일"})
    text = client.get(f"/api/projects/{made}/export?format=md").text
    assert "## 과제 개요\n\n### 배경" in text
    assert "## 코드 안" in text and "### 코드 안" not in text
    assert "###### 맨 아래" in text
    assert "## 2026-04-01 일지\n\n### 내용" in text
