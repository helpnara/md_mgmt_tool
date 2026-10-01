"""다년도 과제 로드맵 (TODO 174) — 줄기 · 단계 · 기간 · 살펴볼 것."""
from datetime import date

from app.services import roadmap

THIS_YEAR = date.today().year


def _project(client, title, **extra):
    return client.post("/api/projects", json={"title": title, **extra}).json()


def _kinds(lineage, project_id):
    return sorted(w["kind"] for w in lineage["warnings"] if w["project_id"] == project_id)


def test_only_connected_projects_form_lineages(client):
    _project(client, "혼자 가는 과제")
    a = _project(client, "1단계", status="done", start_date="2024-03-01", due_date="2024-12-31", completed_at="2024-12-20")
    b = _project(client, "1단계 둘째", status="done", start_date="2024-05-01", due_date="2024-12-31")
    c = _project(client, "2단계", start_date="2025-01-02", due_date="2025-12-31", predecessors=[a["id"], b["id"]])
    d = _project(client, "3단계", status="planned", start_date="2026-01-02", due_date="2026-12-31", predecessors=[c["id"]])

    data = client.get("/api/roadmap").json()
    assert data["summary"]["lineages"] == 1 and data["summary"]["projects"] == 4
    lineage = data["lineages"][0]
    assert lineage["key"] == a["id"] and lineage["title"] == "1단계"  # 1단계에서 먼저 시작한 과제가 이름
    assert lineage["stage_count"] == 3
    assert [(p["id"], p["stage"]) for p in lineage["projects"]] == [(a["id"], 1), (b["id"], 1), (c["id"], 2), (d["id"], 3)]
    assert lineage["start_date"] == "2024-03-01" and lineage["end_date"] == "2026-12-31"
    # 끝난 과제의 막대는 끝낸 날까지
    assert lineage["projects"][0]["end_date"] == "2024-12-20"
    assert lineage["projects"][2]["predecessors"] == sorted([a["id"], b["id"]])
    assert lineage["projects"][2]["successors"] == [d["id"]]
    assert lineage["state"] == "active" and lineage["current_stage"] == 3


def test_warnings_for_managers(client):
    today = date.today()
    past = f"{today.year - 1}-06-30"
    this_year_end = f"{today.year}-12-31"
    dropped = _project(client, "중단된 선행", status="dropped", start_date=f"{today.year - 2}-01-01", due_date=past)
    late = _project(client, "늦은 후속", start_date=f"{today.year - 1}-01-01", due_date=past, predecessors=[dropped["id"]])
    running = _project(client, "겹쳐 가는 후속", start_date=f"{today.year}-01-01", due_date=this_year_end, predecessors=[late["id"]])
    undated = _project(client, "기간 미정", status="planned", predecessors=[late["id"]])

    lineage = client.get("/api/roadmap").json()["lineages"][0]
    assert _kinds(lineage, late["id"]) == ["overdue", "pred_dropped"]
    # 진행 중인데 선행이 아직 · 올해 끝나는 마지막 단계인데 다음 단계가 없다
    assert _kinds(lineage, running["id"]) == ["next_open", "pred_open"]
    assert _kinds(lineage, undated["id"]) == ["no_dates"]
    assert _kinds(lineage, dropped["id"]) == []  # 끝난 과제는 지연을 따지지 않는다
    levels = {w["kind"]: w["level"] for w in lineage["warnings"]}
    assert levels["overdue"] == "warn" and levels["pred_open"] == "info"


def test_next_stage_present_clears_next_open(client):
    a = _project(client, "올해 끝나는 단계", start_date=f"{THIS_YEAR}-01-01", due_date=f"{THIS_YEAR}-12-31")
    b = _project(client, "내년 단계", status="planned", start_date=f"{THIS_YEAR + 1}-01-01",
                 due_date=f"{THIS_YEAR + 1}-12-31", predecessors=[a["id"]])
    lineage = client.get("/api/roadmap").json()["lineages"][0]
    assert "next_open" not in _kinds(lineage, a["id"])
    assert _kinds(lineage, b["id"]) == []


def test_missing_predecessor_keeps_the_lineage_with_a_gap(client):
    a = _project(client, "보관함에 갈 선행", start_date="2024-01-01", due_date="2024-12-31")
    b = _project(client, "남는 후속", start_date="2025-01-01", due_date="2025-12-31", predecessors=[a["id"]])
    client.post(f"/api/projects/{a['id']}/archive")
    data = client.get("/api/roadmap").json()
    lineage = data["lineages"][0]
    assert [(p["id"], p["missing"]) for p in lineage["projects"]] == [(a["id"], True), (b["id"], False)]
    assert lineage["key"] == b["id"]
    assert "missing" in _kinds(lineage, b["id"])
    assert data["summary"]["projects"] == 1


def test_active_lineages_come_first(client):
    old_a = _project(client, "끝난 줄기 1", status="done", start_date="2022-01-01", due_date="2022-12-31")
    _project(client, "끝난 줄기 2", status="done", start_date="2023-01-01", due_date="2023-12-31", predecessors=[old_a["id"]])
    new_a = _project(client, "진행 줄기 1", status="done", start_date="2025-01-01", due_date="2025-12-31")
    _project(client, "진행 줄기 2", start_date="2026-01-01", due_date="2027-12-31", predecessors=[new_a["id"]])
    data = client.get("/api/roadmap").json()
    assert [item["state"] for item in data["lineages"]] == ["active", "ended"]
    assert data["summary"]["active"] == 1


def test_build_accepts_a_fixed_today(client):
    a = _project(client, "가", start_date="2030-01-01", due_date="2030-06-30")
    _project(client, "나", start_date="2030-07-01", due_date="2030-12-31", predecessors=[a["id"]])
    from app import deps

    conn = deps.connect()
    try:
        data = roadmap.build(conn, today=date(2030, 8, 1))
    finally:
        conn.close()
    lineage = data["lineages"][0]
    assert data["today"] == "2030-08-01"
    assert _kinds(lineage, a["id"]) == ["overdue"]
    assert _kinds(lineage, lineage["projects"][1]["id"]) == ["next_open", "pred_open"]


# ── 175 과제명 뒤 단계 띠 ──────────────────────────────────────────────────


def test_stage_rides_along_list_detail_candidates_and_search(client):
    alone = _project(client, "혼자 가는 띠없음 과제")
    a = _project(client, "띠시험 1단계", start_date="2024-01-01")
    b = _project(client, "띠시험 2단계", start_date="2025-01-01", predecessors=[a["id"]])
    listed = {item["id"]: item["stage"] for item in client.get("/api/projects").json()}
    assert listed[a["id"]] == 1 and listed[b["id"]] == 2 and listed[alone["id"]] is None
    assert client.get(f"/api/projects/{b['id']}").json()["stage"] == 2
    candidates = {item["id"]: item.get("stage") for item in client.get("/api/report-candidates").json()["items"]}
    assert candidates.get(b["id"]) == 2
    found = {item["id"]: item["stage"] for item in client.get("/api/search", params={"q": "띠시험"}).json()["projects"]}
    assert found[b["id"]] == 2
