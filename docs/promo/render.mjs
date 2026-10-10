/**
 * 느린 나이테 홍보 모션그래픽을 mp4 로 (TODO 188).
 *
 *   node docs/promo/render.mjs              # 느린나이테-소개-16x9.mp4 (1920×1080, 30fps, 소리 없음) + 표지 png
 *   node docs/promo/render.mjs --fps 24     # 가볍게
 *
 * promo.html 의 seek(t) 로 한 장씩 그려 ffmpeg 에 바로 넘긴다 — 재생 속도와 상관없이 매번 같은 영상이 나온다.
 * 준비물: ffmpeg, playwright(전역), 글꼴(fonts/ 가 없으면 npm 으로 Noto Sans KR 을 받아 채운다 — OFL).
 */
import { createRequire } from "node:module";
import { spawn, execFileSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, copyFileSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = fileURLToPath(new URL(".", import.meta.url));
const require = createRequire(import.meta.url);
const { chromium } = (() => {
  for (const name of ["playwright", process.env.PLAYWRIGHT_PATH, "/opt/node22/lib/node_modules/playwright"].filter(Boolean)) {
    try { return require(name); } catch { /* 다음 */ }
  }
  throw new Error("playwright 를 찾지 못했습니다. npm i -g playwright");
})();

const fps = Number(process.argv[process.argv.indexOf("--fps") + 1]) || 30;

// 글꼴 — 저장소에 넣지 않는다(.gitignore). 없으면 받아 온다.
const FONTS = join(HERE, "fonts");
const NEED = ["latin", "korean"].flatMap((s) => [400, 500, 700].map((w) => `noto-sans-kr-${s}-${w}-normal.woff2`));
if (!NEED.every((f) => existsSync(join(FONTS, f)))) {
  const tmp = mkdtempSync(join(tmpdir(), "font-"));
  execFileSync("npm", ["pack", "@fontsource/noto-sans-kr@5", "--silent"], { cwd: tmp });
  const tgz = readdirSync(tmp).find((f) => f.endsWith(".tgz"));
  execFileSync("tar", ["xzf", tgz], { cwd: tmp });
  mkdirSync(FONTS, { recursive: true });
  for (const f of NEED) copyFileSync(join(tmp, "package", "files", f), join(FONTS, f));
}

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
await page.goto(`file://${join(HERE, "promo.html")}`);
await page.evaluate(() => document.fonts.ready);
const duration = await page.evaluate(() => window.DURATION);

const out = join(HERE, "느린나이테-소개-16x9.mp4");
const ff = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(fps), "-c:v", "mjpeg", "-i", "-",
  "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "slow", "-movflags", "+faststart", out], { stdio: ["pipe", "inherit", "inherit"] });
const frames = Math.round(duration * fps);
for (let i = 0; i < frames; i += 1) {
  await page.evaluate((t) => window.seek(t), i / fps);
  const jpg = await page.screenshot({ type: "jpeg", quality: 94 });
  if (!ff.stdin.write(jpg)) await new Promise((r) => ff.stdin.once("drain", r));
  if (i % (fps * 5) === 0) process.stdout.write(`  ${Math.round((i / frames) * 100)}%\r`);
}
ff.stdin.end();
await new Promise((r) => ff.on("close", r));

// 표지 — 블로그 · SNS 미리보기용 (인트로가 다 그려진 때)
await page.evaluate(() => window.seek(4.0));
await page.screenshot({ path: join(HERE, "느린나이테-소개-표지.png") });
await browser.close();
console.log(`\n만들었습니다: ${out} (${frames} 장, ${duration}초)`);
