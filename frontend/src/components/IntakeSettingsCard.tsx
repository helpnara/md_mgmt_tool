import { useEffect, useState } from "react";
import { api } from "../api";
import type { ClassificationKey, Meta } from "../types";

/**
 * 과제 분류 넷의 목록 · 접수 서식 · 묵힘 기준일 (TODO 136).
 *
 * 분류 목록은 **한 줄에 하나**. 목록에서 뺀 값도 이미 적힌 과제에서는 지우지 않는다 —
 * 입력 칸에 "(목록에 없음)" 으로 남아 보이고, 필요하면 과제마다 고치면 된다.
 * 목록을 통째로 비우면 기본 목록으로 돌아간다(고를 것 없는 칸은 칸이 아니다).
 */
export default function IntakeSettingsCard({ meta, onSaved }: { meta: Meta; onSaved: () => void }) {
  const [lists, setLists] = useState<Record<ClassificationKey, string>>(() => ({
    nature: "",
    category: "",
    delivery: "",
    cost_kind: "",
  }));
  const [template, setTemplate] = useState("");
  const [fallback, setFallback] = useState("");
  const [staleDays, setStaleDays] = useState(String(meta.intake_stale_days));
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLists(
      Object.fromEntries(meta.classifications.map((info) => [info.key, info.items.join("\n")])) as Record<
        ClassificationKey,
        string
      >,
    );
    setStaleDays(String(meta.intake_stale_days));
  }, [meta.classifications, meta.intake_stale_days]);

  useEffect(() => {
    api.settings().then((s) => setTemplate(s.intake_template ?? "")).catch(() => undefined);
    api
      .settingsDefaults()
      .then((d) => setFallback((d as { intake_template?: string }).intake_template ?? ""))
      .catch(() => undefined);
  }, []);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.saveSettings({
        classifications: lists as unknown as Record<string, string[]>,
        intake_template: template,
        intake_stale_days: Number(staleDays),
      });
      onSaved();
      setNotice("저장했습니다.");
      window.setTimeout(() => setNotice(null), 3000);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card wide intake-settings">
      <h2>과제 분류 · 접수</h2>
      <p className="hint">
        스마트과제의 <b>성격 · 분류 · 수행 방식 · 비용구분</b> 목록입니다. <b>한 줄에 하나</b>씩 적습니다. 목록에서
        뺀 값도 이미 적힌 과제에서는 지워지지 않습니다.
      </p>
      <div className="class-lists">
        {meta.classifications.map((info) => (
          <label key={info.key}>
            {info.label}
            <textarea
              value={lists[info.key] ?? ""}
              onChange={(e) => setLists((prev) => ({ ...prev, [info.key]: e.target.value }))}
              rows={6}
              spellCheck={false}
            />
          </label>
        ))}
      </div>
      <div className="form-row">
        <label>
          묵힘 기준 (일)
          <input type="number" min="1" value={staleDays} onChange={(e) => setStaleDays(e.target.value)} />
          <span className="hint">접수 후 이 날수가 지나도 판정이 없으면 홈과 접수 풀에 표시합니다 (보류는 제외)</span>
        </label>
      </div>
      <label>
        접수 본문 서식
        <textarea
          className="template-box"
          value={template}
          onChange={(e) => setTemplate(e.target.value)}
          placeholder={fallback}
          spellCheck={false}
        />
      </label>
      <p className="hint">
        비워 두면 기본 서식을 씁니다. 섹션 제목의 <b>괄호·줄표 앞 이름</b>을 과제 개요와 같게 두면(배경 · 목표 ·
        추진내용 · 효과 산출 근거 · 활용 방안 및 향후 계획) 승격할 때 그 자리로 그대로 넘어갑니다. 예:{" "}
        <code>## 목표 (성과지표)</code>
      </p>
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
