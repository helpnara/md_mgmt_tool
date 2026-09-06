import { useEffect, useState } from "react";
import { api } from "../api";

/**
 * AI 요약 프롬프트의 앞뒤에 붙일 글 (TODO 71).
 *
 * **이 도구는 AI 를 부르지 않는다.** 인터넷이 차단된 사내 PC 에서 돌기도 하고,
 * 과제 내용을 어디로 보낼지는 사람이 정할 일이기도 하다. 여기서 정한 글은
 * 보고 편집 화면의 [AI 요약 프롬프트]가 만들어 주는 글의 맨 앞과 맨 뒤에 붙는다.
 */
export default function AiPromptCard() {
  const [prefix, setPrefix] = useState("");
  const [suffix, setSuffix] = useState("");
  const [fallback, setFallback] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .settings()
      .then((s) => {
        setPrefix(s.ai_prompt_prefix ?? "");
        setSuffix(s.ai_prompt_suffix ?? "");
      })
      .catch(() => undefined);
    api.settingsDefaults().then((d) => setFallback(d.ai_prompt_prefix)).catch(() => undefined);
  }, []);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const saved = await api.saveSettings({ ai_prompt_prefix: prefix, ai_prompt_suffix: suffix });
      setPrefix(saved.ai_prompt_prefix ?? "");
      setSuffix(saved.ai_prompt_suffix ?? "");
      setNotice("저장했습니다.");
      window.setTimeout(() => setNotice(null), 3000);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card wide">
      <h2>AI 요약 프롬프트</h2>
      <p className="hint">
        보고 편집 화면의 <b>[AI 요약 프롬프트]</b>가 만들어 주는 글의 <b>맨 앞과 맨 뒤</b>에 붙습니다.
        쓰시던 프롬프트를 그대로 넣으면 됩니다. 위를 비우면 기본 지시문을 씁니다.
        <br />
        <b>이 도구는 AI 를 부르지 않습니다.</b> 붙여넣기 좋은 글을 만들어 줄 뿐이고, 어디에 넣을지는
        직접 정하십니다. 밖으로 나가는 것은 없습니다.
      </p>

      <label className="stack-label">
        앞에 붙일 글 — 지시문
        <textarea
          className="template-box"
          value={prefix}
          onChange={(event) => setPrefix(event.target.value)}
          placeholder={fallback}
          spellCheck={false}
        />
      </label>

      <label className="stack-label">
        뒤에 붙일 글 — 없으면 비워 둡니다
        <textarea
          className="template-box short"
          value={suffix}
          onChange={(event) => setSuffix(event.target.value)}
          placeholder="예: 표로 정리해 주세요."
          spellCheck={false}
        />
      </label>

      <p className="hint">
        두 글 사이에는 <b>과제명·과제번호·보고일·포함 기간·피보고자</b>와 진행 내용이 자동으로 들어갑니다.
      </p>
      {notice && <p className="hint notice">{notice}</p>}
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button className="ghost" onClick={() => setPrefix("")}>
          기본 지시문으로
        </button>
        <button disabled={busy} onClick={() => void save()}>
          {busy ? "저장 중…" : "저장"}
        </button>
      </div>
    </div>
  );
}
