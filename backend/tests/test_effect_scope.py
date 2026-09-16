"""효과 금액 — 분모를 눌러 보기(TODO 124)와 효과성 관리 비대상(TODO 125).

홈이 적는 수와 그 수를 눌렀을 때 나오는 목록은 **같아야 한다**(DESIGN 5.8).
비대상은 금액으로 재지 않는 과제라 "완료했는데 실증효과 미입력" 에서 빠진다 —
줄지 않는 경고는 곧 안 보게 된다.
"""
from __future__ import annotations


def setup(client):
    """기대만 적은 것 · 둘 다 적은 것 · 완료인데 실증 없는 것 · 비대상(완료) 넷."""
    ids = {}
    ids["expected"] = client.post("/api/projects", json={
        "title": "기대만", "status": "in_progress", "effect_expected": 3.5}).json()["id"]
    ids["both"] = client.post("/api/projects", json={
        "title": "둘 다", "status": "done",
        "effect_expected": 2.0, "effect_verified": 1.5}).json()["id"]
    ids["missing"] = client.post("/api/projects", json={
        "title": "완료인데 실증 없음", "status": "done", "effect_expected": 1.0}).json()["id"]
    ids["exempt"] = client.post("/api/projects", json={
        "title": "유지보수", "status": "done", "type": "maintenance", "no_effect": True}).json()["id"]
    return ids


def test_the_flag_round_trips_through_the_file(client, vault_dir):
    ids = setup(client)
    assert client.get(f"/api/projects/{ids['exempt']}").json()["no_effect"] is True
    assert client.get(f"/api/projects/{ids['both']}").json()["no_effect"] is False
    index = next((vault_dir / "projects").glob(f"{ids['exempt']}*")) / "index.md"
    assert "no_effect: true" in index.read_text(encoding="utf-8")


def test_exempt_projects_leave_the_warning_alone(client):
    ids = setup(client)
    team = client.get("/api/home").json()["team"]
    # 완료 셋 중 실증이 빈 것은 둘이지만, 비대상 하나를 빼면 하나다.
    assert team["done"] == 3
    assert team["done_unverified"] == 1
    assert team["effect_managed"] == 3 and team["total"] == 4

    # 비대상 표시를 지우면 다시 잡힌다 — 뺀 것이지 없앤 것이 아니다.
    client.patch(f"/api/projects/{ids['exempt']}", json={"no_effect": False})
    assert client.get("/api/home").json()["team"]["done_unverified"] == 2


def test_the_denominators_match_what_the_list_filters(client):
    setup(client)
    team = client.get("/api/home").json()["team"]
    expected = client.get("/api/projects", params={"effect": "expected", "year": ""}).json()
    verified = client.get("/api/projects", params={"effect": "verified", "year": ""}).json()
    assert len(expected) == team["effect_expected_projects"] == 3
    assert len(verified) == team["effect_verified_projects"] == 1
    assert {p["title"] for p in verified} == {"둘 다"}


def test_the_unverified_number_matches_its_list(client):
    setup(client)
    team = client.get("/api/home").json()["team"]
    listed = client.get("/api/projects", params={
        "verified": "none", "status": "done", "no_effect": "only", "year": ""}).json()
    assert len(listed) == team["done_unverified"]
    assert [p["title"] for p in listed] == ["완료인데 실증 없음"]


def test_exempt_projects_can_be_listed_on_their_own(client):
    setup(client)
    only = client.get("/api/projects", params={"no_effect": "none", "year": ""}).json()
    assert [p["title"] for p in only] == ["유지보수"]


def test_old_files_without_the_flag_are_managed_by_default(client, vault_dir):
    """이 칸이 없던 때의 파일 — 없으면 **관리 대상**이다 (빼는 것은 사람이 정한다)."""
    project = client.post("/api/projects", json={"title": "옛 과제", "status": "done"}).json()
    index = next((vault_dir / "projects").glob(f"{project['id']}*")) / "index.md"
    text = index.read_text(encoding="utf-8").replace("no_effect: false\n", "")
    index.write_text(text, encoding="utf-8")
    client.post("/api/reindex")
    assert client.get(f"/api/projects/{project['id']}").json()["no_effect"] is False
    assert client.get("/api/home").json()["team"]["done_unverified"] == 1


def test_account_is_kept_even_though_the_screen_no_longer_shows_it(client):
    """계정 칸은 화면에서 뺐지만 파일의 값은 지우지 않는다 (TODO 126)."""
    client.put("/api/people", json={"people": [
        {"name": "권경락", "employee_id": "12345", "account": "kwon"},
    ]})
    # 화면은 이제 account 를 보내지 않는다.
    client.put("/api/people", json={"people": [{"name": "권경락", "employee_id": "12345"}]})
    person = client.get("/api/people").json()["people"][0]
    assert person["employee_id"] == "12345"
    assert person["account"] == "kwon"

    # 일부러 비우는 것은 그대로 받는다 — 안 보내는 것과 빈 값은 다른 뜻이다.
    client.put("/api/people", json={"people": [
        {"name": "권경락", "employee_id": "12345", "account": ""},
    ]})
    assert client.get("/api/people").json()["people"][0]["account"] == ""
