"""과제의 '진행 상태'와 '성격(속성)'은 서로 다른 축이다."""
from __future__ import annotations


def test_a_project_of_any_type_can_reach_done(client):
    """기획보고가 상태였을 때는 그 과제가 영영 완료될 수 없었다."""
    project = client.post(
        "/api/projects", json={"title": "기획보고 과제", "type": "plan_report", "status": "planned"}
    ).json()
    assert project["type"] == "plan_report"
    assert project["status"] == "planned"

    done = client.patch(f"/api/projects/{project['id']}", json={"status": "done"}).json()
    assert done["status"] == "done"
    assert done["type"] == "plan_report"  # 속성은 그대로 남는다


def test_type_is_written_to_the_file(client, vault_dir):
    project = client.post("/api/projects", json={"title": "속성 확인", "type": "rnd"}).json()
    raw = (vault_dir / "projects" / f"{project['id']}-속성-확인" / "index.md").read_text(encoding="utf-8")
    assert "status: in_progress" in raw
    assert "type: rnd" in raw


def test_unknown_status_or_type_is_rejected(client):
    assert client.post("/api/projects", json={"title": "x", "status": "없는상태"}).status_code == 400
    assert client.post("/api/projects", json={"title": "x", "type": "없는속성"}).status_code == 400


def test_projects_can_be_filtered_by_type(client):
    smart = client.post("/api/projects", json={"title": "스마트 과제", "type": "smart"}).json()
    client.post("/api/projects", json={"title": "국책 과제", "type": "national"})
    client.post("/api/projects", json={"title": "속성 없음"})

    filtered = [item["id"] for item in client.get("/api/projects", params={"type": "smart"}).json()]
    assert filtered == [smart["id"]]
    assert len(client.get("/api/projects").json()) == 3


def test_legacy_status_values_are_migrated_on_read(client, vault_dir):
    """예전에 상태로 쓰이던 기획보고·제안·검토를 새 체계로 옮겨 읽는다."""
    project = client.post("/api/projects", json={"title": "구버전 과제"}).json()
    path = vault_dir / "projects" / f"{project['id']}-구버전-과제" / "index.md"

    for legacy, expected_status, expected_type in [
        ("plan_report", "planned", "plan_report"),
        ("proposal", "planned", None),
        ("review", "reviewing", None),
    ]:
        raw = path.read_text(encoding="utf-8")
        path.write_text(
            "\n".join(
                line if not line.startswith("status:") else f"status: {legacy}"
                for line in raw.splitlines()
            )
            + "\n",
            encoding="utf-8",
        )
        client.post("/api/reindex")
        loaded = client.get(f"/api/projects/{project['id']}").json()
        assert loaded["status"] == expected_status, legacy
        assert loaded["type"] == expected_type, legacy


def test_report_candidates_cover_the_early_stages(client):
    """예정·검토중 과제도 보고 대상 후보에 오른다 (보류·완료·중단은 제외)."""
    for status in ("planned", "reviewing", "in_progress"):
        client.post("/api/projects", json={"title": f"{status} 과제", "status": status})
    for status in ("on_hold", "done", "dropped"):
        client.post("/api/projects", json={"title": f"{status} 과제", "status": status})

    titles = [item["title"] for item in client.get("/api/report-candidates").json()["items"]]
    assert sorted(titles) == sorted(["planned 과제", "reviewing 과제", "in_progress 과제"])


def test_maintenance_is_a_type_you_can_pick_and_filter(client):
    """유지보수 (TODO 99).

    시작과 끝이 뚜렷한 나머지 넷과 성격이 다르지만, 팀이 실제로 시간을 쓰는 축이다.
    새 속성 하나를 더하는 일은 목록에 이름을 넣는 것으로 끝나야 한다 —
    거르기·대시보드·홈이 모두 같은 목록을 보기 때문이다.
    """
    labels = [item["label"] for item in client.get("/api/meta").json()["types"]]
    assert "유지보수" in labels

    made = client.post("/api/projects", json={"title": "설비 제어 SW 유지보수", "type": "maintenance"})
    assert made.status_code == 201
    assert made.json()["type"] == "maintenance"

    # 골라서 거를 수 있어야 한다 — 목록에만 있고 안 걸리면 더 나쁘다.
    listed = client.get("/api/projects", params={"type": "maintenance"}).json()
    assert [row["title"] for row in listed] == ["설비 제어 SW 유지보수"]

    # 대시보드도 같은 목록을 보므로 칸이 저절로 하나 는다.
    counts = {row["key"]: row["count"] for row in client.get("/api/dashboard").json()["types"]}
    assert counts["maintenance"] == 1
