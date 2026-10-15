from harness import *
import threading, time, collections

with fresh() as (c, vault):
    stop = time.time() + 5
    stats = collections.Counter(); errs = []; lock = threading.Lock()
    def worker(n):
        local_ids = []
        while time.time() < stop:
            r = c.post("/api/projects", json={"title": f"동시 과제 {n}", "owners": [f"사람{n}"], "tags": [f"t{n}"]})
            with lock: stats[("create", r.status_code)] += 1
            if r.status_code != 201:
                with lock: errs.append(("create", r.status_code, r.text[:120])); continue
            pid = r.json()["id"]; local_ids.append(pid)
            for i in range(2):
                e = c.post(f"/api/projects/{pid}/entries", json={"title": f"일지 {i}", "date": f"2026-03-{i+1:02d}", "body": f"내용 {n}-{i}"})
                with lock: stats[("entry", e.status_code)] += 1
                if e.status_code != 201:
                    with lock: errs.append(("entry", e.status_code, e.text[:120]))
            p = c.patch(f"/api/projects/{pid}", json={"status": "done"})
            with lock: stats[("patch", p.status_code)] += 1
            if p.status_code != 200:
                with lock: errs.append(("patch", p.status_code, p.text[:120]))
            g = c.get("/api/home")
            with lock: stats[("home", g.status_code)] += 1
            if g.status_code != 200:
                with lock: errs.append(("home", g.status_code, g.text[:120]))
    ts = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    [t.start() for t in ts]; [t.join() for t in ts]
    print("stats:", dict(stats)); print("errs:", errs[:10])
    rec("concurrency", "8 threads x 5s create/entries/patch/home", 200, "ok" if not errs else "PROBLEM", f"stats={dict(stats)} errs={errs[:5]}", "⛔")
    api = c.get("/api/projects").json(); ids = [p["id"] for p in api]; fs = project_dirs(vault)
    rec("concurrency", "unique ids", 200, "ok" if len(ids) == len(set(ids)) else "PROBLEM", f"n={len(ids)} unique={len(set(ids))}", "⛔")
    rec("concurrency", "api count == folders", 200, "ok" if len(ids) == len(fs) else "PROBLEM", f"api={len(ids)} fs={len(fs)}", "🔴")
    fs_ids = [d[:8] for d in fs]
    rec("concurrency", "folder id prefixes unique", 200, "ok" if len(fs_ids) == len(set(fs_ids)) else "PROBLEM", f"dups={[i for i, n in collections.Counter(fs_ids).items() if n > 1]}", "⛔")
    n_entries_api = sum(len(c.get(f"/api/projects/{p}/entries").json()) for p in ids)
    n_entries_fs = len(list((vault / "projects").glob("*/logs/*.md")))
    rec("concurrency", "entries api == files", 200, "ok" if n_entries_api == n_entries_fs else "PROBLEM", f"api={n_entries_api} fs={n_entries_fs}", "🔴")
    ri = c.post("/api/reindex").json(); ids2 = [p["id"] for p in c.get("/api/projects").json()]
    n_entries_api2 = sum(len(c.get(f"/api/projects/{p}/entries").json()) for p in ids2)
    rec("concurrency", "reindex identical", 200, "ok" if sorted(ids2) == sorted(ids) and ri["indexed"] == len(fs) and n_entries_api2 == n_entries_api and not ri["problems"] else "PROBLEM", f"indexed={ri['indexed']} fs={len(fs)} entries={n_entries_api2} problems={ri['problems'][:3]}", "🔴")
    # all projects should be status done
    nd = [p["id"] for p in c.get("/api/projects").json() if p["status"] != "done"]
    rec("concurrency", "all patched to done", 200, "ok" if not nd else "PROBLEM", f"not done={nd[:5]}", "🔴")
    # mixed: delete + restore concurrently
    errs2 = []
    def deleter(sub):
        for pid in sub:
            r = c.post(f"/api/projects/{pid}/archive")
            if r.status_code != 204: errs2.append(("archive", pid, r.status_code, r.text[:80]))
    chunks = [ids[i::4] for i in range(4)]
    ts = [threading.Thread(target=deleter, args=(ch,)) for ch in chunks]
    [t.start() for t in ts]; [t.join() for t in ts]
    rec("concurrency", "parallel archive all", 200, "ok" if not errs2 and len(c.get("/api/projects").json()) == 0 and not project_dirs(vault) else "PROBLEM", f"errs={errs2[:3]} left_api={len(c.get('/api/projects').json())} left_fs={len(project_dirs(vault))}", "🔴")
    trash = c.get("/api/trash").json(); names = [t["trash_name"] for t in trash if t["kind"] == "project"]
    errs3 = []
    def restorer(sub):
        for tn in sub:
            r = c.post(f"/api/trash/{tn}/restore")
            if r.status_code != 200: errs3.append((tn, r.status_code, r.text[:80]))
    ts = [threading.Thread(target=restorer, args=(names[i::4],)) for i in range(4)]
    [t.start() for t in ts]; [t.join() for t in ts]
    n_api = len(c.get("/api/projects").json()); n_fs = len(project_dirs(vault))
    rec("concurrency", "parallel restore all", 200, "ok" if not errs3 and n_api == len(names) == n_fs else "PROBLEM", f"errs={errs3[:3]} api={n_api} fs={n_fs} trash={len(names)}", "🔴")
    ri = c.post("/api/reindex").json(); rec("concurrency", "reindex after restore", 200, "ok" if ri["indexed"] == n_fs and not ri["problems"] else "PROBLEM", f"{ri['indexed']} vs {n_fs} problems={ri['problems'][:3]}", "🔴")
finish("p11_concurrency")
