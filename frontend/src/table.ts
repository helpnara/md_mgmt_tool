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
  const rows = splitRows(text);
  const columns = rows[0].length;
  const head = `| ${rows[0].map(cell).join(" | ")} |`;
  const rule = `|${"---|".repeat(columns)}`;
  const body = rows.slice(1).map((row) => `| ${row.map(cell).join(" | ")} |`);
  return [head, rule, ...body].join("\n");
}

/**
 * 붙여넣기를 가로채 표로 바꾼다. 표가 아니면 아무것도 하지 않는다(기본 동작에 맡긴다).
 * 바꿨으면 true 를 돌려준다.
 */
export function pasteAsTable(
  event: React.ClipboardEvent<HTMLTextAreaElement>,
  onInsert: (text: string) => void,
): boolean {
  const text = event.clipboardData.getData("text/plain");
  if (!text || !looksLikeTable(text)) return false;
  event.preventDefault();
  onInsert(`\n${toMarkdownTable(text)}\n`);
  return true;
}
