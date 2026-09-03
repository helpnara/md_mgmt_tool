import { useEffect, useState } from "react";
import { api } from "../api";

/**
 * 보고 초안 서식.
 *
 * 지금까지 `보고 요약 / 특이사항 및 이슈 / 다음 계획` 이 코드에 박혀 있어,
 * 회의체마다 양식이 다르면 매번 손으로 고쳐야 했다.
 */
export default function ReportTemplateCard() {
  const [template, setTemplate] = useState("");
  const [fallback, setFallback] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.settings().then((s) => setTemplate(s.report_template ?? "")).catch(() => undefined);
    api.settingsDefaults().then((d) => setFallback(d.report_template)).catch(() => undefined);
  }, []);

  // {summary} 가 없으면 미보고 진행 내용이 통째로 사라진다. 저장 전에 막는다.
  const missingSummary = template.trim() !== "" && !template.includes("{summary}");

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const saved = await api.saveSettings({ report_template: template });
      setTemplate(saved.report_template ?? "");
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
      <h2>보고 초안 서식</h2>
      <p className="hint">
        [보고 초안 만들기]로 만드는 문서의 뼈대입니다. <code>{"{summary}"}</code> 자리에{" "}
        <b>마지막 보고 이후의 진행일지</b>가 들어갑니다. 비워 두면 기본 서식을 씁니다.
      </p>
      <textarea
        className="template-box"
        value={template}
        onChange={(event) => setTemplate(event.target.value)}
        placeholder={fallback}
        spellCheck={false}
      />
      {missingSummary && (
        <p className="hint warn-text">
          <code>{"{summary}"}</code> 가 없습니다. 이대로 두면 진행 내용이 초안에 들어가지 않아
          기본 서식이 대신 쓰입니다.
        </p>
      )}
      {notice && <p className="hint notice">{notice}</p>}
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button className="ghost" onClick={() => setTemplate("")}>
          기본 서식으로
        </button>
        <button disabled={busy} onClick={() => void save()}>
          {busy ? "저장 중…" : "저장"}
        </button>
      </div>
    </div>
  );
}
