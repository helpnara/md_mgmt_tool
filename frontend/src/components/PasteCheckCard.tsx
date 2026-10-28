import { useState } from "react";
import { copyText } from "../clipboard";
import { describeClipboard } from "../htmlPaste";

/**
 * 붙여넣기 점검 (TODO 225) — 이 칸에 붙여 넣으면 클립보드에 **무엇이 어떤 모양으로** 왔는지만 보여 준다.
 * 내용은 보이지도 남지도 않는다. 코파일럿처럼 여기서 시험할 수 없는 도구에서 그림이 안 들어올 때, 이 요약을 알려 주면 원인을 가를 수 있다.
 */
export default function PasteCheckCard() {
  const [lines, setLines] = useState<string[] | null>(null);
  const [copied, setCopied] = useState(false);
  return (
    <div className="card paste-check">
      <h2>붙여넣기 점검</h2>
      <p className="hint">
        AI 답 · 문서를 붙였는데 그림이나 표가 빠질 때 — 같은 것을 아래 칸에 붙여 넣으면 <b>무엇이 어떤 모양으로 왔는지</b>만 셉니다.
        내용은 보이지도 저장되지도 않습니다.
      </p>
      <textarea
        className="paste-check-area"
        rows={2}
        // 늘 빈 칸 — 붙인 것은 세기만 하고 담지 않는다(읽기 전용 칸은 브라우저에 따라 붙여넣기가 오지 않는다)
        value=""
        onChange={() => undefined}
        placeholder="여기에 Ctrl+V"
        onPaste={(event) => {
          event.preventDefault();
          setLines(describeClipboard(event.clipboardData));
          setCopied(false);
        }}
      />
      {lines && (
        <>
          <ul className="paste-check-result">
            {lines.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <button
            className="ghost small"
            onClick={async () => setCopied(await copyText(lines.join("\n")))}
          >
            {copied ? "복사했습니다 ✓" : "요약 복사"}
          </button>
        </>
      )}
    </div>
  );
}
