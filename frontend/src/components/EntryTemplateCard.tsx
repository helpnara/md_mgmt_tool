import { useEffect, useState } from "react";
import { api } from "../api";
import type { Meta } from "../types";

/**
 * 진행일지 서식.
 *
 * 빈칸에서 시작하면 무엇을 적을지부터 고민하게 된다. 과제 속성마다 적는 것이
 * 다르므로(R&D 는 시험 조건, 투자는 검토 항목) 속성별로 따로 둘 수 있게 한다.
 * 비워 두면 공통 서식을, 공통도 비어 있으면 기본 서식을 쓴다.
 */
export default function EntryTemplateCard({ meta }: { meta: Meta }) {
  const [templates, setTemplates] = useState<Record<string, string>>({});
  const [target, setTarget] = useState(""); // "" = 공통
  const [fallback, setFallback] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.settings().then((s) => setTemplates(s.entry_templates ?? {})).catch(() => undefined);
    api.settingsDefaults().then((d) => setFallback(d.entry_template)).catch(() => undefined);
  }, []);

  const value = templates[target] ?? "";
  const label = target === "" ? "공통" : (meta.types.find((t) => t.key === target)?.label ?? target);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const saved = await api.saveSettings({ entry_templates: templates });
      setTemplates(saved.entry_templates ?? {});
      setNotice("저장했습니다.");
      window.setTimeout(() => setNotice(null), 3000);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <div className="card-head">
        <h2>진행일지 서식</h2>
        <select value={target} onChange={(event) => setTarget(event.target.value)}>
          <option value="">공통</option>
          {meta.types.map((type) => (
            <option key={type.key} value={type.key}>
              {type.label}
              {templates[type.key] ? " ✓" : ""}
            </option>
          ))}
        </select>
      </div>
      <p className="hint">
        [기록 추가]를 누르면 이 내용으로 시작합니다.
        {target === "" ? (
          <> 비워 두면 아래 기본 서식을 씁니다.</>
        ) : (
          <> <b>{label}</b> 과제에만 쓰입니다. 비워 두면 공통 서식을 씁니다.</>
        )}
      </p>
      <textarea
        className="template-box"
        value={value}
        onChange={(event) =>
          setTemplates((prev) => ({ ...prev, [target]: event.target.value }))
        }
        placeholder={fallback}
        spellCheck={false}
      />
      {notice && <p className="hint notice">{notice}</p>}
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button className="ghost" onClick={() => setTemplates((prev) => ({ ...prev, [target]: "" }))}>
          이 서식 비우기
        </button>
        <button disabled={busy} onClick={() => void save()}>
          {busy ? "저장 중…" : "저장"}
        </button>
      </div>
    </div>
  );
}
