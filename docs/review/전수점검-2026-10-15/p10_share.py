from harness import *
import os
from fastapi.testclient import TestClient
import re

SENSITIVE = [r"/tmp/claude", r"probe_vault", r"backup_dir", r"employee_id", r"사번", r"\.versions", r"error-20", r"\.drafts", r"비밀면담"]

with fresh(share=True, client_addr=("10.0.0.2", 51000)) as (remote, vault):
    from app.main import app
    with TestClient(app, client=("127.0.0.1", 51001)) as local:
        # seed data
        local.put("/api/settings", json={"author": "주인", "backup_dir": str(vault.parent / "bk")})
        local.put("/api/people", json={"people": [{"name": "홍길동", "employee_id": "EMP-7777", "account": "hong"}]})
        pid = local.post("/api/projects", json={"title": "공유 과제", "owners": ["홍길동"], "body": "개요 비밀"}).json()["id"]
        dn = local.get(f"/api/projects/{pid}").json()["dir_name"]
        eid = local.post(f"/api/projects/{pid}/entries", json={"title": "일지", "date": "2026-03-01", "body": "일지 내용"}).json()["id"]
        local.patch(f"/api/entries/{eid}", json={"body": "일지 내용 v2"})
        att = local.post(f"/api/entries/{eid}/attachments", files={"file": ("a.txt", b"attachment text", "text/plain")}).json()
        rid = local.post(f"/api/projects/{pid}/reports/draft", json={"report_date": "2026-03-05"}).json()["id"]
        local.put(f"/api/drafts/overview:{pid}", json={"content": "쓰다 만 비밀 글"})
        mid = local.post("/api/meetings", json={"person": "홍길동", "date": "2026-10-01", "kind": "정기", "summary": "비밀면담", "followups": ["후속"]}).json()["id"]
        iid = local.post("/api/intakes", json={"title": "접수", "leader": "홍길동"}).json()["id"]
        iatt = local.post(f"/api/intakes/{iid}/attachments", files={"file": ("i.txt", b"intake attach", "text/plain")}).json()
        aid = local.post("/api/activities", json={"person": "홍길동", "title": "교육", "date": "2026-01-01"}).json()["id"]
        local.post(f"/api/projects/{pid}/archive") if False else None
        local.post("/api/settings/backup/run")
        local.get("/api/projects/nope")  # error log entry
        vs = local.get("/api/versions", params={"path": f"projects/{dn}/logs/2026-03-01-일지.md"}).json()["items"]
        stamp = vs[0]["stamp"] if vs else "x"
        GETS = ["/api/health", "/api/meta", "/api/dashboard", "/api/home", "/api/activities", "/api/activities/summary", f"/api/activities?person=홍길동",
                "/api/projects", "/api/projects/next-id", f"/api/projects/{pid}", f"/api/projects/{pid}/year-fix", f"/api/projects/{pid}/clone", f"/api/projects/{pid}/to-intake",
                f"/api/projects/{pid}/entries", f"/api/entries/{eid}", f"/api/entries/{eid}/attachments", f"/api/projects/{pid}/attachments", f"/api/attachments/{att['id']}/preview",
                f"/api/attachments/{att['id']}/thumb", att["url"], "/api/reports", f"/api/projects/{pid}/reports", f"/api/reports/{rid}", f"/api/reports/{rid}/diff", f"/api/reports/{rid}/attachments",
                f"/api/reports/{rid}/ai-prompt", "/api/report-month-grid?year=2026", "/api/report-candidates", "/api/search?q=비밀", "/api/search?q=면담", "/api/backup", f"/api/projects/{pid}/export",
                f"/api/projects/{pid}/export?format=backup", f"/api/projects/{pid}/export?format=html", "/api/settings", "/api/settings/defaults", "/api/settings/project-types", "/api/settings/backup/status",
                "/api/people", "/api/trash", "/api/errors", f"/api/versions?path=projects/{dn}/logs/2026-03-01-일지.md", "/api/versions/overview", f"/api/versions/content?path=projects/{dn}/logs/2026-03-01-일지.md&stamp={stamp}",
                "/api/folders", "/api/maintenance/link-fix", "/api/intakes", "/api/intakes?scope=all", "/api/intakes/next-id", f"/api/intakes/{iid}", f"/api/intakes/{iid}/promote",
                f"/api/intakes/{iid}/attachments/preview?path={iatt.get('rel_path','x')}", iatt.get("url", "/intake-files/x/y"), "/api/drafts", f"/api/drafts/overview:{pid}", "/api/roadmap", "/api/meetings", "/api/meetings?person=홍길동",
                "/api/meetings/?person=홍길동", "/API/meetings", "/api/meetings/", "/api//meetings", "/api/settings/", "/api/people/", "/api/drafts/", "/api/health/", "/api/trash/", "/api/folders/", "/api/errors/", "/api/versions/overview/",
                "/openapi.json", "/docs"]
        for path in GETS:
            r = remote.get(path)
            body = r.text if "json" in r.headers.get("content-type", "") or "text" in r.headers.get("content-type", "") else ""
            hits = [s for s in SENSITIVE if re.search(s, body)]
            if r.status_code == 200 and hits:
                rec("share-get", f"GET {path}", r, "PROBLEM", f"200 with sensitive: {hits}", "⛔")
            elif r.status_code == 200:
                rec("share-get", f"GET {path}", r, "ok", f"len={len(r.content)}")
            elif r.status_code == 403: rec("share-get", f"GET {path}", r, "ok", "403")
            elif r.status_code >= 500: rec("share-get", f"GET {path}", r, "PROBLEM", "500", "⛔")
            else: rec("share-get", f"GET {path}", r, "note", f"{r.status_code} {detail(r)[:60]}")
        # summary content check
        s = remote.get("/api/activities/summary").json(); print("remote summary people:", s["people"])
        print("remote meta keys w/ values:", {k: v for k, v in remote.get("/api/meta").json().items() if k in ("vault", "people", "people_left", "project_code", "share", "readonly", "problems")})
        print("remote home:", str(remote.get("/api/home").json())[:600])
        print("remote search 면담:", remote.get("/api/search?q=면담").json())
        print("remote search 비밀:", str(remote.get("/api/search?q=비밀").json())[:400])
        # non-GET
        WRITES = [("post", "/api/projects", {"title": "x"}), ("patch", f"/api/projects/{pid}", {"title": "x"}), ("post", f"/api/projects/{pid}/archive", None), ("post", f"/api/projects/{pid}/entries", {"title": "x"}),
                  ("patch", f"/api/entries/{eid}", {"body": "x"}), ("delete", f"/api/entries/{eid}", None), ("post", f"/api/entries/{eid}/attachments", None), ("delete", f"/api/attachments/{att['id']}", None),
                  ("post", f"/api/projects/{pid}/reports/draft", {}), ("patch", f"/api/reports/{rid}", {"body": "x"}), ("post", f"/api/reports/{rid}/freeze", None), ("delete", f"/api/reports/{rid}", None),
                  ("post", "/api/reindex", None), ("put", "/api/settings", {"author": "x"}), ("put", "/api/settings/project-types", {"types": []}), ("post", "/api/settings/project-code/renumber", {"code": "x"}),
                  ("post", "/api/settings/backup/run", None), ("put", "/api/people", {"people": []}), ("post", "/api/people", {"name": "x"}), ("post", "/api/people/rename", {"old": "a", "new": "b"}),
                  ("post", "/api/trash/x/restore", None), ("delete", "/api/errors", None), ("post", "/api/errors/client", {"screen": "x"}), ("post", "/api/versions/restore", {"path": "x", "stamp": "y"}),
                  ("post", "/api/folders", {"parent": "/tmp", "name": "x"}), ("post", "/api/maintenance/link-fix", {}), ("post", "/api/intakes", {"title": "x"}), ("patch", f"/api/intakes/{iid}", {"title": "x"}),
                  ("post", f"/api/intakes/{iid}/status", {"status": "rejected", "note": "x"}), ("put", f"/api/intakes/{iid}/precheck", {"items": []}), ("post", f"/api/intakes/{iid}/promote", {}), ("post", f"/api/intakes/{iid}/archive", None),
                  ("post", f"/api/intakes/{iid}/logs", {}), ("delete", f"/api/intakes/{iid}/attachments?path=x", None), ("put", f"/api/drafts/overview:{pid}", {"content": "x"}), ("delete", f"/api/drafts/overview:{pid}", None),
                  ("post", "/api/meetings", {"person": "a", "date": "2026-01-01", "summary": "x"}), ("patch", f"/api/meetings/{mid}", {"summary": "x"}), ("delete", f"/api/meetings/{mid}", None),
                  ("post", "/api/activities", {"person": "a", "title": "x"}), ("delete", f"/api/activities/{aid}", None), ("options", "/api/projects", None), ("head", "/api/settings", None), ("head", "/api/health", None),
                  ("post", "/api/projects/", {"title": "x"}), ("post", "/API/projects", {"title": "x"}), ("post", "/api//projects", {"title": "x"})]
        for m, path, body in WRITES:
            r = remote.request(m.upper(), path, json=body) if body is not None else remote.request(m.upper(), path)
            if m in ("options", "head"):
                rec("share-write", f"{m.upper()} {path}", r, "note" if r.status_code == 200 and m == "head" and "settings" in path else "ok", f"{r.status_code} len={len(r.content)}")
            elif r.status_code != 403:
                rec("share-write", f"{m.upper()} {path}", r, "PROBLEM", f"not 403: {r.status_code}", "⛔")
            else: rec("share-write", f"{m.upper()} {path}", r, "ok", "403")
        # header spoofing: X-Forwarded-For / Host from remote
        for h in [{"X-Forwarded-For": "127.0.0.1"}, {"X-Real-IP": "127.0.0.1"}, {"Host": "localhost"}, {"Forwarded": "for=127.0.0.1"}]:
            r = remote.post("/api/projects", json={"title": "spoof"}, headers=h)
            rec("share-spoof", f"POST with {h}", r, "ok" if r.status_code == 403 else "PROBLEM", f"{r.status_code}", "⛔")
        # no client info
        # state unchanged?
        print("projects after remote writes:", [p["title"] for p in local.get("/api/projects").json()])
        print("access log:", [p.name for p in (vault / ".logs").glob("access-*")], (vault / ".logs").glob("access-*").__class__)
        # readcache leak: local GET of /api/meta first then remote
        lm = local.get("/api/meta").json(); rm = remote.get("/api/meta").json()
        rec("share-cache", "meta local vs remote vault field", 200, "ok" if rm["vault"] == "" and lm["vault"] else "PROBLEM", f"local={lm['vault']!r} remote={rm['vault']!r}", "⛔")
        lh = local.get("/api/home").text; rh = remote.get("/api/home").text
        rec("share-cache", "home remote contains vault path?", 200, "PROBLEM" if str(vault) in rh else "ok", f"local_has={str(vault) in lh}", "⛔")
        ls = local.get("/api/activities/summary").json(); rs = remote.get("/api/activities/summary").json()
        rec("share-cache", "summary remote meetings hidden after local fetch", 200, "ok" if all(p["meetings"] == 0 for p in rs["people"]) else "PROBLEM", f"remote={rs['people']}", "⛔")
finish("p10_share")
