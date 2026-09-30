/**
 * 엑셀에서 복사한 표를 마크다운 표로 바꾼다.
 *
 * 엑셀·구글시트에서 셀 범위를 복사하면 클립보드에 **탭으로 나뉜 텍스트**가 담긴다.
 * 그대로 붙여넣으면 탭만 늘어선 한 덩어리가 되어, 결국 손으로 표를 다시 그려야 했다.
 * 실무에서 가장 자주 하는 동작이라 여기서 손이 가장 많이 준다.
 */

/** 표로 볼 만한 최소 조건 — 두 줄 이상이고, 모든 줄에 탭이 같은 개수로 들어 있다. */
export function looksLikeTable(text: string): boolean {
  const rows = splitRows(text);
  if (rows.length < 2) return false;
  const columns = rows[0].length;
  // 열이 하나뿐이면 그냥 여러 줄 텍스트다. 표로 바꾸면 오히려 방해가 된다.
  if (columns < 2) return false;
  return rows.every((row) => row.length === columns);
}

function splitRows(text: string): string[][] {
  return text
    .replace(/\r\n?/g, "\n")
    .replace(/\n+$/, "") // 엑셀은 끝에 줄바꿈을 하나 붙인다
    .split("\n")
    .map((line) => line.split("\t"));
}

/** 셀 안의 파이프는 표를 깨뜨리므로 벗어나게 한다. 줄바꿈은 <br> 로 바꾼다. */
function cell(value: string): string {
  return value.trim().replace(/\|/g, "\\|").replace(/\n/g, "<br>");
}

/**
 * 첫 줄을 머리글로 본다.
 *
 * 엑셀에서 표를 복사할 때 대개 머리글부터 잡기 때문이다. 머리글이 아니었다면
 * 사용자가 한 줄만 고치면 되지만, 머리글 없이 붙으면 표 자체가 성립하지 않는다.
 */
export function toMarkdownTable(text: string): string {
  return rowsToMarkdown(splitRows(text));
}

/** 표를 마크다운으로 — 행 길이가 다르면 가장 긴 행에 맞춰 빈 칸을 채운다. */
function rowsToMarkdown(rows: string[][]): string {
  const columns = Math.max(...rows.map((row) => row.length));
  const pad = (row: string[]) => [...row, ...Array(columns - row.length).fill("")];
  const head = `| ${pad(rows[0]).map(cell).join(" | ")} |`;
  const rule = `|${"---|".repeat(columns)}`;
  const body = rows.slice(1).map((row) => `| ${pad(row).map(cell).join(" | ")} |`);
  return [head, rule, ...body].join("\n");
}

/** 셀의 글 — 소스의 줄바꿈·들여쓰기는 공백 하나로, `<br>` 만 진짜 줄바꿈으로. */
function cellText(node: Node): string {
  let out = "";
  node.childNodes.forEach((child) => {
    if (child.nodeType === Node.TEXT_NODE) out += (child.textContent ?? "").replace(/\s+/g, " ");
    else if (child.nodeName === "BR") out += "\n";
    else if (child.nodeName === "STYLE" || child.nodeName === "SCRIPT") return;
    else {
      const inner = cellText(child);
      // 셀 안의 문단(<p>·<div>)은 줄을 바꾼다 — 워드 표가 이렇게 온다
      out += /^(P|DIV|LI)$/.test(child.nodeName) && out && !out.endsWith("\n") ? `\n${inner}` : inner;
    }
  });
  return out;
}

/**
 * HTML 표 → 행 목록 (TODO 137).
 *
 * 탭 글보다 HTML 이 정확하다. 탭 글은 셀 안 줄바꿈을 `"…"` 로 감싸 보내 줄 나누기가 셀을
 * 쪼개고, 병합 셀은 흔적이 없다. HTML 은 `<br>` · `colspan` · `rowspan` 을 그대로 준다.
 * 병합 셀은 마크다운 표에 없으므로 **값을 첫 칸에 두고 나머지를 비운다.**
 */
export function htmlTableRows(html: string): string[][] | null {
  const doc = new DOMParser().parseFromString(html, "text/html");
  const table = doc.querySelector("table");
  if (!table) return null;
  const rows: string[][] = [];
  // 위 행의 rowspan 이 아래 행 몇 칸을 차지하는지 — 열 번호 → 남은 행 수
  const carry = new Map<number, number>();
  table.querySelectorAll("tr").forEach((tr) => {
    const row: string[] = [];
    let column = 0;
    const skip = () => {
      while ((carry.get(column) ?? 0) > 0) {
        carry.set(column, (carry.get(column) ?? 0) - 1);
        row.push("");
        column += 1;
      }
    };
    tr.querySelectorAll(":scope > td, :scope > th").forEach((td) => {
      skip();
      const span = Math.max(1, Number(td.getAttribute("colspan")) || 1);
      const down = Math.max(1, Number(td.getAttribute("rowspan")) || 1);
      row.push(cellText(td).trim());
      for (let i = 1; i < span; i += 1) row.push("");
      if (down > 1) for (let i = 0; i < span; i += 1) carry.set(column + i, down - 1);
      column += span;
    });
    skip();
    rows.push(row);
  });
  // 엑셀은 선택 범위 끝에 빈 행을 붙이기도 한다
  while (rows.length > 0 && rows[rows.length - 1].every((value) => !value)) rows.pop();
  return rows;
}

/** 표로 볼 만한가 — 두 줄 이상 · 두 칸 이상 (탭 글과 같은 기준). */
function isTable(rows: string[][] | null): rows is string[][] {
  return rows !== null && rows.length >= 2 && Math.max(...rows.map((row) => row.length)) >= 2;
}

/** 클립보드의 표를 마크다운 표로. 표가 아니면 null. HTML 을 먼저 보고, 없으면 탭 글. */
export function tableFromClipboard(data: DataTransfer): string | null {
  const html = data.getData("text/html");
  if (html && /<table[\s>]/i.test(html)) {
    const rows = htmlTableRows(html);
    if (isTable(rows)) return rowsToMarkdown(rows);
  }
  const text = data.getData("text/plain");
  if (text && looksLikeTable(text)) return toMarkdownTable(text);
  return null;
}

/**
 * 표로 넣은 붙여넣기에 **그림도 함께 왔을 때** — 붙인 직후 [그림으로 바꾸기]를 권한다 (TODO 149).
 *
 * 처음(137)에는 Ctrl+Shift+V 를 그림 넣기로 정했는데, 크롬·엣지의 Ctrl+Shift+V 는 *서식 없이 붙여넣기*
 * 라 브라우저가 **글자만** 넘긴다 — 그림을 만들 재료가 오지 않는다. 그래서 단축키 대신, 붙인 순간 함께
 * 온 그림을 들고 있다가 사람이 고르게 한다. 엑셀 차트처럼 그림이 맞는 것도 Ctrl+V 한 번 + 단추 한 번이다.
 */
export interface PasteOffer {
  /** 방금 넣은 마크다운 표 — 바꿀 때 이 글을 찾아 지운다 */
  table: string;
  image: File;
}

/**
 * 편집기의 붙여넣기 — **모든 편집기가 이것 하나를 쓴다** (TODO 137).
 *
 * 윈도우 엑셀은 셀을 복사하면 클립보드에 **탭 글 · 표 HTML · 그 범위를 찍은 그림**을 함께 담는다.
 * 예전 편집기들은 파일(그림)부터 보고 거기서 끝나, 엑셀 표가 그림으로 들어갔다. 순서는
 *
 *   1. 표 → 마크다운 표. 그림도 함께 왔으면 [그림으로 바꾸기] 를 권한다(`onOffer`, 149)
 *   2. 표에서 온 글인데 표가 아니면(셀 하나) → 기본 붙여넣기(글자)
 *   3. 파일(캡처·그림) → `onFiles` 로 첨부
 *   4. 나머지 → 기본 동작
 *
 * 처리했으면 true.
 */
export function handleEditorPaste(
  event: React.ClipboardEvent<HTMLTextAreaElement>,
  handlers: {
    onInsert: (text: string) => void;
    onFiles?: (files: File[]) => void;
    /** 표로 넣었는데 그림도 함께 왔다 — [그림으로 바꾸기] 를 띄울 자리 (TODO 149) */
    onOffer?: (offer: PasteOffer) => void;
  },
): boolean {
  const data = event.clipboardData;
  const files = Array.from(data.files);
  const table = tableFromClipboard(data);
  if (table) {
    event.preventDefault();
    handlers.onInsert(`\n${table}\n`);
    const image = files.find((file) => file.type.startsWith("image/"));
    if (image && handlers.onFiles && handlers.onOffer) handlers.onOffer({ table, image });
    return true;
  }
  // 엑셀 셀 하나: 글자로 붙인다 — 그림 한 장이 되면 고칠 수도 없다
  if (/<table[\s>]/i.test(data.getData("text/html")) && data.getData("text/plain")) return false;
  if (files.length > 0 && handlers.onFiles) {
    event.preventDefault();
    handlers.onFiles(files);
    return true;
  }
  return false;
}

/** 예전 이름 — 표만 가로챈다. 파일을 받지 않는 칸(보고 지시사항 등)에서 쓴다. */
export function pasteAsTable(
  event: React.ClipboardEvent<HTMLTextAreaElement>,
  onInsert: (text: string) => void,
): boolean {
  return handleEditorPaste(event, { onInsert });
}

/**
 * 커서 자리에 글을 끼운 새 값. 편집기마다 커서 다루기를 따로 짜지 않게 둔다.
 * 끼운 뒤 커서는 끼운 글 끝으로 옮긴다(그리고 나서 부르는 쪽이 값을 바꾼다).
 */
export function spliceAtCaret(area: HTMLTextAreaElement | null, value: string, snippet: string): string {
  if (!area) return `${value.replace(/\s*$/, "")}\n${snippet}`;
  const start = area.selectionStart ?? value.length;
  const end = area.selectionEnd ?? start;
  const next = value.slice(0, start) + snippet + value.slice(end);
  const caret = start + snippet.length;
  window.requestAnimationFrame(() => {
    area.focus();
    area.setSelectionRange(caret, caret);
  });
  return next;
}
