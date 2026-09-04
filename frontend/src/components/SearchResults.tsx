import { useEffect, useState } from "react";
import { api } from "../api";
import { projectLink } from "../nav";
import type { Meta, SearchResults as Results } from "../types";
import { formatBytes } from "../upload";
import StatusBadge from "./StatusBadge";

/** 검색어와 일치하는 부분을 강조한다. */
function Highlight({ text, query }: { text: string; query: string }) {
  if (!query) return <>{text}</>;
  const parts: (string | JSX.Element)[] = [];
  const lowerText = text.toLowerCase();
  const lowerQuery = query.toLowerCase();
  let cursor = 0;
  for (let found = lowerText.indexOf(lowerQuery); found >= 0; found = lowerText.indexOf(lowerQuery, cursor)) {
    parts.push(text.slice(cursor, found));
    parts.push(<mark key={found}>{text.slice(found, found + query.length)}</mark>);
    cursor = found + query.length;
  }
  parts.push(text.slice(cursor));
  return <>{parts}</>;
}

export default function SearchResults({ query, meta }: { query: string; meta: Meta }) {
  const [results, setResults] = useState<Results | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setResults(null);
    api.search(query).then(setResults).catch((err: Error) => setError(err.message));
  }, [query]);

  if (error) return <p className="form-error">{error}</p>;
  if (!results) return <div className="app-loading">검색 중…</div>;

  const cut = Object.values(results.truncated ?? {}).some(Boolean);

  return (
    <section className="search-results">
      <a className="back" href="#/">
        ← 과제 목록
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

      {results.total === 0 && <p className="empty card">일치하는 내용이 없습니다.</p>}

      {results.projects.length > 0 && (
        <div className="card">
          <h2>과제 {results.projects.length}건{results.truncated?.projects && " 이상"}</h2>
          <ul className="result-list">
            {results.projects.map((project) => (
              <li key={project.id}>
                <a href={projectLink(project.id)}>
                  <span className="project-id">{project.id}</span>
                  <strong>
                    <Highlight text={project.title} query={query} />
                  </strong>
                  <StatusBadge status={project.status} meta={meta} />
                </a>
                <p className="snippet">
                  <Highlight text={project.snippet} query={query} />
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {results.entries.length > 0 && (
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
                    <Highlight text={entry.title} query={query} />
                  </strong>
                </a>
                <p className="snippet">
                  <Highlight text={entry.snippet} query={query} />
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {results.reports.length > 0 && (
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
                    <Highlight text={report.audience || report.title || "보고"} query={query} />
                  </strong>
                </a>
                <p className="snippet">
                  <Highlight text={report.snippet} query={query} />
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {results.attachments.length > 0 && (
        <div className="card">
          <h2>첨부 파일 {results.attachments.length}건{results.truncated?.attachments && " 이상"}</h2>
          <ul className="result-list">
            {results.attachments.map((attachment) => (
              <li key={attachment.id}>
                <a href={projectLink(attachment.project_id)}>
                  <span className="project-id">{attachment.project_title}</span>
                  <strong>
                    <Highlight text={attachment.orig_name} query={query} />
                  </strong>
                  <span className="muted">{formatBytes(attachment.size_bytes)}</span>
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
