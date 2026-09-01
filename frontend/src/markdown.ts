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
  tokens[idx].attrSet("target", "_blank");
  tokens[idx].attrSet("rel", "noreferrer");
  return renderLink(tokens, idx, options, env, self);
};

/** base를 주면 첨부 링크가 실제 파일을 가리키도록 렌더링한다. */
export function renderMarkdown(text: string, base?: string): string {
  return renderer.render(text ?? "", { base });
}

export function filesBase(dirName: string | undefined): string | undefined {
  return dirName ? `/files/${encodeURIComponent(dirName)}` : undefined;
}
