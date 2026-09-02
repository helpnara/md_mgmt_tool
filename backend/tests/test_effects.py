"""과제 효과 (억원/년).

기대효과와 실증효과는 시점이 다른 별개의 값이다. 한 칸에 담으면
"예상은 얼마였고 실제로 얼마였나"를 되짚을 수 없다.
비어 있는 것과 0인 것도 다른 뜻이다 — 전자는 "아직 안 정했다", 후자는 "효과가 없다".
"""
from __future__ import annotations


def make(client, **kwargs):
    payload = {"title": "효과 과제"}
    payload.update(kwargs)
    response = client.post("/api/projects", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_effects_round_trip_through_the_markdown_file(client, vault_dir):
    project = make(client, title="수율 개선", effect_expected=1.2)
    assert project["effect_expected"] == 1.2
    assert project["effect_verified"] is None

    raw = (vault_dir / "projects" / f"{project['id']}-수율-개선" / "index.md").read_text(
        encoding="utf-8"
    )
    assert "effect_expected: 1.2" in raw
    # 사람이 파일을 열었을 때도 읽히는 이름이어야 한다.
    assert "effect_verified:" in raw


def test_overview_template_asks_for_qualitative_effect_and_basis(client):
    project = make(client)
    body = client.get(f"/api/projects/{project['id']}").json()["body"]
    assert "## 정성적 효과" in body
    # 근거 없는 숫자는 보고 자리에서 방어하지 못한다.
    assert "## 효과 산출 근거" in body


def test_verified_effect_is_filled_in_later(client):
    project = make(client, effect_expected=1.2)
    updated = client.patch(
        f"/api/projects/{project['id']}", json={"effect_verified": 1.45}
    ).json()
    # 실증효과를 채워도 기대효과는 그대로 남아야 비교가 된다.
    assert updated["effect_expected"] == 1.2
    assert updated["effect_verified"] == 1.45


def test_empty_and_zero_are_different(client):
    blank = make(client, title="아직 미정")
    zero = make(client, title="효과 없음", effect_expected=0)
    assert blank["effect_expected"] is None
    assert zero["effect_expected"] == 0


def test_effect_can_be_cleared(client):
    project = make(client, effect_expected=1.2)
    cleared = client.patch(
        f"/api/projects/{project['id']}", json={"effect_expected": None}
    ).json()
    assert cleared["effect_expected"] is None


def test_rejects_negative_effect(client):
    response = client.post("/api/projects", json={"title": "음수", "effect_expected": -1})
    assert response.status_code == 400


def test_sorted_by_effect_uses_verified_first_and_puts_blanks_last(client):
    make(client, title="기대만 큼", effect_expected=5.0)
    make(client, title="실증으로 줄어듦", effect_expected=9.0, effect_verified=1.0)
    make(client, title="실증으로 늘어남", effect_expected=0.5, effect_verified=7.0)
    make(client, title="안 적음")

    titles = [
        item["title"] for item in client.get("/api/projects", params={"sort": "effect"}).json()
    ]
    # 실증효과가 있으면 그것을 기준으로 본다 (9.0을 기대했지만 실제 1.0인 과제는 뒤로).
    assert titles == ["실증으로 늘어남", "기대만 큼", "실증으로 줄어듦", "안 적음"]


def test_broken_effect_value_does_not_stop_indexing(client, vault_dir):
    """손으로 파일을 고쳐 숫자가 아닌 값이 들어와도 과제 전체가 사라지면 안 된다."""
    project = make(client, title="손으로 고침", effect_expected=1.2)
    index_md = vault_dir / "projects" / f"{project['id']}-손으로-고침" / "index.md"
    index_md.write_text(
        index_md.read_text(encoding="utf-8").replace("effect_expected: 1.2", "effect_expected: 많이"),
        encoding="utf-8",
    )

    assert client.post("/api/reindex").json()["problems"] == []
    again = client.get(f"/api/projects/{project['id']}").json()
    assert again["title"] == "손으로 고침"
    assert again["effect_expected"] is None


def test_attachment_can_be_added_to_the_project_itself(client, vault_dir):
    """효과 산출 근거(엑셀·PPT)는 특정 진행일지가 아니라 과제에 딸린 자료다."""
    project = make(client, title="근거 첨부")
    response = client.post(
        f"/api/projects/{project['id']}/attachments",
        files={"file": ("효과산출.xlsx", b"fake xlsx", "application/vnd.ms-excel")},
    )
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved["rel_path"].startswith("assets/과제/")
    # 개요 문서는 과제 폴더 바로 아래에 있으므로 링크에 ../ 가 붙지 않아야 한다.
    assert saved["markdown"] == "[효과산출.xlsx](assets/과제/001-효과산출.xlsx)"
    assert (vault_dir / "projects" / f"{project['id']}-근거-첨부" / saved["rel_path"]).exists()

    listed = client.get(f"/api/projects/{project['id']}/attachments").json()
    assert [item["orig_name"] for item in listed["items"]] == ["효과산출.xlsx"]


def test_upload_to_missing_project_is_404(client):
    response = client.post(
        "/api/projects/2099-999/attachments", files={"file": ("x.txt", b"x", "text/plain")}
    )
    assert response.status_code == 404
