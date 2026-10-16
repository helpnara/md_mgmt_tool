import { useCallback, useEffect, useRef } from "react";
import { useUnsaved } from "./unsaved";

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  return value.slice(0, 10);
}

/** 마감일까지 남은 일수. 지난 경우 음수. */
export function daysUntil(due: string | null | undefined): number | null {
  if (!due) return null;
  const target = new Date(`${due.slice(0, 10)}T00:00:00`);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((target.getTime() - today.getTime()) / 86_400_000);
}

/** 끝난 과제 — 마감이 지났다고 경고할 이유가 없다. */
const FINISHED_STATUSES = new Set(["done", "dropped"]);

/**
 * 마감 표시.
 * 빨간 초과 표시는 "기한이 지났는데 아직 못 끝냈다"는 경고이므로,
 * 이미 끝난 과제(완료·중단)에는 띄우지 않는다. 그래야 진짜 늦은 과제가 눈에 띈다.
 * 보류는 멈춰 있을 뿐 끝난 것이 아니라서 그대로 경고한다.
 */
export function dueLabel(
  due: string | null | undefined,
  status?: string,
): { text: string; tone: string } | null {
  const days = daysUntil(due);
  if (days === null) return null;
  if (status && FINISHED_STATUSES.has(status)) return null;
  if (days < 0) return { text: `D+${-days} 초과`, tone: "danger" };
  if (days === 0) return { text: "D-day", tone: "danger" };
  if (days <= 7) return { text: `D-${days}`, tone: "warn" };
  return { text: `D-${days}`, tone: "muted" };
}

/** '2026-09-08T17:40:00+09:00' → '2026-09-08 17:40' */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const [date, time = ""] = value.split("T");
  return time ? `${date} ${time.slice(0, 5)}` : date;
}

/** 시작·마감이 비어 있을 때 "— ~ —" 로 보이지 않게 한다. */
export function periodText(start: string | null | undefined, due: string | null | undefined): string {
  if (start && due) return `기간 ${formatDate(start)} ~ ${formatDate(due)}`;
  if (start) return `시작 ${formatDate(start)}`;
  if (due) return `마감 ${formatDate(due)}`;
  return "기간 미정";
}

export function todayIso(): string {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 10);
}

/**
 * 방금 연 편집기를 화면 안으로 데려온다.
 *
 * 편집기를 열면 2단이 1단으로 바뀌면서 화면 배치가 통째로 달라진다.
 * 스크롤 위치는 그대로 남으므로, 목록 아래쪽 항목을 고치려고 [수정]을 누르면
 * 편집기가 화면 밖으로 밀려 다시 찾아 내려가야 한다. 그 수고를 없앤다.
 *
 * 배치가 다시 그려진 뒤에 움직여야 엉뚱한 위치로 가지 않으므로 한 프레임 기다린다.
 * 상단 고정 헤더에 가리지 않는 것은 CSS 의 scroll-margin-top 이 맡는다.
 *
 * 편집을 닫고 원래 자리로 되돌아갈 때는 block="center" 를 쓴다. 닫으면서 목록을
 * 다시 읽어 오므로 높이가 조금 달라지는데, 가운데로 두면 그 정도 어긋남은 묻힌다.
 */
export function scrollEditorIntoView(
  el: HTMLElement | null,
  block: ScrollLogicalPosition = "start",
): void {
  if (!el) return;
  requestAnimationFrame(() => {
    el.scrollIntoView({ behavior: "smooth", block });
  });
}

/** 과제 효과 금액의 단위. 사내에서 쓰는 표기를 그대로 따른다 (backend/app/config.py 와 같은 값). */
export const EFFECT_UNIT = "억원/년";

/**
 * 효과 금액 한 줄 표기.
 *
 * 기대효과와 실증효과는 시점이 다른 별개의 값이다. 둘 다 있으면 `1.2 → 1.4` 로 나란히
 * 보여 "예상은 얼마였고 실제로 얼마였나"가 한눈에 들어오게 한다.
 * 아무것도 안 적힌 과제는 null 을 돌려주고, 화면에서는 아예 그리지 않는다 —
 * "0"으로 적으면 실제로 효과가 0인 과제와 구분되지 않는다.
 */
/**
 * 효과 금액 한 숫자를 글자로 — **어디서나 소수 첫째 자리, 끝의 0 도 적는다** (TODO 156).
 *
 * `3` → `3.0`, `1.2` → `1.2`, `1.25` → `1.3`.
 * 전에는 둘째 자리까지 적고 끝의 0 을 뗐다(`3` · `3.5` · `1.25`) — 한 표 안에서 줄마다 자릿수가 달라
 * 눈으로 견주기 어려웠다. **입력·저장은 여전히 둘째 자리**(1억 2,500만 원, TODO 76)이고 보일 때만 줄인다.
 * 합계는 원래 값으로 더한 뒤 여기서 한 번 반올림한다 — 반올림한 값끼리 더하면 줄의 합과 어긋난다.
 *
 * `toFixed(1)` 을 그냥 쓰면 `1.15` 가 `1.1` 이 된다(2진수로 1.1499…). 저장 값은 둘째 자리까지라
 * 아주 작은 값을 더해 반올림하면 서버(`round`)·엑셀과 같은 사사오입이 된다.
 */
export function effectNumber(value: number): string {
  const tenths = Math.round(value * 10 + (value >= 0 ? 1e-9 : -1e-9));
  return (tenths / 10).toFixed(1);
}

/**
 * 표 안에서 값이 없거나 0 일 때 쓰는 표시 (TODO 158).
 * 표 밖(요약 카드·상세 화면)의 빈 값은 그대로 `—` 다 — 카드의 `0건` 은 "없다" 를 말하는 값이다.
 */
export const DASH = "-";

/** 표 칸의 수. 0 이면 `-` (TODO 158). */
export function cellCount(value: number | null | undefined, suffix = ""): string {
  return value ? `${value}${suffix}` : DASH;
}

/** 표 칸의 효과 금액. 없거나 소수 첫째 자리에서 0 이면 `-` (TODO 156 · 158). */
export function cellEffect(value: number | null | undefined): string {
  if (value == null) return DASH;
  const text = effectNumber(value);
  return Number(text) === 0 ? DASH : text;
}

/** 표의 합계 줄 (TODO 157) — 걸러져 보이는 줄을 **원래 값으로** 더한다. 빈 값은 0 으로 본다. */
export function sumBy<T>(rows: T[], pick: (row: T) => number | null | undefined): number {
  return rows.reduce((total, row) => total + (pick(row) ?? 0), 0);
}

export function effectText(
  expected: number | null | undefined,
  verified: number | null | undefined,
): { text: string; verified: boolean } | null {
  const num = effectNumber;
  if (expected != null && verified != null) {
    return { text: `${num(expected)} → ${num(verified)}`, verified: true };
  }
  if (verified != null) return { text: num(verified), verified: true };
  if (expected != null) return { text: num(expected), verified: false };
  return null;
}

/** Esc 로 닫히는 창 (TODO 169) — 승격 창 · 엑셀 [내용 보기] 가 Esc 에 안 닫혔다(사전점검 창만 닫혔다). */
export function useEscape(onEscape: () => void, active = true): void {
  useEffect(() => {
    if (!active) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onEscape();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onEscape, active]);
}

/**
 * 불러온 뒤 고치는 칸(설정 카드들)의 "저장 안 한 것" (TODO 211 ②).
 *
 * `useFormUnsaved` 는 **처음 그린 값**과 견준다 — 설정 카드는 빈 값으로 서고 서버 값이 뒤에 오므로, 그대로 쓰면
 * 불러오자마자 "고쳤다" 가 된다. 여기서는 **마지막으로 불러오거나 저장한 값**(saved)과 견준다.
 * saved 가 아직 없으면(불러오는 중 · 실패) 묻지 않는다. 고쳤는가를 돌려준다.
 */
export function useEditedUnsaved(key: string, current: unknown, saved: unknown, busy = false): boolean {
  const edited = saved !== undefined && saved !== null && JSON.stringify(current) !== JSON.stringify(saved);
  useUnsaved(key, edited && !busy);
  return edited;
}

/** 입력 양식의 [취소] · [닫기] · Esc — 고친 것이 있으면 한 번 묻는다 (TODO 211 ①, 편집기와 같은 문구) */
export const DISCARD_MESSAGE = "저장하지 않은 내용을 버릴까요?";

export function confirmDiscard(dirty: boolean): boolean {
  return !dirty || window.confirm(DISCARD_MESSAGE);
}

/**
 * 날짜 칸 검사 (TODO 212) — 서버 422 를 받기 전에 화면에서.
 * 시작이 끝보다 늦으면 문구를, 아니면 null. 한쪽이라도 비면 따지지 않는다.
 */
export function dateOrderProblem(start: string | null | undefined, end: string | null | undefined, startLabel: string, endLabel: string): string | null {
  if (!start || !end) return null;
  return start > end ? `${startLabel}(${start})이 ${endLabel}(${end})보다 늦습니다.` : null;
}

/**
 * 같은 조건으로 다시 부를 때 **늦게 온 옛 응답**을 버린다 (TODO 210 ①).
 * `const take = useLatest();` → 부를 때 `const mine = take();` → 응답에서 `if (!mine()) return;`
 */
export function useLatest(): () => () => boolean {
  const counter = useRef(0);
  useEffect(
    () => () => {
      counter.current += 1; // 떠난 화면에 늦게 온 응답도 버린다
    },
    [],
  );
  return useCallback(() => {
    counter.current += 1;
    const ticket = counter.current;
    return () => ticket === counter.current;
  }, []);
}

/**
 * 입력 양식의 Enter 규칙 (TODO 211 ⑥) — **한 줄 칸에서 누른 Enter** 인가.
 * 여러 줄 칸(textarea) · 단추 · 선택 상자 · 체크 · 한글 조합 중(IME) · Shift/Ctrl/Alt 와 함께면 아니다.
 * 목록에 줄을 더하는 칸(하기로 한 것 · 선행 과제)은 `data-enter="add"` 로 표시해 따로 다룬다.
 */
export function isPlainEnter(event: React.KeyboardEvent): boolean {
  if (event.key !== "Enter" || event.defaultPrevented) return false;
  if (event.shiftKey || event.ctrlKey || event.altKey || event.metaKey) return false;
  if ((event.nativeEvent as KeyboardEvent).isComposing || event.keyCode === 229) return false;
  const target = event.target as HTMLElement;
  if (!(target instanceof HTMLInputElement)) return false;
  if (target.dataset.enter === "add") return false;
  return !["checkbox", "radio", "button", "submit", "file", "reset"].includes(target.type);
}

/**
 * 줄을 눌러 여는 편의 — 단 **제목 링크 · 가운데 클릭 · Ctrl/Shift/⌘ 클릭은 브라우저에 맡긴다** (TODO 210 ⑤).
 * 새 탭으로 열려는 클릭을 가로채 지금 탭을 옮기면 안 된다. 글자를 끌어 고르는 중이어도 옮기지 않는다.
 */
export function openRowClick(event: React.MouseEvent, href: string): void {
  if (event.defaultPrevented || event.button !== 0) return;
  if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
  if ((event.target as HTMLElement).closest("a, button, input, select, textarea, label")) return;
  if (window.getSelection()?.toString()) return;
  window.location.hash = href;
}
