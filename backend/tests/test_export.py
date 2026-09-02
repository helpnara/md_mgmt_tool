from __future__ import annotations

import io
import zipfile

from PIL import Image


def make_png(color: str = "red") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (60, 40), color).save(buffer, "PNG")
    return buffer.getvalue()


def build_project(client):
    project = client.post(
        "/api/projects",
        json={"title": "리튬전지 수명평가", "group": "차세대전지", "tags": ["수명평가"],
              "start_date": "2026-03-02", "due_date": "2026-12-20"},
    ).json()
    client.patch(f"/api/projects/{project['id']}", json={"body": "## 배경\n\n수명 800회 목표."})

    first = client.post(
        f"/api/projects/{project['id']}/entries",
        json={"date": "2026-08-25", "title": "셀 조립", "body": "3종 조립 완료."},
    ).json()
    saved = client.post(
        f"/api/entries/{first['id']}/attachments",
        files={"file": ("측정그래프.png", make_png(), "image/png")},
    ).json()
    client.patch(f"/api/entries/{first['id']}", json={"body": f"3종 조립 완료.\n\n{saved['markdown']}"})
    client.post(
        f"/api/projects/{project['id']}/entries",
        json={"date": "2026-09-03", "title": "1차 측정", "body": "유지율 98.2%."},
    )
    return project


def test_merged_markdown_has_overview_and_entries_in_order(client):
    project = build_project(client)
    response = client.get(f"/api/projects/{project['id']}/export", params={"format": "md"})
    assert response.status_code == 200
    text = response.text

    assert text.startswith("# 리튬전지 수명평가")
    assert "상태: 진행중" in text and "그룹: 차세대전지" in text
    assert "## 배경" in text
    assert text.index("2026-08-25 셀 조립") < text.index("2026-09-03 1차 측정")


def test_download_filename_survives_hangul(client):
    project = build_project(client)
    response = client.get(f"/api/projects/{project['id']}/export", params={"format": "md"})
    disposition = response.headers["content-disposition"]
    # RFC 5987 이름과 함께, 그것을 모르는 도구를 위한 ASCII 대체 이름도 있어야 한다.
    assert "filename*=UTF-8''" in disposition
    assert "%EB%A6%AC%ED%8A%AC" in disposition  # '리튬'
    assert 'filename="2026-001' in disposition


def test_inline_export_embeds_images_in_one_file(client):
    project = build_project(client)
    text = client.get(
        f"/api/projects/{project['id']}/export", params={"format": "md", "assets": "inline"}
    ).text
    assert "data:image/png;base64," in text
    assert "](../assets/" not in text  # 남은 상대 링크가 없어야 파일 하나로 완결된다


def test_zip_export_keeps_relative_links_working(client):
    project = build_project(client)
    response = client.get(f"/api/projects/{project['id']}/export", params={"format": "zip"})
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = archive.namelist()

    md_name = next(name for name in names if name.endswith(".md"))
    text = archive.read(md_name).decode("utf-8")
    # 압축을 풀었을 때 md 옆에 assets/ 가 있고 링크가 그대로 맞아야 한다.
    assert "![측정그래프.png](assets/2026-08-25/001-측정그래프.png)" in text
    assert "assets/2026-08-25/001-측정그래프.png" in names


def test_export_bundles_the_file_used_for_reporting(client):
    """보고에 쓴 엑셀은 본문에 링크하지 않아도 함께 담겨야 한다."""
    project = build_project(client)
    report = client.post(
        f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-09-08"}
    ).json()
    client.post(
        f"/api/reports/{report['id']}/attachments",
        files={"file": ("주간보고.xlsx", b"PK\x03\x04", "application/octet-stream")},
    )
    client.post(f"/api/reports/{report['id']}/freeze")

    response = client.get(f"/api/projects/{project['id']}/export", params={"format": "zip"})
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    assert "reports/2026-09-08/assets/001-주간보고.xlsx" in archive.namelist()

    md_name = next(name for name in archive.namelist() if name.endswith(".md"))
    assert "보고 자료: 주간보고.xlsx" in archive.read(md_name).decode("utf-8")


def test_report_title_is_not_duplicated_with_its_date(client):
    project = build_project(client)
    report = client.post(
        f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-09-08"}
    ).json()
    client.post(f"/api/reports/{report['id']}/freeze")

    text = client.get(f"/api/projects/{project['id']}/export", params={"format": "md"}).text
    assert "2026-09-08 2026-09-08" not in text
    assert "**2026-09-08** 보고" in text


def test_export_includes_report_history(client):
    project = build_project(client)
    report = client.post(
        f"/api/projects/{project['id']}/reports/draft", json={"report_date": "2026-09-08"}
    ).json()
    client.patch(f"/api/reports/{report['id']}", json={"body": "## 보고 요약\n\n- B안 유지율 98.2%"})
    client.post(f"/api/reports/{report['id']}/freeze")

    text = client.get(f"/api/projects/{project['id']}/export", params={"format": "md"}).text
    assert "# 보고 이력" in text
    assert "2026-09-08" in text and "확정" in text
    assert "[보고] 2026-09-08" not in text  # 기본은 요약만

    full = client.get(
        f"/api/projects/{project['id']}/export",
        params={"format": "md", "include_reports_full": True},
    ).text
    assert "[보고] 2026-09-08" in full
    assert "B안 유지율 98.2%" in full


def test_html_export_is_self_contained(client):
    project = build_project(client)
    response = client.get(f"/api/projects/{project['id']}/export", params={"format": "html"})
    assert response.headers["content-type"].startswith("text/html")
    html = response.text
    assert "<h1>리튬전지 수명평가</h1>" in html
    assert "data:image/png;base64," in html


def test_backup_export_keeps_original_folder_structure(client):
    project = build_project(client)
    response = client.get(f"/api/projects/{project['id']}/export", params={"format": "backup"})
    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    assert "index.md" in names
    assert any(name.startswith("logs/") for name in names)
    assert "assets/2026-08-25/001-측정그래프.png" in names


def test_export_of_missing_project_is_404(client):
    assert client.get("/api/projects/9999-999/export").status_code == 404


def test_backup_covers_the_whole_vault_without_the_index(client, vault_dir):
    """설정 화면에서 내려받는 전체 백업 — 원본만 담고 다시 만들 수 있는 것은 뺀다."""
    import io as _io
    import zipfile as _zip

    build_project(client)
    client.post("/api/projects", json={"title": "두 번째 과제"})

    response = client.get("/api/backup")
    assert response.status_code == 200
    names = _zip.ZipFile(_io.BytesIO(response.content)).namelist()

    assert any("리튬전지-수명평가/index.md" in name for name in names)
    assert any("두-번째-과제/index.md" in name for name in names)
    assert any("assets/" in name for name in names)
    # 색인과 휴지통은 백업에 넣지 않는다 (파일에서 다시 만들어진다)
    assert not any(name.startswith(".index/") for name in names)
    assert not any(name.startswith(".trash/") for name in names)


def test_project_detail_carries_summary_numbers(client):
    """상단 요약에 쓸 수치가 상세 응답에 함께 온다."""
    project = build_project(client)
    detail = client.get(f"/api/projects/{project['id']}").json()

    assert detail["entry_count"] == 2
    assert detail["unreported_entries"] == 2
    assert detail["attachment_count"] == 1
    assert detail["attachment_bytes"] > 0
    assert detail["report_count"] == 0


def test_projects_can_be_sorted_by_time_since_last_report(client):
    """마지막 보고가 오래된 과제부터. 보고한 적 없는 과제가 맨 앞."""
    reported = client.post("/api/projects", json={"title": "보고한 과제"}).json()
    client.post(f"/api/projects/{reported['id']}/entries", json={"title": "기록"})
    report = client.post(
        f"/api/projects/{reported['id']}/reports/draft", json={"report_date": "2026-09-08"}
    ).json()
    client.post(f"/api/reports/{report['id']}/freeze")
    never = client.post("/api/projects", json={"title": "보고한 적 없는 과제"}).json()

    order = [item["id"] for item in client.get("/api/projects", params={"sort": "reported"}).json()]
    assert order.index(never["id"]) < order.index(reported["id"])
