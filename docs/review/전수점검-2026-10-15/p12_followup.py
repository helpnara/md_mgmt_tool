from harness import *

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
    # intake orphan folders on rejected create
    def idirs(): return sorted(p.name for p in (vault / "intakes").iterdir()) if (vault / "intakes").exists() else []
    for body in [{"title": "x", "effect_request": -1}, {"title": "x", "received_on": "2026-13-01"}, {"title": "x", "start_date": "bad"}, {"title": "x", "due_date": "bad"}, {"title": "x", "priority": "최상"}, {"title": "x", "nature": "없음"}]:
        r = c.post("/api/intakes", json=body); print("intake", body, r.status_code, r.text[:80])
    api = c.get("/api/intakes", params={"scope": "all"}).json()["items"]; fs = idirs()
    rec("intake-orphan", "intake api count vs folders after rejected creates", 200, "ok" if len(api) == len(fs) else "PROBLEM", f"api={len(api)} fs={fs}", "🔴")
    ri = c.post("/api/reindex").json(); print("reindex problems:", ri["problems"])
    # settings author newline → entry front matter
    c.put("/api/settings", json={"author": "a\nb"})
    pid = c.post("/api/projects", json={"title": "작성자 과제"}).json()["id"]
    e = c.post(f"/api/projects/{pid}/entries", json={"title": "일지", "date": "2026-03-01"}).json()
    ri = c.post("/api/reindex").json(); g = c.get(f"/api/entries/{e['id']}").json()
    rec("author-newline", "author 'a\\nb' → entry file → reindex", 200, "ok" if not ri["problems"] and g["author"] == "a\nb" else "PROBLEM", f"author={g['author']!r} problems={ri['problems']}", "🟡")
    c.put("/api/settings", json={"author": "정상"})
    # project PATCH title '' → file title '' → reindex → title?
    pid2 = c.post("/api/projects", json={"title": "제목 지우기"}).json()["id"]
    r = c.patch(f"/api/projects/{pid2}", json={"title": ""}); g1 = c.get(f"/api/projects/{pid2}").json()
    ri = c.post("/api/reindex").json(); g2 = c.get(f"/api/projects/{pid2}").json()
    rec("project-title", "PATCH title='' then reindex", r, "PROBLEM" if r.status_code == 200 else "ok", f"after patch title={g1['title']!r} after reindex title={g2['title']!r} dir={g2['dir_name']} problems={ri['problems']}", "🔴")
    r = c.patch(f"/api/projects/{pid2}", json={"title": "   "}); g1 = c.get(f"/api/projects/{pid2}").json()
    rec("project-title", "PATCH title='   '", r, "PROBLEM" if r.status_code == 200 else "ok", f"title={g1['title']!r} dir={g1['dir_name']} fs={[d for d in project_dirs(vault) if d.startswith(pid2)]}", "🔴")
    # home / search / export with empty-title project
    for path in ["/api/home", "/api/search?q=제목", f"/api/projects/{pid2}/export?format=md", "/api/report-candidates"]:
        judge("project-title", f"GET {path} with blank-title project", c.get(path), accept_2xx=True)
    # entry title whitespace
    e2 = c.post(f"/api/projects/{pid}/entries", json={"title": "   ", "date": "2026-03-02"}); print("entry title '   ':", e2.status_code, e2.json().get("title"), e2.json().get("rel_path"))
    r = c.patch(f"/api/entries/{e['id']}", json={"title": "   "}); g = c.get(f"/api/entries/{e['id']}").json()
    rec("entry-title", "PATCH entry title='   '", r, "note", f"title={g['title']!r} rel={g['rel_path']}")
    # start_date with time → period filters / due logic
    pid3 = c.post("/api/projects", json={"title": "T날짜", "start_date": "2026-01-01T00:00:00", "due_date": "2026-01-02T00:00:00"}).json()["id"]
    g = c.get(f"/api/projects/{pid3}").json(); print("Tdate stored:", g["start_date"], g["due_date"])
    h = c.get("/api/home").json(); print("home overdue:", h.get("this_week"))
    judge("tdate", "projects?period=2026", c.get("/api/projects", params={"period": "2026"}), accept_2xx=True, extra=f"includes={pid3 in [p['id'] for p in c.get('/api/projects', params={'period': '2026'}).json()]}")
    judge("tdate", "projects?overdue=1", c.get("/api/projects", params={"overdue": "1"}), accept_2xx=True)
    judge("tdate", "year-fix plan", c.get(f"/api/projects/{pid3}/year-fix"), accept_2xx=True)
    judge("tdate", "roadmap", c.get("/api/roadmap"), accept_2xx=True)
    ri = c.post("/api/reindex").json(); rec("tdate", "reindex with T-date", 200, "ok" if not ri["problems"] else "PROBLEM", f"{ri['problems']}", "🟡")
    g = c.get(f"/api/projects/{pid3}").json(); print("Tdate after reindex:", g["start_date"], g["due_date"])
    # meeting person traversal
    r = c.post("/api/meetings", json={"person": "../x", "date": "2026-10-01", "summary": "s"}); print("meeting ../x:", r.status_code, r.text[:100])
    items = c.get("/api/meetings").json()["items"]; print("meeting persons:", [i["person"] for i in items], tree(vault / "people"))
    rec("meeting-person", "person '../x'", r, "note", f"stored person={[i['person'] for i in items]} dirs={[d for d in tree(vault / 'people') if d.endswith('/') and d.count('/') == 1]}")
    # people left_on invalid silently cleared
    r = c.put("/api/people", json={"people": [{"name": "홍길동", "left_on": "2026-13-01", "left_reason": "퇴사"}]})
    rec("people", "left_on invalid silently cleared", r, "PROBLEM" if r.status_code == 200 and r.json()["people"][0]["left_on"] == "" else "ok", f"{r.json()}", "🟡")
    # tags comma vs owners comma
    g = c.post("/api/projects", json={"title": "쉼표", "tags": ["a, b"], "owners": ["c, d"]}).json(); g = c.get(f"/api/projects/{g['id']}").json()
    rec("comma", "tags 'a, b' vs owners 'c, d'", 200, "note", f"tags={g['tags']} owners={g['owners']}")
    # report draft date before earliest entry: covers?
    # project_code CON → folder name
    c.put("/api/settings", json={"project_code": "CON"}); g = c.post("/api/projects", json={"title": "콘"}).json(); print("CON code id:", g["id"], [d for d in project_dirs(vault) if "CON" in d]); c.put("/api/settings", json={"project_code": ""})
    # share mode: openapi exposure check already; check /docs is reachable w/o share
    # drafts: huge key beyond route? 5000-char key
    r = c.put("/api/drafts/overview:" + "x" * 5000, json={"content": "x"}); judge("drafts", "5000-char key", r)
    # precheck thresholds variants
    for th in [[-1], [1], [1, 2, 3], [], [0, 0], ["a", "b"], [1.5, 2.5], [100, 200]]:
        judge("precheck", f"thresholds={th}", c.put("/api/settings", json={"precheck_thresholds": th}), accept_2xx=True)
    # intake promote with bad payload
    iid = c.post("/api/intakes", json={"title": "승격"}).json()["id"]
    judge("promote", "promote type bogus", c.post(f"/api/intakes/{iid}/promote", json={"type": "bogus"}), extra=f"intake status={c.get(f'/api/intakes/{iid}').json()['status']} fs={len(project_dirs(vault))} api={len(c.get('/api/projects').json())}")
    judge("promote", "promote start_date bad", c.post(f"/api/intakes/{iid}/promote", json={"start_date": "bad"}), extra=f"status={c.get(f'/api/intakes/{iid}').json()['status']}")
    judge("promote", "promote status bogus", c.post(f"/api/intakes/{iid}/promote", json={"status": "bogus"}), extra=f"status={c.get(f'/api/intakes/{iid}').json()['status']}")
    judge("promote", "promote title ''", c.post(f"/api/intakes/{iid}/promote", json={"title": ""}), accept_2xx=True, extra=f"status={c.get(f'/api/intakes/{iid}').json()['status']}")
    n_api = len(c.get("/api/projects").json()); n_fs = len(project_dirs(vault))
    rec("promote", "projects api vs fs after failed promotes", 200, "ok" if n_api == n_fs else "PROBLEM", f"api={n_api} fs={n_fs} orphans={[d for d in project_dirs(vault) if d[:8] not in {p['id'][:8] for p in c.get('/api/projects').json()}]}", "🔴")
    # year-fix on project with start_date in another year
    pid4 = c.post("/api/projects", json={"title": "연도", "start_date": "2026-05-01"}).json()["id"]
    c.patch(f"/api/projects/{pid4}", json={"start_date": "2025-05-01"})
    plan = c.get(f"/api/projects/{pid4}/year-fix").json(); print("year-fix plan:", plan)
    r = c.post(f"/api/projects/{pid4}/year-fix"); judge("year-fix", "apply year-fix", r, accept_2xx=True); print(r.json())
    nid = r.json().get("new_id") or pid4
    rec("year-fix", "fs after year-fix", 200, "ok" if any(d.startswith(nid) for d in project_dirs(vault)) and not any(d.startswith(pid4) for d in project_dirs(vault)) or nid == pid4 else "PROBLEM", f"new={nid} fs={[d for d in project_dirs(vault) if '연도' in d]}", "🔴")
    judge("year-fix", "GET old id after year-fix", c.get(f"/api/projects/{pid4}"))
    judge("year-fix", "year-fix twice", c.post(f"/api/projects/{nid}/year-fix"), accept_2xx=True)
    # clone → create with returned payload
    cl = c.get(f"/api/projects/{nid}/clone").json(); r = c.post("/api/projects", json=cl); judge("clone", "POST clone payload back", r, accept_2xx=True)
    # final consistency
    api = c.get("/api/projects").json(); fs = project_dirs(vault)
    rec("final", "api vs fs", 200, "ok" if len(api) == len(fs) else "PROBLEM", f"api={len(api)} fs={len(fs)} orphans={[d for d in fs if d[:8] not in {p['id'][:8] for p in api}]}", "🔴")
finish("p12")
