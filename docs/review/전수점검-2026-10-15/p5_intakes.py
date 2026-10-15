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
    I = "/api/intakes"
    def idirs(): return sorted(p.name for p in (vault / "intakes").iterdir()) if (vault / "intakes").exists() else []
    judge("intake", "create title=''", c.post(I, json={"title": ""}), extra=f"dirs={idirs()}")
    judge("intake", "create title='   '", c.post(I, json={"title": "   "}), extra=f"dirs={idirs()}")
    judge("intake", "create received_on invalid", c.post(I, json={"title": "x", "received_on": "2026-13-01"}), extra=f"dirs={idirs()}")
    judge("intake", "create start>due", c.post(I, json={"title": "x", "start_date": "2026-05-01", "due_date": "2026-01-01"}), accept_2xx=True)
    judge("intake", "create priority='최상'", c.post(I, json={"title": "x", "priority": "최상"}), accept_2xx=True)
    judge("intake", "create effect_request=-1", c.post(I, json={"title": "x", "effect_request": -1}), extra=f"dirs={idirs()}")
    judge("intake", "create effect_request='abc'", c.post(I, json={"title": "x", "effect_request": "abc"}), extra=f"dirs={idirs()}")
    judge("intake", "create nature not in list", c.post(I, json={"title": "x", "nature": "없는분류"}), accept_2xx=True)
    r = c.post(I, json={"title": "승격 대상", "leader": "홍길동", "leader_team": "압연"}); iid = r.json()["id"]
    judge("intake", "GET promote plan", c.get(f"{I}/{iid}/promote"), accept_2xx=True)
    r = c.post(f"{I}/{iid}/promote", json={}); judge("intake", "promote (empty payload)", r, accept_2xx=True)
    pid = r.json().get("project_id") or r.json().get("id"); print("promoted ->", r.json())
    judge("intake", "promote twice", c.post(f"{I}/{iid}/promote", json={}))
    judge("intake", "PATCH after promote", c.patch(f"{I}/{iid}", json={"title": "x"}))
    judge("intake", "status after promote", c.post(f"{I}/{iid}/status", json={"status": "reviewing"}))
    print("intake after promote:", c.get(f"{I}/{iid}").json())
    # delete promoted project → intake back to pool?
    judge("intake", "archive promoted project", c.post(f"/api/projects/{pid}/archive"), accept_2xx=True)
    g = c.get(f"{I}/{iid}").json(); print("intake after project delete:", {k: g.get(k) for k in ("status", "project_id", "decision")})
    pool = c.get(I).json()["items"]; rec("intake", "intake after promoted project deleted", 200, "note", f"status={g.get('status')} in_pool={any(x['id']==iid for x in pool)} project_id={g.get('project_id')}")
    judge("intake", "promote again after project deleted", c.post(f"{I}/{iid}/promote", json={}), accept_2xx=True)
    # demote: project → to-intake
    pid2 = c.post("/api/projects", json={"title": "강등 대상"}).json()["id"]
    c.post(f"/api/projects/{pid2}/entries", json={"title": "일지", "body": "x"})
    judge("intake", "GET to-intake plan", c.get(f"/api/projects/{pid2}/to-intake"), accept_2xx=True)
    r = c.post(f"/api/projects/{pid2}/to-intake"); judge("intake", "POST to-intake (demote)", r, accept_2xx=True); print(r.json() if r.status_code < 300 else "")
    judge("intake", "demote twice", c.post(f"/api/projects/{pid2}/to-intake"))
    judge("intake", "GET demoted project", c.get(f"/api/projects/{pid2}"))
    # merge into non-existent
    iid2 = c.post(I, json={"title": "병합 대상"}).json()["id"]
    judge("intake", "merge into non-existent", c.post(f"{I}/{iid2}/status", json={"status": "merged", "merged_into": "2099-999", "note": "x"}))
    judge("intake", "merge into '' ", c.post(f"{I}/{iid2}/status", json={"status": "merged", "merged_into": "", "note": "x"}))
    judge("intake", "merge into itself (intake id)", c.post(f"{I}/{iid2}/status", json={"status": "merged", "merged_into": iid2, "note": "x"}))
    judge("intake", "status bogus", c.post(f"{I}/{iid2}/status", json={"status": "bogus"}))
    judge("intake", "status started (only via promote)", c.post(f"{I}/{iid2}/status", json={"status": "started", "note": "x"}))
    judge("intake", "reject without note", c.post(f"{I}/{iid2}/status", json={"status": "rejected"}))
    judge("intake", "reject note whitespace", c.post(f"{I}/{iid2}/status", json={"status": "rejected", "note": "   "}))
    judge("intake", "on_hold then PATCH", c.post(f"{I}/{iid2}/status", json={"status": "on_hold", "note": "보류"}), accept_2xx=True)
    judge("intake", "PATCH while on_hold", c.patch(f"{I}/{iid2}", json={"title": "보류 중 수정"}), accept_2xx=True)
    # logs
    judge("intake", "log create empty", c.post(f"{I}/{iid2}/logs", json={}), accept_2xx=True)
    judge("intake", "log create bad date", c.post(f"{I}/{iid2}/logs", json={"date": "2026-99-01"}))
    judge("intake", "log patch missing", c.patch(f"{I}/{iid2}/logs/nope.md", json={"body": "x"}))
    judge("intake", "log delete traversal", c.delete(f"{I}/{iid2}/logs/..%2Frequest.md"))
    judge("intake", "log delete 'request.md' (main file!)", c.delete(f"{I}/{iid2}/logs/request.md"), extra=f"still exists={c.get(f'{I}/{iid2}').status_code}")
    # precheck
    judge("intake", "precheck items bogus", c.put(f"{I}/{iid2}/precheck", json={"items": [{"group": "x", "item": "y", "choice": "z"}]}), accept_2xx=True)
    judge("intake", "precheck items 1000", c.put(f"{I}/{iid2}/precheck", json={"items": [{"group": "g", "item": f"i{i}", "choice": "a"} for i in range(1000)]}), accept_2xx=True)
    # attachments
    judge("intake", "attach ../x.png", c.post(f"{I}/{iid2}/attachments", files={"file": ("../x.png", b"\x89PNG\r\n", "image/png")}), accept_2xx=True)
    judge("intake", "attach zero byte", c.post(f"{I}/{iid2}/attachments", files={"file": ("empty.xlsx", b"", "application/octet-stream")}), accept_2xx=True)
    judge("intake", "attach delete without body", c.delete(f"{I}/{iid2}/attachments"))
    judge("intake", "attach delete path=../../x", c.request("DELETE", f"{I}/{iid2}/attachments", params={"path": "../../x"}))
    judge("intake", "attach delete json path", c.request("DELETE", f"{I}/{iid2}/attachments", json={"path": "../../settings.json"}), extra=f"settings exists={ (vault/'settings.json').exists()}")
    judge("intake", "attach preview path=../../settings.json", c.get(f"{I}/{iid2}/attachments/preview", params={"path": "../../settings.json"}))
    judge("intake", "intake-files traversal", c.get(f"/intake-files/{iid2}/../../settings.json"))
    # renumber with collisions
    c.put("/api/settings", json={"project_code": ""})
    a = c.post("/api/projects", json={"title": "코드없음 A"}).json()["id"]
    c.put("/api/settings", json={"project_code": "소재"})
    b = c.post("/api/projects", json={"title": "코드있음 B"}).json()["id"]
    print("ids:", a, b, "intakes:", [x["id"] for x in c.get(I, params={"scope": "all"}).json()["items"]])
    judge("renumber", "preview code=소재", c.post("/api/settings/project-code/renumber/preview", json={"code": "소재"}), accept_2xx=True)
    r = c.post("/api/settings/project-code/renumber", json={"code": "소재"}); judge("renumber", "apply code=소재", r, accept_2xx=True); print(r.json() if r.status_code < 300 else "")
    judge("renumber", "preview code=''", c.post("/api/settings/project-code/renumber/preview", json={"code": ""}), accept_2xx=True)
    judge("renumber", "apply code='' (back)", c.post("/api/settings/project-code/renumber", json={"code": ""}), accept_2xx=True)
    judge("renumber", "apply code='a/b'", c.post("/api/settings/project-code/renumber", json={"code": "a/b"}))
    judge("renumber", "apply code='소재' again (idempotent)", c.post("/api/settings/project-code/renumber", json={"code": "소재"}), accept_2xx=True)
    ids = [p["id"] for p in c.get("/api/projects").json()]; fs = project_dirs(vault)
    rec("renumber", "ids vs folders after renumber", 200, "ok" if all(any(d.startswith(i) for d in fs) for i in ids) and len(ids) == len(fs) else "PROBLEM", f"ids={ids} fs={fs}", "🔴")
    ri = c.post("/api/reindex").json(); ids2 = [p["id"] for p in c.get("/api/projects").json()]
    rec("renumber", "reindex after renumber", 200, "ok" if sorted(ids2) == sorted(ids) else "PROBLEM", f"before={ids} after={ids2} problems={ri['problems']}", "🔴")
    print("intakes after renumber:", [x["id"] for x in c.get(I, params={"scope": "all"}).json()["items"]], idirs())
    # intake next-id odd
    judge("intake", "next-id received_on=bad", c.get(f"{I}/next-id", params={"received_on": "x"}), accept_2xx=True)
    # intake archive and restore
    iid3 = c.post(I, json={"title": "보관"}).json()["id"]
    judge("intake", "archive", c.post(f"{I}/{iid3}/archive"), accept_2xx=True)
    judge("intake", "archive twice", c.post(f"{I}/{iid3}/archive"))
    judge("intake", "GET archived", c.get(f"{I}/{iid3}"))
    judge("intake", "GET /api/intakes/..%2F..%2Fsettings.json", c.get(f"{I}/..%2F..%2Fsettings.json"))
    judge("intake", "GET /api/intakes/%00", c.get(f"{I}/%00"))
finish("p5_intakes")
