import os, sys, tempfile
tmp = tempfile.mkdtemp(); os.environ["MD_MGMT_VAULT"] = tmp + "/vault"; sys.path.insert(0, os.getcwd())
from app.config import get_settings; get_settings.cache_clear()
from fastapi.testclient import TestClient
from app.main import app
P = tmp + "/vault/projects"
with TestClient(app) as c:
    r = c.post("/api/projects", json={"title": "거절될 과제", "effect_expected": -1}); print("#3 create with bad effect:", r.status_code, "| folders:", os.listdir(P))
    r = c.post("/api/projects", json={"title": "정상", "start_date": "2026-13-01"}); pid = r.json().get("id"); print("#4 bad start_date:", r.status_code, "api start_date=", r.json().get("start_date"), "| id", pid)
    d = [x for x in os.listdir(P) if x.startswith(pid)][0]; print("   file:", [l for l in open(f"{P}/{d}/index.md", encoding="utf-8") if "start_date" in l])
    print("   reindex problems:", c.post("/api/reindex").json().get("problems"))
    e = c.post(f"/api/projects/{pid}/entries", json={"date": "2026-05-01", "title": "제목", "body": "x"}).json(); eid = e["id"]
    c.patch(f"/api/entries/{eid}", json={"title": ""})
    for i in range(3): c.patch(f"/api/entries/{eid}", json={"body": f"수정 {i}"})
    print("#5 entry files:", os.listdir(f"{P}/{d}/logs"))
    r = c.patch(f"/api/projects/{pid}", json={"title": "   "}); print("#6 blank title patch:", r.status_code, "| folders:", [x for x in os.listdir(P) if x.startswith(pid)])
