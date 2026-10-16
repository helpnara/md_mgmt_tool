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
