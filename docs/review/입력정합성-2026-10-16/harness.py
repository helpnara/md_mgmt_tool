import os, sys, tempfile, json, contextlib
from pathlib import Path
sys.path.insert(0, "/home/user/md_mgmt_tool/backend")

@contextlib.contextmanager
def fresh():
    tmp = tempfile.mkdtemp(prefix="cons-", dir=os.path.dirname(__file__))
    os.environ["MD_MGMT_VAULT"] = str(Path(tmp) / "vault")
    from app.config import get_settings
    get_settings.cache_clear()
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c, get_settings().vault_dir
    get_settings.cache_clear()

def show(label, r):
    try:
        body = r.json()
    except Exception:
        body = r.text[:200]
    if isinstance(body, dict):
        body = {k: body[k] for k in list(body)[:40]}
    s = json.dumps(body, ensure_ascii=False, default=str)
    print(f"[{label}] {r.status_code} {s[:400]}")
    return body

def proj(c, **kw):
    kw.setdefault("title", "과제")
    r = c.post("/api/projects", json=kw)
    return r

def find_index(vault, pid):
    for d in (vault / "projects").iterdir():
        if d.name.startswith(pid + "-") or d.name == pid:
            return d / "index.md"
