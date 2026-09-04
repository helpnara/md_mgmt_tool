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
  // 진행일지가 쌓여 화면이 길어진 과제 — [맨 위로]가 필요해지는 바로 그 상황이다.
  for (let day = 1; day <= 14; day += 1) {
    await api.post(`/api/projects/${a.id}/entries`, {
      date: `2026-07-${String(day).padStart(2, "0")}`,
      title: `${day}일차 진행`,
      body: "## 내용\n\n" + "설비 조건을 바꿔 가며 시험했다.\n".repeat(6),
    });
  }

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
  // 어떤 요청이 실패했는지까지 남긴다 — "404" 만으로는 어디를 봐야 할지 알 수 없다.
  page.on("response", (response) => {
    if (response.status() >= 400) pageErrors.push(`${response.status()} ${response.url()}`);
  });

  /**
   * 일부러 실패를 만드는 시험 구간. **그 구간에서 예상한 실패만** 걷어낸다.
   *
   * 감시를 통째로 끄면, 그 사이에 난 진짜 오류까지 같이 묻힌다.
   */
  async function expectingFailures(patterns, fn) {
    const before = pageErrors.length;
    await fn();
    const during = pageErrors.splice(before);
    const unexpected = during.filter(
      (text) =>
        !patterns.some((pattern) => text.includes(pattern)) &&
        !text.startsWith("Failed to load resource"),
    );
    pageErrors.push(...unexpected);
  }
  page.on("pageerror", (err) => pageErrors.push(String(err)));
  page.on("dialog", (dialog) => dialog.accept());
  await page.addInitScript(CONTRAST_HELPERS);

  const seeded = await seed();

  /**
   * 화면을 옮긴다. **사람이 링크를 누르는 것과 같은 방식**으로.
   *
   * page.goto 로 주소의 `#` 뒤만 바꾸면 주소는 바뀌는데 hashchange 가 나지 않아,
   * 화면이 예전 상태(걸어 둔 조건·정렬)를 그대로 들고 있는다. 실제 사용에서는
   * 링크를 누르므로 그런 일이 없다 — 시험도 같은 길로 다녀야 한다.
   */
  async function go(hash) {
    const onSamePage = page.url().startsWith(BASE);
    if (!onSamePage) {
      await page.goto(BASE + hash, { waitUntil: "networkidle" });
    } else if (page.url() === BASE + "/" + hash || page.url() === BASE + hash) {
      // 같은 주소면 아무 일도 안 일어난다. 자료가 바뀌었을 수 있으니 다시 읽는다.
      await page.reload({ waitUntil: "networkidle" });
    } else {
      await page.evaluate((target) => {
        window.location.hash = target.replace(/^#/, "");
      }, hash);
      await page.waitForLoadState("networkidle");
    }
    await page.waitForTimeout(400);
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

  console.log("\n[2-2] 왔던 화면으로 돌아가는가 (TODO 48)");

  /** 상세 화면의 뒤로 가기 문구. */
  const backLabel = () => page.locator(".back").first().innerText();

  await check("보고 대상에서 연 과제는 보고 대상으로 돌아간다", async () => {
    await go("#/reports");
    await page.locator(".grid tbody tr .plain-link").first().click();
    await page.waitForTimeout(700);
    equal((await backLabel()).trim(), "← 보고 대상", "뒤로 가기 문구");
    await page.locator(".back").first().click();
    await page.waitForTimeout(700);
    expect(page.url().includes("#/reports"), `보고 대상으로 안 갔습니다: ${page.url()}`);
  });

  await check("보고 이력에서 연 보고는 보고 이력으로 돌아간다", async () => {
    await go("#/history");
    await page.locator(".history-list a").first().click();
    await page.waitForTimeout(900);
    equal((await backLabel()).trim(), "← 보고 이력", "뒤로 가기 문구");
    await page.locator(".back").first().click();
    await page.waitForTimeout(700);
    expect(page.url().includes("#/history"), `보고 이력으로 안 갔습니다: ${page.url()}`);
  });

  await check("검색 결과에서 연 과제는 검색 결과로 돌아간다", async () => {
    await go("#/search?q=시제품");
    await page.locator("main a[href*='#/projects/']").first().click();
    await page.waitForTimeout(700);
    equal((await backLabel()).trim(), "← 검색 결과", "뒤로 가기 문구");
    await page.locator(".back").first().click();
    await page.waitForTimeout(700);
    expect(page.url().includes("q=") && page.url().includes("search"), `검색 결과로 안 갔습니다: ${page.url()}`);
  });

  await check("과제 목록에서 연 과제는 지금까지처럼 과제 목록으로 돌아간다", async () => {
    await go("#/");
    await page.locator(".grid tbody tr").first().click();
    await page.waitForTimeout(700);
    equal((await backLabel()).trim(), "← 과제 목록", "뒤로 가기 문구");
  });

  await check("거른 조건이 주소에 남고, 돌아왔을 때 그대로 살아난다", async () => {
    await go("#/history");
    await page.fill(".history-filters input[list]", "주간");
    await page.waitForTimeout(700);
    const filtered = await page.locator(".history-list li").count();
    expect(page.url().includes("audience="), `조건이 주소에 없습니다: ${page.url()}`);

    // 보고를 열었다가 뒤로 가기 — 조건이 살아 있어야 한다
    await page.locator(".history-list a").first().click();
    await page.waitForTimeout(900);
    await page.locator(".back").first().click();
    await page.waitForTimeout(900);
    equal(await page.locator(".history-filters input[list]").inputValue(), "주간", "되돌아온 뒤 피보고자 조건");
    equal(await page.locator(".history-list li").count(), filtered, "되돌아온 뒤 걸러진 건수");
  });

  await check("과제 목록의 조건도 주소에 남는다", async () => {
    await go("#/");
    await page.selectOption(".filters select", { index: 1 }); // 상태 하나 고르기
    await page.waitForTimeout(600);
    expect(page.url().includes("status="), `조건이 주소에 없습니다: ${page.url()}`);
  });

  await check("주소만으로도 걸러진 화면을 열 수 있다 (즐겨찾기)", async () => {
    await go("#/history?audience=" + encodeURIComponent("팀 주간회의"));
    equal(await page.locator(".history-filters input[list]").inputValue(), "팀 주간회의", "주소로 연 조건");
    expect(await page.locator(".history-list li").count() > 0, "걸러진 결과가 없습니다");
  });

  await check("상단 메뉴를 누르면 조건이 풀리고 주소도 그에 맞는다", async () => {
    // 주소가 화면을 속이면 안 된다 — #/ 인데 걸러진 채로 남아 있으면 안 된다.
    await go("#/?status=done");
    expect(await page.locator(".filters select").first().inputValue() === "done", "주소의 조건이 안 걸렸습니다");
    await page.locator("nav a[href='#/']").click();
    await page.waitForTimeout(700);
    equal(await page.locator(".filters select").first().inputValue(), "", "메뉴를 누른 뒤 상태 조건");
  });

  await check("상세 안에서 보고를 열고 닫아도 온 곳을 잃지 않는다", async () => {
    await go("#/reports");
    await page.locator(".grid tbody tr .plain-link").first().click();
    await page.waitForTimeout(700);

    const report = page.locator(".report-open").first();
    expect(await report.count() > 0, "상세에 열어 볼 보고가 없습니다 (시험 자료 문제)");
    await report.click();
    await page.waitForTimeout(800);
    expect(await page.locator(".report-editor").count() > 0, "보고가 열리지 않았습니다");

    equal((await backLabel()).trim(), "← 보고 대상", "보고를 연 뒤 뒤로 가기");
    await page.locator(".back").first().click();
    await page.waitForTimeout(700);
    expect(page.url().includes("#/reports"), `보고 대상으로 안 갔습니다: ${page.url()}`);
  });

  console.log("\n[2-3] 이번에 넣은 것 (TODO 50·51·54·55)");

  await check("주간 보고 요일을 바꾸면 보고 예정일이 따라온다", async () => {
    await go("#/settings");
    const card = page.locator(".card").filter({ hasText: "주간 보고 요일" });
    expect(await card.count() > 0, "요일 설정 칸이 없습니다");
    await card.locator("select").selectOption("4"); // 금요일
    await card.getByRole("button", { name: /저장/ }).click();
    await page.waitForTimeout(800);

    const meta = await api.get("/api/meta");
    equal(meta.report_weekday, 4, "설정에 저장된 요일");
    // 보고 대상 화면의 기본 보고 예정일이 금요일이어야 한다.
    const candidates = await api.get("/api/report-candidates");
    const day = new Date(candidates.default_report_date + "T00:00:00").getDay();
    equal(day, 5, `보고 예정일의 요일 (${candidates.default_report_date})`);

    await go("#/settings");
    await page.locator(".card").filter({ hasText: "주간 보고 요일" }).locator("select").selectOption("1");
    await page.locator(".card").filter({ hasText: "주간 보고 요일" }).getByRole("button", { name: /저장/ }).click();
    await page.waitForTimeout(700);
  });

  await check("설정 화면이 넓은 화면에서 오른쪽 여백을 쓴다", async () => {
    await page.setViewportSize({ width: 1600, height: 900 });
    await go("#/settings");
    const main = await page.locator("main").boundingBox();
    const cards = await page.locator(".settings-grid > .card").all();
    expect(cards.length > 1, "설정 카드가 격자에 들어 있지 않습니다");

    // 두 칸으로 흐르는지 — 같은 줄에 선 카드가 있어야 한다.
    const boxes = [];
    for (const card of cards) boxes.push(await card.boundingBox());
    const sameRow = boxes.some((a, i) => boxes.some((b, j) => i !== j && Math.abs(a.y - b.y) < 20));
    expect(sameRow, "카드가 여전히 한 줄에 하나씩입니다");

    // 오른쪽 끝까지 쓰는지 — 예전에는 720px 에서 끊겨 있었다.
    const rightMost = Math.max(...boxes.map((b) => b.x + b.width));
    expect(rightMost > main.x + main.width * 0.85,
      `오른쪽이 비어 있습니다 (본문 ${Math.round(main.width)}px, 카드 끝 ${Math.round(rightMost - main.x)}px)`);
    await page.setViewportSize({ width: 1440, height: 900 });
  });

  await check("좁은 화면에서는 설정이 한 줄에 하나씩 선다", async () => {
    await page.setViewportSize({ width: 900, height: 900 });
    await go("#/settings");
    const boxes = [];
    for (const card of await page.locator(".settings-grid > .card").all()) {
      boxes.push(await card.boundingBox());
    }
    const sameRow = boxes.some((a, i) => boxes.some((b, j) => i !== j && Math.abs(a.y - b.y) < 20));
    expect(!sameRow, "좁은 화면인데 두 칸으로 벌어졌습니다");
    await page.setViewportSize({ width: 1440, height: 900 });
  });

  await check("보고 편집기에서 쓰던 피보고자를 눌러 넣는다", async () => {
    await go(`#/projects/${seeded.projectA}?report=${seeded.draft}`);
    const chip = page.locator(".audience-suggest .tag-pick").first();
    expect(await chip.count() > 0, "쓰던 피보고자 칩이 없습니다");
    const name = (await chip.innerText()).trim();
    await chip.click();
    await page.waitForTimeout(300);
    equal(await page.locator(".report-meta input[list]").inputValue(), name, "눌러서 들어간 피보고자");
  });

  await check("보고 초안을 만든 자리에서 바로 지운다", async () => {
    const draft = await api.post(`/api/projects/${seeded.projectB}/reports/draft`, {
      report_date: "2026-10-06", audience: "지울 것",
    });
    await go(`#/projects/${seeded.projectB}?report=${draft.id}`);
    await page.locator(".report-editor").getByRole("button", { name: "삭제" }).click();
    await page.waitForTimeout(1200);

    const left = await api.get("/api/reports");
    expect(!left.some((row) => row.id === draft.id), "보고가 지워지지 않았습니다");
  });

  await check("확정된 보고에는 삭제가 없다", async () => {
    const rows = await api.get("/api/reports?state=frozen");
    expect(rows.length > 0, "확정된 보고가 없습니다 (시험 자료 문제)");
    await go(`#/projects/${rows[0].project_id}?report=${rows[0].id}`);
    equal(
      await page.locator(".report-editor").getByRole("button", { name: "삭제" }).count(),
      0,
      "확정된 보고 편집기의 삭제 단추 수",
    );
  });

  await check("화면을 옮기면 맨 위에서 시작한다", async () => {
    // 해시 이동은 같은 문서 안에서 일어나 스크롤이 그대로 남는다.
    // 목록을 한참 내려보다 과제를 열면 상세가 중간부터 보이던 문제.
    await go("#/");
    await page.evaluate(() => window.scrollTo(0, 1500));
    await page.waitForTimeout(300);
    await page.locator(".grid tbody tr").first().click();
    await page.waitForTimeout(800);
    equal(await page.evaluate(() => Math.round(window.scrollY)), 0, "과제를 연 뒤 스크롤 위치");
  });

  await check("보고를 지정해 열면 그 자리로 데려간다 (맨 위로 덮어쓰지 않는다)", async () => {
    await go("#/history");
    await page.locator(".history-list a").first().click();
    await page.waitForTimeout(1200);
    expect(await page.locator(".report-editor").count() > 0, "보고가 열리지 않았습니다");
    // 문서 자리로 데려가는 동작이 살아 있어야 한다 — 맨 위로 올려 버리면 안 된다.
    const box = await page.locator(".report-editor").boundingBox();
    expect(box.y < 400, `보고가 화면 안에 들어오지 않았습니다 (y=${Math.round(box.y)})`);
  });

  await check("맨 위로 단추가 내렸을 때만 나타난다", async () => {
    await go(`#/projects/${seeded.projectA}`);
    // 앞선 시험이 보고를 열어 놓았을 수 있다. 맨 위에서 시작하는지부터 맞춰 둔다.
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(300);
    equal(await page.locator(".scroll-top").count(), 0, "맨 위에서의 단추 수");

    await page.evaluate(() => window.scrollTo(0, 2000));
    await page.waitForTimeout(400);
    expect(await page.locator(".scroll-top").count() > 0, "내렸는데도 단추가 없습니다");

    await page.locator(".scroll-top").click();
    await page.waitForTimeout(900);
    equal(await page.evaluate(() => Math.round(window.scrollY)), 0, "맨 위로 간 뒤 위치");
  });

  await check("맨 위로 단추가 모든 화면에서 같은 자리에 있다", async () => {
    // 요청의 핵심이 "동일한 위치"다. 스크롤이 실제로 생기는 긴 화면들로 견준다.
    const spots = [];
    for (const hash of [`#/projects/${seeded.projectA}`, "#/settings", "#/", "#/reports", "#/history"]) {
      await go(hash);
      await page.evaluate(() => window.scrollTo(0, 4000));
      await page.waitForTimeout(400);
      const button = page.locator(".scroll-top");
      if ((await button.count()) === 0) continue; // 내용이 짧아 스크롤이 안 생기는 화면
      const box = await button.boundingBox();
      spots.push({ hash, x: Math.round(box.x), y: Math.round(box.y) });
    }
    expect(spots.length >= 2, `단추가 뜬 화면이 너무 적습니다: ${JSON.stringify(spots)}`);
    const first = spots[0];
    for (const spot of spots) {
      expect(spot.x === first.x && spot.y === first.y,
        `자리가 다릅니다: ${JSON.stringify(spots)}`);
    }
    await page.evaluate(() => window.scrollTo(0, 0));
  });

  console.log("\n[2-4] 거르기·정렬·검색 (TODO 49·52·53·57)");

  await check("보고 대상이 기본 순서로 선다 (보고 이력 없음 먼저)", async () => {
    await go("#/reports");
    const first = await page.locator(".grid tbody tr").first().innerText();
    expect(first.includes("보고 이력 없음"), `맨 위가 보고 이력 없음이 아닙니다: ${first}`);
    expect(await page.locator(".sort-note").count() > 0, "기본 순서 표시가 없습니다");
    // 점수 열은 없앴다 — 기본 순서가 더는 점수순이 아니라 쓰이지 않는 숫자가 된다.
    expect(!(await page.locator(".grid thead").innerText()).includes("점수"), "점수 열이 남아 있습니다");
  });

  await check("보고 대상을 담당자로 거른다", async () => {
    await go("#/reports");
    const all = await page.locator(".grid tbody tr").count();
    await page.selectOption(".candidates .filters select:nth-of-type(3)", "김현우");
    await page.waitForTimeout(700);
    const some = await page.locator(".grid tbody tr").count();
    expect(some > 0 && some < all, `거르기가 듣지 않았습니다 (전체 ${all}, 거른 뒤 ${some})`);
    expect(page.url().includes("owner="), `조건이 주소에 없습니다: ${page.url()}`);
    await page.getByRole("button", { name: "조건 지우기" }).click();
    await page.waitForTimeout(600);
    equal(await page.locator(".grid tbody tr").count(), all, "조건을 지운 뒤");
  });

  await check("열 이름을 누르면 그 열로 정렬되고, 다시 누르면 방향이 바뀐다", async () => {
    await go("#/reports");
    const title = () => page.locator(".grid tbody tr td:nth-child(2) .project-title").allInnerTexts();

    await page.locator(".grid thead th.sortable button", { hasText: "과제" }).click();
    await page.waitForTimeout(700);
    const up = await title();
    expect(page.url().includes("sort=title"), `정렬이 주소에 없습니다: ${page.url()}`);

    await page.locator(".grid thead th.sortable button", { hasText: "과제" }).click();
    await page.waitForTimeout(700);
    const down = await title();
    equal(down.join("|"), [...up].reverse().join("|"), "다시 눌렀을 때의 순서");
  });

  await check("[기본 순서로]를 누르면 원래 순서로 돌아간다", async () => {
    await go("#/reports");
    // 앞선 시험이 정렬을 걸어 두었을 수 있다. 화면이 "기본 순서"라고 말할 때까지 기다린다.
    await page.locator(".sort-note").waitFor({ state: "visible" });
    await page.waitForTimeout(300);
    const base = await page.locator(".grid tbody tr td:nth-child(2) .project-title").allInnerTexts();

    await page.locator(".grid thead th.sortable button", { hasText: "과제" }).click();
    await page.waitForTimeout(700);
    await page.getByRole("button", { name: "기본 순서로" }).click();
    await page.locator(".sort-note").waitFor({ state: "visible" });
    await page.waitForTimeout(400);

    equal(
      (await page.locator(".grid tbody tr td:nth-child(2) .project-title").allInnerTexts()).join("|"),
      base.join("|"),
      "기본 순서로 돌아온 뒤",
    );
    expect(!page.url().includes("sort="), `정렬이 주소에 남아 있습니다: ${page.url()}`);
  });

  await check("과제 목록도 열 이름으로 정렬된다", async () => {
    await go("#/");
    await page.locator(".grid thead th.sortable button", { hasText: "과제" }).click();
    await page.waitForTimeout(700);
    const up = await page.locator(".grid tbody tr .project-title").allInnerTexts();
    expect(page.url().includes("sort=title"), `정렬이 주소에 없습니다: ${page.url()}`);

    await page.locator(".grid thead th.sortable button", { hasText: "과제" }).click();
    await page.waitForTimeout(700);
    const down = await page.locator(".grid tbody tr .project-title").allInnerTexts();
    equal(down.join("|"), [...up].reverse().join("|"), "다시 눌렀을 때의 순서");
  });

  await check("정렬 선택 상자와 열 머리글이 같은 값을 본다", async () => {
    await go("#/");
    await page.locator(".grid thead th.sortable button", { hasText: "마감" }).click();
    await page.waitForTimeout(700);
    // 상자가 머리글을 따라와야 한다 — 둘이 따로 놀면 무엇이 이기는지 알 수 없다.
    equal(await page.locator(".filters select").last().inputValue(), "due", "정렬 상자의 값");
  });

  await check("상단 검색으로 보고를 찾는다 (피보고자)", async () => {
    await go("#/search?q=" + encodeURIComponent("주요업무"));
    const cards = await page.locator(".search-results .card h2").allInnerTexts();
    expect(cards.some((text) => text.startsWith("보고")), `보고 갈래가 없습니다: ${cards}`);
    // 눌러서 그 보고 문서로 바로 갈 수 있어야 한다.
    const link = page.locator(".search-results .card", { hasText: "보고 " }).locator("a").first();
    await link.click();
    await page.waitForTimeout(1200);
    expect(await page.locator(".report-editor").count() > 0, "보고 문서가 열리지 않았습니다");
  });

  await check("상단 검색으로 담당자와 태그도 찾는다", async () => {
    await go("#/search?q=" + encodeURIComponent("김현우"));
    expect(await page.locator(".search-results .card").count() > 0, "담당자로 찾지 못했습니다");
    const text = await page.locator(".search-results").innerText();
    expect(text.includes("공정 자동화"), `담당 과제가 안 나옵니다: ${text.slice(0, 200)}`);
  });

  await check("대시보드는 보고 대상 목록 대신 길만 열어 둔다", async () => {
    await go("#/");
    equal(await page.locator(".dash-list").count(), 0, "대시보드에 남은 보고 대상 목록");
    const link = page.locator(".dash-mini.go");
    expect(await link.count() > 0, "보고 대상으로 가는 길이 없습니다");
    await link.click();
    await page.waitForTimeout(700);
    expect(page.url().includes("#/reports"), `보고 대상으로 가지 않았습니다: ${page.url()}`);
  });

  console.log("\n[2-5] 안전망과 안내 (TODO 37-1·62·63)");

  await check("진행일지를 고치면 직전 내용이 남고, 되돌릴 수 있다", async () => {
    await go(`#/projects/${seeded.projectA}`);
    // 첫 진행일지를 고친다.
    await page.locator(".timeline .entry").first().getByRole("button", { name: "수정" }).click();
    await page.waitForTimeout(700);
    const box = page.locator(".entry-editor textarea").first();
    const before = await box.inputValue();
    await box.fill("실수로 통째로 지운 내용");
    await page.locator(".entry-editor").getByRole("button", { name: /^저장/ }).click();
    await page.waitForTimeout(1200);

    // 다시 열어 [이전 버전] 에서 되돌린다.
    await page.locator(".timeline .entry").first().getByRole("button", { name: "수정" }).click();
    await page.waitForTimeout(700);
    await page.locator(".entry-editor").getByRole("button", { name: "이전 버전" }).click();
    await page.waitForTimeout(900);
    expect(await page.locator(".version-list li").count() > 0, "남은 버전이 없습니다");

    await page.locator(".version-list").getByRole("button", { name: "내용 보기" }).first().click();
    await page.waitForTimeout(600);
    const preview = await page.locator(".version-preview").innerText();
    expect(preview.includes(before.split("\n")[0].trim() || "내용"), `미리보기가 예전 내용이 아닙니다`);

    await page.locator(".version-list").getByRole("button", { name: "되돌리기" }).first().click();
    await page.waitForTimeout(1500);
    const text = await page.locator(".timeline").innerText();
    expect(!text.includes("실수로 통째로 지운 내용"), "되돌아가지 않았습니다");
  });

  await check("같은 내용을 다시 저장해도 버전이 쌓이지 않는다", async () => {
    const path = `projects/${(await api.get(`/api/projects/${seeded.projectA}`)).dir_name}/index.md`;
    await go(`#/projects/${seeded.projectA}`);
    await page.locator(".card").filter({ hasText: "과제 개요" }).getByRole("button", { name: "수정" }).click();
    await page.waitForTimeout(600);
    const box = page.locator(".card").filter({ hasText: "과제 개요" }).locator("textarea").first();
    await box.fill("## 배경\n\n한 번 고친 개요\n");
    await page.locator(".card").filter({ hasText: "과제 개요" }).getByRole("button", { name: /^저장/ }).click();
    await page.waitForTimeout(1200);
    const once = (await api.get(`/api/versions?path=${encodeURIComponent(path)}`)).items.length;

    await page.locator(".card").filter({ hasText: "과제 개요" }).getByRole("button", { name: "수정" }).click();
    await page.waitForTimeout(600);
    await page.locator(".card").filter({ hasText: "과제 개요" }).locator("textarea").first()
      .fill("## 배경\n\n한 번 고친 개요\n");
    await page.locator(".card").filter({ hasText: "과제 개요" }).getByRole("button", { name: /^저장/ }).click();
    await page.waitForTimeout(1200);

    equal((await api.get(`/api/versions?path=${encodeURIComponent(path)}`)).items.length, once,
      "같은 내용을 다시 저장한 뒤의 버전 수");
  });

  await check("설정에 보관 현황이 보인다", async () => {
    await go("#/settings");
    const card = page.locator(".card").filter({ hasText: "이전 버전 보관" });
    expect(await card.count() > 0, "보관 현황 칸이 없습니다");
    const text = await card.innerText();
    expect(/보관본 \d+벌/.test(text), `보관본 수가 안 보입니다: ${text}`);
  });

  await check("없는 과제를 열면 번호가 바뀌었을 수 있다고 알려 준다", async () => {
    // 이 시험은 일부러 없는 과제를 연다 — 404 는 예상한 실패다.
    await expectingFailures(["2099"], async () => {
      await go("#/projects/2099-없는-999");
    });
    const text = await page.locator("main").innerText();
    expect(text.includes("찾을 수 없습니다"), `안내가 없습니다: ${text.slice(0, 150)}`);
    expect(text.includes("번호가 바뀌었거나"), "번호 변경 안내가 없습니다");
    await page.getByRole("link", { name: "과제 목록으로" }).click();
    await page.waitForTimeout(700);
    expect(await page.locator(".grid").count() > 0, "과제 목록으로 가지 않았습니다");
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
