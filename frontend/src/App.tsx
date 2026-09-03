import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import ProjectDetail from "./components/ProjectDetail";
import ProjectList from "./components/ProjectList";
import ReportCandidates from "./components/ReportCandidates";
import ReportHistory from "./components/ReportHistory";
import Settings from "./components/Settings";
import SearchResults from "./components/SearchResults";
import type { Meta } from "./types";

type Route =
  | { name: "list" }
  | { name: "project"; id: string; reportId?: number; entryId?: number }
  | { name: "search"; query: string }
  | { name: "reports" }
  | { name: "history" }
  | { name: "settings" };

function readRoute(): Route {
  const hash = window.location.hash.replace(/^#\/?/, "");
  const [path, queryString] = hash.split("?");
  const params = new URLSearchParams(queryString ?? "");

  if (path.startsWith("projects/")) {
    const reportId = params.get("report");
    const entryId = params.get("entry");
    return {
      name: "project",
      id: path.slice("projects/".length),
      reportId: reportId ? Number(reportId) : undefined,
      entryId: entryId ? Number(entryId) : undefined,
    };
  }
  if (path.startsWith("search")) return { name: "search", query: params.get("q") ?? "" };
  if (path.startsWith("history")) return { name: "history" };
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
  const [author, setAuthor] = useState<string | null>(null);
  const [authorNoticeClosed, setAuthorNoticeClosed] = useState(false);
  const headerRef = useRef<HTMLElement>(null);

  // 상단 헤더는 화면이 좁아지면 두세 줄로 접혀 67px에서 183px까지 자란다.
  // 편집기로 화면을 옮길 때(util.ts) 제목이 헤더에 가리지 않도록 실제 높이를 CSS에 알려 준다.
  useEffect(() => {
    const header = headerRef.current;
    if (!header) return;
    const publish = () =>
      document.documentElement.style.setProperty(
        "--header-h",
        `${Math.round(header.getBoundingClientRect().height)}px`,
      );
    publish();
    const observer = new ResizeObserver(publish);
    observer.observe(header);
    return () => observer.disconnect();
  });

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
    // 작성자를 정하지 않으면 기록에 작성자가 비어 쌓인다. 한 번 알려 준다.
    api.settings().then((settings) => setAuthor(settings.author)).catch(() => setAuthor(null));
  }, []);

  useEffect(loadMeta, [loadMeta]);

  if (error) return <div className="app-error">서버에 연결하지 못했습니다: {error}</div>;
  if (!meta) return <div className="app-loading">불러오는 중…</div>;

  return (
    <div className="app">
      <header className="app-header" ref={headerRef}>
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
          <a href="#/history" className={route.name === "history" ? "active" : undefined}>
            보고 이력
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
      {author === "" && !authorNoticeClosed && route.name !== "settings" && (
        <div className="author-notice">
          <span>
            <strong>작성자가 아직 정해지지 않았습니다.</strong> 지금 정해 두면 앞으로 쓰는 진행일지와
            보고에 작성자가 함께 기록됩니다.
          </span>
          <a href="#/settings">설정에서 지정</a>
          <button className="ghost small" onClick={() => setAuthorNoticeClosed(true)}>
            나중에
          </button>
        </div>
      )}
      <main>
        {route.name === "project" && (
          <ProjectDetail
            projectId={route.id}
            meta={meta}
            onMetaChange={loadMeta}
            openReportId={route.reportId}
            openEntryId={route.entryId}
          />
        )}
        {route.name === "reports" && <ReportCandidates meta={meta} />}
        {route.name === "history" && <ReportHistory meta={meta} />}
        {route.name === "settings" && <Settings meta={meta} onSaved={loadMeta} />}
        {route.name === "search" && <SearchResults query={route.query} meta={meta} />}
        {route.name === "list" && <ProjectList meta={meta} onMetaChange={loadMeta} />}
      </main>
    </div>
  );
}
