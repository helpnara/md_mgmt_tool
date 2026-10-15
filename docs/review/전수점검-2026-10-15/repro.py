"""Stability repro experiments (read-only against repo; uses temp vaults)."""
from __future__ import annotations
import io, os, sys, tempfile, shutil, json, traceback
from pathlib import Path
sys.path.insert(0, "/home/user/md_mgmt_tool/backend")

results = {}

def fresh_client():
    vault = Path(tempfile.mkdtemp(prefix="sweep-")) / "vault"
    os.environ["MD_MGMT_VAULT"] = str(vault)
    from app.config import get_settings
    get_settings.cache_clear()
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app, raise_server_exceptions=False)
    c.__enter__()
    return c, vault

def close(c):
    try: c.__exit__(None, None, None)
    except Exception: pass
    from app.config import get_settings
    get_settings.cache_clear()

def run(name, fn):
    import sys as _s
    if len(_s.argv) > 1 and name.split("_")[0] not in _s.argv[1:]:
        return
    try:
        results[name] = fn()
    except Exception as exc:
        results[name] = f"EXC {type(exc).__name__}: {exc}\n{traceback.format_exc()[-800:]}"

# A. BOM in index.md
def exp_bom():
    c, vault = fresh_client()
    try:
        p = c.post("/api/projects", json={"title": "BOM 과제", "owners": ["홍길동"], "due_date": "2026-12-31"}).json()
        p = c.get(f"/api/projects/{p['id']}").json()
        d = vault / "projects" / p["dir_name"] / "index.md"
        d.write_bytes(b"\xef\xbb\xbf" + d.read_bytes())
        r = c.post("/api/reindex"); 
        g = c.get(f"/api/projects/{p['id']}").json()
        before = {"title": g.get("title"), "owners": g.get("owners"), "due": g.get("due_date"), "body_head": (g.get("body") or "")[:60]}
        # now a normal status change through the tool
        u = c.patch(f"/api/projects/{p['id']}", json={"status": "done"})
        text = d.read_text(encoding="utf-8")
        return {"reindex": r.status_code, "after_bom": before, "patch": u.status_code, "file_head": text[:200]}
    finally: close(c)
run("A_bom", exp_bom)

# B. update_project: rename fails after index.md saved -> later 409
def exp_rename_fail():
    c, vault = fresh_client()
    try:
        from app.services import projects as svc
        from app.vault import paths
        p = c.post("/api/projects", json={"title": "원래 제목"}).json()
        p = c.get(f"/api/projects/{p['id']}").json()
        orig = paths.move
        def boom(s, t): raise paths.FileInUseError("busy")
        paths.move = boom
        try:
            r1 = c.patch(f"/api/projects/{p['id']}", json={"title": "바뀐 제목"})
        finally:
            paths.move = orig
        g = c.get(f"/api/projects/{p['id']}").json()
        r2 = c.patch(f"/api/projects/{p['id']}", json={"status": "done"})
        d = vault / "projects" / p["dir_name"] / "index.md"
        return {"first": r1.status_code, "db_title_after": g.get("title"), "file_has_new_title": "바뀐 제목" in d.read_text(encoding="utf-8"), "second_patch": (r2.status_code, r2.json().get("detail", "")[:60])}
    finally: close(c)
run("B_rename_fail", exp_rename_fail)

# C. restore entry after project renamed
def exp_restore_after_rename():
    c, vault = fresh_client()
    try:
        p = c.post("/api/projects", json={"title": "첫 제목"}).json()
        e = c.post(f"/api/projects/{p['id']}/entries", json={"title": "기록", "body": "내용", "date": "2026-01-05"}).json()
        c.delete(f"/api/entries/{e['id']}")
        c.patch(f"/api/projects/{p['id']}", json={"title": "둘째 제목"})
        items = c.get("/api/trash").json()
        name = items[0]["trash_name"]
        r = c.post(f"/api/trash/{name}/restore")
        entries = c.get(f"/api/projects/{p['id']}/entries").json()
        dirs = sorted(x.name for x in (vault / "projects").iterdir())
        problems = c.get("/api/meta").json()["problems"]
        return {"restore": (r.status_code, r.json()), "entries_visible": len(entries), "project_dirs": dirs, "problems": problems}
    finally: close(c)
run("C_restore_after_rename", exp_restore_after_rename)

# D. thumbnail of fake png
def exp_thumb():
    c, vault = fresh_client()
    try:
        p = c.post("/api/projects", json={"title": "썸네일"}).json()
        e = c.post(f"/api/projects/{p['id']}/entries", json={"title": "기록"}).json()
        r = c.post(f"/api/entries/{e['id']}/attachments", files={"file": ("photo.png", b"not really a png", "image/png")})
        a = r.json()
        t = c.get(a["thumb_url"])
        return {"upload": r.status_code, "thumb": t.status_code}
    finally: close(c)
run("D_thumb_fake_png", exp_thumb)

# E. malformed precheck -> reindex crash
def exp_precheck():
    c, vault = fresh_client()
    try:
        i = c.post("/api/intakes", json={"title": "요청"}).json()
        req = vault / "intakes" / i["dir_name"] / "request.md"
        text = req.read_text(encoding="utf-8")
        text = text.replace("precheck: null", "precheck:\n  items:\n  - choice: 있음\n    score: 십\n    group: 데이터\n    item: x\n")
        req.write_text(text, encoding="utf-8")
        r = c.post("/api/reindex")
        g = c.get(f"/api/intakes/{i['id']}")
        from app.vault.indexer import reindex_all
        from app import deps
        try:
            reindex_all(deps._conn); direct = "ok"
        except Exception as exc:
            direct = f"{type(exc).__name__}: {exc}"
        return {"reindex_http": r.status_code, "get": g.status_code, "startup_reindex_would": direct}
    finally: close(c)
run("E_precheck_malformed", exp_precheck)

# F. entry PATCH with rename failing -> 500?
def exp_entry_move_fail():
    c, vault = fresh_client()
    try:
        from app.vault import paths
        p = c.post("/api/projects", json={"title": "과제"}).json()
        e = c.post(f"/api/projects/{p['id']}/entries", json={"title": "기록 하나", "date": "2026-01-05"}).json()
        orig = paths.move
        paths.move = lambda s, t: (_ for _ in ()).throw(paths.FileInUseError("busy"))
        try:
            r = c.patch(f"/api/entries/{e['id']}", json={"title": "기록 둘"})
        finally:
            paths.move = orig
        r2 = c.patch(f"/api/entries/{e['id']}", json={"body": "x"})
        return {"first": r.status_code, "second": (r2.status_code, str(r2.json().get("detail"))[:50])}
    finally: close(c)
run("F_entry_move_fail", exp_entry_move_fail)

# G. backup partial write
def exp_backup_partial():
    c, vault = fresh_client()
    try:
        from app.services import backup as b
        from app import deps
        bdir = Path(tempfile.mkdtemp(prefix="bk-"))
        c.put("/api/settings", json={"backup_dir": str(bdir)})
        import pathlib
        orig = pathlib.Path.write_bytes
        def partial(self, data):
            with open(self, "wb") as h: h.write(data[: len(data)//2])
            raise OSError(28, "No space left on device")
        pathlib.Path.write_bytes = partial
        try:
            r = c.post("/api/settings/backup/run")
        finally:
            pathlib.Path.write_bytes = orig
        files = sorted(x.name for x in bdir.iterdir())
        import zipfile
        valid = [zipfile.is_zipfile(bdir / f) for f in files]
        return {"run": (r.status_code, r.json().get("detail", "")[:60]), "files_left": files, "valid_zip": valid, "due_now": b.due(), "status_count": b.status()["count"]}
    finally: close(c)
run("G_backup_partial", exp_backup_partial)

# H. renumber partial failure -> refs broken
def exp_renumber_partial():
    c, vault = fresh_client()
    try:
        from app.vault import paths
        from app.services import renumber
        a = c.post("/api/projects", json={"title": "A 과제"}).json()
        b = c.post("/api/projects", json={"title": "B 과제", "predecessors": [a["id"]]}).json()
        orig = paths.move
        calls = {"n": 0}
        def flaky(s, t):
            calls["n"] += 1
            if calls["n"] == 2: raise paths.FileInUseError("busy")
            return orig(s, t)
        paths.move = flaky
        try:
            r1 = c.post("/api/settings/project-code/renumber", json={"code": "X"})
        finally:
            paths.move = orig
        r2 = c.post("/api/settings/project-code/renumber", json={"code": "X"})
        projects = c.get("/api/projects").json()
        return {"first": (r1.status_code, r1.json().get("detail","")[:40]), "second": (r2.status_code, r2.text[:200]),
                "projects": [(p["id"], p["predecessors"], p.get("stage")) for p in projects],
                "dirs": sorted(x.name for x in (vault/"projects").iterdir()),
                "lineage_B": c.get(f"/api/projects/{[p['id'] for p in projects if p['title']=='B 과제'][0]}").json()["lineage"]["stages"]}
    finally: close(c)
run("H_renumber_partial", exp_renumber_partial)

# I. dedup attachment across entries
def exp_dedup():
    c, vault = fresh_client()
    try:
        p = c.post("/api/projects", json={"title": "중복"}).json()
        e1 = c.post(f"/api/projects/{p['id']}/entries", json={"title": "하나", "date": "2026-01-05"}).json()
        e2 = c.post(f"/api/projects/{p['id']}/entries", json={"title": "둘", "date": "2026-01-06"}).json()
        c.post(f"/api/entries/{e1['id']}/attachments", files={"file": ("doc.txt", b"same content", "text/plain")})
        r = c.post(f"/api/entries/{e2['id']}/attachments", files={"file": ("doc.txt", b"same content", "text/plain")})
        l2 = c.get(f"/api/entries/{e2['id']}/attachments").json()
        return {"second_upload": (r.status_code, r.json().get("deduplicated"), r.json().get("entry_id")), "entry2_attachments": len(l2)}
    finally: close(c)
run("I_dedup_other_entry", exp_dedup)

# J. demote fails at archive -> retry duplicates intake
def exp_demote_dup():
    c, vault = fresh_client()
    try:
        from app.vault import paths
        p = c.post("/api/projects", json={"title": "되돌릴 과제", "type": "smart"}).json()
        c.post(f"/api/projects/{p['id']}/entries", json={"title": "기록", "body": "x"})
        orig = paths.move
        def boom(s, t):
            if Path(s).name.startswith(p["id"]): raise paths.FileInUseError("busy")
            return orig(s, t)
        paths.move = boom
        try:
            r1 = c.post(f"/api/projects/{p['id']}/to-intake")
        finally:
            paths.move = orig
        r2 = c.post(f"/api/projects/{p['id']}/to-intake")
        intakes = c.get("/api/intakes").json()["items"]
        return {"first": (r1.status_code, r1.json().get("detail","")[:40]), "second": r2.status_code, "intakes": [(i["id"], i["title"]) for i in intakes]}
    finally: close(c)
run("J_demote_dup", exp_demote_dup)

# K. os.replace PermissionError on md.save -> status?
def exp_save_perm():
    c, vault = fresh_client()
    try:
        from app.vault import markdown as md
        p = c.post("/api/projects", json={"title": "잠긴 파일"}).json()
        orig = md.os.replace
        def boom(a, b): raise PermissionError(13, "[WinError 32] used by another process")
        md.os.replace = boom
        try:
            r = c.patch(f"/api/projects/{p['id']}", json={"status": "done"})
        finally:
            md.os.replace = orig
        return {"patch": r.status_code}
    finally: close(c)
run("K_save_permission", exp_save_perm)

# L. frontmatter + BOM pure
def exp_fm():
    import frontmatter
    post = frontmatter.loads("﻿---\ntitle: x\n---\nbody")
    return {"meta": post.metadata, "content_head": post.content[:30]}
run("L_frontmatter_bom", exp_fm)

import sys as _s
only = set(_s.argv[1:])
for k, v in results.items():
    if only and k.split("_")[0] not in only: continue
    print(f"\n### {k}\n{v}")
