from harness import *
import re
with fresh() as (c, v):
    a = proj(c, title="A").json()["id"]; b = proj(c, title="B").json()["id"]
    p = find_index(v, a); t = p.read_text(); t = t.replace("effect_expected: null", "effect_expected: .inf"); p.write_text(t)
    print(p.read_text().split("---")[1][:400])
    show("reindex", c.post("/api/reindex"))
    show("get", c.get(f"/api/projects/{a}"))
    show("home", c.get("/api/home"))
    show("list", c.get("/api/projects"))
    p = find_index(v, b); t = p.read_text().replace("effect_expected: null", "effect_expected: 1.0e+308").replace("effect_verified: null","effect_verified: 1.0e+308"); p.write_text(t)
    p = find_index(v, a); t = p.read_text().replace("effect_expected: .inf", "effect_expected: 1.0e+308"); p.write_text(t)
    show("reindex2", c.post("/api/reindex"))
    print("home2 team", {k:val for k,val in c.get("/api/home").json()["team"].items() if "effect" in k})
    show("dashboard2", c.get("/api/dashboard"))
    show("list2", c.get("/api/projects"))
