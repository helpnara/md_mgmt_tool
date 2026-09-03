import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { Meta, ReportCandidate } from "../types";
import { formatDate } from "../util";
import StatusBadge from "./StatusBadge";

const PICKS_KEY = "md-mgmt:report-picks";

/** 이번 주 보고 묶음. 월요일에 고른 과제를 화요일 보고까지 들고 간다. */
function loadPicks(): string[] {
  try {
    return JSON.parse(localStorage.getItem(PICKS_KEY) ?? "[]");
  } catch {
    return [];
  }
}

export default function ReportCandidates({ meta }: { meta: Meta }) {
  const [items, setItems] = useState<ReportCandidate[]>([]);
  const [cycleDays, setCycleDays] = useState(7);
  const [reportDate, setReportDate] = useState("");
  const [includeInactive, setIncludeInactive] = useState(false);
  const [picks, setPicks] = useState<string[]>(loadPicks);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .reportCandidates(includeInactive)
      .then((data) => {
        setItems(data.items);
        setCycleDays(data.cycle_days);
        setReportDate((prev) => prev || data.default_report_date);
      })
      .catch((err: Error) => setError(err.message));
  }, [includeInactive]);

  useEffect(load, [load]);

  function togglePick(id: string) {
    setPicks((prev) => {
      const next = prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id];
      localStorage.setItem(PICKS_KEY, JSON.stringify(next));
      return next;
    });
  }

  async function makeDraft(projectId: string) {
    setBusy(true);
    setError(null);
    try {
      const report = await api.createDraft(projectId, reportDate);
      window.location.hash = `#/projects/${projectId}?report=${report.id}`;
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const picked = items.filter((item) => picks.includes(item.id));

  return (
    <section className="candidates">
      <div className="card-head page-head">
        <div>
          <h1>보고 대상 후보</h1>
          <p className="hint">
            기준 주기 {cycleDays}일 · 점수 = 보고 후 경과일 ÷ {cycleDays} + 미보고 건수 × 0.5
          </p>
        </div>
        <div className="candidate-controls">
          <label>
            보고 예정일
            <input type="date" value={reportDate} onChange={(event) => setReportDate(event.target.value)} />
          </label>
          <label className="toggle">
            <input
              type="checkbox"
              checked={includeInactive}
              onChange={(event) => setIncludeInactive(event.target.checked)}
            />
            보류·완료도 보기
          </label>
        </div>
      </div>

      {picks.length > 0 && (
        <div className="card picked">
          <div className="card-head">
            <h2>이번 주 보고 묶음 ({picked.length})</h2>
            <button
              className="ghost"
              onClick={() => {
                setPicks([]);
                localStorage.removeItem(PICKS_KEY);
              }}
            >
              묶음 비우기
            </button>
          </div>
          <ul className="picked-list">
            {picked.map((item) => (
              <li key={item.id}>
                <a href={`#/projects/${item.id}`}>{item.title}</a>
                <button className="ghost small" disabled={busy} onClick={() => makeDraft(item.id)}>
                  보고 초안 만들기
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {error && <p className="form-error">{error}</p>}

      <table className="grid">
        <thead>
          <tr>
            <th className="pick-col">담기</th>
            <th>과제</th>
            <th>상태</th>
            <th>마지막 보고</th>
            <th>보고처</th>
            <th>보고 경과</th>
            <th>미보고</th>
            <th>점수</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id} className={picks.includes(item.id) ? "picked-row" : undefined}>
              <td className="pick-col">
                <input
                  type="checkbox"
                  checked={picks.includes(item.id)}
                  onChange={() => togglePick(item.id)}
                  aria-label={`${item.title} 담기`}
                />
              </td>
              <td>
                <a className="plain-link" href={`#/projects/${item.id}`}>
                  <span className="project-id">{item.id}</span>
                  <span className="project-title">{item.title}</span>
                </a>
              </td>
              <td>
                <StatusBadge status={item.status} meta={meta} />
              </td>
              <td>
                {item.never_reported ? (
                  <span className="never">보고 이력 없음</span>
                ) : (
                  formatDate(item.last_reported_at)
                )}
              </td>
              <td>
                {/* 같은 날짜라도 팀 주간회의와 전사 보고는 수준이 다르다.
                    누른 곳에서 그때 무엇을 보고했는지 바로 열어 볼 수 있게 한다. */}
                {item.last_report_audience ? (
                  item.last_report_id ? (
                    <a
                      className="plain-link audience-link"
                      href={`#/projects/${item.id}?report=${item.last_report_id}`}
                      title="그때 보고한 내용 열기"
                    >
                      {item.last_report_audience}
                    </a>
                  ) : (
                    item.last_report_audience
                  )
                ) : item.never_reported ? (
                  <span className="muted">—</span>
                ) : (
                  <span className="muted" title="보고 문서에 피보고자가 적혀 있지 않습니다.">
                    미기재
                  </span>
                )}
              </td>
              <td>
                {item.days_since_report === null ? (
                  "—"
                ) : (
                  <span className={item.days_since_report >= cycleDays * 2 ? "due due-danger" : "due"}>
                    D+{item.days_since_report}
                  </span>
                )}
              </td>
              <td>{item.unreported_entries}건</td>
              <td>
                <strong>{item.score.toFixed(1)}</strong>
              </td>
              <td>
                <button className="ghost small" disabled={busy} onClick={() => makeDraft(item.id)}>
                  보고 초안
                </button>
              </td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td colSpan={9} className="empty">
                보고 후보가 없습니다.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </section>
  );
}
