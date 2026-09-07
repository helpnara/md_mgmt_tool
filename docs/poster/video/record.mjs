import { createRequire } from "node:module";
import { mkdir, readdir, rename } from "node:fs/promises";
import { join } from "node:path";
const require = createRequire(import.meta.url);
let pw; for (const n of ["playwright","/opt/node22/lib/node_modules/playwright"]) { try { pw = require(n); break; } catch {} }

const B = "http://127.0.0.1:8094";
const OUT = process.env.OUT;
const W = 1440, H = 900;

const browser = await pw.chromium.launch({ executablePath: "/opt/pw-browsers/chromium-1194/chrome-linux/chrome" });

/** 장면 하나를 따로 녹화한다. 뒤에서 자막 카드와 번갈아 붙인다. */
async function scene(name, run) {
  const dir = join(OUT, "raw", name);
  await mkdir(dir, { recursive: true });
  const ctx = await browser.newContext({
    viewport: { width: W, height: H },
    recordVideo: { dir, size: { width: W, height: H } },
  });
  const page = await ctx.newPage();
  // 마우스를 실제로 움직여 보여 준다 — 커서가 없으면 무엇을 누르는지 알 수 없다.
  await page.addStyleTag({ content: "* { scroll-behavior: smooth !important; }" }).catch(() => {});
  await run(page);
  await ctx.close();
  const files = await readdir(dir);
  const webm = files.find((f) => f.endsWith(".webm"));
  await rename(join(dir, webm), join(OUT, `${name}.webm`));
  console.log("녹화:", name);
}

const wait = (p, ms) => p.waitForTimeout(ms);

await scene("01-home", async (page) => {
  await page.goto(B + "/#/", { waitUntil: "networkidle" });
  await wait(page, 1600);
  await page.mouse.move(700, 300, { steps: 20 });
  await wait(page, 800);
  await page.evaluate(() => window.scrollTo({ top: 620, behavior: "smooth" }));
  await wait(page, 2600);
  await page.evaluate(() => window.scrollTo({ top: 1400, behavior: "smooth" }));
  await wait(page, 2400);
});

await scene("02-candidates", async (page) => {
  await page.goto(B + "/#/reports", { waitUntil: "networkidle" });
  await wait(page, 1800);
  const row = page.locator(".grid tbody tr").first();
  await row.hover();
  await wait(page, 1200);
  await page.evaluate(() => window.scrollTo({ top: 300, behavior: "smooth" }));
  await wait(page, 2200);
});

await scene("03-draft", async (page) => {
  await page.goto(B + "/#/projects/2026-001", { waitUntil: "networkidle" });
  await wait(page, 1500);
  await page.evaluate(() => window.scrollTo({ top: 480, behavior: "smooth" }));
  await wait(page, 1400);
  const button = page.getByRole("button", { name: "보고 초안 만들기" });
  await button.scrollIntoViewIfNeeded();
  await button.hover();
  await wait(page, 900);
  await button.click();
  await wait(page, 3200);
});

await scene("04-history", async (page) => {
  await page.goto(B + "/#/history", { waitUntil: "networkidle" });
  await wait(page, 2000);
  await page.evaluate(() => window.scrollTo({ top: 260, behavior: "smooth" }));
  await wait(page, 2600);
});

await scene("05-skills", async (page) => {
  await page.goto(B + "/#/skills", { waitUntil: "networkidle" });
  await wait(page, 1800);
  await page.evaluate(() => window.scrollTo({ top: 520, behavior: "smooth" }));
  await wait(page, 2600);
});

await browser.close();
