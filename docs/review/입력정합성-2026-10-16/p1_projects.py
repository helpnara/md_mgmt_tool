from harness import *
with fresh() as (c, v):
    print("== status/completed_at ==")
    show("in_progress+completed_at", proj(c, title="A", status="in_progress", completed_at="2026-01-05"))
    show("done no completed_at", proj(c, title="B", status="done"))
    show("done completed<start", proj(c, title="C", status="done", start_date="2026-05-01", completed_at="2026-01-01"))
    show("done completed future", proj(c, title="D", status="done", start_date="2026-01-01", completed_at="2031-12-31"))
    show("dropped with completed_at", proj(c, title="E", status="dropped", completed_at="2026-03-01"))
    # stale completed_at revival
    r = proj(c, title="F", status="in_progress", completed_at="2020-01-01"); pid=r.json()["id"]
    show("F -> done (no completed_at sent)", c.patch(f"/api/projects/{pid}", json={"status":"done"}))
    # done -> in_progress with explicit completed_at kept
    r = proj(c, title="G", status="done"); pid=r.json()["id"]
    show("G done->in_progress keeping completed_at", c.patch(f"/api/projects/{pid}", json={"status":"in_progress","completed_at":"2026-02-02"}))
    show("G clear completed_at while done? set done again then null", c.patch(f"/api/projects/{pid}", json={"status":"done","completed_at":None}))
    print("== effects ==")
    show("verified without expected, in_progress", proj(c, title="H", effect_verified=5))
    show("no_effect true with values", proj(c, title="I", no_effect=True, effect_expected=100, effect_verified=50, status="done"))
    show("home team", c.get("/api/home"))
    h = c.get("/api/home").json()
    print("home keys:", list(h)[:30])
    def walk(o, path=""):
        if isinstance(o, dict):
            for k, val in o.items():
                if "effect" in k and not isinstance(val,(dict,list)): print("  ", path+"."+k, val)
                walk(val, path+"."+k)
    walk(h.get("team", h))
    print("== dates ==")
    show("start 0025", proj(c, title="J", start_date="0025-01-01"))
    show("start 9999", proj(c, title="K", start_date="9999-01-01", due_date="9999-12-31"))
    show("years", c.get("/api/meta"))
    print("== titles ==")
    long = "가"*300
    r = show("title 300 chars", proj(c, title=long))
    show("title newline colon quotes", proj(c, title='a: "b"\n---\nc: d'))
    show("title control char", proj(c, title="x\x00y\x07z"))
    show("title emoji", proj(c, title="🚀 로켓"))
    show("title only emoji", proj(c, title="🚀"))
    show("title spaces", proj(c, title="  공백  "))
    for d in sorted((v/"projects").iterdir()): print("   dir:", d.name[:100])
    print("== body front-matter injection ==")
    r = proj(c, title="Body", body="---\nstatus: done\nowners: [hacker]\n---\nreal"); pid = r.json()["id"]
    show("reindex", c.post("/api/reindex"))
    show("get body proj", c.get(f"/api/projects/{pid}"))
    print(find_index(v,pid).read_text()[:400])
    r = proj(c, title="NUL", body="a\x00b"); show("body NUL", r)
    r = proj(c, title="Big", body="x"*5_000_000); show("body 5MB", r)
    print("== group/classification ==")
    show("group newline long", proj(c, title="Grp", group="g\n"*100))
    show("classification unknown+long", proj(c, title="Cls", nature="없는값"*20, category=" a  b "))
    print("== owners/tags ==")
    show("owners variants", proj(c, title="Own", owners=["김철수", " 김철수", "김 철수", "Kim", "kim", "x"*500]))
    show("tags variants", proj(c, title="Tag", tags=["AI", "ai", " AI ", "#AI", "a"*500, "x\ny"]))
    show("in_progress no owners", proj(c, title="NoOwn", status="in_progress"))
    show("created_by long/newline", proj(c, title="CB", created_by="a\nb"+"z"*100))
