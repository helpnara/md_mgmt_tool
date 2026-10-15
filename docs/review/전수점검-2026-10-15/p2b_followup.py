from harness import *
with fresh() as (c, vault):
    P = "/api/projects"
    ids = {}
    for t in ["a\x00b", "​", "ﾊﾝｶｸ 半角 全角", "...", "정상"]:
        r = c.post(P, json={"title": t}); ids[t] = r.status_code, r.json().get("id")
    r = c.post(P, content='{"title":"nan","effect_expected":NaN}', headers={"content-type": "application/json"}); ids["NaN"] = r.status_code, r.json().get("id")
    r = c.post(P, content='{"title":"inf","effect_expected":Infinity}', headers={"content-type": "application/json"}); ids["Inf"] = r.status_code, r.json().get("id")
    r = c.post(P, json={"title": "T날짜", "start_date": "2026-01-01T00:00:00"}); ids["Tdate"] = r.status_code, r.json().get("id")
    r = c.post(P, json={"title": "잘못날짜", "start_date": "2026-13-01"}); ids["baddate"] = r.status_code, r.json().get("id")
    print(ids)
    api_ids = {p["id"] for p in c.get(P).json()}
    fs = project_dirs(vault)
    print("API ids:", sorted(api_ids)); print("FS:", fs)
    for d in fs:
        pid = d[:8]
        f = vault / "projects" / d / "index.md"
        print("----", d, "in_api=", pid in api_ids)
        print(f.read_text(encoding="utf-8")[:400].replace("\n", " | "))
    ri = c.post("/api/reindex").json(); print("REINDEX", ri)
    print("after reindex API ids:", sorted(p["id"] for p in c.get(P).json()))
    # get each
    for k, (st, pid) in ids.items():
        if pid:
            g = c.get(f"{P}/{pid}"); print(k, pid, g.status_code, g.json().get("title") if g.status_code == 200 else g.text[:100], g.json().get("effect_expected") if g.status_code==200 else "")
    # search / home / dashboard / roadmap / export with this vault
    for path in ["/api/home", "/api/dashboard", "/api/roadmap", "/api/report-candidates", "/api/search?q=a", "/api/projects?period=2026", "/api/projects?sort=start", "/api/backup"]:
        g = c.get(path); print(path, g.status_code, g.text[:120] if g.status_code != 200 else "ok")
    # PATCH title '' case
    pid = ids["정상"][1]
    r = c.patch(f"{P}/{pid}", json={"title": ""}); print("PATCH title '' ->", r.status_code, r.json().get("title"))
    print((vault / "projects" / [d for d in project_dirs(vault) if d.startswith(pid)][0] / "index.md").read_text()[:200].replace("\n", " | "))
    r = c.patch(f"{P}/{pid}", json={"title": "  "}); print("PATCH title '  ' ->", r.status_code, repr(r.json().get("title")), project_dirs(vault)[-1])
    # Tdate: period filter behaviour
    g = c.get(P, params={"period": "2026"}).json(); print("period=2026 ids", [p["id"] for p in g])
    g = c.get(P, params={"sort": "start"}); print("sort=start", g.status_code)
    # export the NUL title project
    for k in ["a\x00b", "NaN", "Tdate", "baddate"]:
        pid = ids[k][1]
        for fmt in ["md", "zip", "html", "backup"]:
            g = c.get(f"{P}/{pid}/export", params={"format": fmt}); print("export", k, fmt, g.status_code, g.text[:100] if g.status_code != 200 else len(g.content))
finish("p2b")
