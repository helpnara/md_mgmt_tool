import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import ProjectDetail from "./components/ProjectDetail";
import ProjectList from "./components/ProjectList";
import ReportCandidates from "./components/ReportCandidates";
import Settings from "./components/Settings";
import SearchResults from "./components/SearchResults";
import type { Meta } from "./types";

type Route =
  | { name: "list" }
  | { name: "project"; id: string; reportId?: number }
  | { name: "search"; query: string }
  | { name: "reports" }
  | { name: "settings" };

function readRoute(): Route {
  const hash = window.location.hash.replace(/^#\/?/, "");
  const [path, queryString] = hash.split("?");
  const params = new URLSearchParams(queryString ?? "");

  if (path.startsWith("projects/")) {
    const reportId = params.get("report");
    return {
      name: "project",
      id: path.slice("projects/".length),
      reportId: reportId ? Number(reportId) : undefined,
    };
  }
  if (path.startsWith("search")) return { name: "search", query: params.get("q") ?? "" };
  if (path.startsWith("reports")) return { name: "reports" };
  if (path.startsWith("settings")) return { name: "settings" };
  return { name: "list" };
}

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [route, setRoute] = useState<Route>(readRoute());
  const [term, setTerm] = useState(() => {
    const initial = readRoute();
    return initial.name === "search" ? initial.query : "";
  });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onHashChange = () => {
      const next = readRoute();
      setRoute(next);
      if (next.name === "search") setTerm(next.query);
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const loadMeta = useCallback(() => {
    api.meta().then(setMeta).catch((err: Error) => setError(err.message));
  }, []);

  useEffect(loadMeta, [loadMeta]);

  if (error) return <div className="app-error">서버에 연결하지 못했습니다: {error}</div>;
  if (!meta) return <div className="app-loading">불러오는 중…</div>;

  return (
    <div className="app">
      <header className="app-header">
        <a className="brand" href="#/">
          과제 이력 관리
        </a>
        <nav className="nav">
          <a href="#/" className={route.name === "list" ? "active" : undefined}>
            과제
          </a>
          <a href="#/reports" className={route.name === "reports" ? "active" : undefined}>
            보고 대상
          </a>
          <a href="#/settings" className={route.name === "settings" ? "active" : undefined}>
            설정
          </a>
        </nav>
        <form
          className="search-box"
          onSubmit={(event) => {
            event.preventDefault();
            const query = term.trim();
            window.location.hash = query ? `#/search?q=${encodeURIComponent(query)}` : "#/";
          }}
        >
          <input
            type="search"
            value={term}
            onChange={(event) => setTerm(event.target.value)}
            placeholder="과제·진행일지·첨부 파일명 검색"
            aria-label="검색"
          />
          <button type="submit" className="ghost">
            검색
          </button>
        </form>
        <span className="vault-path" title="데이터 위치">
          {meta.vault}
        </span>
      </header>
      <main>
        {route.name === "project" && (
          <ProjectDetail
            projectId={route.id}
            meta={meta}
            onMetaChange={loadMeta}
            openReportId={route.reportId}
          />
        )}
        {route.name === "reports" && <ReportCandidates meta={meta} />}
        {route.name === "settings" && <Settings meta={meta} onSaved={loadMeta} />}
        {route.name === "search" && <SearchResults query={route.query} meta={meta} />}
        {route.name === "list" && <ProjectList meta={meta} onMetaChange={loadMeta} />}
      </main>
    </div>
  );
}
