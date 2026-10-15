import sys, os, time
sys.path.insert(0, "/home/user/md_mgmt_tool/backend")
exec(open("/tmp/claude-0/-home-user-md-mgmt-tool/c32970f6-4741-525a-bf74-43fa93408437/scratchpad/backend-sweep/repro.py", encoding="utf-8").read().split("# A. BOM")[0])
c, vault = fresh_client()
try:
    from app.vault import paths
    p = c.post("/api/projects", json={"title": "원래 제목"}).json()
    time.sleep(1.3)  # project was created a while ago
    orig = paths.move
    paths.move = lambda s, t: (_ for _ in ()).throw(paths.FileInUseError("busy"))
    try: r1 = c.patch(f"/api/projects/{p['id']}", json={"title": "바뀐 제목"})
    finally: paths.move = orig
    r2 = c.patch(f"/api/projects/{p['id']}", json={"status": "done"})
    print("first", r1.status_code, "| retry:", r2.status_code, r2.text[:140])
    g = c.get(f"/api/projects/{p['id']}").json()
    print("GET after reload title:", g["title"], "| retry after reload:", c.patch(f"/api/projects/{p['id']}", json={"status": "done"}).status_code)
    # same for report date move
    rep = c.post(f"/api/projects/{p['id']}/reports/draft", json={"report_date": "2026-03-03"}).json()
    time.sleep(1.3)
    paths.move = lambda s, t: (_ for _ in ()).throw(paths.FileInUseError("busy"))
    try: q1 = c.patch(f"/api/reports/{rep['id']}", json={"report_date": "2026-03-10"})
    finally: paths.move = orig
    q2 = c.patch(f"/api/reports/{rep['id']}", json={"audience": "팀장"})
    print("report: first", q1.status_code, "| retry:", q2.status_code, q2.text[:120])
finally: close(c)
