/**
 * 글 · 표가 섞인 HTML 붙여넣기 → 마크다운 (TODO 222 · 225).
 *
 * 생성형 AI 답 · 워드 · 웹 페이지를 복사하면 클립보드에 **글 · 표 여러 개 · 그림이 섞인 HTML** 이 담긴다.
 * 예전 붙여넣기(137)는 엑셀만 생각해 **첫 `<table>` 만** 표로 바꾸고 나머지를 버렸다. 여기서는 통째로 바꾼다.
 *
 * **그림은 경우마다 다르다 (225)** — 222 는 `data:` 가 아니면 모두 안내 줄로 두었고, 단추 · 표 칸 · `<svg>` 안의 그림은 말없이 버렸다.
 *
 *   | 경우                                   | 무엇을 하나                                                  |
 *   |----------------------------------------|-------------------------------------------------------------|
 *   | 이 앱에서 복사한 그림 (같은 PC 주소)    | 가져와 **이 문서에 다시 첨부** — 실제 그림이 그 자리에       |
 *   | `data:` 그림                            | 파일로 바꿔 첨부                                             |
 *   | `blob:` 주소                            | 가져와 보고, 안 되면 안내 줄                                 |
 *   | 바깥 주소 (`https://…`)                 | 가져오지 않는다(사내망 · 밖으로 나가는 요청) — 안내 줄에 도메인 |
 *   | `<svg>` 도형 · 차트                     | PNG 로 바꿔 첨부. 작은 것(단추 아이콘)은 건너뛴다            |
 *   | `<canvas>` 차트                         | 그림 데이터가 오지 않는다 — 안내 줄                          |
 *   | 단추 · 링크로 감싼 그림, `<picture>` · `srcset` · `data-src` · 배경 그림 | 감싼 것을 벗기고 주소를 찾아 위 규칙대로 |
 *
 * 가져와야 하는 그림은 그 자리에 **표시(marker)** 를 남기고 `jobs` 로 돌려준다. 편집기가 하나씩 가져와 올리고 표시를 그림 링크로 바꾼다
 * (`pasteImages.placeImages`). 그림을 받지 않는 칸이면(`canAttach: false`) 처음부터 안내 줄만 넣는다.
 */
import { rowsToMarkdown, tableElementRows } from "./table";

export interface ImageJob {
  /** 본문에 먼저 들어가는 자리 표시 — 그림 링크나 안내 줄로 바뀐다 */
  marker: string;
  /** 그림 파일을 가져온다. 못 가져오면 null */
  load: () => Promise<File | null>;
  /** 못 가져왔을 때 그 자리에 둘 글 (reason 을 주면 그 까닭으로) */
  fallback: (reason?: string) => string;
}

export interface HtmlPaste {
  markdown: string;
  jobs: ImageJob[];
}

/** 엑셀처럼 **표 하나뿐인** HTML 인가 — 표 밖에 글 · 그림 · 다른 표가 없다. */
export function soleTable(doc: Document): boolean {
  const tables = doc.querySelectorAll("table");
  if (tables.length !== 1) return false;
  const body = doc.body.cloneNode(true) as HTMLElement;
  body.querySelectorAll("table, style, script, meta, title, link").forEach((node) => node.remove());
  if (body.querySelector("img, svg, picture, canvas")) return false;
  return (body.textContent ?? "").replace(/\s+/g, "") === "";
}

/** 그림으로 칠 만한 것이 있는가 — 작은 `<svg>`(단추 아이콘)는 빼고 (225). */
export function hasMedia(doc: Document): boolean {
  if (doc.querySelector("img, picture, canvas")) return true;
  if (Array.from(doc.querySelectorAll("svg")).some((svg) => bigSvg(svg))) return true;
  return Array.from(doc.querySelectorAll<HTMLElement>("[style]")).some((el) => backgroundUrl(el) !== null);
}

const BLOCK = /^(P|DIV|SECTION|ARTICLE|MAIN|HEADER|FOOTER|ASIDE|FIGURE|FIGCAPTION|DETAILS|SUMMARY)$/;
const SKIP = /^(STYLE|SCRIPT|META|TITLE|LINK|NOSCRIPT|TEMPLATE|INPUT|SELECT|TEXTAREA)$/;
const MEDIA = /^(IMG|SVG|svg|PICTURE|CANVAS)$/;
/** 그림 링크로 바꿀 때까지 두는 표시 — 붙여넣기마다 다른 꼬리를 단다(두 번 붙여도 섞이지 않게) */
const MARK = "⏳ 그림 가져오는 중";
/** 이 크기보다 작은 `<svg>` 는 단추 · 글자 옆 아이콘으로 본다 */
const SVG_MIN = 64;

/** 클립보드 HTML 전체를 마크다운으로. `canAttach` — 그림을 첨부로 받을 수 있는 편집기인가 */
export function htmlToMarkdown(html: string, { canAttach = true }: { canAttach?: boolean } = {}): HtmlPaste {
  const doc = new DOMParser().parseFromString(html, "text/html");
  const jobs: ImageJob[] = [];
  const tag = Math.random().toString(36).slice(2, 6);

  // ── 그림 ────────────────────────────────────────────────────────────────
  /** 그림 하나를 그 자리의 글로. inCell — 표 칸 안이면 한 줄로 */
  const media = (el: Element, inCell = false): string => {
    const name = el.nodeName;
    if (name === "PICTURE") {
      const img = el.querySelector("img");
      if (img) return media(img, inCell);
      const source = firstSrcset(el.querySelector("source")?.getAttribute("srcset"));
      return source ? fromUrl(source, "", inCell) : "";
    }
    if (name === "IMG") {
      const img = el as HTMLImageElement;
      const src = img.getAttribute("src") || firstSrcset(img.getAttribute("srcset")) || img.getAttribute("data-src")
        || firstSrcset(img.getAttribute("data-srcset")) || "";
      const alt = (img.getAttribute("alt") || img.getAttribute("title") || "").trim();
      // 글자 옆의 작은 그림(이모지 · 아이콘)은 건너뛴다 — 크기를 적어 둔 것만 본다
      const w = Number(img.getAttribute("width")), h = Number(img.getAttribute("height"));
      if (w && h && w < 32 && h < 32) return alt;
      return fromUrl(src, alt, inCell);
    }
    if (name === "svg" || name === "SVG") {
      if (!bigSvg(el)) return "";
      const label = (el.getAttribute("aria-label") || el.querySelector("title")?.textContent || "").trim();
      const n = jobs.length + 1;
      return job(label || "도형", async () => svgToPng(el, n), "도형 그림을 그림 파일로 바꾸지 못했습니다.", inCell);
    }
    if (name === "CANVAS") {
      return placeholder((el.getAttribute("aria-label") || "차트").trim(), "차트(그림판)는 붙여넣기에 그림 데이터가 오지 않습니다.", inCell);
    }
    return "";
  };

  /** 주소로 온 그림 — 어디서 왔는지에 따라 */
  const fromUrl = (src: string, alt: string, inCell: boolean): string => {
    if (!src) return placeholder(alt, "그림 주소가 오지 않았습니다.", inCell);
    const n = jobs.length + 1; // 파일 이름의 번호 — 찾은 순서대로
    if (/^data:image\//i.test(src)) return job(alt, async () => dataUrlFile(src, n), "그림 데이터를 읽지 못했습니다.", inCell);
    if (/^blob:/i.test(src)) return job(alt, () => fetchFile(src, alt), "다른 창에서만 열리는 그림(blob)이라 가져오지 못했습니다.", inCell);
    let url: URL;
    try {
      url = new URL(src, window.location.href);
    } catch {
      return placeholder(alt, "그림 주소를 읽지 못했습니다.", inCell);
    }
    // 이 앱의 그림(같은 PC) — 가져와 다시 첨부한다. 다른 과제의 그림이어도 이 문서의 첨부가 된다
    if (url.origin === window.location.origin) return job(alt, () => fetchFile(url.href, alt), "이 PC 의 그림을 가져오지 못했습니다.", inCell);
    if (/^https?:$/.test(url.protocol)) {
      return placeholder(alt, `바깥 주소(${url.hostname})의 그림이라 가져오지 않았습니다.`, inCell);
    }
    return placeholder(alt, "그림 주소를 읽지 못했습니다.", inCell);
  };

  /** 가져올 그림 — 표시를 남기고 일을 적어 둔다. 받지 않는 칸이면 안내 줄 */
  const job = (alt: string, load: () => Promise<File | null>, reason: string, inCell: boolean): string => {
    if (!canAttach) return placeholder(alt, "이 칸에는 그림을 넣지 않습니다.", inCell);
    const marker = `${MARK} (${jobs.length + 1}·${tag})`;
    jobs.push({ marker, load, fallback: (why) => placeholder(alt, why ?? reason, inCell).trim() });
    return inCell ? marker : `\n\n${marker}\n\n`;
  };

  /** 배경 그림(`style="background-image:url(…)"`)만 있는 칸 */
  const backgroundMedia = (el: HTMLElement): string | null => {
    const url = backgroundUrl(el);
    if (url === null || (el.textContent ?? "").trim()) return null;
    return fromUrl(url, (el.getAttribute("aria-label") || el.getAttribute("title") || "").trim(), false);
  };

  /** 감싼 것(단추 · 링크) 안의 그림만 — 단추의 글자("크게 보기")는 버린다 */
  const mediaInside = (el: Element): string =>
    Array.from(el.querySelectorAll("img, svg, picture, canvas"))
      // 가장 바깥 것만 — `<picture>` 안의 `<img>`, `<svg>` 안의 것은 바깥 것이 맡는다
      .filter((item) => {
        const outer = item.parentElement?.closest("picture, svg");
        return !outer || !el.contains(outer);
      })
      .map((item) => media(item))
      .join("");

  // ── 글 ──────────────────────────────────────────────────────────────────
  /** 노드 하나를 줄 안의 마크다운으로 — 굵게 · 기울임 · 코드 · 링크 · 그림 · 줄바꿈 */
  const inlineOne = (child: Node): string => {
    if (child.nodeType === Node.TEXT_NODE) return (child.textContent ?? "").replace(/\s+/g, " ");
    if (child.nodeType !== Node.ELEMENT_NODE) return "";
    const el = child as HTMLElement;
    const name = el.nodeName;
    if (SKIP.test(name)) return "";
    if (MEDIA.test(name)) return media(el);
    if (name === "BUTTON") return mediaInside(el); // 크게 보기 단추로 감싼 그림 (225)
    if (name === "BR") return "\n";
    const bg = backgroundMedia(el);
    if (bg !== null) return bg;
    if (name === "STRONG" || name === "B") return wrap(inline(el), "**");
    if (name === "EM" || name === "I") return wrap(inline(el), "*");
    if (name === "DEL" || name === "S") return wrap(inline(el), "~~");
    if (name === "CODE") return code(el.textContent ?? "");
    if (name === "A") {
      // 그림을 감싼 링크는 그림만 — 링크 글자 안에 그림 자리가 들어가면 깨진다 (225)
      if (el.querySelector("img, svg, picture, canvas") && !(el.textContent ?? "").trim()) return mediaInside(el);
      const text = inline(el).trim();
      const href = el.getAttribute("href") ?? "";
      return /^https?:\/\//i.test(href) && text && text !== href && !text.includes("\n") ? `[${text}](${href})` : text || href;
    }
    if (name === "TABLE" || BLOCK.test(name) || /^(H[1-6]|UL|OL|PRE|BLOCKQUOTE|HR)$/.test(name)) {
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
    if (!trimmed || trimmed.includes("\n")) return text; // 그림 자리처럼 여러 줄이 든 것은 감싸지 않는다
    const lead = text.match(/^\s*/)?.[0] ?? "";
    const tail = text.match(/\s*$/)?.[0] ?? "";
    return `${lead}${mark}${trimmed}${mark}${tail}`;
  };
  const code = (text: string) => (text.includes("`") ? `\`\` ${text} \`\`` : `\`${text}\``);

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
      const text = head.replace(/[ \t]+/g, " ").replace(/\n{2,}/g, "\n").trim().split("\n").map((line, i) => (i ? pad + line.trim() : line)).join("\n");
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
      const name = el.nodeName;
      if (SKIP.test(name)) return;
      if (/^H[1-6]$/.test(name)) {
        flush();
        parts.push(`${"#".repeat(Number(name[1]))} ${inline(el).replace(/\s+/g, " ").trim()}`);
      } else if (name === "TABLE") {
        flush();
        const rows = tableElementRows(el as HTMLTableElement, (item) => media(item, true));
        if (rows.length > 0 && Math.max(...rows.map((row) => row.length)) >= 1) parts.push(rowsToMarkdown(rows));
      } else if (name === "UL" || name === "OL") {
        flush();
        const text = list(el, indent);
        if (text.trim()) parts.push(text);
      } else if (name === "PRE") {
        flush();
        const codeEl = el.querySelector("code");
        const lang = (codeEl?.className.match(/language-([\w+-]+)/) ?? [])[1] ?? "";
        const text = (el.textContent ?? "").replace(/\n+$/, "");
        const fence = text.includes("```") ? "~~~" : "```";
        parts.push(`${fence}${lang}\n${text}\n${fence}`);
      } else if (name === "BLOCKQUOTE") {
        flush();
        const inner = block(el, "").trim();
        if (inner) parts.push(inner.split("\n").map((row) => (row ? `> ${row}` : ">")).join("\n"));
      } else if (name === "HR") {
        flush();
        parts.push("---");
      } else if (name === "BR") {
        line += "\n";
      } else if ((BLOCK.test(name) || name === "LI") && backgroundUrl(el) === null) {
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
  return { markdown, jobs };
}

/**
 * 글자(마크다운)로만 온 붙여넣기의 **바깥 그림** — `![설명](https://…)` 을 안내 줄로 (225).
 * AI 도구의 [복사] 단추는 HTML 없이 마크다운 글자만 주기도 한다. 바깥 주소가 그대로 본문에 들어가면 사내망에서 안 보이고 밖으로 요청이 나간다.
 * 바꿀 것이 없으면 null.
 */
export function markdownExternalImages(text: string): string | null {
  let changed = false;
  const out = text.replace(/!\[([^\]]*)\]\(\s*<?((?:https?:|blob:)[^)\s>]+)>?(?:\s+"[^"]*")?\s*\)/gi, (_, alt: string, src: string) => {
    let host = "";
    try {
      host = new URL(src).hostname;
    } catch {
      host = "";
    }
    if (host && host === window.location.hostname) return _; // 이 PC 의 주소는 그대로
    changed = true;
    const why = /^blob:/i.test(src) ? "다른 창에서만 열리는 그림(blob)이라 가져오지 못했습니다." : `바깥 주소(${host || "알 수 없음"})의 그림이라 가져오지 않았습니다.`;
    return placeholder(alt.trim(), why, false); // 앞뒤 빈 줄 — 다음 줄이 인용에 붙지 않게
  });
  return changed ? out.replace(/\n{3,}/g, "\n\n") : null;
}

/** 그림 자리 안내 — 왜 못 넣었는지 · 어떻게 하면 되는지 */
function placeholder(alt: string, reason: string, inCell: boolean): string {
  if (inCell) return `🖼 그림 자리${alt ? `(${alt.replace(/[|\n]/g, " ")})` : ""}`;
  return `\n\n> 🖼 **그림 자리**${alt ? ` — ${alt}` : ""}: ${reason} 그림만 따로 복사(그림 위 오른쪽 단추 → 이미지 복사)해 이 자리에 붙여 넣으세요.\n\n`;
}

function firstSrcset(value: string | null | undefined): string {
  return (value ?? "").split(",")[0]?.trim().split(/\s+/)[0] ?? "";
}

function backgroundUrl(el: Element): string | null {
  const style = el.getAttribute("style") ?? "";
  const match = style.match(/background(?:-image)?\s*:[^;]*url\(\s*['"]?([^'")]+)['"]?\s*\)/i);
  return match ? match[1] : null;
}

function svgSize(svg: Element): { w: number; h: number } {
  let w = parseFloat(svg.getAttribute("width") ?? "");
  let h = parseFloat(svg.getAttribute("height") ?? "");
  const box = (svg.getAttribute("viewBox") ?? "").split(/[\s,]+/).map(Number);
  if ((!w || !h) && box.length === 4 && box[2] > 0 && box[3] > 0) {
    w = w || box[2];
    h = h || box[3];
  }
  return { w: w || 0, h: h || 0 };
}

function bigSvg(svg: Element): boolean {
  if (svg.parentElement?.closest("svg")) return false;
  const { w, h } = svgSize(svg);
  return w >= SVG_MIN && h >= SVG_MIN;
}

/** `data:image/png;base64,…` → File. 아니면 null. */
function dataUrlFile(src: string, n: number): File | null {
  const match = src.match(/^data:(image\/[\w.+-]+);base64,(.+)$/);
  if (!match) return null;
  try {
    const bytes = Uint8Array.from(atob(match[2]), (c) => c.charCodeAt(0));
    const ext = extOf(match[1]);
    return new File([bytes], `붙여넣은-그림-${n}.${ext}`, { type: match[1] });
  } catch {
    return null;
  }
}

function extOf(mime: string): string {
  return (mime.split("/")[1] ?? "png").replace("jpeg", "jpg").replace("svg+xml", "svg").replace(/[^\w]/g, "") || "png";
}

/** 같은 PC · blob 주소의 그림을 가져와 파일로. 그림이 아니거나 못 가져오면 null */
async function fetchFile(href: string, alt: string): Promise<File | null> {
  try {
    const response = await fetch(href);
    if (!response.ok) return null;
    const blob = await response.blob();
    if (!blob.type.startsWith("image/")) return null;
    // 이 앱의 첨부 이름은 `001-이름.png` — 번호를 떼고 원래 이름으로
    const last = decodeURIComponent(new URL(href, window.location.href).pathname.split("/").pop() ?? "");
    const fromPath = /^blob:/i.test(href) ? "" : last.replace(/^\d{3}-/, "");
    const base = fromPath && /\.\w{2,5}$/.test(fromPath) ? fromPath : `${(alt || "붙여넣은-그림").replace(/[\\/:*?"<>|]/g, " ").slice(0, 40)}.${extOf(blob.type)}`;
    return new File([blob], base, { type: blob.type });
  } catch {
    return null;
  }
}

/** `<svg>` 도형 · 차트 → PNG. 글꼴 · 바깥 그림을 쓰는 svg 는 모양이 조금 다를 수 있다 */
async function svgToPng(svg: Element, n: number): Promise<File | null> {
  const { w, h } = svgSize(svg);
  const clone = svg.cloneNode(true) as Element;
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  if (!clone.getAttribute("width")) clone.setAttribute("width", String(w));
  if (!clone.getAttribute("height")) clone.setAttribute("height", String(h));
  const text = new XMLSerializer().serializeToString(clone);
  const url = URL.createObjectURL(new Blob([text], { type: "image/svg+xml" }));
  try {
    const image = await new Promise<HTMLImageElement>((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error("svg"));
      img.src = url;
    });
    const scale = 2; // 선명하게
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(w * scale);
    canvas.height = Math.round(h * scale);
    const context = canvas.getContext("2d");
    if (!context) return null;
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
    return blob ? new File([blob], `붙여넣은-도형-${n}.png`, { type: "image/png" }) : null;
  } catch {
    return null;
  } finally {
    URL.revokeObjectURL(url);
  }
}

/**
 * 붙여넣기 점검 (TODO 225) — 클립보드에 **무엇이 어떤 모양으로** 왔는지만 센다. 내용(글 · 주소 전체)은 보이지 않는다.
 * 코파일럿처럼 이 PC 에서 시험할 수 없는 도구의 붙여넣기를 사용자가 이 요약으로 알려 준다.
 */
export function describeClipboard(data: DataTransfer): string[] {
  const lines: string[] = [];
  const html = data.getData("text/html");
  const plain = data.getData("text/plain");
  const files = Array.from(data.files);
  lines.push(`형식: ${Array.from(data.types).join(", ") || "(없음)"}`);
  lines.push(`파일: ${files.length}개${files.length ? ` (${files.map((file) => file.type || "형식 모름").join(", ")})` : ""}`);
  lines.push(`글자: ${plain.length.toLocaleString("ko-KR")}자${countMarkdownImages(plain)}`);
  if (!html) {
    lines.push("HTML: 없음 — 글자(마크다운)로만 왔습니다");
  } else {
    const doc = new DOMParser().parseFromString(html, "text/html");
    const imgs = Array.from(doc.querySelectorAll("img"));
    const kinds = { here: 0, data: 0, blob: 0, outside: 0, none: 0 };
    const hosts = new Set<string>();
    for (const img of imgs) {
      const src = img.getAttribute("src") || firstSrcset(img.getAttribute("srcset")) || img.getAttribute("data-src") || "";
      if (!src) kinds.none += 1;
      else if (/^data:/i.test(src)) kinds.data += 1;
      else if (/^blob:/i.test(src)) kinds.blob += 1;
      else {
        try {
          const url = new URL(src, window.location.href);
          if (url.origin === window.location.origin) kinds.here += 1;
          else {
            kinds.outside += 1;
            hosts.add(url.hostname);
          }
        } catch {
          kinds.none += 1;
        }
      }
    }
    const svgs = Array.from(doc.querySelectorAll("svg")).filter((svg) => !svg.parentElement?.closest("svg"));
    const big = svgs.filter((svg) => bigSvg(svg)).length;
    const inButton = Array.from(doc.querySelectorAll("button img, button svg, button picture")).length;
    const inCell = Array.from(doc.querySelectorAll("td img, th img, td svg, th svg")).length;
    const backgrounds = Array.from(doc.querySelectorAll<HTMLElement>("[style]")).filter((el) => backgroundUrl(el) !== null).length;
    lines.push(`HTML: ${html.length.toLocaleString("ko-KR")}자 · 표 ${doc.querySelectorAll("table").length}개 · 제목 ${doc.querySelectorAll("h1,h2,h3,h4,h5,h6").length}개 · 목록 ${doc.querySelectorAll("ul,ol").length}개`);
    lines.push(`그림(img): ${imgs.length}개 — 이 PC ${kinds.here} · data ${kinds.data} · blob ${kinds.blob} · 바깥 ${kinds.outside}${hosts.size ? ` (${[...hosts].join(", ")})` : ""} · 주소 없음 ${kinds.none}`);
    lines.push(`도형(svg): ${svgs.length}개 (큰 것 ${big}) · 그림판(canvas) ${doc.querySelectorAll("canvas").length}개 · picture ${doc.querySelectorAll("picture").length}개 · 배경 그림 ${backgrounds}개`);
    lines.push(`감싼 그림: 단추 안 ${inButton}개 · 표 칸 안 ${inCell}개`);
    const mixed = Boolean(doc.querySelector("table")) ? !soleTable(doc) : hasMedia(doc);
    lines.push(`이 붙여넣기는: ${mixed ? "글 · 표 · 그림을 통째로 마크다운으로" : doc.querySelector("table") ? "엑셀처럼 표 하나로" : "글자 그대로"} 들어갑니다`);
  }
  return lines;
}

function countMarkdownImages(text: string): string {
  const found = [...text.matchAll(/!\[[^\]]*\]\(\s*<?([^)\s>]+)/g)].map((match) => match[1]);
  if (found.length === 0) return "";
  const hosts = new Set(found.map((src) => { try { return new URL(src, window.location.href).hostname; } catch { return "?"; } }));
  return ` · 마크다운 그림 ${found.length}개 (${[...hosts].join(", ")})`;
}
