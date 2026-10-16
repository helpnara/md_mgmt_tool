from harness import *
with fresh() as (c, v):
    print("== roster ==")
    show("dup employee ids + future left_on + account", c.put("/api/people", json={"people":[
        {"name":"김철수","employee_id":"100","account":"a b\nc","left_on":"2030-01-01","left_reason":"퇴사"},
        {"name":"박민수","employee_id":"100"},
        {"name":"김 철수"},{"name":"Kim"},{"name":"kim"},
        {"name":"이, 영희"},{"name":"../x"},{"name":"a\nb"},
        {"name":"떠난이","left_on":"2026-01-01","left_reason":"이상한사유"}]}))
    print("roster:", [(p["name"], p["employee_id"], p["left_on"], p["left_reason"], p["account"]) for p in c.get("/api/people").json()["people"]])
    show("add person comma", c.post("/api/people", json={"name":"최, 수지"}))
    show("add person slash", c.post("/api/people", json={"name":"a/b"}))
    print("== departed newly assigned ==")
    pid = proj(c, title="P", owners=["떠난이"], partners=[{"team":"T","people":"떠난이, 없는사람"}]).json()["id"]
    show("project with departed owner", c.get(f"/api/projects/{pid}"))
    show("activity departed", c.post("/api/activities", json={"person":"떠난이","title":"교육","date":"2026-05-01"}))
    show("meeting departed", c.post("/api/meetings", json={"person":"떠난이","summary":"s","date":"2026-05-01"}))
    print("== rename ==")
    c.post("/api/activities", json={"person":"김철수","title":"교육A","date":"2026-05-01"})
    c.post("/api/meetings", json={"person":"김철수","summary":"m","date":"2026-05-01"})
    pid2 = proj(c, title="P2", owners=["김철수"], partners=[{"team":"T","people":["김철수"]}]).json()["id"]
    iid = c.post("/api/intakes", json={"title":"I","leader":"김철수"}).json()["id"]
    show("rename 김철수 -> 김철순", c.post("/api/people/rename", json={"old":"김철수","new":"김철순"}))
    print("  project owners:", c.get(f"/api/projects/{pid2}").json()["owners"], "partners:", c.get(f"/api/projects/{pid2}").json()["partners"])
    print("  activities persons:", sorted({a["person"] for a in c.get("/api/activities").json()}))
    print("  meetings persons:", sorted({m["person"] for m in c.get("/api/meetings").json()["items"]}))
    print("  intake leader:", c.get(f"/api/intakes/{iid}").json().get("leader"))
    print("  roster:", [p["name"] for p in c.get("/api/people").json()["people"]], "unregistered:", c.get("/api/people").json()["unregistered"])
    show("rename new with comma", c.post("/api/people/rename", json={"old":"김철순","new":"가, 나"}))
    print("  project owners after comma rename:", c.get(f"/api/projects/{pid2}").json()["owners"])
    show("reindex", c.post("/api/reindex"))
    print("  project owners after reindex:", c.get(f"/api/projects/{pid2}").json()["owners"])
    show("handover to nobody-string", c.post("/api/people/handover", json={"old":"가, 나","new":"../evil"}))
    print("  owners:", c.get(f"/api/projects/{pid2}").json()["owners"])
with fresh() as (c, v):
    print("== activities ==")
    show("hours negative", c.post("/api/activities", json={"person":"A","title":"t","hours":-1}))
    show("hours 1e300 cost 1e300 x2", c.post("/api/activities", json={"person":"A, B","title":"t","hours":1e300,"cost":1e300}))
    show("summary", c.get("/api/activities/summary"))
    show("future date", c.post("/api/activities", json={"person":"A","title":"future","date":"2030-01-01"}))
    show("hours 10000 for 1-day", c.post("/api/activities", json={"person":"A","title":"h","hours":10000}))
    show("Kim vs kim", c.post("/api/activities", json={"person":"Kim","title":"t"}))
    show("Kim vs kim 2", c.post("/api/activities", json={"person":"kim","title":"t2"}))
    print("people dirs:", sorted(p.name for p in (v/"people").iterdir()))
    show("author newline", c.post("/api/activities", json={"person":"A","title":"au","author":"x\ny"}))
    # hand edit activity date/kind
    f = sorted((v/"people").rglob("activities/*.md"))[0]
    t = f.read_text(); import re
    t = re.sub(r"^date:.*$", "date: 어제", t, flags=re.M); t = re.sub(r"^kind:.*$", "kind: 워크숍", t, flags=re.M); t = re.sub(r"^hours:.*$", "hours: -3", t, flags=re.M)
    f.write_text(t)
    show("reindex", c.post("/api/reindex"))
    print([ (a["date"], a["kind"], a["hours"]) for a in c.get("/api/activities").json()][:3])
with fresh() as (c, v):
    print("== meetings ==")
    show("kind not in settings", c.post("/api/meetings", json={"person":"A","summary":"s","kind":"없는구분"}))
    show("future meeting date", c.post("/api/meetings", json={"person":"A","summary":"s","date":"2030-01-01"}))
    show("followup done before meeting", c.post("/api/meetings", json={"person":"A","summary":"s","date":"2026-05-01","followups":[{"text":"x","done":"2020-01-01"}]}))
    show("summary 5000", c.post("/api/meetings", json={"person":"A","summary":"s"*5000}))
