import os, sys, tempfile
tmp = tempfile.mkdtemp(); os.environ["MD_MGMT_VAULT"] = tmp + "/vault"; sys.path.insert(0, os.getcwd())
from app.config import get_settings; get_settings.cache_clear()
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
    pid = c.post("/api/projects", json={"title": "비오엠", "start_date": "2026-01-01", "due_date": "2026-12-31", "owners": ["홍길동"], "effect_expected": 12.5}).json()["id"]
    d = [p for p in os.listdir(tmp + "/vault/projects")][0]
    path = f"{tmp}/vault/projects/{d}/index.md"
    raw = open(path, encoding="utf-8").read()
    open(path, "w", encoding="utf-8").write("﻿" + raw)   # 메모장이 BOM 으로 저장
    print("reindex", c.post("/api/reindex").status_code, "problems:", c.get("/api/health").json().get("problems"))
    g = c.get(f"/api/projects/{pid}").json(); print("after reindex: title=", g["title"], "owners=", g["owners"], "effect=", g.get("effect_expected"))
    r = c.patch(f"/api/projects/{pid}", json={"status": "on_hold"}); print("patch", r.status_code)
    print("---- file now ----"); print(open(path, encoding="utf-8").read()[:400])
