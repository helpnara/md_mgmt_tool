import type { Meta } from "../types";

export default function StatusBadge({ status, meta }: { status: string; meta: Meta }) {
  const info = meta.statuses.find((item) => item.key === status);
  return <span className={`status status-${status}`}>{info?.label ?? status}</span>;
}
