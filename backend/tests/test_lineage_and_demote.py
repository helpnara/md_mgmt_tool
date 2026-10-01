"""선행 과제(다년도) · 과제를 접수로 되돌리기 (TODO 171 · 172)."""


def _project(client, title, **extra):
    return client.post("/api/projects", json={"title": title, **extra}).json()


# ── 172 선행 과제 ─────────────────────────────────────────────────────────


def _stages(lineage):
    return [(group["stage"], [item["id"] for item in group["items"]]) for group in lineage["stages"]]


def test_three_stage_chain_shows_stage_and_neighbours(client, vault_dir):
    first = _project(client, "1단계 기술 개발", start_date="2024-03-01")
    second = _project(client, "2단계 현장 적용", start_date="2025-03-01", predecessors=[first["id"]])
    third = _project(client, "3단계 확대 전개", start_date="2026-03-01")
    client.patch(f"/api/projects/{third['id']}", json={"predecessors": [second["id"]]})

    lineage = client.get(f"/api/projects/{third['id']}").json()["lineage"]
    assert lineage["stage"] == 3
    assert _stages(lineage) == [(1, [first["id"]]), (2, [second["id"]]), (3, [third["id"]])]
    assert lineage["predecessors"] == [second["id"]] and lineage["successors"] == []
    middle = client.get(f"/api/projects/{second['id']}").json()["lineage"]
    assert middle["stage"] == 2 and middle["successors"] == [third["id"]]
    here = [item for group in middle["stages"] for item in group["items"] if item["here"]]
    assert [item["id"] for item in here] == [second["id"]]
    # 파일에 남는다
    index = next((vault_dir / "projects").glob(f"{third['id']}-*")) / "index.md"
    assert f"predecessors:\n- {second['id']}" in index.read_text(encoding="utf-8")


def test_a_stage_can_hold_several_projects_and_a_project_several_predecessors(client):
    # 1단계 둘(A · B) → 2단계 둘(C ← A, D ← A · B) → 3단계(E ← C · D)
    a = _project(client, "A 소재", start_date="2024-01-01")
    b = _project(client, "B 공정", start_date="2024-01-01")
    c = _project(client, "C 시제품", start_date="2025-01-01", predecessors=[a["id"]])
    d = _project(client, "D 설비", start_date="2025-01-01", predecessors=[a["id"], b["id"]])
    e = _project(client, "E 양산", start_date="2026-01-01", predecessors=[c["id"], d["id"]])
    lineage = client.get(f"/api/projects/{d['id']}").json()["lineage"]
    assert lineage["stage"] == 2
    assert _stages(lineage) == [(1, sorted([a["id"], b["id"]])), (2, sorted([c["id"], d["id"]])), (3, [e["id"]])]
    assert lineage["predecessors"] == sorted([a["id"], b["id"]]) and lineage["successors"] == [e["id"]]
    assert client.get(f"/api/projects/{e['id']}").json()["predecessors"] == sorted([c["id"], d["id"]])
    # 단계는 가장 긴 길로 센다 — 1단계(A)와 2단계(C)를 함께 이어받으면 3단계
    f = _project(client, "F 응용", predecessors=[a["id"], c["id"]])
    assert client.get(f"/api/projects/{f['id']}").json()["lineage"]["stage"] == 3


def test_single_year_project_has_no_stage(client):
    alone = _project(client, "단년도 과제")
    assert client.get(f"/api/projects/{alone['id']}").json()["lineage"]["stage"] is None


def test_predecessor_rules(client):
    a = _project(client, "가")
    b = _project(client, "나", predecessors=[a["id"]])
    assert client.patch(f"/api/projects/{a['id']}", json={"predecessors": [a["id"]]}).status_code == 400  # 자기 자신
    assert client.patch(f"/api/projects/{a['id']}", json={"predecessors": [b["id"]]}).status_code == 400  # 고리
    assert client.patch(f"/api/projects/{a['id']}", json={"predecessors": ["2099-999"]}).status_code == 400
    assert client.post("/api/projects", json={"title": "다", "predecessors": ["2099-999"]}).status_code == 400
    # 이름까지 붙여 보내도 번호만 쓴다 · 겹치면 하나로 · [] 이면 끊는다
    saved = client.patch(f"/api/projects/{b['id']}", json={"predecessors": [f"{a['id']} 가", a["id"]]}).json()
    assert saved["predecessors"] == [a["id"]]
    assert client.patch(f"/api/projects/{b['id']}", json={"predecessors": []}).json()["predecessors"] == []


def test_clone_links_the_new_project_as_next_stage(client):
    source = _project(client, "수명평가 표준화")
    before = len(client.get("/api/projects").json())
    next_id = client.get("/api/projects/next-id").json()["id"]
    # 미리 채울 값만 — 만들지 않는다 (173): 과제 수도 다음 번호도 그대로
    draft = client.get(f"/api/projects/{source['id']}/clone").json()
    assert draft["predecessors"] == [source["id"]]
    assert draft["status"] == "planned" and draft["title"] == "수명평가 표준화"
    assert len(client.get("/api/projects").json()) == before
    assert client.get("/api/projects/next-id").json()["id"] == next_id
    # [만들기] = 보통의 과제 만들기
    clone = client.post("/api/projects", json=draft).json()
    assert clone["id"] == next_id and clone["predecessors"] == [source["id"]]
    assert client.get(f"/api/projects/{clone['id']}").json()["lineage"]["stage"] == 2
    assert client.post(f"/api/projects/{source['id']}/clone").status_code == 405
    assert client.get("/api/projects/2099-999/clone").status_code == 404


def test_archived_predecessor_shows_as_missing(client):
    a = _project(client, "지울 선행")
    b = _project(client, "남는 후속", predecessors=[a["id"]])
    client.post(f"/api/projects/{a['id']}/archive")
    lineage = client.get(f"/api/projects/{b['id']}").json()["lineage"]
    first = lineage["stages"][0]["items"][0]
    assert first["id"] == a["id"] and first["missing"] is True and lineage["stage"] == 2


def test_renumbering_rewrites_predecessors_and_intake_links(client, vault_dir):
    a = _project(client, "선행")
    b = _project(client, "후속", predecessors=[a["id"]])
    intake = client.post("/api/intakes", json={"title": "요청"}).json()
    promoted = client.post(f"/api/intakes/{intake['id']}/promote", json={"title": "승격 과제"}).json()
    applied = client.post("/api/settings/project-code/renumber", json={"code": "팀"}).json()
    mapping = {item["id"]: item["new_id"] for item in applied["changed"]}
    assert client.get(f"/api/projects/{mapping[b['id']]}").json()["predecessors"] == [mapping[a["id"]]]
    assert client.get(f"/api/intakes/{intake['id']}").json()["project_id"] == mapping[promoted["project_id"]]


# ── 171 과제 → 접수 ─────────────────────────────────────────────────────


def test_demote_moves_overview_logs_and_files_to_a_pool_intake(client, vault_dir):
    project = _project(client, "직접 만든 스마트과제", type="smart", nature="현장적용",
                       effect_expected=2.5, body="## 배경\n\n현장 요청\n\n![도면](assets/2026-09-01/001-도면.png)\n")
    folder = next((vault_dir / "projects").glob(f"{project['id']}-*"))
    (folder / "assets" / "2026-09-01").mkdir(parents=True, exist_ok=True)
    (folder / "assets" / "2026-09-01" / "001-도면.png").write_bytes(b"png")
    client.post(f"/api/projects/{project['id']}/entries", json={"date": "2026-09-02", "title": "현장 미팅", "body": "논의"})

    plan = client.get(f"/api/projects/{project['id']}/to-intake").json()
    assert plan["eligible"] and plan["entries"] == 1

    intake_id = client.post(f"/api/projects/{project['id']}/to-intake").json()["intake_id"]
    assert intake_id == plan["next_intake_id"]
    intake = client.get(f"/api/intakes/{intake_id}").json()
    assert intake["status"] == "reviewing" and intake["in_pool"]
    assert intake["nature"] == "현장적용" and intake["effect_request"] == 2.5
    assert "현장 요청" in intake["body"]
    intake_folder = next((vault_dir / "intakes").glob(f"{intake_id}-*"))
    assert (intake_folder / "assets" / "2026-09-01" / "001-도면.png").is_file()  # 링크가 그대로 산다
    assert "demoted_from: " + project["id"] in (intake_folder / "request.md").read_text(encoding="utf-8")
    titles = [log["title"] for log in intake["logs"]]
    assert "현장 미팅" in titles and any("되돌림" in title for title in titles)
    # 과제는 보관함으로 — 목록에서 빠지고 번호는 다시 쓰지 않는다
    assert client.get(f"/api/projects/{project['id']}").status_code == 404
    assert client.post("/api/projects", json={"title": "다음"}).json()["id"] != project["id"]


def test_demote_refuses_reported_or_promoted_projects(client):
    reported = _project(client, "보고한 과제")
    client.post(f"/api/projects/{reported['id']}/reports/draft", json={})
    plan = client.get(f"/api/projects/{reported['id']}/to-intake").json()
    assert not plan["eligible"] and "보고" in plan["reason"]
    assert client.post(f"/api/projects/{reported['id']}/to-intake").status_code == 400

    intake = client.post("/api/intakes", json={"title": "요청"}).json()
    promoted = client.post(f"/api/intakes/{intake['id']}/promote", json={"title": "승격"}).json()
    plan = client.get(f"/api/projects/{promoted['project_id']}/to-intake").json()
    assert not plan["eligible"] and "재검토" in plan["reason"]


def test_lineage_items_carry_period_and_sort_by_start(client):
    """과제 상세의 단계 칸이 연도를 적고, 같은 단계는 먼저 시작한 과제가 위로 (TODO 176)."""
    root = _project(client, "1단계", start_date="2024-03-01", due_date="2024-12-20")
    late = _project(client, "2단계 늦게 시작", start_date="2025-05-01", due_date="2025-12-31", predecessors=[root["id"]])
    early = _project(client, "2단계 먼저 시작", status="done", start_date="2025-01-02", due_date="2025-12-31",
                     completed_at="2025-11-30", predecessors=[root["id"]])
    stages = client.get(f"/api/projects/{root['id']}").json()["lineage"]["stages"]
    second = stages[1]["items"]
    assert [item["id"] for item in second] == [early["id"], late["id"]]
    assert second[0]["end_date"] == "2025-11-30"  # 끝난 과제는 끝낸 날
    assert second[1]["end_date"] == "2025-12-31"
    assert stages[0]["items"][0]["end_date"] == "2024-12-20"


# ── 178 단계를 뒤 과제 쪽으로 당겨 센다 ─────────────────────────────────────


def _stage_titles(client, project_id):
    lineage = client.get(f"/api/projects/{project_id}").json()["lineage"]
    return [(group["stage"], sorted(item["title"] for item in group["items"])) for group in lineage["stages"]]


def test_new_project_joining_a_later_stage_sits_right_before_it(client):
    """v11 사용자 확인 — 2년차에 새로 시작해 3년차로 합쳐지는 과제가 1단계로 들어갔다 (TODO 178)."""
    a = _project(client, "1년차 과제")
    b = _project(client, "2년차 이어받은 과제", predecessors=[a["id"]])
    c = _project(client, "2년차 새로 시작한 과제")  # 앞 과제가 없다
    d = _project(client, "3년차 합친 과제", predecessors=[b["id"], c["id"]])
    expected = [(1, ["1년차 과제"]), (2, ["2년차 새로 시작한 과제", "2년차 이어받은 과제"]), (3, ["3년차 합친 과제"])]
    for item in (a, b, c, d):  # 어느 과제에서 봐도 같다
        assert _stage_titles(client, item["id"]) == expected
    # 단계 띠 · 로드맵도 같은 단계
    listed = {row["id"]: row["stage"] for row in client.get("/api/projects").json()}
    assert [listed[item["id"]] for item in (a, b, c, d)] == [1, 2, 2, 3]
    roadmap = client.get("/api/roadmap").json()["lineages"][0]
    assert {p["id"]: p["stage"] for p in roadmap["projects"]} == {a["id"]: 1, b["id"]: 2, c["id"]: 2, d["id"]: 3}


def test_short_chain_is_pulled_next_to_its_successor_but_dead_ends_stay(client):
    a = _project(client, "가1")
    b = _project(client, "가2", predecessors=[a["id"]])
    c = _project(client, "가3", predecessors=[b["id"]])
    x = _project(client, "나1")
    y = _project(client, "나2", predecessors=[x["id"]])
    e = _project(client, "합류", predecessors=[c["id"], y["id"]])
    ended = _project(client, "가2에서 갈라져 끝남", predecessors=[a["id"]])
    stages = dict((title, stage) for stage, titles in _stage_titles(client, e["id"]) for title in titles)
    assert stages == {"가1": 1, "가2": 2, "가3": 3, "나1": 2, "나2": 3, "합류": 4, "가2에서 갈라져 끝남": 2}
    assert ended  # 후속이 없는 갈래는 당기지 않는다 — 마지막 단계로 밀려가지 않는다
