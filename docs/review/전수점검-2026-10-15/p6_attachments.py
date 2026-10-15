from harness import *
def safe(fn):
    try: return fn()
    except Exception as e:
        class R: status_code=500; text=f'EXC {type(e).__name__}: {e}'; headers={}; content=b''
        return R()

import io
from PIL import Image

def png(color="red", size=(40, 30)):
    b = io.BytesIO(); Image.new("RGB", size, color).save(b, "PNG"); return b.getvalue()

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
    pid = c.post("/api/projects", json={"title": "첨부 과제"}).json()["id"]
    eid = c.post(f"/api/projects/{pid}/entries", json={"title": "일지", "date": "2026-03-01"}).json()["id"]
    pdir = vault / "projects" / project_dirs(vault)[0]
    A = f"/api/entries/{eid}/attachments"
    def up(name, data=None, mime="image/png", path=A):
        return c.post(path, files={"file": (name, data if data is not None else png(), mime)})
    def assets(): return sorted(str(p.relative_to(pdir)) for p in pdir.rglob("*") if p.is_file() and "assets" in p.parts)
    for name in ["공백 있는 이름.png", "한글이름.png", "../x.png", "a/b.png", "..\\..\\x.png", "C:\\temp\\x.png", "x" * 200 + ".png", ".png", "", "CON.png", "nul", "a.b.c.PNG", "\u200b.png", "trailing. ", "😀.png", "\x00evil.png", "%2e%2e%2fx.png"]:
        r = up(name)
        if r.status_code == 201:
            j = r.json(); f = pdir / j["rel_path"]
            rec("attach-name", f"upload {name!r}", r, "ok" if f.exists() and f.is_relative_to(pdir) else "PROBLEM", f"rel={j['rel_path']} exists={f.exists()} url={j['url']}", "🔴")
            if f.exists():
                g = c.get(j["url"]); 
                if g.status_code != 200: rec("attach-serve", f"GET {j['url']}", g, "PROBLEM", "uploaded file not served", "🔴")
                t = safe(lambda: c.get(j["thumb_url"])) if j.get("thumb_url") else None
                if t is not None and t.status_code >= 500: rec("attach-thumb", f"GET thumb {name!r}", t, "PROBLEM", "500", "⛔")
        else: judge("attach-name", f"upload {name!r}", r)
    judge("attach-size", "zero-byte png", up("zero.png", b""), accept_2xx=True)
    r = up("zero.png", b"")
    if r.status_code == 201:
        t = safe(lambda: c.get(r.json()["thumb_url"])); judge("attach-size", "thumb of zero-byte png", t, accept_2xx=True)
        p = c.get(f"/api/attachments/{r.json()['id']}/preview"); judge("attach-size", "preview of zero-byte png", p)
    judge("attach-size", "corrupt png bytes", up("bad.png", b"\x89PNG not really" * 10), accept_2xx=True)
    r = up("bad.png", b"\x89PNG not really" * 10)
    if r.status_code == 201: judge("attach-size", "thumb of corrupt png", safe(lambda: c.get(r.json()["thumb_url"])), accept_2xx=True)
    r = up("big.bin", b"\0" * (50 * 1024 * 1024), "application/octet-stream"); judge("attach-size", "50MB upload", r, accept_2xx=True, extra=f"stored={[a for a in assets() if 'big' in a]}")
    XL = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    i1 = up('x.xlsx', b'PK\x03\x04junk', XL).json()['id']; judge("attach-size", "fake xlsx preview", safe(lambda: c.get(f"/api/attachments/{i1}/preview")))
    i2 = up('x.csv', ('a,b,c\n' * 10000).encode(), 'text/csv').json()['id']; judge("attach-size", "csv with 10000 rows preview", c.get(f"/api/attachments/{i2}/preview"), accept_2xx=True)
    i3 = up('x.xlsx', png(), XL).json()['id']; judge("attach-size", "xlsx mime but png content preview", safe(lambda: c.get(f"/api/attachments/{i3}/preview")))
    i4 = up('x.png', b'PK\x03\x04junk', 'image/png').json()['id']; judge("attach-size", "png mime but xlsx content thumb", safe(lambda: c.get(f"/api/attachments/{i4}/thumb")))
    i5 = up('real.xlsx', open('/dev/null','rb').read(), XL).json()['id']; judge("attach-size", "empty xlsx preview", safe(lambda: c.get(f"/api/attachments/{i5}/preview")))
    judge("attach-size", "svg with script", up("evil.svg", b"<svg onload='alert(1)'/>", "image/svg+xml"), accept_2xx=True)
    r = up("evil.svg", b"<svg onload='alert(1)'/>", "image/svg+xml")
    if r.status_code == 201:
        g = c.get(r.json()["url"]); rec("attach-svg", "served svg content-type", g, "note", f"ct={g.headers.get('content-type')} disp={g.headers.get('content-disposition')}")
    r = up("page.html", b"<script>alert(1)</script>", "text/html")
    if r.status_code == 201:
        g = c.get(r.json()["url"]); rec("attach-html", "served html content-type", g, "PROBLEM" if "text/html" in g.headers.get("content-type", "") and "attachment" not in g.headers.get("content-disposition", "") else "ok", f"ct={g.headers.get('content-type')} disp={g.headers.get('content-disposition')}", "🟡")
    # same filename twice
    r1 = up("same.png"); r2 = up("same.png"); r3 = up("same.png", png("blue"))
    rec("attach-dup", "same name same bytes x2, then same name diff bytes", r3, "note", f"{r1.json()['rel_path']} / {r2.json()['rel_path']} / {r3.json()['rel_path']}")
    # delete referenced
    r = up("ref.png"); j = r.json()
    c.patch(f"/api/entries/{eid}", json={"body": f"본문 {j['markdown']}"})
    judge("attach-del", "delete attachment referenced in body", c.delete(f"/api/attachments/{j['id']}"), accept_2xx=True)
    g = c.get(f"/api/entries/{eid}").json(); print("body after delete:", g["body"]); print("summary:", c.get(f"/api/projects/{pid}/attachments").json())
    lf = c.get("/api/maintenance/link-fix").json(); rec("attach-del", "link-fix sees broken link", 200, "ok" if lf["link_count"] >= 1 else "note", f"{lf}")
    judge("attach-del", "delete twice", c.delete(f"/api/attachments/{j['id']}"))
    judge("attach-del", "GET served after delete", c.get(j["url"]))
    # upload to project
    PA = f"/api/projects/{pid}/attachments"
    judge("attach-proj", "upload to project", up("개요.png", path=PA), accept_2xx=True)
    judge("attach-proj", "upload to missing project", up("x.png", path="/api/projects/2099-999/attachments"))
    judge("attach-proj", "upload to missing entry", up("x.png", path="/api/entries/99999/attachments"))
    judge("attach-proj", "upload no file field", c.post(A, data={"x": "y"}))
    judge("attach-proj", "upload two files", c.post(A, files=[("file", ("a.png", png(), "image/png")), ("file", ("b.png", png(), "image/png"))]), accept_2xx=True)
    # serve traversal variants (raw)
    dn = c.get(f"/api/projects/{pid}").json()["dir_name"]
    for raw in [f"/files/{dn}/../index.md", f"/files/{dn}/..%2Findex.md", f"/files/{dn}/%2e%2e/index.md", f"/files/{dn}/logs/2026-03-01-일지.md", f"/files/{dn}/index.md", f"/files/..%2F..%2Fsettings.json/x", f"/files/{dn}/assets%2F..%2F..%2F..%2Fsettings.json"]:
        g = c.get(raw); rec("files-traversal", f"GET {raw}", g, "PROBLEM" if g.status_code == 200 and b"vault" in g.content[:200] else ("note" if g.status_code == 200 else "ok"), f"len={len(g.content)} ct={g.headers.get('content-type')}", "🔴")
    # consistency: db attachments vs files
    summ = c.get(f"/api/projects/{pid}/attachments").json(); files = assets()
    rec("attach-consistency", "db attachments vs asset files", 200, "note", f"api={len(summ['items'])} files={len(files)} orphans={summ.get('orphans', summ.get('orphan_count'))}")
    ri = c.post("/api/reindex").json(); summ2 = c.get(f"/api/projects/{pid}/attachments").json()
    rec("attach-consistency", "after reindex", 200, "ok" if len(summ2["items"]) == len(summ["items"]) else "PROBLEM", f"before={len(summ['items'])} after={len(summ2['items'])} problems={ri['problems']}", "🔴")
    print("ASSETS:", files)
finish("p6_attachments")
