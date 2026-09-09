/**
 * 표를 엑셀에 붙여넣을 수 있게 복사한다 (TODO 108).
 *
 * "과제 현황 표 좀 보내 줘" 를 팀장은 한 달에 몇 번 듣는다. 지금까지는 화면을 보며 엑셀에
 * 다시 쳤다. 여기서는 **지금 걸러진 줄 그대로**를 탭 구분으로 클립보드에 넣는다 —
 * 붙여넣으면 엑셀 표가 된다. 나가는 것은 클립보드뿐이다.
 *
 * 셀 안의 탭·줄바꿈은 공백으로 눌러 한 줄로 만든다. 표 복사의 목적은 "한 줄에 한 과제" 다.
 */
export function toTsv(headers: string[], rows: (string | number | null | undefined)[][]): string {
  const cell = (value: string | number | null | undefined) =>
    String(value ?? "").replace(/[\t\r\n]+/g, " ").trim();
  return [headers, ...rows].map((row) => row.map(cell).join("\t")).join("\n") + "\n";
}

export async function copyTsv(
  headers: string[],
  rows: (string | number | null | undefined)[][],
): Promise<void> {
  await navigator.clipboard.writeText(toTsv(headers, rows));
}
