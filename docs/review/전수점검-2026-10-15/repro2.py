import sys, os, tempfile, json, time
from pathlib import Path
sys.path.insert(0, "/home/user/md_mgmt_tool/backend")
exec(open("/tmp/claude-0/-home-user-md-mgmt-tool/c32970f6-4741-525a-bf74-43fa93408437/scratchpad/backend-sweep/repro.py", encoding="utf-8").read().split("# A. BOM")[0])

def B2():
    c, vault = fresh_client()
    try:
        from app.vault import paths
        p = c.post("/api/projects", json={"title": "원래 제목"}).json()
        orig = paths.move
        paths.move = lambda s, t: (_ for _ in ()).throw(paths.FileInUseError("busy"))
        try: r1 = c.patch(f"/api/projects/{p['id']}", json={"title": "바뀐 제목"})
        finally: paths.move = orig
        time.sleep(1.3)  # user closes Excel and retries a couple of seconds later
        r2 = c.patch(f"/api/projects/{p['id']}", json={"status": "done"})
        print("B2 first", r1.status_code, "| retry:", r2.status_code, r2.text[:120])
        r3 = c.patch(f"/api/projects/{p['id']}", json={"status": "done"})
        print("B2 retry again", r3.status_code, "| GET title:", c.get(f"/api/projects/{p['id']}").json()["title"])
    finally: close(c)

def M():
    # hand-edited id in index.md (folder name unchanged) -> reindex -> restart
    c, vault = fresh_client()
    p = c.post("/api/projects", json={"title": "손으로 고침"}).json()
    d = vault / "projects" / c.get(f"/api/projects/{p['id']}").json()["dir_name"] / "index.md"
    d.write_text(d.read_text(encoding="utf-8").replace("id: 2026-001", "id: 2026-007"), encoding="utf-8")
    r = c.post("/api/reindex")
    print("M reindex after hand id edit:", r.status_code, r.text[:80])
    close(c)
    # restart the app on the same vault
    os.environ["MD_MGMT_VAULT"] = str(vault)
    from app.config import get_settings; get_settings.cache_clear()
    from fastapi.testclient import TestClient
    from app.main import app
    try:
        with TestClient(app) as c2:
            print("M restart ok, projects:", [x["id"] for x in c2.get("/api/projects").json()])
    except Exception as exc:
        print("M RESTART CRASH:", type(exc).__name__, str(exc)[:120])
    get_settings.cache_clear()

def N():
    os.environ["MD_MGMT_SHARE"] = "1"
    try:
        c, vault = fresh_client()
        try:
            p = c.post("/api/projects", json={"title": "공유 과제", "owners": ["김퇴사"]}).json()
            c.put("/api/people", json={"people": [{"name": "김퇴사", "employee_id": "E123", "left_on": "2026-01-01", "left_reason": "퇴사"}]})
            e = c.post(f"/api/projects/{p['id']}/entries", json={"title": "기록", "body": "비밀 내용"}).json()
            c.post(f"/api/entries/{e['id']}/attachments", files={"file": ("a.txt", b"attached", "text/plain")})
            from fastapi.testclient import TestClient
            from app.main import app
            remote = TestClient(app, raise_server_exceptions=False, client=("10.0.0.5", 5555))
            for path in [f"/api/projects/{p['id']}/export?format=backup", "/api/maintenance/link-fix", "/api/home",
                         "/api/meta", "/api/activities/summary", f"/api/projects/{p['id']}/clone", "/api/search?q=비밀",
                         "/api/settings/backup/status", "/api/backup", "/api/versions/overview", "/api/reindex"]:
                r = remote.get(path) if path != "/api/reindex" else remote.post(path)
                body = r.text
                leak = ""
                if path == "/api/home": leak = f"owner_gaps={r.json()['this_week']['owner_gaps']}"
                if path == "/api/meta" and r.status_code == 200: leak = f"people_left={r.json()['people_left']} people={r.json()['people']}"
                print(f"N {path}: {r.status_code} {len(body)}B {leak}")
            # owner using hostname URL from the server PC itself: client host is LAN IP
            lan = TestClient(app, raise_server_exceptions=False, client=("192.168.0.10", 5555))
            print("N owner-via-LAN-ip PATCH:", lan.patch(f"/api/projects/{p['id']}", json={"status": "done"}).status_code)
        finally: close(c)
    finally:
        os.environ.pop("MD_MGMT_SHARE", None)

B2(); print("====="); M(); print("====="); N()
