import { useEffect, useState } from "react";
import { api } from "../api";

/** 0=월 … 6=일. 파이썬 `date.weekday()` 와 같은 순서로 맞춘다. */
const DAYS = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"];

/**
 * 주간 보고 요일.
 *
 * 지금까지는 화요일이 코드에 굳어 있었다. 팀마다 다른 값이라 설정으로 뺀다.
 *
 * 이 값 하나가 **네 곳을 함께 움직인다** — 보고 예정일, 보고 초안의 기본 날짜,
 * 대시보드 머리글, 그리고 리마인더. 따로 두면 "내일 보고입니다" 안내가
 * 실제 보고 예정일과 어긋난다.
 */
export default function ReportDayCard({ onSaved }: { onSaved: () => void }) {
  const [weekday, setWeekday] = useState(1);
  const [saved, setSaved] = useState(1);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .settings()
      .then((settings) => {
        setWeekday(settings.report_weekday ?? 1);
        setSaved(settings.report_weekday ?? 1);
      })
      .catch(() => undefined);
  }, []);

  /** 고른 요일로 다음 보고일이 언제가 되는지 미리 보여 준다. */
  const nextDate = (() => {
    const today = new Date();
    // getDay() 는 일=0 이라 월=0 기준으로 옮긴다.
    const ahead = (weekday - ((today.getDay() + 6) % 7) + 7) % 7;
    const target = new Date(today.getTime() + ahead * 86400000);
    return new Date(target.getTime() - target.getTimezoneOffset() * 60000)
      .toISOString()
      .slice(0, 10);
  })();

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.saveSettings({ report_weekday: weekday });
      setSaved(weekday);
      setNotice("저장했습니다. 보고 예정일과 알림이 함께 바뀝니다.");
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
      <h2>주간 보고 요일</h2>
      <p className="hint">
        팀에서 <b>주간업무를 보고하는 요일</b>입니다. 보고 예정일, 보고 초안의 기본 날짜,
        그리고 알림이 모두 이 요일을 따라갑니다.
        <br />
        보고 대상을 고르라는 알림은 <b>그 하루 전</b>에 뜹니다.
      </p>
      <div className="form-row">
        <label>
          보고 요일
          <select value={weekday} onChange={(event) => setWeekday(Number(event.target.value))}>
            {DAYS.map((label, index) => (
              <option key={label} value={index}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <p className="hint effect-hint">
          다음 보고 예정일 → <code>{nextDate}</code> ({DAYS[weekday]})
          <br />
          보고 대상 선정 알림 → {DAYS[(weekday + 6) % 7]}
        </p>
      </div>
      {notice && <p className="hint notice">{notice}</p>}
      {error && <p className="form-error">{error}</p>}
      <p className="hint">
        <b>이미 만든 보고의 날짜는 바뀌지 않습니다</b> — 그 날짜는 &ldquo;언제 보고했는가&rdquo;라는
        사실이기 때문입니다.
      </p>
      <div className="form-actions">
        <button disabled={busy || weekday === saved} onClick={() => void save()}>
          {busy ? "저장 중…" : "저장"}
        </button>
      </div>
    </div>
  );
}
