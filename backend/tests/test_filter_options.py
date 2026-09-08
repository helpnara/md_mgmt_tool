"""거르기 상자에는 **실제로 있는 것만** 선다 (TODO 96).

골라도 0건인 항목이 목록에 있으면, 사용자는 그것이 "없는 것" 인지 "거르기가 고장난 것"
인지 알 수 없다. 그래서 화면이 세우는 목록은 자료에서 나와야 한다.

세 자리에서 어긋나 있었다.

1. **연도** — 올해부터 5년 전까지를 그냥 세웠다. 홈과 팀원 역량은 이미 *과제가 있는 해*
   만 세우고 있었으니, 같은 자료를 두고 화면마다 말이 달랐다.
2. **태그** — `tag` 표는 한 번 쓴 이름을 지우지 않는다. 떼어 낸 태그도, 진행일지에만
   붙인 태그도 과제 거르기 상자에 남았다.
3. **그룹** — 홈의 그룹별 표는 *미지정* 줄을 세우고 `group=none` 으로 이어 주는데,
   정작 거르기 상자에는 그 선택지가 없었다.

**고정 어휘(상태·속성·역량 구분)는 좁히지 않는다.** 그것은 자료가 아니라 사용자가 고르는
말이고, "보류인 게 있나?" 에 *없다* 고 답하는 것도 답이다.
"""
from __future__ import annotations

from datetime import date


def make(client, title, **extra):
    return client.post("/api/projects", json={"title": title, **extra}).json()


def meta(client) -> dict:
    return client.get("/api/meta").json()


def this_year() -> str:
    return str(date.today().year)


# ── 연도 ─────────────────────────────────────────────────────────────────────

def test_years_are_empty_before_any_project(client):
    assert meta(client)["years"] == []


def test_years_are_only_the_years_that_have_projects(client):
    make(client, "지난해 과제", start_date="2025-05-05")
    make(client, "올해 과제")
    # 최근 것부터. 2024·2023 처럼 과제가 없는 해는 서지 않는다.
    assert meta(client)["years"] == [this_year(), "2025"]


def test_years_follow_the_project_number_not_the_start_date(client):
    project = make(client, "번호는 올해, 시작일은 지난해")
    client.patch(f"/api/projects/{project['id']}", json={"start_date": "2025-01-01"})
    # 연도를 가르는 기준은 번호 앞 네 자리다 (DESIGN 5.8). 목록도 같은 기준이어야 한다.
    assert meta(client)["years"] == [this_year()]


def test_moving_a_project_moves_the_year_out_of_the_list(client):
    project = make(client, "뒤늦게 등록한 지난해 과제")
    client.patch(f"/api/projects/{project['id']}", json={"start_date": "2025-01-01"})
    client.post(f"/api/projects/{project['id']}/year-fix")
    assert meta(client)["years"] == ["2025"]


# ── 태그 ─────────────────────────────────────────────────────────────────────

def test_a_tag_taken_off_every_project_leaves_the_filter(client):
    project = make(client, "태그 붙은 과제", tags=["공정", "수명평가"])
    assert meta(client)["project_tags"] == ["공정", "수명평가"]

    client.patch(f"/api/projects/{project['id']}", json={"tags": ["공정"]})
    # `tag` 표에는 남아 있어도, 거르기 상자에 세우면 골라도 0건이다.
    assert meta(client)["project_tags"] == ["공정"]


def test_an_entry_only_tag_does_not_stand_in_the_project_filter(client):
    project = make(client, "과제", tags=["공정"])
    client.post(f"/api/projects/{project['id']}/entries", json={
        "date": "2026-03-10", "title": "시험", "body": "## 내용\n\n돌려 봤다\n",
        "tags": ["설비"],
    })
    data = meta(client)
    # 과제를 거르는 상자에는 과제에 붙은 것만.
    assert data["project_tags"] == ["공정"]
    # 자동완성은 어디든 쓰이는 이름을 안다 — 진행일지에 태그를 달 때 필요하다.
    assert data["tags"] == ["공정", "설비"]


def test_the_autocomplete_list_drops_tags_nothing_wears(client):
    project = make(client, "과제", tags=["오타태그"])
    client.patch(f"/api/projects/{project['id']}", json={"tags": []})
    data = meta(client)
    assert data["tags"] == []
    assert data["project_tags"] == []


# ── 그룹 ─────────────────────────────────────────────────────────────────────

def test_the_none_group_is_offered_only_when_something_has_no_group(client):
    make(client, "그룹 있는 과제", group="회의체")
    assert meta(client)["groups"] == ["회의체"]
    assert meta(client)["groups_none"] is False

    make(client, "그룹 없는 과제")
    assert meta(client)["groups_none"] is True
    # 그 선택지가 실제로 걸러야 한다 — 상자에만 있고 안 걸리면 더 나쁘다.
    listed = client.get("/api/projects", params={"group": "none"}).json()
    assert [row["title"] for row in listed] == ["그룹 없는 과제"]


# ── 좁히지 않는 것 ───────────────────────────────────────────────────────────

def test_the_fixed_vocabularies_are_not_narrowed_to_the_data(client):
    make(client, "진행중 과제 하나", status="in_progress")
    data = meta(client)
    # 상태·속성·역량 구분은 사용자가 고르는 말이다. 하나도 없는 상태를 골라
    # "없다" 는 답을 얻는 것도 거르기의 쓸모다.
    assert [item["key"] for item in data["statuses"]].count("on_hold") == 1
    assert len(data["types"]) > 1
    assert len(data["activity_kinds"]) > 1


# ── 자료에서 나오던 것들은 그대로 ────────────────────────────────────────────

def test_owner_and_partner_and_audience_lists_still_come_from_the_data(client):
    make(client, "과제", owners=["권경락"], partners=[{"team": "설비기술팀", "people": "김철수"}])
    data = meta(client)
    assert data["owners"] == ["권경락"]
    assert data["partner_teams"] == ["설비기술팀"]
    assert data["partner_people"] == ["김철수"]
    # 아직 보고가 없으면 피보고자 목록도 비어 있다.
    assert data["audiences"] == []
