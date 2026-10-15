from harness import *
import threading, zipfile, io

def judge(name, req, r, accept_2xx=False, extra=""):
    st = r.status_code
    if st >= 500: rec(name, req, r, "PROBLEM", "500 " + extra, "⛔")
    elif st >= 400:
        d = detail(r)
        if st == 422: rec(name, req, r, "note", "422 english: " + d[:90] + extra)
        elif not is_korean(d): rec(name, req, r, "PROBLEM", "non-Korean " + d[:80], "🟡")
        else: rec(name, req, r, "ok", d[:80] + extra)
    else: rec(name, req, r, "ok" if accept_2xx else "note", f"{st} " + extra)
    return r

with fresh() as (c, vault):
    # export on empty + Korean names
    judge("export", "backup zip empty vault", c.get("/api/backup"), accept_2xx=True)
    pid = c.post("/api/projects", json={"title": "한글 이름 과제 ★", "body": "![깨진](assets/none.png) ![또](assets/a%20b.png) [문서](assets/x.xlsx)"}).json()["id"]
    eid = c.post(f"/api/projects/{pid}/entries", json={"title": "일지 ★", "date": "2026-03-01", "body": "![x](assets/missing.png) ![y](../other/x.png) ![z](http://ext/x.png) ![w](assets/../index.md)"}).json()["id"]
    rid = c.post(f"/api/projects/{pid}/reports/draft", json={"report_date": "2026-03-05"}).json()["id"]
    c.patch(f"/api/reports/{rid}", json={"body": "![r](assets/gone.png)"}); c.post(f"/api/reports/{rid}/freeze")
    for fmt in ["md", "zip", "html", "backup"]:
        for assets in ["zip", "inline", "link"]:
            r = c.get(f"/api/projects/{pid}/export", params={"format": fmt, "assets": assets, "include_reports_full": "true"})
            judge("export", f"format={fmt} assets={assets}", r, accept_2xx=True, extra=f"disp={r.headers.get('content-disposition','')[:80]} len={len(r.content)}")
            if r.status_code == 200 and fmt in ("zip", "backup"):
                try: zipfile.ZipFile(io.BytesIO(r.content)).testzip()
                except Exception as e: rec("export", f"zip valid {fmt}", r, "PROBLEM", str(e), "🔴")
    judge("export", "format=pdf", c.get(f"/api/projects/{pid}/export", params={"format": "pdf"}))
    judge("export", "include_reports_full=zzz", c.get(f"/api/projects/{pid}/export", params={"include_reports_full": "zzz"}))
    judge("export", "backup zip whole", c.get("/api/backup"), accept_2xx=True)
    # linkfix
    g = c.get("/api/maintenance/link-fix"); judge("linkfix", "scan", g, accept_2xx=True); print("scan:", g.json())
    g = c.get("/api/maintenance/link-fix", params={"include_frozen": "true"}); print("scan frozen:", g.json())
    body_before = c.get(f"/api/entries/{eid}").json()["body"]; ov_before = c.get(f"/api/projects/{pid}").json()["body"]
    r = c.post("/api/maintenance/link-fix", json={"include_frozen": False}); judge("linkfix", "apply", r, accept_2xx=True); print("apply:", r.json())
    body_after = c.get(f"/api/entries/{eid}").json()["body"]; ov_after = c.get(f"/api/projects/{pid}").json()["body"]
    print("entry before:", body_before); print("entry after :", body_after); print("overview before:", ov_before); print("overview after :", ov_after)
    rec("linkfix", "frozen report untouched", 200, "ok" if "assets/gone.png" in c.get(f"/api/reports/{rid}").json()["body"] else "PROBLEM", c.get(f"/api/reports/{rid}").json()["body"][:60], "🔴")
    rec("linkfix", "external/relative-up links untouched", 200, "ok" if "http://ext/x.png" in body_after else "PROBLEM", body_after[:120], "🟡")
    r = c.post("/api/maintenance/link-fix", json={"include_frozen": True}); judge("linkfix", "apply include_frozen", r, accept_2xx=True); print("apply frozen:", r.json())
    print("frozen report body after:", c.get(f"/api/reports/{rid}").json()["body"])
    judge("linkfix", "apply again (idempotent)", c.post("/api/maintenance/link-fix", json={}), accept_2xx=True)
    # reindex concurrently
    results = []
    def rx():
        results.append(c.post("/api/reindex").status_code)
    ts = [threading.Thread(target=rx) for _ in range(4)]
    [t.start() for t in ts]; [t.join() for t in ts]
    rec("reindex", "4 concurrent reindex", 200, "ok" if set(results) == {200} else "PROBLEM", f"{results}", "⛔")
    # reindex while writing
    errs = []
    def writer():
        for i in range(10):
            r = c.post("/api/projects", json={"title": f"동시 {i}"})
            if r.status_code != 201: errs.append(("create", r.status_code, r.text[:100]))
    def reindexer():
        for i in range(5):
            r = c.post("/api/reindex")
            if r.status_code != 200: errs.append(("reindex", r.status_code, r.text[:100]))
    ts = [threading.Thread(target=writer), threading.Thread(target=reindexer), threading.Thread(target=writer)]
    [t.start() for t in ts]; [t.join() for t in ts]
    n_api = len(c.get("/api/projects").json()); n_fs = len(project_dirs(vault))
    rec("reindex", "create+reindex interleaved", 200, "ok" if not errs and n_api == n_fs else "PROBLEM", f"errs={errs} api={n_api} fs={n_fs}", "⛔")
    # broken files on disk → reindex problems → GETs still fine
    bad = vault / "projects" / "2026-999-broken"; (bad / "logs").mkdir(parents=True)
    (bad / "index.md").write_text("---\nid: 2026-999\ntitle: [unclosed\nstatus: {{\n---\nbody", encoding="utf-8")
    (bad / "logs" / "notadate-x.md").write_text("---\ndate: 2026-99-99\n---\nx", encoding="utf-8")
    src_txt = (vault / "projects" / c.get(f"/api/projects/{pid}").json()["dir_name"] / "index.md").read_text(encoding="utf-8")
    dup = vault / "projects" / f"{pid}-복제본"; dup.mkdir(); (dup / "index.md").write_text(src_txt, encoding="utf-8")
    r = c.post("/api/reindex"); judge("reindex", "with broken + duplicate-id folders", r, accept_2xx=True); print("problems:", r.json())
    for path in ["/api/home", "/api/dashboard", "/api/projects", "/api/roadmap", "/api/report-candidates", "/api/meta", "/api/search?q=한글", f"/api/projects/{pid}", "/api/backup"]:
        judge("reindex", f"GET {path} after broken files", c.get(path), accept_2xx=True)
    n_api = len(c.get("/api/projects").json()); n_fs = len(project_dirs(vault))
    rec("reindex", "duplicate id folder: which wins?", 200, "note", f"api={n_api} fs={n_fs} dir_name of {pid}={c.get(f'/api/projects/{pid}').json().get('dir_name')}")
    # external edit then PATCH (ExternalChangeError)
    print("FS now:", project_dirs(vault)); print("project dir_name:", c.get(f"/api/projects/{pid}").json()["dir_name"]); print("trash:", [t["trash_name"] for t in c.get("/api/trash").json()])
    idx = vault / "projects" / c.get(f"/api/projects/{pid}").json()["dir_name"] / "index.md"
    rec("reindex", "dir_name in DB exists on disk after duplicate-id reindex", 200, "ok" if idx.exists() else "PROBLEM", f"{idx.relative_to(vault)} exists={idx.exists()}", "⛔")
    if not idx.exists():
        idx = vault / "projects" / f"{pid}-복제본" / "index.md"
    txt = idx.read_text(encoding="utf-8"); idx.write_text(txt.replace("한글 이름 과제", "외부에서 바꾼"), encoding="utf-8")
    r = c.patch(f"/api/projects/{pid}", json={"body": "덮어쓰기?"})
    g = c.get(f"/api/projects/{pid}").json(); idx2 = vault / "projects" / g["dir_name"] / "index.md"
    rec("external", "PATCH body after external title edit (no reindex)", r, "note", f"status={r.status_code} api title={g['title']!r} dir={g['dir_name']} old_idx_exists={idx.exists()} new_idx_exists={idx2.exists()} fs={[d for d in project_dirs(vault) if d.startswith(pid)]}")
    if idx2.exists(): print("file after:", idx2.read_text(encoding="utf-8")[:300].replace("\n", " | "))
    rec("external", "externally edited title preserved after PATCH body", 200, "ok" if "외부에서" in g["title"] else "PROBLEM", f"title={g['title']!r}", "🔴")
    # delete the folder externally then API ops
    import shutil
    victim = c.post("/api/projects", json={"title": "외부삭제"}).json()["id"]; vd = vault / "projects" / c.get(f"/api/projects/{victim}").json()["dir_name"]
    shutil.rmtree(vd)
    judge("external", "GET project whose folder was deleted", c.get(f"/api/projects/{victim}"), accept_2xx=True)
    judge("external", "PATCH project whose folder was deleted", c.patch(f"/api/projects/{victim}", json={"title": "x"}))
    judge("external", "POST entry to project whose folder was deleted", c.post(f"/api/projects/{victim}/entries", json={"title": "x"}), extra=f"fs now={[d for d in project_dirs(vault) if victim in d]}")
    judge("external", "archive project whose folder was deleted", c.post(f"/api/projects/{victim}/archive"))
    judge("external", "export project whose folder was deleted", c.get(f"/api/projects/{victim}/export"))
    judge("external", "home after folder deleted", c.get("/api/home"), accept_2xx=True)
    # entry file removed externally
    e2 = c.post(f"/api/projects/{pid}/entries", json={"title": "파일삭제", "date": "2026-04-01"}).json()
    (vault / "projects" / c.get(f"/api/projects/{pid}").json()["dir_name"] / e2["rel_path"]).unlink()
    judge("external", "GET entry whose file removed", c.get(f"/api/entries/{e2['id']}"), accept_2xx=True)
    judge("external", "PATCH entry whose file removed", c.patch(f"/api/entries/{e2['id']}", json={"body": "x"}))
    judge("external", "DELETE entry whose file removed", c.delete(f"/api/entries/{e2['id']}"))
    judge("external", "upload to entry whose file removed", c.post(f"/api/entries/{e2['id']}/attachments", files={"file": ("a.png", b"\x89PNG", "image/png")}))
finish("p9_maint")
