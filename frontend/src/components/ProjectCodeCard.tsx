import { useEffect, useState } from "react";
import { api } from "../api";

/**
 * 과제 번호의 팀·부문 코드.
 *
 * 지금은 `2026-001`. 팀장이 여럿이 되면 번호가 겹친다.
 * 코드를 넣어 두면 이후 만드는 과제가 `2026-소재-001` 이 된다.
 *
 * **이미 만든 과제 번호는 바꾸지 않는다.** 번호는 식별자라 섞여도 되고,
 * 바꾸면 폴더명과 문서 안의 링크가 모두 흔들린다.
 */
export default function ProjectCodeCard({ onSaved }: { onSaved: () => void }) {
  const [code, setCode] = useState("");
  const [saved, setSaved] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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
      window.setTimeout(() => setNotice(null), 4000);
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
        <b>이미 만든 과제 번호는 바뀌지 않습니다</b> — 바꾸면 폴더명과 문서 안의 링크가 흔들립니다.
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
      </div>
    </div>
  );
}
