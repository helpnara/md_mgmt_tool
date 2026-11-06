import { useLayoutEffect, useRef, useState } from "react";

/**
 * [담당과 역할] 회고 칸의 긴 글 (TODO 240) — 쓰기(자라는 칸 · 글자 수 · 붙여넣기 정리)와 읽기(목록 · 접기).
 *
 * 생성형 AI 로 요약한 200자 남짓을 붙여넣으면 좁은 두 칸 · 고정 높이 · 코드용 글꼴이 겹쳐 읽기 어려웠다.
 */

export const RETRO_MAX = 1000;
const MIN_ROWS = 3;
const MAX_ROWS = 15;

/** 공백 포함 글자 수 — 서버(파이썬 len)와 같게 코드포인트로 센다 */
export function charCount(text: string): number {
  return [...text].length;
}

/**
 * AI 답의 마크다운 기호를 걷는다 (⑤) — `**굵게**` · `__굵게__` · `### 제목` · `> 인용`, 글머리표(`*` `•` `●` `▪` `◦` `‣` `-`)는 `- ` 로,
 * 세 줄 이상의 빈 줄은 하나로. 번호(1. 2.)는 그대로 둔다. 바뀐 것이 없으면 그대로 돌려준다.
 */
export function cleanPasted(text: string): string {
  const lines = text.replace(/\r\n?/g, "\n").split("\n").map((line) => {
    let out = line.replace(/\*\*(.+?)\*\*/g, "$1").replace(/__(.+?)__/g, "$1");
    out = out.replace(/^\s{0,3}#{1,6}\s+/, "");
    out = out.replace(/^\s*>\s?/, "");
    out = out.replace(/^(\s*)[*•●▪◦‣\-–]\s+/, (_match, indent: string) => `${indent.length >= 2 ? "  " : ""}- `);
    return out.replace(/\s+$/, "");
  });
  return lines.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

/** 글에 맞춰 자라는 글상자 + 글자 수 + 붙여넣기 정리(되돌리기) */
export function RetroField({
  label,
  value,
  placeholder,
  onChange,
}: {
  label: string;
  value: string;
  placeholder?: string;
  onChange: (next: string) => void;
}) {
  const box = useRef<HTMLTextAreaElement>(null);
  // 정리하기 전의 글 — [되돌리기] 가 이것으로 돌아간다
  const [undo, setUndo] = useState<string | null>(null);

  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const style = getComputedStyle(el);
    const line = parseFloat(style.lineHeight) || 22;
    const padding = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
    const border = parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth);
    el.style.height = "auto";
    // scrollHeight 는 안쪽 여백을 품는다 — 테두리만 더한다. 3줄보다 작지도, 15줄보다 크지도 않게(넘치면 안에서 굴린다)
    const wanted = Math.min(Math.max(el.scrollHeight, line * MIN_ROWS + padding), line * MAX_ROWS + padding);
    el.style.height = `${Math.ceil(wanted + border)}px`;
  }, [value]);

  const count = charCount(value);
  return (
    <label className="retro-field">
      {label}
      <textarea
        ref={box}
        rows={MIN_ROWS}
        maxLength={RETRO_MAX}
        value={value}
        placeholder={placeholder}
        aria-label={label}
        onChange={(event) => {
          setUndo(null);
          onChange(event.target.value);
        }}
        onPaste={(event) => {
          const raw = event.clipboardData.getData("text/plain");
          const cleaned = cleanPasted(raw);
          if (!raw || cleaned === raw.trim() || cleaned === raw) return;
          event.preventDefault();
          const el = event.currentTarget;
          const start = el.selectionStart ?? value.length;
          const end = el.selectionEnd ?? value.length;
          const before = value.slice(0, start);
          const after = value.slice(end);
          setUndo(before + raw + after);
          onChange(before + cleaned + after);
        }}
      />
      <span className="retro-field-foot">
        {undo !== null && (
          <span className="retro-cleaned">
            붙여넣은 글의 기호(**, ###, 글머리표)를 정리했습니다 ·{" "}
            <button
              type="button"
              className="linkish"
              onClick={() => {
                onChange(undo);
                setUndo(null);
              }}
            >
              되돌리기
            </button>
          </span>
        )}
        <span className={count > RETRO_MAX ? "retro-count over" : "retro-count"}>
          공백 포함 {count.toLocaleString()}자 / {RETRO_MAX.toLocaleString()}
        </span>
      </span>
    </label>
  );
}

/** 저장한 글 — 줄바꿈 · `- ` 글머리표는 목록으로(④). `clamp` 면 5줄 넘을 때 접고 [더 보기] */
export function RetroText({ text, clamp = false }: { text: string; clamp?: boolean }) {
  const body = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [overflow, setOverflow] = useState(false);

  useLayoutEffect(() => {
    const el = body.current;
    if (!el || !clamp) return;
    setOverflow(el.scrollHeight > el.clientHeight + 2);
  }, [text, clamp]);

  // 줄을 묶는다 — 연이은 `- ` 줄은 한 목록, 나머지는 문단
  const blocks: { kind: "p" | "ul"; lines: string[] }[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    if (!line.trim()) continue;
    const item = line.match(/^\s*-\s+(.*)$/);
    const last = blocks[blocks.length - 1];
    if (item) {
      if (last?.kind === "ul") last.lines.push(item[1]);
      else blocks.push({ kind: "ul", lines: [item[1]] });
    } else {
      blocks.push({ kind: "p", lines: [line] });
    }
  }

  return (
    <div className="retro-text">
      <div ref={body} className={clamp && !open ? `retro-text-body clamped${overflow ? " faded" : ""}` : "retro-text-body"}>
        {blocks.map((block, index) =>
          block.kind === "ul" ? (
            <ul key={index}>
              {block.lines.map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ul>
          ) : (
            <p key={index}>{block.lines[0]}</p>
          ),
        )}
      </div>
      {clamp && (overflow || open) && (
        <button type="button" className="linkish retro-more" onClick={() => setOpen((value) => !value)}>
          {open ? "접기 ▴" : "더 보기 ▾"}
        </button>
      )}
    </div>
  );
}
