import { useEffect, useState } from "react";
import { Paperclip } from "lucide-react";
import { api } from "../api";
import CardIntro from "./CardIntro";
import IconTitle from "./IconTitle";

/**
 * 첨부 최대 크기 (TODO 335). 넘는 파일은 올리기 전에 거절한다 — 수 GB 파일 하나로 서버 PC 의 저장 공간이
 * 차서 멈추지 않게. 올리는 동안의 임시 파일은 데이터 폴더가 있는 드라이브에 쓴다(전: 시스템 임시 폴더 C:).
 */
export default function AttachLimitCard() {
  const [value, setValue] = useState("");
  const [saved, setSaved] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.settings().then((settings) => {
      const mb = String(settings.attach_max_mb ?? 2048);
      setValue(mb);
      setSaved(mb);
    }).catch((err: Error) => setError(err.message));
  }, []);

  const number = Number(value);
  const problem = value && (!Number.isInteger(number) || number < 1 || number > 102400)
    ? "1 ~ 102400 사이의 MB 로 적어 주세요." : null;

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.saveSettings({ attach_max_mb: number });
      setSaved(value);
      setNotice("저장했습니다. 다음에 올리는 첨부부터 이 크기를 봅니다.");
      window.setTimeout(() => setNotice(null), 4000);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card" data-testid="attach-limit-card">
      <IconTitle icon={Paperclip}>첨부 최대 크기</IconTitle>
      <CardIntro id="attach-limit">
        첨부 <b>한 개</b>의 최대 크기입니다. 넘는 파일은 올리기 전에 거절합니다 — 큰 파일 하나로 서버 PC 의 저장 공간이
        차서 멈추지 않게. 올리는 동안의 임시 파일은 데이터 폴더가 있는 드라이브에 씁니다.
      </CardIntro>
      <div className="form-row">
        <label>
          최대 크기(MB)
          <input inputMode="numeric" value={value} onChange={(e) => setValue(e.target.value.trim())} aria-invalid={problem ? true : undefined} style={{ width: 120 }} />
        </label>
        <p className="hint effect-hint">{number >= 1024 ? `= ${(number / 1024).toFixed(number % 1024 ? 1 : 0)}GB` : ""} · 기본 2048MB(2GB)</p>
      </div>
      {problem && <p className="field-error">{problem}</p>}
      {notice && <p className="hint notice">{notice}</p>}
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button disabled={busy || !value || Boolean(problem) || value === saved} onClick={() => void save()}>
          {busy ? "저장 중…" : "저장"}
        </button>
      </div>
    </div>
  );
}
