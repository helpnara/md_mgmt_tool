/**
 * 화면 자동 시험 (T50 · T51).
 *
 * 백엔드는 시험 200건 남짓으로 지켜지는데 **화면은 0건이었다.** 대시보드 칩 글자색이
 * 안 보이던 결함(TODO 25)이 정확히 그 틈으로 샜다 — 숫자는 다 맞았고, 눈으로 봐야만
 * 알 수 있는 문제였다. 그래서 기계가 대신 보게 한다.
 *
 * 보는 것은 셋뿐이다. 화면을 픽셀 단위로 굳히지 않는다 — 그러면 색 하나 바꿀 때마다
 * 시험이 깨져서 아무도 안 돌리게 된다.
 *
 *   1. 주요 화면이 **오류 없이 열리는가**
 *   2. 눌렀을 때 **기대한 것이 나오는가** (대시보드 수 = 목록 수 같은 약속)
 *   3. **글자가 읽히는가** — 선택·마우스올림 상태까지 (T51)
 *
 * 실행:  node tests/ui/screens.mjs
 * 준비물: playwright (전역 설치면 된다), 그리고 이 저장소의 .venv
 */
import { createRequire } from "node:module";
import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { CONTRAST_HELPERS, AA, AA_LARGE } from "./contrast.mjs";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const PORT = Number(process.env.UI_TEST_PORT || 8765);
const BASE = `http://127.0.0.1:${PORT}`;

/** playwright 는 이 저장소의 의존성이 아니다 (사용자 PC 에는 Node 자체가 없다). */
function loadPlaywright() {
  const require = createRequire(import.meta.url);
  const candidates = [
    "playwright",
    process.env.PLAYWRIGHT_PATH,
    "/opt/node22/lib/node_modules/playwright",
    "/usr/lib/node_modules/playwright",
  ].filter(Boolean);
  for (const name of candidates) {
    try {
      return require(name);
    } catch {
      /* 다음 후보 */
    }
  }
  console.error("playwright 를 찾지 못했습니다. `npm i -g playwright` 후 다시 실행하세요.");
  process.exit(2);
}

// ── 아주 작은 시험 틀 ────────────────────────────────────────────────────────
// 틀을 들여오면 설치할 것이 늘어난다. 필요한 것은 "무엇이 왜 틀렸나" 뿐이다.
const results = [];
let current = "";

async function check(name, fn) {
  current = name;
  try {
    await fn();
    results.push({ name, ok: true });
    console.log(`  ✓ ${name}`);
  } catch (err) {
    results.push({ name, ok: false, reason: err.message });
    console.log(`  ✗ ${name}\n      ${err.message}`);
  }
}

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

function equal(actual, wanted, message) {
  if (actual !== wanted) throw new Error(`${message} — 기대 ${wanted}, 실제 ${actual}`);
}

// ── 서버 띄우기 ──────────────────────────────────────────────────────────────
async function startServer(vault) {
  const server = spawn(
    join(REPO, ".venv/bin/python"),
    ["-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--port", String(PORT)],
    { cwd: REPO, env: { ...process.env, MD_MGMT_VAULT: vault }, stdio: "pipe" },
  );
  const logs = [];
  server.stdout.on("data", (chunk) => logs.push(String(chunk)));
  server.stderr.on("data", (chunk) => logs.push(String(chunk)));

  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      const response = await fetch(`${BASE}/api/meta`);
      if (response.ok) return { server, logs };
    } catch {
      /* 아직 안 떴다 */
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  console.error("서버가 뜨지 않았습니다:\n" + logs.join(""));
  server.kill();
  process.exit(2);
}

const api = {
  async post(path, body) {
    const response = await fetch(BASE + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body ?? {}),
    });
    if (!response.ok) throw new Error(`${path} → ${response.status} ${await response.text()}`);
    return response.json();
  },
  async patch(path, body) {
    const response = await fetch(BASE + path, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) throw new Error(`${path} → ${response.status}`);
    return response.json();
  },
  get: async (path) => (await fetch(BASE + path)).json(),
};

/** 화면이 비어 있으면 볼 것이 없다. 실제로 쓰는 모양에 가깝게 채운다. */
async function seed() {
  const a = await api.post("/api/projects", {
    title: "고강도 소재 개발", status: "in_progress", type: "rnd",
    owners: ["권경락"], due_date: "2026-08-20", effect_expected: 3.5,
  });
  const b = await api.post("/api/projects", {
    title: "공정 자동화", status: "reviewing", type: "smart", owners: ["김현우", "권경락"],
  });
  await api.post("/api/projects", { title: "예정 과제", status: "planned" });
  await api.post("/api/projects", { title: "끝난 과제", status: "done", owners: ["김현우"] });

  await api.post(`/api/projects/${a.id}/entries`, {
    date: "2026-08-20", title: "1차 시제품", body: "## 내용\n\n시제품 1차 제작\n",
  });
  await api.post(`/api/projects/${a.id}/entries`, {
    date: "2026-08-27", title: "측정", body: "## 내용\n\n인장강도 측정\n",
  });

  const first = await api.post(`/api/projects/${a.id}/reports/draft`, {
    report_date: "2026-08-25", audience: "전사 주요업무 보고",
  });
  await api.patch(`/api/reports/${first.id}`, {
    body: "## 보고 요약\n\n- 시제품 1차 제작 완료\n- 협력사 미팅\n\n## 다음 계획\n\n2차 착수\n",
  });
  await api.post(`/api/reports/${first.id}/freeze`);

  const second = await api.post(`/api/projects/${a.id}/reports/draft`, {
    report_date: "2026-09-08", audience: "전사 주요업무 보고",
  });
  await api.patch(`/api/reports/${second.id}`, {
    body: "## 보고 요약\n\n- 시제품 2차 제작 완료\n- 협력사 미팅\n\n## 다음 계획\n\n양산성 검토\n",
  });
  await api.post(`/api/projects/${b.id}/reports/draft`, {
    report_date: "2026-09-01", audience: "팀 주간회의",
  });
  return { projectA: a.id, projectB: b.id, draft: second.id };
}

// ── 본 시험 ──────────────────────────────────────────────────────────────────
async function main() {
  const vault = await mkdtemp(join(tmpdir(), "md-mgmt-ui-"));
  const { server } = await startServer(vault);
  const { chromium } = loadPlaywright();
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || "/opt/pw-browsers/chromium",
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  // 화면에서 난 오류는 소리 없이 사라진다. 전부 모아 두었다가 시험 끝에 따진다.
  const pageErrors = [];
  page.on("console", (message) => message.type() === "error" && pageErrors.push(message.text()));
  page.on("pageerror", (err) => pageErrors.push(String(err)));
  page.on("dialog", (dialog) => dialog.accept());
  await page.addInitScript(CONTRAST_HELPERS);

  const seeded = await seed();

  async function go(hash) {
    // 이미 그 주소에 있으면 goto 는 아무것도 하지 않는다(같은 문서 안 이동).
    // 그러면 화면이 다시 그려지지 않아, 방금 만든 자료가 없는 것처럼 보인다.
    if (page.url() === BASE + "/" + hash || page.url() === BASE + hash) {
      await page.reload({ waitUntil: "networkidle" });
    } else {
      await page.goto(BASE + hash, { waitUntil: "networkidle" });
    }
    await page.waitForTimeout(350);
  }

  /** 요소 하나의 명암비. state 는 마우스올림 같은 상태를 만들어 두고 잰다. */
  async function contrastOf(selector, { hover = false } = {}) {
    const element = page.locator(selector).first();
    await element.scrollIntoViewIfNeeded();
    if (hover) await element.hover();
    await page.waitForTimeout(120);
    const value = await element.evaluate((el) => __contrast(el));
    expect(value !== null, `${selector} 의 색을 읽지 못했습니다`);
    return value;
  }

  console.log("\n[1] 주요 화면이 오류 없이 열리는가");

  const screens = [
    ["과제 목록", "#/", ".grid"],
    ["과제 상세", `#/projects/${seeded.projectA}`, ".project-detail, .detail-columns"],
    ["보고 대상", "#/reports", ".candidates .grid"],
    ["보고 이력", "#/history", ".history-list"],
    ["설정", "#/settings", ".card"],
    ["검색 결과", "#/search?q=시제품", ".search-results, .card"],
  ];
  for (const [label, hash, selector] of screens) {
    await check(`${label} 화면이 열린다`, async () => {
      const before = pageErrors.length;
      await go(hash);
      expect(await page.locator(selector).count() > 0, `${selector} 가 없습니다`);
      equal(pageErrors.length, before, `${label} 에서 화면 오류가 났습니다: ${pageErrors.slice(before)}`);
    });
  }

  console.log("\n[2] 눌렀을 때 기대한 것이 나오는가");

  await check("대시보드의 수와 목록이 거른 수가 같다", async () => {
    await go("#/");
    const chips = await page.locator(".dash-chip:not(.more)").all();
    expect(chips.length > 0, "대시보드 칩이 없습니다");
    for (const chip of chips.slice(0, 6)) {
      const label = (await chip.innerText()).trim();
      const counted = Number(await chip.locator("b").innerText());
      await chip.click();
      await page.waitForTimeout(450);
      const listed = await page.locator(".grid tbody tr:not(.empty-row)").count();
      equal(listed, counted, `"${label}" 을 눌렀을 때 나오는 과제 수`);
      await chip.click(); // 해제
      await page.waitForTimeout(300);
    }
  });

  await check("보고 이력을 피보고자로 거른다", async () => {
    await go("#/history");
    const all = await page.locator(".history-list li").count();
    await page.fill(".history-filters input[list]", "주간");
    await page.waitForTimeout(600);
    const some = await page.locator(".history-list li").count();
    expect(some > 0 && some < all, `거르기가 듣지 않았습니다 (전체 ${all}, 거른 뒤 ${some})`);
  });

  await check("보고 문서에서 지난 보고 대비 변경분이 나온다", async () => {
    await go(`#/projects/${seeded.projectA}?report=${seeded.draft}`);
    await page.getByRole("button", { name: "지난 보고 대비" }).click();
    await page.waitForTimeout(600);
    expect(await page.locator(".diff-add").count() > 0, "추가된 줄이 없습니다");
    expect(await page.locator(".diff-del").count() > 0, "삭제된 줄이 없습니다");
  });

  await check("과제 번호 일괄 변경 미리보기가 바뀔 목록을 보여 준다", async () => {
    await go("#/settings");
    await page.fill('input[placeholder^="예: 소재"]', "소재");
    await page.getByRole("button", { name: "기존 과제 번호도 맞추기…" }).click();
    await page.waitForTimeout(600);
    const rows = await page.locator(".renumber-list li").count();
    equal(rows, 4, "바뀔 과제 수");
    // 미리보기는 파일을 건드리지 않는다.
    const projects = await api.get("/api/projects");
    expect(projects.every((item) => !item.id.includes("소재")), "미리보기가 실제로 번호를 바꿨습니다");
  });

  await check("실패한 동작이 설정의 [최근 오류]에 남는다", async () => {
    await fetch(`${BASE}/api/settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_code: "12" }), // 숫자만 → 거절
    });
    await go("#/settings");
    const rows = await page.locator(".error-list li").count();
    expect(rows > 0, "오류가 기록되지 않았습니다");
    const text = await page.locator(".error-list li").first().innerText();
    expect(text.includes("/api/settings"), `무슨 동작이었는지 안 보입니다: ${text}`);
  });

  console.log("\n[3] 글자가 읽히는가 (WCAG AA)");

  await check("대시보드 칩 — 기본·마우스올림·선택·선택+올림 모두 읽힌다", async () => {
    await go("#/");
    // TODO 25 가 난 바로 그 조합이다. 네 상태를 모두 본다.
    for (const [kind, selector] of [
      ["상태 칩", ".dash-chips .dash-chip:not(.type):not(.more)"],
      ["속성 칩", ".dash-chip.type"],
    ]) {
      const chip = page.locator(selector).first();
      const plain = await contrastOf(selector);
      expect(plain >= AA, `${kind} 기본 상태 ${plain} < ${AA}`);

      const hovered = await contrastOf(selector, { hover: true });
      expect(hovered >= AA, `${kind} 마우스올림 ${hovered} < ${AA}`);

      await chip.click();
      await page.waitForTimeout(350);
      await page.mouse.move(0, 0);
      const selected = await contrastOf(selector);
      expect(selected >= AA, `${kind} 선택 상태 ${selected} < ${AA}`);

      const selectedHover = await contrastOf(selector, { hover: true });
      expect(selectedHover >= AA, `${kind} 선택+마우스올림 ${selectedHover} < ${AA}`);

      await chip.click();
      await page.waitForTimeout(300);
      await page.mouse.move(0, 0);
    }
  });

  await check("보고 리마인더 배너의 글자가 읽힌다", async () => {
    await go("#/");
    // 배너는 월·화에만 뜬다. 요일에 따라 시험이 되었다 말았다 하면 안 되므로
    // 같은 클래스로 만든 요소를 넣어 색만 잰다.
    await page.evaluate(() => {
      for (const phase of ["select", "report"]) {
        const box = document.createElement("div");
        box.className = `report-reminder ${phase} probe-${phase}`;
        box.innerHTML =
          '<span class="reminder-mark">오늘 보고</span>' +
          '<span class="reminder-text">보고할 진행이 쌓인 과제 3건</span>' +
          '<a class="reminder-go" href="#/reports">보고 대상 보기</a>';
        document.querySelector("main").prepend(box);
      }
    });
    for (const phase of ["select", "report"]) {
      for (const [part, selector] of [
        ["표식", `.probe-${phase} .reminder-mark`],
        ["본문", `.probe-${phase} .reminder-text`],
        ["링크", `.probe-${phase} .reminder-go`],
      ]) {
        const value = await contrastOf(selector);
        expect(value >= AA, `${phase} 배너 ${part} ${value} < ${AA}`);
      }
    }
  });

  await check("변경분의 추가·삭제 줄이 읽힌다", async () => {
    await go(`#/projects/${seeded.projectA}?report=${seeded.draft}`);
    await page.getByRole("button", { name: "지난 보고 대비" }).click();
    await page.waitForTimeout(600);
    for (const [label, selector] of [["추가", ".diff-add"], ["삭제", ".diff-del"], ["같음", ".diff-same"]]) {
      const value = await contrastOf(`${selector} .diff-text`);
      expect(value >= AA, `변경분 ${label} 줄 ${value} < ${AA}`);
    }
  });

  await check("보고 이력·오류 기록의 글자가 읽힌다", async () => {
    await go("#/history");
    for (const [label, selector] of [
      ["날짜", ".history-date"],
      ["과제", ".history-project"],
      ["발췌", ".history-excerpt"],
      ["보고처", ".history-audience"],
    ]) {
      const value = await contrastOf(selector);
      expect(value >= AA, `보고 이력 ${label} ${value} < ${AA}`);
    }
    await go("#/settings");
    for (const [label, selector] of [
      ["상태 표식", ".error-status"],
      ["동작", ".error-action"],
      ["직전 동작", ".error-trail"],
    ]) {
      const value = await contrastOf(selector);
      expect(value >= AA, `최근 오류 ${label} ${value} < ${AA}`);
    }
  });

  await check("표의 흐린 글자도 최소 기준은 넘는다", async () => {
    await go("#/reports");
    for (const [label, selector] of [
      ["보고처 링크", ".audience-link"],
      ["보고 경과", ".due"],
      ["과제 번호", ".project-id"],
    ]) {
      const value = await contrastOf(selector);
      expect(value >= AA_LARGE, `${label} ${value} < ${AA_LARGE}`);
    }
  });

  console.log("\n[4] 화면 오류가 하나도 없었는가");
  await check("전체를 도는 동안 화면 오류가 없다", () => {
    equal(pageErrors.length, 0, `화면 오류: ${JSON.stringify(pageErrors.slice(0, 5), null, 1)}`);
  });

  await browser.close();
  server.kill();
  await rm(vault, { recursive: true, force: true });

  const failed = results.filter((item) => !item.ok);
  console.log(`\n${results.length - failed.length}건 통과, ${failed.length}건 실패`);
  if (failed.length > 0) {
    for (const item of failed) console.log(`  ✗ ${item.name}\n      ${item.reason}`);
    process.exit(1);
  }
}

main().catch((err) => {
  console.error(`\n시험을 마치지 못했습니다 (${current}):\n`, err);
  process.exit(2);
});
