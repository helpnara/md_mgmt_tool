import { useState } from "react";
import { copyTsv } from "../tsv";

/**
 * [표 복사] 단추 (TODO 108). 눌러서 클립보드에 넣고, 잠깐 "복사됨" 으로 바뀐다.
 * 줄은 누를 때 만든다 — 화면이 걸러 둔 그 목록이 그대로 나가야 한다.
 */
export default function CopyTableButton({
  headers,
  rows,
  label = "표 복사",
  title = "지금 보이는 줄을 탭 구분으로 복사합니다. 엑셀에 붙여넣으면 표가 됩니다.",
}: {
  headers: string[];
  rows: () => (string | number | null | undefined)[][];
  label?: string;
  title?: string;
}) {
  const [state, setState] = useState<"idle" | "done" | "fail">("idle");
  return (
    <button
      type="button"
      className={`ghost small copy-table${state === "done" ? " on" : ""}`}
      title={title}
      onClick={async () => {
        try {
          await copyTsv(headers, rows());
          setState("done");
        } catch {
          setState("fail");
        }
        window.setTimeout(() => setState("idle"), 1800);
      }}
    >
      {state === "done" ? "복사됨 ✓" : state === "fail" ? "복사 실패" : label}
    </button>
  );
}
