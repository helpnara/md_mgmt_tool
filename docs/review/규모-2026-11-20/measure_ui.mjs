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
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const ui = async (label, hash, sel, shot) => {
  const s = Date.now();
  await page.goto("about:blank");
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
await ui("홈", "#/", ".home-stat", "home");
await ui("보고대상", "#/reports", ".candidates .grid tbody tr", "reports");
await ui("보고이력", "#/history", ".report-history tbody tr", "history");
await ui("로드맵 기본", "#/roadmap", ".roadmap .summary-chip", "roadmap");
await ui("로드맵 전체 줄기", "#/roadmap?state=all", ".roadmap .summary-chip", "roadmap-all");
await ui("검색", "#/search?q=" + encodeURIComponent("측정"), ".search-results .card", "search");
await ui("팀원역량 팀역량", "#/skills?tab=team", "[data-testid=ts-summary]", "skills-team");
writeFileSync(`${OUT}/measure.json`, JSON.stringify(res, null, 1));
console.log(JSON.stringify(res, null, 1));
await browser.close(); server.kill();
