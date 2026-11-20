// 316 · 315 — 과제 1000개 자료로 서버 · 화면 측정
import { createRequire } from "node:module";
import { spawn } from "node:child_process";
import { join } from "node:path";
import { writeFileSync } from "node:fs";
const require = createRequire(import.meta.url);
const { chromium } = require("/opt/node22/lib/node_modules/playwright");
const REPO = "/home/user/md_mgmt_tool", PORT = 8791, BASE = `http://127.0.0.1:${PORT}`, [VAULT, OUT] = process.argv.slice(2);
const env = { ...process.env, MD_MGMT_VAULT: VAULT, MD_MGMT_TODAY: "2026-11-20" };
const t0 = Date.now();
const server = spawn(join(REPO, ".venv/bin/python"), ["-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--port", String(PORT)], { cwd: REPO, env, stdio: "ignore" });
for (let i = 0; i < 600; i++) { try { const r = await fetch(`${BASE}/api/meta`); if (r.ok) break; } catch {} await new Promise((r) => setTimeout(r, 200)); }
const res = { start_ms: Date.now() - t0, api: {}, ui: {} };
const timed = async (label, path, init) => {
  const times = []; let size = 0, status = 0;
  for (let i = 0; i < 3; i++) { const s = performance.now(); const r = await fetch(BASE + path, init); const b = await r.arrayBuffer(); times.push(Math.round(performance.now() - s)); size = b.byteLength; status = r.status; }
  res.api[label] = { first_ms: times[0], warm_ms: Math.min(...times.slice(1)), kb: Math.round(size / 1024), status };
};
await timed("meta", "/api/meta");
await timed("projects 올해", "/api/projects?year=2026");
await timed("projects 전체", "/api/projects");
await timed("home", "/api/home?year=2026");
await timed("dashboard", "/api/dashboard?year=2026");
await timed("report-candidates", "/api/report-candidates");
await timed("report-month-grid", "/api/report-month-grid?year=2026");
await timed("roadmap", "/api/roadmap");
await timed("search 품질", "/api/search?q=" + encodeURIComponent("품질"));
await timed("search 측정 결과", "/api/search?q=" + encodeURIComponent("측정 결과"));
await timed("team-skills", "/api/team-skills");
await timed("person-history", "/api/person-history?name=" + encodeURIComponent("팀원가"));
await timed("project 하나", "/api/projects/2020-001");
await timed("backup estimate", "/api/backup/estimate");
{ const s = performance.now(); const r = await fetch(BASE + "/api/reindex", { method: "POST" }); await r.text(); res.api["reindex 전체"] = { ms: Math.round(performance.now() - s), status: r.status }; }
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const ui = async (label, hash, sel, shot) => {
  const s = Date.now();
  await page.goto(`${BASE}/${hash}`);
  await page.waitForSelector(sel, { timeout: 60000 }).catch(() => {});
  await page.waitForLoadState("networkidle").catch(() => {});
  const ms = Date.now() - s;
  const info = await page.evaluate(() => ({ height: document.scrollingElement.scrollHeight, rows: document.querySelectorAll("tbody tr").length, nodes: document.getElementsByTagName("*").length,
    heap: performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1048576) : null }));
  res.ui[label] = { ms, ...info, screens: Math.round(info.height / 900) };
  if (shot) await page.screenshot({ path: `${OUT}/${shot}.png` });
};
await ui("과제목록 올해", "#/projects", ".grid tbody tr", "list-year");
await ui("과제목록 전체", "#/projects?year=all", ".grid tbody tr", "list-all");
// 거르기 칸 하나 바꾸는 시간(전체 목록에서 상태 바꾸기)
{ const s = Date.now(); await page.locator(".filters select").first().selectOption({ index: 1 }).catch(() => {}); await page.waitForTimeout(50); await page.waitForLoadState("networkidle"); res.ui["과제목록 전체 거르기 한 번"] = { ms: Date.now() - s }; }
await ui("홈", "#/", ".home-head", "home");
await ui("보고대상", "#/reports", ".candidates", "reports");
await ui("보고이력", "#/history", ".report-history", "history");
await ui("로드맵 기본", "#/roadmap", ".roadmap", "roadmap");
await ui("로드맵 전체 줄기", "#/roadmap?state=all", ".roadmap", "roadmap-all");
await ui("검색", "#/search?q=" + encodeURIComponent("측정"), ".search-results", "search");
await ui("팀원역량 팀역량", "#/skills?tab=team", ".skills", null);
writeFileSync(`${OUT}/measure.json`, JSON.stringify(res, null, 1));
console.log(JSON.stringify(res, null, 1));
await browser.close(); server.kill();
