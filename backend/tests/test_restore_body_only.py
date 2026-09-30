"""되돌리기는 본문만 (TODO 152) · 표 칸 안 줄바꿈 (148) · 접수 표 열 머리 정렬 (154).

개요 파일 하나에 본문과 과제 정보(과제명·상태·담당·기간·접수 번호 …)가 함께 있어, 파일을 통째로
되돌리면 *개요 글* 을 되돌리려다 과제명·상태까지 그때로 돌아갔다(폴더 이름은 새 이름 그대로).
"""
from __future__ import annotations


def _versions(client, path):
    return client.get("/api/versions", params={"path": path}).json()["items"]


def test_restoring_overview_keeps_title_and_status(client):
    pid = client.post("/api/projects", json={"title": "옛 이름", "status": "planned"}).json()["id"]
    client.patch(f"/api/projects/{pid}", json={"body": "## 배경\n\n첫 내용\n"})
    client.patch(f"/api/projects/{pid}", json={"body": "## 배경\n\n둘째 내용\n"})
    client.patch(f"/api/projects/{pid}", json={"title": "새 이름", "status": "in_progress"})
    project = client.get(f"/api/projects/{pid}").json()
    path = f"projects/{project['dir_name']}/index.md"
    items = _versions(client, path)
    # 맨 위(과제명·상태만 바꾼 저장)는 본문이 같다 — 화면이 접는다
    assert items[0]["body_changed"] is False
    first = next(item for item in items if "첫 내용" in client.get(
        "/api/versions/content", params={"path": path, "stamp": item["stamp"]}).json()["text"])
    assert client.post("/api/versions/restore", json={"path": path, "stamp": first["stamp"]}).status_code == 200
    after = client.get(f"/api/projects/{pid}").json()
    assert (after["title"], after["status"], after["dir_name"]) == ("새 이름", "in_progress", project["dir_name"])
    assert "첫 내용" in after["body"]


def test_restoring_started_intake_request_keeps_status(client):
    iid = client.post("/api/intakes", json={"title": "요청"}).json()["id"]
    client.patch(f"/api/intakes/{iid}", json={"body": "## 배경\n\n처음 정의\n"})
    client.patch(f"/api/intakes/{iid}", json={"body": "## 배경\n\n바뀐 정의\n"})
    client.post(f"/api/intakes/{iid}/promote", json={})
    intake = client.get(f"/api/intakes/{iid}").json()
    path = f"intakes/{intake['dir_name']}/request.md"
    stamp = next(item["stamp"] for item in _versions(client, path) if "처음 정의" in client.get(
        "/api/versions/content", params={"path": path, "stamp": item["stamp"]}).json()["text"])
    client.post("/api/versions/restore", json={"path": path, "stamp": stamp})
    after = client.get(f"/api/intakes/{iid}").json()
    assert after["status"] == "started"
    assert "처음 정의" in after["body"]


def test_restoring_entry_keeps_its_title(client):
    pid = client.post("/api/projects", json={"title": "과제"}).json()["id"]
    directory = client.get(f"/api/projects/{pid}").json()["dir_name"]
    eid = client.post(f"/api/projects/{pid}/entries",
                      json={"date": "2026-09-01", "title": "첫 제목", "body": "처음"}).json()["id"]
    client.patch(f"/api/entries/{eid}", json={"body": "나중"})
    client.patch(f"/api/entries/{eid}", json={"title": "고친 제목"})
    entry = client.get(f"/api/entries/{eid}").json()
    path = f"projects/{directory}/{entry['rel_path']}"
    stamp = next(item["stamp"] for item in _versions(client, path) if "처음" in client.get(
        "/api/versions/content", params={"path": path, "stamp": item["stamp"]}).json()["text"])
    client.post("/api/versions/restore", json={"path": path, "stamp": stamp})
    after = client.get(f"/api/entries/{eid}").json()
    assert after["title"] == "고친 제목"
    assert after["body"].strip() == "처음"


def test_html_export_keeps_line_breaks_in_table_cells_only(client):
    pid = client.post("/api/projects", json={"title": "표"}).json()["id"]
    body = "| 항목 | 값 |\n|---|---|\n| 온도<br>편차 | 12 |\n\n<br onclick=\"x\"> <script>alert(1)</script>\n"
    client.patch(f"/api/projects/{pid}", json={"body": body})
    response = client.get(f"/api/projects/{pid}/export", params={"format": "html"})
    assert response.status_code == 200, response.text
    html = response.text
    assert "온도<br>편차" in html
    assert "&lt;br onclick" in html          # 속성이 붙은 것은 글자로
    assert "<script>alert" not in html


def test_intake_header_sort_directions(client):
    for title, day, effect in (("가", "2026-01-01", 1.0), ("나", "2026-02-01", 3.0), ("다", "2026-03-01", None)):
        payload = {"title": title, "received_on": day}
        if effect is not None:
            payload["effect_request"] = effect
        client.post("/api/intakes", json=payload)
    titles = lambda **q: [row["title"] for row in client.get("/api/intakes", params=q).json()["items"]]
    assert titles(sort="effect") == ["나", "가", "다"]
    assert titles(sort="effect", order="asc") == ["가", "나", "다"]   # 빈 값은 어느 쪽이든 맨 뒤
    assert titles(sort="received") == ["다", "나", "가"]
    assert titles(sort="received", order="asc") == ["가", "나", "다"]
