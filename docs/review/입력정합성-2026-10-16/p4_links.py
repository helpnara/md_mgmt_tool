from harness import *
with fresh() as (c, v):
    print("== predecessors ==")
    a = proj(c, title="A", start_date="2027-01-01").json()["id"]
    b = proj(c, title="B", start_date="2026-01-01", predecessors=[a]).json()
    show("B (2026) with predecessor A (2027)", c.get(f"/api/projects/{b['id']}"))
    x = proj(c, title="X").json()["id"]; y = proj(c, title="Y", predecessors=[x]).json()["id"]; z = proj(c, title="Z", predecessors=[y]).json()["id"]
    show("cycle via API X<-Z", c.patch(f"/api/projects/{x}", json={"predecessors":[z]}))
    # hand-edit cycle
    p = find_index(v, x); p.write_text(p.read_text().replace("predecessors: []", f"predecessors:\n- {z}"))
    show("reindex cycle", c.post("/api/reindex"))
    r = c.get(f"/api/projects/{x}").json(); print("lineage stage", r.get("lineage", {}).get("stage") if isinstance(r.get("lineage"), dict) else list(r)[:5])
    show("roadmap", c.get("/api/roadmap"))
    # hand-edit missing pred
    p = find_index(v, y); p.write_text(p.read_text().replace(f"predecessors:\n- {x}", "predecessors:\n- 2020-999"))
    show("reindex missing pred", c.post("/api/reindex"))
    # archived predecessor
    q = proj(c, title="Q").json()["id"]; s = proj(c, title="S", predecessors=[q]).json()["id"]
    show("archive Q", c.post(f"/api/projects/{q}/archive"))
    show("S after Q archived", c.get(f"/api/projects/{s}"))
    show("patch S title (pred missing)", c.patch(f"/api/projects/{s}", json={"title":"S2"}))
    show("patch S predecessors unchanged", c.patch(f"/api/projects/{s}", json={"predecessors":[q]}))
    show("new project with archived pred", proj(c, title="T", predecessors=[q]))
with fresh() as (c, v):
    print("== intakes ==")
    i1 = c.post("/api/intakes", json={"title":"I1","received_on":"2026-05-01","start_date":"2026-01-01","due_date":"2026-02-01"}).json()["id"]
    show("I1 (start before received)", c.get(f"/api/intakes/{i1}"))
    show("received_on future", c.post("/api/intakes", json={"title":"I2","received_on":"2030-01-01"}))
    show("leader free text", c.post("/api/intakes", json={"title":"I3","leader":"홍길동, 김철수","leader_team":"x"*500}))
    show("title 300", c.post("/api/intakes", json={"title":"가"*300}))
    show("merged no note", c.post(f"/api/intakes/{i1}/status", json={"status":"merged","merged_into":"2026-999"}))
    pid = proj(c, title="Target", status="dropped").json()["id"]
    show("merged into dropped project", c.post(f"/api/intakes/{i1}/status", json={"status":"merged","merged_into":pid}))
    show("reopen", c.post(f"/api/intakes/{i1}/status", json={"status":"reviewing"}))
    show("promote due<received, owner unknown, departed", c.post(f"/api/intakes/{i1}/promote", json={"owners":["없는사람"],"start_date":"2026-01-01","due_date":"2026-02-01","status":"done"}))
    i4 = c.post("/api/intakes", json={"title":"I4"}).json()["id"]
    # hand-edit status/merged_into
    d = [p for p in (v/"intakes").iterdir() if p.name.startswith(i4)][0] / "request.md"
    d.write_text(d.read_text().replace("status: received", "status: 반려").replace("merged_into: null", "merged_into: 2026-777"))
    i5 = c.post("/api/intakes", json={"title":"I5"}).json()["id"]
    d5 = [p for p in (v/"intakes").iterdir() if p.name.startswith(i5)][0] / "request.md"
    d5.write_text(d5.read_text().replace("status: received", "status: merged").replace("merged_into: null", "merged_into: 2026-777"))
    i6 = c.post("/api/intakes", json={"title":"I6"}).json()["id"]
    d6 = [p for p in (v/"intakes").iterdir() if p.name.startswith(i6)][0] / "request.md"
    d6.write_text(d6.read_text().replace("status: received", "status: started").replace("project_id: null", "project_id: 2026-888"))
    r = show("reindex", c.post("/api/reindex"))
    for i in (i4, i5, i6):
        x = c.get(f"/api/intakes/{i}").json(); x = x.get("intake", x)
        print("  ", i, x.get("status"), x.get("merged_into"), x.get("project_id"))
    print("== precheck ==")
    i7 = c.post("/api/intakes", json={"title":"I7"}).json()["id"]
    defs = c.get(f"/api/intakes/{i7}").json()
    items = (defs.get("precheck") or {}).get("definition") or c.get("/api/meta").json().get("precheck", {}).get("items")
    print("def items:", len(items) if items else None, (items or [None])[0])
    if items:
        first = items[0]
        ans = [{"group": first["group"], "item": first["item"], "choice": first["choices"][0][0]}] * len(items)
        show("precheck all-same-item duplicates", c.put(f"/api/intakes/{i7}/precheck", json={"items": ans}))
        x = c.get(f"/api/intakes/{i7}").json(); 
        print("score:", (x.get("intake") or x).get("precheck_score"), "band", (x.get("intake") or x).get("precheck_band"))
