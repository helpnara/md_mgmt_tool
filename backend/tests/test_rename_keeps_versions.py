"""이름을 바꿔도 [이전 버전]이 남는다 (TODO 142) · 접수 첨부 엑셀 미리보기 (138) · 검색의 접수 (144).

보관본(`.versions/`)은 **경로를 열쇠로** 쓴다. 과제명·진행일지 제목·보고일·접수명·역량 기록을
고치면 폴더나 파일 이름이 따라 바뀌는데, 예전에는 보관본을 두고 와서 [이전 버전]이 0건이 됐다.
"""
from __future__ import annotations

import io


def _count(client, path: str) -> int:
    return len(client.get("/api/versions", params={"path": path}).json()["items"])


def test_project_title_keeps_overview_versions(client):
    pid = client.post("/api/projects", json={"title": "가나다"}).json()["id"]
    client.patch(f"/api/projects/{pid}", json={"body": "## 배경\n\n첫\n"})
    client.patch(f"/api/projects/{pid}", json={"body": "## 배경\n\n둘\n"})
    before_dir = client.get(f"/api/projects/{pid}").json()["dir_name"]
    before = _count(client, f"projects/{before_dir}/index.md")
    assert before >= 2
    client.patch(f"/api/projects/{pid}", json={"title": "라마바"})
    after_dir = client.get(f"/api/projects/{pid}").json()["dir_name"]
    assert after_dir != before_dir
    # 이름을 바꾸는 저장도 한 벌을 남기므로 줄지만 않으면 된다
    assert _count(client, f"projects/{after_dir}/index.md") >= before
    # 진행일지 · 보고도 같은 폴더 아래라 함께 따라왔다
    assert _count(client, f"projects/{before_dir}/index.md") == 0


def test_entry_title_and_report_date_keep_versions(client):
    pid = client.post("/api/projects", json={"title": "과제"}).json()["id"]
    directory = client.get(f"/api/projects/{pid}").json()["dir_name"]
    eid = client.post(f"/api/projects/{pid}/entries",
                      json={"date": "2026-09-01", "title": "첫기록", "body": "a"}).json()["id"]
    client.patch(f"/api/entries/{eid}", json={"body": "b"})
    client.patch(f"/api/entries/{eid}", json={"title": "고친기록"})
    rel = client.get(f"/api/entries/{eid}").json()["rel_path"]
    assert rel.endswith("고친기록.md")
    assert _count(client, f"projects/{directory}/{rel}") >= 2

    report = client.post(f"/api/projects/{pid}/reports/draft", json={"report_date": "2026-09-02"}).json()
    client.patch(f"/api/reports/{report['id']}", json={"body": "x"})
    client.patch(f"/api/reports/{report['id']}", json={"report_date": "2026-09-09"})
    moved = client.get(f"/api/reports/{report['id']}").json()["rel_path"]
    assert moved.startswith("reports/2026-09-09/")
    assert _count(client, f"projects/{directory}/{moved}") >= 2


def test_intake_title_and_log_keep_versions(client):
    intake = client.post("/api/intakes", json={"title": "접수가"}).json()
    iid = intake["id"]
    client.patch(f"/api/intakes/{iid}", json={"body": "## 배경\n\nA\n"})
    client.patch(f"/api/intakes/{iid}", json={"title": "접수나"})
    directory = client.get(f"/api/intakes/{iid}").json()["dir_name"]
    assert directory.endswith("접수나")
    assert _count(client, f"intakes/{directory}/request.md") >= 2

    name = client.post(f"/api/intakes/{iid}/logs",
                       json={"date": "2026-09-01", "title": "1차", "body": "a"}).json()["name"]
    renamed = client.patch(f"/api/intakes/{iid}/logs/{name}", json={"title": "1차 인터뷰", "body": "b"}).json()["name"]
    assert renamed != name
    assert _count(client, f"intakes/{directory}/logs/{renamed}") >= 1


def test_trash_does_not_move_versions(client):
    """지울 때는 보관본을 옮기지 않는다 — 되돌리면 원래 자리로 오므로 거기 있어야 한다."""
    pid = client.post("/api/projects", json={"title": "지울과제"}).json()["id"]
    client.patch(f"/api/projects/{pid}", json={"body": "첫"})
    client.patch(f"/api/projects/{pid}", json={"body": "둘"})
    directory = client.get(f"/api/projects/{pid}").json()["dir_name"]
    before = _count(client, f"projects/{directory}/index.md")
    client.post(f"/api/projects/{pid}/archive")
    assert _count(client, f"projects/{directory}/index.md") == before


def _xlsx_bytes() -> bytes:
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.append(["항목", "값"])
    sheet.append(["온도편차", 12])
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def test_intake_spreadsheet_preview(client):
    iid = client.post("/api/intakes", json={"title": "엑셀 첨부"}).json()["id"]
    saved = client.post(f"/api/intakes/{iid}/attachments",
                        files={"file": ("효과산출.xlsx", _xlsx_bytes())}).json()
    assert saved["preview_url"]
    preview = client.get(saved["preview_url"]).json()
    assert preview["orig_name"] == "효과산출.xlsx"
    assert preview["sheets"][0]["rows"][1][:2] == ["온도편차", "12"]

    # 그림에는 미리보기가 없고, 깨진 엑셀은 500 이 아니라 읽을 수 있는 400
    image = client.post(f"/api/intakes/{iid}/attachments", files={"file": ("a.png", b"\x89PNG")}).json()
    assert image["preview_url"] is None
    broken = client.post(f"/api/intakes/{iid}/attachments", files={"file": ("깨짐.xlsx", b"not a zip")}).json()
    response = client.get(broken["preview_url"])
    assert response.status_code == 400
    assert "미리 볼 수 없습니다" in response.json()["detail"]
    # 첨부 폴더 밖은 못 본다
    assert client.get(f"/api/intakes/{iid}/attachments/preview", params={"path": "request.md"}).status_code == 400


def test_search_finds_intakes_by_team_and_body(client):
    client.post("/api/intakes", json={"title": "코일 표면결함", "leader": "현업이", "leader_team": "품질보증팀"})
    iid = client.post("/api/intakes", json={"title": "다른 요청"}).json()["id"]
    client.patch(f"/api/intakes/{iid}", json={"body": "## 배경\n\n열연 스케일 불량이 잦다\n"})
    by_team = client.get("/api/search", params={"q": "품질보증"}).json()
    assert [row["title"] for row in by_team["intakes"]] == ["코일 표면결함"]
    by_body = client.get("/api/search", params={"q": "스케일"}).json()
    assert by_body["intakes"][0]["id"] == iid
    assert "스케일" in by_body["intakes"][0]["snippet"]
    # 반려된 것도 찾아진다 — 반년 뒤 "그 요청 어떻게 됐더라" 의 답이다
    client.post(f"/api/intakes/{iid}/status", json={"status": "rejected", "note": "시험 반려"})
    again = client.get("/api/search", params={"q": "스케일"}).json()
    assert again["intakes"][0]["status"] == "rejected"
    assert again["total"] >= 1
