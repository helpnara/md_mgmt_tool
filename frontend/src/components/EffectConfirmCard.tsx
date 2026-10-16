import { useEffect, useState } from "react";
import { api } from "../api";
import type { Meta } from "../types";
import { EFFECT_CONFIRM_DEFAULT, numberProblem } from "../inputRules";
import { useEditedUnsaved } from "../util";
import { enterToSave } from "./enterSave";

/** 서버가 받는 상한 — 효과 금액 상한(100만 억원/년)과 같다 */
const LIMIT_MAX = 1_000_000;

/**
 * 효과 금액 확인 기준 (TODO 214 D4).
 *
 * 효과는 **억원/년** 이다. 원 · 백만원 단위로 잘못 적으면 한 과제가 팀 합계를 덮는다. 한 과제에 이 금액을 넘게 적으면
 * 과제 폼 · 승격 창이 저장 전에 "단위를 확인하세요" 하고 묻는다. 0 이면 묻지 않는다.
 */
export default function EffectConfirmCard({ meta, onSaved }: { meta: Meta; onSaved: () => void }) {
  const initial = typeof meta.effect_confirm_over === "number" ? String(meta.effect_confirm_over) : String(EFFECT_CONFIRM_DEFAULT);
  const [value, setValue] = useState(initial);
  const [saved, setSaved] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .settings()
      .then((settings) => {
        const stored = typeof settings.effect_confirm_over === "number" ? settings.effect_confirm_over : null;
        const next = stored === null ? initial : String(stored);
        setValue(next);
        setSaved(next);
      })
      .catch(() => setSaved(initial));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEditedUnsaved("settings:effect-confirm", value.trim(), saved, busy);

  // 빈 칸은 0 이 아니다 (TODO 214 F12) — 0 은 "묻지 않음" 이라 일부러 적어야 한다
  const problem = numberProblem(value, { min: 0, max: LIMIT_MAX });
  const canSave = !busy && !problem && value.trim() !== saved;

  async function save() {
    if (!canSave) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.saveSettings({ effect_confirm_over: Number(value.trim()) });
      const stored = typeof result.effect_confirm_over === "number" ? String(result.effect_confirm_over) : value.trim();
      setValue(stored);
      setSaved(stored);
      setNotice("저장했습니다.");
      window.setTimeout(() => setNotice(null), 3000);
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const number = Number(value);
  return (
    <div className="card effect-confirm-card" onKeyDown={enterToSave(() => void save(), canSave)}>
      <h2>효과 금액 확인</h2>
      <p className="hint">
        효과 금액은 <b>억원/년</b> 입니다. 한 과제에 이 금액을 넘게 적으면 저장하기 전에 <b>&ldquo;단위를 확인하세요&rdquo;</b> 하고 묻습니다 —
        원 · 백만원 단위로 잘못 적은 숫자가 팀 합계를 덮지 않게.
      </p>
      <div className="form-row">
        <label>
          효과 금액 확인 기준 (억원/년, 0 = 묻지 않음)
          <input
            type="number"
            min={0}
            max={LIMIT_MAX}
            step="any"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            aria-invalid={problem ? true : undefined}
          />
          {problem ? (
            <span className="field-error">{problem}</span>
          ) : (
            <span className="hint">
              {number === 0 ? "묻지 않습니다." : `한 과제에 ${number}억원/년을 넘으면 묻습니다.`} 기본 {EFFECT_CONFIRM_DEFAULT}
            </span>
          )}
        </label>
      </div>
      {notice && <p className="hint notice">{notice}</p>}
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button disabled={!canSave} onClick={() => void save()}>
          {busy ? "저장 중…" : "저장"}
        </button>
      </div>
    </div>
  );
}
