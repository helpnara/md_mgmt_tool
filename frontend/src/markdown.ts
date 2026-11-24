import MarkdownIt from "markdown-it";

const renderer = new MarkdownIt({ html: false, linkify: true, breaks: true });

/** 상대 경로(assets/...)를 서버가 서빙하는 절대 경로로 바꾼다. */
function resolveHref(href: string, base?: string): string {
  if (!base) return href;
  if (/^[a-z]+:/i.test(href) || href.startsWith("//") || href.startsWith("/") || href.startsWith("#")) {
    return href;
  }
  return `${base}/${href}`;
}

const renderImage = renderer.renderer.rules.image!;
renderer.renderer.rules.image = (tokens, idx, options, env, self) => {
  const src = tokens[idx].attrGet("src");
  if (src) tokens[idx].attrSet("src", resolveHref(src, env?.base));
  return renderImage(tokens, idx, options, env, self);
};

const renderLink =
  renderer.renderer.rules.link_open ??
  ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options));
renderer.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const href = tokens[idx].attrGet("href");
  if (href) tokens[idx].attrSet("href", resolveHref(href, env?.base));
  // 앱 안 주소(`#/projects/…` — `>>` 과제 연결, 321)는 같은 창에서, 바깥 주소 · 첨부는 새 창에서
  if (!(href ?? "").startsWith("#")) {
    tokens[idx].attrSet("target", "_blank");
    tokens[idx].attrSet("rel", "noreferrer");
  }
  return renderLink(tokens, idx, options, env, self);
};

/**
 * 할 일 체크박스 (TODO 321 2단계) — 목록 항목이 `[ ] ` · `[x] ` 로 시작하면 체크박스로 그린다.
 * `data-task-line` 에 그 항목의 **원문 줄 번호(0 부터)** 를 싣는다 — 누르면 화면이 그 줄의 한 글자만 바꿔 저장한다.
 * 누를 수 있는 것은 부르는 쪽이 `tasks: true` 를 줄 때만(진행일지 · 개요의 읽기 화면). 미리보기 · 다른 곳은 보기만(disabled).
 */
renderer.core.ruler.after("inline", "task_items", (state) => {
  const tokens = state.tokens;
  for (let i = 2; i < tokens.length; i += 1) {
    const inline = tokens[i];
    if (inline.type !== "inline" || tokens[i - 1].type !== "paragraph_open" || tokens[i - 2].type !== "list_item_open") continue;
    const first = inline.children?.[0];
    const hit = first && first.type === "text" ? first.content.match(/^\[([ xX])\]\s/) : null;
    if (!hit || !first) continue;
    const checked = hit[1] !== " ";
    const line = tokens[i - 2].map?.[0] ?? -1;
    first.content = first.content.slice(hit[0].length);
    const box = new state.Token("html_inline", "", 0);
    const enabled = Boolean(state.env?.tasks) && line >= 0;
    box.content = `<input type="checkbox" class="task-box" data-task-line="${line}"${checked ? " checked" : ""}${enabled ? "" : " disabled"} aria-label="할 일 ${checked ? "끝냄" : "남음"}"> `;
    inline.children!.unshift(box);
    tokens[i - 2].attrJoin("class", checked ? "task-item done" : "task-item");
  }
});

// 열이 많은 표는 좁은 칸을 그대로 뚫고 나간다. 표만 가로로 스크롤되게 감싼다.
renderer.renderer.rules.table_open = () => '<div class="table-scroll"><table>';
renderer.renderer.rules.table_close = () => "</table></div>";

/**
 * 표 칸 안의 줄바꿈 `<br>` 만 되살린다 (TODO 148).
 *
 * 본문에 섞인 HTML 은 실행하지 않고 글자로 보인다(`html: false` — 붙여넣은 글에 무엇이 섞여도 안전하게).
 * 그런데 마크다운 표는 한 칸이 한 줄이라 칸 안 줄바꿈을 `<br>` 로 적는 것이 관례이고, 엑셀 표를 붙여넣으면
 * 도구가 직접 그렇게 적는다(137). **속성 없는 `<br>` 한 가지만** 되살리고 나머지는 계속 글자로 둔다.
 * 코드(`…`) 안은 적힌 그대로 둔다.
 */
export function restoreLineBreaks(html: string): string {
  return html
    .split(/(<code[\s\S]*?<\/code>)/)
    .map((part, index) => (index % 2 === 1 ? part : part.replace(/&lt;br\s*\/?&gt;/gi, "<br>")))
    .join("");
}

/** base를 주면 첨부 링크가 실제 파일을 가리키도록 렌더링한다. */
export function renderMarkdown(text: string, base?: string, options: { tasks?: boolean } = {}): string {
  return restoreLineBreaks(renderer.render(text ?? "", { base, tasks: options.tasks }));
}

/**
 * 마크다운 안의 상대 링크를 풀 기준 경로.
 * 문서가 놓인 폴더(logs, reports/<날짜> 등)까지 포함해야 ../ 링크가 맞게 풀린다.
 */
export function filesBase(dirName: string | undefined, docDir = ""): string | undefined {
  if (!dirName) return undefined;
  const base = `/files/${encodeURIComponent(dirName)}`;
  return docDir ? `${base}/${docDir.split("/").map(encodeURIComponent).join("/")}` : base;
}
