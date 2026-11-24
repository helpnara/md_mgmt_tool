import { leftOf } from "../people";

/** 323 — 떠난 사람(전배 · 퇴사) 띠지. 지금 사람이면 아무것도 그리지 않는다 */
export default function LeftTag({ name, className = "" }: { name: string | null | undefined; className?: string }) {
  const label = leftOf(name);
  if (!label) return null;
  return (
    <span className={`tag left-tag${className ? ` ${className}` : ""}`} title={`명부에서 ${label === "떠남" ? "떠난" : `${label}한`} 사람입니다`}>
      {label}
    </span>
  );
}
