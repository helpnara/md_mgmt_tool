"""공백·괄호가 있는 파일 이름의 첨부 링크 (TODO 114).

`[이름](assets/측정 결과.png)` 은 공백에서 끊겨 링크가 깨진다. 목적지를 `<…>` 로 감싸고,
그 링크를 읽는 곳(참조 추적·보고 초안·내보내기)이 모두 감싼 모양을 이해해야 한다.
"""
from __future__ import annotations

from app.services.attachments import link_target, referenced_paths
from tests.test_attachments import make_png, setup_entry, upload


def test_link_target_wraps_only_when_needed():
    assert link_target("assets/001-a.png") == "assets/001-a.png"
    assert link_target("../assets/001-측정 결과.png") == "<../assets/001-측정 결과.png>"
    assert link_target("assets/001-보고서(최종).xlsx") == "<assets/001-보고서(최종).xlsx>"


def test_upload_with_spaces_returns_angled_markdown(client):
    _, entry_id = setup_entry(client)
    saved = upload(client, entry_id, "측정 결과 (최종).png", make_png()).json()
    assert saved["rel_path"] == "assets/2026-09-03/001-측정 결과 (최종).png"
    assert saved["markdown"] == "![측정 결과 (최종).png](<../assets/2026-09-03/001-측정 결과 (최종).png>)"


def test_angled_links_count_as_references_not_orphans(client):
    project_id, entry_id = setup_entry(client)
    linked = upload(client, entry_id, "쓰는 이미지.png", make_png("red")).json()
    upload(client, entry_id, "안 쓰는 이미지.png", make_png("blue"))
    client.patch(f"/api/entries/{entry_id}", json={"body": f"결과\n\n{linked['markdown']}"})

    summary = client.get(f"/api/projects/{project_id}/attachments").json()
    assert summary["orphan_count"] == 1
    assert [item["orig_name"] for item in summary["items"] if item["orphan"]] == ["안 쓰는 이미지.png"]


def test_referenced_paths_reads_both_shapes():
    body = "![a](../assets/x/001-a.png) [b](<../assets/x/002-b c.xlsx>) [ext](https://example.com/a b)"
    found = referenced_paths([(body, "logs")])
    assert found == {"assets/x/001-a.png", "assets/x/002-b c.xlsx"}


def test_report_draft_moves_angled_links_two_levels_up(client):
    project_id, entry_id = setup_entry(client)
    saved = upload(client, entry_id, "측정 결과.png", make_png()).json()
    client.patch(f"/api/entries/{entry_id}", json={"body": f"결과\n\n{saved['markdown']}"})
    draft = client.post(
        f"/api/projects/{project_id}/reports/draft", json={"report_date": "2026-09-05"}
    ).json()
    assert "](<../../assets/2026-09-03/001-측정 결과.png>)" in draft["body"]


def test_export_keeps_angled_links_readable(client):
    project_id, entry_id = setup_entry(client)
    saved = upload(client, entry_id, "측정 결과.png", make_png()).json()
    client.patch(f"/api/entries/{entry_id}", json={"body": f"결과\n\n{saved['markdown']}"})

    merged = client.get(f"/api/projects/{project_id}/export", params={"format": "md"}).text
    # 병합 문서는 과제 폴더 기준으로 옮겨진다 — 감싼 모양은 그대로다.
    assert "](<assets/2026-09-03/001-측정 결과.png>)" in merged

    inline = client.get(
        f"/api/projects/{project_id}/export", params={"format": "md", "assets": "inline"}
    ).text
    assert "data:image/png;base64," in inline
    assert "<../assets" not in inline
