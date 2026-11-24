import { type RefObject, useEffect, useLayoutEffect, useRef, useState } from "react";
import { api } from "../api";
import {
  type Active, type Edit, type LineKind, type Wrap,
  activeAt, enterInList, insertLink, insertTable, linkProject, linkQuery, repairLineBreaks, shiftLines, toggleLine, toggleWrap,
} from "../mdEdit";

// 321 2단계 — `>>` 과제 연결의 후보(과제 전체를 한 번 받아 둔다 — 치는 동안 서버를 부르지 않게)
type Pick = { id: string; title: string; status: string };
let projectCache: Promise<Pick[]> | null = null;
function projectsOnce(): Promise<Pick[]> {
  if (!projectCache) {
    projectCache = api.listProjects({ year: "all" })
      .then((rows) => rows.map((p) => ({ id: p.id, title: p.title, status: p.status })))
      .catch(() => { projectCache = null; return []; });
  }
  return projectCache;
}

/**
 * 322 — 칸 안 커서 자리(칸 왼쪽 위 기준 px). 칸과 똑같이 꾸민 보이지 않는 복제 칸에 커서 앞 글을 넣고
 * 끝에 표식을 두어 잰다 — 줄바꿈 · 글꼴 · 안쪽 여백이 칸과 같으므로 자리도 같다.
 */
const MIRROR_PROPS = [
  "boxSizing", "width", "borderTopWidth", "borderRightWidth", "borderBottomWidth", "borderLeftWidth",
  "paddingTop", "paddingRight", "paddingBottom", "paddingLeft", "fontFamily", "fontSize", "fontWeight", "fontStyle",
  "letterSpacing", "lineHeight", "textTransform", "wordSpacing", "textIndent", "tabSize", "wordBreak", "overflowWrap",
] as const;
export function caretPoint(area: HTMLTextAreaElement, pos: number): { left: number; top: number; height: number } {
  const css = getComputedStyle(area);
  const div = document.createElement("div");
  const st = div.style as unknown as Record<string, string>;
  for (const key of MIRROR_PROPS) st[key] = (css as unknown as Record<string, string>)[key];
  st.position = "absolute"; st.visibility = "hidden"; st.top = "0"; st.left = "-9999px";
  st.whiteSpace = "pre-wrap"; st.overflow = "hidden"; st.height = "auto";
  div.textContent = area.value.slice(0, pos);
  const mark = document.createElement("span");
  mark.textContent = area.value.slice(pos, pos + 1) || ".";
  div.appendChild(mark);
  document.body.appendChild(div);
  const lineHeight = parseFloat(css.lineHeight) || parseFloat(css.fontSize) * 1.4;
  const point = { left: mark.offsetLeft - area.scrollLeft, top: mark.offsetTop - area.scrollTop, height: lineHeight };
  div.remove();
  return point;
}

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
  // `>>찾을말` — 과제 고르기 목록
  const [picks, setPicks] = useState<Pick[] | null>(null);
  const [pickAt, setPickAt] = useState(0);
  // 목록 자리(화면 기준) — 커서 바로 밑, 모자라면 위. 편집 칸 폭을 넘지 않는다
  const [pickPos, setPickPos] = useState<{ left: number; top: number; width: number; above: number } | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

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
      // `>>` 목록이 열려 있으면 ↑ ↓ 로 고르고 Enter · Tab 으로 넣는다, Esc 는 닫기
      const list = pickRef.current;
      if (list && list.length) {
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
          event.preventDefault();
          setPickAt((n) => (n + (event.key === "ArrowDown" ? 1 : list.length - 1)) % list.length);
          return;
        }
        if (event.key === "Enter" || event.key === "Tab") {
          event.preventDefault();
          choose(list[pickIndex.current] ?? list[0]);
          return;
        }
        if (event.key === "Escape") { event.preventDefault(); setPicks(null); return; }
      }
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
    // 칸을 떠나면 닫는다(목록을 누르는 것은 mousedown 을 막아 칸이 안 떠남)
    const onBlur = () => setPicks(null);
    const onInput = () => {
      const q = area.selectionStart === area.selectionEnd ? linkQuery(area.value, area.selectionStart) : null;
      if (!q) { setPicks(null); return; }
      void projectsOnce().then((all) => {
        const key = q.query.toLowerCase();
        const found = all.filter((p) => !key || p.id.toLowerCase().includes(key) || p.title.toLowerCase().includes(key)).slice(0, 8);
        place();
        setPicks(found);
        setPickAt(0);
      });
    };
    const onScroll = () => { if (pickRef.current) place(); };
    area.addEventListener("scroll", onScroll);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onScroll);
    area.addEventListener("blur", onBlur);
    area.addEventListener("input", onInput);
    area.addEventListener("keydown", onKey);
    area.addEventListener("keyup", onMove);
    area.addEventListener("click", onMove);
    return () => {
      area.removeEventListener("scroll", onScroll);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onScroll);
      area.removeEventListener("blur", onBlur);
      area.removeEventListener("input", onInput);
      area.removeEventListener("keydown", onKey);
      area.removeEventListener("keyup", onMove);
      area.removeEventListener("click", onMove);
    };
    // 칸은 편집기와 함께 한 번 선다 — 규칙 함수들은 늘 같은 것을 부른다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);

  // 열린 목록 · 고른 줄 — 키 처리기는 한 번 걸리므로 최신 값을 ref 로 본다
  const pickRef = useRef<Pick[] | null>(null);
  pickRef.current = picks;
  const pickIndex = useRef(0);
  pickIndex.current = pickAt;
  function place() {
    const area = target.current;
    if (!area) return;
    const rect = area.getBoundingClientRect();
    const caret = caretPoint(area, area.selectionStart);
    const width = Math.max(200, Math.min(420, rect.width - 8));
    // 커서가 칸 밖(스크롤로 가려짐)이면 칸 가장자리에 붙인다
    const y = Math.min(Math.max(caret.top, 0), rect.height - caret.height);
    const left = Math.min(Math.max(rect.left + caret.left, rect.left + 4), rect.right - width - 4);
    setPickPos({ left, top: rect.top + y + caret.height + 4, width, above: rect.top + y - 4 });
  }
  // 늘 커서 바로 밑에 — 화면 아래에 자리가 없으면 화면을 그만큼 올리고, 더 올릴 수 없을 때만 커서 위로
  useLayoutEffect(() => {
    const list = listRef.current;
    if (!list || !pickPos) return;
    const h = list.offsetHeight;
    const over = pickPos.top + h - (window.innerHeight - 8);
    if (over > 0) {
      const before = window.scrollY;
      window.scrollBy(0, Math.ceil(over) + 8);   // 1px 아래 넘침은 반올림으로 안 굴러 위로 가 버렸다
      if (window.scrollY !== before) { place(); return; }   // 올라간 만큼 다시 잰다
      if (pickPos.above - h > 8) { list.style.top = `${pickPos.above - h}px`; return; }
    }
    list.style.top = `${pickPos.top}px`;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [picks, pickPos]);
  // 고른 줄이 보이게
  useEffect(() => {
    // scrollIntoView 는 바깥(화면)까지 굴릴 수 있어 목록 안에서만 맞춘다 — 맨 위 안내 줄은 고정
    const list = listRef.current;
    const item = list?.querySelector<HTMLElement>(".md-pick.on");
    if (!list || !item) return;
    const head = list.querySelector<HTMLElement>(".md-picks-head")?.offsetHeight ?? 0;
    if (item.offsetTop - head < list.scrollTop) list.scrollTop = item.offsetTop - head - 6;
    else if (item.offsetTop + item.offsetHeight > list.scrollTop + list.clientHeight) list.scrollTop = item.offsetTop + item.offsetHeight - list.clientHeight + 6;
  }, [pickAt]);

  function choose(p: Pick) {
    const area = target.current;
    if (!area) return;
    setPicks(null);
    apply(linkProject(area.value, area.selectionStart, p.id, p.title));
  }

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
      {btn("S", "줄 긋기 (~~)", active.wraps.includes("~~"), () => wrap("~~"), "md-strike")}
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
      {picks !== null && (
        <div className="md-picks" role="listbox" aria-label="과제 연결" data-testid="md-picks" ref={listRef}
          style={pickPos ? { left: pickPos.left, top: pickPos.top, width: pickPos.width } : undefined}
          onMouseDown={(event) => event.preventDefault()}>
          <span className="muted md-picks-head">과제 연결 — ↑↓ 고르고 Enter (Esc 닫기)</span>
          {picks.length === 0 && <span className="muted">맞는 과제가 없습니다</span>}
          {picks.map((p, i) => (
            <button key={p.id} type="button" role="option" aria-selected={i === pickAt} className={i === pickAt ? "md-pick on" : "md-pick"}
              onMouseDown={(event) => event.preventDefault()} onClick={() => choose(p)}>
              <span className="project-id">{p.id}</span> {p.title}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
