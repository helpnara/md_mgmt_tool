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

  return (
    <section className="search-results">
      <a className="back" href="#/">
        ← 과제 목록
      </a>
      <h1 className="search-title">
        “{query}” 검색 결과 <span className="muted">{results.total}건</span>
      </h1>

      {results.total === 0 && <p className="empty card">일치하는 내용이 없습니다.</p>}

      {results.projects.length > 0 && (
        <div className="card">
          <h2>과제 {results.projects.length}건</h2>
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
          <h2>진행일지 {results.entries.length}건</h2>
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

      {results.attachments.length > 0 && (
        <div className="card">
          <h2>첨부 파일 {results.attachments.length}건</h2>
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
