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
