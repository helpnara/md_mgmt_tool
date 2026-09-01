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

export function dueLabel(due: string | null | undefined): { text: string; tone: string } | null {
  const days = daysUntil(due);
  if (days === null) return null;
  if (days < 0) return { text: `D+${-days} 초과`, tone: "danger" };
  if (days === 0) return { text: "D-day", tone: "danger" };
  if (days <= 7) return { text: `D-${days}`, tone: "warn" };
  return { text: `D-${days}`, tone: "muted" };
}

export function todayIso(): string {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 10);
}
