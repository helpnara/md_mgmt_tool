"""316 — 과제 1000개 가상 데이터(지어낸 것). 사용: python gen.py <vault> <과제수> <일지수/과제>"""
import os, sys, time, random
vault, N, E = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
os.environ["MD_MGMT_VAULT"] = vault
os.environ["MD_MGMT_TODAY"] = "2026-11-20"
sys.path.insert(0, "/home/user/md_mgmt_tool/backend")
from fastapi.testclient import TestClient
from app.main import app
random.seed(7)
people = [f"팀원{c}" for c in "가나다라마바사아자차카타"]
tags = ["공정", "품질", "설비", "AI", "데이터", "MES", "원가", "안전", "에너지", "자동화"]
statuses = ["in_progress"] * 3 + ["done"] * 4 + ["hold", "dropped", "planned"]
t0 = time.time()
with TestClient(app, client=("127.0.0.1", 50000)) as c:
    c.put("/api/people", json={"people": [{"name": "팀장", "leader": True}] + [{"name": n} for n in people]})
    ids = []
    for i in range(N):
        year = 2016 + (i * 11) // N   # 2016 ~ 2026 고르게
        start = f"{year}-{random.randint(1,12):02d}-{random.randint(1,28):02d}"
        dur = random.randint(3, 30)
        due_y = year + (int(start[5:7]) + dur - 1) // 12
        due = f"{due_y}-{(int(start[5:7]) + dur - 1) % 12 + 1:02d}-15"
        status = random.choice(statuses)
        body = {"title": f"가상 과제 {i:04d} — " + random.choice(["불량 저감", "수율 개선", "예측 모델", "자동 판정", "에너지 절감", "공정 최적화"]),
                "owners": random.sample(people, random.randint(1, 3)), "status": "in_progress", "start_date": start, "due_date": due,
                "tags": random.sample(tags, 2)}
        # 줄기 — 넷 중 하나는 앞 과제를 선행으로(같은 줄기가 여러 해 이어짐)
        if ids and i % 4 == 0:
            body["predecessors"] = [ids[-random.randint(1, min(8, len(ids)))]]
        r = c.post("/api/projects", json=body)
        if r.status_code != 201:
            print("fail", r.status_code, r.text[:200]); continue
        pid = r.json()["id"]; ids.append(pid)
        for k in range(E):
            c.post(f"/api/projects/{pid}/entries", json={"date": start, "title": f"진행 {k+1}", "body": "- 측정 결과 정리\n- 다음: 현장 적용 협의\n" * 3})
        if status != "in_progress":
            c.patch(f"/api/projects/{pid}", json={"status": status, **({"completed_at": due if due < "2026-11-20" else "2026-11-01"} if status == "done" else {})})
        if (i + 1) % 100 == 0:
            print(i + 1, f"{time.time() - t0:.0f}s", flush=True)
print("done", len(ids), f"{time.time() - t0:.0f}s")
