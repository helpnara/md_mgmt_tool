/**
 * 마크다운 편집 규칙 (TODO 321 1단계) — 느린 여백(helpnara/MD_Management)의 `Core/Editor` 규칙을 옮긴 것.
 *
 * 모두 **순수 함수**다: (글, 고른 범위) → 바꿀 한 덩어리(`Edit`). 화면(`MdToolbar`)은 그 덩어리를
 * `insertText` 한 번으로 넣는다 — 그래야 Ctrl+Z 한 번에 되돌아가고, React 의 onChange 가 그대로 돈다.
 *
 * * 서식 걸기 · 풀기 — 굵게 `**` · 기울임 `*` · 취소선 `~~` · 코드 `` ` `` (느린 여백 `Formatting.toggle`)
 * * 줄 앞 표시 — 제목 · 인용 · 목록(`-` · `1.` · `- [ ]`) — 이미 있으면 풀고, 다른 것이면 갈아 끼운다(`ListStyle`)
 * * 표 넣기 · 링크
 * * 목록에서 Enter — 다음 항목 이어 주기, 빈 항목이면 한 단계 위로 · 마커 지움 (`ListEditing`)
 * * Tab / Shift+Tab — 고른 줄 들여쓰기 · 내어쓰기
 * * 줄바꿈 고치기 — `U+2028` · `U+2029` → 줄바꿈, 줄 앞 붙는 빈칸(`U+00A0`) → 빈칸 (`LineBreaks`)
 *
 * 마크다운 표준 안쪽만 쓴다(글자색 · 밑줄 없음) — 파일이 원본이라 다른 도구에서도 그대로 읽혀야 한다.
 */

export interface Edit {
  /** 바꿀 범위(지금 글 기준)와 넣을 글 */
  from: number;
  to: number;
  insert: string;
  /** 바꾼 뒤 고를 범위(바꾼 글 기준) */
  selStart: number;
  selEnd: number;
}

export type Wrap = "**" | "*" | "~~" | "`";
export type LineKind = "h1" | "h2" | "h3" | "quote" | "bullet" | "number" | "task";

const LIST = /^(\s*)([-*+]\s\[[ xX]\]\s|[-*+]\s|\d+[.)]\s)/;
const PREFIX = /^(\s*)(#{1,6}\s|>\s?|[-*+]\s\[[ xX]\]\s|[-*+]\s|\d+[.)]\s)?/;

/** 고른 범위가 걸친 줄들의 [처음, 끝) */
function lineSpan(text: string, start: number, end: number): [number, number] {
  const a = text.lastIndexOf("\n", start - 1) + 1;
  let b = text.indexOf("\n", end > start && text[end - 1] === "\n" ? end - 1 : end);
  if (b < 0) b = text.length;
  return [a, b];
}

// ── 서식 걸기 · 풀기 ─────────────────────────────────────────────────────────
export function toggleWrap(text: string, start: number, end: number, mark: Wrap, placeholder = "글"): Edit {
  const n = mark.length;
  const sel = text.slice(start, end);
  // 고른 글이 이미 표시 안에 있으면(바깥에 표시) 푼다
  if (start >= n && text.slice(start - n, start) === mark && text.slice(end, end + n) === mark
    && !(mark === "*" && (text[start - n - 1] === "*" || text[end + n] === "*"))) {
    return { from: start - n, to: end + n, insert: sel, selStart: start - n, selEnd: end - n };
  }
  // 고른 글 자체가 표시로 싸여 있으면 푼다
  if (sel.length >= 2 * n && sel.startsWith(mark) && sel.endsWith(mark)) {
    const inner = sel.slice(n, sel.length - n);
    return { from: start, to: end, insert: inner, selStart: start, selEnd: start + inner.length };
  }
  const body = sel || placeholder;
  // 고른 범위 앞뒤 빈칸은 표시 밖으로(`** 글**` 은 마크다운이 굵게로 안 본다)
  const lead = body.match(/^\s*/)![0];
  const trail = body.slice(lead.length).match(/\s*$/)![0];
  const core = body.slice(lead.length, body.length - trail.length);
  const insert = `${lead}${mark}${core}${mark}${trail}`;
  const s = start + lead.length + n;
  return { from: start, to: end, insert, selStart: s, selEnd: s + core.length };
}

// ── 줄 앞 표시 ───────────────────────────────────────────────────────────────
const KIND_MARK: Record<LineKind, string> = { h1: "# ", h2: "## ", h3: "### ", quote: "> ", bullet: "- ", number: "1. ", task: "- [ ] " };

function kindOf(prefix: string): LineKind | null {
  const p = prefix.trim();
  if (p === "#") return "h1";
  if (p === "##") return "h2";
  if (p === "###") return "h3";
  if (p.startsWith(">")) return "quote";
  if (/^[-*+]\s\[[ xX]\]$/.test(p)) return "task";
  if (/^[-*+]$/.test(p)) return "bullet";
  if (/^\d+[.)]$/.test(p)) return "number";
  return null;
}

/** 고른 줄들에 줄 앞 표시를 건다. 모든 줄이 이미 그 표시면 푼다. 번호 목록은 1. 2. 3. 으로 다시 센다 */
export function toggleLine(text: string, start: number, end: number, kind: LineKind): Edit {
  const [a, b] = lineSpan(text, start, end);
  const lines = text.slice(a, b).split("\n");
  const parsed = lines.map((line) => {
    const m = line.match(PREFIX)!;
    return { indent: m[1], prefix: m[2] ?? "", rest: line.slice(m[0].length) };
  });
  const all = parsed.every((p) => p.rest.trim() === "" || kindOf(p.prefix) === kind);
  let n = 0;
  const out = parsed.map((p) => {
    if (all) return p.indent + p.rest;                       // 풀기
    if (p.rest.trim() === "" && !p.prefix) return p.indent + p.rest;   // 빈 줄은 그대로
    n += 1;
    // 제목 · 인용은 들여쓰기를 둘 자리가 없다 — 앞 빈칸을 뗀다
    const indent = kind === "h1" || kind === "h2" || kind === "h3" ? "" : p.indent;
    const mark = kind === "number" ? `${n}. ` : KIND_MARK[kind];
    return indent + mark + p.rest;
  });
  const insert = out.join("\n");
  // 커서가 한 줄이면 글 끝으로, 여러 줄이면 바꾼 덩어리 전체를 고른다
  const single = lines.length === 1;
  return { from: a, to: b, insert, selStart: single ? a + insert.length : a, selEnd: a + insert.length };
}

// ── 표 · 링크 ────────────────────────────────────────────────────────────────
export function insertTable(text: string, start: number, rows = 3, cols = 3): Edit {
  const head = Array.from({ length: cols }, (_, i) => `제목${i + 1}`);
  const line = (cells: string[]) => `| ${cells.join(" | ")} |`;
  const body = [line(head), `|${" --- |".repeat(cols)}`, ...Array.from({ length: rows - 1 }, () => line(Array(cols).fill("  ")))].join("\n");
  // 표는 앞뒤가 빈 줄이어야 표로 선다
  const before = start === 0 || text.slice(0, start).endsWith("\n\n") ? "" : text.slice(0, start).endsWith("\n") ? "\n" : "\n\n";
  const after = text.slice(start).startsWith("\n\n") || start === text.length ? "\n" : "\n\n";
  const insert = before + body + after;
  const first = start + before.length + 2;     // 첫 머리 칸
  return { from: start, to: start, insert, selStart: first, selEnd: first + head[0].length };
}

export function insertLink(text: string, start: number, end: number, url = "https://"): Edit {
  const label = text.slice(start, end) || "링크 글";
  const insert = `[${label}](${url})`;
  // 주소 자리를 고른다 — 바로 붙여넣으면 된다
  const s = start + label.length + 3;
  return { from: start, to: end, insert, selStart: s, selEnd: s + url.length };
}

// ── 목록에서 Enter ───────────────────────────────────────────────────────────
/** 목록 줄 끝에서 Enter — 다음 항목을 이어 준다. 목록이 아니면 null(브라우저 그대로) */
export function enterInList(text: string, caret: number): Edit | null {
  const a = text.lastIndexOf("\n", caret - 1) + 1;
  const lineEnd = text.indexOf("\n", caret) < 0 ? text.length : text.indexOf("\n", caret);
  const line = text.slice(a, lineEnd);
  const m = line.match(LIST);
  if (!m) return null;
  const [whole, indent, marker] = m;
  if (caret < a + whole.length) return null;               // 표시 앞에서 누르면 그대로
  const rest = line.slice(whole.length);
  if (rest.trim() === "" && caret === lineEnd) {
    // 빈 항목 — 겹친 것이면 한 단계 위로, 맨 위면 표시를 지워 보통 줄
    if (indent.length > 0) {
      const parent = parentIndent(text, a, indent.length);
      const shifted = " ".repeat(parent) + marker;
      return { from: a, to: lineEnd, insert: shifted, selStart: a + shifted.length, selEnd: a + shifted.length };
    }
    return { from: a, to: lineEnd, insert: "", selStart: a, selEnd: a };
  }
  let next = marker;
  const num = marker.match(/^(\d+)([.)])\s$/);
  if (num) next = `${Number(num[1]) + 1}${num[2]} `;
  else if (/\[[ xX]\]/.test(marker)) next = marker.replace(/\[[ xX]\]/, "[ ]");
  const insert = `\n${indent}${next}`;
  // 커서 뒤 글은 새 항목으로 따라간다
  return { from: caret, to: caret, insert, selStart: caret + insert.length, selEnd: caret + insert.length };
}

/** 이 줄보다 얕은 바로 위 목록 줄의 들여쓰기(없으면 0) */
function parentIndent(text: string, lineStart: number, indent: number): number {
  const lines = text.slice(0, lineStart).split("\n").reverse();
  for (const l of lines) {
    const m = l.match(LIST);
    if (m && m[1].length < indent) return m[1].length;
    if (l.trim() === "") continue;
  }
  return 0;
}

/** 바로 위 목록 줄의 글이 시작하는 칸 — 그 아래로 들여 쓸 자리(`1. ` 아래는 세 칸, `- ` 아래는 두 칸) */
function childIndent(text: string, lineStart: number, indent: number): number {
  const lines = text.slice(0, lineStart).split("\n").reverse();
  for (const l of lines) {
    if (l.trim() === "") continue;
    const m = l.match(LIST);
    if (m && m[1].length <= indent) return m[1].length + m[2].length;
    if (!m) break;
  }
  return indent + 2;
}

// ── 들여쓰기 · 내어쓰기 ──────────────────────────────────────────────────────
export function shiftLines(text: string, start: number, end: number, deeper: boolean): Edit {
  const [a, b] = lineSpan(text, start, end);
  const lines = text.slice(a, b).split("\n");
  let pos = a;
  let firstDelta = 0;
  const out = lines.map((line, i) => {
    const indent = line.match(/^\s*/)![0].length;
    let next = indent;
    if (deeper) next = LIST.test(line) ? Math.max(childIndent(text, pos, indent), indent + 2) : indent + 2;
    else next = LIST.test(line) ? parentIndent(text, pos, indent) : Math.max(0, indent - 2);
    let body = line.slice(indent);
    // 번호 목록을 옮기면 그 단계의 번호로 — 바로 위 같은 단계 번호 + 1, 없으면 1 (느린 여백 ListStyle 과 같은 셈)
    const num = body.match(/^(\d+)([.)])\s/);
    if (num && next !== indent) {
      const prev = text.slice(0, pos).split("\n").reverse().find((l) => l.trim() !== "" && (l.match(/^\s*/)![0].length <= next));
      const pm = prev?.match(/^(\s*)(\d+)[.)]\s/);
      const n = pm && pm[1].length === next ? Number(pm[2]) + 1 : 1;
      body = `${n}${num[2]} ` + body.slice(num[0].length);
    }
    if (i === 0) firstDelta = next - indent + (body.length - line.slice(indent).length);
    pos += line.length + 1;
    return " ".repeat(next) + body;
  });
  const insert = out.join("\n");
  const single = lines.length === 1;
  return {
    from: a, to: b, insert,
    selStart: single ? Math.max(a, start + firstDelta) : a,
    selEnd: single ? Math.max(a, end + firstDelta) : a + insert.length,
  };
}

// ── 줄바꿈 고치기 ────────────────────────────────────────────────────────────
/** 바꿀 것이 없으면 null. 글자 수는 그대로(한 글자 → 한 글자) */
export function repairLineBreaks(text: string): string | null {
  let out = text.replace(/[\u2028\u2029]/g, "\n");
  out = out.split("\n").map((line) => line.replace(/^[ \u00a0]+/, (lead) => lead.replace(/\u00a0/g, " "))).join("\n");
  return out === text ? null : out;
}

// ── 커서 자리에 걸린 표시(도구 띠가 눌린 모습) ───────────────────────────────
export interface Active { wraps: Wrap[]; line: LineKind | null }

export function activeAt(text: string, caret: number): Active {
  const a = text.lastIndexOf("\n", caret - 1) + 1;
  const b = text.indexOf("\n", caret) < 0 ? text.length : text.indexOf("\n", caret);
  const line = text.slice(a, b);
  const m = line.match(PREFIX)!;
  const kind = m[2] ? kindOf(m[2]) : null;
  const at = caret - a;
  const wraps: Wrap[] = [];
  const inside = (re: RegExp) => {
    for (const hit of line.matchAll(re)) {
      if (hit.index !== undefined && at > hit.index && at < hit.index + hit[0].length) return true;
    }
    return false;
  };
  if (inside(/\*\*[^*\n]+\*\*/g)) wraps.push("**");
  if (inside(/(?<!\*)\*[^*\n]+\*(?!\*)/g)) wraps.push("*");
  if (inside(/~~[^~\n]+~~/g)) wraps.push("~~");
  if (inside(/`[^`\n]+`/g)) wraps.push("`");
  return { wraps, line: kind };
}

// ── 읽기 화면 체크박스 (321 2단계) ───────────────────────────────────────────
/** 원문 `line` 줄(0 부터)의 할 일 표시 한 글자만 바꾼다 — `[ ]` ↔ `[x]`. 그 줄이 할 일이 아니면 null */
export function toggleTask(text: string, line: number): string | null {
  const lines = text.split("\n");
  const target = lines[line];
  if (target === undefined) return null;
  const m = target.match(/^(\s*(?:[-*+]|\d+[.)])\s+)\[([ xX])\]/);
  if (!m) return null;
  const mark = m[2] === " " ? "x" : " ";
  lines[line] = target.slice(0, m[1].length) + `[${mark}]` + target.slice(m[1].length + 3);
  return lines.join("\n");
}

// ── >> 과제 연결 (321 2단계) ─────────────────────────────────────────────────
/** 커서 바로 앞이 `>>찾을말` 이면 {처음, 찾을말}. 빈칸 · 줄바꿈이 끼면 끝난 것 */
export function linkQuery(text: string, caret: number): { from: number; query: string } | null {
  const head = text.slice(Math.max(0, caret - 40), caret);
  const m = head.match(/>>([^\s>\]\[()]{0,30})$/);
  if (!m) return null;
  return { from: caret - m[0].length, query: m[1] };
}

/** `>>찾을말` 을 과제 링크로 — 파일에는 표준 마크다운 링크만 남는다(`[제목](#/projects/번호)`) */
export function linkProject(text: string, caret: number, id: string, title: string): Edit | null {
  const q = linkQuery(text, caret);
  if (!q) return null;
  const insert = `[${title.replace(/[[\]]/g, "")}](#/projects/${id})`;
  return { from: q.from, to: caret, insert, selStart: q.from + insert.length, selEnd: q.from + insert.length };
}
