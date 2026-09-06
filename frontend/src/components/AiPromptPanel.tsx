import { useEffect, useState } from "react";
import { api } from "../api";
import { copyAsPlainText } from "../plaintext";

/**
 * AI 에게 넘길 글을 **먼저 보여 주고** 복사하게 한다 (TODO 71).
 *
 * 곧바로 클립보드에 넣지 않는 이유는 하나다 — 무엇이 담기는지 모르고 누르게 하면 안 된다.
 * 사내 자료를 다른 도구에 붙여넣는 일이므로, 무엇을 옮기는지는 눈으로 확인하고 결정해야 한다.
 */
export default function AiPromptPanel({ reportId }: { reportId: number }) {
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setText(null);
    setError(null);
    api
      .aiPrompt(reportId)
      .then((data) => setText(data.text))
      .catch((err: Error) => setError(err.message));
  }, [reportId]);

  async function copy() {
    if (!text) return;
    try {
      await copyAsPlainText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 3000);
    } catch {
      setError("복사하지 못했습니다. 아래 글을 직접 선택해 복사하세요.");
    }
  }

  return (
    <div className="ai-prompt">
      <div className="ai-prompt-head">
        <strong>AI 요약 프롬프트</strong>
        <span className="hint">
          아래 글을 복사해 <b>사내에서 승인된 AI 도구</b>에 붙여넣으세요. 이 도구는 AI 를 부르지 않습니다.
        </span>
        <button className="ghost small" disabled={!text} onClick={() => void copy()}>
          {copied ? "복사했습니다" : "복사"}
        </button>
      </div>
      {error && <p className="form-error">{error}</p>}
      {text === null && !error ? (
        <p className="hint">만드는 중…</p>
      ) : (
        <textarea className="ai-prompt-box" value={text ?? ""} readOnly spellCheck={false} />
      )}
      <p className="hint">
        앞뒤에 붙는 글은 <a href="#/settings">설정 → AI 요약 프롬프트</a>에서 바꿉니다.
      </p>
    </div>
  );
}
