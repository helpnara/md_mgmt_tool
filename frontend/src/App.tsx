import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import Home from "./components/Home";
import ProjectDetail from "./components/ProjectDetail";
import ProjectList from "./components/ProjectList";
import ReportCandidates from "./components/ReportCandidates";
import ReportHistory from "./components/ReportHistory";
import ScrollTop from "./components/ScrollTop";
import Settings from "./components/Settings";
import Skills from "./components/Skills";
import Help from "./components/Help";
import SearchResults from "./components/SearchResults";
import type { Meta } from "./types";
import { BACK_PARAM } from "./nav";

type Route =
  // 홈이 `#/` 를 쓰고, 과제 목록은 `#/projects` 로 내려간다 (TODO 56).
  | { name: "home" }
  // 목록 화면은 거른 조건을 주소에 두고 그대로 돌려받는다 (nav.ts).
  | { name: "list"; query: string }
  | { name: "project"; id: string; reportId?: number; entryId?: number; back: string | null; edit?: boolean }
  | { name: "search"; query: string }
  | { name: "reports"; query: string }
  | { name: "history"; query: string }
  | { name: "skills"; query: string }
  | { name: "settings" }
  | { name: "help" };

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
      back: params.get(BACK_PARAM),
      edit: params.get("edit") === "1",
    };
  }
  if (path.startsWith("search")) return { name: "search", query: params.get("q") ?? "" };
  if (path.startsWith("history")) return { name: "history", query: queryString ?? "" };
  if (path.startsWith("reports")) return { name: "reports", query: queryString ?? "" };
  if (path.startsWith("skills")) return { name: "skills", query: queryString ?? "" };
  if (path.startsWith("settings")) return { name: "settings" };
  if (path.startsWith("help")) return { name: "help" };
  if (path.replace(/\/$/, "") === "projects") return { name: "list", query: queryString ?? "" };
  // 아는 주소가 아니면 홈으로. 손으로 고친 주소에서 빈 화면을 만나는 것보다 낫다.
  return { name: "home" };
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

  // 화면을 옮기면 맨 위에서 시작한다.
  //
  // 해시 이동은 같은 문서 안에서 일어나 **스크롤이 그대로 남는다.** 그래서 목록을 한참
  // 내려보다 과제를 열면 상세가 중간부터 보였다. 옮긴 화면은 처음부터 보여야 한다.
  //
  // 다만 보고·진행일지를 지정해 여는 경우(`?report=` `?entry=`)는 건드리지 않는다 —
  // 그쪽은 해당 문서 자리로 데려가는 것이 목적이고(util.ts scrollEditorIntoView),
  // 여기서 맨 위로 올리면 그 동작을 덮어써 버린다.
  const screenKey = route.name === "project" ? `project:${route.id}` : route.name;
  const targeted = route.name === "project" && (route.reportId !== undefined || route.entryId !== undefined);
  useEffect(() => {
    // 브라우저는 같은 문서 안 이동에서 스크롤 위치를 **되살린다.** 그대로 두면
    // 아래에서 맨 위로 올려 놓아도 곧바로 원래 자리로 되돌려 놓는다.
    if ("scrollRestoration" in window.history) window.history.scrollRestoration = "manual";
  }, []);

  useEffect(() => {
    if (!targeted) window.scrollTo(0, 0);
    // 같은 화면 안에서 조건만 바뀐 경우는 제외하려고 화면 이름만 본다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [screenKey]);

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
          <a href="#/" className={route.name === "home" ? "active" : undefined}>
            홈
          </a>
          <a href="#/projects" className={route.name === "list" ? "active" : undefined}>
            과제목록
          </a>
          <a href="#/reports" className={route.name === "reports" ? "active" : undefined}>
            보고대상
          </a>
          <a href="#/history" className={route.name === "history" ? "active" : undefined}>
            보고이력
          </a>
          <a href="#/skills" className={route.name === "skills" ? "active" : undefined}>
            팀원역량
          </a>
          <a href="#/settings" className={route.name === "settings" ? "active" : undefined}>
            설정
          </a>
          <a href="#/help" className={route.name === "help" ? "active" : undefined}>
            도움말
          </a>
        </nav>
        <form
          className="search-box"
          onSubmit={(event) => {
            event.preventDefault();
            const query = term.trim();
            // 검색어를 비우고 누르면 검색을 그만두는 것이므로 과제 목록으로 돌려보낸다.
            window.location.hash = query ? `#/search?q=${encodeURIComponent(query)}` : "#/projects";
          }}
        >
          <input
            type="search"
            value={term}
            onChange={(event) => setTerm(event.target.value)}
            placeholder="과제·진행일지·보고·첨부·담당자·유관부서 검색"
            aria-label="검색"
          />
          <button type="submit" className="ghost">
            검색
          </button>
        </form>
        {/* 길면 잘린다 — 마우스를 올리면 전체 경로가 보인다 (TODO 88). */}
        <span className="vault-path" title={`데이터 위치: ${meta.vault}`}>
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
            back={route.back}
            edit={route.edit}
          />
        )}
        {route.name === "reports" && <ReportCandidates meta={meta} query={route.query} />}
        {route.name === "history" && <ReportHistory meta={meta} query={route.query} />}
        {route.name === "settings" && <Settings meta={meta} onSaved={loadMeta} />}
        {route.name === "search" && <SearchResults query={route.query} meta={meta} />}
        {route.name === "list" && <ProjectList meta={meta} onMetaChange={loadMeta} query={route.query} />}
        {route.name === "home" && <Home meta={meta} />}
        {route.name === "skills" && <Skills meta={meta} query={route.query} />}
        {route.name === "help" && <Help />}
      </main>
      {/* 화면마다 따로 두지 않는다 — 요청의 핵심이 "어디서나 같은 자리"다. */}
      <ScrollTop />
    </div>
  );
}
