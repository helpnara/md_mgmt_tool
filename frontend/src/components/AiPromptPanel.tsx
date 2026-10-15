import { useEffect, useState } from "react";
import { api } from "../api";
import { copyAsPlainText } from "../plaintext";
import { COPY_FAILED } from "../clipboard";
import { isReadonly } from "../readonly";

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
    // 공유 주소(비보안 컨텍스트)에서는 폴백으로 넣고, 그래도 안 되면 한국어로 안내한다 (TODO 208)
    if (!(await copyAsPlainText(text))) {
      setError(COPY_FAILED);
      return;
    }
    setError(null);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 3000);
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
        {/* 읽기 전용 공유에서 설정 주소는 막다른 안내 페이지다 — 글자로만 (TODO 208) */}
        앞뒤에 붙는 글은 {isReadonly() ? <b>설정 → AI 요약 프롬프트</b> : <a href="#/settings">설정 → AI 요약 프롬프트</a>}에서
        바꿉니다{isReadonly() && " (서버 PC 에서)"}.
      </p>
    </div>
  );
}
