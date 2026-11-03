import { useState } from "react";
import type { ReactNode } from "react";

const PREFIX = "explain-open:";

function remembered(id: string): boolean {
  try {
    return window.localStorage.getItem(PREFIX + id) === "1";
  } catch {
    return false;
  }
}

function remember(id: string, open: boolean): void {
  try {
    if (open) window.localStorage.setItem(PREFIX + id, "1");
    else window.localStorage.removeItem(PREFIX + id);
  } catch {
    /* 저장이 막힌 창(사생활 보호 등) — 이번에만 펼친다 */
  }
}

/**
 * 표 · 숫자 아래의 설명 글 (TODO 232 ④).
 *
 * 숫자를 잘못 읽지 않게 붙인 설명이 화면 글자의 3분의 1이 되었다(홈 34% · 팀원역량 29%). 처음 한 번은 꼭 필요하지만
 * 매일 보는 사람은 같은 글을 매번 지나가야 한다. 그래서 **첫 문장(`lead`)만 늘 보이고** 나머지는 [설명 ▾] 로 접는다.
 * 펼친 것은 이 브라우저가 기억한다(설명마다 따로). 잘못 읽으면 숫자가 틀리게 보고되는 경고(담당 중복 · 합이 다름)는
 * `lead` 에 둔다 — 접히는 것은 *까닭* 이지 *경고* 가 아니다.
 *
 * 접힌 글도 문서에는 남는다(`hidden`) — 화면 낭독기 · 찾기(Ctrl+F)는 펼친 뒤에 닿는다.
 */
export default function Explain({
  id,
  lead,
  children,
  className = "",
}: {
  /** 펼침을 기억할 열쇠 — 화면 · 자리마다 다르게 */
  id: string;
  lead: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  const [open, setOpen] = useState(() => remembered(id));
  const hasMore = children !== undefined && children !== null && children !== false;
  return (
    <p className={`hint explain ${className}`.trim()} data-explain={id}>
      {lead}
      {hasMore && (
        <>
          <span className="explain-more" hidden={!open}>
            {" "}
            {children}
          </span>{" "}
          <button
            type="button"
            className="explain-toggle"
            aria-expanded={open}
            onClick={() => {
              setOpen(!open);
              remember(id, !open);
            }}
          >
            {open ? "설명 접기 ▴" : "설명 ▾"}
          </button>
        </>
      )}
    </p>
  );
}
