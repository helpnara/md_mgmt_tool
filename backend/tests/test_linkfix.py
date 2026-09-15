"""이미 쌓인 문서의 깨진 첨부 링크 정리 (TODO 116)."""
from __future__ import annotations

from tests.test_attachments import make_png, setup_entry, upload

BROKEN = "![측정 결과.png](../assets/2026-09-03/001-측정 결과.png)"
FIXED = "![측정 결과.png](<../assets/2026-09-03/001-측정 결과.png>)"


def _entry_with_broken_link(client):
    project_id, entry_id = setup_entry(client)
    upload(client, entry_id, "측정 결과.png", make_png())
    # 114 이전에 들어간 모양 그대로 — 감싸지 않은 링크.
    client.patch(f"/api/entries/{entry_id}", json={"body": f"결과\n\n{BROKEN}\n"})
    return project_id, entry_id


def test_scan_counts_without_changing_anything(client):
    project_id, entry_id = _entry_with_broken_link(client)
    report = client.get("/api/maintenance/link-fix").json()
    assert report["applied"] is False
    assert report["document_count"] == 1 and report["link_count"] == 1
    assert report["documents"][0]["kind"] == "entry"
    assert BROKEN in client.get(f"/api/entries/{entry_id}").json()["body"]
    # 감싸지 않은 링크는 고아로 보인다 — 고칠 이유가 그것이다.
    assert client.get(f"/api/projects/{project_id}/attachments").json()["orphan_count"] == 1


def test_apply_wraps_links_and_attachment_is_no_longer_orphan(client):
    project_id, entry_id = _entry_with_broken_link(client)
    report = client.post("/api/maintenance/link-fix", json={}).json()
    assert report["applied"] is True and report["link_count"] == 1
    body = client.get(f"/api/entries/{entry_id}").json()["body"]
    assert FIXED in body and BROKEN not in body
    assert client.get(f"/api/projects/{project_id}/attachments").json()["orphan_count"] == 0
    # 두 번째는 고칠 것이 없다.
    assert client.get("/api/maintenance/link-fix").json()["document_count"] == 0


def test_frozen_reports_are_skipped_unless_asked(client):
    project_id, entry_id = _entry_with_broken_link(client)
    draft = client.post(f"/api/projects/{project_id}/reports/draft", json={"report_date": "2026-09-05"}).json()
    # 초안이 만들어질 때는 이미 감싸 옮겨지므로, 옛 모양을 손으로 심는다.
    client.patch(f"/api/reports/{draft['id']}", json={"body": "## 요약\n\n![측정 결과.png](../../assets/2026-09-03/001-측정 결과.png)\n"})
    client.post(f"/api/reports/{draft['id']}/freeze")

    report = client.get("/api/maintenance/link-fix").json()
    assert report["document_count"] == 1 and report["skipped_frozen"] == 1

    with_frozen = client.get("/api/maintenance/link-fix", params={"include_frozen": "true"}).json()
    assert with_frozen["document_count"] == 2 and with_frozen["skipped_frozen"] == 0
    assert {d["kind"] for d in with_frozen["documents"]} == {"entry", "report"}

    client.post("/api/maintenance/link-fix", json={"include_frozen": True})
    body = client.get(f"/api/reports/{draft['id']}").json()["body"]
    assert "](<../../assets/2026-09-03/001-측정 결과.png>)" in body


def test_names_without_spaces_and_plain_text_are_left_alone(client):
    project_id, entry_id = setup_entry(client)
    saved = upload(client, entry_id, "그래프.png", make_png()).json()
    text = f"결과 (최종)\n\n{saved['markdown']}\n\n[외부](https://example.com/a b)\n"
    client.patch(f"/api/entries/{entry_id}", json={"body": text})
    assert client.get("/api/maintenance/link-fix").json()["document_count"] == 0
    client.post("/api/maintenance/link-fix", json={})
    assert client.get(f"/api/entries/{entry_id}").json()["body"].strip() == text.strip()
