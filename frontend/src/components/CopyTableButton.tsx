import { useState } from "react";
import { copyTsv } from "../tsv";
import { COPY_FAILED } from "../clipboard";

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
  // 공유 주소(비보안 컨텍스트)에서는 clipboard API 가 없다 — 폴백도 안 되면 "선택해서 Ctrl+C" 를 안내한다 (TODO 208)
  return (
    <button
      type="button"
      className={`ghost small copy-table${state === "done" ? " on" : ""}${state === "fail" ? " fail" : ""}`}
      title={state === "fail" ? COPY_FAILED : title}
      onClick={async () => {
        const ok = await copyTsv(headers, rows());
        setState(ok ? "done" : "fail");
        window.setTimeout(() => setState("idle"), ok ? 1800 : 6000);
      }}
    >
      {state === "done" ? "복사됨 ✓" : state === "fail" ? COPY_FAILED : label}
    </button>
  );
}
