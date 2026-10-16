/**
 * 입력 규칙 — 화면이 서버보다 **먼저** 알려 주기 위한 한 자리 (TODO 214 · 216).
 *
 * 서버가 마지막에 지키는 규칙(`backend/app/schemas.py`)과 같은 수를 쓴다. 화면은 저장 단추를 끄고 칸 옆에 이유를 적는다 —
 * 사용자가 [저장] 을 누른 뒤에야 거절을 보지 않게. 여러 화면이 같은 규칙을 따로 적으면 한쪽만 고쳐진다(회고 2번 모양)라 여기에 모은다.
 */
import type { Meta, Person } from "./types";

/** 날짜가 놓일 수 있는 해 (D5) — 9999 같은 값이 "최근 갱신" · 보고 대상을 망가뜨렸다 */
export const YEAR_MIN = 2000;
export const YEAR_MAX = 2100;

/** 글 길이 상한 (D14) — 서버와 같은 수 */
export const LIMITS = { title: 100, name: 40, group: 40 } as const;

/** 효과 금액 확인 기준선의 기본값 (D4, 억원/년). 설정 `effect_confirm_over` 가 있으면 그것을 쓴다. 0 이면 묻지 않는다 */
export const EFFECT_CONFIRM_DEFAULT = 100;

/** 이 PC 의 오늘 (YYYY-MM-DD) */
export function today(): string {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 10);
}

/** YYYY-MM-DD 에 날짜 더하기 — 달력 칸의 `min` 등에 쓴다 */
export function addDays(day: string, days: number): string {
  const [y, m, d] = day.split("-").map(Number);
  const date = new Date(Date.UTC(y, (m || 1) - 1, d || 1));
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

/** 달력 칸의 하한 · 상한으로 쓰는 값 */
export const DATE_MIN = `${YEAR_MIN}-01-01`;
export const DATE_MAX = `${YEAR_MAX}-12-31`;

/** 날짜 한 칸의 문제 — 없으면 null. 비어 있으면 문제 아님(필수 여부는 부르는 쪽이 본다) */
export function dateProblem(day: string | null | undefined, label = "날짜"): string | null {
  if (!day) return null;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return `${label}는 2026-03-01 처럼 적어 주세요.`;
  const year = Number(day.slice(0, 4));
  if (year < YEAR_MIN || year > YEAR_MAX) return `${label}는 ${YEAR_MIN}~${YEAR_MAX}년 사이여야 합니다.`;
  return null;
}

/** 앞 날짜보다 뒤 날짜가 앞서면 문제 — `strict` 면 같은 날도 문제(다음 면담처럼) */
export function orderProblem(
  first: string | null | undefined,
  second: string | null | undefined,
  message: string,
  strict = false,
): string | null {
  if (!first || !second) return null;
  return strict ? (second <= first ? message : null) : second < first ? message : null;
}

/** 미래 날짜인가 (오늘 기준) */
export function isFuture(day: string | null | undefined): boolean {
  return Boolean(day) && (day as string) > today();
}

/** 글 길이 — 남은 글자와 넘었는지 */
export function lengthState(value: string, limit: number): { left: number; over: boolean } {
  const length = [...value].length;
  return { left: limit - length, over: length > limit };
}

/** 줄바꿈 · 제어문자가 섞였는가 (한 줄 칸) */
export function hasControlChars(value: string): boolean {
  // eslint-disable-next-line no-control-regex
  return /[\u0000-\u001f\u007f]/.test(value);
}

/** 쉼표로 나눈 이름들 — 서버의 `split_list` 와 같은 규칙(앞뒤 공백 정리 · 빈 것 버림 · 겹친 것 하나로) */
export function splitNames(value: string): string[] {
  const out: string[] = [];
  for (const part of value.split(",")) {
    const name = part.replace(/\s+/g, " ").trim();
    if (name && !out.includes(name)) out.push(name);
  }
  return out;
}

/** 태그 하나를 서버와 같은 모양으로 — 앞의 `#` 떼고 공백 정리 (D12) */
export function normalizeTag(tag: string): string {
  return tag.replace(/^#+/, "").replace(/\s+/g, " ").trim();
}

/** 이미 쓰는 태그 가운데 대소문자 · 띄어쓰기만 다른 것 — 있으면 그 표기를 쓰게 권한다 (D12) */
export function sameTagAs(tag: string, known: string[]): string | null {
  const key = normalizeTag(tag).toLowerCase().replace(/\s/g, "");
  if (!key) return null;
  const hit = known.find((item) => normalizeTag(item).toLowerCase().replace(/\s/g, "") === key);
  return hit && hit !== tag ? hit : null;
}

/** 비슷한 팀 이름 — 띄어쓰기 · 대소문자만 다른 것 (D13). 같으면 null */
export function similarTeam(name: string, known: string[]): string | null {
  const key = name.toLowerCase().replace(/\s/g, "");
  if (!key) return null;
  const hit = known.find((item) => item !== name && item.toLowerCase().replace(/\s/g, "") === key);
  return hit ?? null;
}

/** 떠난 사람인가 — 떠난 날이 **오늘 이후면 아직 있는 사람** (D8) */
export function isDeparted(person: Pick<Person, "left_on"> | undefined | null): boolean {
  return Boolean(person?.left_on) && (person!.left_on as string) <= today();
}

/**
 * 이름들을 명부와 견준다 (D6 · D7).
 * - `unknown` — 명부에 없는 이름(명부가 비어 있으면 묻지 않으므로 빈 목록)
 * - `departed` — 이미 떠난 사람
 */
export function checkPeople(names: string[], meta: Pick<Meta, "people" | "people_left">): { unknown: string[]; departed: string[] } {
  const active = new Set(meta.people ?? []);
  const left = new Map((meta.people_left ?? []).map((person) => [person.name, person]));
  if (active.size === 0 && left.size === 0) return { unknown: [], departed: [] };
  const unknown: string[] = [];
  const departed: string[] = [];
  for (const name of names) {
    if (left.has(name) && isDeparted(left.get(name))) departed.push(name);
    else if (!active.has(name) && !left.has(name)) unknown.push(name);
  }
  return { unknown, departed };
}

/**
 * 저장 전에 묻는다 — 명부에 없는 이름은 "추가할까요?", 떠난 사람은 "그래도 맡길까요?" (D6 · D7).
 * 돌려주는 값: 계속 저장해도 되면 true. 추가하기로 한 이름은 `addPerson` 으로 명부에 넣는다.
 * **자동으로 넣지 않는다** — 예전에 면담 · 역량 기록이 오타를 명부에 조용히 넣었다.
 */
export async function confirmPeople(
  names: string[],
  meta: Pick<Meta, "people" | "people_left">,
  addPerson: (name: string) => Promise<unknown>,
  role = "담당자",
): Promise<boolean> {
  const { unknown, departed } = checkPeople(names, meta);
  if (departed.length > 0) {
    const ok = window.confirm(`${departed.join(", ")} — 명부에서 떠난 사람입니다. 그래도 ${role}(으)로 적을까요?`);
    if (!ok) return false;
  }
  if (unknown.length > 0) {
    const add = window.confirm(
      `명부에 없는 이름입니다: ${unknown.join(", ")}\n\n[확인] 명부에 추가하고 저장 · [취소] 이름을 고치러 돌아가기`,
    );
    if (!add) return false;
    for (const name of unknown) await addPerson(name);
  }
  return true;
}

/** 효과 금액의 단위를 확인할 때인가 (D4). 기준선이 0 이면 묻지 않는다 */
export function effectThreshold(meta: Partial<Meta> & { effect_confirm_over?: number | null }): number {
  const value = meta.effect_confirm_over;
  return typeof value === "number" && value >= 0 ? value : EFFECT_CONFIRM_DEFAULT;
}

/** 저장 전에 큰 효과 금액을 확인한다 (D4) — 계속 저장해도 되면 true */
export function confirmEffects(
  values: { label: string; value: number | null | undefined }[],
  meta: Partial<Meta> & { effect_confirm_over?: number | null },
): boolean {
  const limit = effectThreshold(meta);
  if (limit <= 0) return true;
  const big = values.filter((item) => typeof item.value === "number" && (item.value as number) > limit);
  if (big.length === 0) return true;
  const lines = big.map((item) => `${item.label} ${item.value}억원/년`).join(", ");
  return window.confirm(`${lines} — 한 과제에 ${limit}억원/년을 넘습니다.\n단위(억원/년)가 맞는지 확인해 주세요. 이대로 저장할까요?`);
}

// ── TODO 214 과제 · 기록 · 접수 입력 (F1) ──────────────────────────────────────

/** 효과 금액 한 칸의 문제 (U4) — `<form>` 밖 칸은 `min` · `step` 이 꾸밈뿐이라 직접 본다. 비면 문제 아님 */
export const EFFECT_MAX = 1_000_000;
export function effectProblem(value: string, label = "기대효과"): string | null {
  const text = value.trim();
  if (!text) return null;
  if (text.includes(",")) return `${label}는 쉼표 없이 숫자로 적어 주세요 (예: 1000).`;
  if (!/^-?\d+(\.\d+)?$/.test(text)) return `${label}는 숫자로 적어 주세요 (억원/년, 예: 1.25).`;
  const number = Number(text);
  if (number < 0) return `${label}는 0보다 작을 수 없습니다.`;
  if (number > EFFECT_MAX) return `${label}가 너무 큽니다 (최대 ${EFFECT_MAX.toLocaleString("ko-KR")}) — 단위를 확인하세요.`;
  if (/\.\d{3,}$/.test(text)) return `${label}는 소수 둘째 자리까지 적습니다.`;
  return null;
}

/** 한 줄 제목 칸의 문제 (D14) — 넘었거나 줄바꿈 · 제어문자. 비었는지는 부르는 쪽이 본다 */
export function titleProblem(value: string, label = "제목", limit: number = LIMITS.title): string | null {
  if (hasControlChars(value)) return `${label}에 줄바꿈 · 탭 같은 제어문자를 쓸 수 없습니다.`;
  const { over } = lengthState(value.trim(), limit);
  return over ? `${label}은(는) ${limit}자까지입니다.` : null;
}

/** 남은 글자 안내 (U6) — 상한 가까이(20자 이하 남음)부터 보인다. 멀면 null */
export function lengthHint(value: string, limit: number = LIMITS.title): string | null {
  const { left, over } = lengthState(value.trim(), limit);
  if (over) return `${-left}자 넘었습니다 (${limit}자까지)`;
  return left <= 20 ? `${left}자 남음` : null;
}

/** 과제 번호의 연도 (2026-003 · 팀2026-003 모두) — 없으면 null */
export function idYear(id: string | null | undefined): number | null {
  const hit = /(\d{4})-\d+$/.exec(id ?? "");
  return hit ? Number(hit[1]) : null;
}

/**
 * 명부 밖 사람이 올 수 있는 칸(유관부서 담당자 · 접수 과제리더)의 확인 (TODO 214 D6 · D7).
 * 떠난 사람이면 묻고, 처음 보는 이름이면 —
 *  - `addPerson` 이 있으면 "그대로(명부 밖) 적을까요?" → [취소] 면 "명부에 추가하고 저장할까요?"
 *  - 없으면 "그대로 적을까요?" 만 (다른 팀 사람을 우리 팀 명부에 넣지 않는다)
 * `known` — 명부 말고도 이미 쓰던 이름(유관부서 담당자 등). 계속 저장해도 되면 true.
 */
export async function confirmOutsiders(
  names: string[],
  meta: Pick<Meta, "people" | "people_left">,
  options: { role: string; known?: string[]; addPerson?: (name: string) => Promise<unknown> },
): Promise<boolean> {
  const known = new Set(options.known ?? []);
  const { unknown, departed } = checkPeople(names, meta);
  if (departed.length > 0) {
    const ok = window.confirm(`${departed.join(", ")} — 명부에서 떠난 사람입니다. 그래도 ${options.role}(으)로 적을까요?`);
    if (!ok) return false;
  }
  const fresh = unknown.filter((name) => !known.has(name));
  if (fresh.length === 0) return true;
  const list = fresh.join(", ");
  if (options.addPerson) {
    // [확인] 은 늘 "명부를 건드리지 않는" 쪽 — 다른 부서 사람이 우리 팀 명부에 잘못 들어가지 않게
    const keep = window.confirm(
      `명부에 없는 ${options.role}입니다: ${list}\n\n[확인] 다른 부서(현업) 사람 — 명부에 넣지 않고 그대로 저장 · [취소] 우리 팀원이거나 이름을 고치려면`,
    );
    if (keep) return true;
    const add = window.confirm(`${list} 을(를) 담당자 명부에 추가하고 저장할까요?\n\n[확인] 명부에 추가하고 저장 · [취소] 이름을 고치러 돌아가기`);
    if (!add) return false;
    for (const name of fresh) await options.addPerson(name);
    return true;
  }
  return window.confirm(`처음 적는 ${options.role}입니다: ${list}\n\n[확인] 그대로 저장 · [취소] 이름을 고치러 돌아가기`);
}

/** 서버가 준 `warnings` 를 글 목록으로 — 칸이 없거나 모양이 달라도 빈 목록 */
export function warningList(value: unknown, skip?: RegExp): string[] {
  const list = (value as { warnings?: unknown } | null | undefined)?.warnings;
  if (!Array.isArray(list)) return [];
  return list.filter((item): item is string => typeof item === "string" && item.trim() !== "" && !(skip && skip.test(item)));
}

/** 저장 전에 확인한 같은 이름 알림은 저장 뒤에 다시 띄우지 않는다 (D11) */
export const SAME_TITLE_WARNING = /같은 이름/;
/** 과제 폼 · 승격 창이 저장 **전에** 이미 보인 알림 — 같은 이름 · 효과 · 선행 과제 연도 · 명부 (D2 · D3 · D6 · D11 · D15) */
export const FORM_SHOWN_WARNING = /같은 이름|효과|선행 과제|명부에 없는|떠난 사람/;

// ── TODO 214 · 216 사람 · 면담 · 설정 화면이 쓰는 규칙 ─────────────────────────────

/** 명부의 떠난 사유 — 서버(`settings.LEFT_REASONS`)와 같은 목록 (TODO 214 D8) */
export const LEFT_REASONS = ["전배", "퇴사"] as const;

/**
 * 사람 이름 한 칸의 문제 (TODO 214 D9 · D10 · F6) — 쉼표(여러 명이 한 사람으로 굳는다) · `/ \ ..`(파일 · 폴더 이름에 들어간다) ·
 * 줄바꿈 금지, 40자까지. 비어 있으면 문제 아님(필수 여부는 부르는 쪽이 본다).
 */
export function personNameProblem(name: string | null | undefined): string | null {
  const raw = name ?? "";
  const text = raw.trim();
  if (!text) return null;
  if (hasControlChars(raw)) return "이름에 줄바꿈을 넣을 수 없습니다.";
  if (text.includes(",")) return "이름에 쉼표(,)를 넣을 수 없습니다 — 한 칸에 한 사람입니다.";
  if (/[\\/]/.test(text) || text.includes("..")) return "이름에 / \\ .. 는 쓸 수 없습니다.";
  if (lengthState(text, LIMITS.name).over) return `이름은 ${LIMITS.name}자까지입니다.`;
  return null;
}

/** 팀 코드 규칙 (TODO 214 D16) — 서버 `^[가-힣A-Za-z0-9]{1,20}$`, 숫자만은 안 됨 */
export const PROJECT_CODE_RULE = "한글 · 영문 · 숫자 20자까지, 숫자만은 안 됩니다";

export function projectCodeProblem(code: string | null | undefined): string | null {
  const text = (code ?? "").trim();
  if (!text) return null;
  if (!/^[가-힣A-Za-z0-9]+$/.test(text)) return "팀 코드에는 한글 · 영문 · 숫자만 쓸 수 있습니다 (- & # 공백 같은 기호는 안 됩니다).";
  if (/^\d+$/.test(text)) return "팀 코드는 숫자만으로 지을 수 없습니다 — 일련번호와 구분되지 않습니다.";
  if ([...text].length > 20) return "팀 코드는 20자까지입니다.";
  return null;
}

/**
 * 숫자 칸 하나의 문제 (TODO 214 F12 · U4) — **빈 칸은 0 이 아니다.** `<form>` 밖의 min · max · step 은 꾸밈뿐이라 여기서 실제로 본다.
 * `optional` 이면 빈 칸은 문제 아님.
 */
export function numberProblem(
  value: string,
  rule: { min?: number; max?: number; integer?: boolean; optional?: boolean } = {},
): string | null {
  const text = value.trim();
  if (!text) return rule.optional ? null : "숫자를 적어 주세요.";
  const number = Number(text.replace(/,/g, ""));
  if (!Number.isFinite(number)) return "숫자를 적어 주세요.";
  if (rule.integer && !Number.isInteger(number)) return "소수 없이 적어 주세요.";
  const range =
    rule.min !== undefined && rule.max !== undefined
      ? `${rule.min}~${rule.max} 사이로 적어 주세요.`
      : rule.min !== undefined
        ? `${rule.min} 이상으로 적어 주세요.`
        : `${rule.max} 이하로 적어 주세요.`;
  if (rule.min !== undefined && number < rule.min) return range;
  if (rule.max !== undefined && number > rule.max) return range;
  return null;
}

/**
 * 한 줄에 하나인 목록(분류 · 면담 구분)의 문제 (TODO 214 U6) — 항목 수 · 항목 길이. 빈 줄 · 겹친 값은 서버가 버리므로 세지 않는다.
 * `commas` 면 쉼표도 나눔표로 본다(면담 구분 — 서버가 그렇게 받는다).
 */
export function listProblem(text: string, maxItems: number, maxLength: number, commas = false): string | null {
  const parts = (commas ? text.replace(/,/g, "\n") : text).split("\n").map((part) => part.replace(/\s+/g, " ").trim());
  const items = [...new Set(parts.filter(Boolean))];
  const long = items.find((item) => lengthState(item, maxLength).over);
  if (long) return `"${long.slice(0, 12)}…" — 항목은 ${maxLength}자까지입니다.`;
  if (items.length > maxItems) return `항목은 ${maxItems}개까지입니다 (지금 ${items.length}개).`;
  return null;
}

/** 두 날짜 사이의 날수(양 끝 포함) — 역량 기록의 "시간 ≤ 24 × 날수" (TODO 214 F14) */
export function daySpan(start: string, end: string | null | undefined): number {
  if (!start || !end || end < start) return 1;
  const toUtc = (day: string) => {
    const [y, m, d] = day.split("-").map(Number);
    return Date.UTC(y, (m || 1) - 1, d || 1);
  };
  return Math.round((toUtc(end) - toUtc(start)) / 86400000) + 1;
}

// ── TODO 214 과제 · 기록 · 접수 입력 (F1) — 보고일 ─────────────────────────────
/** 보고 초안 날짜는 오늘 ±1년 (TODO 214 D5) — 다음 주 화요일 보고처럼 미래도 받는다 */
export const REPORT_DRAFT_DAYS = 365;
/** 보고일이 오늘보다 이만큼 넘게 뒤면 확정하지 않는다 (D5) */
export const REPORT_FREEZE_AHEAD_DAYS = 7;
export function reportDateProblem(day: string | null | undefined): string | null {
  const basic = dateProblem(day, "보고일");
  if (basic || !day) return basic;
  const now = today();
  const min = addDays(now, -REPORT_DRAFT_DAYS);
  const max = addDays(now, REPORT_DRAFT_DAYS);
  if (day < min || day > max) return `보고일은 오늘 앞뒤 1년(${min} ~ ${max}) 안에서 고릅니다.`;
  return null;
}
