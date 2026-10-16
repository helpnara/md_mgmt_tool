from harness import *
with fresh() as (c, v):
    pid = proj(c, title="P", start_date="2026-03-01", due_date="2026-06-30", status="done", completed_at="2026-06-30").json()["id"]
    show("entry before start", c.post(f"/api/projects/{pid}/entries", json={"date":"2025-01-01","title":"early"}))
    show("entry after completed", c.post(f"/api/projects/{pid}/entries", json={"date":"2026-09-01","title":"late"}))
    show("entry far future", c.post(f"/api/projects/{pid}/entries", json={"date":"9999-12-31","title":"future"}))
    show("entry year 0001", c.post(f"/api/projects/{pid}/entries", json={"date":"0001-01-01","title":"ancient"}))
    show("entry author long+newline", c.post(f"/api/projects/{pid}/entries", json={"title":"au","author":"a\nb"+"x"*200}))
    show("entry title 500 + newline", c.post(f"/api/projects/{pid}/entries", json={"title":"t\n"+"y"*500}))
    show("entry tags", c.post(f"/api/projects/{pid}/entries", json={"title":"tg","tags":["AI","ai"," AI","#AI"]}))
    p = c.get(f"/api/projects/{pid}").json()
    print("project updated_at:", p["updated_at"])
    lst = c.get("/api/projects", params={"sort":"updated"}).json()
    print("dirs logs:", sorted(x.name for x in (find_index(v,pid).parent/"logs").iterdir()))
    print("== reports ==")
    show("report far future", c.post(f"/api/projects/{pid}/reports/draft", json={"report_date":"9999-12-31"}))
    r = show("report before entries", c.post(f"/api/projects/{pid}/reports/draft", json={"report_date":"2020-01-01"}))
    show("report compact date", c.post(f"/api/projects/{pid}/reports/draft", json={"report_date":"20260101"}))
    show("report week date", c.post(f"/api/projects/{pid}/reports/draft", json={"report_date":"2026-W02-1"}))
    rep = c.get(f"/api/projects/{pid}/reports").json()
    for x in rep: print("   report", x["id"], x["report_date"], x.get("covers_from"), x.get("covers_to"))
    fut = [x for x in rep if x["report_date"]=="9999-12-31"][0]
    show("freeze future", c.post(f"/api/reports/{fut['id']}/freeze"))
    p = c.get(f"/api/projects/{pid}").json(); print("last_reported_at:", p["last_reported_at"])
    show("candidates", c.get("/api/report-candidates"))
with fresh() as (c, v):
    print("== report date moved earlier then freeze: covers_to ==")
    pid = proj(c, title="Q").json()["id"]
    for d in ("2026-09-01","2026-09-10","2026-09-20"):
        c.post(f"/api/projects/{pid}/entries", json={"date":d,"title":"e"+d})
    rid = c.post(f"/api/projects/{pid}/reports/draft", json={"report_date":"2026-09-30"}).json()["id"]
    show("move date earlier", c.patch(f"/api/reports/{rid}", json={"report_date":"2026-09-05"}))
    show("freeze", c.post(f"/api/reports/{rid}/freeze"))
    x = c.get(f"/api/reports/{rid}").json(); print("covers", x.get("covers_from"), x.get("covers_to"), x["report_date"])
    print([ (e["date"], e["reported_on"]) for e in c.get(f"/api/projects/{pid}/entries").json()])
    md = [p for p in (find_index(v,pid).parent/"reports").rglob("report.md")][0].read_text().split("---")[1]
    print(md)
with fresh() as (c, v):
    print("== report problem path refresh ==")
    pid = proj(c, title="R").json()["id"]
    rid = c.post(f"/api/projects/{pid}/reports/draft", json={"report_date":"2026-09-30"}).json()["id"]
    rp = [p for p in (find_index(v,pid).parent/"reports").rglob("report.md")][0]
    rp.write_text(rp.read_text().replace("report_date: '2026-09-30'", "report_date: '2026-13-40'").replace("report_date: 2026-09-30", "report_date: '2026-13-40'"))
    r = show("reindex", c.post("/api/reindex"))
    for i in range(3):
        c.post(f"/api/projects/{pid}/entries", json={"title":"x"})
    m = c.get("/api/meta").json()
    print("problems after 3 saves:", [ (p["path"]) for p in m["problems"]])
    # entry hand edit with non-date filename
    (find_index(v,pid).parent/"logs"/"notes.md").write_text("---\ntitle: hand\n---\nbody")
    (find_index(v,pid).parent/"logs"/"메모.md").write_text("no front matter")
    show("reindex2", c.post("/api/reindex"))
    print([(e["date"], e["title"]) for e in c.get(f"/api/projects/{pid}/entries").json()])
