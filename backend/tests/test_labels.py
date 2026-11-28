"""그룹 · 과제 태그 이름 바꾸기 · 합치기 (TODO 341)."""
from __future__ import annotations


def test_group_and_tag_rename_and_merge(client):
    a = client.post("/api/projects", json={"title": "가", "status": "in_progress", "group": "MES", "tags": ["mes", "데이터"]}).json()
    b = client.post("/api/projects", json={"title": "나", "status": "in_progress", "group": "MES 고도화", "tags": ["MES"]}).json()
    usage = client.get("/api/settings/labels/usage").json()["usage"]
    assert {row["value"] for row in usage["group"]} == {"MES", "MES 고도화"}
    # 그룹 합치기
    done = client.post("/api/settings/labels/rename", json={"kind": "group", "old": "MES 고도화", "new": "MES"}).json()
    assert done["merged"] is True and done["projects"] == 1
    assert client.get(f"/api/projects/{b['id']}").json()["group"] == "MES"
    # 태그 표기만 바꾸기(대소문자는 이미 한 태그) — 보이는 표기가 바뀐다
    done = client.post("/api/settings/labels/rename", json={"kind": "tag", "old": "mes", "new": "MES"}).json()
    assert done["merged"] is False and done["projects"] == 2
    tags = {row["value"]: row["projects"] for row in client.get("/api/settings/labels/usage").json()["usage"]["tag"]}
    assert tags.get("MES") == 2 and "mes" not in tags
    # 다른 낱말끼리 합치기 — 둘 다 단 과제에는 하나만
    client.patch(f"/api/projects/{a['id']}", json={"tags": ["MES", "데이터", "데이타"]})
    done = client.post("/api/settings/labels/rename", json={"kind": "tag", "old": "데이타", "new": "데이터"}).json()
    assert done["merged"] is True
    assert client.get(f"/api/projects/{a['id']}").json()["tags"] == ["MES", "데이터"]
    assert client.post("/api/settings/labels/rename", json={"kind": "group", "old": "MES", "new": "MES"}).status_code == 400
