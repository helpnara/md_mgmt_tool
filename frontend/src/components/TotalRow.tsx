import type { ReactNode } from "react";
import { DASH } from "../util";

/**
 * 표 맨 아래 합계 줄 (TODO 157).
 *
 * 표마다 합계 칸을 따로 짜면 언젠가 한 표만 다르게 센다. 그래서 **칸마다 무엇을 적을지만** 받는다 —
 * 더한 값은 글자로, 더할 수 없는 칸(이름·날짜·상태·점수)은 `null` 을 주면 `-` 가 선다.
 *
 * * 더하는 것은 **지금 걸러져 보이는 줄**이다(호출하는 쪽이 그 줄로 더한다).
 * * [표 복사] 에는 넣지 않는다 — 엑셀에서 합계를 다시 더하면 두 배가 된다.
 * * 이름표 칸은 `span` 만큼 칸을 합친다(★·담기 칸이 앞에 있는 표).
 */
export type TotalCell = string | null | { text: string; className?: string; title?: string };

export default function TotalRow({
  label,
  span = 1,
  labelClass,
  cells,
}: {
  label: ReactNode;
  span?: number;
  /** 이름표 칸의 모양 — 과제 × 월 표처럼 첫 칸이 옆으로 붙어 있는 표 */
  labelClass?: string;
  cells: TotalCell[];
}) {
  return (
    <tfoot>
      <tr className="total-row">
        <th scope="row" colSpan={span} className={labelClass}>
          {label}
        </th>
        {cells.map((cell, index) => {
          // 더한 값이 0 이라 `-` 가 된 칸도 "없음" 모양으로 (TODO 158)
          if (cell === null || cell === DASH) {
            return (
              <td key={index} className="total-none">
                {DASH}
              </td>
            );
          }
          if (typeof cell === "string") return <td key={index}>{cell}</td>;
          return (
            <td
              key={index}
              className={[cell.className, cell.text === DASH ? "total-none" : ""].filter(Boolean).join(" ") || undefined}
              title={cell.title}
            >
              {cell.text}
            </td>
          );
        })}
      </tr>
    </tfoot>
  );
}
