import { type RefObject, useEffect, useState } from "react";
import {
  type Active, type Edit, type LineKind, type Wrap,
  activeAt, enterInList, insertLink, insertTable, repairLineBreaks, shiftLines, toggleLine, toggleWrap,
} from "../mdEdit";

/**
 * 마크다운 도구 띠 (TODO 321 1단계) — 글 편집 칸(과제 개요 · 진행일지 · 보고 초안 · 접수 요청 내용 · 검토 기록) 위.
 *
 * 규칙은 `mdEdit.ts`(순수 함수)가 정하고, 여기서는 그 결과를 **`insertText` 한 번**으로 넣는다 —
 * Ctrl+Z 한 번에 되돌아가고, 칸의 onChange(임시 보관 · 고치는 중 알림 · 떠날 때 묻기)가 그대로 돈다.
 *
 * 단축키 — Ctrl+B 굵게 · Ctrl+I 기울임 · Ctrl+K 링크 · Tab / Shift+Tab 들여쓰기 · 목록에서 Enter 는 다음 항목.
 * 한글을 조합하는 중(`isComposing`)에는 아무것도 가로채지 않는다.
 */
export default function MdToolbar({ target }: { target: RefObject<HTMLTextAreaElement | null> }) {
  const [active, setActive] = useState<Active>({ wraps: [], line: null });

  const apply = (edit: Edit | null) => {
    const area = target.current;
    if (!area || !edit) return;
    area.focus();
    area.setSelectionRange(edit.from, edit.to);
    // 되돌리기에 한 번으로 남는 길 — 안 되는 브라우저면 값을 바꾸고 input 을 알린다
    const ok = edit.insert === "" ? document.execCommand("delete") || document.execCommand("insertText", false, "")
      : document.execCommand("insertText", false, edit.insert);
    if (!ok) {
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
      setter?.call(area, area.value.slice(0, edit.from) + edit.insert + area.value.slice(edit.to));
      area.dispatchEvent(new Event("input", { bubbles: true }));
    }
    area.setSelectionRange(edit.selStart, edit.selEnd);
    setActive(activeAt(area.value, area.selectionStart));
  };

  const run = (make: (text: string, start: number, end: number) => Edit | null) => {
    const area = target.current;
    if (!area) return;
    apply(make(area.value, area.selectionStart, area.selectionEnd));
  };
  const wrap = (mark: Wrap) => run((t, s, e) => toggleWrap(t, s, e, mark));
  const line = (kind: LineKind) => run((t, s, e) => toggleLine(t, s, e, kind));

  useEffect(() => {
    const area = target.current;
    if (!area) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.isComposing || event.keyCode === 229) return;   // 한글 조합 중
      const mod = event.ctrlKey || event.metaKey;
      const key = event.key.toLowerCase();
      if (mod && !event.shiftKey && !event.altKey && (key === "b" || key === "i" || key === "k")) {
        event.preventDefault();
        if (key === "b") wrap("**");
        else if (key === "i") wrap("*");
        else run((t, s, e) => insertLink(t, s, e));
        return;
      }
      if (event.key === "Tab" && !mod && !event.altKey) {
        event.preventDefault();
        run((t, s, e) => shiftLines(t, s, e, !event.shiftKey));
        return;
      }
      if (event.key === "Enter" && !mod && !event.shiftKey && !event.altKey && area.selectionStart === area.selectionEnd) {
        const edit = enterInList(area.value, area.selectionStart);
        if (edit) {
          event.preventDefault();
          apply(edit);
        }
      }
    };
    const onMove = () => setActive(activeAt(area.value, area.selectionStart));
    area.addEventListener("keydown", onKey);
    area.addEventListener("keyup", onMove);
    area.addEventListener("click", onMove);
    return () => {
      area.removeEventListener("keydown", onKey);
      area.removeEventListener("keyup", onMove);
      area.removeEventListener("click", onMove);
    };
    // 칸은 편집기와 함께 한 번 선다 — 규칙 함수들은 늘 같은 것을 부른다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);

  const btn = (label: string, title: string, on: boolean, onClick: () => void, cls = "") => (
    <button type="button" className={`md-btn${on ? " on" : ""}${cls ? ` ${cls}` : ""}`} title={title} aria-label={title} aria-pressed={on}
      // 누를 때 칸의 고른 범위를 잃지 않게
      onMouseDown={(event) => event.preventDefault()} onClick={onClick}>
      {label}
    </button>
  );

  return (
    <div className="md-toolbar" role="toolbar" aria-label="마크다운 서식" data-testid="md-toolbar">
      {btn("B", "굵게 (Ctrl+B)", active.wraps.includes("**"), () => wrap("**"), "md-bold")}
      {btn("I", "기울임 (Ctrl+I)", active.wraps.includes("*"), () => wrap("*"), "md-italic")}
      {btn("S", "취소선", active.wraps.includes("~~"), () => wrap("~~"), "md-strike")}
      {btn("</>", "코드", active.wraps.includes("`"), () => wrap("`"))}
      <span className="md-sep" aria-hidden />
      {btn("제목1", "제목 1 (#)", active.line === "h1", () => line("h1"))}
      {btn("제목2", "제목 2 (##)", active.line === "h2", () => line("h2"))}
      {btn("제목3", "제목 3 (###)", active.line === "h3", () => line("h3"))}
      <span className="md-sep" aria-hidden />
      {btn("•", "글머리 목록 (-)", active.line === "bullet", () => line("bullet"))}
      {btn("1.", "번호 목록 (1.)", active.line === "number", () => line("number"))}
      {btn("☐", "할 일 목록 (- [ ])", active.line === "task", () => line("task"))}
      {btn("❝", "인용 (>)", active.line === "quote", () => line("quote"))}
      {btn("⇤", "내어쓰기 (Shift+Tab)", false, () => run((t, s, e) => shiftLines(t, s, e, false)))}
      {btn("⇥", "들여쓰기 (Tab)", false, () => run((t, s, e) => shiftLines(t, s, e, true)))}
      <span className="md-sep" aria-hidden />
      {btn("표", "표 넣기 (3 × 3)", false, () => run((t, s) => insertTable(t, s)))}
      {btn("링크", "링크 (Ctrl+K)", false, () => run((t, s, e) => insertLink(t, s, e)))}
      {btn("줄바꿈 고치기", "웹 · 메모에서 붙여넣은 글의 보이지 않는 줄바꿈 · 빈칸을 고칩니다", false, () => run((t) => {
        const fixed = repairLineBreaks(t);
        return fixed === null ? null : { from: 0, to: t.length, insert: fixed, selStart: 0, selEnd: 0 };
      }), "md-repair")}
    </div>
  );
}
