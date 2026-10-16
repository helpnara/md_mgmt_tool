from harness import *
import re
def edit(path, **repl):
    t = path.read_text()
    for k, val in repl.items():
        t = re.sub(rf"^{k}:.*$", f"{k}: {val}", t, count=1, flags=re.M)
    path.write_text(t)

with fresh() as (c, v):
    print("== year views: done with completed_at in future ==")
    p = proj(c, title="D", status="done", start_date="2026-01-01", completed_at="2031-12-31", effect_expected=10, effect_verified=7).json()["id"]
    t = c.get("/api/home", params={"year":"2026"}).json()["team"]
    print("2026 team:", {k: t[k] for k in ("total","done","in_progress","effect_expected","effect_verified","done_in_year")})
    t = c.get("/api/home", params={"year":"2031"}).json()["team"]
    print("2031 team:", {k: t[k] for k in ("total","done","in_progress","effect_expected","effect_verified","done_in_year")})
    lst = c.get("/api/projects", params={"year":"2026"}).json()
    print("list 2026:", [(x["id"], x["status"], x.get("y_status")) for x in lst])

with fresh() as (c, v):
    print("== hand-edited project fields ==")
    ids = [proj(c, title=f"H{i}").json()["id"] for i in range(10)]
    edit(find_index(v, ids[0]), status="완료")
    edit(find_index(v, ids[1]), status="Done")
    edit(find_index(v, ids[2]), type="없는속성")
    edit(find_index(v, ids[3]), effect_expected=".inf", effect_verified="-5")
    edit(find_index(v, ids[4]), owners="'김철수, 박민수'", tags="'AI, ai,  AI'")
    edit(find_index(v, ids[5]), start_date="2026/03/01", due_date="2026-02-30", completed_at="어제")
    edit(find_index(v, ids[6]), status="done", completed_at="null")
    edit(find_index(v, ids[7]), no_effect="'예'", nature="없는분류값", effect_expected="'1억'")
    edit(find_index(v, ids[8]), effect_expected="1e300", effect_verified="1e300")
    edit(find_index(v, ids[9]), start_date="2026-12-01", due_date="2026-01-01")
    r = show("reindex", c.post("/api/reindex"))
    for pr in r.get("problems", []): print("   problem:", pr)
    for pid in ids:
        x = c.get(f"/api/projects/{pid}").json()
        print("  ", pid, {k: x.get(k) for k in ("status","type","effect_expected","effect_verified","owners","tags","start_date","due_date","completed_at","no_effect","nature")})
    show("home", c.get("/api/home"))
    show("home 2026", c.get("/api/home", params={"year":"2026"}))
    show("projects list", c.get("/api/projects"))
    # save via API on the inf project
    show("patch inf project title", c.patch(f"/api/projects/{ids[3]}", json={"title":"H3x"}))
    show("patch bad-date project", c.patch(f"/api/projects/{ids[5]}", json={"title":"H5x"}))
    show("patch reversed period project unrelated field", c.patch(f"/api/projects/{ids[9]}", json={"title":"H9x"}))
    show("patch reversed period project due", c.patch(f"/api/projects/{ids[9]}", json={"due_date":"2026-12-31"}))
