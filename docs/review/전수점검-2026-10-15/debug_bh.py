import sys, os, tempfile, json
from pathlib import Path
sys.path.insert(0, "/home/user/md_mgmt_tool/backend")
exec(open("/tmp/claude-0/-home-user-md-mgmt-tool/c32970f6-4741-525a-bf74-43fa93408437/scratchpad/backend-sweep/repro.py", encoding="utf-8").read().split("# A. BOM")[0])

def dbg_B():
    c, vault = fresh_client()
    try:
        from app.vault import paths
        p = c.post("/api/projects", json={"title": "원래 제목"}).json()
        print("dirs0", sorted(x.name for x in (vault/"projects").iterdir()))
        orig = paths.move
        def boom(s, t): raise paths.FileInUseError("busy")
        paths.move = boom
        try:
            r1 = c.patch(f"/api/projects/{p['id']}", json={"title": "바뀐 제목"})
        finally:
            paths.move = orig
        print("r1", r1.status_code, r1.text[:200])
        print("dirs1", sorted(x.name for x in (vault/"projects").iterdir()))
        g = c.get(f"/api/projects/{p['id']}").json()
        print("db title", g.get("title"), g.get("dir_name"))
        r2 = c.patch(f"/api/projects/{p['id']}", json={"status": "done"})
        print("r2", r2.status_code, r2.text[:200])
        for f in (vault/"projects").rglob("index.md"): print(f, f.read_text(encoding="utf-8")[:80].replace("\n","|"))
        print(json.dumps([json.loads(l) for f in (vault/".logs").glob("error-*.log") for l in f.read_text().splitlines()], ensure_ascii=False)[:800])
    finally: close(c)

def dbg_H():
    c, vault = fresh_client()
    try:
        from app.vault import paths
        a = c.post("/api/projects", json={"title": "A 과제"}).json()
        b = c.post("/api/projects", json={"title": "B 과제", "predecessors": [a["id"]]}).json()
        orig = paths.move
        calls = {"n": 0}
        def flaky(s, t):
            calls["n"] += 1
            if calls["n"] == 2: raise paths.FileInUseError("busy")
            return orig(s, t)
        paths.move = flaky
        try:
            r1 = c.post("/api/settings/project-code/renumber", json={"code": "X"})
        finally:
            paths.move = orig
        print("r1", r1.status_code, r1.text[:300])
        print("dirs", sorted(x.name for x in (vault/"projects").iterdir()))
        r2 = c.post("/api/settings/project-code/renumber", json={"code": "X"})
        print("r2", r2.status_code, r2.text[:300])
        projects = c.get("/api/projects").json()
        print([(p["id"], p["title"], p["predecessors"], p.get("stage")) for p in projects])
        print("dirs", sorted(x.name for x in (vault/"projects").iterdir()))
        bid = [p["id"] for p in projects if p["title"] == "B 과제"][0]
        print("lineage", c.get(f"/api/projects/{bid}").json()["lineage"])
        print(json.dumps([json.loads(l) for f in (vault/".logs").glob("error-*.log") for l in f.read_text().splitlines()], ensure_ascii=False)[:1200])
    finally: close(c)

dbg_B(); print("=========="); dbg_H()
