from harness import *
import time

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
    pid = c.post("/api/projects", json={"title": "버전 과제", "body": "## 배경\n\n원본 개요"}).json()["id"]
    dn = c.get(f"/api/projects/{pid}").json()["dir_name"]
    eid = c.post(f"/api/projects/{pid}/entries", json={"title": "일지", "date": "2026-03-01", "body": "v1"}).json()["id"]
    c.patch(f"/api/entries/{eid}", json={"body": "v2"}); time.sleep(1.1); c.patch(f"/api/entries/{eid}", json={"body": "v3"})
    path = f"projects/{dn}/logs/2026-03-01-일지.md"
    vs = c.get("/api/versions", params={"path": path}).json()["items"]; print("versions:", vs)
    V = "/api/versions"
    judge("versions", "restore non-existent stamp", c.post(f"{V}/restore", json={"path": path, "stamp": "19990101000000"}))
    judge("versions", "restore non-existent path", c.post(f"{V}/restore", json={"path": "projects/nope/index.md", "stamp": "19990101000000"}))
    judge("versions", "restore path traversal", c.post(f"{V}/restore", json={"path": "../../etc/passwd", "stamp": "x"}))
    judge("versions", "restore stamp traversal", c.post(f"{V}/restore", json={"path": path, "stamp": "../../x"}))
    judge("versions", "content stamp traversal", c.get(f"{V}/content", params={"path": path, "stamp": "../../../settings.json"}))
    judge("versions", "content path NUL", c.get(f"{V}/content", params={"path": "a\x00b", "stamp": "x"}))
    judge("versions", "list path NUL", c.get(V, params={"path": "a\x00b"}))
    judge("versions", "list path absolute", c.get(V, params={"path": "/etc/passwd"}), accept_2xx=True)
    judge("versions", "list path 5000 chars", c.get(V, params={"path": "a" * 5000}), accept_2xx=True)
    if vs:
        r = c.post(f"{V}/restore", json={"path": path, "stamp": vs[-1]["stamp"]}); judge("versions", "restore oldest", r, accept_2xx=True)
        print("entry after restore:", c.get(f"/api/entries/{eid}").json()["body"])
    # restore body-only after rename: project overview
    c.patch(f"/api/projects/{pid}", json={"body": "## 배경\n\n고친 개요"}); time.sleep(1.1)
    c.patch(f"/api/projects/{pid}", json={"title": "이름 바뀐 과제", "status": "done"})
    dn2 = c.get(f"/api/projects/{pid}").json()["dir_name"]; print("dir after rename:", dn, "->", dn2)
    ipath_old = f"projects/{dn}/index.md"; ipath_new = f"projects/{dn2}/index.md"
    vo = c.get(V, params={"path": ipath_old}).json()["items"]; vn = c.get(V, params={"path": ipath_new}).json()["items"]
    rec("versions", "versions follow rename", 200, "ok" if vn else "PROBLEM", f"old_path={len(vo)} new_path={len(vn)}", "🔴")
    if vn:
        r = c.post(f"{V}/restore", json={"path": ipath_new, "stamp": vn[-1]["stamp"]}); judge("versions", "restore overview oldest (body-only?)", r, accept_2xx=True)
        g = c.get(f"/api/projects/{pid}").json(); print("after restore:", g["title"], g["status"], repr(g["body"][:40]))
        rec("versions", "restore keeps title/status (body-only semantics)", r, "ok" if g["title"] == "이름 바뀐 과제" and g["status"] == "done" and "원본" in (g["body"] or "") else "PROBLEM", f"title={g['title']} status={g['status']} body={g['body'][:30]!r}", "🔴")
        rec("versions", "folder still matches", 200, "ok" if g["dir_name"] in project_dirs(vault) else "PROBLEM", f"{g['dir_name']} fs={project_dirs(vault)}", "🔴")
    if vo:
        judge("versions", "restore via OLD path after rename", c.post(f"{V}/restore", json={"path": ipath_old, "stamp": vo[-1]["stamp"]}), extra=f"fs={project_dirs(vault)}")
    judge("versions", "overview", c.get(f"{V}/overview"), accept_2xx=True)
    # search
    for q in ["", "a", "ㄱ", "ㅏ", "가", '"', "*", "(", ")", ":", "-", "'OR 1=1", "a OR b", "NEAR(a b)", "a*", '"unterminated', "x" * 500, "일지 AND", "일지 NOT", "col:x", "^일", "일지 -v3", "\x00", "%", "_", "일지\n개요"]:
        judge("search", f"q={q!r:.40}", c.get("/api/search", params={"q": q}), accept_2xx=True)
    judge("search", "q with 20 words", c.get("/api/search", params={"q": " ".join(["단어"] * 20)}), accept_2xx=True)
    judge("search", "intakes q special", c.get("/api/intakes", params={"q": '" * ( ) : -'}), accept_2xx=True)
    judge("search", "projects q special", c.get("/api/projects", params={"q": '" * ( ) : -'}), accept_2xx=True)
    judge("search", "activities q special", c.get("/api/activities", params={"q": '"*():-'}), accept_2xx=True)
    judge("search", "reports q special", c.get("/api/reports", params={"q": '"*():-'}), accept_2xx=True)
    # meetings
    M = "/api/meetings"
    judge("meetings", "person not in roster", c.post(M, json={"person": "낯선이", "date": "2026-10-01", "summary": "x"}), accept_2xx=True)
    judge("meetings", "date ''", c.post(M, json={"person": "홍", "date": "", "summary": "x"}), accept_2xx=True)
    judge("meetings", "date missing", c.post(M, json={"person": "홍", "summary": "x"}), accept_2xx=True)
    judge("meetings", "person ''", c.post(M, json={"person": "", "date": "2026-10-01", "summary": "x"}))
    judge("meetings", "person '../x'", c.post(M, json={"person": "../x", "date": "2026-10-01", "summary": "x"}), accept_2xx=True)
    judge("meetings", "person 300 chars", c.post(M, json={"person": "홍" * 300, "date": "2026-10-01", "summary": "x"}), accept_2xx=True)
    judge("meetings", "next_date before date", c.post(M, json={"person": "홍", "date": "2026-10-01", "next_date": "2020-01-01", "summary": "x"}), accept_2xx=True)
    judge("meetings", "followups odd shapes", c.post(M, json={"person": "홍", "date": "2026-10-01", "summary": "x", "followups": [1, None, {"text": ""}, {"done": "x"}, "str", {"text": "a", "done": "2026-99-99"}]}), accept_2xx=True)
    judge("meetings", "kind not in settings", c.post(M, json={"person": "홍", "date": "2026-10-01", "summary": "x", "kind": "없음"}), accept_2xx=True)
    r = c.post(M, json={"person": "홍", "date": "2026-10-02", "summary": "y", "followups": [{"text": "할일", "done": None}]}); mid = r.json().get("id")
    judge("meetings", "toggle followup on missing meeting", c.patch(f"{M}/999999", json={"followups": [{"text": "할일", "done": "2026-10-03"}]}))
    judge("meetings", "PATCH followups=[] (clear)", c.patch(f"{M}/{mid}", json={"followups": []}), accept_2xx=True)
    judge("meetings", "PATCH person=''", c.patch(f"{M}/{mid}", json={"person": ""}))
    judge("meetings", "PATCH summary=''", c.patch(f"{M}/{mid}", json={"summary": ""}))
    judge("meetings", "PATCH date=''", c.patch(f"{M}/{mid}", json={"date": ""}), accept_2xx=True)
    judge("meetings", "list person=../x", c.get(M, params={"person": "../x"}), accept_2xx=True)
    print("meetings:", c.get(M).json()); print("people dir:", tree(vault / "people"))
    judge("meetings", "delete twice", c.delete(f"{M}/{mid}"), accept_2xx=True); judge("meetings", "delete twice", c.delete(f"{M}/{mid}"))
    # activities
    AC = "/api/activities"
    judge("activities", "person 'a, b' creates 2", c.post(AC, json={"person": "a, b", "title": "교육", "date": "2026-01-01"}), accept_2xx=True)
    judge("activities", "end_date before date", c.post(AC, json={"person": "a", "title": "교육", "date": "2026-02-01", "end_date": "2026-01-01"}), accept_2xx=True)
    judge("activities", "hours='많이'", c.post(AC, json={"person": "a", "title": "교육", "hours": "많이"}))
    judge("activities", "hours=-1", c.post(AC, json={"person": "a", "title": "교육", "hours": -1}), accept_2xx=True)
    judge("activities", "cost=1e308", c.post(AC, json={"person": "a", "title": "교육", "cost": 1e308}), accept_2xx=True)
    judge("activities", "kind bogus", c.post(AC, json={"person": "a", "title": "교육", "kind": "bogus"}))
    judge("activities", "title ''", c.post(AC, json={"person": "a", "title": ""}))
    judge("activities", "person '' ", c.post(AC, json={"person": "", "title": "x"}))
    judge("activities", "link javascript:", c.post(AC, json={"person": "a", "title": "x", "link": "javascript:alert(1)"}), accept_2xx=True)
    judge("activities", "summary year=0000", c.get(f"{AC}/summary", params={"year": "0000"}), accept_2xx=True)
    # drafts
    D = "/api/drafts"
    for key in ["overview:" + "x" * 80, "overview:" + "x" * 81, "overview:../x", "entry:new-../x", "entry:0", "entry:" + "9" * 18, "entry:" + "9" * 19, "report:abc", "intake:R2026-001", "bogus:x", "overview:", "overview:%2e%2e", "overview:a%00b"]:
        r = c.put(f"{D}/{key}", json={"content": "글"})
        if r.status_code == 200:
            g = c.get(f"{D}/{key}"); d = c.delete(f"{D}/{key}")
            rec("drafts", f"PUT/GET/DELETE key={key[:40]!r}", r, "ok" if g.status_code == 200 and g.json()["content"] == "글" and d.status_code == 204 else "PROBLEM", f"get={g.status_code} del={d.status_code} files={[p.name for p in (vault/'.drafts').glob('*')]}", "🔴")
        else: judge("drafts", f"PUT key={key[:40]!r}", r)
    judge("drafts", "PUT content 2MB", c.put(f"{D}/overview:big", json={"content": "가" * 700_000}))
    judge("drafts", "PUT content 1.9MB", c.put(f"{D}/overview:big", json={"content": "x" * 1_900_000}), accept_2xx=True)
    judge("drafts", "PUT content=null", c.put(f"{D}/overview:n", json={"content": None}), accept_2xx=True)
    judge("drafts", "PUT content={} ", c.put(f"{D}/overview:o", json={"content": {}}), accept_2xx=True)
    judge("drafts", "PUT no content key", c.put(f"{D}/overview:o", json={}))
    judge("drafts", "GET missing", c.get(f"{D}/overview:missing"), accept_2xx=True)
    judge("drafts", "DELETE missing", c.delete(f"{D}/overview:missing"), accept_2xx=True)
    judge("drafts", "list", c.get(D), accept_2xx=True)
    print("drafts listing:", c.get(D).json())
    # entry draft shaped content listed?
    c.put(f"{D}/entry:new-{pid}", json={"content": {"date": "x", "title": 1, "body": None, "tags": "x"}})
    judge("drafts", "list with odd entry draft", c.get(D), accept_2xx=True); print(c.get(D).json())
    c.put(f"{D}/entry:{eid}", json={"content": "글"}); c.delete(f"/api/entries/{eid}")
    judge("drafts", "list after entry deleted", c.get(D), accept_2xx=True); print(c.get(D).json())
    judge("drafts", "home after entry deleted w/ draft", c.get("/api/home"), accept_2xx=True)
    # errors
    judge("errors", "client error huge", c.post("/api/errors/client", json={"screen": "s", "kind": "k", "message": "m" * 300}), accept_2xx=True)
    judge("errors", "GET errors", c.get("/api/errors", params={"limit": 200}), accept_2xx=True)
    # trash
    judge("trash", "restore '..'", c.post("/api/trash/../restore"))
    judge("trash", "restore 'manifest.jsonl'", c.post("/api/trash/manifest.jsonl/restore"))
    judge("trash", "restore '%2e%2e%2fsettings.json'", c.post("/api/trash/%2e%2e%2fsettings.json/restore"))
    judge("trash", "list", c.get("/api/trash"), accept_2xx=True)
    # folders
    judge("folders", "list path=/etc/shadow", c.get("/api/folders", params={"path": "/etc/shadow"}))
    judge("folders", "list path=\\\\server\\share", c.get("/api/folders", params={"path": "\\\\server\\share"}))
    judge("folders", "list path=NUL", c.get("/api/folders", params={"path": "a\x00b"}))
    judge("folders", "create name='..'", c.post("/api/folders", json={"parent": str(vault), "name": ".."}))
    judge("folders", "create name='a/b'", c.post("/api/folders", json={"parent": str(vault), "name": "a/b"}))
    judge("folders", "create name='CON'", c.post("/api/folders", json={"parent": str(vault), "name": "CON"}), accept_2xx=True)
    judge("folders", "create name='  '", c.post("/api/folders", json={"parent": str(vault), "name": "  "}))
    judge("folders", "create twice", c.post("/api/folders", json={"parent": str(vault), "name": "새폴더"}), accept_2xx=True); judge("folders", "create twice", c.post("/api/folders", json={"parent": str(vault), "name": "새폴더"}))
    print("vault top:", sorted(p.name for p in vault.iterdir()))
finish("p8_misc")
