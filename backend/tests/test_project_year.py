"""과제 번호의 연도는 **착수년도**다 (TODO 95).

지난해에 한 과제를 올해 뒤늦게 등록하는 일이 실제로 있다. 그때까지는 번호가 등록한 날의
연도로 붙어서, 시작일을 2025-01-01 로 적어도 `2026-…` 이 되고 홈·대시보드·목록에서
전부 올해 것으로 세였다 — 연도를 가르는 기준이 **과제 번호 앞 네 자리**이기 때문이다.

여기서 고정하는 것 둘.

1. **만들 때** 번호의 연도는 시작일에서 온다.
2. **이미 만든 과제**의 번호는 자동으로 바뀌지 않는다. 어긋난 사실을 알려 주고,
   사용자가 눌렀을 때만 옮긴다.
"""
from __future__ import annotations

from datetime import date


def make(client, title, **extra):
    return client.post("/api/projects", json={"title": title, **extra}).json()


def this_year() -> str:
    return str(date.today().year)


# ── 만들 때 ──────────────────────────────────────────────────────────────────

def test_number_year_comes_from_the_start_date(client):
    project = make(client, "2025년 수명평가 표준화", start_date="2025-01-01")
    assert project["id"].startswith("2025-"), project["id"]


def test_number_year_falls_back_to_this_year_without_a_start_date(client):
    project = make(client, "시작일 없는 과제")
    assert project["id"].startswith(f"{this_year()}-"), project["id"]


def test_the_team_code_still_sits_in_the_middle(client):
    client.put("/api/settings", json={"project_code": "선강DX개발팀"})
    project = make(client, "지난해 과제", start_date="2025-03-02")
    assert project["id"] == "2025-선강DX개발팀-001", project["id"]


def test_each_year_counts_its_own_sequence(client):
    first = make(client, "2025 첫째", start_date="2025-01-01")
    second = make(client, "2025 둘째", start_date="2025-06-01")
    now = make(client, "올해 것", start_date=f"{this_year()}-01-01")
    assert first["id"].endswith("-001")
    assert second["id"].endswith("-002")
    # 연도가 다르면 일련번호는 다시 001 부터다.
    assert now["id"].endswith("-001")


def test_a_nonsense_start_date_does_not_make_a_nonsense_year(client):
    # 오타로 0025-01-01 이 들어오면 없는 연도의 번호가 생긴다. 그때는 올해로 둔다.
    project = make(client, "오타", start_date="0025-01-01")
    assert project["id"].startswith(f"{this_year()}-"), project["id"]


def test_the_form_can_ask_which_number_it_would_get(client):
    make(client, "먼저 만든 2025 과제", start_date="2025-02-02")
    preview = client.get("/api/projects/next-id", params={"start_date": "2025-09-01"}).json()
    assert preview["year"] == 2025
    assert preview["id"] == "2025-002"
    # 미리보기는 자리를 차지하지 않는다 — 여러 번 물어도 같은 답이다.
    assert client.get("/api/projects/next-id", params={"start_date": "2025-09-01"}).json() == preview


def test_next_id_without_a_start_date_is_this_year(client):
    preview = client.get("/api/projects/next-id").json()
    assert preview["year"] == date.today().year
    assert preview["id"].startswith(f"{this_year()}-")


# ── 이미 만든 과제 ───────────────────────────────────────────────────────────

def test_changing_the_start_date_does_not_move_the_number_by_itself(client):
    project = make(client, "나중에 시작일을 채운 과제")
    kept = project["id"]
    client.patch(f"/api/projects/{kept}", json={"start_date": "2025-01-01"})
    # 번호는 이미 보고 자리에서 불린 이름이다. 소리 없이 움직이면 그 편이 더 위험하다.
    assert client.get(f"/api/projects/{kept}").json()["id"] == kept


def test_the_screen_is_told_the_number_and_the_start_date_disagree(client):
    project = make(client, "지난해 과제인데 올해 등록")
    client.patch(f"/api/projects/{project['id']}", json={"start_date": "2025-01-01"})
    plan = client.get(f"/api/projects/{project['id']}/year-fix").json()
    assert plan["new_id"] == "2025-001"
    assert plan["from_year"] == this_year()
    assert plan["to_year"] == "2025"
    assert plan["reason"] is None


def test_nothing_to_say_when_the_number_already_matches(client):
    project = make(client, "맞는 과제", start_date="2025-05-05")
    plan = client.get(f"/api/projects/{project['id']}/year-fix").json()
    assert plan["new_id"] is None
    assert plan["reason"] == "이미 맞습니다."


def test_nothing_to_say_without_a_start_date(client):
    project = make(client, "시작일 없음")
    plan = client.get(f"/api/projects/{project['id']}/year-fix").json()
    assert plan["new_id"] is None
    assert plan["reason"] == "시작일이 비어 있습니다."


def test_moving_the_number_moves_the_folder_and_keeps_everything(client, vault_dir):
    project = make(client, "지난해 과제")
    old_id = project["id"]
    client.post(f"/api/projects/{old_id}/entries", json={
        "date": "2025-03-10", "title": "1차 시험", "body": "## 내용\n\n돌려 봤다\n",
    })
    client.patch(f"/api/projects/{old_id}", json={"start_date": "2025-01-02"})

    done = client.post(f"/api/projects/{old_id}/year-fix").json()
    new_id = done["new_id"]
    assert new_id == "2025-001"

    # 옛 번호는 사라지고 새 번호로 열린다.
    assert client.get(f"/api/projects/{old_id}").status_code == 404
    moved = client.get(f"/api/projects/{new_id}").json()
    assert moved["title"] == "지난해 과제"

    # 진행일지는 폴더째 따라온다.
    entries = client.get(f"/api/projects/{new_id}/entries").json()
    assert len(entries) == 1
    assert entries[0]["title"] == "1차 시험"

    # 파일이 원본이다 — 폴더 이름과 front matter 의 id 가 함께 바뀌어야 한다.
    folder = vault_dir / "projects" / done["new_dir_name"]
    assert folder.is_dir()
    assert not (vault_dir / "projects" / done["dir_name"]).exists()
    assert "id: 2025-001" in (folder / "index.md").read_text(encoding="utf-8")


def test_the_moved_project_is_counted_in_its_own_year(client):
    project = make(client, "지난해 과제")
    client.patch(f"/api/projects/{project['id']}", json={"start_date": "2025-01-02"})
    client.post(f"/api/projects/{project['id']}/year-fix")

    # 연도를 가르는 기준은 번호 앞 네 자리다 (DESIGN 5.8). 옮긴 뒤 2025 쪽에 선다.
    listed = client.get("/api/projects", params={"year": "2025"}).json()
    assert [row["id"] for row in listed] == ["2025-001"]
    assert client.get("/api/projects", params={"year": this_year()}).json() == []
    assert client.get("/api/dashboard", params={"year": "2025"}).json()["total"] == 1


def test_the_moved_project_never_takes_a_number_that_year_already_uses(client):
    taken = make(client, "이미 2025-001", start_date="2025-01-01")
    assert taken["id"] == "2025-001"

    late = make(client, "뒤늦게 등록")
    client.patch(f"/api/projects/{late['id']}", json={"start_date": "2025-08-08"})
    plan = client.get(f"/api/projects/{late['id']}/year-fix").json()
    # 그 해의 다음 번호다. 겹치면 폴더가 서로를 덮으므로 이것이 먼저다.
    assert plan["new_id"] == "2025-002"
    assert plan["renumbered"] is True

    done = client.post(f"/api/projects/{late['id']}/year-fix").json()
    assert done["new_id"] == "2025-002"
    assert client.get("/api/projects/2025-001").json()["title"] == "이미 2025-001"


def test_the_moved_project_takes_that_years_next_number(client):
    # 일련번호를 그대로 들고 가면 2025년에 003 하나만 덩그러니 선다.
    # 처음부터 그 해에 만들었더라면 받았을 번호를 준다.
    make(client, "올해 첫째")
    make(client, "올해 둘째")
    late = make(client, "올해 셋째인데 사실 지난해 것")
    assert late["id"].endswith("-003")

    client.patch(f"/api/projects/{late['id']}", json={"start_date": "2025-07-07"})
    plan = client.get(f"/api/projects/{late['id']}/year-fix").json()
    assert plan["new_id"] == "2025-001"
    assert plan["renumbered"] is True


def test_the_kept_versions_follow_the_folder(client, vault_dir):
    project = make(client, "고쳐 가며 쓴 과제")
    old_id = project["id"]
    # 두 번 고쳐 이전 버전을 쌓는다.
    client.patch(f"/api/projects/{old_id}", json={"body": "첫 벌\n"})
    client.patch(f"/api/projects/{old_id}", json={"body": "둘째 벌\n"})
    old_dir = client.get(f"/api/projects/{old_id}").json()["dir_name"]
    assert (vault_dir / ".versions" / "projects" / old_dir).is_dir()

    client.patch(f"/api/projects/{old_id}", json={"start_date": "2025-04-04"})
    done = client.post(f"/api/projects/{old_id}/year-fix").json()

    # 보관본은 경로를 열쇠로 쓴다. 함께 옮기지 않으면 그때까지 쌓인 것이 미아가 된다.
    assert not (vault_dir / ".versions" / "projects" / old_dir).exists()
    assert (vault_dir / ".versions" / "projects" / done["new_dir_name"]).is_dir()
    versions = client.get(
        "/api/versions", params={"rel_path": f"projects/{done['new_dir_name']}/index.md"}
    ).json()
    assert len(versions) >= 1


def test_a_missing_project_is_a_404(client):
    assert client.get("/api/projects/2025-999/year-fix").status_code == 404
    assert client.post("/api/projects/2025-999/year-fix").status_code == 404
