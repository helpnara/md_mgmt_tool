import MarkdownIt from "markdown-it";

const renderer = new MarkdownIt({ html: false, linkify: true, breaks: true });

export function renderMarkdown(text: string): string {
  return renderer.render(text ?? "");
}
