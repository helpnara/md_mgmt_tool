import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

/**
 * 아이콘 칸이 붙은 카드 제목 (TODO 252).
 *
 * 예시 녹화(Nimbus 화면)의 카드는 제목 곁에 연파랑 둥근 사각 안 파란 선 아이콘을 둔다. 녹화처럼 제목 *위* 에 두면 카드마다
 * 50px 씩 길어져 249 의 정돈과 어긋나므로 **왼쪽** 에 둔다. 아이콘은 꾸밈이라 화면 낭독기에는 숨긴다 — 제목 글자는 그대로 h2 다.
 * 아이콘 묶음은 lucide-react(ISC). 쓰는 것만 빌드에 들어간다.
 */
export default function IconTitle({ icon: Icon, children, className = "" }: { icon: LucideIcon; children: ReactNode; className?: string }) {
  return (
    <h2 className={`icon-title ${className}`.trim()}>
      <span className="icon-tile" aria-hidden="true">
        <Icon size={20} strokeWidth={2} />
      </span>
      <span className="icon-title-text">{children}</span>
    </h2>
  );
}
