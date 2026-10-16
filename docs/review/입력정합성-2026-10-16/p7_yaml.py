from harness import *
with fresh() as (c, v):
    ids = {}
    for t in ['a: "b"\n---\nc: d', "x\x00y\x07z", "yes", "2026-01-01", "null", "~", "'quoted'", "# 해시", "- dash", "﻿bom", "a b", "x\x85y"]:
        r = proj(c, title=t); ids[t] = r.json().get("id") if r.status_code == 201 else r.status_code
    c.post("/api/reindex")
    for t, pid in ids.items():
        if isinstance(pid, int): print(repr(t), "->", pid); continue
        got = c.get(f"/api/projects/{pid}").json()["title"]
        print(repr(t), "->", repr(got), "OK" if got == t.strip() else "MISMATCH")
    pid = proj(c, title="E").json()["id"]
    e = c.post(f"/api/projects/{pid}/entries", json={"title":"t","body":"---\ndate: 1999-01-01\ntitle: injected\n---\nbody"}).json()
    c.post("/api/reindex")
    x = c.get(f"/api/projects/{pid}/entries").json()[0]; print("entry after reindex:", x["date"], x["title"], repr(x["body"][:40]))
    # entry body NUL
    show("entry body NUL", c.post(f"/api/projects/{pid}/entries", json={"title":"n","body":"a\x00b"}))
    show("search NUL", c.get("/api/search", params={"q":"a"}))
