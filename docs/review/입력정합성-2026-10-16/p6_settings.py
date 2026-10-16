from harness import *
import json as J
with fresh() as (c, v):
    print("== settings via API ==")
    for k, val in [("project_code","팀-2"),("project_code","R&D"),("project_code","a"*21),("project_code","소재."),("project_code","CON"),("project_code","x#y"),
                   ("intake_stale_days",0),("intake_stale_days",1000),("meeting_cycle_days",-1),("backup_keep",0),("backup_keep_weekly",100000),
                   ("precheck_thresholds",[60,80]),("precheck_thresholds",[0,0]),("entry_templates",{"없는속성":"x","":"y"*200000}),
                   ("report_template","no summary placeholder"),("author","a"*41),("meeting_kinds",["a"]*5),("classifications",{"nature":["가"]*3,"category":[]})]:
        show(f"{k}={str(val)[:30]}", c.put("/api/settings", json={k: val}))
    show("types empty", c.put("/api/settings/project-types", json={"types":[]}))
    show("types dup labels", c.put("/api/settings/project-types", json={"types":[{"label":"A"},{"label":"A "}]}))
    show("types case", c.put("/api/settings/project-types", json={"types":[{"label":"AI"},{"label":"ai"}]}))
with fresh() as (c, v):
    print("== project code with digit segment ==")
    show("code 팀-2", c.put("/api/settings", json={"project_code":"팀-2"}))
    pid = proj(c, title="P", start_date="2025-03-01").json()["id"]; print("pid", pid)
    show("year-fix plan", c.get(f"/api/projects/{pid}/year-fix"))
    show("renumber preview to ''", c.post("/api/settings/project-code/renumber/preview", json={"code":""}))
    show("draft key overview", c.put(f"/api/drafts/overview:{pid}", json={"content":"x"}))
with fresh() as (c, v):
    print("== R&D code: drafts ==")
    show("code R&D", c.put("/api/settings", json={"project_code":"R&D"}))
    pid = proj(c, title="P").json()["id"]; print("pid", pid)
    show("draft overview", c.put(f"/api/drafts/overview:{pid}", json={"content":"x"}))
    show("draft entry new", c.put(f"/api/drafts/entry:new-{pid}", json={"content":{"body":"x"}}))
    show("draft orphan entry id", c.put("/api/drafts/entry:999999", json={"content":"x"}))
    show("drafts list", c.get("/api/drafts"))
with fresh() as (c, v):
    print("== hand-edited settings.json ==")
    (v/"settings.json").write_text(J.dumps({"intake_stale_days": 100000, "backup_keep": 999999, "meeting_cycle_days": 10**9,
        "people":[{"name":"A","left_on":"어제"},{"name":"A","employee_id":"9"},{"name":" B "}], "project_types":[{"key":"x"},{"key":"smart","label":"스마트"}],
        "precheck_thresholds":[200,-5], "report_weekday": 9, "project_code":"a/b"}, ensure_ascii=False))
    s = show("settings", c.get("/api/settings"))
    print("people", s["people"], "unreadable", s["unreadable"], "code", s["project_code"])
    show("create project with bad code in file", proj(c, title="P"))
    print(sorted(p.name for p in (v/"projects").rglob("*") if p.is_dir())[:5])
with fresh() as (c, v):
    print("== demote with hand-edited bad dates ==")
    pid = proj(c, title="D", start_date="2026-01-01", due_date="2026-02-01").json()["id"]
    p = find_index(v, pid); p.write_text(p.read_text().replace("due_date: '2026-02-01'", "due_date: '2025-01-01'").replace("due_date: 2026-02-01", "due_date: '2025-01-01'"))
    c.post("/api/reindex")
    show("to-intake plan", c.get(f"/api/projects/{pid}/to-intake"))
    show("to-intake do", c.post(f"/api/projects/{pid}/to-intake"))
    show("project now", c.get(f"/api/projects/{pid}"))
    show("intakes", c.get("/api/intakes"))
    show("trash", c.get("/api/trash"))
