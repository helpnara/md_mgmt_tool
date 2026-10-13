"""느린 나이테 다중 읽기 부하 시험 (TODO 190 검토용).

사용자 N 명이 **동시에** 화면을 여는 것을 흉내 낸다 — 한 사람 = 첫 화면 한 번(index.html + JS + meta + home)
그리고 과제목록 · 상세 · 기록 · 보고대상 · 검색을 차례로. 지연의 p50 · p95 · 최대와 오류 수를 센다.

    python loadtest.py --base http://127.0.0.1:8095 --users 10 50 100 --rounds 2
    python loadtest.py ... --writer          # 읽는 동안 한 사람이 0.2초마다 고치고, 중간에 다시 읽기(POST /api/reindex)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import time

import httpx


async def one_user(client: httpx.AsyncClient, base: str, ids: list[str], asset: str, out: list, uid: int) -> None:
    steps = [
        ("GET", "/", None), ("GET", asset, None), ("GET", "/api/meta", None), ("GET", "/api/home?year=2026", None),
        ("GET", "/api/dashboard?year=2026", None), ("GET", "/api/projects?year=2026", None),
    ]
    pid = random.choice(ids)
    steps += [("GET", f"/api/projects/{pid}", None), ("GET", f"/api/projects/{pid}/entries", None),
              ("GET", "/api/report-candidates", None), ("GET", "/api/search?q=%EC%84%A4%EA%B3%84", None),
              ("GET", "/api/roadmap", None), ("GET", "/api/activities/summary?year=2026", None)]
    for method, path, body in steps:
        t0 = time.perf_counter()
        try:
            r = await client.request(method, base + path, json=body, timeout=60)
            ok = r.status_code < 400
            size = len(r.content)
            if path.startswith("/api/projects?") and ok:
                out.append(("count", uid, len(r.json()), 0, 0))
        except Exception as exc:  # noqa: BLE001
            ok, size = False, 0
            out.append(("err", uid, path, type(exc).__name__, 0))
        dt = (time.perf_counter() - t0) * 1000
        out.append(("req", uid, path.split("?")[0], dt, ok, size))


async def writer(client: httpx.AsyncClient, base: str, ids: list[str], stop: asyncio.Event, out: list) -> None:
    """읽는 동안 한 사람(주인)이 고친다 — 0.2초마다 과제 하나 PATCH, 중간에 한 번 다시 읽기."""
    n = 0
    while not stop.is_set():
        pid = random.choice(ids)
        t0 = time.perf_counter()
        r = await client.patch(f"{base}/api/projects/{pid}", json={"group": f"부하시험-{n}"}, timeout=60)
        out.append(("write", 0, "PATCH /api/projects/{id}", (time.perf_counter() - t0) * 1000, r.status_code < 400, 0))
        n += 1
        if n == 5:
            t0 = time.perf_counter()
            r = await client.post(f"{base}/api/reindex", timeout=120)
            out.append(("write", 0, "POST /api/reindex", (time.perf_counter() - t0) * 1000, r.status_code < 400, 0))
        await asyncio.sleep(0.2)


async def run(base: str, users: int, rounds: int, with_writer: bool) -> dict:
    async with httpx.AsyncClient(limits=httpx.Limits(max_connections=users + 5, max_keepalive_connections=users + 5)) as client:
        ids = [p["id"] for p in (await client.get(f"{base}/api/projects")).json()]
        html = (await client.get(f"{base}/")).text
        asset = "/assets/" + html.split("/assets/")[1].split('"')[0]
        out: list = []
        stop = asyncio.Event()
        w = asyncio.create_task(writer(client, base, ids, stop, out)) if with_writer else None
        wall0 = time.perf_counter()
        for _ in range(rounds):
            await asyncio.gather(*(one_user(client, base, ids, asset, out, i) for i in range(users)))
        wall = time.perf_counter() - wall0
        stop.set()
        if w:
            await w
    reqs = [o for o in out if o[0] == "req"]
    lat = sorted(o[3] for o in reqs)
    by_path: dict[str, list[float]] = {}
    for o in reqs:
        by_path.setdefault(o[2], []).append(o[3])
    counts = sorted({o[2] for o in out if o[0] == "count"})
    return {
        "users": users, "rounds": rounds, "writer": with_writer, "requests": len(reqs), "wall_s": round(wall, 1),
        "errors": sum(1 for o in reqs if not o[4]) + sum(1 for o in out if o[0] == "err"),
        "error_detail": [o[2:4] for o in out if o[0] == "err"][:5] + [(o[2], "status>=400") for o in reqs if not o[4]][:5],
        "p50_ms": round(statistics.median(lat), 1), "p95_ms": round(lat[int(len(lat) * 0.95) - 1], 1), "max_ms": round(lat[-1], 1),
        "by_path_p95": {k: round(sorted(v)[int(len(v) * 0.95) - 1], 1) for k, v in sorted(by_path.items())},
        "bytes_per_user": round(sum(o[5] for o in reqs) / (users * rounds) / 1024),
        "list_counts_seen": counts,
        "writes": [(o[2], round(o[3]), o[4]) for o in out if o[0] == "write"][:12],
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8095")
    ap.add_argument("--users", type=int, nargs="+", default=[10, 50, 100])
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--writer", action="store_true")
    a = ap.parse_args()
    for n in a.users:
        print(json.dumps(await run(a.base, n, a.rounds, a.writer), ensure_ascii=False))


asyncio.run(main())
