import os, sys, tempfile
tmp = tempfile.mkdtemp(); os.environ["MD_MGMT_VAULT"] = tmp + "/vault"; sys.path.insert(0, os.getcwd())
from app.config import get_settings; get_settings.cache_clear()
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
    a = c.post("/api/projects", json={"title": "효과 관리 안 함", "start_date": "2026-01-01", "due_date": "2026-06-30", "status": "done", "completed_at": "2026-05-01", "no_effect": True, "effect_expected": 100, "effect_verified": 50}).json()
    h = c.get("/api/home?year=2026").json()
    print("no_effect 과제만 있는데 홈 효과:", {k: v for k, v in h.items() if "effect" in k.lower()} or [k for k in h])
    b = c.post("/api/projects", json={"title": "완료일 되살아남", "start_date": "2026-01-01", "due_date": "2026-12-31", "completed_at": "2020-01-01"}).json()
    print("진행중 + 완료일 2020 저장:", b["status"], b.get("completed_at"))
    r = c.patch(f"/api/projects/{b['id']}", json={"status": "done"}).json()
    print("완료로 바꾼 뒤 완료일:", r.get("completed_at"))
    import json
    h = c.get("/api/home?year=2026").json()
    def find(o, path=""):
        if isinstance(o, dict):
            for k, v in o.items():
                if "effect" in k.lower() and isinstance(v, (int, float)): print(" ", path + k, v)
                find(v, path + k + ".")
    find(h)
