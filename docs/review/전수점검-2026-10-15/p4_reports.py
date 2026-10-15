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
    pid = c.post(P, json={"title": "보고 과제"}).json()["id"]
    D = f"{P}/{pid}/reports/draft"
    judge("report", "draft with no entries", c.post(D, json={}), accept_2xx=True)
    judge("report", "draft date invalid", c.post(D, json={"report_date": "2026-13-01"}))
    judge("report", "draft date ''", c.post(D, json={"report_date": ""}), accept_2xx=True)
    judge("report", "draft audience 1000 chars", c.post(D, json={"audience": "회" * 1000}), accept_2xx=True)
    for x in ["2026-05-01", "2026-05-10", "2026-05-20"]:
        c.post(f"{P}/{pid}/entries", json={"title": f"일지 {x}", "date": x, "body": f"내용 {x}"})
    r = c.post(D, json={"report_date": "2026-05-21"}); judge("report", "draft with entries", r, accept_2xx=True); rid = r.json()["id"]
    judge("report", "second draft same date (dup)", c.post(D, json={"report_date": "2026-05-21"}), accept_2xx=True)
    judge("report", "PATCH report_date before earliest entry", c.patch(f"/api/reports/{rid}", json={"report_date": "2026-01-01"}), accept_2xx=True)
    print("after date move:", c.get(f"/api/reports/{rid}").json())
    judge("report", "PATCH report_date invalid", c.patch(f"/api/reports/{rid}", json={"report_date": "x"}))
    judge("report", "PATCH report_date ''", c.patch(f"/api/reports/{rid}", json={"report_date": ""}), accept_2xx=True)
    judge("report", "PATCH body='' then freeze", c.patch(f"/api/reports/{rid}", json={"body": ""}), accept_2xx=True)
    judge("report", "freeze with empty body", c.post(f"/api/reports/{rid}/freeze"), accept_2xx=True)
    judge("report", "freeze twice", c.post(f"/api/reports/{rid}/freeze"), accept_2xx=True)
    judge("report", "PATCH body when frozen", c.patch(f"/api/reports/{rid}", json={"body": "몰래"}))
    judge("report", "PATCH report_date when frozen", c.patch(f"/api/reports/{rid}", json={"report_date": "2026-06-01"}))
    judge("report", "PATCH feedback when frozen", c.patch(f"/api/reports/{rid}", json={"feedback": "지시"}), accept_2xx=True)
    judge("report", "feedback-done frozen", c.post(f"/api/reports/{rid}/feedback-done", json={}), accept_2xx=True)
    judge("report", "feedback-done twice", c.post(f"/api/reports/{rid}/feedback-done", json={}), accept_2xx=True)
    judge("report", "DELETE frozen report", c.delete(f"/api/reports/{rid}"))
    judge("report", "unfreeze", c.post(f"/api/reports/{rid}/unfreeze"), accept_2xx=True)
    judge("report", "unfreeze twice", c.post(f"/api/reports/{rid}/unfreeze"), accept_2xx=True)
    judge("report", "diff", c.get(f"/api/reports/{rid}/diff"), accept_2xx=True)
    judge("report", "ai-prompt", c.get(f"/api/reports/{rid}/ai-prompt"), accept_2xx=True)
    judge("report", "upload attachment to report (zero byte)", c.post(f"/api/reports/{rid}/attachments", files={"file": ("empty.png", b"", "image/png")}), accept_2xx=True)
    judge("report", "upload attachment to report (../x.png)", c.post(f"/api/reports/{rid}/attachments", files={"file": ("../x.png", b"\x89PNG", "image/png")}), accept_2xx=True)
    print("report attachments:", c.get(f"/api/reports/{rid}/attachments").json())
    judge("report", "DELETE draft report", c.delete(f"/api/reports/{rid}"), accept_2xx=True)
    judge("report", "DELETE twice", c.delete(f"/api/reports/{rid}"))
    # month grid / candidates / search filters
    judge("report", "month-grid year=0000", c.get("/api/report-month-grid", params={"year": "0000"}), accept_2xx=True)
    judge("report", "month-grid year=9999", c.get("/api/report-month-grid", params={"year": "9999"}), accept_2xx=True)
    judge("report", "reports?from=bad", c.get("/api/reports", params={"from": "2026-99-99"}), accept_2xx=True)
    judge("report", "reports?from>to", c.get("/api/reports", params={"from": "2026-12-01", "to": "2026-01-01"}), accept_2xx=True)
    judge("report", "reports?q=special", c.get("/api/reports", params={"q": '" * ( ) : - \'OR 1=1'}), accept_2xx=True)
    judge("report", "report-candidates include_inactive=zzz", c.get("/api/report-candidates", params={"include_inactive": "zzz"}))
    # report on a deleted project
    r = c.post(D, json={"report_date": "2026-05-25"}); rid2 = r.json()["id"]
    c.post(f"/api/reports/{rid2}/freeze")
    judge("report", "archive project with frozen report", c.post(f"{P}/{pid}/archive"), accept_2xx=True)
    judge("report", "GET report of deleted project", c.get(f"/api/reports/{rid2}"))
    judge("report", "GET /api/reports after project delete", c.get("/api/reports"), accept_2xx=True)
    print("reports listing:", c.get("/api/reports").json())
    judge("report", "PATCH report of deleted project", c.patch(f"/api/reports/{rid2}", json={"feedback": "x"}))
    judge("report", "freeze report of deleted project", c.post(f"/api/reports/{rid2}/freeze"))
    judge("report", "candidates after delete", c.get("/api/report-candidates"), accept_2xx=True)
    judge("report", "month-grid after delete", c.get("/api/report-month-grid", params={"year": "2026"}), accept_2xx=True)
    # restore project, check reports come back
    trash = c.get("/api/trash").json(); print("TRASH", trash)
    if trash:
        judge("report", "restore project from trash", c.post(f"/api/trash/{trash[0]['trash_name']}/restore"), accept_2xx=True)
        reps = c.get(f"{P}/{pid}/reports"); judge("report", "reports after restore", reps, accept_2xx=True, extra=f"n={len(reps.json()) if reps.status_code==200 else '-'}")
        g = c.get(f"/api/reports/{rid2}"); print("old report id after restore:", g.status_code)
    # project with no_report → draft?
    pid2 = c.post(P, json={"title": "보고없음", "no_report": True}).json()["id"]
    judge("report", "draft on no_report project", c.post(f"{P}/{pid2}/reports/draft", json={}), accept_2xx=True)
    # done project draft
    pid3 = c.post(P, json={"title": "완료", "status": "done"}).json()["id"]
    judge("report", "draft on done project", c.post(f"{P}/{pid3}/reports/draft", json={}), accept_2xx=True)
    # reports dir vs db
    reps = c.get("/api/reports").json()
    files = list((vault / "projects").rglob("reports/*/*.md")) + list((vault / "projects").rglob("reports/*.md"))
    rec("report-consistency", "report rows vs files", 200, "ok" if len(reps.get("items", reps) if isinstance(reps, dict) else reps) == len(files) else "note", f"api={len(reps.get('items', reps) if isinstance(reps, dict) else reps)} files={len(files)} {[str(f.relative_to(vault)) for f in files]}")
finish("p4_reports")
