import { useEffect, useState } from "react";
import { api } from "../api";
import type { Meta } from "../types";
import { useEditedUnsaved } from "../util";
import { listProblem, numberProblem } from "../inputRules";
import { enterToSave } from "./enterSave";

/** 팀원 면담의 구분 목록 · 면담 주기 (TODO 182). 목록은 한 줄에 하나, 비우면 기본 목록. */
export default function MeetingSettingsCard({ meta, onSaved }: { meta: Meta; onSaved: () => void }) {
  const [kinds, setKinds] = useState(meta.meeting_kinds.join("\n"));
  const [cycle, setCycle] = useState(String(meta.meeting_cycle_days));
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // 마지막으로 불러온 값 — 고치다 메뉴를 누르면 묻는다 (TODO 211 ②)
  const [saved, setSaved] = useState(() => ({ kinds: meta.meeting_kinds.join("\n"), cycle: String(meta.meeting_cycle_days) }));
  useEditedUnsaved("settings:meeting", { kinds, cycle }, saved, busy);

  useEffect(() => {
    setKinds(meta.meeting_kinds.join("\n"));
    setCycle(String(meta.meeting_cycle_days));
    setSaved({ kinds: meta.meeting_kinds.join("\n"), cycle: String(meta.meeting_cycle_days) });
  }, [meta.meeting_kinds, meta.meeting_cycle_days]);

  // 칸 옆에서 먼저 (TODO 214 F12 · U4 · U6) — 빈 칸은 0 이 아니다. 구분은 30자 20개(서버는 줄바꿈 · 쉼표로 나눈다)
  const kindsProblem = listProblem(kinds, 20, 30, true);
  const cycleProblem = numberProblem(cycle, { min: 1, max: 999, integer: true });
  const canSave = !busy && !kindsProblem && !cycleProblem;

  async function save() {
    if (!canSave) return;
    setBusy(true);
    setError(null);
    try {
      await api.saveSettings({ meeting_kinds: kinds, meeting_cycle_days: Number(cycle) });
      setSaved({ kinds, cycle });
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
    <div className="card meeting-settings" onKeyDown={enterToSave(() => void save(), canSave)}>
      <h2>팀원 면담</h2>
      <p className="hint">
        팀원역량 화면의 <b>면담 기록</b>에서 고르는 구분과, 면담할 때가 지났다고 볼 날수입니다. 구분은 <b>한 줄에 하나</b> —
        30자 20개까지, 비우면 기본 목록(정기 · 목표 설정 · 중간 점검 · 수시 · 고충)으로 돌아갑니다.
      </p>
      <div className="form-row">
        <label className="grow">
          면담 구분
          <textarea
            value={kinds}
            onChange={(e) => setKinds(e.target.value)}
            rows={5}
            spellCheck={false}
            aria-invalid={kindsProblem ? true : undefined}
          />
          {kindsProblem && <span className="field-error">{kindsProblem}</span>}
        </label>
        <label>
          면담 주기 (일)
          <input
            type="number"
            min="1"
            max="999"
            step="1"
            value={cycle}
            onChange={(e) => setCycle(e.target.value)}
            aria-invalid={cycleProblem ? true : undefined}
          />
          {cycleProblem && <span className="field-error">{cycleProblem}</span>}
          <span className="hint">마지막 면담에서 이 날수가 지나면 "면담에서 먼저 볼 사람" 에 섭니다 · 1~999일</span>
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
