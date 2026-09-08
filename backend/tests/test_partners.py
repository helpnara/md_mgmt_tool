"""유관부서와 그쪽 담당자 (TODO 92).

과제는 대개 두 팀 이상이 함께 하고, 팀마다 담당자가 여럿이다. 그 사실을 과제 정보에
남기고 **팀 이름으로도 사람 이름으로도 찾을 수 있어야** 한다.

이 파일이 지키는 약속 하나 — **팀과 사람을 한 문자열로 묶지 않는다.**
"설비기술팀: 김철수, 박민수" 처럼 두면 집계도 검색도 그 문자열을 다시 쪼개야 하고,
쪼개는 규칙이 어긋나는 순간 없는 사람이 생긴다 (TODO 74 에서 겪었다).
"""
from __future__ import annotations


def make(client, title, partners=None, **extra):
    body = {"title": title, **extra}
    if partners is not None:
        body["partners"] = partners
    return client.post("/api/projects", json=body).json()


def test_a_project_keeps_several_teams_each_with_several_people(client):
    project = make(client, "전고체 파일럿", partners=[
        {"team": "설비기술팀", "people": "김철수, 박민수"},
        {"team": "품질보증팀", "people": "이영희"},
    ])
    assert project["partners"] == [
        {"team": "설비기술팀", "people": ["김철수", "박민수"]},
        {"team": "품질보증팀", "people": ["이영희"]},
    ]
    # 다시 읽어도 같다 — 파일이 원본이고 색인은 파생물이다.
    again = client.get(f"/api/projects/{project['id']}").json()
    assert again["partners"] == project["partners"]


def test_people_are_split_by_the_server_not_the_screen(client):
    """화면만 고치면 API 를 직접 부르는 길로 같은 사고가 다시 난다 (TODO 74)."""
    project = make(client, "쉼표 확인", partners=[{"team": "설비기술팀", "people": "김철수,박민수;최우진"}])
    assert project["partners"][0]["people"] == ["김철수", "박민수", "최우진"]
    # "김철수,박민수" 한 덩이가 사람 하나로 굳으면 안 된다.
    assert client.get("/api/meta").json()["partner_people"] == ["김철수", "박민수", "최우진"]


def test_a_team_without_a_contact_is_still_recorded(client):
    """팀은 정해졌는데 담당자는 나중에 정해지는 일이 흔하다."""
    project = make(client, "담당자 미정", partners=[{"team": "구매팀", "people": ""}])
    assert project["partners"] == [{"team": "구매팀", "people": []}]
    # 팀만 적어 두어도 그 팀으로 찾을 수 있어야 한다.
    assert [row["id"] for row in client.get("/api/projects", params={"partner": "구매팀"}).json()] == [
        project["id"]
    ]


def test_the_same_team_written_twice_becomes_one_row(client):
    """두 줄로 적었다고 표와 검색에서 두 번 세면 안 된다."""
    project = make(client, "중복 입력", partners=[
        {"team": "설비기술팀", "people": "김철수"},
        {"team": "설비기술팀", "people": "박민수"},
    ])
    assert project["partners"] == [{"team": "설비기술팀", "people": ["김철수", "박민수"]}]


def test_the_list_filters_by_team_and_by_person(client):
    first = make(client, "과제 하나", partners=[
        {"team": "설비기술팀", "people": "김철수, 박민수"},
        {"team": "품질보증팀", "people": "이영희"},
    ])
    second = make(client, "과제 둘", partners=[{"team": "설비기술팀", "people": "최우진"}])
    make(client, "유관부서 없음")

    def ids(value):
        return {row["id"] for row in client.get("/api/projects", params={"partner": value}).json()}

    assert ids("설비기술팀") == {first["id"], second["id"]}   # 팀으로
    assert ids("품질보증팀") == {first["id"]}
    assert ids("김철수") == {first["id"]}                      # 사람으로
    assert ids("최우진") == {second["id"]}
    assert ids("없는팀") == set()


def test_search_finds_projects_by_team_or_by_contact(client):
    project = make(client, "검색 확인", partners=[{"team": "설비기술팀", "people": "박민수"}])
    make(client, "관계 없는 과제")

    for query in ("설비기술팀", "박민수"):
        found = client.get("/api/search", params={"q": query}).json()["projects"]
        assert [row["id"] for row in found] == [project["id"]], f"'{query}' 로 찾지 못했다"


def test_editing_replaces_the_whole_set(client):
    """부서를 지웠으면 지워져야 한다 — 색인에 유령이 남으면 안 된다."""
    project = make(client, "고쳐 쓰기", partners=[
        {"team": "설비기술팀", "people": "김철수"},
        {"team": "품질보증팀", "people": "이영희"},
    ])
    client.patch(
        f"/api/projects/{project['id']}",
        json={"partners": [{"team": "구매팀", "people": "정우성"}]},
    )
    after = client.get(f"/api/projects/{project['id']}").json()
    assert after["partners"] == [{"team": "구매팀", "people": ["정우성"]}]
    assert client.get("/api/projects", params={"partner": "설비기술팀"}).json() == []
    assert client.get("/api/search", params={"q": "김철수"}).json()["projects"] == []


def test_the_markdown_file_stays_readable(client, vault_dir):
    """이 도구가 없어도 읽히는 것이 첫 번째 약속이다."""
    project = make(client, "파일 확인", partners=[{"team": "설비기술팀", "people": "김철수, 박민수"}])
    path = next((vault_dir / "projects").glob("*파일-확인*/index.md"))
    text = path.read_text(encoding="utf-8")
    assert "team: 설비기술팀" in text
    assert "- 김철수" in text and "- 박민수" in text
    # 재색인해도 같은 값이 나온다 (파일이 원본).
    client.post("/api/reindex")
    assert client.get(f"/api/projects/{project['id']}").json()["partners"] == project["partners"]


def test_meta_offers_teams_and_people_for_the_filter(client):
    make(client, "메타 확인", partners=[
        {"team": "품질보증팀", "people": "이영희"},
        {"team": "설비기술팀", "people": "김철수"},
    ])
    meta = client.get("/api/meta").json()
    assert meta["partner_teams"] == ["설비기술팀", "품질보증팀"]   # 이름순
    assert meta["partner_people"] == ["김철수", "이영희"]


def test_projects_without_partners_are_unaffected(client):
    project = make(client, "예전 과제")
    assert project["partners"] == []
    assert client.get("/api/meta").json()["partner_teams"] == []
