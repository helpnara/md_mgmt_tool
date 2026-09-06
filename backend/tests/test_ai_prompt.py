"""AI 요약 프롬프트 (TODO 71 · T14 (가)안).

핵심은 **도구가 AI 를 부르지 않는다**는 것이다. 여기서 지키는 것은 셋이다.
  1. 붙여넣을 글에 과제·기간·진행 내용이 빠짐없이 담긴다
  2. 앞뒤에 붙는 글을 설정에서 바꿀 수 있다
  3. 설정을 비우면 기본 지시문이 쓰인다
"""
from __future__ import annotations


def _project(client, title="고강도 열연강판 소재 개발"):
    return client.post("/api/projects", json={"title": title, "status": "in_progress"}).json()


def _report(client, project_id, date="2026-09-08", audience="전사 주요업무 보고"):
    return client.post(
        f"/api/projects/{project_id}/reports/draft",
        json={"report_date": date, "audience": audience},
    ).json()


def test_prompt_carries_the_facts_and_the_body(client):
    project = _project(client)
    client.post(
        f"/api/projects/{project['id']}/entries",
        json={"date": "2026-09-02", "title": "1차 압연 시험", "body": "## 내용\n\n인장강도 780MPa 확보\n"},
    )
    report = _report(client, project["id"])

    text = client.get(f"/api/reports/{report['id']}/ai-prompt").json()["text"]

    assert "고강도 열연강판 소재 개발" in text
    assert project["id"] in text
    assert "보고일: 2026-09-08" in text
    assert "피보고자: 전사 주요업무 보고" in text
    # 진행 내용이 통째로 실려야 요약할 거리가 있다.
    assert "인장강도 780MPa 확보" in text
    assert "--- 진행 내용 ---" in text


def test_default_instruction_is_used_when_the_setting_is_empty(client):
    from app.services.ai_prompt import DEFAULT_PREFIX

    report = _report(client, _project(client)["id"])
    text = client.get(f"/api/reports/{report['id']}/ai-prompt").json()["text"]
    assert text.startswith(DEFAULT_PREFIX.split("\n")[0])


def test_the_user_prompt_wins_and_sits_front_and_back(client):
    """사용자가 쓰던 프롬프트를 그대로 넣을 자리다. 위·아래 둘 다."""
    client.put(
        "/api/settings",
        json={"ai_prompt_prefix": "우리 팀 보고 서식대로 요약해줘.", "ai_prompt_suffix": "표로 만들어줘."},
    )
    report = _report(client, _project(client)["id"])
    text = client.get(f"/api/reports/{report['id']}/ai-prompt").json()["text"]

    assert text.startswith("우리 팀 보고 서식대로 요약해줘.")
    assert text.rstrip().endswith("표로 만들어줘.")
    # 기본 지시문은 밀려난다 — 둘이 겹쳐 나오면 AI 가 무엇을 따를지 알 수 없다.
    assert "3~5줄로 요약해 주세요" not in text


def test_empty_body_says_so_instead_of_going_silent(client):
    """진행 내용이 없는 채로 복사하면, 붙여넣은 쪽에서 이유를 알 수 있어야 한다."""
    project = _project(client)
    report = _report(client, project["id"])
    client.patch(f"/api/reports/{report['id']}", json={"body": "  "})

    text = client.get(f"/api/reports/{report['id']}/ai-prompt").json()["text"]
    assert "(진행 내용이 비어 있습니다)" in text


def test_missing_report_is_a_404(client):
    assert client.get("/api/reports/999999/ai-prompt").status_code == 404
