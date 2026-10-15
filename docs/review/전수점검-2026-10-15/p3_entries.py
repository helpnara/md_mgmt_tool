from harness import *

def judge(name, req, r, accept_2xx=False, extra=""):
    st = r.status_code
    if st >= 500:
        rec(name, req, r, "PROBLEM", "500 " + extra, "⛔")
    elif st >= 400:
        d = detail(r)
        if st == 422:
            rec(name, req, r, "note", "422 english: " + d[:90] + extra)
        elif not is_korean(d):
            rec(name, req, r, "PROBLEM", "non-Korean " + d[:80], "🟡")
        else:
            rec(name, req, r, "ok", d[:80] + extra)
    else:
        rec(name, req, r, "ok" if accept_2xx else "note", f"{st} " + extra)
    return r

with fresh() as (c, vault):
    P = "/api/projects"
    pid = c.post(P, json={"title": "일지 과제", "start_date": "2026-03-01", "due_date": "2026-06-30"}).json()["id"]
    E = f"{P}/{pid}/entries"
    pdir = vault / "projects" / [d for d in project_dirs(vault) if d.startswith(pid)][0]
    def logs(): return sorted(p.name for p in (pdir / "logs").iterdir())
    # empty
    judge("entry-create", "POST {} (all empty)", c.post(E, json={}), extra=f"logs={logs()}")
    judge("entry-create", "POST body=''", c.post(E, json={"body": ""}), extra=f"logs={logs()}")
    judge("entry-create", "POST title='' body='' date=''", c.post(E, json={"title": "", "body": "", "date": ""}), extra=f"logs={logs()}")
    r = c.post(E, json={"title": "1MB", "body": "가" * 350_000}); judge("entry-create", "POST body=1MB", r, accept_2xx=True)
    if r.status_code == 201:
        g = c.get(f"/api/entries/{r.json()['id']}").json(); rec("entry-create", "1MB round trip", r, "ok" if len(g["body"]) == 350_000 else "PROBLEM", f"len back={len(g['body'])}", "🔴")
    judge("entry-create", "POST date before project start", c.post(E, json={"title": "이전", "date": "2025-01-01"}), accept_2xx=True)
    judge("entry-create", "POST date after project due", c.post(E, json={"title": "이후", "date": "2027-01-01"}), accept_2xx=True)
    judge("entry-create", "POST date in future", c.post(E, json={"title": "미래", "date": "2030-12-31"}), accept_2xx=True)
    for bad in ["2026-13-01", "2026/03/01", "abc", "../../x", "2026-03-01T10:00", "20260301", "2026-3-1"]:
        judge("entry-create", f"POST date={bad!r}", c.post(E, json={"title": "날짜", "date": bad}))
    r = c.post(E, json={"title": "이미지", "date": "2026-03-05", "body": "![없음](assets/missing.png) ![바깥](../../etc/passwd) ![원격](http://x/y.png)"}); judge("entry-create", "POST body with missing image links", r, accept_2xx=True)
    a1 = c.post(E, json={"title": "같은날 1", "date": "2026-03-10"}); a2 = c.post(E, json={"title": "같은날 2", "date": "2026-03-10"}); a3 = c.post(E, json={"title": "같은날 1", "date": "2026-03-10"})
    rec("entry-create", "two/three entries same date (+same title)", a3, "ok" if {a1.status_code, a2.status_code, a3.status_code} == {201} else "PROBLEM", f"{a1.status_code},{a2.status_code},{a3.status_code} logs={[l for l in logs() if '2026-03-10' in l]}", "🔴")
    judge("entry-create", "POST title 500 chars", c.post(E, json={"title": "제" * 500, "date": "2026-03-11"}), accept_2xx=True)
    judge("entry-create", "POST title with / \\ : NUL", c.post(E, json={"title": "a/b\\c:d\x00e", "date": "2026-03-12"}), accept_2xx=True)
    judge("entry-create", "POST title='CON'", c.post(E, json={"title": "CON", "date": "2026-03-13"}), accept_2xx=True)
    judge("entry-create", "POST tags=['', 'a,b']", c.post(E, json={"title": "태그", "tags": ["", "a,b"]}), accept_2xx=True)
    judge("entry-create", "POST author=''", c.post(E, json={"title": "작성자", "author": ""}), accept_2xx=True)
    judge("entry-create", "POST tags='x' (string)", c.post(E, json={"title": "태그", "tags": "x"}))
    judge("entry-create", "POST to missing project", c.post(f"{P}/2099-999/entries", json={"title": "x"}))
    print("LOGS:", logs())
    # edit / delete / restore / edit cycle
    e = c.post(E, json={"title": "순환", "date": "2026-04-01", "body": "원본"}).json(); eid = e["id"]
    judge("entry-cycle", "PATCH body", c.patch(f"/api/entries/{eid}", json={"body": "수정1"}), accept_2xx=True)
    judge("entry-cycle", "PATCH date → other date (file move)", c.patch(f"/api/entries/{eid}", json={"date": "2026-04-02"}), accept_2xx=True)
    judge("entry-cycle", "PATCH date invalid", c.patch(f"/api/entries/{eid}", json={"date": "2026-99-99"}))
    judge("entry-cycle", "PATCH title=''", c.patch(f"/api/entries/{eid}", json={"title": ""}), accept_2xx=True)
    judge("entry-cycle", "PATCH {}", c.patch(f"/api/entries/{eid}", json={}), accept_2xx=True)
    judge("entry-cycle", "PATCH body=null (should be no-op)", c.patch(f"/api/entries/{eid}", json={"body": None}), accept_2xx=True)
    print("after patches:", c.get(f"/api/entries/{eid}").json())
    judge("entry-cycle", "DELETE", c.delete(f"/api/entries/{eid}"), accept_2xx=True)
    judge("entry-cycle", "DELETE twice", c.delete(f"/api/entries/{eid}"))
    judge("entry-cycle", "PATCH after delete", c.patch(f"/api/entries/{eid}", json={"body": "유령"}))
    judge("entry-cycle", "GET after delete", c.get(f"/api/entries/{eid}"))
    trash = c.get("/api/trash").json(); print("TRASH:", trash)
    tn = trash[0]["trash_name"] if trash else "none"
    r = c.post(f"/api/trash/{tn}/restore"); judge("entry-cycle", f"restore {tn}", r, accept_2xx=True)
    judge("entry-cycle", "restore twice", c.post(f"/api/trash/{tn}/restore"))
    ents = c.get(E).json(); restored = [x for x in ents if x["title"] in ("순환", "") and x["date"] == "2026-04-02"]
    print("restored:", restored)
    if restored:
        nid = restored[0]["id"]
        judge("entry-cycle", "PATCH after restore (new id)", c.patch(f"/api/entries/{nid}", json={"body": "복구 후 수정"}), accept_2xx=True)
        judge("entry-cycle", "PATCH old id after restore", c.patch(f"/api/entries/{eid}", json={"body": "옛 id"}), accept_2xx=(eid == nid))
        g = c.get(f"/api/entries/{nid}").json()
        f = pdir / "logs" / Path(g["rel_path"]).name if g.get("rel_path") else None
        print("file:", g.get("rel_path"), [x for x in logs()])
    # versions of entry
    v = c.get("/api/versions", params={"path": f"projects/{pdir.name}/logs"}); print("versions dir listing", v.status_code, v.text[:200])
    # consistency: entries count vs log files
    ents = c.get(E).json(); files = [l for l in logs() if l.endswith(".md")]
    rec("entry-consistency", "entries vs log files", 200, "ok" if len(ents) == len(files) else "PROBLEM", f"api={len(ents)} files={len(files)} files={files}", "🔴")
    ri = c.post("/api/reindex").json(); ents2 = c.get(E).json()
    rec("entry-consistency", "reindex entries", 200, "ok" if len(ents2) == len(files) else "PROBLEM", f"after reindex api={len(ents2)} files={len(files)} problems={ri['problems']}", "🔴")
    # the markdown content of one entry equals API body
    for x in ents2[:3]:
        g = c.get(f"/api/entries/{x['id']}").json()
        f = vault / g["rel_path"] if g.get("rel_path") else None
        if f and f.exists():
            txt = f.read_text(encoding="utf-8")
            rec("entry-file", f"file body contains api body ({f.name})", 200, "ok" if (g["body"] or "").strip() in txt else "PROBLEM", f"body={g['body']!r:.40}", "🔴")
        else:
            rec("entry-file", f"rel_path {g.get('rel_path')} exists", 200, "PROBLEM" if g.get("rel_path") else "note", "file missing", "🔴")
finish("p3_entries")
