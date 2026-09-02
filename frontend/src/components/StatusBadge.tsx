import type { Meta } from "../types";

export default function StatusBadge({ status, meta }: { status: string; meta: Meta }) {
  const info = meta.statuses.find((item) => item.key === status);
  return <span className={`status status-${status}`}>{info?.label ?? status}</span>;
}

/** 과제 속성(성격). 상태와 구분되도록 다른 모양으로 보여 준다. */
export function TypeBadge({ type, meta }: { type: string | null; meta: Meta }) {
  if (!type) return <span className="muted">—</span>;
  const info = meta.types.find((item) => item.key === type);
  return <span className={`type-badge type-${type}`}>{info?.label ?? type}</span>;
}
