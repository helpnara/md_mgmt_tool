import { useEffect, useState } from "react";
import { api } from "../api";
import type { RenumberPlan } from "../types";

/**
 * 과제 번호의 팀·부문 코드.
 *
 * 지금은 `2026-001`. 팀장이 여럿이 되면 번호가 겹친다.
 * 코드를 넣어 두면 이후 만드는 과제가 `2026-소재-001` 이 된다.
 *
 * 코드를 나중에 정하면 이미 만든 과제(`2026-001`)와 새 과제(`2026-소재-001`)의 형태가 갈린다.
 * 한 목록에 두 형태가 섞이면 번호 체계가 무의미해지므로, **일괄 변경**을 함께 둔다.
 * 되돌리기 어려운 동작이라 반드시 미리보기를 먼저 보여 준다.
 */
export default function ProjectCodeCard({ onSaved }: { onSaved: () => void }) {
  const [code, setCode] = useState("");
  const [saved, setSaved] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [plan, setPlan] = useState<RenumberPlan | null>(null);

  useEffect(() => {
    api
      .settings()
      .then((settings) => {
        setCode(settings.project_code ?? "");
        setSaved(settings.project_code ?? "");
      })
      .catch(() => undefined);
  }, []);

  const year = new Date().getFullYear();
  const preview = code.trim() ? `${year}-${code.trim()}-001` : `${year}-001`;

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const result = await api.saveSettings({ project_code: code.trim() });
      setSaved(result.project_code ?? "");
      setNotice("저장했습니다. 다음에 만드는 과제부터 적용됩니다.");
      setPlan(null);
      window.setTimeout(() => setNotice(null), 4000);
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  /** 파일을 건드리지 않고 무엇이 어떻게 바뀌는지만 먼저 보여 준다. */
  async function loadPlan() {
    setBusy(true);
    setError(null);
    try {
      setPlan(await api.renumberPreview(code.trim()));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function applyPlan() {
    if (!plan) return;
    if (!window.confirm(`과제 ${plan.changes.length}건의 번호를 바꿉니다. 되돌리려면 손으로 폴더를 옮겨야 합니다. 계속할까요?`)) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await api.renumberApply(code.trim());
      setSaved(result.code);
      setPlan(null);
      setNotice(`과제 ${result.changed.length}건의 번호를 바꿨습니다.`);
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h2>과제 번호 체계</h2>
      <p className="hint">
        비워 두면 지금처럼 <code>{year}-001</code> 입니다. 팀·부문 코드를 넣으면{" "}
        <code>{year}-소재-001</code> 처럼 붙습니다. 여러 팀장이 함께 쓰게 될 때 번호가 겹치지 않게
        하는 자리입니다.
        <br />
        저장은 <b>다음에 만드는 과제부터</b> 적용됩니다. 이미 만든 과제까지 같은 형태로 맞추려면
        아래 <b>[기존 과제 번호도 맞추기]</b> 를 쓰세요 — 연도와 일련번호는 그대로 두고 가운데
        코드만 바꿉니다 (<code>2026-001</code> → <code>{year}-소재-001</code>).
      </p>
      <div className="form-row">
        <label>
          팀·부문 코드
          <input
            value={code}
            onChange={(event) => setCode(event.target.value)}
            placeholder="예: 소재 (비워 두어도 됩니다)"
          />
        </label>
        <p className="hint effect-hint">
          다음에 만들 과제 번호 → <code>{preview}</code>
        </p>
      </div>
      {notice && <p className="hint notice">{notice}</p>}
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button disabled={busy || code.trim() === saved} onClick={() => void save()}>
          {busy ? "저장 중…" : "저장"}
        </button>
        <button className="ghost" disabled={busy} onClick={() => void loadPlan()}>
          기존 과제 번호도 맞추기…
        </button>
      </div>

      {plan && (
        <div className="renumber-plan">
          <h3>
            바뀌는 과제 {plan.changes.length}건
            {plan.skipped.length > 0 && (
              <span className="muted"> · 그대로 두는 과제 {plan.skipped.length}건</span>
            )}
          </h3>
          {plan.changes.length === 0 ? (
            <p className="hint">바꿀 과제가 없습니다. 이미 모두 이 형태입니다.</p>
          ) : (
            <>
              <ol className="renumber-list">
                {plan.changes.map((item) => (
                  <li key={item.id}>
                    <code className="from">{item.id}</code>
                    <span aria-hidden="true">→</span>
                    <code className="to">{item.new_id}</code>
                    <span className="renumber-title">{item.title}</span>
                    {item.renumbered && (
                      <span className="warn-tag" title="같은 번호가 이미 쓰이고 있어 뒤 번호로 밀었습니다.">
                        번호 밀림
                      </span>
                    )}
                  </li>
                ))}
              </ol>
              <p className="hint">
                과제 폴더 이름과 문서 안의 <code>id</code> 를 함께 바꾸고 색인을 다시 만듭니다.
                진행일지·보고·첨부는 폴더째 따라갑니다.
                <br />
                <b>바꾸기 전에 vault 폴더를 한 번 복사해 두시길 권합니다.</b> 엑셀·탐색기에서
                과제 폴더를 열어 두었다면 먼저 닫아 주세요 — 열려 있으면 옮기지 못합니다.
              </p>
            </>
          )}
          <div className="form-actions">
            <button className="ghost" onClick={() => setPlan(null)}>
              취소
            </button>
            {plan.changes.length > 0 && (
              <button disabled={busy} onClick={() => void applyPlan()}>
                {busy ? "바꾸는 중…" : `${plan.changes.length}건 바꾸기`}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
