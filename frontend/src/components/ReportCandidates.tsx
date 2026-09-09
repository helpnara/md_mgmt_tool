import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { Meta, OpenDraft, ReportCandidate } from "../types";
import { formatDate } from "../util";
import { projectLink, useAddressBar } from "../nav";
import SortHeader, { type SortState } from "./SortHeader";
import LoadError from "./LoadError";
import StatusBadge from "./StatusBadge";
import CopyTableButton from "./CopyTableButton";

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
  // 확정을 기다리는 초안 (TODO 91). 후보를 고르는 일보다 **먼저 끝내야 하는 일**이라
  // 화면 맨 위에 세운다. 배너에서 "초안 N건 확정하기" 로 오면 여기에 닿는다.
  const [drafts, setDrafts] = useState<OpenDraft[]>([]);
  /** 서버가 정한 다음 보고일. 주소에 날짜가 없을 때 되돌아갈 값이다. */
  const [defaultDate, setDefaultDate] = useState("");
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
        setDrafts(data.drafts ?? []);
        setDefaultDate(data.default_report_date);
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
      // 주소에 날짜가 없으면 빈칸이 아니라 기본 보고일이다 (TODO 103-D). `?date=` 가 붙은
      // 채로 즐겨찾기의 `#/reports` 를 다시 열면 칸이 비어 보이던 것.
      setReportDate(params.get("date") || defaultDate);
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
          {/* 이번 주 보고 대상 표를 회의 안건으로 (TODO 108) */}
          <CopyTableButton
            headers={["번호", "과제", "상태", "담당자", "마지막 보고", "피보고자", "경과일", "미보고 기록", "최근 기록"]}
            rows={() =>
              items.map((item) => [
                item.id,
                item.title,
                meta.statuses.find((status) => status.key === item.status)?.label ?? item.status,
                item.owners.join(", "),
                item.last_reported_at ?? (item.never_reported ? "없음" : ""),
                item.last_report_audience ?? "",
                item.not_started ? "" : item.days_since_report ?? "",
                item.unreported_entries,
                item.latest_entry_date ?? "",
              ])
            }
          />
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

      {/* ── 확정을 기다리는 초안 ──────────────────────────────────────
          후보를 고르기 전에 끝내야 하는 일이라 맨 위다 (TODO 91). */}
      {drafts.length > 0 && (
        <div className="card drafts-waiting">
          <div className="card-head">
            <h2>확정을 기다리는 초안 ({drafts.length})</h2>
            {/* 날짜를 가리지 않는다 (TODO 103-A) — 지난주에 쓰다 만 것도 여기 선다. */}
            <span className="hint">오래된 것부터 · 날짜를 가리지 않습니다</span>
          </div>
          <ul className="picked-list">
            {drafts.map((draft) => (
              <li key={draft.id}>
                {/* 제목은 과제로, 단추는 초안으로 — 묶음 카드와 같은 짜임이다.
                    확정하기 전에 과제를 한 번 훑어보는 길을 막지 않는다. */}
                <a href={projectLink(draft.project_id)}>{draft.project_title}</a>
                {draft.report_date && (
                  <span className={draft.overdue_days ? "due due-danger" : "due"}>
                    {draft.report_date}
                    {draft.overdue_days ? ` · D+${draft.overdue_days}` : ""}
                  </span>
                )}
                {draft.audience && <span className="hint">{draft.audience}</span>}
                <a
                  className="linkish-button"
                  href={projectLink(draft.project_id, { report: draft.id })}
                >
                  초안 열기
                </a>
              </li>
            ))}
          </ul>
          <p className="hint">
            정리를 마치고 <b>[보고 확정]</b>을 누르면 그 시점 문서가 그대로 굳고, 그 과제의
            미보고 분량이 0으로 돌아갑니다.
          </p>
        </div>
      )}

      {/* ── 이번 주 보고 묶음 ────────────────────────────────────────
          **비어 있을 때도 세운다** (TODO 91). 담긴 것이 없으면 카드가 통째로 사라져,
          무엇을 해야 하는지 알려 줄 자리도 함께 사라졌다. 빈 상태가 곧 안내다. */}
      <div className="card picked">
        <div className="card-head">
          <h2>이번 주 보고 묶음 ({picked.length})</h2>
          {picks.length > 0 && (
            <button
              className="ghost"
              onClick={() => {
                setPicks([]);
                localStorage.removeItem(PICKS_KEY);
              }}
            >
              묶음 비우기
            </button>
          )}
        </div>
        {picked.length === 0 ? (
          <p className="hint">
            이번 주 보고할 대상을 아래 목록에서 골라 <b>[담기]</b>에 체크해 주세요.
            담아 두면 보고하는 날 이 자리에서 <b>초안을 바로 만들 수 있습니다.</b>
          </p>
        ) : (
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
        )}
      </div>

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
                {item.not_started ? (
                  /* 착수일이 아직 오지 않았다. `D+-27` 로는 읽히지 않는다 (TODO 70). */
                  <span className="muted" title="착수일이 아직 오지 않았습니다.">
                    착수 전
                  </span>
                ) : item.days_since_report === null ? (
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
