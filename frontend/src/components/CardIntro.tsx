import { useLayoutEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { remember, remembered } from "./Explain";

/**
 * 설정 카드 머리의 설명 글 (TODO 249 ③).
 *
 * 설정 카드는 설명이 한 줄 ~ 여섯 줄이라, 같은 일을 하는 카드끼리도 높이가 들쭉날쭉했다. **두 줄까지만 보이고** 넘치면
 * [설명 ▾] 로 편다 — 232 ④ 의 `Explain` 과 같은 단추 · 같은 기억(펼친 것은 이 브라우저가 기억한다, 카드마다 따로).
 * 글을 자르지 않고 **보이는 높이만** 줄이므로 찾기(Ctrl+F) · 화면 낭독기에는 다 닿는다. 두 줄 안에 들면 단추도 없다.
 */
export default function CardIntro({ id, children }: { id: string; children: ReactNode }) {
  const ref = useRef<HTMLParagraphElement>(null);
  const [open, setOpen] = useState(() => remembered(`card:${id}`));
  const [long, setLong] = useState(false);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || open) return;
    const check = () => setLong(el.scrollHeight > el.clientHeight + 2);
    check();
    if (typeof ResizeObserver === "undefined") return;
    const watch = new ResizeObserver(check);
    watch.observe(el);
    return () => watch.disconnect();
  }, [open]);
  return (
    <div className="card-intro" data-intro={id}>
      <p ref={ref} className={open ? "hint card-intro-text" : "hint card-intro-text clamped"}>
        {children}
      </p>
      {(long || open) && (
        <button
          type="button"
          className="explain-toggle"
          aria-expanded={open}
          onClick={() => {
            setOpen(!open);
            remember(`card:${id}`, !open);
          }}
        >
          {open ? "설명 접기 ▴" : "설명 ▾"}
        </button>
      )}
    </div>
  );
}
