from harness import *
with fresh() as (c, vault):
    pid = c.post("/api/projects", json={"title": "일지 과제"}).json()["id"]
    E = f"/api/projects/{pid}/entries"
    pdir = vault / "projects" / project_dirs(vault)[0]
    def show(tag, eid):
        g = c.get(f"/api/entries/{eid}").json()
        f = pdir / g["rel_path"]
        head = f.read_text(encoding="utf-8")[:160].replace("\n", " | ") if f.exists() else "MISSING"
        print(f"{tag}: title={g['title']!r} date={g['date']} rel={g['rel_path']} exists={f.exists()} :: {head}")
        return g
    # scenario A: PATCH date only
    e = c.post(E, json={"title": "순환", "date": "2026-04-01", "body": "원본"}).json(); eid = e["id"]
    show("A0 created", eid)
    c.patch(f"/api/entries/{eid}", json={"date": "2026-04-02"}); gA = show("A1 after PATCH date", eid)
    c.patch(f"/api/entries/{eid}", json={"date": "2026-04-03"}); gA = show("A2 after PATCH date again", eid)
    rec("entry-title", "PATCH date only (x2)", 200, "ok" if gA["title"] == "순환" else "PROBLEM", f"title became {gA['title']!r} rel={gA['rel_path']}", "🔴")
    # scenario B: PATCH title=''
    e = c.post(E, json={"title": "제목", "date": "2026-05-01", "body": "원본"}).json(); eid = e["id"]
    c.patch(f"/api/entries/{eid}", json={"title": ""}); gB = show("B1 after PATCH title=''", eid)
    c.patch(f"/api/entries/{eid}", json={"body": "x"}); gB = show("B2 after PATCH body", eid)
    c.patch(f"/api/entries/{eid}", json={}); gB = show("B3 after PATCH {}", eid)
    rec("entry-title", "PATCH title='' then body", 200, "ok" if gB["title"] in ("제목", "진행 기록") else "PROBLEM", f"title became {gB['title']!r} rel={gB['rel_path']}", "🔴")
    # scenario C: PATCH {} repeatedly
    e = c.post(E, json={"title": "빈패치", "date": "2026-06-01", "body": "원본"}).json(); eid = e["id"]
    for i in range(3): c.patch(f"/api/entries/{eid}", json={})
    gC = show("C after 3x PATCH {}", eid)
    rec("entry-title", "PATCH {} x3", 200, "ok" if gC["title"] == "빈패치" else "PROBLEM", f"title became {gC['title']!r}", "🔴")
    # scenario D: body=null
    e = c.post(E, json={"title": "널", "date": "2026-07-01", "body": "원본"}).json(); eid = e["id"]
    c.patch(f"/api/entries/{eid}", json={"body": None}); gD = show("D after PATCH body=null", eid)
    rec("entry-title", "PATCH body=null", 200, "ok" if gD["title"] == "널" and gD["body"] == "원본" else "PROBLEM", f"title={gD['title']!r} body={gD['body']!r}", "🔴")
    # scenario E: PATCH date invalid after valid
    e = c.post(E, json={"title": "날짜오류", "date": "2026-08-01", "body": "원본"}).json(); eid = e["id"]
    r = c.patch(f"/api/entries/{eid}", json={"date": "2026-99-99"}); gE = show(f"E after PATCH bad date ({r.status_code})", eid)
    rec("entry-title", "PATCH bad date", r, "ok" if gE["title"] == "날짜오류" and gE["date"] == "2026-08-01" else "PROBLEM", f"title={gE['title']!r} date={gE['date']}", "🔴")
    # delete → restore → check
    e = c.post(E, json={"title": "복구", "date": "2026-09-01", "body": "원본"}).json(); eid = e["id"]
    c.delete(f"/api/entries/{eid}")
    tn = c.get("/api/trash").json()[0]["trash_name"]
    r = c.post(f"/api/trash/{tn}/restore"); print("restore:", r.status_code, r.text[:200])
    ents = [x for x in c.get(E).json() if x["title"] == "복구"]
    rec("entry-restore", "restore deleted entry", r, "ok" if ents else "PROBLEM", f"found={ents}", "🔴")
    if ents:
        nid = ents[0]["id"]; r = c.patch(f"/api/entries/{nid}", json={"body": "복구 후"}); show(f"after restore+patch ({r.status_code})", nid)
        print("old id same?", nid == eid, "old id patch:", c.patch(f"/api/entries/{eid}", json={"body": "old"}).status_code)
    # files vs entries
    files = sorted(p.name for p in (pdir / "logs").glob("*.md")); ents = c.get(E).json()
    rec("entry-consistency", "entries vs files", 200, "ok" if len(files) == len(ents) else "PROBLEM", f"api={len(ents)} files={len(files)} {files}", "🔴")
    for g in ents:
        full = c.get(f"/api/entries/{g['id']}").json(); f = pdir / full["rel_path"]
        ok = f.exists() and (full["body"] or "").strip() in f.read_text(encoding="utf-8")
        if not ok: rec("entry-file", f"{full['rel_path']}", 200, "PROBLEM", f"exists={f.exists()} body={full['body']!r:.30}", "🔴")
finish("p3b")
