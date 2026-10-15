from harness import *
import io, shutil
from PIL import Image
def png():
    b = io.BytesIO(); Image.new("RGB", (10, 10), "red").save(b, "PNG"); return b.getvalue()

with fresh(keep=True) as (c, vault):
    pid = c.post("/api/projects", json={"title": "퍼센트"}).json()["id"]
    eid = c.post(f"/api/projects/{pid}/entries", json={"title": "일지", "date": "2026-03-01"}).json()["id"]
    pdir = vault / "projects" / project_dirs(vault)[0]
    for name in ["100%달성.png", "a%20b.png", "50%.png", "a+b.png", "a#b.png", "a?b.png", "a&b.png"]:
        r = c.post(f"/api/entries/{eid}/attachments", files={"file": (name, png(), "image/png")})
        j = r.json(); f = pdir / j["rel_path"]
        g = c.get(j["url"])
        rec("percent", f"upload {name!r} then GET url", g, "ok" if g.status_code == 200 else "PROBLEM", f"rel={j['rel_path']} on_disk={f.exists()} url={j['url']} -> {g.status_code} {g.text[:60] if g.status_code!=200 else ''}", "🔴")
        # also via export html inline? skip
    # entry PATCH title '   ' growth
    e = c.post(f"/api/projects/{pid}/entries", json={"title": "공백", "date": "2026-04-01"}).json()
    c.patch(f"/api/entries/{e['id']}", json={"title": "   "}); c.patch(f"/api/entries/{e['id']}", json={"body": "x"}); c.patch(f"/api/entries/{e['id']}", json={"body": "y"})
    g = c.get(f"/api/entries/{e['id']}").json(); rec("entry-title", "PATCH title='   ' then 2 body patches", 200, "note", f"title={g['title']!r} rel={g['rel_path']}")
    # duplicate-id folder scenario isolated
    pid2 = c.post("/api/projects", json={"title": "원본"}).json()["id"]; dn = c.get(f"/api/projects/{pid2}").json()["dir_name"]
    c.post(f"/api/projects/{pid2}/entries", json={"title": "원본일지", "date": "2026-05-01", "body": "원본 내용"})
    src = vault / "projects" / dn
    dup = vault / "projects" / f"{pid2}-복제본"; shutil.copytree(src, dup)
    before = project_dirs(vault); print("before reindex:", before)
    r = c.post("/api/reindex"); print("reindex:", r.status_code, r.json())
    after = project_dirs(vault); print("after reindex:", after)
    g = c.get(f"/api/projects/{pid2}").json(); print("db dir_name:", g.get("dir_name"))
    rec("dup-folder", "reindex with duplicate-id folder keeps both folders", 200, "ok" if set(before) == set(after) else "PROBLEM", f"before={before} after={after} trash={[t['trash_name'] for t in c.get('/api/trash').json()]}", "⛔")
    rec("dup-folder", "db dir_name exists on disk", 200, "ok" if (vault / "projects" / g["dir_name"] / "index.md").exists() else "PROBLEM", f"dir_name={g['dir_name']} exists={(vault / 'projects' / g['dir_name']).exists()}", "⛔")
    r = c.patch(f"/api/projects/{pid2}", json={"body": "수정"}); rec("dup-folder", "PATCH project after dup reindex", r, "ok" if r.status_code == 200 else "PROBLEM", r.text[:150], "⛔")
    r = c.post(f"/api/projects/{pid2}/entries", json={"title": "새 일지", "date": "2026-05-02"}); rec("dup-folder", "POST entry after dup reindex", r, "ok" if r.status_code == 201 else "PROBLEM", r.text[:150], "⛔")
    r = c.post("/api/reindex"); print("reindex 2:", r.json()); print("after reindex 2:", project_dirs(vault)); print("db dir_name 2:", c.get(f"/api/projects/{pid2}").json().get("dir_name"))
    print("VAULT", vault)
finish("p13")
