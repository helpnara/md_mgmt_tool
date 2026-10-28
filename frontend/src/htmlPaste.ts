/**
 * 글 · 표가 섞인 HTML 붙여넣기 → 마크다운 (TODO 222).
 *
 * 생성형 AI 답 · 워드 · 웹 페이지를 복사하면 클립보드에 **글 · 표 여러 개 · 그림이 섞인 HTML** 이 담긴다.
 * 예전 붙여넣기(137)는 엑셀만 생각해 **첫 `<table>` 만** 표로 바꾸고 나머지를 버렸다. 여기서는 통째로 바꾼다.
 *
 * 그림은 대개 파일이 아니라 **주소**로 온다(`<img src="https://…">` — 로그인해야 열리는 주소). 바깥 주소를 본문에 두면
 * 사내망에서 안 보이고 밖으로 요청이 나가므로, 그 자리에 **안내 줄**을 남긴다. 그림 데이터(`data:`)가 함께 오면 파일로 돌려준다.
 */
import { tableElementRows, rowsToMarkdown } from "./table";

export interface HtmlPaste {
  markdown: string;
  /** `data:` 로 함께 온 그림 — 첨부로 올린다 */
  files: File[];
  /** 주소로만 와서 넣지 못한 그림 수 — 안내 줄이 그 자리에 있다 */
  missingImages: number;
}

/** 엑셀처럼 **표 하나뿐인** HTML 인가 — 표 밖에 글 · 그림 · 다른 표가 없다. */
export function soleTable(doc: Document): boolean {
  const tables = doc.querySelectorAll("table");
  if (tables.length !== 1) return false;
  const body = doc.body.cloneNode(true) as HTMLElement;
  body.querySelectorAll("table, style, script, meta, title, link").forEach((node) => node.remove());
  if (body.querySelector("img, svg, picture")) return false;
  return (body.textContent ?? "").replace(/\s+/g, "") === "";
}

const BLOCK = /^(P|DIV|SECTION|ARTICLE|MAIN|HEADER|FOOTER|ASIDE|FIGURE|FIGCAPTION|DETAILS|SUMMARY)$/;
const SKIP = /^(STYLE|SCRIPT|META|TITLE|LINK|BUTTON|NOSCRIPT|TEMPLATE|SVG)$/;

/** 클립보드 HTML 전체를 마크다운으로. */
export function htmlToMarkdown(html: string): HtmlPaste {
  const doc = new DOMParser().parseFromString(html, "text/html");
  const files: File[] = [];
  let missingImages = 0;

  /** 노드 하나를 줄 안의 마크다운으로 — 굵게 · 기울임 · 코드 · 링크 · 그림 · 줄바꿈 */
  const inlineOne = (child: Node): string => {
    if (child.nodeType === Node.TEXT_NODE) return (child.textContent ?? "").replace(/\s+/g, " ");
    if (child.nodeType !== Node.ELEMENT_NODE) return "";
    const el = child as HTMLElement;
    const tag = el.nodeName;
    if (SKIP.test(tag)) return "";
    if (tag === "BR") return "\n";
    if (tag === "IMG") return image(el as HTMLImageElement);
    if (tag === "STRONG" || tag === "B") return wrap(inline(el), "**");
    if (tag === "EM" || tag === "I") return wrap(inline(el), "*");
    if (tag === "DEL" || tag === "S") return wrap(inline(el), "~~");
    if (tag === "CODE") return code(el.textContent ?? "");
    if (tag === "A") {
      const text = inline(el).trim();
      const href = el.getAttribute("href") ?? "";
      return /^https?:\/\//i.test(href) && text && text !== href ? `[${text}](${href})` : text || href;
    }
    if (tag === "TABLE" || BLOCK.test(tag) || /^(H[1-6]|UL|OL|PRE|BLOCKQUOTE|HR)$/.test(tag)) {
      // 줄 안에 블록이 섞여 왔다 — 블록으로 내보낸다
      const wrapper = doc.createElement("div");
      wrapper.appendChild(el.cloneNode(true));
      return `\n\n${block(wrapper, "").trim()}\n\n`;
    }
    return inline(el);
  };

  /** 노드의 자식들을 줄 안의 마크다운으로 */
  const inline = (node: Node): string => {
    let out = "";
    node.childNodes.forEach((child) => {
      out += inlineOne(child);
    });
    return out;
  };

  const wrap = (text: string, mark: string) => {
    const trimmed = text.trim();
    if (!trimmed) return text;
    const lead = text.match(/^\s*/)?.[0] ?? "";
    const tail = text.match(/\s*$/)?.[0] ?? "";
    return `${lead}${mark}${trimmed}${mark}${tail}`;
  };
  const code = (text: string) => (text.includes("`") ? `\`\` ${text} \`\`` : `\`${text}\``);

  const image = (img: HTMLImageElement): string => {
    const src = img.getAttribute("src") ?? "";
    const alt = (img.getAttribute("alt") ?? "").trim();
    const file = dataUrlFile(src, files.length + 1);
    if (file) {
      files.push(file);
      return ""; // 올린 뒤 편집기가 링크를 넣는다
    }
    missingImages += 1;
    return `\n\n> 🖼 **그림 자리**${alt ? ` — ${alt}` : ""}: 붙여넣기에 그림 파일이 오지 않았습니다. 그림만 따로 복사해(그림 위 오른쪽 단추 → 이미지 복사) 이 자리에 붙여 넣으세요.\n\n`;
  };

  const list = (el: HTMLElement, indent: string): string => {
    const ordered = el.nodeName === "OL";
    let n = Number(el.getAttribute("start")) || 1;
    const lines: string[] = [];
    el.querySelectorAll(":scope > li").forEach((li) => {
      const marker = ordered ? `${n++}. ` : "- ";
      const pad = indent + " ".repeat(marker.length);
      let head = "";
      const nested: string[] = [];
      li.childNodes.forEach((child) => {
        if (child.nodeName === "UL" || child.nodeName === "OL") nested.push(list(child as HTMLElement, pad));
        else if (child.nodeType === Node.ELEMENT_NODE && /^(P|DIV)$/.test(child.nodeName)) head += ` ${inline(child)}`;
        else head += inlineOne(child);
      });
      const text = head.replace(/[ \t]+/g, " ").trim().split("\n").map((line, i) => (i ? pad + line.trim() : line)).join("\n");
      lines.push(`${indent}${marker}${text}`);
      lines.push(...nested);
    });
    return lines.join("\n");
  };

  const block = (node: Node, indent: string): string => {
    const parts: string[] = [];
    let line = "";
    const flush = () => {
      const text = line.replace(/[ \t]+/g, " ").replace(/ *\n */g, "\n").trim();
      if (text) parts.push(text);
      line = "";
    };
    node.childNodes.forEach((child) => {
      if (child.nodeType === Node.TEXT_NODE) {
        line += (child.textContent ?? "").replace(/\s+/g, " ");
        return;
      }
      if (child.nodeType !== Node.ELEMENT_NODE) return;
      const el = child as HTMLElement;
      const tag = el.nodeName;
      if (SKIP.test(tag)) return;
      if (/^H[1-6]$/.test(tag)) {
        flush();
        parts.push(`${"#".repeat(Number(tag[1]))} ${inline(el).replace(/\s+/g, " ").trim()}`);
      } else if (tag === "TABLE") {
        flush();
        const rows = tableElementRows(el as HTMLTableElement);
        if (rows.length > 0 && Math.max(...rows.map((row) => row.length)) >= 1) parts.push(rowsToMarkdown(rows));
      } else if (tag === "UL" || tag === "OL") {
        flush();
        const text = list(el, indent);
        if (text.trim()) parts.push(text);
      } else if (tag === "PRE") {
        flush();
        const codeEl = el.querySelector("code");
        const lang = (codeEl?.className.match(/language-([\w+-]+)/) ?? [])[1] ?? "";
        const text = (el.textContent ?? "").replace(/\n+$/, "");
        const fence = text.includes("```") ? "~~~" : "```";
        parts.push(`${fence}${lang}\n${text}\n${fence}`);
      } else if (tag === "BLOCKQUOTE") {
        flush();
        const inner = block(el, "").trim();
        if (inner) parts.push(inner.split("\n").map((row) => (row ? `> ${row}` : ">")).join("\n"));
      } else if (tag === "HR") {
        flush();
        parts.push("---");
      } else if (tag === "BR") {
        line += "\n";
      } else if (BLOCK.test(tag) || tag === "LI") {
        flush();
        const inner = block(el, indent).trim();
        if (inner) parts.push(inner);
      } else {
        line += inlineOne(el);
      }
    });
    flush();
    return parts.join("\n\n");
  };

  const markdown = block(doc.body, "")
    .replace(/[ \t]+$/gm, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  return { markdown, files, missingImages };
}

/** `data:image/png;base64,…` → File. 아니면 null. */
function dataUrlFile(src: string, n: number): File | null {
  const match = src.match(/^data:(image\/[\w.+-]+);base64,(.+)$/);
  if (!match) return null;
  try {
    const bytes = Uint8Array.from(atob(match[2]), (c) => c.charCodeAt(0));
    const ext = match[1].split("/")[1].replace("jpeg", "jpg").replace("svg+xml", "svg");
    return new File([bytes], `붙여넣은-그림-${n}.${ext}`, { type: match[1] });
  } catch {
    return null;
  }
}
