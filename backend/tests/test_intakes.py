"""과제 접수 풀 (TODO 136).

지키는 약속:
  * 접수는 과제가 아니다 — 과제 목록·홈 집계에 섞이지 않는다
  * 번호는 따로 (R연도-팀코드-일련), 착수할 때 비로소 과제 번호가 붙는다
  * 풀에 있을 때만 고친다 — 판정이 난 접수는 굳고, [재검토]로만 연다
  * 반려·이관·보류는 사유가 있어야 한다
  * 승격: 같은 제목끼리 옮기고 나머지는 '접수 내용'에, 첨부는 복사, 양쪽 링크
  * 과제리더는 명부로 가른다 — 명부에 있으면 담당자, 없으면 유관부서
  * 요청자 기대효과는 과제 기대효과로 옮기지 않는다
"""
from __future__ import annotations

import io


def _make(client, **extra) -> dict:
    payload = {"title": "압연 온도편차 예측", "leader": "홍길동", "leader_team": "압연기술팀",
               "nature": "현장적용", "category": "예측/분류모델 개발", "effect_request": 3.5}
    payload.update(extra)
    response = client.post("/api/intakes", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_numbers_are_separate_and_use_team_code(client):
    client.put("/api/settings", json={"project_code": "소재"})
    first = _make(client, received_on="2026-03-02")
    second = _make(client, title="두 번째", received_on="2026-04-01")
    assert first["id"] == "R2026-소재-001"
    assert second["id"] == "R2026-소재-002"
    # 과제 번호는 하나도 쓰지 않았다
    assert client.get("/api/projects").json() == []
    assert client.get("/api/projects/next-id").json()["id"].endswith("-001")


def test_intake_does_not_leak_into_projects_or_home(client):
    _make(client)
    assert client.get("/api/projects").json() == []
    home = client.get("/api/home").json()
    assert home["team"]["total"] == 0


def test_starts_in_pool_with_template_body(client):
    item = _make(client)
    assert item["status"] == "received"
    assert item["in_pool"] is True
    assert "## 목표 (성과지표)" in item["body"]
    listing = client.get("/api/intakes").json()
    assert [row["id"] for row in listing["items"]] == [item["id"]]
    assert listing["summary"]["pool"] == 1


def test_rejection_needs_a_reason_and_closes_the_intake(client):
    item = _make(client)
    no_reason = client.post(f"/api/intakes/{item['id']}/status", json={"status": "rejected"})
    assert no_reason.status_code == 400
    done = client.post(f"/api/intakes/{item['id']}/status",
                       json={"status": "rejected", "note": "설비 교체 예정이라 지금은 효과가 없다"})
    assert done.status_code == 200
    body = done.json()
    assert body["status"] == "rejected" and body["in_pool"] is False
    assert body["decision_note"].startswith("설비 교체")
    # 판정 기록이 검토 기록에 한 줄 남는다
    assert any("반려" in log["title"] for log in body["logs"])
    # 굳은 접수는 고칠 수 없다
    blocked = client.patch(f"/api/intakes/{item['id']}", json={"title": "고쳐 보기"})
    assert blocked.status_code == 409
    # 풀에서 빠지고, 판정이 난 것 목록에 선다
    assert client.get("/api/intakes").json()["items"] == []
    closed = client.get("/api/intakes", params={"scope": "closed"}).json()["items"]
    assert [row["id"] for row in closed] == [item["id"]]
    # 재검토로 되돌리면 다시 고칠 수 있다 — 지난 판정 사유는 기록 줄에만 남는다
    reopened = client.post(f"/api/intakes/{item['id']}/status", json={"status": "reviewing"}).json()
    assert reopened["in_pool"] and reopened["decision_note"] is None
    assert client.patch(f"/api/intakes/{item['id']}", json={"title": "고쳐 보기"}).status_code == 200


def test_merge_needs_an_existing_project(client):
    item = _make(client)
    bad = client.post(f"/api/intakes/{item['id']}/status", json={"status": "merged", "merged_into": "2026-999"})
    assert bad.status_code == 400
    project = client.post("/api/projects", json={"title": "이미 하는 과제"}).json()
    ok = client.post(f"/api/intakes/{item['id']}/status",
                     json={"status": "merged", "merged_into": project["id"], "note": "같은 요청"}).json()
    assert ok["status"] == "merged" and ok["merged_into"] == project["id"]
    # 과제 상세에서 병합된 접수가 보인다
    detail = client.get(f"/api/projects/{project['id']}").json()
    assert [row["id"] for row in detail["intakes"]] == [item["id"]]
    assert detail["intakes"][0]["relation"] == "merged"


def test_logs_are_kept_and_counted_without_status_lines(client):
    item = _make(client)
    made = client.post(f"/api/intakes/{item['id']}/logs",
                       json={"date": "2026-10-02", "title": "1차 인터뷰", "body": "범위를 좁혔다"}).json()
    client.post(f"/api/intakes/{item['id']}/status", json={"status": "reviewing"})
    detail = client.get(f"/api/intakes/{item['id']}").json()
    assert detail["log_count"] == 1  # 상태 변경 줄은 세지 않는다
    assert detail["last_log_date"] == "2026-10-02"
    names = [log["name"] for log in detail["logs"]]
    assert made["name"] in names
    edited = client.patch(f"/api/intakes/{item['id']}/logs/{made['name']}",
                          json={"title": "1차 인터뷰 (현장)", "body": "범위를 두 라인으로"}).json()
    after = client.get(f"/api/intakes/{item['id']}").json()
    log = next(log for log in after["logs"] if log["name"] == edited["name"])
    assert log["body"].strip() == "범위를 두 라인으로"
    assert client.delete(f"/api/intakes/{item['id']}/logs/{edited['name']}").status_code == 204
    assert client.get(f"/api/intakes/{item['id']}").json()["log_count"] == 0


def test_log_name_cannot_escape(client, vault_dir):
    import pytest
    from app.services import intakes

    item = _make(client)
    # 주소에서 막히든(405) 서비스에서 막히든, 요청 본문이 지워지면 안 된다
    response = client.delete(f"/api/intakes/{item['id']}/logs/..%2Frequest.md")
    assert response.status_code in (400, 404, 405)
    assert client.get(f"/api/intakes/{item['id']}").status_code == 200
    directory = next((vault_dir / "intakes").iterdir())
    with pytest.raises(ValueError):
        intakes._log_path(directory, "../request.md")
    with pytest.raises(ValueError):
        intakes._log_path(directory, "sub/x.md")


def test_attachment_upload_and_serve(client):
    item = _make(client)
    uploaded = client.post(f"/api/intakes/{item['id']}/attachments",
                           files={"file": ("과제정의서 초안.pptx", io.BytesIO(b"pptx"), "application/octet-stream")})
    assert uploaded.status_code == 201, uploaded.text
    info = uploaded.json()
    assert info["rel_path"].startswith("assets/") and info["orig_name"] == "과제정의서 초안.pptx"
    # 공백이 있는 이름은 < > 로 감싼다 (TODO 114)
    assert "(<assets/" in info["markdown"]
    assert "(<../assets/" in info["markdown_log"]
    served = client.get(info["url"])
    assert served.status_code == 200 and served.content == b"pptx"


def test_promotion_maps_sections_copies_files_and_links_both_ways(client, vault_dir):
    client.put("/api/people", json={"people": [{"name": "권경락"}]})
    item = _make(client, leader="홍길동", leader_team="압연기술팀", start_date="2026-11-01",
                 due_date="2027-03-31", cost_kind="변동비")
    uploaded = client.post(f"/api/intakes/{item['id']}/attachments",
                           files={"file": ("공정 설명.png", io.BytesIO(b"png"), "image/png")}).json()
    body = (
        "## 배경 (과제배경)\n\n압연 온도가 흔들린다.\n\n"
        "## 목표 (성과지표)\n\n| KPI 항목 | 정의(계산식) | 현수준 | 목표 | 기대효과(억원/년) | 비용구분 |\n"
        "|---|---|---|---|---|---|\n| 온도편차 | 표준편차 | 12 | 5 | 3.5 | 변동비 |\n\n"
        f"## 추진내용 — 범위\n\n두 라인부터.\n\n{uploaded['markdown']}\n\n"
        "## 현장 사진\n\n별도 섹션이다.\n"
    )
    client.patch(f"/api/intakes/{item['id']}", json={"body": body})

    plan = client.get(f"/api/intakes/{item['id']}/promote").json()
    # 홍길동은 명부에 없다 → 현업 사람으로 보고 유관부서 줄로
    assert plan["leader_in_roster"] is False
    assert plan["owners"] == []
    assert plan["partners"] == [{"team": "압연기술팀", "people": ["홍길동"]}]
    assert set(plan["matched_sections"]) == {"배경", "목표", "추진내용"}
    assert plan["leftover_sections"] == ["현장 사진"]
    assert plan["effect_request"] == 3.5

    result = client.post(f"/api/intakes/{item['id']}/promote", json={
        "owners": ["권경락"], "partners": plan["partners"],
        "start_date": plan["start_date"], "due_date": plan["due_date"],
        "cost_kind": "변동비", "nature": "현장적용",
    })
    assert result.status_code == 201, result.text
    project_id = result.json()["project_id"]
    project = client.get(f"/api/projects/{project_id}").json()

    # 과제 번호는 이때 붙고, 과제에는 접수 번호가 남는다 — 양쪽 링크
    assert project["intake_id"] == item["id"]
    assert result.json()["intake"]["project_id"] == project_id
    assert result.json()["intake"]["status"] == "started"
    assert project["intakes"][0]["relation"] == "started"
    # 같은 제목끼리 옮겼고, 짝 없는 섹션은 '접수 내용' 에 모였다
    assert "압연 온도가 흔들린다." in project["body"]
    assert "| 온도편차 |" in project["body"]
    assert "## 접수 내용" in project["body"] and "### 현장 사진" in project["body"]
    assert f"- 접수: {item['id']}" in project["body"]
    # 요청자 기대효과는 옮기지 않았다 (보내지 않았으므로 비어 있다)
    assert project["effect_expected"] is None
    assert project["cost_kind"] == "변동비" and project["nature"] == "현장적용"
    assert project["owners"] == ["권경락"]
    assert project["partners"] == [{"team": "압연기술팀", "people": ["홍길동"]}]
    # 첨부는 복사됐고, 본문의 링크가 그대로 산다
    files = client.get(f"/api/projects/{project_id}/attachments").json()["items"]
    assert [f["orig_name"] for f in files] == ["공정 설명.png"]
    assert files[0]["rel_path"] == uploaded["rel_path"]
    assert files[0]["orphan"] is False
    # 원본도 접수 쪽에 남아 있다
    assert client.get(uploaded["url"]).status_code == 200

    # 승격된 접수는 굳고, 되돌릴 수도 지울 수도 없다
    assert client.post(f"/api/intakes/{item['id']}/status", json={"status": "reviewing"}).status_code == 409
    assert client.post(f"/api/intakes/{item['id']}/archive").status_code == 409
    # 이제 과제 목록에는 하나, 풀에는 없다
    assert [p["id"] for p in client.get("/api/projects", params={"from_intake": "yes"}).json()] == [project_id]
    assert client.get("/api/intakes").json()["items"] == []


def test_leader_in_roster_becomes_owner(client):
    client.put("/api/people", json={"people": [{"name": "권경락"}]})
    item = _make(client, leader="권경락", leader_team="선강DX개발팀")
    plan = client.get(f"/api/intakes/{item['id']}/promote").json()
    assert plan["leader_in_roster"] is True
    assert plan["owners"] == ["권경락"]
    assert plan["partners"] == []


def test_placeholder_sections_do_not_overwrite_project_guides(client):
    item = _make(client)  # 서식 그대로
    plan = client.get(f"/api/intakes/{item['id']}/promote").json()
    assert plan["matched_sections"] == []
    assert plan["leftover_sections"] == []
    assert "## 접수 내용" not in plan["body_preview"]


def test_stale_counts_only_undecided(client):
    client.put("/api/settings", json={"intake_stale_days": 14})
    old = _make(client, received_on="2020-01-01")
    held = _make(client, title="보류 건", received_on="2020-01-01")
    client.post(f"/api/intakes/{held['id']}/status", json={"status": "on_hold", "note": "설비 교체 이후"})
    _make(client, title="새 건")
    listing = client.get("/api/intakes").json()
    assert listing["summary"]["stale"] == 1
    stale = client.get("/api/intakes", params={"stale": "1"}).json()["items"]
    assert [row["id"] for row in stale] == [old["id"]]


def test_reindex_restores_intakes_from_files(client, db):
    item = _make(client)
    db.execute("DELETE FROM intake")
    db.commit()
    client.post("/api/reindex")
    assert [row["id"] for row in client.get("/api/intakes").json()["items"]] == [item["id"]]


def test_archive_moves_to_trash_and_restores(client):
    item = _make(client)
    assert client.post(f"/api/intakes/{item['id']}/archive").status_code == 204
    assert client.get("/api/intakes").json()["items"] == []
    trash = client.get("/api/trash").json()
    entry = next(row for row in trash if row["kind"] == "intake")
    assert entry["kind_label"] == "접수"
    client.post(f"/api/trash/{entry['trash_name']}/restore")
    assert [row["id"] for row in client.get("/api/intakes").json()["items"]] == [item["id"]]


def test_project_classification_fields_and_filters(client):
    made = client.post("/api/projects", json={"title": "센싱 과제", "type": "smart",
                                              "nature": "연구과제/PoC", "category": "스마트 센싱",
                                              "delivery": "외부 전문업체 협업", "cost_kind": "고정비"}).json()
    client.post("/api/projects", json={"title": "기획 보고", "type": "plan_report"})
    assert made["nature"] == "연구과제/PoC" and made["intake_id"] is None
    only = client.get("/api/projects", params={"category": "스마트 센싱"}).json()
    assert [p["id"] for p in only] == [made["id"]]
    none = client.get("/api/projects", params={"nature": "none"}).json()
    assert [p["title"] for p in none] == ["기획 보고"]
    assert client.get("/api/projects", params={"from_intake": "no"}).json().__len__() == 2
    # 승격으로 붙은 접수 번호는 화면에서 고칠 수 없다
    client.patch(f"/api/projects/{made['id']}", json={"title": "센싱 과제", "intake_id": "R2026-999"})
    assert client.get(f"/api/projects/{made['id']}").json()["intake_id"] is None


def test_classification_lists_are_editable(client):
    meta = client.get("/api/meta").json()
    nature = next(c for c in meta["classifications"] if c["key"] == "nature")
    assert nature["items"][0] == "연구과제/PoC"
    saved = client.put("/api/settings", json={"classifications": {"nature": "PoC\n현장적용\n\nPoC"}})
    assert saved.status_code == 200
    meta = client.get("/api/meta").json()
    nature = next(c for c in meta["classifications"] if c["key"] == "nature")
    assert nature["items"] == ["PoC", "현장적용"]
    # 비우면 기본 목록으로 되돌린다
    client.put("/api/settings", json={"classifications": {"nature": ""}})
    nature = next(c for c in client.get("/api/meta").json()["classifications"] if c["key"] == "nature")
    assert nature["items"][0] == "연구과제/PoC"


def test_old_overview_template_still_counts_as_blank(client):
    from app.services import projects

    assert projects.overview_is_blank(projects.LEGACY_INDEX_TEMPLATES[0])
    assert projects.overview_is_blank(projects.INDEX_TEMPLATE)
    assert "## 추진내용" in projects.INDEX_TEMPLATE
    assert "## 활용 방안 및 향후 계획" in projects.INDEX_TEMPLATE


def test_home_counts_match_what_the_list_filters(client):
    """홈의 성격별·분류별 표 — 줄의 수 = 그 줄이 보내는 거르기 조건의 목록 길이 (DESIGN 5.8)."""
    client.post("/api/projects", json={"title": "A", "type": "smart", "nature": "현장적용", "cost_kind": "고정비",
                                       "effect_expected": 1.5})
    client.post("/api/projects", json={"title": "B", "type": "smart", "cost_kind": "변동비", "effect_expected": 2})
    client.post("/api/projects", json={"title": "C", "type": "plan_report"})  # 미지정에 섞이면 안 된다
    client.post("/api/projects", json={"title": "D", "type": "plan_report", "nature": "현장적용"})
    home = client.get("/api/home").json()
    rows = {row["label"]: row for row in home["natures"]}
    assert rows["현장적용"]["count"] == 2
    assert rows["미지정"]["count"] == 1  # 스마트과제인데 비어 있는 B 하나
    for row in home["natures"]:
        listed = client.get("/api/projects", params=row["filter"]).json()
        assert len(listed) == row["count"], row
    split = {item["key"]: item for item in home["effect_by_cost"]}
    assert split["고정비"]["effect_expected"] == 1.5 and split["변동비"]["effect_expected"] == 2
    assert home["intakes"]["pool"] == 0
    _make(client)
    assert client.get("/api/home").json()["intakes"]["pool"] == 1
