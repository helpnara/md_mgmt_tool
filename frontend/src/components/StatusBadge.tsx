import type { Meta, Project } from "../types";

export default function StatusBadge({ status, meta }: { status: string; meta: Meta }) {
  const info = meta.statuses.find((item) => item.key === status);
  return <span className={`status status-${status}`}>{info?.label ?? status}</span>;
}

/** 목록이 보여 줄 상태 — 연도를 골랐으면 그 해의 상태, 아니면 지금 상태 (TODO 184). */
export function shownStatus(project: Project): string {
  return project.year_status || project.status;
}

/**
 * 과제목록 · 보드의 상태 딱지 (TODO 184).
 *
 * 연도를 고르면 **그 해의 상태**를 보인다 — 2025~2026 과제를 2025 에서 보면 진행중. 홈 · 대시보드가 그렇게 세고
 * [진행중] 거르기도 그렇게 거르므로, 딱지만 지금 상태(완료)를 말하면 숫자를 눌러 나온 줄이 숫자와 어긋난다.
 * 지금 상태가 다르면 옆에 작게 적어 "왜 진행중이지?" 가 그 자리에서 풀리게 한다.
 */
export function YearStatusBadge({ project, meta, year }: { project: Project; meta: Meta; year?: string }) {
  const shown = shownStatus(project);
  if (shown === project.status) return <StatusBadge status={shown} meta={meta} />;
  const now = meta.statuses.find((item) => item.key === project.status)?.label ?? project.status;
  const when = project.status === "done" && project.completed_at ? `${project.completed_at.slice(0, 10)} ` : "";
  const label = meta.statuses.find((item) => item.key === shown)?.label ?? shown;
  return (
    <span
      className="year-status"
      title={`지금은 ${now}${when ? `(${when.trim()})` : ""} — ${year ? `${year}년` : "그 해"} 말에는 아직 ${label}이었습니다`}
    >
      <StatusBadge status={shown} meta={meta} />
      <span className="year-status-now">
        → {when}
        {now}
      </span>
    </span>
  );
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
