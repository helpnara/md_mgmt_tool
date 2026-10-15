from harness import *
import shutil, io
from PIL import Image
def png():
    b = io.BytesIO(); Image.new("RGB", (10, 10), "red").save(b, "PNG"); return b.getvalue()
def safe(fn):
    try: return fn()
    except Exception as e:
        class R: status_code=500; text=f'EXC {type(e).__name__}: {str(e)[:120]}'; headers={}; content=b''
        return R()
def judge(name, req, r, accept_2xx=False, extra=""):
    st = r.status_code
    if st >= 500: rec(name, req, r, "PROBLEM", "500 " + r.text[:120] + extra, "⛔")
    elif st >= 400:
        d = detail(r) if hasattr(r, "json") else r.text
        if st == 422: rec(name, req, r, "note", "422 english: " + d[:90] + extra)
        elif not is_korean(d): rec(name, req, r, "PROBLEM", "non-Korean " + d[:80], "🟡")
        else: rec(name, req, r, "ok", d[:80] + extra)
    else: rec(name, req, r, "ok" if accept_2xx else "note", f"{st} " + extra)
    return r

with fresh() as (c, vault):
    P = "/api/projects"
    # project folder deleted externally
    pid = c.post(P, json={"title": "외부삭제"}).json()["id"]; dn = c.get(f"{P}/{pid}").json()["dir_name"]
    eid = c.post(f"{P}/{pid}/entries", json={"title": "일지", "date": "2026-03-01"}).json()["id"]
    rid = c.post(f"{P}/{pid}/reports/draft", json={"report_date": "2026-03-02"}).json()["id"]
    att = c.post(f"/api/entries/{eid}/attachments", files={"file": ("a.png", png(), "image/png")}).json()
    shutil.rmtree(vault / "projects" / dn)
    judge("ext-project", "GET project (folder gone)", c.get(f"{P}/{pid}"), accept_2xx=True)
    judge("ext-project", "PATCH project (folder gone)", safe(lambda: c.patch(f"{P}/{pid}", json={"title": "x"})))
    judge("ext-project", "PATCH project body only (folder gone)", safe(lambda: c.patch(f"{P}/{pid}", json={"body": "x"})))
    judge("ext-project", "POST entry (folder gone)", safe(lambda: c.post(f"{P}/{pid}/entries", json={"title": "x"})), extra=f"fs={[d for d in project_dirs(vault) if d.startswith(pid)]}")
    judge("ext-project", "GET entry (folder gone)", safe(lambda: c.get(f"/api/entries/{eid}")), accept_2xx=True)
    judge("ext-project", "PATCH entry (folder gone)", safe(lambda: c.patch(f"/api/entries/{eid}", json={"body": "x"})))
    judge("ext-project", "DELETE entry (folder gone)", safe(lambda: c.delete(f"/api/entries/{eid}")))
    judge("ext-project", "GET report (folder gone)", safe(lambda: c.get(f"/api/reports/{rid}")), accept_2xx=True)
    judge("ext-project", "PATCH report (folder gone)", safe(lambda: c.patch(f"/api/reports/{rid}", json={"body": "x"})))
    judge("ext-project", "freeze report (folder gone)", safe(lambda: c.post(f"/api/reports/{rid}/freeze")))
    judge("ext-project", "DELETE report (folder gone)", safe(lambda: c.delete(f"/api/reports/{rid}")))
    judge("ext-project", "draft report (folder gone)", safe(lambda: c.post(f"{P}/{pid}/reports/draft", json={})))
    judge("ext-project", "GET attachment url (folder gone)", safe(lambda: c.get(att["url"])))
    judge("ext-project", "GET thumb (folder gone)", safe(lambda: c.get(att["thumb_url"])))
    judge("ext-project", "DELETE attachment (folder gone)", safe(lambda: c.delete(f"/api/attachments/{att['id']}")))
    judge("ext-project", "upload attachment (folder gone)", safe(lambda: c.post(f"/api/entries/{eid}/attachments", files={"file": ("b.png", png(), "image/png")})))
    judge("ext-project", "export (folder gone)", safe(lambda: c.get(f"{P}/{pid}/export")))
    judge("ext-project", "export md (folder gone)", safe(lambda: c.get(f"{P}/{pid}/export?format=md")))
    judge("ext-project", "ai-prompt (folder gone)", safe(lambda: c.get(f"/api/reports/{rid}/ai-prompt")), accept_2xx=True)
    judge("ext-project", "to-intake (folder gone)", safe(lambda: c.post(f"{P}/{pid}/to-intake")))
    judge("ext-project", "year-fix (folder gone)", safe(lambda: c.post(f"{P}/{pid}/year-fix")), accept_2xx=True)
    judge("ext-project", "archive (folder gone)", safe(lambda: c.post(f"{P}/{pid}/archive")))
    judge("ext-project", "backup zip (folder gone)", safe(lambda: c.get("/api/backup")), accept_2xx=True)
    judge("ext-project", "link-fix apply (folder gone)", safe(lambda: c.post("/api/maintenance/link-fix", json={})), accept_2xx=True)
    judge("ext-project", "renumber (folder gone)", safe(lambda: c.post("/api/settings/project-code/renumber", json={"code": "소재"})), accept_2xx=True)
    judge("ext-project", "home (folder gone)", c.get("/api/home"), accept_2xx=True)
    r = c.post("/api/reindex"); rec("ext-project", "reindex clears ghost", r, "ok" if c.get(f"{P}/{pid}").status_code == 404 else "PROBLEM", f"{r.json()}", "🔴")
    # entry file removed only
    pid2 = c.post(P, json={"title": "일지삭제"}).json()["id"]; dn2 = c.get(f"{P}/{pid2}").json()["dir_name"]
    e2 = c.post(f"{P}/{pid2}/entries", json={"title": "파일삭제", "date": "2026-04-01"}).json()
    (vault / "projects" / dn2 / e2["rel_path"]).unlink()
    judge("ext-entry", "GET entry (file gone)", safe(lambda: c.get(f"/api/entries/{e2['id']}")), accept_2xx=True)
    judge("ext-entry", "PATCH entry (file gone)", safe(lambda: c.patch(f"/api/entries/{e2['id']}", json={"body": "x"})))
    judge("ext-entry", "upload to entry (file gone)", safe(lambda: c.post(f"/api/entries/{e2['id']}/attachments", files={"file": ("a.png", png(), "image/png")})))
    judge("ext-entry", "DELETE entry (file gone)", safe(lambda: c.delete(f"/api/entries/{e2['id']}")))
    judge("ext-entry", "draft report (entry file gone)", safe(lambda: c.post(f"{P}/{pid2}/reports/draft", json={})), accept_2xx=True)
    judge("ext-entry", "export (entry file gone)", safe(lambda: c.get(f"{P}/{pid2}/export?format=html")), accept_2xx=True)
    # attachment file removed
    e3 = c.post(f"{P}/{pid2}/entries", json={"title": "첨부삭제", "date": "2026-04-02"}).json()
    a3 = c.post(f"/api/entries/{e3['id']}/attachments", files={"file": ("c.png", png(), "image/png")}).json()
    (vault / "projects" / dn2 / a3["rel_path"]).unlink()
    judge("ext-att", "GET thumb (file gone)", safe(lambda: c.get(a3["thumb_url"])))
    judge("ext-att", "GET url (file gone)", safe(lambda: c.get(a3["url"])))
    judge("ext-att", "preview (file gone)", safe(lambda: c.get(f"/api/attachments/{a3['id']}/preview")))
    judge("ext-att", "DELETE attachment (file gone)", safe(lambda: c.delete(f"/api/attachments/{a3['id']}")))
    judge("ext-att", "export zip (att file gone)", safe(lambda: c.get(f"{P}/{pid2}/export?format=zip")), accept_2xx=True)
    judge("ext-att", "export md inline (att file gone)", safe(lambda: c.get(f"{P}/{pid2}/export?format=md&assets=inline")), accept_2xx=True)
    # intake folder removed
    iid = c.post("/api/intakes", json={"title": "접수삭제"}).json()["id"]; idn = c.get(f"/api/intakes/{iid}").json()["dir_name"]
    shutil.rmtree(vault / "intakes" / idn)
    judge("ext-intake", "GET intake (folder gone)", safe(lambda: c.get(f"/api/intakes/{iid}")), accept_2xx=True)
    judge("ext-intake", "PATCH intake (folder gone)", safe(lambda: c.patch(f"/api/intakes/{iid}", json={"title": "x"})))
    judge("ext-intake", "status intake (folder gone)", safe(lambda: c.post(f"/api/intakes/{iid}/status", json={"status": "rejected", "note": "x"})))
    judge("ext-intake", "promote intake (folder gone)", safe(lambda: c.post(f"/api/intakes/{iid}/promote", json={})), extra=f"fs projects={len(project_dirs(vault))} api={len(c.get(P).json())}")
    judge("ext-intake", "log intake (folder gone)", safe(lambda: c.post(f"/api/intakes/{iid}/logs", json={"body": "x"})))
    judge("ext-intake", "archive intake (folder gone)", safe(lambda: c.post(f"/api/intakes/{iid}/archive")))
    judge("ext-intake", "list intakes (folder gone)", c.get("/api/intakes"), accept_2xx=True)
    # meeting / activity file removed
    mid = c.post("/api/meetings", json={"person": "홍", "date": "2026-10-01", "summary": "s"}).json()["id"]
    shutil.rmtree(vault / "people" / "홍")
    judge("ext-meeting", "PATCH meeting (file gone)", safe(lambda: c.patch(f"/api/meetings/{mid}", json={"summary": "x"})))
    judge("ext-meeting", "DELETE meeting (file gone)", safe(lambda: c.delete(f"/api/meetings/{mid}")))
    aid = c.post("/api/activities", json={"person": "김", "title": "교육", "date": "2026-01-01"}).json()["id"]
    shutil.rmtree(vault / "people" / "김")
    judge("ext-activity", "PATCH activity (file gone)", safe(lambda: c.patch(f"/api/activities/{aid}", json={"title": "x"})))
    judge("ext-activity", "DELETE activity (file gone)", safe(lambda: c.delete(f"/api/activities/{aid}")))
    # trash manifest corrupted
    (vault / ".trash" / "manifest.jsonl").write_text("{bad json\n", encoding="utf-8")
    judge("ext-trash", "GET trash with corrupt manifest", safe(lambda: c.get("/api/trash")), accept_2xx=True)
    # drafts file corrupted
    (vault / ".drafts").mkdir(exist_ok=True); (vault / ".drafts" / "overview__x.json").write_text("{bad", encoding="utf-8")
    judge("ext-drafts", "GET drafts with corrupt file", safe(lambda: c.get("/api/drafts")), accept_2xx=True)
    judge("ext-drafts", "GET draft corrupt", safe(lambda: c.get("/api/drafts/overview:x")), accept_2xx=True)
    # versions dir file corrupted / errors log corrupted
    (vault / ".logs").mkdir(exist_ok=True); (vault / ".logs" / "error-2026-10.log").write_text("not json\n{also bad", encoding="utf-8")
    judge("ext-errors", "GET errors with corrupt log", safe(lambda: c.get("/api/errors")), accept_2xx=True)
    # settings.json unreadable types
    (vault / "settings.json").write_text('{"people": "notalist", "project_types": "x", "report_weekday": "x", "classifications": [], "backup_keep": "x"}', encoding="utf-8")
    judge("ext-settings", "GET settings with wrong-typed settings.json", safe(lambda: c.get("/api/settings")), accept_2xx=True)
    judge("ext-settings", "GET meta with wrong-typed settings.json", safe(lambda: c.get("/api/meta")), accept_2xx=True)
    judge("ext-settings", "GET people with wrong-typed settings.json", safe(lambda: c.get("/api/people")), accept_2xx=True)
    judge("ext-settings", "POST project with wrong-typed settings.json", safe(lambda: c.post(P, json={"title": "x"})), accept_2xx=True)
    judge("ext-settings", "GET home with wrong-typed settings.json", safe(lambda: c.get("/api/home")), accept_2xx=True)
    judge("ext-settings", "GET activities/summary wrong-typed", safe(lambda: c.get("/api/activities/summary")), accept_2xx=True)
    judge("ext-settings", "GET intakes wrong-typed", safe(lambda: c.get("/api/intakes")), accept_2xx=True)
    judge("ext-settings", "GET report-candidates wrong-typed", safe(lambda: c.get("/api/report-candidates")), accept_2xx=True)
    judge("ext-settings", "backup status wrong-typed", safe(lambda: c.get("/api/settings/backup/status")), accept_2xx=True)
finish("p14")
