"""과제 속성을 설정에서 더하고 빼고 고친다 (TODO 100).

속성은 오래 **코드에 박힌** 목록이었다. 팀마다 쓰는 말이 다르고, 하나 더하려면
개발자를 불러야 했다.

이 파일이 지키는 약속 셋.

1. **열쇠와 이름을 나눈다.** 과제 파일에 남는 것은 열쇠고 화면에 보이는 것은 이름이라,
   이름을 고쳐도 이미 만든 과제가 속성을 잃지 않는다.
2. **쓰고 있는 속성은 뺄 수 없다.** 빼면 그 과제들이 미지정이 된다.
3. **비워 두면 기본 여섯.** 예전 vault 가 그대로 열린다.
"""
from __future__ import annotations


def types(client) -> list[dict]:
    return client.get("/api/settings/project-types").json()["types"]


def labels(client) -> list[str]:
    return [item["label"] for item in types(client)]


def put(client, items):
    return client.put("/api/settings/project-types", json={"types": items})


def as_input(rows):
    return [{"key": item["key"], "label": item["label"]} for item in rows]


# ── 기본값 ───────────────────────────────────────────────────────────────────

def test_an_untouched_vault_gets_the_built_in_six(client):
    assert labels(client) == ["스마트과제", "R&D", "투자", "기획보고", "국책과제", "유지보수"]
    assert all(item["count"] == 0 for item in types(client))


# ── 더하기 ───────────────────────────────────────────────────────────────────

def test_a_new_type_can_be_added_and_used(client):
    put(client, as_input(types(client)) + [{"key": "", "label": "설비투자"}])
    assert "설비투자" in labels(client)

    key = next(item["key"] for item in types(client) if item["label"] == "설비투자")
    made = client.post("/api/projects", json={"title": "압연기 교체", "type": key})
    assert made.status_code == 201
    assert made.json()["type"] == key
    # 만들 수 있으면 걸러도 져야 한다.
    assert len(client.get("/api/projects", params={"type": key}).json()) == 1
    # 대시보드도 같은 목록을 본다.
    counts = {row["key"]: row["count"] for row in client.get("/api/dashboard").json()["types"]}
    assert counts[key] == 1


def test_a_new_type_gets_a_key_of_its_own(client):
    put(client, as_input(types(client)) + [{"key": "", "label": "설비 투자"}])
    key = next(item["key"] for item in types(client) if item["label"] == "설비 투자")
    # 한글은 그대로 두고 공백만 다듬는다 — 파일 안에 남는 값이라 읽을 수 있어야 한다.
    assert key == "설비-투자"


def test_a_name_that_differs_only_by_spaces_is_the_same_name(client):
    response = put(client, as_input(types(client)) + [
        {"key": "", "label": "설비투자"},
        {"key": "", "label": "  설비투자  "},
    ])
    # 화면에서 구분되지 않는 두 줄을 만들게 두면 어느 쪽을 골랐는지 알 수 없다.
    assert response.status_code == 400
    assert "같은 이름" in response.json()["detail"]


def test_the_same_name_twice_is_refused(client):
    response = put(client, as_input(types(client)) + [
        {"key": "", "label": "설비투자"}, {"key": "", "label": "설비투자"},
    ])
    assert response.status_code == 400
    assert "같은 이름" in response.json()["detail"]


def test_an_empty_name_is_refused(client):
    response = put(client, as_input(types(client)) + [{"key": "", "label": "   "}])
    assert response.status_code == 400
    assert "이름을 적어" in response.json()["detail"]


# ── 고치기 ───────────────────────────────────────────────────────────────────

def test_renaming_a_type_keeps_the_projects_that_use_it(client):
    client.post("/api/projects", json={"title": "설비 제어 SW 유지보수", "type": "maintenance"})

    rows = as_input(types(client))
    for item in rows:
        if item["key"] == "maintenance":
            item["label"] = "유지·보수"
    put(client, rows)

    # 열쇠는 그대로다 — 과제 파일에 남는 것이 그것이다.
    assert "유지·보수" in labels(client)
    project = client.get("/api/projects").json()[0]
    assert project["type"] == "maintenance"
    # 화면이 보는 이름만 바뀐다.
    meta = {item["key"]: item["label"] for item in client.get("/api/meta").json()["types"]}
    assert meta["maintenance"] == "유지·보수"


def test_the_order_is_kept_as_sent(client):
    rows = as_input(types(client))
    rows = [rows[-1], *rows[:-1]]           # 유지보수를 맨 앞으로
    put(client, rows)
    assert labels(client)[0] == "유지보수"
    # 거르기 상자·대시보드가 보는 목록도 같은 순서다.
    assert client.get("/api/meta").json()["types"][0]["label"] == "유지보수"


# ── 빼기 ─────────────────────────────────────────────────────────────────────

def test_an_unused_type_can_be_removed(client):
    rows = [item for item in as_input(types(client)) if item["key"] != "national"]
    put(client, rows)
    assert "국책과제" not in labels(client)
    # 없는 속성으로는 과제를 만들 수 없다.
    refused = client.post("/api/projects", json={"title": "국책", "type": "national"})
    assert refused.status_code == 400


def test_a_type_in_use_cannot_be_removed(client):
    client.post("/api/projects", json={"title": "국책 과제", "type": "national"})
    rows = [item for item in as_input(types(client)) if item["key"] != "national"]
    response = put(client, rows)
    assert response.status_code == 400
    assert "국책과제(1건)" in response.json()["detail"]
    # 아무것도 바뀌지 않았다.
    assert "국책과제" in labels(client)


def test_the_screen_is_told_how_many_projects_use_each_type(client):
    client.post("/api/projects", json={"title": "가", "type": "rnd"})
    client.post("/api/projects", json={"title": "나", "type": "rnd"})
    counts = {item["label"]: item["count"] for item in types(client)}
    assert counts["R&D"] == 2
    assert counts["투자"] == 0


def test_moving_the_projects_first_lets_the_type_go(client):
    made = client.post("/api/projects", json={"title": "국책 과제", "type": "national"}).json()
    client.patch(f"/api/projects/{made['id']}", json={"type": "rnd"})
    rows = [item for item in as_input(types(client)) if item["key"] != "national"]
    assert put(client, rows).status_code == 200
    assert "국책과제" not in labels(client)


def test_every_type_can_be_removed_if_nothing_uses_them(client):
    # 속성을 아예 안 쓰는 팀도 있다. **빈 목록도 정한 값**이라, 다음에 열어도 여섯이
    # 되살아나면 안 된다 (설정에 없는 것과 비운 것은 다르다).
    assert put(client, []).status_code == 200
    assert labels(client) == []
    assert client.get("/api/meta").json()["types"] == []


# ── 파일이 원본이다 ──────────────────────────────────────────────────────────

def test_an_unknown_type_in_a_file_is_blanked_in_the_index_but_kept_on_disk(client, vault_dir):
    made = client.post("/api/projects", json={"title": "과제", "type": "national"}).json()
    index_md = vault_dir / "projects" / f"{made['id']}-과제" / "index.md"
    assert "type: national" in index_md.read_text(encoding="utf-8")

    # 설정 파일을 손으로 고쳐 그 속성을 지운 상황을 만든다 (화면으로는 막혀 있다).
    from app.services import settings as settings_service

    settings_service.save({"project_types": [{"key": "rnd", "label": "R&D"}]})
    client.post("/api/reindex")

    # 색인에서는 미지정이지만 **파일은 그대로다.**
    assert client.get(f"/api/projects/{made['id']}").json()["type"] is None
    assert "type: national" in index_md.read_text(encoding="utf-8")
    # 목록에 없는 열쇠를 쓰는 과제가 있다는 사실은 설정 화면이 알아야 한다.
    orphans = client.get("/api/settings/project-types").json()["orphans"]
    assert orphans == []   # 색인이 비웠으므로 여기서는 잡히지 않는다


def test_settings_survive_a_reopen(client, vault_dir):
    put(client, as_input(types(client)) + [{"key": "", "label": "설비투자"}])
    stored = (vault_dir / "settings.json").read_text(encoding="utf-8")
    assert "설비투자" in stored
