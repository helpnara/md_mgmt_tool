import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { Meta, ReportCandidate } from "../types";
import { formatDate } from "../util";
import { projectLink, useAddressBar } from "../nav";
import SortHeader, { type SortState } from "./SortHeader";
import LoadError from "./LoadError";
import StatusBadge from "./StatusBadge";

const PICKS_KEY = "md-mgmt:report-picks";
/** 이만큼 지나면 붉게 — 주간 보고 기준으로 두 주를 넘긴 것. */
const LATE_DAYS = 14;

/** 이번 주 보고 묶음. 월요일에 고른 과제를 화요일 보고까지 들고 간다. */
function loadPicks(): string[] {
  try {
    return JSON.parse(localStorage.getItem(PICKS_KEY) ?? "[]");
  } catch {
    return [];
  }
}

interface Props {
  meta: Meta;
  /** 주소에 실려 온 조건 (보고 예정일 · 보류·완료 포함 여부). */
  query: string;
}

export default function ReportCandidates({ meta, query }: Props) {
  const initial = new URLSearchParams(query);
  const [items, setItems] = useState<ReportCandidate[]>([]);
  const [reportDate, setReportDate] = useState(() => initial.get("date") ?? "");
  const [includeInactive, setIncludeInactive] = useState(() => initial.get("all") === "1");
  // 거르기 (TODO 49). 과제 화면의 일곱 개를 다 세우지 않는다 — 이 화면의 물음은
  // "이번 주에 무엇을 보고할까" 하나라, 상태·속성·담당이면 충분하다.
  const [status, setStatus] = useState(() => initial.get("status") ?? "");
  const [type, setType] = useState(() => initial.get("type") ?? "");
  const [owner, setOwner] = useState(() => initial.get("owner") ?? "");
  // 정렬 (TODO 57). 비어 있으면 기본 순서 — 보고 이력 없음 먼저, 그다음 오래된 순.
  const [sort, setSort] = useState(() => initial.get("sort") ?? "");
  const [order, setOrder] = useState(() => initial.get("order") ?? "");
  const [picks, setPicks] = useState<string[]>(loadPicks);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .reportCandidates({ includeInactive, status, type, owner, sort, order })
      .then((data) => {
        setItems(data.items);
        setReportDate((prev) => prev || data.default_report_date);
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  }, [includeInactive, status, type, owner, sort, order]);

  useEffect(load, [load]);

  // 고른 조건과 주소를 맞춘다. 과제를 열어 보고 돌아와도 그대로다.
  useAddressBar(
    "reports",
    { date: reportDate, all: includeInactive ? "1" : "", status, type, owner, sort, order },
    (params) => {
      setReportDate(params.get("date") ?? "");
      setIncludeInactive(params.get("all") === "1");
      setStatus(params.get("status") ?? "");
      setType(params.get("type") ?? "");
      setOwner(params.get("owner") ?? "");
      setSort(params.get("sort") ?? "");
      setOrder(params.get("order") ?? "");
    },
  );

  const sortState: SortState | null = sort ? { key: sort, order: (order || "asc") as "asc" | "desc" } : null;
  const onSort = (next: SortState) => {
    setSort(next.key);
    setOrder(next.order);
  };
  const filtered = Boolean(status || type || owner);

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
      window.location.hash = projectLink(projectId, { report: report.id });
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
            한 번도 보고하지 않은 과제가 맨 위, 그다음은 마지막 보고가 오래된 것부터입니다.
            열 이름을 누르면 그 열로 정렬합니다.
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

      <div className="toolbar">
        <div className="filters">
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">상태 전체</option>
            {meta.statuses.map((item) => (
              <option key={item.key} value={item.key}>
                {item.label}
              </option>
            ))}
          </select>
          <select value={type} onChange={(event) => setType(event.target.value)}>
            <option value="">속성 전체</option>
            <option value="none">미지정</option>
            {meta.types.map((item) => (
              <option key={item.key} value={item.key}>
                {item.label}
              </option>
            ))}
          </select>
          <select value={owner} onChange={(event) => setOwner(event.target.value)}>
            <option value="">담당자 전체</option>
            <option value="none">미지정</option>
            {meta.owners.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          {filtered && (
            <button
              className="ghost small"
              onClick={() => {
                setStatus("");
                setType("");
                setOwner("");
              }}
            >
              조건 지우기
            </button>
          )}
        </div>
        <div className="toolbar-actions sort-reset">
          {/* 열 머리글을 세 번 돌려 해제하는 방식은 세 번째를 못 찾는다. 길을 따로 낸다. */}
          {sort ? (
            <button
              className="ghost small"
              onClick={() => {
                setSort("");
                setOrder("");
              }}
            >
              기본 순서로
            </button>
          ) : (
            <span className="sort-note">기본 순서 · 보고 이력 없음 → 오래된 보고 순</span>
          )}
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
                <a href={projectLink(item.id)}>{item.title}</a>
                <button className="ghost small" disabled={busy} onClick={() => makeDraft(item.id)}>
                  보고 초안 만들기
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {error && <LoadError message={error} onRetry={load} />}

      <table className="grid">
        <thead>
          <tr>
            <th className="pick-col">담기</th>
            <SortHeader sortKey="title" current={sortState} onSort={onSort}>과제</SortHeader>
            <SortHeader sortKey="status" current={sortState} onSort={onSort}>상태</SortHeader>
            <SortHeader sortKey="last_reported_at" current={sortState} onSort={onSort}>
              마지막 보고
            </SortHeader>
            <SortHeader sortKey="audience" current={sortState} onSort={onSort}>보고처</SortHeader>
            <SortHeader sortKey="last_reported_at" current={sortState} onSort={onSort}>
              보고 경과
            </SortHeader>
            <SortHeader sortKey="unreported" current={sortState} onSort={onSort} first="desc">
              미보고
            </SortHeader>
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
                <a className="plain-link" href={projectLink(item.id)}>
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
                      href={projectLink(item.id, { report: item.last_report_id })}
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
                  <span className={item.days_since_report >= LATE_DAYS ? "due due-danger" : "due"}>
                    D+{item.days_since_report}
                  </span>
                )}
              </td>
              <td>{item.unreported_entries}건</td>
              <td>
                <button className="ghost small" disabled={busy} onClick={() => makeDraft(item.id)}>
                  보고 초안
                </button>
              </td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td colSpan={8} className="empty">
                보고 후보가 없습니다.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </section>
  );
}
