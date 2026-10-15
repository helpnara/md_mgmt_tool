from harness import *

GETS = [
    "/api/health", "/api/meta", "/api/dashboard", "/api/home", "/api/activities", "/api/activities/summary",
    "/api/projects", "/api/projects/next-id", "/api/projects/2026-001", "/api/projects/2026-001/year-fix",
    "/api/projects/2026-001/clone", "/api/projects/2026-001/to-intake", "/api/projects/2026-001/entries",
    "/api/entries/1", "/api/entries/1/attachments", "/api/projects/2026-001/attachments",
    "/api/attachments/1/preview", "/api/attachments/1/thumb", "/files/x/y.png",
    "/api/reports", "/api/projects/2026-001/reports", "/api/reports/1", "/api/reports/1/diff",
    "/api/reports/1/attachments", "/api/reports/1/ai-prompt", "/api/report-month-grid?year=2026",
    "/api/report-month-grid", "/api/report-candidates", "/api/search", "/api/search?q=x", "/api/backup",
    "/api/projects/2026-001/export", "/api/projects/2026-001/export?format=md", "/api/settings",
    "/api/settings/defaults", "/api/settings/project-types", "/api/settings/backup/status", "/api/people",
    "/api/trash", "/api/errors", "/api/versions?path=x", "/api/versions", "/api/versions/overview",
    "/api/versions/content?path=x&stamp=y", "/api/folders", "/api/maintenance/link-fix", "/api/intakes",
    "/api/intakes?scope=all", "/api/intakes/next-id", "/api/intakes/R2026-001", "/api/intakes/R2026-001/promote",
    "/api/intakes/R2026-001/attachments/preview", "/intake-files/x/y.png", "/api/drafts", "/api/drafts/overview:x",
    "/api/drafts/bad key", "/api/roadmap", "/api/meetings", "/api/meetings?year=abcd", "/api/projects?year=20266",
    "/api/projects?sort=;DROP", "/api/projects?sort=__class__", "/api/intakes?sort=x;--", "/api/reports?limit=0",
    "/api/reports?from=2026-99-99", "/api/errors?limit=0", "/api/entries/99999999999999999999", "/api/entries/-1",
    "/api/entries/abc", "/api/projects/..%2F..%2Fetc", "/api/projects/%00", "/api/activities?year=x",
]

with fresh() as (c, vault):
    for path in GETS:
        r = c.get(path)
        st = r.status_code
        if st >= 500:
            rec("empty-get", f"GET {path}", r, "PROBLEM", "500", "⛔")
        elif st >= 400:
            d = detail(r)
            if st == 422:
                rec("empty-get", f"GET {path}", r, "note", f"422 pydantic english msg: {d[:80]}")
            elif not is_korean(d):
                rec("empty-get", f"GET {path}", r, "PROBLEM", f"non-Korean error: {d[:80]}", "🟡")
            else:
                rec("empty-get", f"GET {path}", r, "ok", d[:60])
        else:
            rec("empty-get", f"GET {path}", r, "ok", f"len={len(r.content)}")
    # POST-ish on empty
    for m, path, body in [
        ("post", "/api/reindex", None),
        ("post", "/api/maintenance/link-fix", {}),
        ("post", "/api/settings/backup/run", None),
        ("post", "/api/settings/project-code/renumber/preview", {"code": "소재"}),
        ("post", "/api/settings/project-code/renumber", {"code": "소재"}),
        ("post", "/api/projects/2026-001/reports/draft", {}),
        ("post", "/api/trash/nothing/restore", None),
        ("post", "/api/trash/..%2F..%2Fetc/restore", None),
        ("post", "/api/versions/restore", {"path": "x", "stamp": "y"}),
        ("post", "/api/versions/restore", {"path": "../../../etc/passwd", "stamp": "y"}),
        ("post", "/api/people/handover", {"old": "a", "new": "b"}),
        ("post", "/api/people/rename", {"old": "a", "new": "b"}),
        ("post", "/api/people/rename", {"old": "", "new": ""}),
        ("post", "/api/people", {"name": ""}),
        ("post", "/api/people", {"name": "   "}),
        ("post", "/api/intakes/R2026-001/promote", {}),
        ("post", "/api/intakes/R2026-001/status", {"status": "rejected", "note": "x"}),
        ("post", "/api/errors/client", {"screen": "x" * 81}),
        ("post", "/api/errors/client", {}),
        ("delete", "/api/errors", None),
        ("post", "/api/activities", {}),
        ("post", "/api/activities", {"person": "", "title": "x"}),
        ("post", "/api/meetings", {}),
        ("patch", "/api/meetings/1", {"summary": "x"}),
        ("delete", "/api/meetings/1", None),
        ("delete", "/api/activities/1", None),
        ("patch", "/api/activities/1", {"title": "x"}),
        ("post", "/api/reports/1/feedback-done", None),
        ("post", "/api/reports/1/freeze", None),
        ("delete", "/api/reports/1", None),
        ("delete", "/api/attachments/1", None),
        ("delete", "/api/entries/1", None),
        ("patch", "/api/entries/1", {"body": "x"}),
        ("post", "/api/projects/2026-001/archive", None),
        ("post", "/api/projects/2026-001/year-fix", None),
        ("post", "/api/projects/2026-001/to-intake", None),
        ("post", "/api/folders", {"parent": str(vault), "name": "../x"}),
        ("post", "/api/folders", {"parent": str(vault), "name": ""}),
        ("post", "/api/folders", {"parent": "/nonexistent/zzz", "name": "a"}),
        ("put", "/api/settings/project-types", {"types": []}),
        ("put", "/api/settings/project-types", {"types": [{"key": "", "label": ""}]}),
        ("put", "/api/settings/project-types", {"types": [{"key": "../x", "label": "a"}]}),
    ]:
        r = getattr(c, m)(path, json=body) if body is not None else getattr(c, m)(path)
        st = r.status_code
        if st >= 500:
            rec("empty-write", f"{m.upper()} {path} {body}", r, "PROBLEM", "500", "⛔")
        elif st >= 400:
            d = detail(r)
            if st == 422:
                rec("empty-write", f"{m.upper()} {path} {body}", r, "note", f"422: {d[:80]}")
            elif not is_korean(d):
                rec("empty-write", f"{m.upper()} {path} {body}", r, "PROBLEM", f"non-Korean: {d[:80]}", "🟡")
            else:
                rec("empty-write", f"{m.upper()} {path} {body}", r, "ok", d[:60])
        else:
            rec("empty-write", f"{m.upper()} {path} {body}", r, "note", f"{st} on empty vault")
    print("TREE", tree(vault))
    r = c.get("/api/settings/project-types").json()
    print("project-types after empty put:", r)
finish("p1_empty")
