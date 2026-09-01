/**
 * 마크다운을 엑셀 셀에 붙여넣기 좋은 평문으로 바꾼다.
 * 보고서는 셀 한 칸에 여러 줄로 넣으므로 줄바꿈을 살리는 것이 핵심이다.
 */
export function toPlainText(markdown: string): string {
  const lines: string[] = [];
  let inCodeFence = false;

  for (const raw of (markdown ?? "").split("\n")) {
    let line = raw;

    if (/^\s*```/.test(line)) {
      inCodeFence = !inCodeFence;
      continue;
    }
    if (inCodeFence) {
      lines.push(line);
      continue;
    }

    // 표 구분선(| --- | --- |)은 버리고, 나머지 표 행은 셀 구분만 남긴다.
    if (/^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(line) && line.includes("-")) continue;
    if (/^\s*\|.*\|\s*$/.test(line)) {
      line = line.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim()).join(" | ");
    }

    line = line
      .replace(/^\s*#{1,6}\s*/, "")           // 제목 기호 제거
      .replace(/^\s*>\s?/, "")                // 인용 기호 제거
      .replace(/!\[([^\]]*)\]\([^)]*\)/g, (_match, alt) => `[이미지: ${alt || "첨부"}]`)
      .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1") // 링크는 글자만
      .replace(/\*\*([^*]+)\*\*/g, "$1")
      .replace(/(^|[^*])\*([^*]+)\*/g, "$1$2")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/^\s*[-*]\s+/, "- ")            // 목록 기호는 통일해 유지
      .replace(/\s+$/, "");

    lines.push(line);
  }

  return lines
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/**
 * 엑셀 "한 칸"에 줄바꿈을 유지한 채 붙여넣기.
 * 엑셀은 클립보드의 HTML 플레이버를 우선 인식하므로 표 한 칸으로 감싸 보낸다.
 */
export async function copyAsExcelCell(text: string): Promise<void> {
  const html = `<table><tr><td>${escapeHtml(text).replace(/\n/g, "<br>")}</td></tr></table>`;
  // RFC4180 규칙: 전체를 큰따옴표로 감싸면 내부 줄바꿈도 한 셀로 들어간다.
  const plain = `"${text.replace(/"/g, '""')}"`;

  if (typeof ClipboardItem !== "undefined" && navigator.clipboard?.write) {
    await navigator.clipboard.write([
      new ClipboardItem({
        "text/html": new Blob([html], { type: "text/html" }),
        "text/plain": new Blob([plain], { type: "text/plain" }),
      }),
    ]);
    return;
  }
  await navigator.clipboard.writeText(plain);
}

/** 메모장·메일 등 어디에나 붙여넣을 수 있는 그대로의 평문 복사. */
export async function copyAsPlainText(text: string): Promise<void> {
  await navigator.clipboard.writeText(text);
}
