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
import { mkdir, mkdtemp, readdir, readFile, rm, writeFile } from "node:fs/promises";
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
/** 두 번째 서버가 필요할 때가 있다 — 빈 vault 의 첫 화면을 보려면 (TODO 84). */
async function startServer(vault, port = PORT) {
  const server = spawn(
    join(REPO, ".venv/bin/python"),
    ["-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--port", String(port)],
    { cwd: REPO, env: { ...process.env, MD_MGMT_VAULT: vault }, stdio: "pipe" },
  );
  const logs = [];
  server.stdout.on("data", (chunk) => logs.push(String(chunk)));
  server.stderr.on("data", (chunk) => logs.push(String(chunk)));

  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/api/meta`);
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
  async put(path, body) {
    const response = await fetch(BASE + path, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) throw new Error(`${path} → ${response.status}`);
    return response.json();
  },
  async delete(path) {
    const response = await fetch(BASE + path, { method: "DELETE" });
    if (!response.ok) throw new Error(`${path} → ${response.status}`);
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
  /** 주소에서 화면 이름만 (`#/reports?date=…` → `reports`). */
  function screenOf(url) {
    return (url.split("#")[1] ?? "").replace(/^\/?/, "").split("?")[0].replace(/\/$/, "");
  }

  async function go(hash) {
    const target = `${BASE}/${hash}`;
    if (!page.url().startsWith(BASE)) {
      await page.goto(target, { waitUntil: "networkidle" });
      await page.waitForTimeout(400);
      return;
    }

    // **같은 화면으로 다시 오면 새로 읽는다.**
    //
    // 화면이 주소에 조건을 적어 두므로(nav.ts) `#/reports` 로 가려 해도 실제 주소는
    // `#/reports?date=…` 라 둘이 절대 같아지지 않는다. 그래서 "주소가 같으면 reload"
    // 규칙만으로는 다시 읽히지 않고, **서버 자료를 바꾼 뒤 같은 화면을 다시 열면
    // 예전 것을 보게 된다.** 실제로 이 함정에 세 번 빠졌다.
    // 화면 이름이 같으면 무조건 다시 읽어 그 틈을 없앤다.
    const sameScreen = screenOf(page.url()) === screenOf(target);
    if (page.url() !== target) {
      await page.evaluate((value) => {
        window.location.hash = value.replace(/^#/, "");
      }, hash);
      await page.waitForLoadState("networkidle");
    }
    if (sameScreen) {
      await page.reload({ waitUntil: "networkidle" });
    }
    await page.waitForTimeout(400);
  }

  /** 요소 하나의 명암비. state 는 마우스올림 같은 상태를 만들어 두고 잰다. */
  async function contrastOf(selector, { hover = false } = {}) {
    const element = page.locator(selector).first();
    await element.scrollIntoViewIfNeeded();
    // 앞선 시험이 눌러 둔 자리에 마우스가 남아 있으면 엉뚱한 줄이 hover 상태가 되어,
    // "기본 상태" 를 잰다면서 실제로는 마우스올림 색을 잰다. 먼저 치운다.
    if (!hover) await page.mouse.move(0, 0);
    if (hover) await element.hover();
    await page.waitForTimeout(120);
    const value = await element.evaluate((el) => __contrast(el));
    expect(value !== null, `${selector} 의 색을 읽지 못했습니다`);
    return value;
  }

  console.log("\n[1] 주요 화면이 오류 없이 열리는가");

  const screens = [
    ["홈", "#/", ".home"],
    ["과제 목록", "#/projects", ".grid"],
    ["과제 상세", `#/projects/${seeded.projectA}`, ".project-detail, .detail-columns"],
    ["보고 대상", "#/reports", ".candidates .grid"],
    ["보고 이력", "#/history", ".history-list"],
    ["팀원 역량", "#/skills", ".skills"],
    ["설정", "#/settings", ".card"],
    ["검색 결과", "#/search?q=시제품", ".search-results, .card"],
  ];
  for (const [label, hash, selector] of screens) {
    await check(`${label} 화면이 열린다`, async () => {
      const before = pageErrors.length;
      await go(hash);
      // 자료를 받아 그리는 화면(홈 등)은 networkidle 뒤에 한 번 더 부른다.
      // "안 그려졌다" 와 "아직 안 그려졌다" 를 시험이 헷갈리면 안 된다.
      await page.waitForSelector(selector, { timeout: 8000 }).catch(() => undefined);
      expect(await page.locator(selector).count() > 0, `${selector} 가 없습니다`);
      equal(pageErrors.length, before, `${label} 에서 화면 오류가 났습니다: ${pageErrors.slice(before)}`);
    });
  }

  console.log("\n[2] 눌렀을 때 기대한 것이 나오는가");

  await check("대시보드의 수와 목록이 거른 수가 같다", async () => {
    await go("#/projects");
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

  await check("홈의 수를 누르면 그 조건의 과제 목록으로 이어진다", async () => {
    // DESIGN 5.8 의 약속 — 이어지지 않는 수는 홈에 두지 않는다.
    await go("#/");
    const stat = page.locator(".home-team .home-stat").first();
    const counted = Number((await stat.locator("strong").innerText()).replace(/[^0-9]/g, ""));
    await stat.click();
    await page.waitForTimeout(800);
    const listed = await page.locator(".grid tbody tr:not(.empty-row)").count();
    equal(listed, counted, "홈의 과제 수와 목록에 실제로 선 줄 수");
  });

  await check("홈의 두 표가 상태 여섯 칸을 모두 세운다", async () => {
    // 줄끼리 세로로 견주는 표라, 칸이 줄마다 달라지면 비교가 안 된다 (TODO 75).
    await go("#/");
    const labels = (await api.get("/api/meta")).statuses.map((item) => item.label);
    for (const [name, selector] of [
      ["팀원별", ".home-members thead"],
      ["속성별", ".home-slice-type thead"],
      ["그룹별", ".home-slice-group thead"],
    ]) {
      const head = await page.locator(selector).innerText();
      for (const label of labels) {
        expect(head.includes(label), `${name} 표에 "${label}" 칸이 없습니다: ${head}`);
      }
    }
  });

  await check("상태 칸의 합이 그 줄의 합계와 같다", async () => {
    await go("#/");
    const count = (await api.get("/api/meta")).statuses.length;
    for (const selector of [".home-members tbody tr", ".home-slice-type tbody tr"]) {
      const row = page.locator(selector).first();
      const cells = await row.locator("td").allInnerTexts();
      // [이름, 합계, 상태 6칸, …] — 표 안의 0 은 `-` 로 선다 (TODO 158)
      const num = (text) => (text.trim() === "-" ? 0 : Number(text));
      const total = num(cells[1]);
      const sum = cells.slice(2, 2 + count).reduce((acc, text) => acc + num(text), 0);
      equal(sum, total, `${selector} 의 상태 칸 합`);
    }
  });

  await check("홈이 팀원별 성과와 담당 중복을 함께 보여 준다", async () => {
    await go("#/");
    expect(await page.locator(".home-member-table tbody tr").count() > 0, "팀원 줄이 없습니다");
    // 공동 담당 과제가 있으면 사람별 합이 팀 합계를 넘는다. 그 사실을 숨기면 안 된다.
    const text = await page.locator(".home-members").innerText();
    expect(text.includes("담당 중복 포함"), "담당 중복을 밝히는 문구가 없습니다");
  });

  await check("과제별 보고 표에서 칸을 누르면 그 보고가 열린다", async () => {
    // 홈에 있던 표를 보고 이력으로 옮겼다 — 팀이 크면 줄이 과제 수만큼 늘어난다 (TODO 79).
    await go("#/history");
    const hit = page.locator(".month-grid .month-hit").first();
    expect(await hit.count() > 0, "보고가 찍힌 칸이 없습니다");
    const label = (await hit.innerText()).trim();
    await hit.click();
    await page.waitForTimeout(900);
    expect(page.url().includes("report="), `보고를 열지 않았습니다: ${page.url()}`);
    expect(await page.locator(".report-editor, .snapshot").count() > 0, `보고가 안 열렸습니다 (${label})`);
  });

  await check("보고가 한 번도 없는 과제도 줄로 선다", async () => {
    // 한 줄이 통째로 비면 "올해 한 번도 보고하지 않은 과제" 다. 그 사실이 보여야 한다.
    await go("#/history");
    const rows = await page.locator(".month-grid tbody tr").count();
    const projects = (await api.get("/api/projects")).filter((p) => !p.no_report).length;
    expect(rows >= projects, `줄이 모자랍니다 (줄 ${rows}, 올해 과제 ${projects})`);
    expect(await page.locator(".month-grid tbody tr.quiet-row").count() > 0,
      "보고 없는 과제 줄이 없습니다");
  });

  await check("효과 금액은 둘째 자리까지 저장되고, 첫째 자리로 보인다", async () => {
    // 저장은 둘째 자리(TODO 76), 표시는 어디서나 첫째 자리(TODO 156) — 1.25 는 1.3 으로 선다.
    // 새 과제를 만들지 않는다 — 과제 수를 세는 다른 시험이 흔들린다.
    await api.patch(`/api/projects/${seeded.projectA}`, { effect_expected: 1.25 });
    equal((await api.get(`/api/projects/${seeded.projectA}`)).effect_expected, 1.25, "저장 값");
    await go("#/projects");
    const row = page.locator(".grid tbody tr").filter({ hasText: "고강도 소재 개발" }).first();
    const text = await row.innerText();
    expect(text.includes("1.3") && !text.includes("1.25"), `1.3 으로 안 보입니다: ${text}`);
    await api.patch(`/api/projects/${seeded.projectA}`, { effect_expected: 3.5 });
  });

  await check("홈이 이번 주 할 일과 팀 현황을 한 줄로 놓는다", async () => {
    // 세로로 쌓으면 오른쪽이 통째로 비고, 매일 보는 것을 보려고 스크롤해야 한다 (TODO 78).
    await page.setViewportSize({ width: 1500, height: 900 });
    await go("#/");
    const week = await page.locator(".home-top .home-week").boundingBox();
    const team = await page.locator(".home-top .home-team").boundingBox();
    expect(week !== null && team !== null, "위쪽 두 칸을 찾지 못했습니다");
    expect(team.x > week.x + week.width - 10, `나란히 서지 않았습니다: ${JSON.stringify({ week, team })}`);
    // 좁은 화면에서는 다시 한 줄씩 선다.
    await page.setViewportSize({ width: 900, height: 900 });
    await page.waitForTimeout(400);
    const narrow = await page.locator(".home-top .home-team").boundingBox();
    expect(narrow.y > week.y + 50, "좁은 화면에서 아래로 안 내려갑니다");
    await page.setViewportSize({ width: 1500, height: 900 });
  });

  await check("별도 보고 불필요 과제는 보고 대상 후보에서 빠진다", async () => {
    // 단순 현황 관리를 과제로 세운 경우. 매주 눈으로 걸러 내지 않아도 되게 한다 (TODO 80).
    // 새 과제를 만들지 않는다 — 과제 수와 보고 대상 순서를 보는 다른 시험이 흔들린다.
    await go("#/reports");
    expect((await page.locator(".grid tbody").innerText()).includes("공정 자동화"),
      "시험 자료 문제 — 공정 자동화가 후보에 없습니다");

    await api.patch(`/api/projects/${seeded.projectB}`, { no_report: true });
    await go("#/reports");
    const listed = await page.locator(".grid tbody").innerText();
    expect(!listed.includes("공정 자동화"), `후보에 남아 있습니다: ${listed}`);

    // 체크를 풀면 다시 후보로 돌아온다.
    await api.patch(`/api/projects/${seeded.projectB}`, { no_report: false });
    await go("#/reports");
    expect((await page.locator(".grid tbody").innerText()).includes("공정 자동화"),
      "체크를 풀었는데 후보로 안 돌아옵니다");
  });

  await check("과제 정보 화면에서 별도 보고 불필요를 켠다", async () => {
    await go(`#/projects/${seeded.projectB}`);
    await page.getByRole("button", { name: "과제 정보 수정" }).click();
    await page.waitForTimeout(500);
    // 체크 칸이 둘이 됐다(효과성 비대상 · 별도 보고 불필요, TODO 125) — 이름으로 집는다.
    const box = page
      .locator("label.check-label", { hasText: "별도 보고 불필요" })
      .locator("input[type=checkbox]");
    equal(await box.count(), 1, "체크 칸이 없습니다");
    await box.check();
    await page.getByRole("button", { name: "저장" }).first().click();
    await page.waitForTimeout(1000);
    equal((await api.get(`/api/projects/${seeded.projectB}`)).no_report, true, "저장된 값");
    await api.patch(`/api/projects/${seeded.projectB}`, { no_report: false });
  });

  await check("홈은 기대효과와 실증효과를 합치지 않는다", async () => {
    await go("#/");
    const text = await page.locator(".home-stat.effect").innerText();
    expect(text.includes("기대") && text.includes("실증"), `둘이 나뉘어 있지 않습니다: ${text}`);
  });

  await check("AI 요약 프롬프트에 설정의 앞뒤 글과 진행 내용이 함께 담긴다", async () => {
    // 도구가 AI 를 부르지는 않는다. 붙여넣을 글을 정확히 만들어 주는 것이 전부다 (TODO 71).
    await fetch(`${BASE}/api/settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ai_prompt_prefix: "시험용 지시문입니다.", ai_prompt_suffix: "시험용 꼬리말입니다." }),
    });
    await go(`#/projects/${seeded.projectA}?report=${seeded.draft}`);
    await page.getByRole("button", { name: "AI 요약 프롬프트" }).click();
    await page.waitForTimeout(900);
    const text = await page.locator(".ai-prompt-box").inputValue();
    expect(text.startsWith("시험용 지시문입니다."), `앞에 붙는 글이 없습니다: ${text.slice(0, 40)}`);
    expect(text.trim().endsWith("시험용 꼬리말입니다."), `뒤에 붙는 글이 없습니다: ${text.slice(-40)}`);
    expect(text.includes("--- 진행 내용 ---"), "진행 내용 구분선이 없습니다");
    // 되돌려 놓는다 — 뒤따르는 시험이 이 설정에 걸리지 않게.
    await fetch(`${BASE}/api/settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ai_prompt_prefix: "", ai_prompt_suffix: "" }),
    });
  });

  console.log("\n[2-8] 팀원 역량 이력 (TODO 72)");

  // 기본 연도가 올해이므로 기록도 오늘 날짜로 만든다 — 해가 바뀌어도 시험이 흔들리지 않는다.
  const todayStr = new Date().toISOString().slice(0, 10);

  await check("기록 단위는 사람이되, 목록에서는 한 행사가 한 줄이다", async () => {
    // 저장은 사람 수만큼이어야 집계에서 빠지는 사람이 없고 (TODO 74),
    // 화면은 행사 하나로 접혀야 "올해 몇 번 갔나"를 눈으로 셀 수 있다 (TODO 85).
    for (const name of ["권경락", "김현우", "이수민"]) {
      await api.post("/api/activities", {
        person: name, date: todayStr, kind: "expo", title: "스마트제조 박람회",
      });
    }
    equal(
      (await api.get("/api/activities")).filter((row) => row.title === "스마트제조 박람회").length,
      3,
      "저장된 기록 수",
    );
    await go("#/skills");
    const row = page.locator(".activity-list > li").filter({ hasText: "스마트제조 박람회" });
    equal(await row.count(), 1, "화면에 선 행사 줄 수");
    equal(await row.locator(".activity-person").count(), 3, "그 줄에 붙은 사람 수");
    // 고치고 지우는 일은 사람마다 따로다.
    equal(await row.locator(".activity-person-row").count(), 3, "사람마다 붙는 수정·삭제");
  });

  await check("시간·비용은 비워 두어도 되고, 채운 것만 합계에 들어간다", async () => {
    await api.post("/api/activities", {
      person: "권경락", date: todayStr, kind: "education",
      title: "열처리 공정 심화 과정", hours: 16, cost: 350000,
      takeaway: "소입 조건 설계 기준을 정리해 옴",
    });
    await go("#/skills");
    const text = await page.locator(".skills .card").first().innerText();
    // 앞서 넣은 세 건은 시간·비용이 비어 있다. 그것이 0 으로 굳으면 합계가 흔들린다.
    expect(text.includes("16h"), `교육 시간 합계가 16h 가 아닙니다: ${text}`);
    expect(text.includes("350,000원"), `비용 합계가 안 맞습니다: ${text}`);
  });

  await check("기록이 없는 사람이 면담 대상으로 먼저 뜬다", async () => {
    await api.post("/api/people", { name: "박지훈" });
    await go("#/skills");
    const quiet = await page.locator(".skills-quiet").innerText();
    expect(quiet.includes("박지훈"), `기록 없는 사람이 안 뜹니다: ${quiet}`);
  });

  await check("사람을 누르면 그 사람의 기록만 남는다", async () => {
    await go("#/skills");
    // 행사 줄은 접히므로 사람 칩 수(= 참여 기록 수)로 본다.
    const before = await page.locator(".activity-list .activity-person").count();
    await page.locator(".skills-table tbody .linkish").first().click();
    await page.waitForTimeout(800);
    const after = await page.locator(".activity-list .activity-person").count();
    expect(after > 0 && after < before, `걸러지지 않았습니다 (전체 ${before}, 거른 뒤 ${after})`);
    expect(page.url().includes("person="), `조건이 주소에 없습니다: ${page.url()}`);
  });

  await check("역량 기록을 화면에서 추가한다", async () => {
    await go("#/skills");
    await page.getByRole("button", { name: "기록 추가" }).click();
    await page.waitForTimeout(400);
    await page.fill('.activity-form input[placeholder^="예: 권경락, 김현우"]', "이수민");
    await page.fill('.activity-form input[placeholder^="예: 열처리"]', "화면에서 넣은 기록");
    await page.locator(".activity-form").getByRole("button", { name: "저장" }).click();
    await page.waitForTimeout(1200);
    const list = await page.locator(".activity-list").innerText();
    expect(list.includes("화면에서 넣은 기록"), `추가한 기록이 안 보입니다: ${list}`);
  });

  await check("여러 명을 한 번에 넣으면 사람 수만큼 나뉜다", async () => {
    // 실사용에서 "A,B" 한 덩이가 사람 하나로 굳었던 사고를 막는 자리다 (TODO 74).
    await go("#/skills");
    await page.getByRole("button", { name: "기록 추가" }).click();
    await page.waitForTimeout(400);
    await page.fill('.activity-form input[placeholder^="예: 권경락, 김현우"]', "권경락, 김현우");
    await page.fill('.activity-form input[placeholder^="예: 열처리"]', "둘이 같이 간 교육");
    // 저장 전에 무엇이 만들어질지 화면이 미리 말해 준다.
    const hint = await page.locator(".activity-form").innerText();
    expect(hint.includes("2건"), `나뉠 건수를 미리 알려 주지 않습니다: ${hint}`);
    await page.locator(".activity-form").getByRole("button", { name: /저장/ }).click();
    await page.waitForTimeout(1400);

    equal(
      (await api.get("/api/activities")).filter((row) => row.title === "둘이 같이 간 교육").length,
      2,
      "나뉜 기록 수",
    );
    const rows = page.locator(".activity-list > li").filter({ hasText: "둘이 같이 간 교육" });
    equal(await rows.count(), 1, "화면에 선 행사 줄 수");
    equal(await rows.locator(".activity-person").count(), 2, "그 줄에 붙은 사람 수");
    // 사람별 표에 "권경락, 김현우" 같은 없는 사람이 생기면 안 된다.
    const table = await page.locator(".skills-table").innerText();
    expect(!table.includes("권경락,"), `붙은 이름이 표에 남았습니다: ${table}`);
  });

  await check("명부에서 이름을 눌러 넣는다", async () => {
    await go("#/skills");
    await page.getByRole("button", { name: "기록 추가" }).click();
    await page.waitForTimeout(400);
    const chip = page.locator(".activity-form .tag-pick").first();
    const name = (await chip.innerText()).trim();
    await chip.click();
    await page.waitForTimeout(250);
    equal(
      await page.locator('.activity-form input[placeholder^="예: 권경락, 김현우"]').inputValue(),
      name,
      "명부를 눌러 넣은 이름",
    );
    await page.locator(".activity-form").getByRole("button", { name: "취소" }).click();
  });

  await check("수정 폼은 누른 기록 바로 아래에서 열린다", async () => {
    // 화면 맨 위에서 열면 방금 누른 자리가 밀려나 무엇을 고치는 중인지 알 수 없다.
    await go("#/skills");
    // 여럿이 간 행사는 사람마다 단추가 있으므로, 혼자 간 기록으로 확인한다.
    const row = page.locator(".activity-list > li").filter({ hasText: "열처리 공정 심화 과정" }).first();
    await row.getByRole("button", { name: "수정" }).click();
    await page.waitForTimeout(500);
    equal(await row.locator(".activity-form").count(), 1, "누른 줄 안에 열린 수정 폼");
    equal(await page.locator(".activity-form").count(), 1, "화면 전체의 수정 폼 수");
    await row.locator(".activity-form").getByRole("button", { name: "취소" }).click();
  });

  await check("여러 날에 걸친 교육은 기간으로 보인다", async () => {
    const twoDaysLater = new Date(Date.now() + 2 * 86400000).toISOString().slice(0, 10);
    await api.post("/api/activities", {
      person: "권경락", kind: "education", title: "사흘짜리 교육",
      date: todayStr, end_date: twoDaysLater,
    });
    await go("#/skills");
    const row = page.locator(".activity-list > li").filter({ hasText: "사흘짜리 교육" }).first();
    const text = await row.locator(".activity-date").innerText();
    expect(text.includes("~"), `기간으로 보이지 않습니다: ${text}`);
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
    await go("#/projects");
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
    await go("#/projects");
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
    // 주소가 화면을 속이면 안 된다 — #/projects 인데 걸러진 채로 남아 있으면 안 된다.
    await go("#/projects?status=done");
    expect(await page.locator(".filters select").first().inputValue() === "done", "주소의 조건이 안 걸렸습니다");
    await page.locator("nav a[href='#/projects']").click();
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
    await go("#/projects");
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
    for (const hash of [`#/projects/${seeded.projectA}`, "#/settings", "#/", "#/projects", "#/reports", "#/history", "#/skills"]) {
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
    await go("#/projects");
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
    await go("#/projects");
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
    await go("#/projects");
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

  await check("없는 폴더를 백업 위치로 적으면 그렇다고 말해 준다", async () => {
    // 오타로 엉뚱한 곳에 폴더가 생기는 것보다, 먼저 만들라고 하는 편이 안전하다.
    await go("#/settings");
    const card = page.locator(".card").filter({ hasText: "자동 백업" });
    // 일부러 거절당하는 값을 넣는다 — 400 은 예상한 실패다.
    await expectingFailures(["/api/settings"], async () => {
      await card.locator('input[placeholder^="예: D:"]').fill(`${vault}-없는폴더`);
      await card.getByRole("button", { name: /^저장/ }).click();
      await page.waitForTimeout(900);
    });
    expect((await card.innerText()).includes("없습니다"), "안내가 없습니다");
  });

  await check("백업 폴더를 정하면 실제로 파일이 생긴다", async () => {
    const folder = `${vault}-backup`;
    await mkdir(folder, { recursive: true });
    await go("#/settings");
    const card = page.locator(".card").filter({ hasText: "자동 백업" });
    expect(await card.count() > 0, "자동 백업 칸이 없습니다");

    await card.locator('input[placeholder^="예: D:"]').fill(folder);
    await card.getByRole("button", { name: /^저장/ }).click();
    await page.waitForTimeout(900);

    await card.getByRole("button", { name: "지금 백업" }).click();
    await page.waitForTimeout(1500);
    const text = await card.innerText();
    expect(text.includes("과제이력-백업-"), `백업이 안 만들어졌습니다: ${text.slice(0, 300)}`);

    const status = await api.get("/api/settings/backup/status");
    equal(status.count, 1, "백업 파일 수");
    expect(status.reachable, "백업 폴더에 닿지 못합니다");
  });

  await check("데이터 폴더 안을 백업 폴더로 잡으면 막는다", async () => {
    await go("#/settings");
    const card = page.locator(".card").filter({ hasText: "자동 백업" });
    await expectingFailures(["/api/settings"], async () => {
      await card.locator('input[placeholder^="예: D:"]').fill(`${vault}/백업`);
      await card.getByRole("button", { name: /^저장/ }).click();
      await page.waitForTimeout(900);
    });
    const text = await card.innerText();
    expect(text.includes("데이터 폴더 안") || text.includes("없습니다"),
      `막지 않았습니다: ${text.slice(0, 300)}`);
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

  console.log("\n[2-6] 보고 마커 (TODO 35)");

  await check("보고 뒤에 지난 날짜로 쓴 기록도 미보고로 보인다", async () => {
    // 선만으로는 표현할 수 없던 경우다 — 날짜순으로는 선 아래에 놓이는데 실제로는 미보고다.
    const project = seeded.projectA;
    await api.post(`/api/projects/${project}/entries`, {
      date: "2026-08-21", title: "뒤늦게 쓴 시험", body: "## 내용\n\n깜빡했던 기록\n",
    });
    await go(`#/projects/${project}`);

    const row = page.locator(".timeline .entry").filter({ hasText: "뒤늦게 쓴 시험" });
    expect(await row.count() > 0, "뒤늦게 쓴 기록이 안 보입니다");
    expect((await row.innerText()).includes("미보고"), "미보고 딱지가 없습니다");
  });

  await check("이미 보고한 기록에는 미보고 딱지가 없다", async () => {
    await go(`#/projects/${seeded.projectA}`);
    const reported = page.locator(".timeline .entry").filter({ hasText: "1차 시제품" });
    if (await reported.count() > 0) {
      expect(!(await reported.innerText()).includes("미보고"), "보고한 기록에 딱지가 붙었습니다");
    }
  });

  await check("보고가 여러 건이어도 선은 하나만 긋는다", async () => {
    // 보고마다 그으면 이력이 쌓일수록 선이 늘어 정작 경계가 안 보인다.
    await go(`#/projects/${seeded.projectA}`);
    const markers = await page.locator(".timeline .report-marker").count();
    expect(markers <= 1, `선이 ${markers}개 그어졌습니다`);
  });

  console.log("\n[2-7] 연도·검색 상한·과제 안 찾기 (TODO 66·67·68)");

  await check("첫 화면은 올해 과제만 보여 준다", async () => {
    await go("#/projects");
    const year = String(new Date().getFullYear());
    equal(await page.locator('.filters select[aria-label="연도"]').inputValue(), year, "연도 칸의 기본값");
    // 기본값은 주소에 적지 않는다 — 주소가 짧게 유지되고, 해가 바뀌면 저절로 따라간다.
    expect(!page.url().includes("year="), `기본값이 주소에 적혔습니다: ${page.url()}`);
  });

  await check("연도를 [전체]로 바꾸면 지난해 과제도 나온다", async () => {
    // 지난해 번호를 가진 과제를 만들어 둔다.
    const year = String(new Date().getFullYear());
    const before = await page.locator(".grid tbody tr").count();
    await page.locator('.filters select[aria-label="연도"]').selectOption("all");
    await page.waitForTimeout(700);
    expect(await page.locator(".grid tbody tr").count() >= before, "전체가 올해보다 적습니다");
    // [전체]는 기본값과 구분되어야 한다 — 아니면 즐겨찾기해도 올해로 돌아온다.
    expect(page.url().includes("year=all"), `[전체]가 주소에 남지 않았습니다: ${page.url()}`);
    await page.locator('.filters select[aria-label="연도"]').selectOption(year);
    await page.waitForTimeout(600);
  });

  await check("대시보드의 수가 연도를 따라간다", async () => {
    await go("#/projects");
    const chips = await page.locator(".dash-chip:not(.more)").all();
    expect(chips.length > 0, "대시보드 칩이 없습니다");
    for (const chip of chips.slice(0, 3)) {
      const counted = Number(await chip.locator("b").innerText());
      await chip.click();
      await page.waitForTimeout(500);
      equal(await page.locator(".grid tbody tr:not(.empty-row)").count(), counted, "연도가 걸린 상태의 수");
      await chip.click();
      await page.waitForTimeout(400);
    }
  });

  await check("검색이 잘리면 잘렸다고 말한다", async () => {
    // 진행일지를 상한 위로 만든다.
    const project = seeded.projectB;
    for (let n = 0; n < 45; n += 1) {
      await api.post(`/api/projects/${project}/entries`, {
        date: "2026-05-01", title: `대량 기록 ${n}`, body: "굽힘강도 시험 결과",
      });
    }
    await go("#/search?q=" + encodeURIComponent("굽힘강도"));
    const text = await page.locator(".search-results").innerText();
    expect(text.includes("이상"), `잘렸다는 표시가 없습니다: ${text.slice(0, 200)}`);
    expect(text.includes("일부만 보여 주고"), "왜 그런지 설명이 없습니다");
  });

  await check("과제 안에서 찾으면 걸린 기록만 펼쳐 보인다", async () => {
    await go(`#/projects/${seeded.projectA}`);
    const all = await page.locator(".timeline .entry").count();
    await page.fill(".entry-find", "인장강도");
    await page.waitForTimeout(500);

    const found = await page.locator(".timeline .entry").count();
    expect(found > 0 && found < all, `걸러지지 않았습니다 (전체 ${all}, 찾은 뒤 ${found})`);
    // 걸린 기록은 펼쳐져야 한다 — 접힌 채로는 왜 걸렸는지 알 수 없다.
    expect(await page.locator(".timeline .entry .markdown").count() > 0, "본문이 안 펼쳐졌습니다");
    expect((await page.locator(".timeline-head").innerText()).includes("찾은 것"), "찾은 수가 안 보입니다");
  });

  await check("과제 안에서 못 찾으면 그렇다고 말한다", async () => {
    await go(`#/projects/${seeded.projectA}`);
    await page.fill(".entry-find", "있을리없는낱말");
    await page.waitForTimeout(500);
    expect((await page.locator(".timeline").innerText()).includes("든 기록이 없습니다"), "안내가 없습니다");
  });

  console.log("\n[3] 글자가 읽히는가 (WCAG AA)");

  await check("대시보드 칩 — 기본·마우스올림·선택·선택+올림 모두 읽힌다", async () => {
    await go("#/projects");
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
    await go("#/projects");
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

  await check("이번에 새로 생긴 안내 글자도 읽힌다", async () => {
    await go("#/projects");
    // 대시보드에서 보고 대상으로 가는 길 — 연한 파랑 위의 파란 글씨라 위험한 조합이다.
    if (await page.locator(".dash-mini.go").count()) {
      const value = await contrastOf(".dash-mini.go");
      expect(value >= AA, `[보고 대상 보기] ${value} < ${AA}`);
    }
    // 연도로 걸러 숨은 과제 안내 — 화면에 없을 수 있으므로 같은 모양을 만들어 잰다.
    await page.evaluate(() => {
      const box = document.createElement("div");
      box.className = "dash-row hidden-note probe-hidden";
      box.innerHTML =
        '<span class="dash-note">2026년 밖에 있지만 <b>아직 진행 중인 과제 1건</b>이 빠져 있습니다.</span>' +
        '<button class="dash-mini go">연도 전체로 보기 →</button>';
      (document.querySelector(".dashboard") || document.querySelector("main")).prepend(box);
    });
    for (const [label, selector] of [
      ["안내 문구", ".probe-hidden .dash-note"],
      ["전체로 보기", ".probe-hidden .dash-mini.go"],
    ]) {
      const value = await contrastOf(selector);
      expect(value >= AA, `숨은 과제 ${label} ${value} < ${AA}`);
    }

    // 검색이 잘렸다는 안내
    await go("#/search?q=" + encodeURIComponent("굽힘강도"));
    if (await page.locator(".search-cut").count()) {
      const value = await contrastOf(".search-cut");
      expect(value >= AA, `검색 잘림 안내 ${value} < ${AA}`);
    }
  });

  await check("홈의 글자가 읽힌다", async () => {
    await go("#/");
    for (const [label, selector, floor] of [
      // 흐린 글자(--muted)는 이 도구 전체가 AA_LARGE 기준으로 쓰고 있다 (.project-id 와 같다).
      ["칸 제목", ".home-stat-label", AA_LARGE],
      ["안내 문구", ".home .hint", AA_LARGE],
      ["막대 눈금", ".bar-label", AA_LARGE],
    ]) {
      if (!(await page.locator(selector).count())) continue;
      const value = await contrastOf(selector);
      expect(value >= floor, `홈 ${label} ${value} < ${floor}`);
    }
    // 눌러서 이어지는 칸은 마우스를 올렸을 때가 위험하다 (연한 파랑 위 파란 글씨).
    const hovered = await contrastOf(".home-team a.home-stat strong", { hover: true });
    expect(hovered >= AA, `홈 숫자 마우스올림 ${hovered} < ${AA}`);
  });

  await check("팀원 역량 화면의 글자가 읽힌다", async () => {
    await go("#/skills");
    for (const [label, selector, floor] of [
      ["면담 대상 칩", ".skills-quiet-chip", AA],
      ["사람 이름", ".skills-table .linkish", AA],
      ["0 인 칸", ".skills-table td.zero", AA_LARGE],
      ["얻은 것", ".activity-takeaway", AA],
    ]) {
      if (!(await page.locator(selector).count())) continue;
      const value = await contrastOf(selector);
      expect(value >= floor, `역량 ${label} ${value} < ${floor}`);
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

  console.log("\n[5] 사용자 관점 점검에서 고친 것 (TODO 81~90)");

  await check("대시보드가 적은 보고 대상 수와 누른 뒤 나오는 수가 같다", async () => {
    // 화면에 세우는 줄은 상위 몇 건으로 잘리지만, 글자로 적는 수는 전체여야 한다 (TODO 82).
    await go("#/projects");
    const label = await page.locator(".dash-candidates .dash-mini").first().innerText();
    const said = Number(label.match(/(\d+)건/)[1]);
    await go("#/reports");
    const listed = await page.locator(".grid tbody tr").count();
    equal(said, listed, "대시보드가 적은 수와 보고 대상 목록의 줄 수");
  });

  await check("좁은 화면에서도 목록이 옆으로 밀리지 않는다", async () => {
    // 1366×768 에 윈도우 125% 배율이면 뷰포트가 1093px 다 — 사내 노트북의 표준 (TODO 83).
    await page.setViewportSize({ width: 1093, height: 900 });
    for (const hash of ["#/", "#/projects", "#/reports", "#/history", "#/skills", "#/settings"]) {
      await go(hash);
      const over = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      equal(over, 0, `${hash} 에서 가로로 ${over}px 넘침`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
  });

  await check("긴 vault 경로가 머리글을 무너뜨리지 않는다", async () => {
    await go("#/");
    const before = await page.evaluate(() => document.querySelector(".app-header").offsetHeight);
    await page.evaluate(() => {
      document.querySelector(".vault-path").textContent =
        "\\\\사내서버\\연구소\\소재개발팀\\권경락\\문서\\느린나이테\\vault\\2026";
    });
    const after = await page.evaluate(() => document.querySelector(".app-header").offsetHeight);
    equal(after, before, "경로가 길어지자 머리글이 줄바꿈됐다");
  });

  await check("홈이 효과 금액의 분모를 함께 적는다", async () => {
    // 화살표만 있으면 "기대 대비 달성률" 로 읽힌다 (TODO 86).
    await go("#/");
    // 완료했는데 실증효과가 없는 과제로 가는 링크도 같은 자리에 선다 (TODO 106-F) — 문구 줄만 본다.
    const note = await page.locator(".home-stat.effect span.home-stat-note").innerText();
    expect(/기대 \d+건 · 실증 \d+건/.test(note), `분모가 안 보인다: ${note}`);
  });

  await check("팀원별 표에 역량 이력 열이 있다", async () => {
    await go("#/");
    const heads = await page.locator(".home-members thead th").allInnerTexts();
    expect(heads.includes("역량 이력"), `열이 없다: ${heads.join("|")}`);
  });

  await check("홈의 그룹별 표가 세는 수와 목록이 거르는 수가 같다", async () => {
    await api.patch(`/api/projects/${seeded.projectA}`, { group: "차세대전지" });
    await api.patch(`/api/projects/${seeded.projectB}`, { group: "차세대전지" });
    await go("#/");
    const row = page.locator(".home-slice-group").locator("tbody tr").first();
    const label = await row.locator("td").first().innerText();
    const count = Number(await row.locator("td").nth(1).innerText());
    await row.locator("td a").first().click();
    await page.waitForTimeout(500);
    const listed = await page.locator(".grid tbody tr").count();
    equal(listed, count, `${label} — 표 ${count}건 / 목록 ${listed}건`);
    await api.patch(`/api/projects/${seeded.projectA}`, { group: "" });
    await api.patch(`/api/projects/${seeded.projectB}`, { group: "" });
  });

  await check("한 행사에 여러 명이 가도 목록에서는 한 줄이다", async () => {
    // 집계를 위해 기록은 사람 수만큼 만들되, 눈으로 세는 자리에서는 한 행사다 (TODO 85).
    await api.post("/api/activities", {
      date: "2026-05-21", end_date: "2026-05-23", kind: "expo",
      person: "권경락, 김현우, 박서연", title: "InterBattery 2026",
    });
    await go("#/skills");
    // 앞선 시험들이 남긴 행사도 함께 서 있으므로, **이 행사 하나**만 골라서 본다.
    const row = page.locator(".activity-list > li").filter({ hasText: "InterBattery 2026" });
    equal(await row.count(), 1, "화면에 선 행사 줄 수");
    equal(await row.locator(".activity-person").count(), 3, "그 줄에 붙은 사람 수");
    equal(await row.locator(".activity-person-row").count(), 3, "사람마다 붙는 수정·삭제");
    // 제목은 행사 수와 참여 기록 수를 **따로** 적는다. 둘이 같으면 잘못 센 것이다.
    const heading = await page.locator(".card-head h2").last().innerText();
    const events = Number(heading.match(/행사 (\d+)건/)[1]);
    const records = Number(heading.match(/참여 기록 (\d+)건/)[1]);
    expect(records > events, `참여 기록이 행사보다 많아야 한다: ${heading}`);
  });

  await check("처음 켰을 때 다음에 할 일을 알려 준다", async () => {
    // 0 이 여덟 개 늘어선 대시보드는 아무것도 알려 주지 않는다 (TODO 84).
    const empty = await mkdtemp(join(tmpdir(), "md-mgmt-ui-empty-"));
    const fresh = await startServer(empty, PORT + 1);
    const blank = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    try {
      await blank.goto(`http://127.0.0.1:${PORT + 1}/#/`, { waitUntil: "networkidle" });
      await blank.waitForSelector(".home-start", { timeout: 8000 });
      const steps = await blank.locator(".home-steps li").count();
      equal(steps, 3, "첫 실행 안내의 단계 수");
      // [과제 만들기] 를 누르면 바로 입력 칸이 열려야 한다 — 메뉴를 뒤지게 하지 않는다.
      await blank.locator(".home-step-go.primary").click();
      await blank.waitForSelector(".project-form, form input[name='title'], .card form", { timeout: 8000 });
    } finally {
      await blank.close();
      fresh.server.kill();
      await rm(empty, { recursive: true, force: true });
      await rm(`${empty}-backup`, { recursive: true, force: true });
    }
  });

  console.log("\n[6] 배너가 말한 곳으로 데려가는가 (TODO 91)");

  // 오늘을 보고일로 만들어 배너를 띄운다. (JS 는 일=0, 파이썬은 월=0)
  await api.put("/api/settings", { report_weekday: (new Date().getDay() + 6) % 7 });

  /** 그날의 열린 초안을 모두 치운다 — 시드가 만들어 둔 것이 섞이면 건수 갈래를 못 본다. */
  async function clearDrafts() {
    const { reminder } = await api.get("/api/dashboard");
    for (const item of reminder?.draft_items ?? []) await api.delete(`/api/reports/${item.id}`);
    return (await api.get("/api/dashboard")).reminder.report_date;
  }

  /** 초안을 원하는 건수만큼 만들고, 끝나면 지운다. */
  async function withDrafts(projects, run) {
    const date = await clearDrafts();
    const made = [];
    for (const project of projects) {
      made.push(await api.post(`/api/projects/${project}/reports/draft`, { report_date: date }));
    }
    try {
      await run(made);
    } finally {
      for (const draft of made) await api.delete(`/api/reports/${draft.id}`);
    }
  }

  await check("초안 1건이면 그 초안 편집기로 곧장 간다", async () => {
    await withDrafts([seeded.projectB], async ([draft]) => {
      await go("#/projects");
      const link = page.locator(".report-reminder .reminder-go");
      const href = await link.getAttribute("href");
      expect(href.includes(`report=${draft.id}`), `초안으로 가지 않는다: ${href}`);
      expect((await link.innerText()).includes("공정 자동화"), "어느 과제인지 이름이 없다");
      await link.click();
      await page.waitForTimeout(900);
      // 보고 편집기가 열려 있어야 한다 — 후보 목록이 아니다.
      equal(await page.locator(".report-editor").count(), 1, "열린 보고 편집기");
    });
  });

  await check("초안이 둘이면 이름을 칩으로 세운다", async () => {
    await withDrafts([seeded.projectA, seeded.projectB], async () => {
      await go("#/projects");
      const chips = page.locator(".report-reminder .reminder-chip");
      equal(await chips.count(), 2, "칩 수");
      for (let i = 0; i < 2; i += 1) {
        const href = await chips.nth(i).getAttribute("href");
        expect(/report=\d+/.test(href), `칩이 초안을 가리키지 않는다: ${href}`);
      }
      // 이름을 적었으면 그 이름으로 데려간다 (DESIGN 5.8).
      equal(await page.locator(".report-reminder .reminder-go").count(), 0, "칩 대신 뜬 단일 링크");
    });
  });

  await check("초안이 없으면 보고 대상으로 보내고 무엇을 할지 알려 준다", async () => {
    await clearDrafts();
    await go("#/projects");
    const link = page.locator(".report-reminder .reminder-go");
    equal(await link.getAttribute("href"), "#/reports", "목적지");
    await link.click();
    await page.waitForTimeout(900);
    // 묶음이 비어 있어도 카드가 서고, 그 자리가 안내가 된다.
    const picked = await page.locator(".picked").innerText();
    expect(picked.includes("담기"), `안내가 없다: ${picked}`);
  });

  await check("확정을 기다리는 초안이 보고 대상 화면 맨 위에 선다", async () => {
    await withDrafts([seeded.projectA, seeded.projectB], async () => {
      await go("#/reports");
      const card = page.locator(".drafts-waiting");
      equal(await card.count(), 1, "확정 대기 카드");
      // 날짜를 가리지 않으므로(TODO 101) 심어 둔 초안도 함께 선다. 서버가 세는 수와 같으면 된다.
      const candidates = await api.get("/api/report-candidates");
      equal(await card.locator(".picked-list li").count(), candidates.drafts.length, "카드 안의 줄 수");
      expect(candidates.drafts.length >= 2, `초안 수: ${candidates.drafts.length}`);
      // 줄 전체가 초안으로 가는 링크다 (TODO 130) — 따로 선 [초안 열기] 단추는 없앴다.
      const open = card.locator(".draft-row").first();
      expect(/report=\d+/.test(await open.getAttribute("href")), "줄이 초안을 가리키지 않는다");
      equal(await card.locator(".linkish-button").count(), 0, "남아 있는 [초안 열기]");
      const head = await card.locator(".card-head").innerText();
      expect(head.includes("초안 편집 화면으로 이동"), `머리말의 ※ 안내가 없다: ${head}`);

      // 이름 길이가 달라도 날짜 칸이 같은 자리에 선다 (TODO 131).
      const rows = card.locator(".draft-row");
      const lefts = [];
      for (let i = 0; i < (await rows.count()); i += 1) {
        const box = await rows.nth(i).locator(".due").boundingBox();
        if (box) lefts.push(Math.round(box.x));
      }
      expect(lefts.length >= 2, `날짜 칸을 못 찾았다: ${lefts.length}`);
      expect(
        Math.max(...lefts) - Math.min(...lefts) <= 1,
        `날짜 칸이 줄마다 어긋난다: ${lefts.join(", ")}`,
      );
    });
  });

  console.log("\n[7] 유관부서 (TODO 92)");

  await check("화면에서 부서를 여럿 넣고, 팀·사람으로 찾는다", async () => {
    await go(`#/projects/${seeded.projectA}`);
    await page.getByRole("button", { name: "과제 정보 수정" }).click();
    await page.waitForSelector(".partner-field");

    // 두 팀을 넣는다 — 한 팀에는 담당자 둘, 다른 팀은 담당자 미정.
    for (const [team, people] of [["설비기술팀", "김철수, 박민수"], ["구매팀", ""]]) {
      await page.getByRole("button", { name: "+ 부서 추가" }).click();
      const rows = page.locator(".partner-rows li");
      const last = rows.nth((await rows.count()) - 1);
      await last.locator("input").first().fill(team);
      if (people) await last.locator("input").nth(1).fill(people);
    }
    await page.locator("form").getByRole("button", { name: /저장|수정/ }).first().click();
    await page.waitForTimeout(1400);

    // 저장은 (팀, 사람) 쌍으로 나뉘어야 한다 — 한 덩이로 굳으면 안 된다 (TODO 74).
    const saved = await api.get(`/api/projects/${seeded.projectA}`);
    const 설비 = saved.partners.find((row) => row.team === "설비기술팀");
    equal(설비.people.join(","), "김철수,박민수", "나뉜 담당자");
    equal(saved.partners.find((row) => row.team === "구매팀").people.length, 0, "담당자 미정 팀");

    // 상세 화면에 팀과 사람이 보인다.
    await go(`#/projects/${seeded.projectA}`);
    const line = await page.locator(".partner-line").innerText();
    for (const word of ["설비기술팀", "김철수", "박민수", "구매팀"]) {
      expect(line.includes(word), `유관부서 줄에 "${word}" 가 없다: ${line}`);
    }

    // 팀 이름을 누르면 그 팀과 일하는 과제만 남는다 (세는 수 = 거르는 수).
    await page.locator(".partner-line a", { hasText: "설비기술팀" }).first().click();
    await page.waitForTimeout(900);
    expect(page.url().includes("partner="), `조건이 주소에 없다: ${page.url()}`);
    equal(await page.locator(".grid tbody tr").count(), 1, "설비기술팀으로 거른 과제 수");

    // 사람 이름으로도 걸린다.
    await go("#/projects?partner=" + encodeURIComponent("박민수"));
    equal(await page.locator(".grid tbody tr").count(), 1, "박민수로 거른 과제 수");
  });

  await check("유관부서·담당자로 통합 검색이 된다", async () => {
    for (const query of ["설비기술팀", "박민수"]) {
      await go("#/search?q=" + encodeURIComponent(query));
      const text = await page.locator(".search-results, main").first().innerText();
      expect(text.includes("고강도 소재 개발"), `"${query}" 로 과제를 찾지 못했다`);
    }
  });

  await check("유관부서 거르기 상자가 목록에 선다", async () => {
    await go("#/projects");
    const select = page.locator(".filters select").filter({ hasText: "유관부서 전체" });
    equal(await select.count(), 1, "유관부서 선택 상자");
    // 부서와 담당자를 나눠 담는다 — 어느 쪽을 기억하든 고를 수 있게.
    const groups = await select.locator("optgroup").allTextContents();
    equal(groups.length, 2, "부서·담당자 두 묶음");
  });

  console.log("\n[8] 기간에 든 보고를 표에서 알아본다 (TODO 93)");

  /** 그 날짜에 **확정된** 보고를 하나 만든다 — 과제별 보고 표는 확정된 것만 센다. */
  async function frozenReport(project, date) {
    const draft = await api.post(`/api/projects/${project}/reports/draft`, { report_date: date });
    await api.post(`/api/reports/${draft.id}/freeze`);
    return draft;
  }

  /** 표가 접혀 있으면 펼친다 — 접힘은 브라우저에 기억되므로 앞 시험의 영향을 받는다. */
  async function openGrid() {
    if ((await page.locator(".month-grid").count()) === 0) {
      await page.locator(".month-card .card-head button").click();
      await page.waitForTimeout(300);
    }
  }

  // 한 달에 세 건. 한 칸에 두 건까지만 세우므로 **접히는 자리**도 함께 본다.
  for (const date of ["2026-06-05", "2026-06-12", "2026-06-19"]) {
    await frozenReport(seeded.projectA, date);
  }

  await check("기간에 든 보고만 다른 색으로 선다", async () => {
    await go("#/history?from=2026-06-19&to=2026-06-19");
    await openGrid();
    const marked = page.locator(".month-grid .month-hit.marked");
    equal(await marked.count(), 1, "표시된 칸 수");
    expect((await marked.innerText()).includes("06-19"), "표시된 것이 그날의 보고가 아니다");
    // 표를 펼치기 전에도 몇 건이 걸렸는지 알 수 있어야 한다.
    equal((await page.locator(".month-marked-count").innerText()).trim(),
      "기간에 든 보고 1건", "머리글 옆 건수");
    // 나머지는 그대로 파랗다 — 다 붉으면 표시가 아니다.
    expect(await page.locator(".month-grid .month-hit:not(.marked)").count() > 0,
      "견줄 파란 칸이 없습니다 (시험 자료 문제)");
  });

  await check("한 칸이 접혀도 찾는 그 건은 맨 앞에 선다", async () => {
    await go("#/history?from=2026-06-19&to=2026-06-19");
    await openGrid();
    const cell = page.locator(".month-grid td.month-cell.marked").first();
    equal(await cell.locator(".month-hit").count(), 2, "칸에 세운 수");
    expect((await cell.locator(".month-hit").first().innerText()).includes("06-19"),
      "찾는 건이 +N 밑에 숨었습니다");
    equal((await cell.locator(".month-more").innerText()).trim(), "+1", "접힌 수");
  });

  await check("기간을 안 걸면 아무것도 표시하지 않는다", async () => {
    await go("#/history");
    await openGrid();
    equal(await page.locator(".month-hit.marked").count(), 0, "표시된 칸 수");
    equal(await page.locator(".month-marked-count").count(), 0, "머리글 옆 건수");
  });

  await check("표시된 칸의 글자도 읽힌다", async () => {
    await go("#/history?from=2026-06-19&to=2026-06-19");
    await openGrid();
    const value = await contrastOf(".month-hit.marked .month-date");
    expect(value >= AA, `표시된 칸의 날짜 ${value} < ${AA}`);
    const hovered = await contrastOf(".month-hit.marked .month-date", { hover: true });
    expect(hovered >= AA, `마우스 올린 표시 칸 ${hovered} < ${AA}`);
    // 파란 칸과 **색 계열이 달라야** 한다 — 같은 계열의 농담 차이는 훑어서 안 걸린다.
    const color = (selector) =>
      page.locator(selector).first().evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(await color(".month-hit.marked") !== await color(".month-hit:not(.marked)"),
      "표시된 칸과 보통 칸의 색이 같습니다");
  });

  await check("오늘 보고한 건도 같은 길로 찾아진다", async () => {
    // 배너의 [오늘 보고한 N건 보기] 는 결국 from=to=오늘인 기간 조건이다 (TODO 93).
    const date = await clearDrafts();
    // projectB 는 앞 시험에서 [별도 보고 불필요] 가 되어 이 표에서 빠진다.
    await frozenReport(seeded.projectA, date);
    await go("#/projects");
    const link = page.locator(".report-reminder .reminder-go");
    const href = await link.getAttribute("href");
    expect(href.includes(`from=${date}`) && href.includes(`to=${date}`),
      `오늘로 거르지 않는다: ${href}`);
    await link.click();
    await page.waitForTimeout(900);
    await openGrid();
    expect(await page.locator(".month-hit.marked").count() >= 1, "오늘 보고한 건이 표시되지 않았습니다");
  });

  await check("가로로 밀어도 과제명 열은 왼쪽에 남는다", async () => {
    // 열두 달이 좁은 화면에 다 안 들어간다. 밀었을 때 어느 과제 줄인지 안 보이면 표를 못 읽는다.
    // (표 자신에게 걸린 overflow:hidden 때문에 붙어 있는 줄 알았던 열이 같이 밀려 나갔었다.)
    await page.setViewportSize({ width: 1000, height: 800 });
    await go("#/history");
    await openGrid();
    const moved = await page.evaluate(() => {
      const box = document.querySelector(".month-card .table-scroll");
      box.scrollLeft = 400;
      const name = document.querySelector(".month-grid td.month-name");
      return {
        scrolled: box.scrollLeft,
        gap: name.getBoundingClientRect().left - box.getBoundingClientRect().left,
      };
    });
    expect(moved.scrolled > 100, "표가 가로로 밀리지 않습니다 (시험 자료 문제)");
    expect(Math.abs(moved.gap) < 4, `과제명 열이 같이 밀려 나갔습니다 (${moved.gap}px)`);
    await page.setViewportSize({ width: 1440, height: 900 });
  });

  await check("표시한 칸이 화면 밖이면 가로로 밀어 준다", async () => {
    // 12월 것을 붉게 칠해 놓아도 그 열이 오른쪽 밖이면 여전히 찾아야 한다.
    await frozenReport(seeded.projectA, "2026-12-08");
    await page.setViewportSize({ width: 1000, height: 800 });
    await go("#/history?from=2026-12-08&to=2026-12-08");
    await openGrid();
    await page.waitForTimeout(400);
    const seen = await page.evaluate(() => {
      const box = document.querySelector(".month-card .table-scroll");
      const cell = box.querySelector(".month-cell.marked");
      if (!cell) return null;
      const a = cell.getBoundingClientRect();
      const b = box.getBoundingClientRect();
      return { scrolled: box.scrollLeft, inside: a.left >= b.left - 1 && a.right <= b.right + 1 };
    });
    expect(seen !== null, "표시된 칸을 찾지 못했습니다");
    expect(seen.scrolled > 0, "가로로 밀어 주지 않았습니다");
    expect(seen.inside, "밀었는데도 표시된 칸이 화면 밖입니다");
    await page.setViewportSize({ width: 1440, height: 900 });
  });

  console.log("\n[9] 상단 메뉴 이름");

  await check("메뉴 이름은 붙여 쓴다", async () => {
    // 한 줄에 여섯 칸이라, 이름 안에 띄어쓰기가 있으면 좁은 화면에서 그 자리에서 줄이 꺾인다.
    await go("#/");
    const names = await page.locator(".nav a").allInnerTexts();
    equal(names.map((name) => name.trim()).join("|"),
      "홈|접수|과제목록|로드맵|보고대상|보고이력|팀원역량|설정|도움말", "메뉴 이름");
  });

  console.log("\n[10] 과제 번호의 연도는 착수년도 (TODO 95)");

  /** 과제 만들기 폼을 열고 과제명·시작일을 채운다. */
  async function fillNew(title, startDate) {
    await go("#/projects?new=1");
    await page.waitForSelector("form .next-id-hint");
    await page.getByLabel("과제명").fill(title);
    if (startDate) await page.getByLabel("시작일").fill(startDate);
    // 미리보기는 서버에 물어 오므로 잠깐 기다린다.
    await page.waitForTimeout(600);
  }

  await check("저장하기 전에 붙을 번호를 보여 준다", async () => {
    await fillNew("2025년에 한 과제", "2025-04-01");
    const shown = (await page.locator("form .next-id").innerText()).trim();
    expect(shown.startsWith("2025-"), `미리보기가 2025 번호가 아니다: ${shown}`);

    // 시작일을 올해로 바꾸면 미리보기도 따라온다 — 붙을 번호를 그때그때 보여 준다.
    const thisYear = String(new Date().getFullYear());
    await page.getByLabel("시작일").fill(`${thisYear}-04-01`);
    await page.waitForTimeout(600);
    const now = (await page.locator("form .next-id").innerText()).trim();
    expect(now.startsWith(`${thisYear}-`), `올해 번호가 아니다: ${now}`);
  });

  await check("지난해 시작일로 만들면 지난해 번호가 붙는다", async () => {
    await fillNew("지난해에 수행한 과제", "2025-01-01");
    const preview = (await page.locator("form .next-id").innerText()).trim();
    // 이름을 정확히 짚는다 — 폼 안에는 [+ 부서 추가] 도 있어서 느슨하게 고르면 그쪽이 걸린다.
    await page.locator("form").getByRole("button", { name: "만들기", exact: true }).click();
    await page.waitForTimeout(1400);
    // 만든 과제가 그 번호로 열려야 한다.
    const made = (await api.get("/api/projects")).find((row) => row.title === "지난해에 수행한 과제");
    expect(made !== undefined, "만든 과제를 찾지 못했습니다");
    equal(made.id, preview, "미리보기와 실제로 붙은 번호");
    expect(made.id.startsWith("2025-"), `지난해 번호가 아니다: ${made.id}`);
    // 연도를 가르는 기준은 번호 앞 네 자리다 — 2025 목록에 선다.
    const listed = await api.get("/api/projects?year=2025");
    expect(listed.some((row) => row.id === made.id), "2025년 목록에 없습니다");
  });

  await check("시작일을 고쳐도 번호는 저절로 움직이지 않고, 어긋난 것을 알려 준다", async () => {
    const late = await api.post("/api/projects", { title: "뒤늦게 등록한 지난해 과제" });
    const thisYear = String(new Date().getFullYear());
    expect(late.id.startsWith(`${thisYear}-`), `올해 번호가 아니다: ${late.id}`);

    await api.patch(`/api/projects/${late.id}`, { start_date: "2025-02-02" });
    await go(`#/projects/${late.id}`);
    // 번호는 그대로다 — 이미 보고 자리에서 불린 이름을 소리 없이 바꾸지 않는다.
    equal((await api.get(`/api/projects/${late.id}`)).id, late.id, "고친 뒤의 번호");

    const note = page.locator(".year-fix");
    equal(await note.count(), 1, "어긋났다는 안내");
    const text = await note.innerText();
    expect(text.includes("2025"), `안내에 옮겨 갈 해가 없다: ${text}`);
  });

  await check("누르면 그 번호로 옮겨 가고 진행일지도 따라온다", async () => {
    const late = await api.post("/api/projects", { title: "옮길 지난해 과제" });
    await api.post(`/api/projects/${late.id}/entries`, {
      date: "2025-03-10", title: "지난해 시험", body: "## 내용\n\n돌려 봤다\n",
    });
    await api.patch(`/api/projects/${late.id}`, { start_date: "2025-03-01" });

    await go(`#/projects/${late.id}`);
    const button = page.locator(".year-fix button");
    const label = (await button.innerText()).trim();
    const wanted = label.split(" ")[0];
    expect(wanted.startsWith("2025-"), `단추가 2025 번호를 말하지 않는다: ${label}`);

    // 확인 창은 위쪽에 걸어 둔 page.on("dialog") 가 이미 받아 준다.
    await button.click();
    await page.waitForTimeout(1600);

    // 새 번호의 화면으로 데려간다.
    expect(page.url().includes(wanted), `새 번호로 가지 않았다: ${page.url()}`);
    equal(await page.locator(".year-fix").count(), 0, "옮긴 뒤에도 남은 안내");
    // 진행일지는 폴더째 따라온다.
    const entries = await api.get(`/api/projects/${wanted}/entries`);
    equal(entries.length, 1, "따라온 진행일지 수");
    equal(entries[0].title, "지난해 시험", "따라온 진행일지");
    // 옛 번호는 더 이상 없다.
    expect((await api.get("/api/projects")).every((row) => row.id !== late.id),
      "옛 번호가 남아 있습니다");
  });

  console.log("\n[11] 거르기 상자에는 있는 것만 선다 (TODO 96)");

  /** 과제 목록의 거르기 상자 하나를 골라, 그 안의 선택지 글자를 모두 읽는다. */
  async function optionsOf(label) {
    const select = page.locator(".filters select").filter({ hasText: label });
    expect(await select.count() === 1, `"${label}" 상자를 찾지 못했습니다`);
    return (await select.first().locator("option").allInnerTexts()).map((text) => text.trim());
  }

  await check("연도 상자에 과제가 없는 해는 서지 않는다", async () => {
    await go("#/projects");
    const listed = await optionsOf("연도 전체");
    const real = new Set((await api.get("/api/projects")).map((row) => row.id.slice(0, 4)));
    const thisYear = String(new Date().getFullYear());
    for (const text of listed) {
      if (text === "연도 전체") continue;
      const year = text.replace("년", "");
      // 올해는 과제가 없어도 남는다 — 기본값이고, "올해만 보기" 는 뜻이 통해야 한다.
      expect(real.has(year) || year === thisYear, `과제가 없는 ${year}년이 서 있습니다`);
    }
    // 자료에 있는 해는 빠짐없이 서야 한다.
    for (const year of real) {
      expect(listed.includes(`${year}년`), `${year}년이 빠졌습니다: ${listed.join(", ")}`);
    }
  });

  await check("주소가 가리키는 해는 과제가 없어도 남는다", async () => {
    // 즐겨찾기해 둔 ?year=2019 가 빈칸으로 보이면 지금 무엇으로 걸렀는지 알 수 없다.
    await go("#/projects?year=2019");
    const listed = await optionsOf("연도 전체");
    expect(listed.includes("2019년"), `주소의 해가 빠졌습니다: ${listed.join(", ")}`);
    const select = page.locator(".filters select").filter({ hasText: "연도 전체" }).first();
    equal(await select.inputValue(), "2019", "고른 값");
  });

  await check("태그 상자에는 과제에 붙은 태그만 선다", async () => {
    // 진행일지에만 붙인 태그로 과제를 거르면 늘 0건이다.
    const project = await api.post("/api/projects", { title: "태그 시험 과제", tags: ["과제태그"] });
    await api.post(`/api/projects/${project.id}/entries`, {
      date: "2026-04-01", title: "기록", body: "## 내용\n\n적었다\n", tags: ["일지태그"],
    });
    await go("#/projects");
    const listed = await optionsOf("태그 전체");
    expect(listed.includes("과제태그"), `과제 태그가 빠졌습니다: ${listed.join(", ")}`);
    expect(!listed.includes("일지태그"), `진행일지 태그가 서 있습니다: ${listed.join(", ")}`);

    // 떼어 낸 태그도 사라져야 한다 — `tag` 표에는 남아 있다.
    await api.patch(`/api/projects/${project.id}`, { tags: [] });
    await go("#/projects");
    expect(!(await optionsOf("태그 전체")).includes("과제태그"), "떼어 낸 태그가 남아 있습니다");
  });

  await check("그룹을 안 적은 과제가 있으면 [미지정]으로 고를 수 있다", async () => {
    await go("#/projects?year=all");
    const listed = await optionsOf("그룹 전체");
    expect(listed.includes("미지정"), `[미지정] 이 없습니다: ${listed.join(", ")}`);
    // 상자에만 있고 걸리지 않으면 더 나쁘다 — 홈의 그룹별 표가 이리로 이어 준다.
    const select = page.locator(".filters select").filter({ hasText: "그룹 전체" }).first();
    await select.selectOption("none");
    await page.waitForTimeout(800);
    const rows = await page.locator(".grid tbody tr").count();
    const api_rows = (await api.get("/api/projects?group=none")).length;
    equal(rows, api_rows, "미지정으로 거른 과제 수");
  });

  await check("상태·속성처럼 고르는 말은 좁히지 않는다", async () => {
    await go("#/projects");
    // "보류인 게 있나?" 에 없다고 답하는 것도 거르기의 쓸모다.
    const listed = await optionsOf("상태 전체");
    const known = await api.get("/api/meta");
    equal(listed.length, known.statuses.length + 1, "상태 선택지 수");
  });

  console.log("\n[12] 설정 화면 — 묶음과 폴더 고르기 (TODO 97 · 98)");

  await check("설정이 기능별로 묶여 있다", async () => {
    await go("#/settings");
    const titles = await page.locator(".settings-group-title").allInnerTexts();
    const names = titles.map((text) => text.split("\n")[0].trim());
    equal(names.join("|"), "기본|과제 분류 · 접수|보고|서식|보관과 백업|점검", "묶음 이름");
    // 묶음마다 카드가 하나 이상 들어 있어야 한다 — 빈 묶음은 어수선함만 늘린다.
    for (const group of await page.locator(".settings-group").all()) {
      expect(await group.locator(".card").count() > 0, "카드가 없는 묶음이 있습니다");
    }
    // 백업 관련은 한 묶음에 모여 있다.
    const backup = page.locator(".settings-group").filter({ hasText: "보관과 백업" });
    const cards = (await backup.locator(".card > h2").allInnerTexts()).map((t) => t.trim());
    for (const name of ["데이터 위치", "전체 백업", "자동 백업"]) {
      expect(cards.includes(name), `"${name}" 이 보관과 백업 묶음에 없습니다: ${cards.join(", ")}`);
    }
  });

  /**
   * 자동 백업 카드에서 폴더 고르기를 펼치고 **처음 자리(드라이브·내 폴더)** 까지 올라간다.
   * 앞선 시험이 백업 폴더를 정해 둔 채라 그 자리에서 열리는데, 그 안에 하위 폴더가
   * 없으면 세울 줄도 없다 — 어디서 열리든 같은 자리에서 시작하게 맞춘다.
   */
  async function openPicker() {
    const card = page.locator(".card").filter({ hasText: "자동 백업" }).first();
    await card.getByRole("button", { name: "폴더 고르기" }).click();
    await page.waitForSelector(".folder-picker");
    const up = page.locator(".folder-picker .folder-head button");
    // 임시 vault 경로의 깊이는 실행마다 다르다. 열둘로는 모자란 날이 있어 넉넉히 올라간다
    // — 다 올라가지 못한 채 "처음 자리" 를 재면 시험이 이유 없이 실패한다.
    for (let step = 0; step < 30 && !(await up.isDisabled()); step += 1) {
      await up.click();
      await page.waitForTimeout(250);
    }
    return { card, up };
  }

  await check("백업 폴더를 눌러서 고른다", async () => {
    await go("#/settings");
    const { card, up } = await openPicker();
    // 처음 자리에서는 위로 갈 곳이 없다.
    expect(await up.isDisabled(), "처음 자리인데 [위로]가 켜져 있습니다");

    await page.locator(".folder-picker .folder-row").first().click();
    await page.waitForTimeout(700);
    const at = (await page.locator(".folder-at").innerText()).trim();
    expect(at.length > 0 && at !== "내 PC", `들어간 자리가 표시되지 않습니다: ${at}`);

    // 고르면 경로 칸이 채워진다 — 손으로 치지 않아도 된다.
    const pick = page.locator(".folder-actions button").last();
    expect(!(await pick.isDisabled()), `쓸 수 있는 폴더인데 고를 수 없습니다: ${at}`);
    await pick.click();
    await page.waitForTimeout(600);
    equal((await card.locator(".input-with-button input").inputValue()).trim(), at, "칸에 들어간 값");
    // 고른 것만으로는 아직 아무 일도 일어나지 않는다는 것을 말해 준다.
    expect((await card.innerText()).includes("[저장]"), "저장하라는 안내가 없습니다");
  });

  await check("폴더 고르기에서 새 폴더를 만든다", async () => {
    await go("#/settings");
    await openPicker();
    await page.locator(".folder-picker .folder-row").first().click();
    await page.waitForTimeout(700);

    const name = `백업시험-${Date.now()}`;
    await page.getByRole("button", { name: "+ 새 폴더" }).click();
    await page.locator(".folder-new input").fill(name);
    await page.getByRole("button", { name: "만들기" }).click();
    await page.waitForTimeout(1000);
    // 만들면 그 안으로 들어가 있다 — 탐색기를 따로 열지 않아도 된다.
    const at = await page.locator(".folder-at").innerText();
    expect(at.includes(name), `만든 폴더로 들어가지 않았습니다: ${at}`);
  });

  console.log("\n[13] 속성에 유지보수 (TODO 99)");

  await check("유지보수를 골라 만들고, 그 속성으로 거른다", async () => {
    await go("#/projects?new=1");
    await page.waitForSelector("form .next-id-hint");
    await page.getByLabel("과제명").fill("설비 제어 SW 유지보수");
    await page.getByLabel("속성").selectOption({ label: "유지보수" });
    await page.locator("form").getByRole("button", { name: "만들기", exact: true }).click();
    await page.waitForTimeout(1400);

    const made = (await api.get("/api/projects")).find((row) => row.title === "설비 제어 SW 유지보수");
    expect(made !== undefined, "만든 과제를 찾지 못했습니다");
    equal(made.type, "maintenance", "저장된 속성");

    // 거르기 상자에도 서고, 골라서 걸러야 한다 — 목록에만 있고 안 걸리면 더 나쁘다.
    await go("#/projects");
    const select = page.locator(".filters select").filter({ hasText: "속성 전체" }).first();
    expect((await select.locator("option").allInnerTexts()).some((text) => text.trim() === "유지보수"),
      "속성 상자에 유지보수가 없습니다");
    await select.selectOption("maintenance");
    await page.waitForTimeout(800);
    equal(await page.locator(".grid tbody tr").count(),
      (await api.get("/api/projects?type=maintenance")).length, "유지보수로 거른 과제 수");
  });

  await check("유지보수 딱지의 글자가 읽힌다", async () => {
    await go("#/projects?type=maintenance");
    const value = await contrastOf(".type-maintenance");
    expect(value >= AA, `유지보수 딱지 ${value} < ${AA}`);
  });

  console.log("\n[14] 과제 속성을 설정에서 다룬다 (TODO 100)");

  /** 설정의 [과제 속성] 카드. */
  function typeCard() {
    return page.locator(".card").filter({ hasText: "과제 속성" }).first();
  }

  /** 줄 하나를 더하고 이름을 적는다. 저장은 하지 않는다. */
  async function addType(label) {
    const card = typeCard();
    await card.getByRole("button", { name: "+ 속성 추가" }).click();
    await card.locator(".type-rows li input").last().fill(label);
    return card;
  }

  await check("속성을 더하면 과제 만들기 화면에 곧바로 선다", async () => {
    await go("#/settings");
    const card = await addType("설비투자");
    await card.getByRole("button", { name: "저장", exact: true }).click();
    await page.waitForTimeout(1200);

    // 서버가 이름에서 열쇠를 지어 붙인다.
    const saved = (await api.get("/api/settings/project-types")).types;
    const made = saved.find((row) => row.label === "설비투자");
    expect(made !== undefined, `저장되지 않았습니다: ${saved.map((r) => r.label).join(", ")}`);
    expect(made.key.length > 0, "열쇠가 비어 있습니다");

    // 과제 만들기 화면의 속성 상자에 선다 — 같은 목록을 보기 때문이다.
    await go("#/projects?new=1");
    await page.waitForSelector("form .next-id-hint");
    const options = await page.getByLabel("속성").locator("option").allInnerTexts();
    expect(options.map((t) => t.trim()).includes("설비투자"), `상자에 없습니다: ${options.join(", ")}`);

    // 골라서 만들면 그 속성으로 저장되고 딱지가 선다.
    await page.getByLabel("과제명").fill("압연기 교체");
    await page.getByLabel("속성").selectOption({ label: "설비투자" });
    await page.locator("form").getByRole("button", { name: "만들기", exact: true }).click();
    await page.waitForTimeout(1400);
    const project = (await api.get("/api/projects")).find((row) => row.title === "압연기 교체");
    equal(project.type, made.key, "저장된 속성");
    await go(`#/projects/${project.id}`);
    equal((await page.locator(".type-badge").first().innerText()).trim(), "설비투자", "딱지 글자");
  });

  await check("이름을 고쳐도 그 속성을 쓰던 과제는 속성을 잃지 않는다", async () => {
    const before = (await api.get("/api/projects")).find((row) => row.title === "압연기 교체");
    await go("#/settings");
    const card = typeCard();
    const row = card.locator(".type-rows li").filter({ hasText: "설비투자" }).first();
    await row.locator("input").fill("설비 투자·개선");
    await card.getByRole("button", { name: "저장", exact: true }).click();
    await page.waitForTimeout(1200);

    const after = (await api.get("/api/projects")).find((row) => row.title === "압연기 교체");
    // 과제 파일에 남는 것은 이름이 아니라 열쇠다.
    equal(after.type, before.type, "이름을 고친 뒤의 속성");
    // 화면에 보이는 이름만 바뀐다.
    await go(`#/projects/${after.id}`);
    equal((await page.locator(".type-badge").first().innerText()).trim(), "설비 투자·개선", "딱지 글자");
  });

  await check("쓰고 있는 속성은 빼지 못하게 잠겨 있다", async () => {
    await go("#/settings");
    const used = typeCard().locator(".type-rows li").filter({ hasText: "설비 투자·개선" }).first();
    expect((await used.innerText()).includes("1건"), `쓰는 과제 수가 없습니다: ${await used.innerText()}`);
    expect(await used.getByRole("button", { name: "빼기" }).isDisabled(), "[빼기]가 켜져 있습니다");
  });

  await check("안 쓰는 속성은 뺄 수 있고, 빼면 상자에서도 사라진다", async () => {
    await go("#/settings");
    const card = await addType("잠깐 쓸 속성");
    await card.getByRole("button", { name: "저장", exact: true }).click();
    await page.waitForTimeout(1200);

    const row = card.locator(".type-rows li").filter({ hasText: "잠깐 쓸 속성" }).first();
    await row.getByRole("button", { name: "빼기" }).click();
    await card.getByRole("button", { name: "저장", exact: true }).click();
    await page.waitForTimeout(1200);

    const left = (await api.get("/api/settings/project-types")).types.map((r) => r.label);
    expect(!left.includes("잠깐 쓸 속성"), `아직 남아 있습니다: ${left.join(", ")}`);
    await go("#/projects");
    const options = await page.locator(".filters select").filter({ hasText: "속성 전체" })
      .first().locator("option").allInnerTexts();
    expect(!options.map((t) => t.trim()).includes("잠깐 쓸 속성"), "거르기 상자에 남아 있습니다");
  });

  await check("순서를 바꾸면 거르기 상자도 따라온다", async () => {
    await go("#/settings");
    const card = typeCard();
    const first = (await card.locator(".type-rows li input").first().inputValue()).trim();
    // 둘째 줄을 맨 위로 올린다.
    await card.locator(".type-rows li").nth(1).getByTitle("위로").click();
    await card.getByRole("button", { name: "저장", exact: true }).click();
    await page.waitForTimeout(1200);
    const moved = (await api.get("/api/settings/project-types")).types[0].label;
    expect(moved !== first, `순서가 그대로입니다: ${moved}`);

    await go("#/projects");
    const options = (await page.locator(".filters select").filter({ hasText: "속성 전체" })
      .first().locator("option").allInnerTexts()).map((t) => t.trim());
    // [속성 전체]·[미지정] 다음이 첫 속성이다.
    equal(options[2], moved, "거르기 상자의 첫 속성");
  });

  console.log("\n[15] 쓰다 만 보고를 홈이 들고 있는다 (TODO 101)");

  /** 확정하지 않은 보고를 **전부** 치운다 — 앞 시험이 남긴 것이 섞이면 건수를 못 본다. */
  async function clearAllDrafts() {
    for (const item of await api.get("/api/reports?state=draft")) {
      await api.delete(`/api/reports/${item.id}`);
    }
  }

  /** 오늘 기준 며칠 뒤(음수면 며칠 전) 날짜. */
  function dayFromToday(offset) {
    const now = new Date();
    now.setDate(now.getDate() + offset);
    return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  }

  await check("확정 안 한 보고가 이번 주 할 일에 선다", async () => {
    await clearAllDrafts();
    const made = await api.post(`/api/projects/${seeded.projectA}/reports/draft`, {
      report_date: dayFromToday(2), audience: "전사 주요업무 보고",
    });
    try {
      await go("#/");
      const card = page.locator(".home-week");
      const tile = card.locator(".home-stat").filter({ hasText: "작성 중인 보고" });
      equal(await tile.count(), 1, "작성 중인 보고 칸");
      expect((await tile.innerText()).includes("1건"), `건수가 다릅니다: ${await tile.innerText()}`);

      // 개수만 적어 놓으면 그 한 건을 다시 찾아야 한다 — 이름과 갈 곳을 함께 준다.
      const rows = card.locator(".home-drafts li");
      equal(await rows.count(), 1, "세운 줄 수");
      const href = await rows.first().locator("a").getAttribute("href");
      expect(href.includes(`report=${made.id}`), `그 초안으로 가지 않습니다: ${href}`);
      await rows.first().locator("a").click();
      await page.waitForTimeout(1000);
      equal(await page.locator(".report-editor").count(), 1, "열린 보고 편집기");
    } finally {
      await api.delete(`/api/reports/${made.id}`);
    }
  });

  await check("여러 건이면 여러 줄로 서고, 지난 보고일은 붉게 센다", async () => {
    await clearAllDrafts();
    const made = [];
    for (const [project, offset] of [
      [seeded.projectA, -9], [seeded.projectB, -2], [seeded.projectA, 3],
    ]) {
      made.push(await api.post(`/api/projects/${project}/reports/draft`, {
        report_date: dayFromToday(offset),
      }));
    }
    try {
      await go("#/");
      const card = page.locator(".home-week");
      expect((await card.locator(".home-stat").filter({ hasText: "작성 중인 보고" }).innerText())
        .includes("3건"), "건수가 3건이 아닙니다");
      equal(await card.locator(".home-drafts li").count(), 3, "세운 줄 수");

      // 보고일이 지난 것만 붉다 — 아직 안 온 것은 지금 하는 일이지 밀린 일이 아니다.
      equal(await card.locator(".home-drafts .due-danger").count(), 2, "붉게 선 줄 수");
      const text = await card.innerText();
      expect(text.includes("2건은 보고일이 이미 지났습니다"), `안내가 없습니다: ${text}`);

      // 오래된 것이 맨 앞이다.
      const first = await card.locator(".home-drafts li").first().innerText();
      expect(first.includes(dayFromToday(-9)), `오래된 것이 앞에 없습니다: ${first}`);
    } finally {
      for (const item of made) await api.delete(`/api/reports/${item.id}`);
    }
  });

  await check("확정하면 그 자리에서 사라진다", async () => {
    await clearAllDrafts();
    const made = await api.post(`/api/projects/${seeded.projectA}/reports/draft`, {
      report_date: dayFromToday(0),
    });
    await go("#/");
    equal(await page.locator(".home-week .home-drafts li").count(), 1, "확정 전 줄 수");
    await api.post(`/api/reports/${made.id}/freeze`);
    await go("#/");
    equal(await page.locator(".home-week .home-drafts li").count(), 0, "확정 뒤 줄 수");
    equal(await page.locator(".home-week .home-drafts").count(), 0, "빈 목록은 세우지 않는다");
  });

  await check("연도를 바꿔도 쓰다 만 보고는 그대로 보인다", async () => {
    // 연도는 과제를 가르는 조건이지, 지금 손에 쥔 일을 가리는 조건이 아니다.
    await clearAllDrafts();
    const made = await api.post(`/api/projects/${seeded.projectA}/reports/draft`, {
      report_date: dayFromToday(-4),
    });
    try {
      await go("#/");
      equal(await page.locator(".home-week .home-drafts li").count(), 1, "기본 연도");
      // 홈은 연도를 주소에 싣지 않는다 — 화면의 상자로 바꾼다.
      const select = page.locator(".home-year select");
      await select.selectOption("all");
      await page.waitForTimeout(900);
      equal(await page.locator(".home-week .home-drafts li").count(), 1, "연도 전체");
    } finally {
      await api.delete(`/api/reports/${made.id}`);
    }
  });

  console.log("\n[16] 전수 검토의 새 기능 여섯 (TODO 107~112)");
  await check("메뉴 끝에 [도움말]이 있고 네 묶음이 선다 (TODO 111 · 136)", async () => {
    await go("#/help");
    equal(await page.locator(".help .settings-group").count(), 4, "묶음 수");
    expect(await page.locator(".help-steps li").count() >= 4, "주간 흐름 단계");
    expect(await page.locator(".help-faq dt").count() >= 5, "자주 묻는 것");
    equal(await page.locator(".nav a.active").innerText(), "도움말", "활성 메뉴");
  });

  await check("확정된 보고에만 [보고 결과 · 지시사항] 칸이 있다 (TODO 107)", async () => {
    const reports = await api.get(`/api/projects/${seeded.projectA}/reports`);
    const frozen = reports.find((item) => item.frozen);
    // [15] 가 초안을 모두 치웠으므로 하나 만들어 본다.
    const draft = await api.post(`/api/projects/${seeded.projectA}/reports/draft`, {
      report_date: dayFromToday(0),
    });
    try {
      await go(`#/projects/${seeded.projectA}?report=${draft.id}`);
      equal(await page.locator('[data-testid="report-feedback"]').count(), 0, "초안에는 없다");
    } finally {
      await api.delete(`/api/reports/${draft.id}`);
    }
    await go(`#/projects/${seeded.projectA}?report=${frozen.id}`);
    equal(await page.locator('[data-testid="report-feedback"]').count(), 1, "확정 보고에는 있다");
    await page.locator(".feedback-text").fill("원가 근거 자료를 다음 주까지 보완할 것");
    await page.getByRole("button", { name: "지시사항 저장" }).click();
    await page.waitForTimeout(600);
    const saved = await api.get(`/api/reports/${frozen.id}`);
    equal(saved.feedback, "원가 근거 자료를 다음 주까지 보완할 것", "저장된 지시");
    expect((await page.locator(".feedback-state.open").count()) === 1, "답하지 않음 표시");
  });

  await check("답하지 않은 지시가 과제 위쪽 띠와 보고이력 필터에 선다", async () => {
    await go(`#/projects/${seeded.projectA}`);
    equal(await page.locator('[data-testid="open-feedback"]').count(), 1, "과제 위쪽 띠");
    expect((await page.locator('[data-testid="open-feedback"]').innerText()).includes("1건"), "건수");
    await go("#/history?feedback=open");
    equal(await page.locator(".history-list li").count(), 1, "답하지 않은 지시만");
    equal(await page.locator(".feedback-tag").count(), 1, "지시 표");
    expect(await page.locator('.check-label input[type="checkbox"]').isChecked(), "체크 상태가 주소를 따른다");
  });

  await check("새 초안이 지시를 맨 위에 물고 오고, [답변함]이면 띠가 사라진다", async () => {
    const made = await api.post(`/api/projects/${seeded.projectA}/reports/draft`, {
      report_date: dayFromToday(1),
    });
    try {
      expect(made.body.startsWith("## 지난 보고 지시사항"), `초안 머리: ${made.body.slice(0, 40)}`);
      expect(made.body.includes("원가 근거 자료"), "지시 본문");
    } finally {
      await api.delete(`/api/reports/${made.id}`);
    }
    const reports = await api.get(`/api/projects/${seeded.projectA}/reports`);
    const frozen = reports.find((item) => item.frozen);
    await go(`#/projects/${seeded.projectA}?report=${frozen.id}`);
    await page.getByRole("button", { name: "답변함", exact: true }).click();
    await page.waitForTimeout(600);
    equal(await page.locator(".feedback-state.done").count(), 1, "답변함 표시");
    equal(await page.locator('[data-testid="open-feedback"]').count(), 0, "띠가 사라진다");
  });

  await check("[이 과제로 새 과제]는 미리 채운 칸만 열고, [만들기]를 눌러야 생긴다 (TODO 109 · 173)", async () => {
    await go(`#/projects/${seeded.projectA}`);
    const before = (await api.get("/api/projects")).length;
    await page.getByRole("button", { name: "이 과제로 새 과제" }).click();
    await page.waitForTimeout(700);
    const panel = page.locator(".clone-panel");
    equal(await panel.count(), 1, "새 과제 칸");
    equal(await panel.locator("input").first().inputValue(), "고강도 소재 개발", "과제명이 채워진다");
    equal(await panel.locator(".predecessor-chip").count(), 1, "선행 과제 칩");
    equal((await api.get("/api/projects")).length, before, "열기만 해서는 안 생긴다");
    // [취소] — 아무것도 남지 않는다 (v9 C-1)
    await panel.getByRole("button", { name: "취소" }).click();
    await page.waitForTimeout(400);
    equal(await page.locator(".clone-panel").count(), 0, "칸이 닫힌다");
    equal((await api.get("/api/projects")).length, before, "취소하면 과제 수 그대로");
    // 다시 열어 [만들기]
    await page.getByRole("button", { name: "이 과제로 새 과제" }).click();
    await page.waitForTimeout(700);
    await page.locator(".clone-panel").getByRole("button", { name: "만들기" }).click();
    await page.waitForTimeout(1200);
    const hash = page.url().split("#")[1] ?? "";
    const newId = decodeURIComponent(hash.slice("/projects/".length).split("?")[0]);
    expect(hash.startsWith("/projects/") && newId !== seeded.projectA, `주소: ${hash}`);
    const created = await api.get(`/api/projects/${newId}`);
    equal(created.status, "planned", "상태는 예정");
    expect(created.owners.includes("권경락"), "담당자가 넘어온다");
    expect((created.predecessors ?? []).includes(seeded.projectA), "선행 과제로 이어짐");
    expect((created.body ?? "").length > 0, "개요가 넘어온다");
    equal(created.stage, 2, "2단계");
    // 보관은 204 라 본문이 없다.
    await fetch(`${BASE}/api/projects/${newId}/archive`, { method: "POST" });
  });

  await check("[표 복사]가 과제목록·보고대상·홈 표에 있다 (TODO 108)", async () => {
    await page.context().grantPermissions(["clipboard-read", "clipboard-write"], { origin: BASE });
    await go("#/projects");
    equal(await page.locator(".toolbar .copy-table").count(), 1, "과제목록");
    await page.locator(".toolbar .copy-table").click();
    await page.waitForTimeout(200);
    const text = await page.evaluate(() => navigator.clipboard.readText());
    const lines = text.trim().split("\n");
    expect(lines[0].startsWith("번호\t과제\t상태"), `머리글: ${lines[0]}`);
    equal(lines.length - 1, await page.locator("table.grid tbody tr").count(), "줄 수가 표와 같다");
    equal(await page.locator(".toolbar .copy-table").innerText(), "복사됨 ✓", "눌린 표시");
    await go("#/reports");
    equal(await page.locator(".toolbar .copy-table").count(), 1, "보고대상");
    await go("#/");
    expect((await page.locator(".home .copy-table").count()) >= 2, "홈 표들");
  });

  await check("기준 연도 옆 기간 상자 — 전체 연도에서는 사라진다 (TODO 110)", async () => {
    await go("#/");
    equal(await page.locator(".home-period select").count(), 1, "기간 상자");
    await page.locator(".home-period select").selectOption("H1");
    await page.waitForTimeout(700);
    equal(await page.locator(".home-period-note").count(), 1, "기간 안내 한 줄");
    expect((await page.locator(".home-period-note").innerText()).includes("상반기"), "상반기 표시");
    await page.locator(".home-year select").first().selectOption("all");
    await page.waitForTimeout(700);
    equal(await page.locator(".home-period select").count(), 0, "연도 전체에서는 뜻이 없다");
  });

  await check("진행일지의 ## 계획이 과제 위쪽과 홈의 다음 할 일에 선다 (TODO 112)", async () => {
    const entry = await api.post(`/api/projects/${seeded.projectB}/entries`, {
      date: dayFromToday(0), title: "설비 점검",
      body: "## 내용\n\n점검 완료\n\n## 계획\n\n- 다음 주 2차 점검\n- 보고서 초안 작성\n",
    });
    try {
      await go(`#/projects/${seeded.projectB}`);
      equal(await page.locator('[data-testid="next-plan"]').count(), 1, "과제 위쪽 한 줄");
      expect((await page.locator('[data-testid="next-plan"]').innerText()).includes("다음 주 2차 점검"), "계획 본문");
      await go("#/");
      expect((await page.locator('[data-testid="home-plans"] li').count()) >= 1, "홈 목록");
      expect((await page.locator('[data-testid="home-plans"]').innerText()).includes("공정 자동화"), "과제 이름");
    } finally {
      await api.delete(`/api/entries/${entry.id}`);
    }
  });

  console.log("\n[17] 공백 있는 첨부 이름 · 검색창 비우기 (TODO 114 · 115)");
  await check("이름에 공백·괄호가 있는 첨부가 본문에서 그대로 열린다", async () => {
    const entry = await api.post(`/api/projects/${seeded.projectB}/entries`, {
      date: dayFromToday(0), title: "공백 첨부", body: "## 내용\n\n측정 사진\n",
    });
    // 1×1 PNG. 시험은 그림이 아니라 링크가 살아 있는지를 본다.
    const png = Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
      "base64",
    );
    const form = new FormData();
    form.append("file", new Blob([png], { type: "image/png" }), "측정 결과 (최종).png");
    const uploaded = await fetch(`${BASE}/api/entries/${entry.id}/attachments`, { method: "POST", body: form });
    expect(uploaded.status === 201, `업로드 ${uploaded.status}`);
    const saved = await uploaded.json();
    expect(saved.markdown.includes("](<../assets/"), `링크가 감싸이지 않았습니다: ${saved.markdown}`);
    await api.patch(`/api/entries/${entry.id}`, { body: `## 내용\n\n측정 사진\n\n${saved.markdown}\n` });
    try {
      await go(`#/projects/${seeded.projectB}`);
      const image = page.locator(".timeline .entry .markdown img").first();
      expect((await image.count()) === 1, "본문에 그림이 서지 않았습니다");
      const loaded = await image.evaluate((el) => el.complete && el.naturalWidth > 0);
      expect(loaded, `그림이 열리지 않았습니다: ${await image.getAttribute("src")}`);
      // 미리보기(평문)에서도 링크가 한 덩이로 읽혀야 한다.
      expect(!(await page.locator(".timeline .entry .markdown").first().innerText()).includes("](<"), "링크 기호가 글자로 남았습니다");
    } finally {
      await api.delete(`/api/entries/${entry.id}`);
    }
  });

  await check("검색 결과를 떠나면 검색창이 비워진다", async () => {
    await go("#/search?q=" + encodeURIComponent("시제품"));
    equal(await page.locator(".search-box input").inputValue(), "시제품", "검색 화면의 검색창");
    await go("#/projects");
    equal(await page.locator(".search-box input").inputValue(), "", "떠난 뒤 검색창");
    await go("#/search?q=" + encodeURIComponent("시제품"));
    equal(await page.locator(".search-box input").inputValue(), "시제품", "돌아오면 주소의 검색어");
  });

  await check("설정 → 점검의 [첨부 링크 정리]가 세고 고친다 (TODO 116)", async () => {
    const entry = await api.post(`/api/projects/${seeded.projectB}/entries`, {
      date: dayFromToday(0), title: "옛 링크", body: "## 내용\n\n사진\n",
    });
    const png = Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
      "base64",
    );
    const form = new FormData();
    form.append("file", new Blob([png], { type: "image/png" }), "옛 사진.png");
    const saved = await (await fetch(`${BASE}/api/entries/${entry.id}/attachments`, { method: "POST", body: form })).json();
    // 114 이전 모양을 손으로 심는다 — 감싸지 않은 링크.
    const broken = saved.markdown.replace("](<", "](").replace(">)", ")");
    await api.patch(`/api/entries/${entry.id}`, { body: `## 내용\n\n사진\n\n${broken}\n` });
    try {
      await go("#/settings");
      const card = page.locator('[data-testid="link-fix"]');
      await card.getByRole("button", { name: "점검하기" }).click();
      await page.waitForTimeout(600);
      expect((await card.innerText()).includes("문서 1건 · 링크 1개"), `센 결과: ${await card.innerText()}`);
      await card.getByRole("button", { name: "고치기" }).click();
      await page.waitForTimeout(900);
      expect((await card.innerText()).includes("고쳤습니다"), "고친 뒤 안내");
      const body = (await api.get(`/api/entries/${entry.id}`)).body;
      expect(body.includes("](<../assets/"), `본문이 안 고쳐졌습니다: ${body}`);
      await card.getByRole("button", { name: "다시 세기" }).click();
      await page.waitForTimeout(600);
      expect((await card.innerText()).includes("고칠 링크가 없습니다"), "두 번째는 0건");
    } finally {
      await api.delete(`/api/entries/${entry.id}`);
    }
  });

  await check("설정 → 점검이 지금 무엇이 돌고 있는지 말한다 (TODO 117)", async () => {
    await go("#/settings");
    const line = await page.locator('[data-testid="build-line"]').innerText();
    // 시험은 저장소에서 돌므로 "배포본 아님". 배포본에서는 배포본-정보.txt 의 이름이 선다.
    expect(line.includes("저장소에서 바로 실행") || line.includes("지금 실행 중인 배포본"), `줄: ${line}`);
    const html = await (await fetch(`${BASE}/`)).headers.get("cache-control");
    expect(String(html).includes("no-cache"), `index.html 의 Cache-Control: ${html}`);
  });

  console.log("\n[18] 전배·퇴사한 담당자 (TODO 122)");
  await check("떠난 날을 적으면 홈이 대체 담당자를 찾으라고 알린다", async () => {
    const made = await api.post("/api/projects", {
      title: "담당자 공백 과제", status: "in_progress", owners: ["홍길동"],
    });
    const before = await api.get("/api/people");
    try {
      await api.put("/api/people", {
        people: [...before.people, { name: "홍길동", left_on: "2026-09-30", left_reason: "전배" }],
      });
      // 명부를 API 로 바꿨으므로 meta 를 다시 읽게 한다
      // (실제로는 설정 화면이 저장하면서 다시 읽는다).
      await page.reload({ waitUntil: "networkidle" });
      await go("#/");
      const band = page.locator('[data-testid="owner-gaps"]');
      equal(await band.count(), 1, "홈의 대체 담당자 줄");
      expect((await band.innerText()).includes("담당자 공백 과제"), "과제 이름");
      expect((await band.innerText()).includes("전배"), "사유 딱지");
      // 말한 수와 데려가는 목록이 같아야 한다 (DESIGN 5.8)
      // 주소에 back 이 함께 실린다 (TODO 127) — 앞부분으로 찾는다.
      const link = page.locator('.home-week a[href^="#/projects?owner_left=1"]').first();
      const said = Number((await link.innerText()).match(/(\d+)건/)[1]);
      await link.click();
      await page.waitForTimeout(900);
      equal(await page.locator("table.grid tbody tr").count(), said, "목록 줄 수");
      expect((await page.locator("table.grid tbody").innerText()).includes("전배"), "목록의 딱지");
    } finally {
      await api.put("/api/people", { people: before.people });
      await fetch(`${BASE}/api/projects/${made.id}/archive`, { method: "POST" });
    }
  });

  await check("명부에서 넘기면 끝난 과제는 그대로 두고 홈의 알림이 사라진다", async () => {
    const live = await api.post("/api/projects", {
      title: "넘길 과제", status: "in_progress", owners: ["홍길동"],
    });
    const done = await api.post("/api/projects", {
      title: "이미 끝난 과제", status: "done", owners: ["홍길동"],
    });
    const before = await api.get("/api/people");
    try {
      await api.put("/api/people", {
        people: [...before.people, { name: "홍길동", left_on: "2026-09-30", left_reason: "퇴사" }],
      });
      await page.reload({ waitUntil: "networkidle" });
      await go("#/settings");
      const card = page.locator(".card", { hasText: "담당자 명부" }).first();
      // 이름은 input 안에 있어 글자로는 찾히지 않는다 — 줄에 붙여 둔 이름으로 찾는다.
      const row = card.locator('tr[data-name="홍길동"]').first();
      expect((await row.innerText()).includes("남은 1건"), `남은 건수: ${await row.innerText()}`);
      // 넘기기는 prompt(받을 사람) → confirm 순이다. 위쪽 전역 handler 는 글자 없이 accept 만
      // 하므로 잠시 걷어내고 이 시험의 것으로 바꾼다 (끝나면 되돌린다).
      page.removeAllListeners("dialog");
      page.on("dialog", (dialog) =>
        dialog.type() === "prompt" ? dialog.accept("김현우") : dialog.accept(),
      );
      await row.getByRole("button", { name: "넘기기" }).click();
      await page.waitForTimeout(1500);
      equal((await api.get(`/api/projects/${live.id}`)).owners.join(), "김현우", "넘어간 과제");
      equal((await api.get(`/api/projects/${done.id}`)).owners.join(), "홍길동", "끝난 과제는 그대로");
      await go("#/");
      equal(await page.locator('[data-testid="owner-gaps"]').count(), 0, "알림이 사라진다");
    } finally {
      page.removeAllListeners("dialog");
      page.on("dialog", (dialog) => dialog.accept());
      await api.put("/api/people", { people: before.people });
      for (const item of [live, done]) {
        await fetch(`${BASE}/api/projects/${item.id}/archive`, { method: "POST" });
      }
    }
  });

  await check("명부에 찾기 칸과 스크롤이 있다 (TODO 121)", async () => {
    const before = await api.get("/api/people");
    const many = Array.from({ length: 12 }, (_, i) => ({ name: `시험담당${i + 1}` }));
    try {
      await api.put("/api/people", { people: [...before.people, ...many] });
      await go("#/settings");
      const card = page.locator(".card", { hasText: "담당자 명부" }).first();
      equal(await card.locator(".people-scroll").count(), 1, "스크롤 상자");
      const box = await card.locator(".people-scroll").boundingBox();
      expect(box.height <= 340, `목록 높이가 고정되지 않았습니다: ${box.height}`);
      await card.locator(".people-find input").fill("시험담당1");
      await page.waitForTimeout(300);
      // 시험담당1 · 10 · 11 · 12 넷이 남는다
      equal(await card.locator("tbody tr").count(), 4, "찾기 결과");
    } finally {
      await api.put("/api/people", { people: before.people });
    }
  });

  console.log("\n[19] 백업 층 보관 · 화면 배치 (TODO 119 · 120 · 123)");
  await check("백업 카드가 일·주·월 칸과 덮는 범위를 보여 준다", async () => {
    await go("#/settings");
    const card = page.locator(".card", { hasText: "자동 백업" }).first();
    const labels = await card.locator("label").allInnerTexts();
    for (const want of ["일", "주", "월"]) {
      expect(labels.some((text) => text.trim().startsWith(want)), `${want} 칸이 없습니다: ${labels}`);
    }
    // 백업 폴더가 정해져 있을 때만 목록이 선다 — 여기서는 칸이 있는지까지만 본다.
    expect((await card.innerText()).includes("네트워크 드라이브"), "안내 문구");
  });

  await check("설정의 서식 묶음은 접혀 있고 눌러서 편다 (TODO 120)", async () => {
    await go("#/settings");
    const fold = page.locator("details.settings-fold").first();
    equal(await fold.count(), 1, "접히는 묶음");
    equal(await fold.evaluate((el) => el.open), false, "기본은 접힘");
    // 접혀 있으면 안의 카드는 보이지 않는다 — 그만큼 세로가 짧아진다.
    equal(await fold.locator(".card").first().isVisible(), false, "접힌 동안 카드");
    await fold.locator("summary").click();
    await page.waitForTimeout(300);
    equal(await fold.locator(".card").first().isVisible(), true, "펼친 뒤 카드");
  });

  await check("홈의 연도별 추이가 팀 현황 아래 같은 칸에 선다 (TODO 123)", async () => {
    await go("#/");
    const right = page.locator(".home-right");
    equal(await right.count(), 1, "오른쪽 칸");
    equal(await right.locator(".home-team").count(), 1, "팀 현황");
    equal(await right.locator(".home-compare").count(), 1, "연도별 추이");
    // 두 칸이 나란히 서고, 오른쪽 아래의 빈 자리가 채워졌는지 — 높이 차이로 본다.
    const week = await page.locator(".home-week").boundingBox();
    const box = await right.boundingBox();
    expect(Math.abs(week.y - box.y) < 40, `두 칸이 같은 줄에서 시작하지 않습니다 (${week.y} vs ${box.y})`);
    expect(box.height > 0 && week.height > 0, "두 칸 모두 그려져야 한다");
    // 속성별·그룹별은 나란히
    const slices = page.locator(".home-slices:has(.home-slice-type)");
    equal(await slices.count(), 1, "속성별·그룹별 묶음");
  });

  console.log("\n[20] 효과 금액 분모 · 효과성 비대상 · 계정 칸 (TODO 124 · 125 · 126)");
  await check("홈의 효과 분모를 누르면 그 과제만 나온다 (TODO 124)", async () => {
    await go("#/");
    const note = page.locator(".home-stat.effect span.home-stat-note").first();
    const link = note.locator("a", { hasText: "기대" }).first();
    const said = Number((await link.innerText()).match(/(\d+)건/)[1]);
    await link.click();
    await page.waitForTimeout(900);
    equal(await page.locator("table.grid tbody tr").count(), said, "기대효과가 적힌 과제 수");
  });

  await check("효과성 관리 비대상은 [완료했는데 실증효과 미입력]에서 빠진다 (TODO 125)", async () => {
    const made = await api.post("/api/projects", {
      title: "유지보수 비대상 시험", status: "done", effect_expected: null,
    });
    try {
      await go("#/");
      const warn = page.locator(".home-stat.effect a.warn-text");
      const before = Number((await warn.innerText()).match(/(\d+)건/)[1]);
      // 과제 수정 화면에서 체크한다 — 서버만 고치면 화면을 안 본 것이 된다.
      await go(`#/projects/${made.id}`);
      await page.getByRole("button", { name: "과제 정보 수정" }).click();
      await page.waitForTimeout(400);
      await page.locator("label.check-label", { hasText: "효과성 관리 비대상" })
        .locator("input").check();
      await page.getByRole("button", { name: "저장" }).first().click();
      await page.waitForTimeout(1200);
      equal((await api.get(`/api/projects/${made.id}`)).no_effect, true, "저장된 값");
      await go("#/");
      const after = await page.locator(".home-stat.effect a.warn-text").count();
      const now = after === 0 ? 0 : Number((await warn.innerText()).match(/(\d+)건/)[1]);
      equal(now, before - 1, "경고에서 하나 빠진다");
      // 분모도 "전체" 가 아니라 "관리 대상" 으로 바뀐다.
      const note = await page.locator(".home-stat.effect span.home-stat-note").first().innerText();
      expect(note.includes("관리 대상"), `분모 문구: ${note}`);
    } finally {
      await fetch(`${BASE}/api/projects/${made.id}/archive`, { method: "POST" });
    }
  });

  await check("담당자 명부에 계정 칸이 없다 (TODO 126)", async () => {
    await go("#/settings");
    const card = page.locator(".card", { hasText: "담당자 명부" }).first();
    const heads = await card.locator("thead th").allInnerTexts();
    expect(!heads.includes("계정"), `계정 열이 남아 있습니다: ${heads.join("|")}`);
    expect(heads.includes("사번"), "사번 열은 그대로여야 한다");
  });

  await check("명부 표가 카드 밖으로 밀리지 않는다 (TODO 134)", async () => {
    await go("#/settings");
    const box = page.locator(".people-scroll");
    equal(await box.count(), 1, "명부 표 상자");

    // ① 가로 스크롤이 없어야 한다
    const size = await box.evaluate((el) => ({ scroll: el.scrollWidth, client: el.clientWidth }));
    expect(
      size.scroll <= size.client + 1,
      `가로로 ${size.scroll - size.client}px 밀렸다 (${size.scroll} > ${size.client})`,
    );

    // ② 칸이 서로 겹치지 않아야 한다. `<td>` 에 display:flex 를 걸면 그 칸이 표의 칸
    //    계산에서 빠져 **옆 칸과 같은 자리에** 그려진다 — 가로 스크롤은 안 생기므로
    //    ①만으로는 못 잡는다. 실제로 그래서 맨 오른쪽 단추가 안 보였다.
    const cells = await page.evaluate(() => {
      const row = document.querySelector(".people-table tbody tr");
      if (!row) return null;
      return [...row.children].map((c) => {
        const r = c.getBoundingClientRect();
        return { cls: c.className || "(없음)", x: Math.round(r.x), right: Math.round(r.right) };
      });
    });
    expect(cells !== null && cells.length === 5, `줄의 칸 수: ${cells ? cells.length : "없음"}`);
    for (let i = 1; i < cells.length; i += 1) {
      expect(
        cells[i].x >= cells[i - 1].right - 1,
        `칸이 겹쳤다: ${cells[i - 1].cls}(→${cells[i - 1].right}) 와 ${cells[i].cls}(${cells[i].x}→)`,
      );
    }
    // 마지막 칸이 상자 안에 있어야 보인다
    const edge = await box.evaluate((el) => Math.round(el.getBoundingClientRect().right));
    expect(cells[4].right <= edge + 1, `맨 오른쪽 칸이 상자 밖이다: ${cells[4].right} > ${edge}`);
  });

  console.log("\n[21] 홈에서 간 화면에서 돌아오는 길 (TODO 127)");
  await check("홈의 숫자를 누르면 목록에 ← 홈 이 선다", async () => {
    await go("#/");
    // 팀 현황의 [과제] — 홈에서 목록으로 가는 22곳 중 하나
    await page.locator(".home-team a.home-stat").first().click();
    await page.waitForTimeout(900);
    const back = page.locator(".project-list a.back").first();
    equal(await back.count(), 1, "뒤로 가기 줄");
    equal((await back.innerText()).trim(), "← 홈", "문구");
    await back.click();
    await page.waitForTimeout(900);
    expect((page.url().split("#")[1] ?? "").replace(/^\//, "") === "", `홈으로 안 왔습니다: ${page.url()}`);
  });

  await check("연도별 추이와 팀원별·속성별·그룹별도 같다", async () => {
    for (const [name, selector] of [
      ["연도별 추이", ".home-compare a.bar-col"],
      ["팀원별 성과", ".home-members tbody a"],
      ["속성별", ".home-slice-type tbody a"],
    ]) {
      await go("#/");
      const link = page.locator(selector).first();
      if ((await link.count()) === 0) continue; // 자료가 없으면 건너뛴다
      await link.click();
      await page.waitForTimeout(800);
      equal(await page.locator(".project-list a.back").count(), 1, `${name} 에서 온 뒤로 가기`);
    }
  });

  await check("조건을 더 걸어도 돌아갈 길이 남는다", async () => {
    await go("#/");
    await page.locator(".home-team a.home-stat").first().click();
    await page.waitForTimeout(900);
    // 목록에서 상태를 바꿔도 back 이 주소에서 사라지면 안 된다.
    await page.locator(".toolbar select").first().selectOption("in_progress");
    await page.waitForTimeout(700);
    expect(page.url().includes("back=home"), `주소에서 사라졌습니다: ${page.url()}`);
    equal(await page.locator(".project-list a.back").count(), 1, "뒤로 가기 줄");
  });

  await check("홈에서 과제를 열면 ← 홈, 메뉴로 열면 ← 과제 목록", async () => {
    await go("#/");
    const item = page.locator('.home-week a[href^="#/projects/"]').first();
    if (await item.count()) {
      await item.click();
      await page.waitForTimeout(900);
      const text = (await page.locator(".detail-header a.back, a.back").first().innerText()).trim();
      equal(text, "← 홈", "홈에서 연 과제");
    }
    // 목록에서 연 과제는 목록으로 돌아간다.
    await go("#/projects");
    await page.locator("table.grid tbody tr").first().click();
    await page.waitForTimeout(900);
    equal((await page.locator("a.back").first().innerText()).trim(), "← 과제 목록", "목록에서 연 과제");
  });

  await check("홈에서 설정에 들어가면 홈으로 돌아온다", async () => {
    await go("#/settings?back=home");
    equal((await page.locator(".settings a.back").first().innerText()).trim(), "← 홈", "설정의 뒤로");
    // 메뉴로 들어오면 그리지 않는다 — 다른 메뉴 화면과 같은 규칙 (TODO 153. 전에는 "← 과제 목록" 이 섰다)
    await go("#/settings");
    equal(await page.locator(".settings a.back").count(), 0, "메뉴로 들어간 설정의 뒤로 가기");
  });

  console.log("\n[22] 보고대상·보고이력·팀원역량의 뒤로 가기 · 보고 첨부 삭제 (TODO 128 · 129)");
  await check("홈에서 간 세 화면에도 ← 홈 이 선다 (TODO 128)", async () => {
    for (const [name, selector, screen] of [
      ["보고 대상", '.home-week a[href^="#/reports"]', "candidates"],
      ["보고 이력", '.home-team a[href^="#/history"]', "report-history"],
      ["팀원 역량", '.home-members a[href^="#/skills"]', "skills"],
    ]) {
      await go("#/");
      const link = page.locator(selector).first();
      if ((await link.count()) === 0) continue; // 자료가 없으면 건너뛴다
      await link.click();
      await page.waitForTimeout(900);
      const back = page.locator(`.${screen} a.back`).first();
      equal(await back.count(), 1, `${name} 의 뒤로 가기`);
      equal((await back.innerText()).trim(), "← 홈", `${name} 의 문구`);
    }
  });

  await check("메뉴로 들어가면 그 줄을 그리지 않는다", async () => {
    for (const [hash, screen] of [
      ["#/reports", "candidates"],
      ["#/history", "report-history"],
      ["#/skills", "skills"],
    ]) {
      await go(hash);
      equal(await page.locator(`.${screen} a.back`).count(), 0, `${hash} 에는 없어야 한다`);
    }
  });

  await check("보고이력에서 조건을 바꿔도 돌아갈 길이 남는다", async () => {
    await go("#/");
    const link = page.locator('.home-team a[href^="#/history"]').first();
    if ((await link.count()) === 0) return;
    await link.click();
    await page.waitForTimeout(900);
    await page.locator(".report-history select").first().selectOption("frozen");
    await page.waitForTimeout(700);
    expect(page.url().includes("back=home"), `주소에서 사라졌습니다: ${page.url()}`);
    equal(await page.locator(".report-history a.back").count(), 1, "뒤로 가기 줄");
  });

  await check("보고 초안의 첨부를 지울 수 있다 (TODO 129)", async () => {
    const made = await api.post(`/api/projects/${seeded.projectA}/reports/draft`, {
      report_date: dayFromToday(3),
    });
    const png = Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
      "base64",
    );
    const form = new FormData();
    form.append("file", new Blob([png], { type: "image/png" }), "지울첨부.png");
    const uploaded = await fetch(`${BASE}/api/reports/${made.id}/attachments`, { method: "POST", body: form });
    expect(uploaded.status === 201, `업로드 ${uploaded.status}`);
    try {
      await go(`#/projects/${seeded.projectA}?report=${made.id}`);
      const row = page.locator(".report-editor .attachments li").first();
      equal(await row.count(), 1, "첨부 줄");
      const remove = row.getByRole("button", { name: "삭제" });
      equal(await remove.count(), 1, "삭제 단추");
      await remove.click();
      await page.waitForTimeout(1200);
      equal((await api.get(`/api/reports/${made.id}/attachments`)).length, 0, "서버에서도 빠진다");
    } finally {
      await api.delete(`/api/reports/${made.id}`);
    }
  });

  await check("확정된 보고에는 삭제 단추가 없다", async () => {
    const reports = await api.get(`/api/projects/${seeded.projectA}/reports`);
    const frozen = reports.find((item) => item.frozen);
    await go(`#/projects/${seeded.projectA}?report=${frozen.id}`);
    const rows = page.locator(".report-editor .attachments li");
    if ((await rows.count()) === 0) return; // 첨부가 없으면 볼 것이 없다
    equal(await rows.first().getByRole("button", { name: "삭제" }).count(), 0, "확정 보고의 삭제 단추");
  });

  console.log("\n[23] 이름과 나이테 표시 (TODO 132)");

  await check("탭 제목과 화면 머리가 «느린 나이테» 다", async () => {
    await go("#/");
    // 탭 제목은 화면 이름 · 도구 이름 (TODO 169 — 탭 여러 개를 구분하려고)
    equal(await page.title(), "홈 · 느린 나이테", "탭 제목");
    const brand = page.locator(".app-header .brand");
    equal((await brand.innerText()).trim(), "느린 나이테", "화면 머리의 이름");
    // 표시가 글자 옆에 실제로 그려졌는가 — 주소만 맞고 안 뜨는 경우를 잡는다.
    const mark = brand.locator("img.brand-mark");
    equal(await mark.count(), 1, "나이테 표시");
    const box = await mark.boundingBox();
    expect(box !== null && box.width >= 16, `표시가 그려지지 않았다: ${JSON.stringify(box)}`);
  });

  await check("표시 파일 셋이 서버에서 제 형식으로 내려온다", async () => {
    // public/ 의 파일은 assets 묶음과 달리 이름이 그대로다. SPA 되돌림이 이것까지
    // index.html 로 덮으면 표시가 사라진다 — 형식까지 본다.
    for (const [path, type] of [
      ["/favicon.svg", "image/svg+xml"],
      ["/favicon.ico", "image/"],
      ["/icon-180.png", "image/png"],
    ]) {
      const response = await fetch(BASE + path);
      equal(response.status, 200, `${path} 의 응답`);
      const got = response.headers.get("content-type") ?? "";
      expect(got.startsWith(type), `${path} 의 형식: ${got}`);
    }
  });

  console.log("\n[24] 과제 접수 풀 — 등록 · 검토 · 판정 · 승격 (TODO 136)");

  let intakeId = null;
  await check("[접수] 메뉴가 과제목록 앞에 서고 풀이 열린다", async () => {
    await go("#/");
    const menu = await page.locator(".app-header nav a").allInnerTexts();
    const at = menu.findIndex((text) => text.trim() === "접수");
    expect(at >= 0, `메뉴에 접수가 없다: ${menu.join(" | ")}`);
    expect(menu[at + 1]?.trim() === "과제목록", `접수 다음이 과제목록이 아니다: ${menu.join(" | ")}`);
    await go("#/intakes");
    equal(await page.locator(".intake-pool h1").innerText(), "접수", "화면 제목");
  });

  await check("[+ 접수 등록] 으로 만들면 번호가 붙고 상세로 간다", async () => {
    await go("#/intakes");
    await page.getByRole("button", { name: "접수 등록", exact: true }).click();
    const form = page.locator(".intake-pool form").first();
    await form.locator("label", { hasText: "과제명" }).locator("input").fill("압연 두께 편차 예측");
    await form.locator('input[placeholder="예: 홍길동"]').fill("현업담당");
    await form.locator('input[placeholder="예: 압연기술팀"]').fill("압연기술팀");
    await form.locator('input[placeholder="요청자 추정"]').fill("2.5");
    await form.getByRole("button", { name: "접수 등록" }).click();
    await page.waitForFunction(() => location.hash.startsWith("#/intakes/"), null, { timeout: 5000 });
    await page.waitForTimeout(700);
    intakeId = decodeURIComponent(page.url().split("#/intakes/")[1].split("?")[0]);
    expect(/^R\d{4}-(.+-)?\d{3}$/.test(intakeId), `접수 번호 모양: ${intakeId}`);
    expect((await page.locator(".intake-detail .detail-header").innerText()).includes("압연 두께 편차 예측"), "제목");
    // 기본 서식이 요청 내용에 깔려 있어야 한다 — 비어 있으면 무엇을 적을지 모른다.
    const body = await page.locator(".intake-detail .intake-body").innerText();
    for (const heading of ["배경", "목표", "효과 산출 근거", "추진내용", "활용 방안"]) {
      expect(body.includes(heading), `서식에 ${heading} 이(가) 없다`);
    }
  });

  await check("풀에 서고 ★ 로 착수 후보를 고를 수 있다", async () => {
    await go("#/intakes");
    const row = page.locator(`tr[data-intake="${intakeId}"]`);
    equal(await row.count(), 1, "풀의 줄");
    await row.locator("button.star").click();
    await page.waitForTimeout(700);
    equal((await api.get(`/api/intakes/${encodeURIComponent(intakeId)}`)).picked, true, "서버의 ★");
    await page.locator(".picked-filter input").check();
    await page.waitForTimeout(700);
    equal(await page.locator("tr[data-intake]").count(), 1, "★ 만 거르면 한 줄");
    await page.locator(".picked-filter input").uncheck();
  });

  await check("반려는 사유 없이는 안 되고, 재검토로 풀에 되돌아온다", async () => {
    await go(`#/intakes/${encodeURIComponent(intakeId)}`);
    await page.locator(".decision-bar").getByRole("button", { name: "반려", exact: true }).click();
    const confirm = page.locator(".decision-panel").getByRole("button", { name: "반려(으)로 정리" });
    expect(await confirm.isDisabled(), "사유가 비었는데 누를 수 있다");
    await page.locator(".decision-panel textarea").fill("시험 반려");
    await confirm.click();
    await page.waitForTimeout(900);
    expect((await page.locator(".decision-line").innerText()).includes("시험 반려"), "판정 사유");
    // 닫힌 건에는 승격 단추가 없다
    equal(await page.getByRole("button", { name: "착수 · 과제로 승격" }).count(), 0, "닫힌 건의 승격 단추");
    await page.getByRole("button", { name: "재검토 (풀로 되돌리기)" }).click();
    await page.waitForTimeout(900);
    equal((await api.get(`/api/intakes/${encodeURIComponent(intakeId)}`)).status, "reviewing", "재검토 뒤 상태");
    // 판정의 흔적은 검토 기록에 남는다
    expect((await page.locator(".intake-logs").innerText()).includes("시험 반려"), "검토 기록의 판정 줄");
  });

  let promoted = null;
  await check("승격 — 명부에 없는 리더는 유관부서, 요청 효과는 참고로만", async () => {
    await api.patch(`/api/intakes/${encodeURIComponent(intakeId)}`, {
      body: "## 배경 (과제배경)\n\n두께 편차 클레임\n\n## 추진내용\n\n모델 개발\n\n## 공정 설명\n\n압연 3단\n",
    });
    await go(`#/intakes/${encodeURIComponent(intakeId)}`);
    await page.getByRole("button", { name: "착수 · 과제로 승격" }).click();
    const dialog = page.locator(".promote-dialog");
    await dialog.waitFor();
    // 대화상자는 먼저 서고 미리 채울 값(plan)은 뒤따라 온다 — 채워진 뒤에 읽는다
    await dialog.locator(".next-id").first().waitFor({ timeout: 5000 });
    const text = await dialog.innerText();
    expect(text.includes("요청자 추정"), "요청 효과 참고 문구");
    const owners = await dialog.locator("label", { hasText: "담당자" }).locator("input").first().inputValue();
    equal(owners, "", "명부에 없는 리더가 담당자로 들어갔다");
    const partnerTeam = await dialog.locator(".partner-row input").first().inputValue();
    equal(partnerTeam, "압연기술팀", "유관부서 줄");
    // 저장 단추가 대화상자 안에서 보인다 (길어져도 아래에 붙어 있다)
    const submit = dialog.getByRole("button", { name: "승격하고 과제 열기" });
    expect(await submit.isVisible(), "승격 단추가 보이지 않는다");
    await submit.click();
    await page.waitForFunction(() => location.hash.startsWith("#/projects/"), null, { timeout: 5000 });
    await page.waitForTimeout(900);
    promoted = page.url().split("#/projects/")[1].split("?")[0];
    const project = await api.get(`/api/projects/${promoted}`);
    equal(project.intake_id, intakeId, "과제의 접수 번호");
    equal(project.effect_expected ?? null, null, "요청 효과가 과제 기대효과로 넘어갔다");
    expect(project.body.includes("두께 편차 클레임"), "배경이 제자리로 옮겨지지 않았다");
    expect(project.body.includes("## 접수 내용") && project.body.includes("압연 3단"), "남는 섹션 모음");
  });

  await check("과제와 접수가 서로 링크된다", async () => {
    const link = page.locator(".intake-line a.intake-link");
    equal(await link.count(), 1, "과제 상세의 접수 링크");
    await link.click();
    await page.waitForTimeout(900);
    expect(page.url().includes(`#/intakes/${encodeURIComponent(intakeId)}`), `접수로 가지 않았다: ${page.url()}`);
    const back = page.locator(".intake-detail a.back").first();
    equal((await back.innerText()).trim(), "← 과제", "되돌아갈 곳");
    const line = await page.locator(".decision-line").innerText();
    expect(line.includes(promoted), `착수 줄에 과제 번호가 없다: ${line}`);
  });

  await check("과제목록 [등록 경로] 로 접수에서 온 과제만 거른다", async () => {
    const rows = await api.get("/api/projects?from_intake=yes");
    equal(rows.length, 1, "접수에서 온 과제 수");
    await go("#/projects?year=all&from_intake=yes");
    expect((await page.locator(".project-list, .projects").first().innerText()).includes("압연 두께 편차 예측"), "목록 줄");
  });

  await check("분류 넷 상자는 스마트과제를 골랐을 때만 선다", async () => {
    // 늘 세우면 거르기 줄이 두 줄로 넘어간다 — 다른 속성을 볼 때는 쓸 일이 없다.
    await go("#/projects");
    equal(await page.locator('.filters select[aria-label="성격"]').count(), 0, "기본 화면의 성격 상자");
    await go("#/projects?type=smart");
    equal(await page.locator('.filters select[aria-label="성격"]').count(), 1, "스마트과제의 성격 상자");
    // 홈·과제 상세에서 분류로 걸러 왔으면 속성과 상관없이 보여야 한다 — 걸린 조건이 숨으면 안 된다.
    await go("#/projects?category=" + encodeURIComponent("스마트 센싱"));
    equal(await page.locator('.filters select[aria-label="분류"]').inputValue(), "스마트 센싱", "걸린 분류");
  });

  await check("홈의 접수 풀 칸 = 풀 화면의 줄 수", async () => {
    const made = await api.post("/api/intakes", { title: "홈 확인용 접수", received_on: dayFromToday(-1) });
    try {
      await go("#/");
      const stat = page.locator(".intake-stat");
      equal(await stat.count(), 1, "접수 풀 칸");
      const shown = Number((await stat.locator("strong").innerText()).replace(/\D/g, ""));
      await stat.click();
      await page.waitForTimeout(900);
      equal(await page.locator("tr[data-intake]").count(), shown, "풀의 줄 수");
    } finally {
      await fetch(`${BASE}/api/intakes/${encodeURIComponent(made.id)}/archive`, { method: "POST" }); // 204 — 본문 없음
    }
  });

  await check("설정에 분류 목록 · 접수 서식 칸이 있고 도움말에 접수 흐름이 있다", async () => {
    await go("#/settings");
    const card = page.locator(".intake-settings");
    await page.locator("summary", { hasText: "과제 분류" }).first().click().catch(() => undefined);
    equal(await card.count(), 1, "설정 카드");
    equal(await card.locator(".class-lists textarea").count(), 4, "분류 목록 넷");
    await go("#/help");
    expect((await page.locator(".help").innerText()).includes("과제 접수 흐름"), "도움말 절");
  });

  console.log("\n[25] 붙여넣기 · 첨부 판 · 접수 번호 · 병합 목록 · 2단 · 검색 (TODO 137~144)");

  /**
   * 가짜 클립보드로 붙여넣는다 — 엑셀처럼 **표 HTML · 탭 글 · 그림을 함께** 담을 수 있다.
   * 한 편집기만 보는 시험은 나머지 편집기를 놓친다(137 이 그렇게 샜다). 그래서 편집기 목록 전부에 흘린다.
   */
  async function pasteInto(selector, { html = "", text = "", image = false }) {
    await page.locator(selector).first().evaluate(
      (el, a) => {
        const dt = new DataTransfer();
        if (a.html) dt.setData("text/html", a.html);
        if (a.text) dt.setData("text/plain", a.text);
        if (a.image) {
          const png = Uint8Array.from(atob(a.png), (c) => c.charCodeAt(0));
          dt.items.add(new File([png], "image.png", { type: "image/png" }));
        }
        el.focus();
        el.setSelectionRange(el.value.length, el.value.length);
        el.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
      },
      {
        html, text, image,
        png: "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
      },
    );
    await page.waitForTimeout(400);
  }
  // 엑셀 셀 복사와 같은 모양 — 셀 안 줄바꿈(<br>)과 병합 셀(colspan)까지
  const EXCEL = {
    html:
      "<html><body><table><tr><td>항목</td><td>값</td></tr>" +
      "<tr><td>온도<br style='mso-data-placement:same-cell'>편차</td><td>12</td></tr>" +
      "<tr><td colspan=2>합계</td></tr></table></body></html>",
    text: '항목\t값\n"온도\n편차"\t12\n합계\t\n',
    image: true,
  };
  function expectTable(value, where) {
    expect(value.includes("| 항목 | 값 |"), `${where}: 표 머리가 없다 — ${value.slice(-160)}`);
    expect(value.includes("| 온도<br>편차 | 12 |"), `${where}: 셀 안 줄바꿈이 깨졌다 — ${value.slice(-160)}`);
    expect(value.includes("| 합계 |  |"), `${where}: 병합 셀 — ${value.slice(-160)}`);
    expect(!value.includes("image.png") && !value.includes("⏳"), `${where}: 그림으로 들어갔다`);
  }

  const pasteIntake = await api.post("/api/intakes", { title: "붙여넣기 확인 접수", leader: "현업이", leader_team: "품질팀" });
  const pasteIntakeHash = `#/intakes/${encodeURIComponent(pasteIntake.id)}`;

  await check("엑셀 표는 편집기 다섯 곳 모두에서 표로 들어간다 — 그림이 아니라 (TODO 137)", async () => {
    // 1. 진행일지
    await go(`#/projects/${seeded.projectA}`);
    await page.getByRole("button", { name: "기록 추가" }).click();
    await page.waitForTimeout(500);
    await pasteInto(".entry-editor textarea", EXCEL);
    expectTable(await page.locator(".entry-editor textarea").first().inputValue(), "진행일지");
    // 2. 과제 개요 — 표가 **커서 자리**에 들어가는지도 본다(예전에는 맨 끝)
    await go(`#/projects/${seeded.projectA}`);
    await page.locator(".card").filter({ hasText: "과제 개요" }).getByRole("button", { name: "수정" }).click();
    await page.waitForTimeout(500);
    const overview = page.locator(".card").filter({ hasText: "과제 개요" }).locator("textarea").first();
    await overview.fill("첫 줄\n끝 줄");
    await overview.evaluate((el) => el.setSelectionRange(3, 3));
    await overview.evaluate(
      (el, html) => {
        const dt = new DataTransfer();
        dt.setData("text/html", html);
        el.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
      },
      EXCEL.html,
    );
    await page.waitForTimeout(300);
    const text = await overview.inputValue();
    expectTable(text, "과제 개요");
    expect(text.trim().endsWith("끝 줄"), `표가 커서 자리가 아니라 끝에 붙었다: ${text}`);
    await page.locator(".card").filter({ hasText: "과제 개요" }).getByRole("button", { name: "취소" }).click().catch(() => {});
    // 3. 보고
    const draft = await api.post(`/api/projects/${seeded.projectA}/reports/draft`, { report_date: dayFromToday(5) });
    try {
      await go(`#/projects/${seeded.projectA}?report=${draft.id}`);
      await pasteInto(".report-editor textarea", EXCEL);
      expectTable(await page.locator(".report-editor textarea").first().inputValue(), "보고");
    } finally {
      await api.delete(`/api/reports/${draft.id}`);
    }
    // 4 · 5. 접수 요청 내용 · 검토 기록
    await go(pasteIntakeHash);
    await page.locator(".intake-body").getByRole("button", { name: "수정" }).click();
    await page.waitForTimeout(400);
    await pasteInto(".body-editor textarea", EXCEL);
    expectTable(await page.locator(".body-editor textarea").first().inputValue(), "접수 요청 내용");
    await page.locator(".body-editor").getByRole("button", { name: "취소" }).click();
    await page.getByRole("button", { name: "기록 추가" }).click();
    await page.waitForTimeout(400);
    await pasteInto(".log-editor textarea", EXCEL);
    expectTable(await page.locator(".log-editor textarea").first().inputValue(), "접수 검토 기록");
    await page.locator(".log-editor").getByRole("button", { name: "취소" }).click();
    // 편집기에서 올라간 첨부가 없어야 한다
    equal((await api.get(`/api/intakes/${encodeURIComponent(pasteIntake.id)}`)).attachments.length, 0, "올라간 첨부");
  });

  await check("캡처(그림만)는 여전히 첨부로 올라간다", async () => {
    await go(pasteIntakeHash);
    await page.locator(".intake-body").getByRole("button", { name: "수정" }).click();
    await page.waitForTimeout(400);
    await pasteInto(".body-editor textarea", { image: true });
    await page.waitForTimeout(900);
    const value = await page.locator(".body-editor textarea").first().inputValue();
    expect(value.includes("![image.png]("), `그림 링크가 없다: ${value.slice(-120)}`);
    equal((await api.get(`/api/intakes/${encodeURIComponent(pasteIntake.id)}`)).attachments.length, 1, "올라간 첨부");
    await page.locator(".body-editor").getByRole("button", { name: "취소" }).click();
  });

  await check("접수의 편집기 둘과 첨부 카드에 📎 · [본문에 삽입] 이 있다 (TODO 138)", async () => {
    await go(pasteIntakeHash);
    equal(await page.locator(".intake-files .attach-button").count(), 1, "첨부 카드의 📎");
    await page.locator(".intake-body").getByRole("button", { name: "수정" }).click();
    await page.waitForTimeout(400);
    equal(await page.locator(".body-editor .attach-button").count(), 1, "요청 내용 편집기의 📎");
    const before = await page.locator(".body-editor textarea").first().inputValue();
    await page.locator(".body-editor .attachments li").first().getByRole("button", { name: "본문에 삽입" }).click();
    const after = await page.locator(".body-editor textarea").first().inputValue();
    expect(after.length > before.length && after.includes("assets/"), "본문에 삽입이 링크를 넣지 않았다");
    await page.locator(".body-editor").getByRole("button", { name: "취소" }).click();
    await page.getByRole("button", { name: "기록 추가" }).click();
    await page.waitForTimeout(400);
    equal(await page.locator(".log-editor .attach-button").count(), 1, "검토 기록 편집기의 📎");
    // 검토 기록 편집기에는 그 기록의 첨부만 선다(150) — 여기서 하나 올린 뒤 [본문에 삽입]
    await pasteInto(".log-editor textarea", { image: true });
    await page.waitForTimeout(900);
    await page.locator(".log-editor .attachments li").first().getByRole("button", { name: "본문에 삽입" }).click();
    const log = await page.locator(".log-editor textarea").first().inputValue();
    // 검토 기록은 logs/ 안에 있어 링크가 ../assets/… 여야 한다
    expect(log.includes("../assets/"), `검토 기록의 링크 기준이 틀렸다: ${log}`);
    await page.locator(".log-editor").getByRole("button", { name: "취소" }).click();
  });

  await check("새 접수를 등록할 때 파일을 함께 올린다 (TODO 138)", async () => {
    await go("#/intakes");
    await page.getByRole("button", { name: "접수 등록", exact: true }).click();
    const form = page.locator(".intake-pool form").first();
    await form.locator("label", { hasText: "과제명" }).locator("input").fill("파일 들고 온 접수");
    await form.locator('.intake-form-files input[type="file"]').setInputFiles({
      name: "과제정의서.pptx",
      mimeType: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
      buffer: Buffer.from("PK fake pptx"),
    });
    expect((await form.locator(".intake-form-file-list").innerText()).includes("과제정의서.pptx"), "고른 파일 목록");
    await form.getByRole("button", { name: "접수 등록" }).click();
    await page.waitForFunction(() => location.hash.startsWith("#/intakes/R"), null, { timeout: 5000 });
    await page.waitForTimeout(900);
    const made = decodeURIComponent(page.url().split("#/intakes/")[1].split("?")[0]);
    const detail = await api.get(`/api/intakes/${encodeURIComponent(made)}`);
    equal(detail.attachments.length, 1, "등록과 함께 올라간 첨부");
    equal(detail.attachments[0].orig_name, "과제정의서.pptx", "첨부 이름");
    await fetch(`${BASE}/api/intakes/${encodeURIComponent(made)}/archive`, { method: "POST" });
  });

  await check("풀의 접수 번호는 본문 크기 · 한 줄이다 (TODO 139)", async () => {
    await go("#/intakes");
    const cell = page.locator(`tr[data-intake="${pasteIntake.id}"] td.intake-id`);
    equal(await cell.count(), 1, "번호 칸");
    const size = await cell.evaluate((el) => parseFloat(getComputedStyle(el.querySelector("a")).fontSize));
    expect(size >= 12, `번호 글자가 작다: ${size}px`);
    const lines = await cell.evaluate((el) => {
      const a = el.querySelector("a");
      return Math.round(a.getBoundingClientRect().height / parseFloat(getComputedStyle(a).lineHeight || "18"));
    });
    expect(lines <= 1, `번호가 ${lines}줄로 꺾였다`);
  });

  await check("병합 — 흡수할 과제 목록이 서고 끝까지 정리된다 (TODO 140)", async () => {
    const target = await api.post("/api/intakes", { title: "병합할 접수" });
    const hash = `#/intakes/${encodeURIComponent(target.id)}`;
    await go(hash);
    await page.locator(".decision-bar").getByRole("button", { name: "병합", exact: true }).click();
    await page.waitForTimeout(900);
    // 찾기 칸 + 번호순 목록 (TODO 151) — 목록이 비면 못 받은 것이다(140)
    const options = page.locator(".decision-panel .merge-option");
    expect((await options.count()) > 0, "고를 과제가 없다 — 목록을 못 받았다");
    await page.locator('.decision-panel input[type="search"]').fill(seeded.projectB);
    equal(await options.count(), 1, "번호로 찾은 과제 수");
    await options.first().click();
    await page.locator(".decision-panel").getByRole("button", { name: "병합(으)로 정리" }).click();
    await page.waitForTimeout(900);
    expect((await page.locator(".decision-line").innerText()).includes(seeded.projectB), "판정 줄의 과제");
    const project = await api.get(`/api/projects/${seeded.projectB}`);
    expect(project.intakes.some((row) => row.id === target.id && row.relation === "merged"), "과제 쪽 링크");
  });

  await check("접수 상세는 2단 — 왼쪽 요청·첨부, 오른쪽 검토 기록. 편집 중에는 1단 (TODO 141)", async () => {
    await go(pasteIntakeHash);
    const left = await page.locator(".intake-columns .detail-left").boundingBox();
    const right = await page.locator(".intake-columns .detail-right").boundingBox();
    expect(right.x >= left.x + left.width - 1 && Math.abs(right.y - left.y) < 4, `나란히 서지 않는다: ${JSON.stringify({ left, right })}`);
    equal(await page.locator(".intake-columns .detail-left .intake-files").count(), 1, "첨부는 왼쪽");
    equal(await page.locator(".intake-columns .detail-right .intake-logs").count(), 1, "검토 기록은 오른쪽");
    await page.getByRole("button", { name: "기록 추가" }).click();
    await page.waitForTimeout(400);
    const r2 = await page.locator(".intake-columns .detail-right").boundingBox();
    const l2 = await page.locator(".intake-columns .detail-left").boundingBox();
    expect(r2.y < l2.y && r2.width > 1000, `편집 중인 오른쪽이 넓게 위로 오지 않았다: ${JSON.stringify({ l2, r2 })}`);
    await page.locator(".log-editor").getByRole("button", { name: "취소" }).click();
  });

  await check("요청 내용의 [이전 버전] — 제목을 고쳐도 남는다 (TODO 142 · 143)", async () => {
    const id = encodeURIComponent(pasteIntake.id);
    await api.patch(`/api/intakes/${id}`, { body: "## 배경\n\n처음 정의\n" });
    await api.patch(`/api/intakes/${id}`, { body: "## 배경\n\n인터뷰 뒤 바뀐 정의\n" });
    await api.patch(`/api/intakes/${id}`, { title: "붙여넣기 확인 접수 (범위 조정)" });
    await go(pasteIntakeHash);
    await page.locator(".intake-body").getByRole("button", { name: "이전 버전" }).click();
    await page.waitForTimeout(700);
    const dir = (await api.get(`/api/intakes/${id}`)).dir_name;
    const versions = await api.get(`/api/versions?path=${encodeURIComponent(`intakes/${dir}/request.md`)}`);
    expect(versions.items.length >= 2, `이름을 바꾼 뒤 이전 버전이 ${versions.items.length}벌`);
    equal(await page.locator(".intake-body .version-panel").count(), 1, "요청 내용의 버전 목록");
    // 제목만 바꾼 저장은 본문이 같아 접힌다(152) — 본문이 바뀐 버전이 목록에 선다
    const shown = versions.items.find((item) => item.body_changed !== false);
    expect((await page.locator(".intake-body .version-panel").innerText()).includes(shown.saved_at), "버전 목록의 시각");
    expect((await page.locator(".intake-body .version-panel").innerText()).includes("정보만 바뀐 저장"), "접힌 줄");
  });

  await check("검색창으로 접수도 찾는다 — 소속·과제리더로도 (TODO 144)", async () => {
    await go(`#/search?q=${encodeURIComponent("품질팀")}`);
    const card = page.locator(".search-results .card").filter({ hasText: "접수" });
    expect((await card.innerText()).includes(pasteIntake.id), "검색 결과의 접수");
    await card.locator("a").first().click();
    await page.waitForTimeout(800);
    equal((await page.locator(".intake-detail a.back").innerText()).trim(), "← 검색 결과", "되돌아갈 곳");
  });

  console.log("\n[26] 과제 삭제와 접수 연결 · 화면 통일 (TODO 145 · 147)");

  await check("접수에서 온 과제를 지우려 하면 [중단]을 먼저 권하고, 지우면 접수가 풀로 (TODO 145)", async () => {
    const made = await api.post("/api/intakes", { title: "지울 과제의 접수" });
    const id = encodeURIComponent(made.id);
    const promoted = await api.post(`/api/intakes/${id}/promote`, { owners: ["권경락"] });
    await go(`#/projects/${promoted.project_id}`);
    await page.locator(".detail-actions, .card").first().getByRole("button", { name: "삭제", exact: true }).first().click();
    const panel = page.locator(".archive-panel");
    await panel.waitFor({ timeout: 3000 });
    expect((await panel.innerText()).includes(made.id), "판에 접수 번호가 없다");
    equal(await panel.getByRole("button", { name: "중단으로 바꾸기" }).count(), 1, "[중단으로 바꾸기]");
    await panel.getByRole("button", { name: "그래도 삭제" }).click();
    await page.waitForTimeout(1000);
    const intake = await api.get(`/api/intakes/${id}`);
    equal(intake.status, "reviewing", "지운 뒤 접수 상태");
    equal(intake.project_id, null, "지운 뒤 접수의 과제 번호");
  });

  await check("메뉴 화면의 제목은 한 모양이다 — 20px (TODO 147)", async () => {
    const sizes = {};
    for (const hash of ["#/", "#/intakes", "#/projects", "#/reports", "#/history", "#/skills", "#/settings", "#/help"]) {
      await go(hash);
      const h1 = page.locator("main h1, section h1").first();
      equal(await h1.count(), 1, `${hash} 에 제목이 없다`);
      sizes[hash] = await h1.evaluate((el) => getComputedStyle(el).fontSize);
    }
    const kinds = new Set(Object.values(sizes));
    equal(kinds.size, 1, `제목 크기가 갈린다: ${JSON.stringify(sizes)}`);
  });

  await check("거르기 줄의 상자 높이가 화면마다 같다 · 접수 표도 같은 표 모양 (TODO 147)", async () => {
    const heights = new Set();
    for (const hash of ["#/intakes", "#/projects", "#/reports", "#/skills"]) {
      await go(hash);
      for (const h of await page.locator(".filters select, .filters input:not([type=checkbox])").evaluateAll(
        (els) => els.filter((el) => el.offsetParent).map((el) => Math.round(el.getBoundingClientRect().height)),
      )) heights.add(h);
    }
    equal(heights.size, 1, `상자 높이가 갈린다: ${[...heights].join(", ")}`);
    await go("#/intakes");
    equal(await page.locator("table.grid.intake-table").count(), 1, "접수 표의 모양");
  });

  console.log("\n[27] 표 칸 줄바꿈 · 그림으로 바꾸기 · 검토 기록 첨부 · 병합 찾기 · 화면 머리 · 접수 표 (TODO 148~154)");

  await check("표 칸 안의 <br> 은 줄바꿈으로, 속성 붙은 태그는 글자로 (TODO 148)", async () => {
    await go(`#/projects/${seeded.projectA}`);
    await page.locator(".card").filter({ hasText: "과제 개요" }).getByRole("button", { name: "수정" }).click();
    await page.waitForTimeout(400);
    const box = page.locator(".card").filter({ hasText: "과제 개요" }).locator("textarea").first();
    await box.fill("| 항목 | 값 |\n|---|---|\n| 온도<br>편차 | 12 |\n\n<br onclick=\"x\">\n");
    await page.waitForTimeout(300);
    const preview = page.locator(".card").filter({ hasText: "과제 개요" }).locator(".preview");
    equal(await preview.locator("td br").count(), 1, "칸 안 줄바꿈");
    expect((await preview.innerText()).includes("<br onclick"), "속성 붙은 태그가 글자로 남지 않았다");
    await page.locator(".card").filter({ hasText: "과제 개요" }).getByRole("button", { name: "취소" }).click().catch(() => {});
    await go(`#/projects/${seeded.projectA}`);
  });

  await check("엑셀 표를 붙이면 [그림으로 바꾸기] — 누르면 표 대신 그림 링크 (TODO 149)", async () => {
    const made = await api.post("/api/intakes", { title: "그림으로 바꾸기 확인" });
    await go(`#/intakes/${encodeURIComponent(made.id)}`);
    await page.locator(".intake-body").getByRole("button", { name: "수정" }).click();
    await page.waitForTimeout(400);
    await page.locator(".body-editor textarea").first().fill("");
    await pasteInto(".body-editor textarea", EXCEL);
    const offer = page.locator(".body-editor .paste-offer");
    equal(await offer.count(), 1, "[그림으로 바꾸기] 줄");
    await offer.getByRole("button", { name: "그림으로 바꾸기" }).click();
    await page.waitForTimeout(1500);
    const value = await page.locator(".body-editor textarea").first().inputValue();
    expect(!value.includes("| 항목 | 값 |"), `표가 남았다: ${value}`);
    expect(value.includes("![image.png]("), `그림 링크가 없다: ${value}`);
    equal(await offer.count(), 0, "누른 뒤에는 줄이 사라진다");
    // 그림 없이 표만 온 붙여넣기에는 권하지 않는다
    await pasteInto(".body-editor textarea", { html: EXCEL.html, text: EXCEL.text });
    equal(await offer.count(), 0, "그림 없는 표에 [그림으로 바꾸기]");
    await page.locator(".body-editor").getByRole("button", { name: "취소" }).click();
  });

  await check("검토 기록 편집기에는 그 기록의 첨부만 (TODO 150)", async () => {
    const made = await api.post("/api/intakes", { title: "기록 첨부 확인" });
    const id = encodeURIComponent(made.id);
    const png = Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", "base64");
    const form = new FormData();
    form.append("file", new Blob([png], { type: "image/png" }), "과제정의서화면.png");
    await fetch(`${BASE}/api/intakes/${id}/attachments`, { method: "POST", body: form });
    await go(`#/intakes/${id}`);
    equal(await page.locator(".intake-files .attachments li").count(), 1, "왼쪽 카드는 전체");
    await page.getByRole("button", { name: "기록 추가" }).click();
    await page.waitForTimeout(400);
    equal(await page.locator(".log-editor .attachments li").count(), 0, "새 기록 편집기의 첨부");
    await pasteInto(".log-editor textarea", { image: true });
    await page.waitForTimeout(1000);
    equal(await page.locator(".log-editor .attachments li").count(), 1, "이번에 올린 첨부만");
    await page.locator(".log-editor input").nth(1).fill("인터뷰 — 화면 캡처");
    await page.locator(".log-editor").getByRole("button", { name: /^저장/ }).click();
    await page.waitForTimeout(1000);
    const card = page.locator(".intake-logs .entry").filter({ hasText: "인터뷰 — 화면 캡처" });
    equal(await card.locator(".entry-files .file-chip").count(), 1, "기록 카드의 첨부 칩");
  });

  await check("병합할 과제는 낱말로 찾는다 — 띄어 쓰면 모두 든 것만 (TODO 151)", async () => {
    const made = await api.post("/api/intakes", { title: "공정 자동화 요청" });
    await go(`#/intakes/${encodeURIComponent(made.id)}`);
    await page.locator(".decision-bar").getByRole("button", { name: "병합", exact: true }).click();
    await page.waitForTimeout(900);
    // 접수 제목과 낱말이 겹치는 과제가 위에 선다
    expect((await page.locator(".decision-panel").innerText()).includes("접수 제목과 낱말이 겹치는 과제"), "닮은 과제 묶음");
    const ids = await page.locator(".decision-panel .merge-list").last().locator(".merge-option-id").allInnerTexts();
    const sorted = [...ids].sort((a, b) => a.localeCompare(b, "ko", { numeric: true }));
    equal(ids.join(","), sorted.join(","), "과제 번호순");
    await page.locator('.decision-panel input[type="search"]').fill("공정 없는낱말");
    equal(await page.locator(".decision-panel .merge-option").count(), 0, "낱말이 모두 들어야 한다");
    await page.locator(".decision-panel").getByRole("button", { name: "취소" }).click();
  });

  await check("메뉴 화면의 제목은 탭 이름 그대로, 설명과의 간격은 한 가지, 설정에 뒤로 가기 없음 (TODO 153)", async () => {
    await go("#/");
    const tabs = (await page.locator(".app-header nav a").allInnerTexts()).map((text) => text.trim());
    const gaps = new Set();
    for (const [index, hash] of ["#/", "#/intakes", "#/projects", "#/roadmap", "#/reports", "#/history", "#/skills", "#/settings", "#/help"].entries()) {
      await go(hash);
      const head = await page.evaluate(() => {
        const h1 = document.querySelector("section h1");
        const desc = h1.parentElement.querySelector("p.page-desc");
        return {
          title: h1.textContent.trim(),
          gap: desc ? Math.round(desc.getBoundingClientRect().top - h1.getBoundingClientRect().bottom) : null,
          back: !!document.querySelector("section > a.back"),
        };
      });
      equal(head.title, tabs[index], `${hash} 의 제목`);
      expect(head.gap !== null, `${hash} 에 설명 줄이 없다`);
      gaps.add(head.gap);
      expect(!head.back, `${hash} 에 메뉴로 왔는데 뒤로 가기가 선다`);
    }
    equal(gaps.size, 1, `제목과 설명 사이가 갈린다: ${[...gaps].join(", ")}`);
  });

  await check("접수 표는 과제목록 표와 같은 자리 · 열 머리로 정렬 (TODO 154)", async () => {
    await go("#/intakes");
    equal(await page.locator(".intake-pool .card table.grid").count(), 0, "카드 안에 한 번 더 감싸였다");
    await page.locator(".intake-table th.sortable button", { hasText: "접수일" }).click();
    await page.waitForTimeout(700);
    expect(page.url().includes("sort=received"), `정렬이 주소에 없다: ${page.url()}`);
    await page.locator(".intake-table th.sortable button", { hasText: "접수일" }).click();
    await page.waitForTimeout(700);
    expect(page.url().includes("order=asc"), `방향이 바뀌지 않았다: ${page.url()}`);
  });

  console.log("\n[28] 접수 사전점검 체크리스트 (TODO 155)");

  await check("요약 줄의 [체크리스트] — 다 매기면 합계·구간, 덜 매기면 평가 중", async () => {
    const made = await api.post("/api/intakes", { title: "사전점검 확인" });
    const hash = `#/intakes/${encodeURIComponent(made.id)}`;
    await go(hash);
    const cell = page.locator(".summary-bar .precheck-cell");
    expect((await cell.innerText()).includes("미평가"), "처음에는 미평가");
    await cell.getByRole("button", { name: "체크리스트" }).click();
    const dialog = page.locator(".precheck-dialog");
    await dialog.waitFor();
    const rows = dialog.locator(".precheck-row");
    equal(await rows.count(), 10, "항목 수");
    equal(await dialog.locator(".precheck-group").count(), 5, "분류 수");
    // 셋만 매기면 합계가 없다
    for (let i = 0; i < 3; i += 1) await rows.nth(i).locator(".precheck-choice").first().click();
    expect((await dialog.locator(".precheck-total").innerText()).includes("평가 3/10"), "평가 3/10");
    // 고른 칩을 다시 누르면 지워진다
    await rows.nth(0).locator(".precheck-choice").first().click();
    expect((await dialog.locator(".precheck-total").innerText()).includes("평가 2/10"), "다시 누르면 지움");
    // 나머지를 모두 최고점으로 — 이미 켜진 것은 다시 누르면 지워지므로 건너뛴다
    for (let i = 0; i < 10; i += 1) {
      const on = await rows.nth(i).locator(".precheck-choice.on").count();
      if (!on) await rows.nth(i).locator(".precheck-choice").first().click();
    }
    await rows.nth(0).locator(".precheck-note").fill("9/12 사업부장 회의");
    expect((await dialog.locator(".precheck-total").innerText()).includes("100점"), "합계 100");
    await dialog.getByRole("button", { name: "저장" }).click();
    await page.waitForTimeout(1000);
    const after = await cell.innerText();
    expect(after.includes("100점") && after.includes("착수 권장"), `요약 줄: ${after}`);
    expect((await page.locator(".intake-logs").innerText()).includes("(사전점검) 미평가 → 100점"), "기록 한 줄");
    const stored = await api.get(`/api/intakes/${encodeURIComponent(made.id)}`);
    equal(stored.precheck.items[0].note, "9/12 사업부장 회의", "근거");
    // 풀의 열
    await go("#/intakes?sort=precheck");
    const first = page.locator("tr[data-intake]").first();
    equal(await first.getAttribute("data-intake"), made.id, "사전점검 높은 순의 첫 줄");
    expect((await first.locator(".precheck-col").innerText()).includes("100"), "풀의 점수 칸");
  });

  await check("판정이 난 접수의 체크리스트는 볼 수만 있다", async () => {
    const made = await api.post("/api/intakes", { title: "반려된 점검" });
    await api.post(`/api/intakes/${encodeURIComponent(made.id)}/status`, { status: "rejected", note: "시험" });
    await go(`#/intakes/${encodeURIComponent(made.id)}`);
    await page.locator(".summary-bar .precheck-cell").getByRole("button", { name: "체크리스트" }).click();
    const dialog = page.locator(".precheck-dialog");
    await dialog.waitFor();
    equal(await dialog.getByRole("button", { name: "저장" }).count(), 0, "저장 단추");
    expect(await dialog.locator(".precheck-choice").first().isDisabled(), "고르기가 막혀 있어야 한다");
    await dialog.getByRole("button", { name: "닫기" }).click();
  });

  await check("설정에 사전점검 항목 · 기준 칸이 있다", async () => {
    await go("#/settings");
    await page.locator("summary", { hasText: "과제 분류" }).first().click().catch(() => undefined);
    const box = page.locator(".intake-settings .precheck-lines");
    equal(await box.count(), 1, "항목 칸");
    expect((await box.inputValue()).split("\n").length === 10, "기본 열 줄");
    equal(await page.locator(".intake-settings input[type=number]").count(), 3, "묵힘 · 기준 둘");
  });

  console.log("\n[29] 효과 첫째 자리 · 합계 줄 · 0 은 - · 성격 칸 · 한 줄 칸 (TODO 156~160)");

  /** 칸 안의 글자가 몇 줄로 섰는지 — 글자 조각들의 세로 위치를 묶어 센다 (TODO 160). */
  const lineCount = (locator) =>
    locator.evaluate((cell) => {
      const range = document.createRange();
      range.selectNodeContents(cell);
      const rects = [...range.getClientRects()].filter((rect) => rect.width > 0 && rect.height > 0);
      const lines = [];
      for (const rect of rects) {
        const mid = rect.top + rect.height / 2;
        if (!lines.some((line) => Math.abs(line - mid) < 8)) lines.push(mid);
      }
      return lines.length;
    });

  await check("효과는 어디서나 소수 첫째 자리 — 끝의 0 도 적는다 (156)", async () => {
    await api.patch(`/api/projects/${seeded.projectA}`, { effect_expected: 3 });
    await go("#/projects");
    const row = page.locator(".grid tbody tr").filter({ hasText: "고강도 소재 개발" }).first();
    expect((await row.locator(".effect-col").innerText()).trim() === "3.0", "목록 3.0");
    await go(`#/projects/${seeded.projectA}`);
    expect((await page.locator(".summary-bar, .project-summary, main").first().innerText()).includes("3.0"), "상세 3.0");
    await go("#/");
    expect((await page.locator(".home-team").innerText()).includes("3.0") ||
      (await page.locator(".home-team").innerText()).includes(".0") ||
      /\d\.\d/.test(await page.locator(".home-team").innerText()), "홈 팀 현황의 효과가 첫째 자리");
    await api.patch(`/api/projects/${seeded.projectA}`, { effect_expected: 3.5 });
  });

  await check("표마다 맨 아래 합계 줄이 선다 (157)", async () => {
    for (const [hash, selector] of [
      ["#/projects", ".project-table"],
      ["#/", ".home-member-table"],
      ["#/", ".home-slice-type table"],
      ["#/reports", "table.grid"],
      ["#/skills", ".skills-table"],
      ["#/intakes?status=all", ".intake-table"],
    ]) {
      await go(hash);
      const foot = page.locator(`${selector} tfoot tr.total-row`).first();
      equal(await foot.count(), 1, `${hash} ${selector} 의 합계 줄`);
      expect((await foot.innerText()).startsWith("합계"), `${selector} 첫 칸이 합계`);
      // 합계 줄의 칸 수 = 머리 줄의 칸 수 (칸이 밀리면 합계가 엉뚱한 열 아래 선다)
      const cols = async (row) =>
        row.evaluate((tr) => [...tr.children].reduce((n, cell) => n + (cell.colSpan || 1), 0));
      equal(await cols(foot), await cols(page.locator(`${selector} thead tr`).first()), `${selector} 칸 수`);
    }
    await go("#/history");
    const month = page.locator(".month-grid tfoot tr.total-row");
    equal(await month.count(), 1, "과제 × 월 합계 줄");
    expect((await page.locator(".month-grid thead").innerText()).includes("건") === false, "머리의 N건은 아래로 옮겼다");
  });

  await check("과제목록 합계는 걸러진 줄만 더한다 — 기록 수 · 효과 (157)", async () => {
    // 목록은 연도·상태로 걸러져 있다 — 화면에 선 줄의 과제만 가져와 견준다
    await go("#/projects?status=in_progress");
    const ids = (await page.locator(".project-table tbody .project-id").allInnerTexts()).map((t) => t.trim());
    const rows = (await api.get("/api/projects")).filter((p) => ids.includes(p.id));
    equal(rows.length, ids.length, "화면의 줄");
    expect(rows.every((p) => p.status === "in_progress"), "진행중만 걸러졌다");
    const foot = await page.locator(".project-table tfoot").innerText();
    expect(foot.includes(`합계 (${rows.length}건)`), `줄 수: ${foot}`);
    const entries = rows.reduce((n, p) => n + p.entry_count, 0);
    expect(foot.includes(entries ? `${entries}건` : "-"), `기록 합계 ${entries}: ${foot}`);
    const expected = rows.reduce((n, p) => n + (p.effect_expected ?? 0), 0);
    if (expected) expect(foot.includes((Math.round(expected * 10) / 10).toFixed(1)), `효과 합계 ${expected}: ${foot}`);
    // 더할 수 없는 칸은 `-`
    expect((await page.locator(".project-table tfoot td.total-none").count()) >= 7, "더할 수 없는 칸이 - 로");
  });

  await check("[표 복사] 에는 합계 줄이 들어가지 않는다 (157)", async () => {
    await go("#/projects");
    await page.evaluate(() => {
      window.__copied = "";
      navigator.clipboard.writeText = async (text) => { window.__copied = text; };
    });
    await page.getByRole("button", { name: "표 복사" }).first().click();
    await page.waitForTimeout(300);
    const copied = await page.evaluate(() => window.__copied);
    const lines = copied.trim().split("\n");
    equal(lines.length, (await page.locator(".project-table tbody tr").count()) + 1, "머리 + 과제 줄");
    expect(!copied.includes("합계"), "합계 줄이 섞였습니다");
    expect(lines[0].split("\t").slice(3, 6).join("|") === "속성|성격|그룹", `머리: ${lines[0]}`);
  });

  await check("표 안의 0 은 - 로 선다 (158)", async () => {
    await go("#/");
    const zeros = await page.locator(".home-member-table tbody td.zero").allInnerTexts();
    expect(zeros.length > 0, "빈 상태 칸이 있어야 한다(시험 자료)");
    expect(zeros.every((text) => text.trim() === "-"), `0 이 남았습니다: ${zeros.join(",")}`);
    await go("#/projects");
    const cells = await page.locator(".project-table tbody td").allInnerTexts();
    expect(!cells.some((text) => /^(0|0건|0\.0)$/.test(text.trim())), "과제목록에 0 이 남았습니다");
    await go("#/reports");
    const unreported = await page.locator("table.grid tbody td").allInnerTexts();
    expect(!unreported.some((text) => text.trim() === "0건"), "보고대상에 0건이 남았습니다");
  });

  await check("과제목록에 성격 칸 — 속성 바로 옆, 없으면 - (159)", async () => {
    await api.patch(`/api/projects/${seeded.projectB}`, { nature: "현장적용" });
    await go("#/projects");
    const heads = (await page.locator(".project-table thead th").allInnerTexts()).map((t) => t.trim().split("\n")[0]);
    equal(heads.indexOf("성격"), heads.indexOf("속성") + 1, `칸 순서: ${heads.join(",")}`);
    const col = heads.indexOf("성격");
    const smart = page.locator(".project-table tbody tr").filter({ hasText: "공정 자동화" }).first();
    equal((await smart.locator("td").nth(col).innerText()).trim(), "현장적용", "스마트과제의 성격");
    const other = page.locator(".project-table tbody tr").filter({ hasText: "고강도 소재 개발" }).first();
    equal((await other.locator("td").nth(col).innerText()).trim(), "-", "다른 과제는 -");
    // 머리를 눌러 정렬 — 성격이 있는 과제가 먼저
    await page.locator(".project-table thead th", { hasText: "성격" }).locator("button").click();
    await page.waitForTimeout(600);
    expect(page.url().includes("sort=nature"), `주소: ${page.url()}`);
    expect((await page.locator(".project-table tbody tr").first().innerText()).includes("공정 자동화"), "성격 있는 과제가 맨 위");
  });

  await check("짧은 칸은 한 줄, 그룹은 말줄임 없이 (160)", async () => {
    await api.patch(`/api/projects/${seeded.projectA}`, { group: "차세대 이차전지 고강도 소재 공정 그룹" });
    for (const width of [1366, 1920]) {
      await page.setViewportSize({ width, height: 900 });
      await go("#/projects");
      const cells = page.locator(".project-table tbody td.one-line");
      const n = await cells.count();
      expect(n > 0, "한 줄 칸이 없습니다");
      for (let i = 0; i < n; i += 1) {
        const lines = await lineCount(cells.nth(i));
        expect(lines <= 1, `${width}px — ${await cells.nth(i).innerText()} 가 ${lines}줄`);
      }
      const group = page.locator(".project-table tbody td", { hasText: "차세대 이차전지 고강도 소재 공정 그룹" });
      expect(await group.evaluate((td) => td.scrollWidth <= td.clientWidth + 1 && getComputedStyle(td).textOverflow !== "ellipsis"),
        `${width}px 그룹 이름이 잘렸습니다`);
      // 표가 넘치면 표만 가로로 민다 — 화면 전체가 옆으로 밀리지 않는다
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), `${width}px 화면이 옆으로 넘칩니다`);
      await go("#/intakes?status=all");
      const intakeCells = page.locator(".intake-table tbody td.one-line, .intake-table tbody td.num, .intake-table tbody td.intake-id");
      const m = await intakeCells.count();
      for (let i = 0; i < m; i += 1) {
        const lines = await lineCount(intakeCells.nth(i));
        expect(lines <= 1, `접수 ${width}px — ${await intakeCells.nth(i).innerText()} 가 ${lines}줄`);
      }
    }
    await page.setViewportSize({ width: 1500, height: 900 });
    await api.patch(`/api/projects/${seeded.projectA}`, { group: "" });
  });

  console.log("\n[30] 실패 알림 · 떠나기 경고 · 임시 보관 · 읽지 못한 값 · 안전망 · 좁은 창 (TODO 161~169)");

  // 이 묶음은 **일부러** 실패(409 · 연결 끊김 · 그리기 오류)를 끼워 넣는다 — 그때 나는 콘솔 오류는
  // 끝의 "화면 오류가 없었다" 에 세지 않는다. 묶음이 끝나면 여기까지로 되돌린다.
  const errorsBefore30 = pageErrors.length;

  /** 다음 확인 창 하나만 이 시험의 손으로 받고, 그 뒤는 위쪽의 전역 handler(accept)로 돌린다 */
  const nextDialog = (handle) => {
    page.removeAllListeners("dialog");
    page.once("dialog", async (dialog) => {
      await handle(dialog);
      page.on("dialog", (other) => other.accept());
    });
  };

  /** 서버의 쓰기 요청을 일부러 실패시킨다 — 윈도우에서 파일이 열려 있을 때와 같은 409 */
  const FAIL = "시험용 실패 — 다른 프로그램에서 열려 있습니다";
  const failWrites = (on) =>
    on
      ? page.route("**/api/**", (route) =>
          route.request().method() === "GET"
            ? route.continue()
            : route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ detail: FAIL }) }))
      : page.unroute("**/api/**");

  await check("저장·삭제가 실패하면 화면 아래 알림에 사유가 선다 (161)", async () => {
    nextDialog((d) => d.accept());
    await go(`#/projects/${seeded.projectA}`);
    await failWrites(true);
    await page.locator("li.entry").first().getByRole("button", { name: "삭제" }).click();
    await page.waitForTimeout(700);
    await failWrites(false);
    expect((await page.locator(".toast").innerText()).includes(FAIL), "진행일지 삭제 실패 알림");
    await page.locator(".toast").getByRole("button", { name: "알림 닫기" }).click();
    // 개요 저장 — 실패해도 편집기와 쓰던 글이 남는다
    await page.locator(".card", { hasText: "과제 개요" }).getByRole("button", { name: "수정" }).first().click();
    await page.locator(".card", { hasText: "과제 개요" }).locator("textarea").fill("실패할 개요");
    await failWrites(true);
    await page.getByRole("button", { name: "저장", exact: true }).first().click();
    await page.waitForTimeout(700);
    await failWrites(false);
    expect((await page.locator(".toast").innerText()).includes(FAIL), "개요 저장 실패 알림");
    equal(await page.locator(".card", { hasText: "과제 개요" }).locator("textarea").inputValue(), "실패할 개요", "쓰던 글");
    // 뒷정리 — 버리고 닫는다
    nextDialog((d) => d.accept());
    await page.locator(".card", { hasText: "과제 개요" }).getByRole("button", { name: "취소" }).click();
  });

  await check("편집 중에 메뉴를 누르면 묻고, 머물면 글이 그대로다 (162)", async () => {
    await go(`#/projects/${seeded.projectA}`);
    await page.locator(".card", { hasText: "과제 개요" }).getByRole("button", { name: "수정" }).first().click();
    await page.locator(".card", { hasText: "과제 개요" }).locator("textarea").fill("떠나기 시험");
    let asked = "";
    nextDialog((d) => { asked = d.message(); d.dismiss(); });
    await page.locator("header a", { hasText: "도움말" }).click();
    await page.waitForTimeout(500);
    expect(asked.includes("저장하지 않은 내용"), `묻지 않았다: ${asked}`);
    expect(page.url().includes(`projects/${seeded.projectA}`), `떠났다: ${page.url()}`);
    equal(await page.locator(".card", { hasText: "과제 개요" }).locator("textarea").inputValue(), "떠나기 시험", "쓰던 글");
    // 떠나기로 하면 떠난다 — 그리고 다시 열면 임시 보관이 되살린다
    nextDialog((d) => d.accept());
    await page.locator("header a", { hasText: "도움말" }).click();
    await page.waitForTimeout(500);
    expect(page.url().includes("#/help"), `못 떠났다: ${page.url()}`);
    await go(`#/projects/${seeded.projectA}`);
    await page.locator(".card", { hasText: "과제 개요" }).getByRole("button", { name: "수정" }).first().click();
    equal(await page.locator(".card", { hasText: "과제 개요" }).locator("textarea").inputValue(), "떠나기 시험", "되살린 글");
    expect(await page.locator(".restored").count() > 0, "복구 안내");
    await page.getByRole("button", { name: "복구한 내용 버리기" }).click();
    await page.locator(".card", { hasText: "과제 개요" }).getByRole("button", { name: "취소" }).click();
    // 저장하지 않은 것이 없으면 묻지 않는다
    let again = false;
    nextDialog((d) => { again = true; d.dismiss(); });
    await page.locator("header a", { hasText: "도움말" }).click();
    await page.waitForTimeout(400);
    expect(!again && page.url().includes("#/help"), "편집이 없으면 묻지 않아야 한다");
  });

  await check("Ctrl+S 가 개요 · 접수 편집기에서도 저장한다 (162)", async () => {
    await go(`#/projects/${seeded.projectB}`);
    await page.locator(".card", { hasText: "과제 개요" }).getByRole("button", { name: "수정" }).first().click();
    const area = page.locator(".card", { hasText: "과제 개요" }).locator("textarea");
    await area.fill("## 배경\n\nCtrl+S 로 저장한 개요");
    await area.press("Control+s");
    await page.waitForTimeout(800);
    expect((await api.get(`/api/projects/${seeded.projectB}`)).body.includes("Ctrl+S 로 저장한 개요"), "개요 저장");
    const made = await api.post("/api/intakes", { title: "Ctrl+S 접수" });
    await go(`#/intakes/${encodeURIComponent(made.id)}`);
    await page.locator(".intake-body").getByRole("button", { name: "수정" }).click();
    const box = page.locator(".body-editor textarea");
    await box.fill("## 배경\n\n단축키로 저장");
    await box.press("Control+s");
    await page.waitForTimeout(800);
    expect((await api.get(`/api/intakes/${encodeURIComponent(made.id)}`)).body.includes("단축키로 저장"), "요청 내용 저장");
  });

  await check("서버에 닿지 못하면 한국어로 말하고 [다시 시도] 가 있다 (165)", async () => {
    await page.route("**/api/**", (route) => route.abort("connectionrefused"));
    for (const hash of ["#/intakes", `#/projects/${seeded.projectA}`, "#/settings"]) {
      await go(hash);
      const text = await page.locator("main").innerText();
      expect(text.includes("run.bat") && !text.includes("Failed to fetch"), `${hash}: ${text.slice(0, 120)}`);
      expect(await page.locator(".load-error").getByRole("button", { name: "다시 시도" }).count() > 0, `${hash} 다시 시도`);
    }
    await page.unroute("**/api/**");
  });

  await check("입력 검사 오류는 사유 목록으로 오고, 화면은 항목 이름으로 말한다 (165 · 167)", async () => {
    const res = await fetch(`${BASE}/api/people`, { method: "POST", headers: { "Content-Type": "application/json" }, body: '{"name": NaN}' });
    equal(res.status, 422, "NaN 은 422 (전에는 500)");
    expect(Array.isArray((await res.json()).detail), "사유는 목록");
    // 화면 쪽 — 목록 사유를 받은 요청이 [object Object] 로 보이지 않는다
    await go("#/projects");
    await page.route("**/api/projects", (route) =>
      route.request().method() === "POST"
        ? route.fulfill({ status: 422, contentType: "application/json", body: JSON.stringify({ detail: [{ loc: ["body", "title"], msg: "x", type: "x" }] }) })
        : route.continue());
    await page.getByRole("button", { name: "과제 추가" }).click();
    await page.locator(".card", { hasText: "새 과제" }).locator("input").first().fill("검사 오류 시험");
    await page.locator(".card", { hasText: "새 과제" }).getByRole("button", { name: "만들기" }).click();
    await page.waitForTimeout(600);
    await page.unroute("**/api/projects");
    const shown = await page.locator(".card", { hasText: "새 과제" }).innerText();
    expect(shown.includes("입력값을 서버가 받지 못했습니다") && shown.includes("title") && !shown.includes("[object Object]"), shown.slice(0, 200));
    nextDialog((d) => d.accept());
    await page.locator(".card", { hasText: "새 과제" }).getByRole("button", { name: "취소" }).click();
  });

  await check("화면 하나가 그리다 멈춰도 메뉴가 살고 오류 기록에 남는다 (166)", async () => {
    await api.delete("/api/errors");
    await page.route("**/api/home**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: '{"team": null}' }));
    await go("#/");
    await page.unroute("**/api/home**");
    expect(await page.locator(".render-error").count() === 1, "안전망 판");
    expect(await page.locator("header .nav a").count() >= 8, "메뉴가 살아 있다");
    await page.locator("header a", { hasText: "도움말" }).click();
    await page.waitForTimeout(500);
    equal(await page.locator(".render-error").count(), 0, "다른 화면으로 가면 풀린다");
    await page.waitForTimeout(300);
    const logged = (await api.get("/api/errors")).items;
    expect(logged.some((item) => item.action.startsWith("화면") && item.error === "render"), `기록: ${JSON.stringify(logged.slice(0, 2))}`);
    // 화면 오류는 목록에서 "화면" 으로 보인다
    await go("#/settings");
    await page.locator("summary", { hasText: "점검" }).first().click().catch(() => undefined);
    // 이 시험이 남긴 기록은 지운다 — 뒤의 "화면 오류가 없었다" 는 페이지 오류를 보므로 영향이 없다
    await api.delete("/api/errors");
  });

  await check("손으로 틀린 날짜를 적어도 과제가 남고, 홈 위에 알린다 (164)", async () => {
    const made = await api.post("/api/projects", { title: "날짜 틀린 과제", due_date: "2026-11-01" });
    const index = join(vault, "projects", (await readdir(join(vault, "projects"))).find((name) => name.startsWith(made.id)), "index.md");
    const text = await readFile(index, "utf8");
    await writeFile(index, text.replace(/^due_date: .*$/m, "due_date: 2026-02-30"), "utf8");
    await api.post("/api/reindex");
    // 화면은 켤 때 · [다시 읽기] 를 눌렀을 때 목록을 받는다 — 사용자가 도구를 다시 켠 것과 같게
    await go("#/");
    await page.reload();
    await page.waitForTimeout(800);
    const banner = page.locator(".problems-banner");
    expect(await banner.count() === 1, "홈 위 알림");
    await banner.getByRole("button", { name: "무엇인지 보기" }).click();
    expect((await banner.innerText()).includes("2026-02-30"), "무엇이 틀렸는지");
    expect((await api.get("/api/projects")).some((p) => p.id === made.id), "과제는 목록에 남는다");
    // 도구에서 날짜를 고치면 알림이 사라진다
    await api.patch(`/api/projects/${made.id}`, { due_date: "2026-11-30" });
    await page.reload();
    await page.waitForTimeout(800);
    equal(await page.locator(".problems-banner").count(), 0, "고치면 사라진다");
    await fetch(`${BASE}/api/projects/${made.id}/archive`, { method: "POST" });
  });

  await check("설정 파일의 값이 틀리면 설정 화면이 알린다 (163)", async () => {
    const path = join(vault, "settings.json");
    const before = await readFile(path, "utf8").catch(() => "{}");
    const data = JSON.parse(before || "{}");
    await writeFile(path, JSON.stringify({ ...data, backup_every_hours: "매일" }), "utf8");
    await go("#/settings");
    expect((await page.locator(".warn-banner").innerText()).includes("backup_every_hours"), "설정 화면 알림");
    await writeFile(path, before, "utf8");
  });

  await check("Esc 로 승격 창이 닫히고, 탭 제목이 과제 · 접수 이름이다 (169)", async () => {
    const made = await api.post("/api/intakes", { title: "Esc 시험 접수" });
    await go(`#/intakes/${encodeURIComponent(made.id)}`);
    expect((await page.title()).startsWith(`${made.id} Esc 시험 접수`), `탭 제목: ${await page.title()}`);
    await page.getByRole("button", { name: /착수 · 과제로 승격/ }).click();
    await page.locator(".promote-dialog").waitFor();
    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);
    equal(await page.locator(".promote-dialog").count(), 0, "Esc 로 닫힘");
    await go(`#/projects/${seeded.projectA}`);
    expect((await page.title()).startsWith(seeded.projectA), `과제 탭 제목: ${await page.title()}`);
  });

  await check("창을 반으로 붙인 폭(960px)에서 메뉴가 꺾이지 않는다 (168)", async () => {
    await page.setViewportSize({ width: 960, height: 900 });
    await go("#/");
    const tall = await page.evaluate(() =>
      [...document.querySelectorAll("header .nav a")].filter((a) => a.getClientRects().length > 1 || a.getBoundingClientRect().height > 40).map((a) => a.textContent));
    equal(tall.length, 0, `꺾인 메뉴: ${tall.join(",")}`);
    const search = await page.locator("header .search-box input").boundingBox();
    expect(search && search.width > 200, `검색 칸 폭 ${search?.width}`);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), "가로 넘침");
    await page.setViewportSize({ width: 1500, height: 900 });
  });

  console.log("\n[31] 쓰다 만 글을 데이터 폴더에 · 다른 창에서도 표시 · 홈 목록 · 한글 번호 (TODO 170)");

  await check("팀 코드에 한글이 든 과제에서도 쓰다 만 기록이 표시된다 (170 — v7 B-6 의 원인)", async () => {
    // 주소의 한글은 브라우저가 %ED… 로 바꿔 돌려준다 — 전에는 표시가 그 바뀐 번호로 찾아 못 찾았다
    const before = await api.get("/api/settings");
    await api.put("/api/settings", { project_code: "시험팀" });
    const made = await api.post("/api/projects", { title: "한글 코드 과제" });
    await api.put("/api/settings", { project_code: before.project_code ?? "" });
    expect(made.id.includes("시험팀"), `번호: ${made.id}`);
    // 창 A — 먼저 열어 둔다(사용자처럼 여러 창)
    await go(`#/projects/${encodeURIComponent(made.id)}`);
    equal(await page.locator(".draft-waiting").count(), 0, "처음에는 표시 없음");
    // 창 B — 새 기록을 쓰다가 그 창만 닫는다
    const writer = await browser.newPage();
    writer.on("dialog", (dialog) => dialog.accept());
    await writer.goto(`${BASE}/#/projects/${encodeURIComponent(made.id)}`);
    await writer.waitForTimeout(900);
    await writer.getByRole("button", { name: "기록 추가" }).click();
    await writer.locator("textarea").first().fill("창 B 에서 쓰던 글");
    await writer.waitForTimeout(1200);
    await writer.close({ runBeforeUnload: true });
    // 데이터 폴더에 남았다 — 브라우저 보관이 아니다
    const saved = (await api.get("/api/drafts")).items.find((item) => item.key === `entry:new-${made.id}`);
    expect(saved, "데이터 폴더의 임시 보관");
    // 창 A 로 돌아오면(새로고침 없이) 표시가 선다
    await page.bringToFront();
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await page.waitForTimeout(800);
    expect((await page.locator(".draft-waiting").allInnerTexts()).includes("작성 중이던 기록 있음"), "창 A 의 표시");
    // 홈의 "작성 중이던 글" 을 누르면 그 편집기가 열리고 글이 돌아온다
    await go("#/");
    const row = page.locator(".home-unsaved li", { hasText: "한글 코드 과제" });
    equal(await row.count(), 1, "홈 목록");
    await row.locator("a").click();
    await page.waitForTimeout(1200);
    expect((await page.locator("textarea").first().inputValue()).includes("창 B 에서 쓰던 글"), "되살린 글");
    expect(await page.locator(".restored").count() > 0, "복구 안내");
    // 편집기 [닫기] 로 버리면(묻고) 목록에서도 빠진다
    nextDialog((dialog) => dialog.accept());
    await page.locator(".entry-editor").getByRole("button", { name: "닫기" }).first().click();
    await page.waitForTimeout(800);
    expect(!(await api.get("/api/drafts")).items.some((item) => item.key === `entry:new-${made.id}`), "버리면 지운다");
    await fetch(`${BASE}/api/projects/${encodeURIComponent(made.id)}/archive`, { method: "POST" });
  });

  await check("기존 기록을 고치다 만 것도 카드에 '작성 중' 이 선다 (170)", async () => {
    await go(`#/projects/${seeded.projectA}`);
    const entry = page.locator("li.entry").first();
    await entry.getByRole("button", { name: "수정" }).click();
    await page.locator("textarea").first().click();
    await page.keyboard.type(" 고치다 만 글");
    await page.waitForTimeout(1200);
    const other = await browser.newPage();
    await other.goto(`${BASE}/#/projects/${seeded.projectA}`);
    await other.waitForTimeout(1200);
    expect((await other.locator("li.entry .draft-waiting").allInnerTexts()).includes("작성 중"), "다른 창의 카드 표시");
    await other.close({ runBeforeUnload: false });
    nextDialog((dialog) => dialog.accept());
    await page.locator(".entry-editor").getByRole("button", { name: "닫기" }).first().click();
    await page.waitForTimeout(800);
    expect(!(await api.get("/api/drafts")).items.some((item) => item.label.startsWith("진행일지 고치기")), "버리면 지운다");
  });

  pageErrors.length = errorsBefore30;

  console.log("\n[32] 다년도 과제의 단계 줄기 · 선행 과제 칸 · 스마트과제를 접수로 되돌리기 (TODO 171 · 172)");

  await check("선행 과제가 여럿이고 한 단계에 과제가 여럿이어도 줄기가 단계별로 묶여 보인다 (172)", async () => {
    const one = await api.post("/api/projects", { title: "1단계 소재 A" });
    const two = await api.post("/api/projects", { title: "1단계 소재 B" });
    const mid = await api.post("/api/projects", { title: "2단계 통합", predecessors: [one.id, two.id] });
    const last = await api.post("/api/projects", { title: "3단계 양산", predecessors: [mid.id] });
    await go(`#/projects/${mid.id}`);
    equal((await page.locator(".stage-flow-now").innerText()).trim(), "2단계", "단계 표시");
    equal(await page.locator(".stage-flow-col").count(), 3, "단계 칸 셋");
    // 한 단계에 과제가 여럿이면 그 칸 안에 위아래로 — 꺾여 다른 단계와 섞이지 않는다 (176)
    const boxes = await page.locator(".stage-flow-col").evaluateAll((cols) => cols.map((col) => col.getBoundingClientRect().top));
    equal(new Set(boxes.map(Math.round)).size, 1, "단계 칸은 한 줄에 나란히");
    equal(await page.locator(".stage-flow-col.current").count(), 1, "지금 단계 칸");
    const first = page.locator(".stage-flow-col").first();
    equal(await first.locator("a.stage-flow-item").count(), 2, "1단계에 과제 둘");
    const [upper, lower] = await first.locator("a.stage-flow-item").evaluateAll((items) => items.map((item) => item.getBoundingClientRect().top));
    expect(lower > upper, "같은 단계는 위아래로");
    equal((await page.locator(".stage-flow-item.here").innerText()).includes(mid.id), true, "지금 과제 강조");
    await first.locator("a.stage-flow-item").first().click();
    await page.waitForTimeout(700);
    expect(page.url().includes(`/projects/${one.id}`), `링크 이동: ${page.url()}`);
    equal((await page.locator(".stage-flow-now").innerText()).trim(), "1단계", "앞 단계에서도 줄기가 보인다");
    // 줄이 없는 과제에는 띠가 없다
    await go(`#/projects/${seeded.projectA}`);
    equal(await page.locator(".stage-flow").count(), 0, "외톨이 과제는 단계 칸 없음");
    for (const item of [last, mid, two, one]) await fetch(`${BASE}/api/projects/${item.id}/archive`, { method: "POST" });
  });

  await check("수정 칸에서 선행 과제를 골라 칩으로 넣고 빼고 저장한다 (172)", async () => {
    const before = await api.post("/api/projects", { title: "앞 과제" });
    const after = await api.post("/api/projects", { title: "뒤 과제" });
    await go(`#/projects/${after.id}?edit=1`);
    await page.waitForTimeout(500);
    const input = page.locator('input[aria-label="선행 과제 번호"]');
    await input.fill(before.id);
    await page.waitForTimeout(200);
    equal(await page.locator(".predecessor-chip").count(), 1, "목록에서 고르면 칩");
    await input.fill(seeded.projectA);
    await input.press("Enter");
    equal(await page.locator(".predecessor-chip").count(), 2, "Enter 로도 칩");
    await page.locator(".predecessor-chip").nth(1).getByRole("button").click();
    equal(await page.locator(".predecessor-chip").count(), 1, "× 로 뺀다");
    await page.locator(".project-form").getByRole("button", { name: "저장" }).click();
    await page.waitForTimeout(800);
    equal(JSON.stringify((await api.get(`/api/projects/${after.id}`)).predecessors), JSON.stringify([before.id]), "저장된 선행");
    equal(await page.locator(".stage-flow").count(), 1, "저장하자 단계 칸이 선다");
    for (const item of [after, before]) await fetch(`${BASE}/api/projects/${item.id}/archive`, { method: "POST" });
  });

  await check("직접 만든 스마트과제를 접수로 되돌리면 풀의 검토중 접수가 되고 그리로 간다 (171)", async () => {
    const meta = await api.get("/api/meta");
    const made = await api.post("/api/projects", { title: "자체 스마트 과제", type: meta.classified_type, body: "## 과제 개요\n\n현장 요청으로 바로 세운 과제\n" });
    await api.post(`/api/projects/${made.id}/entries`, { date: "2026-09-20", title: "현장 확인", body: "## 내용\n\n라인 3 확인\n" });
    await go(`#/projects/${made.id}`);
    await page.getByRole("button", { name: "접수로 되돌리기" }).click();
    await page.waitForTimeout(500);
    const panel = page.locator(".demote-panel");
    equal(await panel.count(), 1, "판이 열린다");
    expect((await panel.innerText()).includes("진행일지 1건"), "옮겨 갈 것이 보인다");
    await panel.getByRole("button", { name: "접수로 되돌리기" }).click();
    await page.waitForTimeout(1200);
    const hash = decodeURIComponent(page.url().split("#")[1] ?? "");
    expect(hash.startsWith("/intakes/"), `주소: ${hash}`);
    expect((await page.locator(".demoted-tag").innerText()).includes(made.id), "되돌림 표시");
    const intakeId = hash.slice("/intakes/".length);
    const intake = await api.get(`/api/intakes/${encodeURIComponent(intakeId)}`);
    equal(intake.status, "reviewing", "검토중");
    expect(intake.logs.some((log) => log.title === "현장 확인"), "진행일지가 검토 기록으로");
    equal((await fetch(`${BASE}/api/projects/${made.id}`)).status, 404, "과제는 보관함으로");
  });

  await check("보고가 있는 과제는 되돌리지 못하고 그 까닭을 말한다 (171)", async () => {
    const meta = await api.get("/api/meta");
    const made = await api.post("/api/projects", { title: "보고한 스마트 과제", type: meta.classified_type });
    await api.post(`/api/projects/${made.id}/reports/draft`, { report_date: "2026-09-15", audience: "팀 주간회의" });
    await go(`#/projects/${made.id}`);
    await page.getByRole("button", { name: "접수로 되돌리기" }).click();
    await page.waitForTimeout(500);
    const panel = page.locator(".demote-panel");
    expect((await panel.innerText()).includes("보고"), `사유: ${await panel.innerText()}`);
    equal(await panel.getByRole("button", { name: "접수로 되돌리기" }).count(), 0, "되돌리기 버튼 없음");
    await panel.getByRole("button", { name: "닫기" }).click();
    equal(await page.locator(".demote-panel").count(), 0, "닫힌다");
    await fetch(`${BASE}/api/projects/${made.id}/archive`, { method: "POST" });
  });

  console.log("\n[33] 로드맵 · 과제명 뒤 단계 띠 (TODO 174 · 175)");

  await check("로드맵이 줄기를 단계 순으로 그리고, 살펴볼 것과 선행 → 후속 화살표가 선다 (174)", async () => {
    const year = new Date().getFullYear();
    const one = await api.post("/api/projects", { title: "로드맵 1단계", status: "done", start_date: `${year - 2}-03-02`, due_date: `${year - 2}-12-18`, completed_at: `${year - 2}-12-18` });
    const two = await api.post("/api/projects", { title: "로드맵 2단계", status: "in_progress", start_date: `${year - 1}-01-05`, due_date: `${year - 1}-12-18`, predecessors: [one.id] });
    const three = await api.post("/api/projects", { title: "로드맵 3단계", status: "planned", start_date: `${year + 1}-01-05`, due_date: `${year + 1}-12-18`, predecessors: [two.id] });
    await go("#/roadmap");
    await page.waitForTimeout(800);
    const block = page.locator(`.rm-lineage[data-lineage="${one.id}"]`);
    equal(await block.count(), 1, "줄기 하나");
    expect((await block.locator(".rm-lineage-head").innerText()).includes("3단계"), "단계 수");
    equal(await block.locator(".rm-label").count(), 3, "과제 셋");
    equal(await block.locator(".rm-bar").count(), 3, "막대 셋");
    // 막대에는 번호가 아니라 과제명 — 막대 안이나 바로 옆에 (177)
    const names = await block.locator(".rm-bar span, .rm-bar-label").allInnerTexts();
    for (const title of ["로드맵 1단계", "로드맵 2단계", "로드맵 3단계"]) expect(names.includes(title), `막대 이름: ${title} / ${names}`);
    // 선은 평소에 없다 — 마우스를 올린 과제의 줄만 (180)
    equal(await block.locator(".rm-links > path").count(), 0, "평소에는 선 없음");
    await block.locator(".rm-bar").nth(1).hover();
    await page.waitForTimeout(200);
    equal(await block.locator(".rm-links > path").count(), 2, "2단계에 올리면 앞 · 뒤 선 둘");
    await block.locator(".rm-bar").nth(0).hover();
    await page.waitForTimeout(200);
    equal(await block.locator(".rm-links > path").count(), 2, "1단계에 올려도 줄 전체(1→2→3)");
    equal(await block.locator(".rm-label.even").count(), 1, "2단계 줄은 바탕을 번갈아");
    equal(await block.locator(".rm-delay").count(), 1, "마감 지난 빗금");
    expect((await page.locator(".roadmap-warnings").innerText()).includes(two.id), "살펴볼 것에 늦은 과제");
    // 혼자 가는 과제는 줄기가 아니다
    equal(await page.locator('.rm-label[data-project="' + seeded.projectA + '"]').count(), 0, "외톨이 과제는 없다");
    // 막대를 누르면 그 과제로, 돌아오는 길은 로드맵
    await block.locator(".rm-bar").nth(1).click();
    await page.waitForTimeout(800);
    expect(page.url().includes(`/projects/${two.id}`), `이동: ${page.url()}`);
    equal((await page.locator("a.back").first().innerText()).includes("로드맵"), true, "← 로드맵");
    // 과제 상세의 [로드맵에서 보기]
    await page.locator(".lineage-roadmap").click();
    await page.waitForTimeout(900);
    expect(page.url().includes("focus="), `주소: ${page.url()}`);
    equal(await page.locator(".rm-lineage.focused").count(), 1, "그 줄기를 짚는다");
    // 거르기 — 검색어는 주소에 남는다
    await page.locator('.roadmap input[aria-label="검색어"]').fill("없는줄기");
    await page.waitForTimeout(400);
    equal(await page.locator(".rm-lineage").count(), 0, "거르면 사라진다");
    expect(page.url().includes("q="), "주소에 조건");
    for (const item of [three, two, one]) await fetch(`${BASE}/api/projects/${item.id}/archive`, { method: "POST" });
  });

  await check("한 단계에 여럿이면 이름 칸에 '← 앞 과제', 다른 갈래는 올렸을 때 흐려진다 (180)", async () => {
    const root = await api.post("/api/projects", { title: "갈래 뿌리", start_date: "2025-01-02", due_date: "2025-12-19" });
    const left = await api.post("/api/projects", { title: "갈래 왼쪽", start_date: "2026-01-05", due_date: "2026-12-18", predecessors: [root.id] });
    const right = await api.post("/api/projects", { title: "갈래 오른쪽", start_date: "2026-02-02", due_date: "2026-11-30", predecessors: [root.id] });
    await go("#/roadmap");
    await page.waitForTimeout(800);
    const block = page.locator(`.rm-lineage[data-lineage="${root.id}"]`);
    equal(await block.locator(".rm-preds").count(), 2, "← 앞 과제 둘");
    expect((await block.locator(".rm-preds").first().innerText()).includes(root.id), "앞 과제 번호");
    await block.locator(`.rm-label[data-project="${left.id}"]`).hover();
    await page.waitForTimeout(200);
    expect((await block.locator(`.rm-label[data-project="${right.id}"]`).getAttribute("class")).includes("dim"), "다른 갈래는 흐리게");
    equal(await block.locator(".rm-links > path").count(), 1, "선은 그 과제와 앞 과제 사이 하나");
    for (const item of [right, left, root]) await fetch(`${BASE}/api/projects/${item.id}/archive`, { method: "POST" });
  });

  await check("다년도 과제의 이름 뒤에 단계 띠가 선다 — 과제목록 · 상세 · 보고대상 · 검색 (175)", async () => {
    const one = await api.post("/api/projects", { title: "띠확인 앞단계" });
    const two = await api.post("/api/projects", { title: "띠확인 뒷단계", predecessors: [one.id] });
    await go("#/projects");
    const row = page.locator("tr", { hasText: "띠확인 뒷단계" });
    equal((await row.locator(".stage-band").innerText()).trim(), "2단계", "목록");
    equal(await page.locator("tr", { hasText: "고강도 소재 개발" }).locator(".stage-band").count(), 0, "단년도 과제에는 없다");
    await go(`#/projects/${two.id}`);
    equal((await page.locator("h1 .stage-band").innerText()).trim(), "2단계", "상세 제목");
    await go("#/reports");
    equal((await page.locator("tr", { hasText: "띠확인 앞단계" }).locator(".stage-band").innerText()).trim(), "1단계", "보고대상");
    await go(`#/search?q=${encodeURIComponent("띠확인")}`);
    await page.waitForTimeout(500);
    expect((await page.locator(".result-list .stage-band").count()) >= 2, "검색");
    for (const item of [two, one]) await fetch(`${BASE}/api/projects/${item.id}/archive`, { method: "POST" });
  });

  console.log("\n[34] 연도 = 수행기간 · 신규 착수 · 효과는 끝나는 해 (TODO 181)");

  await check("다년도 과제가 다음 해에도 보이고, 효과는 끝나는 해에만 더한다 (181)", async () => {
    const year = new Date().getFullYear();
    const made = await api.post("/api/projects", {
      title: "두 해 과제", status: "in_progress", start_date: `${year}-01-05`, due_date: `${year + 1}-12-18`, effect_expected: 7,
    });
    // 올해 목록: 보이지만 효과는 흐리게(내년에 센다) · 합계에서 빠진다
    await go(`#/projects?year=${year}`);
    await page.reload(); // 연도 목록은 켤 때 읽는다 — API 로 만든 과제라 화면이 모른다(화면에서 만들면 다시 읽는다)
    await page.waitForTimeout(1000);
    const row = page.locator("tr", { hasText: "두 해 과제" });
    equal(await row.count(), 1, "올해 목록");
    equal(await row.locator(".effect.elsewhere").count(), 1, "효과는 다른 해에 센다(흐리게)");
    // 내년을 고를 수 있고, 거기에도 보인다
    const options = await page.locator('select[aria-label="연도"] option').allInnerTexts();
    expect(options.includes(`${year + 1}년`), `연도 목록: ${options}`);
    await go(`#/projects?year=${year + 1}`);
    await page.waitForTimeout(700);
    equal(await page.locator("tr", { hasText: "두 해 과제" }).locator(".effect.elsewhere").count(), 0, "내년 목록 — 효과를 센다");
    expect((await page.locator("tfoot").innerText()).includes("7.0"), "내년 합계 줄에 7.0");
    // [신규 착수만] — 내년에는 신규가 아니다
    await page.locator(".list-new-check input").check();
    await page.waitForTimeout(600);
    equal(await page.locator("tr", { hasText: "두 해 과제" }).count(), 0, "내년의 신규가 아니다");
    // 홈: 올해 신규 착수 칸, 효과 기준 안내
    await go("#/");
    await page.waitForTimeout(900);
    const stats = await page.locator(".home-team .home-stat-label").allInnerTexts();
    expect(stats.includes("신규 착수"), `팀 현황 칸: ${stats}`);
    expect(stats.some((text) => text.includes("끝나는 해 기준")), "효과 금액 기준");
    equal(stats.filter((text) => text.includes("끝낸 과제")).length, 0, "완료 숫자는 하나");
    await fetch(`${BASE}/api/projects/${made.id}/archive`, { method: "POST" });
  });

  console.log("\n[35] 팀원 면담 기록 — 하기로 한 것 · 먼저 볼 사람 · 검색 제외 (TODO 182)");

  await check("면담을 남기고, 하기로 한 것을 닫고, 사람별 표에 마지막 면담이 선다 (182)", async () => {
    await go(`#/skills?person=${encodeURIComponent("권경락")}`);
    await page.waitForTimeout(800);
    const panel = page.locator(".meeting-panel");
    equal(await panel.count(), 1, "면담 칸");
    await panel.getByRole("button", { name: "면담 추가" }).click();
    const form = panel.locator(".meeting-form");
    equal(await form.locator("input").first().inputValue(), "권경락", "고른 사람이 채워진다");
    await form.locator('input[type="date"]').first().fill("2026-09-15");
    await form.getByPlaceholder(/3분기 목표 점검/).fill("시험 면담 — 목표 점검");
    await form.locator('input[aria-label="하기로 한 것 1"]').fill("교육 신청서 내기");
    await form.getByRole("button", { name: "+ 줄 추가" }).click();
    await form.locator('input[aria-label="하기로 한 것 2"]').fill("멘토 정하기");
    await form.getByRole("button", { name: "저장" }).click();
    await page.waitForTimeout(900);
    const item = panel.locator(".meeting-item", { hasText: "시험 면담" });
    equal(await item.count(), 1, "목록에 선다");
    equal(await item.locator(".meeting-followups input").count(), 2, "하기로 한 것 둘");
    // 하나 닫기
    // 저장한 뒤 다시 읽어 표시한다 — 누른 즉시가 아니라 잠시 뒤에 바뀐다
    await item.locator(".meeting-followups input").first().click();
    await page.waitForTimeout(900);
    equal(await item.locator(".meeting-followups li.done").count(), 1, "닫힌 줄");
    // 사람별 표 — 마지막 면담 · 열린 것 1
    const row = page.locator(".skills-table tr", { hasText: "권경락" });
    expect((await row.innerText()).includes("2026-09-15"), "마지막 면담");
    // 사람을 고르지 않으면 팀 전체의 열린 것
    await go("#/skills");
    await page.waitForTimeout(800);
    expect((await page.locator(".meeting-open-list").innerText()).includes("멘토 정하기"), "팀 전체 열린 것");
    // 통합 검색에 걸리지 않는다
    await go(`#/search?q=${encodeURIComponent("시험 면담")}`);
    await page.waitForTimeout(600);
    equal(await page.locator(".result-list li", { hasText: "시험 면담" }).count(), 0, "검색 제외");
    // 지우기 — 보관함 · 이전 버전 안내
    await go(`#/skills?person=${encodeURIComponent("권경락")}`);
    await page.waitForTimeout(800);
    let asked = "";
    nextDialog((dialog) => { asked = dialog.message(); dialog.accept(); });
    await page.locator(".meeting-item", { hasText: "시험 면담" }).getByRole("button", { name: "삭제" }).click();
    await page.waitForTimeout(800);
    expect(asked.includes("보관함"), `확인 창: ${asked}`);
    equal(await page.locator(".meeting-item", { hasText: "시험 면담" }).count(), 0, "지워졌다");
  });

  console.log("\n[36] 지난해 목록의 상태 칸 · 팀원역량에서 고른 사람 풀기 (TODO 183 · 184 · 185)");

  await check("지난해를 고르면 상태 칸이 그 해의 상태 — 옆에 지금 상태 (184)", async () => {
    const year = new Date().getFullYear();
    const made = await api.post("/api/projects", {
      title: "이듬해 끝낸 과제", status: "done", start_date: `${year - 1}-01-01`, due_date: `${year}-06-30`,
      completed_at: `${year}-06-20`,
    });
    await go(`#/projects?year=${year - 1}`);
    await page.reload(); // 연도 목록은 켤 때 읽는다
    await page.waitForTimeout(1000);
    const last = page.locator("tr", { hasText: "이듬해 끝낸 과제" });
    equal(await last.locator(".status").innerText(), "진행중", "지난해에는 진행중");
    expect((await last.locator(".year-status-now").innerText()).includes(`${year}-06-20`), "옆에 지금 상태(완료일)");
    // [진행중] 으로 거른 줄의 딱지는 모두 진행중 — 숫자와 같은 기준
    await go(`#/projects?year=${year - 1}&status=in_progress`);
    await page.waitForTimeout(800);
    const badges = await page.locator("tbody .status").allInnerTexts();
    expect(badges.length > 0 && badges.every((text) => text === "진행중"), `딱지: ${badges}`);
    // 올해에는 완료, 덧붙임 없음
    await go(`#/projects?year=${year}`);
    await page.waitForTimeout(800);
    const now = page.locator("tr", { hasText: "이듬해 끝낸 과제" });
    equal(await now.locator(".status").innerText(), "완료", "올해에는 완료");
    equal(await now.locator(".year-status-now").count(), 0, "지금 상태와 같으면 덧붙이지 않는다");
    await fetch(`${BASE}/api/projects/${made.id}/archive`, { method: "POST" });
  });

  await check("고른 사람은 좁혀지는 두 칸 위의 띠 [팀 전체로 ×] · 다시 누르기로 푼다 (183 · 185)", async () => {
    await go(`#/skills?person=${encodeURIComponent("권경락")}`);
    await page.waitForTimeout(800);
    const bar = page.locator(".skills-person-bar");
    expect((await bar.innerText()).includes("권경락"), "띠에 보는 사람");
    // 기준 연도 옆(화면 머리)에는 없다 — 화면 전체가 바뀐 것처럼 읽혔다 (185)
    equal(await page.locator(".home-head .skills-person-bar, .home-head .skills-person-chip").count(), 0, "머리에는 없다");
    // 띠는 사람별 표 아래, 면담 칸 바로 위
    const order = await page.evaluate(() => {
      const cards = [...document.querySelectorAll(".card")];
      const at = (selector) => cards.findIndex((card) => card.matches(selector) || card.querySelector(selector));
      return { table: at(".skills-table"), bar: at(".skills-person-bar"), meeting: at(".meeting-panel") };
    });
    expect(order.table < order.bar && order.bar + 1 === order.meeting, `칸 순서: ${JSON.stringify(order)}`);
    equal(await page.locator(".skills-table tr.picked-row", { hasText: "권경락" }).count(), 1, "표에서 고른 줄");
    // 띠의 [팀 전체로 ×]
    await bar.getByRole("button", { name: /팀 전체로/ }).click();
    await page.waitForTimeout(700);
    equal(await bar.count(), 0, "띠가 사라진다");
    expect(!page.url().includes("person="), `주소에서도 빠진다: ${page.url()}`);
    expect((await page.locator(".meeting-panel h2").innerText()).includes("팀 전체"), "면담 칸이 팀 전체로");
    // 표에서 고르면 띠가 서고, 이름을 한 번 더 누르면 풀린다
    await page.locator(".skills-table button", { hasText: "권경락" }).click();
    await page.waitForTimeout(700);
    equal(await bar.count(), 1, "표에서 고르면 띠가 선다");
    await page.locator(".skills-table button", { hasText: "권경락" }).click();
    await page.waitForTimeout(700);
    equal(await bar.count(), 0, "이름을 다시 누르면 풀린다");
    // 먼저 볼 사람 칩 — 다시 누르면 풀린다
    const quiet = page.locator(".skills-quiet-chip").first();
    if ((await quiet.count()) > 0) {
      await quiet.click();
      await page.waitForTimeout(700);
      equal(await page.locator(".skills-quiet-chip.on").count(), 1, "고른 칩은 눌린 모양");
      await page.locator(".skills-quiet-chip.on").click();
      await page.waitForTimeout(700);
      equal(await bar.count(), 0, "칩을 다시 누르면 풀린다");
    }
  });

  console.log("\n[4] 화면 오류가 하나도 없었는가");
  await check("전체를 도는 동안 화면 오류가 없다", () => {
    equal(pageErrors.length, 0, `화면 오류: ${JSON.stringify(pageErrors.slice(0, 5), null, 1)}`);
  });

  await browser.close();
  server.kill();
  await rm(vault, { recursive: true, force: true });
  await rm(`${vault}-backup`, { recursive: true, force: true });

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
