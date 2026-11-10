import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { projectLink, backTarget, screenLink } from "../nav";
import type { Meta, SearchResults as Results } from "../types";
import { formatBytes } from "../upload";
import StatusBadge from "./StatusBadge";
import StageBand from "./StageBand";
import LoadError from "./LoadError";

/** 검색어와 일치하는 부분을 강조한다 — 낱말이 여럿이면 모두(TODO 254). */
function Highlight({ text, query }: { text: string; query: string | string[] }) {
  const words = (Array.isArray(query) ? query : [query]).filter(Boolean).sort((a, b) => b.length - a.length);
  if (words.length === 0 || !text) return <>{text}</>;
  const escape = (w: string) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = new RegExp(`(${words.map(escape).join("|")})`, "gi");
  return <>{text.split(pattern).map((part, index) => (index % 2 === 1 ? <mark key={index}>{part}</mark> : part))}</>;
}

/** 결과 갈래 — 칩의 이름과 순서(TODO 254 C) */
const GROUPS: { key: string; label: string }[] = [
  { key: "projects", label: "과제" }, { key: "intakes", label: "접수" }, { key: "entries", label: "진행일지" },
  { key: "reports", label: "보고" }, { key: "attachments", label: "첨부" }, { key: "contributions", label: "담당과 역할" },
  { key: "activities", label: "팀원역량" },
];
const FIELD_LABELS: Record<string, string> = { owner: "담당", tag: "태그", status: "상태", year: "연도" };

export default function SearchResults({ query, meta, back }: { query: string; meta: Meta; back?: string | null }) {
  const [results, setResults] = useState<Results | null>(null);
  const [error, setError] = useState<string | null>(null);
  // 정렬 · 종류 칩 (TODO 254 C) — 과제는 관련도 순이 기본
  const [sort, setSort] = useState<"relevance" | "recent">("relevance");
  const [only, setOnly] = useState<string>("");

  // 새 검색어마다 지난 오류를 비운다 — 한 번 실패하면 다음 검색어도 같은 오류가 남아 있었다 (TODO 209 ③).
  // 검색어를 빨리 바꾸면 앞 검색이 늦게 와 덮을 수 있다 — 지금 검색어의 것만 받는다(alive)
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let alive = true;
    setResults(null);
    setError(null);
    api
      .search(query, sort)
      .then((next) => alive && setResults(next))
      .catch((err: Error) => alive && setError(err.message));
    return () => {
      alive = false;
    };
  }, [query, attempt, sort]);
  const retry = useCallback(() => setAttempt((value) => value + 1), []);

  if (error)
    return (
      <section className="search-results">
        <a className="back" href={backTarget(back).href}>
          ← {backTarget(back).label}
        </a>
        <LoadError message={error} onRetry={retry} />
      </section>
    );
  if (!results) return <div className="app-loading">검색 중…</div>;

  const cut = Object.values(results.truncated ?? {}).some(Boolean);
  const words = results.parsed?.words ?? [query];
  const counts: Record<string, number> = Object.fromEntries(
    GROUPS.map((g) => [g.key, ((results as unknown as Record<string, unknown[] | undefined>)[g.key] ?? []).length]),
  );
  const show = (key: string) => (!only || only === key) && counts[key] > 0;
  const parsed = results.parsed;
  const conditions = parsed
    ? [
        ...(parsed.words.length > 1 ? [`낱말 ${parsed.words.length}개 모두`] : []),
        ...parsed.excludes.map((w) => `-${w}`),
        ...Object.entries(parsed.fields).flatMap(([key, values]) => values.map((v) => `${FIELD_LABELS[key] ?? key}:${v}`)),
        ...parsed.kinds.map((k) => `종류:${GROUPS.find((g) => g.key === k)?.label ?? k}`),
      ]
    : [];

  return (
    <section className="search-results">
      {/* 온 곳으로 돌아간다 (TODO 127) */}
      <a className="back" href={backTarget(back).href}>
        ← {backTarget(back).label}
      </a>
      <h1 className="search-title">
        “{query}” 검색 결과{" "}
        <span className="muted">
          {results.total}건{cut && " 이상"}
        </span>
      </h1>
      {cut && (
        /* 잘린 줄 모르면 "이게 전부" 라고 믿게 된다. 흔한 낱말일수록 그렇다. */
        <p className="hint search-cut">
          찾은 것이 많아 <b>일부만 보여 주고 있습니다.</b> 낱말을 더 붙이거나
          <b> 보고 이력</b>·<b>과제 목록</b>의 조건으로 좁혀 보세요.
        </p>
      )}

      {/* 종류 칩 · 정렬 · 읽은 조건 (TODO 254) */}
      <div className="search-tools" data-testid="search-tools">
        <span className="search-chips" role="group" aria-label="종류로 거르기">
          <button className={only ? "search-chip" : "search-chip on"} onClick={() => setOnly("")}>전체 {results.total}</button>
          {GROUPS.filter((g) => counts[g.key] > 0).map((g) => (
            <button key={g.key} className={only === g.key ? "search-chip on" : "search-chip"} data-kind={g.key} onClick={() => setOnly(only === g.key ? "" : g.key)}>
              {g.label} {counts[g.key]}{(results.truncated as Record<string, boolean | undefined>)?.[g.key] ? "+" : ""}
            </button>
          ))}
        </span>
        <label className="search-sort">과제 정렬
          <select aria-label="과제 정렬" value={sort} onChange={(event) => setSort(event.target.value as "relevance" | "recent")}>
            <option value="relevance">관련도 순</option>
            <option value="recent">최근 순</option>
          </select>
        </label>
      </div>
      {conditions.length > 0 && <p className="muted search-conditions">조건: {conditions.join(" · ")}</p>}

      {results.total === 0 && (
        <div className="empty card">
          <p>일치하는 내용이 없습니다.</p>
          <p className="hint">찾는 법 — 낱말을 띄어 쓰면 <b>모두 들어간 것</b> · <code>"한 구절"</code> · <code>-뺄말</code> ·
            <code> 담당:이름</code> · <code>태그:품질</code> · <code>상태:진행중</code> · <code>연도:2026</code> · <code>종류:일지</code>(과제 · 일지 · 보고 · 첨부 · 접수 · 역할 · 역량)</p>
        </div>
      )}

      {show("projects") && (
        <div className="card">
          <h2>과제 {results.projects.length}건{results.truncated?.projects && " 이상"}</h2>
          <ul className="result-list">
            {results.projects.map((project) => (
              <li key={project.id}>
                <a href={projectLink(project.id)}>
                  <span className="project-id">{project.id}</span>
                  <strong>
                    <Highlight text={project.title} query={words} />
                  </strong>
                  <StageBand stage={project.stage} />
                  <StatusBadge status={project.status} meta={meta} />
                </a>
                <p className="snippet">
                  <Highlight text={project.snippet} query={words} />
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {show("intakes") && (
        <div className="card">
          <h2>접수 {(results.intakes ?? []).length}건{results.truncated?.intakes && " 이상"}</h2>
          <ul className="result-list">
            {(results.intakes ?? []).map((intake) => (
              <li key={intake.id}>
                <a href={screenLink(`intakes/${intake.id}`)}>
                  <span className="project-id">
                    {intake.id}
                    {intake.leader_team && ` · ${intake.leader_team}`}
                    {intake.leader && ` ${intake.leader}`}
                  </span>
                  <strong>
                    <Highlight text={intake.title} query={words} />
                  </strong>
                  <span className={`intake-status intake-${intake.status}`}>{intake.status_label}</span>
                  {intake.project_id && <span className="muted"> → {intake.project_id}</span>}
                </a>
                <p className="snippet">
                  <Highlight text={intake.snippet} query={words} />
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {show("entries") && (
        <div className="card">
          <h2>진행일지 {results.entries.length}건{results.truncated?.entries && " 이상"}</h2>
          <ul className="result-list">
            {results.entries.map((entry) => (
              <li key={entry.id}>
                <a href={projectLink(entry.project_id, { entry: entry.id })}>
                  <span className="project-id">
                    {entry.date} · {entry.project_title}
                  </span>
                  <strong>
                    <Highlight text={entry.title} query={words} />
                  </strong>
                </a>
                <p className="snippet">
                  <Highlight text={entry.snippet} query={words} />
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {show("reports") && (
        <div className="card">
          <h2>보고 {results.reports.length}건{results.truncated?.reports && " 이상"}</h2>
          <ul className="result-list">
            {results.reports.map((report) => (
              <li key={report.id}>
                {/* 누르면 그 보고 문서가 바로 열린다 — 찾는 이유가 대개 "그때 뭐라고 썼더라"다. */}
                <a href={projectLink(report.project_id, { report: report.id })}>
                  <span className="project-id">
                    {report.report_date} · {report.project_title}
                    {!report.frozen && <span className="draft-tag"> 작성 중</span>}
                  </span>
                  <strong>
                    <Highlight text={report.audience || report.title || "보고"} query={words} />
                  </strong>
                </a>
                <p className="snippet">
                  <Highlight text={report.snippet} query={words} />
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {show("attachments") && (
        <div className="card">
          <h2>첨부 파일 {results.attachments.length}건{results.truncated?.attachments && " 이상"}</h2>
          <ul className="result-list">
            {results.attachments.map((attachment) => (
              <li key={attachment.id}>
                <a href={projectLink(attachment.project_id)}>
                  <span className="project-id">{attachment.project_title}</span>
                  <strong>
                    <Highlight text={attachment.orig_name} query={words} />
                  </strong>
                  <span className="muted">{formatBytes(attachment.size_bytes)}</span>
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
      {show("contributions") && (
        <div className="card" data-testid="search-contributions">
          <h2>담당과 역할 {counts.contributions}건{results.truncated?.contributions && " 이상"}</h2>
          <ul className="result-list">
            {(results.contributions ?? []).map((item) => (
              <li key={`${item.project_id}|${item.name}`}>
                <a href={projectLink(item.project_id)}>
                  <span className="project-id">{item.project_id} · {item.project_title}</span>
                  <strong><Highlight text={item.name} query={words} /></strong>
                  {item.role && <span className="muted"> {item.role}</span>}
                </a>
                <p className="snippet"><Highlight text={item.snippet} query={words} /></p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {show("activities") && (
        <div className="card" data-testid="search-activities">
          <h2>팀원역량 {counts.activities}건{results.truncated?.activities && " 이상"}</h2>
          <ul className="result-list">
            {(results.activities ?? []).map((item) => (
              <li key={item.id}>
                <a href={screenLink(`skills?tab=records&person=${encodeURIComponent(item.person)}`)}>
                  <span className="project-id">{item.date} · {item.person}{item.host ? ` · ${item.host}` : ""}</span>
                  <strong><Highlight text={item.title} query={words} /></strong>
                </a>
                {item.snippet && <p className="snippet"><Highlight text={item.snippet} query={words} /></p>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
