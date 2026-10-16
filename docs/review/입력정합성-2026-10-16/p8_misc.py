from harness import *
with fresh() as (c, v):
    i = c.post("/api/intakes", json={"title":"I", "leader":"미래퇴사"}).json()["id"]
    items = c.get("/api/meta").json()["precheck"]["items"]
    ans = [{"group": it["group"], "item": it["item"], "choice": it["choices"][0][0]} for it in items]
    c.put(f"/api/intakes/{i}/precheck", json={"items": ans})
    x = c.get(f"/api/intakes/{i}").json(); print("before:", x.get("precheck_score"))
    lines = "\n".join(f"{it['group']} | {it['item']} | 좋음=5, 나쁨=0" for it in items[:3])
    show("change items", c.put("/api/settings", json={"precheck_items": lines}))
    x = c.get(f"/api/intakes/{i}").json(); print("after:", x.get("precheck_score"), x.get("precheck_band"), (x.get("precheck") or {}).get("stale"))
    c.post("/api/reindex")
    x = c.get(f"/api/intakes/{i}").json(); print("after reindex:", x.get("precheck_score"), (x.get("precheck") or {}).get("stale"), (x.get("precheck") or {}).get("rated"), (x.get("precheck") or {}).get("total_items"))
    c.put("/api/people", json={"people":[{"name":"미래퇴사","left_on":"2030-12-31","left_reason":"퇴사"}]})
    plan = c.get(f"/api/intakes/{i}/promote").json(); print("promotion plan leader_in_roster:", plan["leader_in_roster"], plan["owners"], plan["partners"])
    h = c.get("/api/home").json(); 
    print("home left alerts keys:", [k for k in h if "left" in k], h.get("this_week",{}).get("owner_gaps"))
