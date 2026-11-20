import { createRequire } from "node:module";
import { spawn } from "node:child_process";
import { join } from "node:path";
const require = createRequire(import.meta.url);
const { chromium } = require("/opt/node22/lib/node_modules/playwright");
const REPO = "/home/user/md_mgmt_tool", PORT = 8792, BASE = `http://127.0.0.1:${PORT}`, [VAULT, OUT] = process.argv.slice(2);
const env = { ...process.env, MD_MGMT_VAULT: VAULT, MD_MGMT_TODAY: "2026-11-20" };
const server = spawn(join(REPO, ".venv/bin/python"), ["-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--port", String(PORT)], { cwd: REPO, env, stdio: "ignore" });
for (let i = 0; i < 600; i++) { try { const r = await fetch(`${BASE}/api/meta`); if (r.ok) break; } catch {} await new Promise((r) => setTimeout(r, 200)); }
const browser = await chromium.launch();
for (const width of [1440, 1920]) {
  const page = await browser.newPage({ viewport: { width, height: 900 } });
  await page.goto(`${BASE}/#/roadmap?state=all`); await page.waitForSelector(".rm-axis", { timeout: 60000 });
  await page.evaluate(() => { const d = document.querySelector(".roadmap-warnings"); if (d) d.open = false; });
  for (const [from, to] of [[2025, 2027], [2024, 2028], [2021, 2028], [2016, 2028]]) {
    const sel = page.locator(".roadmap-range select");
    await sel.nth(0).selectOption(String(from)); await sel.nth(1).selectOption(String(to));
    await page.waitForTimeout(600);
    const info = await page.evaluate(() => { const a = document.querySelector(".rm-axis").getBoundingClientRect(); return { axis: Math.round(a.width) }; });
    const years = to - from + 1;
    console.log(width, `${years}년`, "축 폭", info.axis, "px · 한 해", Math.round(info.axis / years), "px · 한 달", (info.axis / years / 12).toFixed(1), "px");
    await page.locator(".rm-axis").scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${OUT}/rm-${width}-${years}y.png`, clip: { x: 0, y: 0, width, height: 900 } });
  }
}
await browser.close(); server.kill();
