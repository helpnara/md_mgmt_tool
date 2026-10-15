"""두 단계 작업의 원자성 · 한 파일 때문에 멈추지 않는 색인 (검토-전수점검-2026-10-15, TODO 199 · 200 · 201 · 206).

중간에 파일이 잠겨 실패하면(윈도우에서 엑셀이 첨부를 잡고 있을 때) 다시 실행했을 때 **같은 것이 둘 생기거나
참조가 옛 번호로 남지 않아야** 한다. 실패는 재현 스크립트(docs/review/전수점검-2026-10-15/)의 모양을 그대로 쓴다.
"""
from __future__ import annotations

import threading

from app.vault import paths


def _project(client, title, **extra):
    response = client.post("/api/projects", json={"title": title, **extra})
    assert response.status_code == 201, response.text
    return response.json()


# ── 201 ③ 번호 변경이 중간에 멈춰도 참조가 남지 않는다 ────────────────────────


def test_renumber_interrupted_midway_resumes_with_correct_refs(client, monkeypatch):
    a = _project(client, "A 과제")
    b = _project(client, "B 과제", predecessors=[a["id"]])
    intake = client.post("/api/intakes", json={"title": "요청"}).json()
    promoted = client.post(f"/api/intakes/{intake['id']}/promote", json={"title": "C 과제"}).json()

    original = paths.move
    calls = {"n": 0}

    def flaky(source, target):
        calls["n"] += 1
        if calls["n"] == 2:  # 두 번째 과제의 폴더 이동에서 잠김
            raise paths.FileInUseError("busy")
        return original(source, target)

    monkeypatch.setattr(paths, "move", flaky)
    first = client.post("/api/settings/project-code/renumber", json={"code": "X"})
    assert first.status_code == 409, first.text
    monkeypatch.setattr(paths, "move", original)

    # 멈춘 자리까지 바뀐 번호를 가리키던 참조는 이미 새 번호다 — 다시 실행하지 않아도.
    rows = {row["title"]: row for row in client.get("/api/projects").json()}
    assert rows["B 과제"]["predecessors"] == ["2026-X-001"]

    second = client.post("/api/settings/project-code/renumber", json={"code": "X"})
    assert second.status_code == 200, second.text
    rows = {row["title"]: row for row in client.get("/api/projects").json()}
    assert {row["id"] for row in rows.values()} == {"2026-X-001", "2026-X-002", "2026-X-003"}
    assert rows["B 과제"]["predecessors"] == [rows["A 과제"]["id"]]
    lineage = client.get(f"/api/projects/{rows['B 과제']['id']}").json()["lineage"]
    assert not any(item["missing"] for stage in lineage["stages"] for item in stage["items"])
    assert client.get(f"/api/intakes/{intake['id']}").json()["project_id"] == rows["C 과제"]["id"]
    # 폴더 이름도 전부 새 번호 — 세 번째 실행은 할 일이 없다
    plan = client.post("/api/settings/project-code/renumber/preview", json={"code": "X"}).json()
    assert plan["changes"] == []
    assert promoted["project_id"] not in {row["id"] for row in rows.values()}


def test_renumber_plan_treats_old_folder_name_as_pending(client, vault_dir):
    """index.md 의 id 는 새 번호인데 폴더는 옛 번호(지난 변경이 폴더 이동에서 멈춘 자국) → 변경 대상."""
    project = _project(client, "폴더만 남은 과제")
    folder = next((vault_dir / "projects").glob(f"{project['id']}-*"))
    index_md = folder / "index.md"
    index_md.write_text(index_md.read_text(encoding="utf-8").replace(f"id: {project['id']}", "id: 2026-X-001"), encoding="utf-8")
    assert client.post("/api/reindex").status_code == 200
    plan = client.post("/api/settings/project-code/renumber/preview", json={"code": "X"}).json()
    assert [(item["id"], item["new_id"], item["folder_only"]) for item in plan["changes"]] == [("2026-X-001", "2026-X-001", True)]
    client.post("/api/settings/project-code/renumber", json={"code": "X"})
    assert sorted(path.name for path in (vault_dir / "projects").iterdir()) == ["2026-X-001-폴더만-남은-과제"]


# ── 201 ④ 되돌리기가 423 뒤 다시 눌러도 접수는 하나 ──────────────────────────


def test_demote_locked_then_retry_makes_exactly_one_intake(client, monkeypatch):
    project = _project(client, "되돌릴 과제", type="smart")
    client.post(f"/api/projects/{project['id']}/entries", json={"title": "기록", "body": "x"})
    original = paths.move

    def locked(source, target):
        if source.name.startswith(project["id"]):
            raise paths.FileInUseError("busy")
        return original(source, target)

    monkeypatch.setattr(paths, "move", locked)
    first = client.post(f"/api/projects/{project['id']}/to-intake")
    assert first.status_code == 423
    # 실패할 일을 먼저 했으니 아무것도 바뀐 것이 없다 — 과제는 그대로, 접수는 없다
    assert client.get(f"/api/projects/{project['id']}").status_code == 200
    assert client.get("/api/intakes").json()["items"] == []

    monkeypatch.setattr(paths, "move", original)
    second = client.post(f"/api/projects/{project['id']}/to-intake")
    assert second.status_code == 201, second.text
    items = client.get("/api/intakes").json()["items"]
    assert [(item["title"], item["status"]) for item in items] == [("되돌릴 과제", "reviewing")]
    intake = client.get(f"/api/intakes/{items[0]['id']}").json()
    assert intake["demoted_from"] == project["id"] and "기록" in [log["title"] for log in intake["logs"]]
    assert client.get(f"/api/projects/{project['id']}").status_code == 404


# ── 199 ⑪ 사전점검 값 하나가 재색인을 멈추지 않는다 ───────────────────────────


def test_malformed_precheck_is_a_problem_not_a_crash(client, vault_dir):
    intake = client.post("/api/intakes", json={"title": "요청"}).json()
    request = vault_dir / "intakes" / intake["dir_name"] / "request.md"
    text = request.read_text(encoding="utf-8").replace(
        "precheck: null",
        "precheck:\n  items:\n  - choice: 있음\n    score: 십\n    group: 데이터\n    item: x\n  - choice: 있음\n    score: 3\n    item: y\n",
    )
    request.write_text(text, encoding="utf-8")

    reindex = client.post("/api/reindex")
    assert reindex.status_code == 200, reindex.text
    problems = [item for item in reindex.json()["problems"] if item["path"].endswith("request.md")]
    assert problems and "사전점검" in problems[0]["reason"] and "request.md" in problems[0]["reason"]
    assert any("십" in item["reason"] for item in problems)
    assert any("group" in item["reason"] for item in problems)

    detail = client.get(f"/api/intakes/{intake['id']}")
    assert detail.status_code == 200
    assert detail.json()["precheck"]["score"] is None  # 틀린 점수를 보이느니 비운다
    assert detail.json()["precheck"]["problems"]
    assert client.get("/api/meta").json()["problems"]

    from app.services import precheck
    from app.vault.indexer import reindex_all
    from app import deps

    assert precheck.summarize({"items": [{"choice": "있음"}]})["problems"]
    assert precheck.summarize("글자")["problems"]
    assert precheck.summarize({"items": "글자"})["rated"] == 0
    reindex_all(deps._conn)  # 기동 재색인도 같은 길 — 예외 없이


# ── 201 ㉑ 승격이 과제를 만든 뒤 실패해도 과제가 둘 되지 않는다 ───────────────


def test_promote_failing_attachment_copy_leaves_no_duplicate_project(client, monkeypatch):
    from app.services import intakes as svc

    intake = client.post("/api/intakes", json={"title": "첨부 있는 요청"}).json()
    upload = client.post(f"/api/intakes/{intake['id']}/attachments", files={"file": ("a.txt", b"attached", "text/plain")})
    assert upload.status_code == 201, upload.text

    def boom(*args, **kwargs):
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(svc.shutil, "copytree", boom)
    first = client.post(f"/api/intakes/{intake['id']}/promote", json={"title": "승격 과제"})
    assert first.status_code == 500, first.text
    assert "보관함" in first.json()["detail"] and "다시 승격" in first.json()["detail"]
    assert client.get("/api/projects").json() == []  # 만든 과제는 보관함으로
    assert client.get(f"/api/intakes/{intake['id']}").json()["status"] == "received"  # 접수는 풀에 그대로
    assert any(item["kind"] == "project" for item in client.get("/api/trash").json())

    monkeypatch.undo()
    second = client.post(f"/api/intakes/{intake['id']}/promote", json={"title": "승격 과제"})
    assert second.status_code == 201, second.text
    projects = client.get("/api/projects").json()
    assert [row["title"] for row in projects] == ["승격 과제"]
    assert client.get(f"/api/intakes/{intake['id']}").json()["project_id"] == projects[0]["id"]
    assert client.get(f"/api/projects/{projects[0]['id']}/attachments").status_code == 200


# ── 200 ⑩ 접수의 파일 오류는 507 + 영문 errno 가 아니다 ─────────────────────


def test_intake_file_errors_are_korean_409_423_not_507(client, vault_dir):
    intake = client.post("/api/intakes", json={"title": "밖에서 지운 접수"}).json()
    import shutil

    shutil.rmtree(vault_dir / "intakes" / intake["dir_name"])
    response = client.patch(f"/api/intakes/{intake['id']}", json={"title": "고침"})
    assert response.status_code == 409, response.text
    assert "파일이 폴더에 없습니다" in response.json()["detail"] and "다시 읽기" in response.json()["detail"]
    assert "Errno" not in response.json()["detail"]


# ── 206 ㉚ 쓰기 잠금은 영원히 기다리지 않는다 ────────────────────────────────


def test_write_lock_times_out_with_503(client, monkeypatch):
    from app import deps

    monkeypatch.setattr(deps, "WRITE_LOCK_TIMEOUT", 0.2)
    assert deps._write_lock.acquire(timeout=1)
    try:
        response = client.post("/api/projects", json={"title": "기다리다 지침"})
    finally:
        deps._write_lock.release()
    assert response.status_code == 503
    assert "다른 저장이 끝나기를" in response.json()["detail"]
    assert client.post("/api/projects", json={"title": "이제 된다"}).status_code == 201


# ── 206 ㉕ 이전 버전 보관 실패는 삼키되 점검에 남는다 ──────────────────────────


def test_version_keep_failure_is_recorded_once_and_shown(client, monkeypatch):
    from app.vault import versions

    monkeypatch.setattr(versions, "KEEP_FAILURES", {})

    def too_long(bucket):
        raise OSError(36, "File name too long")

    monkeypatch.setattr(versions, "_free_name", too_long)
    project = _project(client, "긴 경로 과제")
    assert client.patch(f"/api/projects/{project['id']}", json={"status": "done"}).status_code == 200  # 저장은 된다
    assert client.patch(f"/api/projects/{project['id']}", json={"status": "in_progress"}).status_code == 200
    failures = client.get("/api/settings").json()["version_keep_failures"]
    assert len(failures) == 1 and failures[0]["path"].endswith("index.md") and "경로가 너무 깁니다" in failures[0]["reason"]
    assert client.get("/api/health").json()["version_keep_failures"] == failures
