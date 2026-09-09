import type { Meta } from "../types";

export default function StatusBadge({ status, meta }: { status: string; meta: Meta }) {
  const info = meta.statuses.find((item) => item.key === status);
  return <span className={`status status-${status}`}>{info?.label ?? status}</span>;
}

/**
 * 처음부터 있던 속성들 — styles.css 에 제 색이 하나씩 있다.
 * 여기 없는 속성(설정에서 더한 것)은 아래 팔레트에서 색을 받는다 (TODO 100).
 */
const BUILT_IN_TYPES = new Set([
  "smart", "rnd", "investment", "plan_report", "national", "maintenance",
]);
/** 더한 속성에 줄 색 수 (styles.css 의 .type-c0 … .type-c4). */
const TYPE_PALETTE = 5;

/**
 * 딱지에 붙일 색 (TODO 100).
 *
 * **열쇠로 정한다** — 목록에서 순서를 바꿨다고 색까지 바뀌면, 어제 파란색이던 속성이
 * 오늘 빨간색이 되어 눈이 기억한 것을 못 쓴다.
 */
export function typeClass(key: string): string {
  if (BUILT_IN_TYPES.has(key)) return `type-${key}`;
  let hash = 0;
  for (const ch of key) hash = (hash * 31 + (ch.codePointAt(0) ?? 0)) % 1000003;
  return `type-c${hash % TYPE_PALETTE}`;
}

/** 과제 속성(성격). 상태와 구분되도록 다른 모양으로 보여 준다. */
export function TypeBadge({ type, meta }: { type: string | null; meta: Meta }) {
  if (!type) return <span className="muted">—</span>;
  const info = meta.types.find((item) => item.key === type);
  return <span className={`type-badge ${typeClass(type)}`}>{info?.label ?? type}</span>;
}
