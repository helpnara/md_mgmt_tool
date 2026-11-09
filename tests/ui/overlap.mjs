/**
 * 겹침 전수 조사 (TODO 252 마무리) — 모든 화면 · 탭 · 연 상태(폼 · 창 · 메뉴) × 네 폭(900 · 1100 · 1440 · 1920)에서
 * 글자 겹침 · 부품 겹침 · 잘린 글자 · 카드 밖으로 나간 글자 · 가로 스크롤을 센다.
 *
 * 보이는 부분만 본다(overflow 로 잘린 조상 · 접힌 설명은 뺀다). 창 · 펼침 메뉴 · 고정 머리줄처럼 위에 뜨는 겹은 일부러 덮으므로
 * 같은 겹끼리만 비교한다. 긴 과제 이름 · 긴 사람 이름 · 긴 접수 제목을 넣은 가상 데이터로 돈다.
 *
 * 실행:  node tests/ui/overlap.mjs [결과 폴더]     → 결과 폴더/audit.json, 화면에 갈래별 건수 ({} 이면 깨끗)
 * 화면 시험(screens.mjs)과 따로 둔다 — 한 번에 144 화면을 훑어 느리고, 디자인을 크게 바꾼 뒤에 돌리는 것이다.
 */
import { createRequire } from "node:module";
import { spawn } from "node:child_process";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
const require = createRequire(import.meta.url);
import { fileURLToPath } from "node:url";
const { chromium } = (() => { for (const name of ["playwright", "/opt/node22/lib/node_modules/playwright", "/usr/lib/node_modules/playwright"]) { try { return require(name); } catch { /* 다음 */ } } throw new Error("playwright 를 찾지 못했습니다"); })();
const REPO = fileURLToPath(new URL("../..", import.meta.url));
const OUT = process.argv[2] || tmpdir();
const PORT = Number(process.env.UI_TEST_PORT || 8770);
const BASE = `http://127.0.0.1:${PORT}`;
const vault = await mkdtemp(join(tmpdir(), "audit-"));
const server = spawn(join(REPO, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python"), ["-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--port", String(PORT)],
  { cwd: REPO, env: { ...process.env, MD_MGMT_VAULT: vault, MD_MGMT_TODAY: "2026-11-09" }, stdio: "ignore" });
for (let i = 0; i < 80; i++) { try { await fetch(`${BASE}/api/meta`); break; } catch { await new Promise((r) => setTimeout(r, 300)); } }
const call = (m, p, b) => fetch(BASE + p, { method: m, headers: { "content-type": "application/json" }, body: b ? JSON.stringify(b) : undefined }).then(async (r) => { const t = await r.text(); try { return JSON.parse(t); } catch { return t; } });
const names = ["김민준", "이서연", "박도윤", "최지우", "정하준", "강서윤", "남궁예린아", "조은우"];
await call("PUT", "/api/people", { people: names.map((name) => ({ name })) });
const st = ["in_progress", "in_progress", "planned", "reviewing", "done", "on_hold", "dropped"];
const types = ["rnd", "smart", "improve", "rnd"];
const ids = [];
for (let i = 0; i < 22; i++) {
  const long = i % 5 === 0 ? " — 고온 고압 환경에서 장시간 운전 시 발생하는 열피로 균열 원인 분석과 개선안 도출" : "";
  const r = await call("POST", "/api/projects", { title: `과제 ${i + 1}${long}`, status: st[i % st.length], type: types[i % 4],
    owners: i % 6 === 0 ? [names[i % 8], names[(i + 3) % 8]] : [names[i % 8]], start_date: `2026-0${1 + (i % 8)}-01`, due_date: `2026-${String(2 + (i % 11)).padStart(2, "0")}-15`,
    effect_expected: i % 3 ? 2.5 : null, group: i % 4 ? "본부장 지시" : "주간 회의체", tags: i % 2 ? ["자동화", "품질"] : [] });
  if (r && r.id) ids.push(r.id);
}
for (let d = 1; d <= 6; d++) await call("POST", `/api/projects/${ids[0]}/entries`, { date: `2026-10-0${d}`, title: `${d}차 진행 — 설비 조건 변경 시험 결과 정리`, body: "## 내용\n\n" + "조건을 바꿔 가며 시험했다. ".repeat(12) + "\n\n## 계획\n\n다음 주 2차 시험\n" });
const draft = await call("POST", `/api/projects/${ids[0]}/reports/draft`, { report_date: "2026-11-03", audience: "전사 주요업무 보고" });
if (draft && draft.id) await call("POST", `/api/reports/${draft.id}/freeze`);
const draft2 = await call("POST", `/api/projects/${ids[0]}/reports/draft`, { report_date: "2026-11-10", audience: "팀 주간회의" });
for (let i = 0; i < 5; i++) await call("POST", "/api/intakes", { title: i === 0 ? "접수 — 생산 라인 비전 검사 불량 오검출 개선 요청 (품질팀 · 2공장 · 긴급)" : `접수 ${i + 1}` });
const intakes = await call("GET", "/api/intakes");
for (let i = 0; i < 4; i++) await call("POST", "/api/activities", { person: names[(i + 2) % 8], kind: "education", title: `다가오는 교육 ${i} — 품질 데이터 분석 실무`, date: `2026-11-${String(20 + i).padStart(2, "0")}` });
for (let i = 0; i < 16; i++) await call("POST", "/api/activities", { person: names[i % 8], kind: i % 3 ? "education" : "seminar", title: i % 4 ? `교육 ${i}` : "스마트 팩토리 데이터 분석 실무 과정 (심화 · 3일)", date: i < 3 ? `2026-11-${String(15 + i).padStart(2, "0")}` : `2026-${String(1 + (i % 10)).padStart(2, "0")}-1${i % 9}`, hours: i % 2 ? 8 : null, host: "한국생산성본부" });
await call("POST", "/api/meetings", { person: names[1], date: "2026-10-20", title: "3분기 목표 점검", followups: ["교육 신청서 내기", "멘토 정하기"] });
const intakeId = Array.isArray(intakes) ? intakes[0]?.id : (intakes.items?.[0]?.id);
const routes = [
  ["home", "#/"], ["home-status", "#/?tab=status"], ["intakes", "#/intakes"], ["intake", `#/intakes/${intakeId}`],
  ["projects", "#/projects"], ["board", "#/projects?view=board"], ["detail", `#/projects/${ids[0]}`], ["detail-long", `#/projects/${ids[5]}`],
  ["report-editor", `#/projects/${ids[0]}?report=${draft2?.id}`], ["roadmap", "#/roadmap"], ["reports", "#/reports"], ["history", "#/history"],
  ["skills", "#/skills"], ["skills-records", `#/skills?tab=records&person=${encodeURIComponent(names[1])}`], ["skills-meetings", `#/skills?tab=meetings&person=${encodeURIComponent(names[1])}`],
  ["person", `#/person/${encodeURIComponent(names[0])}`], ["search", `#/search?q=${encodeURIComponent("과제")}`], ["help", "#/help"],
  ...["", "class", "report", "forms", "backup", "check"].map((t) => [`settings-${t || "basic"}`, `#/settings${t ? `?tab=${t}` : ""}`]),
];
const AUDIT = () => {
  const vis = (el) => { const s = getComputedStyle(el); if (s.visibility === "hidden" || s.display === "none" || +s.opacity === 0) return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const path = (el) => { const p = []; for (let e = el; e && e !== document.body && p.length < 4; e = e.parentElement) p.unshift(e.tagName.toLowerCase() + (e.className && typeof e.className === "string" ? "." + e.className.trim().split(/\s+/).slice(0, 2).join(".") : "")); return p.join(" > "); };
  const scrollAnc = (el, stop) => { for (let e = el.parentElement; e && e !== stop; e = e.parentElement) { const s = getComputedStyle(e); if (/(auto|scroll|hidden|clip)/.test(s.overflowX + s.overflowY)) return e; } return null; };
  const out = [];
  // 보이는 부분만 — overflow 로 잘린 조상(접힌 설명 · 스크롤 상자)의 상자와 겹친 만큼만 남긴다
  const clipOf = (el) => { let c = { left: -1e9, top: -1e9, right: 1e9, bottom: 1e9 }; for (let e = el; e && e !== document.documentElement; e = e.parentElement) { const s = getComputedStyle(e); if (/(auto|scroll|hidden|clip)/.test(s.overflowX + s.overflowY)) { const r = e.getBoundingClientRect(); c = { left: Math.max(c.left, r.left), top: Math.max(c.top, r.top), right: Math.min(c.right, r.right), bottom: Math.min(c.bottom, r.bottom) }; } } return c; };
  const clip = (r, c) => ({ left: Math.max(r.left, c.left), top: Math.max(r.top, c.top), right: Math.min(r.right, c.right), bottom: Math.min(r.bottom, c.bottom) });
  const live = (r) => r.right - r.left > 1 && r.bottom - r.top > 1;
  // 겹(layer) — 창 · 펼침 메뉴 · 고정 머리줄처럼 위에 뜨는 것은 일부러 덮는다. 같은 겹끼리만 비교한다
  const layerOf = (el) => { for (let e = el; e && e !== document.documentElement; e = e.parentElement) { const s = getComputedStyle(e); if (s.position === "fixed" || s.position === "sticky" || (s.position === "absolute" && s.zIndex !== "auto")) return e; } return document.documentElement; };
  const modalOpen = document.querySelector(".modal-backdrop");
  if (document.scrollingElement.scrollWidth > innerWidth + 1) out.push({ kind: "가로스크롤", where: `${document.scrollingElement.scrollWidth} > ${innerWidth}` });
  // 글자 조각
  const texts = []; const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n; (n = w.nextNode());) {
    if (!n.textContent.trim() || !n.parentElement || !vis(n.parentElement)) continue;
    if (n.parentElement.closest("textarea, select, option, script, style, [hidden], .explain-more[hidden]")) continue;
    if (modalOpen && !modalOpen.contains(n.parentElement)) continue;
    const range = document.createRange(); range.selectNodeContents(n);
    const c = clipOf(n.parentElement);
    for (const raw of range.getClientRects()) { const r = clip(raw, c); if (live(r)) texts.push({ r, raw, n, el: n.parentElement }); }
  }
  const hit = (a, b, m = 1) => Math.min(a.right, b.right) - Math.max(a.left, b.left) > m && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > m;
  texts.sort((a, b) => a.r.top - b.r.top);
  for (let i = 0; i < texts.length; i++) for (let j = i + 1; j < texts.length && texts[j].r.top < texts[i].r.bottom; j++) {
    const A = texts[i], B = texts[j]; if (A.n === B.n) continue;
    // 서로 다른 겹(위에 뜬 창 · 잘린 칸 안)이면 건너뛴다
    if (layerOf(A.el) !== layerOf(B.el)) continue;
    if (hit(A.r, B.r, 2)) {
      const sa = scrollAnc(A.el), sb = scrollAnc(B.el);
      out.push({ kind: "글자겹침", where: path(A.el) + "  ×  " + path(B.el), text: `${A.n.textContent.trim().slice(0, 24)} / ${B.n.textContent.trim().slice(0, 24)}`, same: sa === sb });
    }
  }
  // 부품
  const parts = [...document.querySelectorAll("main button, main a, main input:not([type=hidden]), main select, main textarea, main .tag, main .status, main .icon-tile, main .home-stat, main h1, main h2, main h3, .modal button, .modal input, .modal select, .modal textarea, .modal label")].filter(vis);
  const boxes = parts.map((el) => ({ el, r: clip(el.getBoundingClientRect(), clipOf(el.parentElement)) })).filter((b) => live(b.r)).sort((a, b) => a.r.top - b.r.top);
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length && boxes[j].r.top < boxes[i].r.bottom; j++) {
    const A = boxes[i], B = boxes[j]; if (A.el.contains(B.el) || B.el.contains(A.el)) continue;
    if (layerOf(A.el) !== layerOf(B.el)) continue;
    if (modalOpen && (!modalOpen.contains(A.el) || !modalOpen.contains(B.el))) continue;
    if (hit(A.r, B.r, 2)) out.push({ kind: "부품겹침", where: path(A.el) + "  ×  " + path(B.el), text: `${(A.el.innerText || A.el.value || "").trim().slice(0, 20)} / ${(B.el.innerText || B.el.value || "").trim().slice(0, 20)}` });
  }
  // 잘린 글자 · 상자 밖으로 나간 글자
  for (const el of document.querySelectorAll("main button, main .tag, main .status, main .dash-chip, main .people-pill, main th, main h1, main h2, main h3, main label, main .home-stat-label, main .home-stat strong, main .view-tab, main a.button-like")) {
    if (!vis(el)) continue; const s = getComputedStyle(el);
    if (el.scrollWidth > el.clientWidth + 1 && s.textOverflow !== "ellipsis" && !/(auto|scroll)/.test(s.overflowX)) out.push({ kind: s.overflowX === "visible" ? "글자넘침" : "글자잘림", where: path(el), text: (el.innerText || "").trim().slice(0, 30), d: el.scrollWidth - el.clientWidth });
  }
  // 카드 밖으로 나감
  for (const card of document.querySelectorAll("main .card")) {
    if (!vis(card)) continue; const cr = card.getBoundingClientRect();
    for (const t of texts) if (card.contains(t.el) && !scrollAnc(t.el, card) && (t.r.right > cr.right + 1 || t.r.left < cr.left - 1)) out.push({ kind: "카드밖", where: path(t.el), text: t.n.textContent.trim().slice(0, 30), d: Math.round(Math.max(t.r.right - cr.right, cr.left - t.r.left)) });
  }
  return out;
};
// 열고 닫는 것까지 — 폼 · 창 · 메뉴를 연 상태 (route, 누를 단추 이름)
const actions = [
  ["projects+과제 추가", "#/projects", "과제 추가"], ["detail+기록 추가", `#/projects/${ids[0]}`, "기록 추가"], ["detail+개요 수정", `#/projects/${ids[0]}`, "수정"],
  ["detail+내보내기", `#/projects/${ids[0]}`, "내보내기"], ["detail+과제 정보 수정", `#/projects/${ids[0]}`, "과제 정보 수정"],
  ["skills+기록 추가", "#/skills", "기록 추가"], ["skills-meetings+면담 추가", `#/skills?tab=meetings&person=${encodeURIComponent(names[1])}`, "면담 추가"],
  ["intakes+접수 등록", "#/intakes", "접수 등록"], ["intake+체크리스트", `#/intakes/${intakeId}`, "체크리스트"], ["intake+승격", `#/intakes/${intakeId}`, "승격"],
  ["settings+사람 추가", "#/settings", "사람 추가"], ["home+나머지", "#/", "나머지"],
];
const browser = await chromium.launch();
const all = [];
for (const width of [900, 1100, 1440, 1920]) {
  const page = await browser.newPage({ viewport: { width, height: 900 } });
  page.on("dialog", (d) => d.accept().catch(() => {}));
  for (const [name, hash] of routes) {
    await page.goto(`${BASE}/${hash}`); await page.waitForTimeout(1300);
    // 숨은 설명 펼치기는 하지 않는다 — 기본 화면 그대로
    const found = await page.evaluate(AUDIT);
    for (const f of found) all.push({ width, route: name, ...f });
  }
  for (const [name, hash, label] of actions) {
    await page.goto(`${BASE}/${hash}`); await page.reload(); await page.waitForTimeout(1300);
    const btn = (label === "수정" ? page.locator(".detail-left .card-head button", { hasText: /^수정$/ }) : page.getByRole("button", { name: new RegExp(label) })).first();
    if (!(await btn.count())) { all.push({ width, route: name, kind: "단추없음", where: label }); continue; }
    await btn.click().catch(() => {}); await page.waitForTimeout(700);
    for (const f of await page.evaluate(AUDIT)) all.push({ width, route: name, ...f });
  }
  await page.close();
}
const key = (f) => `${f.kind}|${f.route}|${f.where}|${f.text ?? ""}`;
const uniq = new Map(); for (const f of all) { const k = key(f); const u = uniq.get(k) || { ...f, widths: [] }; u.widths.push(f.width); uniq.set(k, u); }
const list = [...uniq.values()];
await writeFile(join(OUT, "audit.json"), JSON.stringify(list, null, 1));
const byKind = {}; for (const f of list) byKind[f.kind] = (byKind[f.kind] || 0) + 1;
console.log(JSON.stringify(byKind));
await browser.close(); server.kill();
