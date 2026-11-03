import { useRef } from "react";
import type { ReactNode } from "react";

export type ViewTab = { key: string; label: ReactNode; title?: string };

/**
 * 한 화면 안의 탭 (TODO 232).
 *
 * 홈은 [할 일] · [팀 현황], 팀원역량은 [사람별] · [기록] · [면담]. 고른 탭은 **주소에 남긴다** — 표의 숫자를 눌러
 * 목록에 갔다가 "← 홈" 으로 돌아오면 보던 탭이 그대로다(48 의 뒤로 가기 규칙). 탭은 화면을 나누는 것이지
 * 조건이 아니라서 숫자는 바뀌지 않는다.
 *
 * 키보드 — ← → 로 옆 탭, Home · End 로 처음 · 끝 (WAI-ARIA tabs 의 자동 선택 방식).
 */
export default function ViewTabs({
  tabs,
  value,
  onChange,
  label,
  className = "",
}: {
  tabs: ViewTab[];
  value: string;
  onChange: (key: string) => void;
  /** 탭 묶음의 이름 — 화면 낭독기가 읽는다 */
  label: string;
  className?: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const index = Math.max(0, tabs.findIndex((tab) => tab.key === value));
  const move = (next: number) => {
    const target = (next + tabs.length) % tabs.length;
    onChange(tabs[target].key);
    refs.current[target]?.focus();
  };
  return (
    <div className={`view-tabs ${className}`.trim()} role="tablist" aria-label={label}>
      {tabs.map((tab, position) => {
        const on = position === index;
        return (
          <button
            key={tab.key || "_"}
            ref={(element) => {
              refs.current[position] = element;
            }}
            type="button"
            role="tab"
            aria-selected={on}
            tabIndex={on ? 0 : -1}
            className={on ? "view-tab on" : "view-tab"}
            title={tab.title}
            data-tab={tab.key || "default"}
            onClick={() => onChange(tab.key)}
            onKeyDown={(event) => {
              if (event.key === "ArrowRight") move(position + 1);
              else if (event.key === "ArrowLeft") move(position - 1);
              else if (event.key === "Home") move(0);
              else if (event.key === "End") move(tabs.length - 1);
              else return;
              event.preventDefault();
            }}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
