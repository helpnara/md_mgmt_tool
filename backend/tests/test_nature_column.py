"""과제목록의 성격 칸 (TODO 159).

성격 열을 눌러 정렬하면 글자순이 아니라 **설정 목록의 순서**(연구과제/PoC → 현장적용 → 확대전개 → 기타)로
선다. 목록에 없는 값은 그 뒤에, 성격이 없는 과제는 어느 방향에서나 맨 뒤다.
"""


def _make(client, title, nature=None):
    body = {"title": title, "type": "smart"} if nature is not None else {"title": title}
    if nature is not None:
        body["nature"] = nature
    return client.post("/api/projects", json=body).json()["id"]


def _titles(client, **params):
    return [item["title"] for item in client.get("/api/projects", params={"sort": "nature", **params}).json()]


def test_nature_sort_follows_the_settings_list(client):
    _make(client, "확대", "확대전개")
    _make(client, "빈칸")
    _make(client, "PoC", "연구과제/PoC")
    _make(client, "현장", "현장적용")

    assert _titles(client) == ["PoC", "현장", "확대", "빈칸"]
    # 뒤집어도 빈 값은 맨 뒤에 남는다
    assert _titles(client, order="desc") == ["확대", "현장", "PoC", "빈칸"]
    assert _titles(client, order="asc") == ["PoC", "현장", "확대", "빈칸"]


def test_nature_sort_uses_the_edited_list_and_survives_odd_names(client):
    # 설정에 쉼표·따옴표·괄호가 든 이름을 적어도 정렬 구문이 깨지지 않는다
    odd = "현장 (1차), '시범'"
    saved = client.put("/api/settings", json={"classifications": {"nature": f"확대전개\n{odd}\n연구과제/PoC"}})
    assert saved.status_code == 200
    _make(client, "PoC", "연구과제/PoC")
    _make(client, "시범", odd)
    _make(client, "확대", "확대전개")

    assert _titles(client) == ["확대", "시범", "PoC"]


def test_list_rows_carry_the_nature(client):
    _make(client, "PoC", "연구과제/PoC")
    _make(client, "기획")
    rows = {item["title"]: item["nature"] for item in client.get("/api/projects").json()}
    assert rows == {"PoC": "연구과제/PoC", "기획": None}
