import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import Home from "./components/Home";
import ProjectDetail from "./components/ProjectDetail";
import ProjectList from "./components/ProjectList";
import ReportCandidates from "./components/ReportCandidates";
import ReportHistory from "./components/ReportHistory";
import Roadmap from "./components/Roadmap";
import ScrollTop from "./components/ScrollTop";
import Settings from "./components/Settings";
import Skills from "./components/Skills";
import Help from "./components/Help";
import IntakeDetail from "./components/IntakeDetail";
import IntakePool from "./components/IntakePool";
import SearchResults from "./components/SearchResults";
import type { Meta } from "./types";
import { BACK_PARAM, SCREEN_TITLES, setPageTitle } from "./nav";
import { confirmLeave, hasUnsaved, LEAVE_MESSAGE, migrateBrowserDrafts } from "./unsaved";
import ErrorBoundary from "./components/ErrorBoundary";
import Toast from "./components/Toast";

type Route =
  // 홈이 `#/` 를 쓰고, 과제 목록은 `#/projects` 로 내려간다 (TODO 56).
  | { name: "home" }
  // 목록 화면은 거른 조건을 주소에 두고 그대로 돌려받는다 (nav.ts).
  | { name: "list"; query: string }
  | { name: "project"; id: string; reportId?: number; entryId?: number; back: string | null; edit?: boolean; draft?: string | null }
  | { name: "search"; query: string; back: string | null }
  | { name: "reports"; query: string }
  | { name: "history"; query: string }
  // 다년도 과제 로드맵 (TODO 174)
  | { name: "roadmap"; query: string }
  | { name: "skills"; query: string }
  | { name: "settings"; back: string | null }
  | { name: "help" }
  // 과제 접수 풀 (TODO 136)
  | { name: "intakes"; query: string }
  | { name: "intake"; id: string; back: string | null; draft?: string | null };

/** 주소 조각을 풀어 쓴다 — 잘못 적힌 `%` 가 있어도 넘어지지 않게 (그때는 그대로) */
function safeDecode(text: string): string {
  try {
    return decodeURIComponent(text);
  } catch {
    return text;
  }
}

function readRoute(): Route {
  const hash = window.location.hash.replace(/^#\/?/, "");
  const [path, queryString] = hash.split("?");
  const params = new URLSearchParams(queryString ?? "");

  if (path.startsWith("projects/")) {
    const reportId = params.get("report");
    const entryId = params.get("entry");
    return {
      name: "project",
      // 브라우저는 주소의 한글을 `%ED%8C%80` 처럼 바꿔 돌려준다. 그대로 쓰면 팀 코드에 한글이 든 과제
      // (`2026-ABC팀-001`)에서 화면이 쓰는 번호와 서버가 준 번호가 **서로 다른 글자**가 된다 — v7 B-6 에서
      // "작성 중이던 기록 있음" 이 안 뜬 까닭이 이것이었다(보관은 한글 번호로, 표시는 바뀐 번호로 찾았다). 접수처럼 풀어 쓴다.
      id: safeDecode(path.slice("projects/".length)),
      reportId: reportId ? Number(reportId) : undefined,
      entryId: entryId ? Number(entryId) : undefined,
      back: params.get(BACK_PARAM),
      edit: params.get("edit") === "1",
      // 홈의 "작성 중이던 글" 에서 — 그 편집기를 연다 (TODO 170)
      draft: params.get("draft"),
    };
  }
  if (path.startsWith("search"))
    return { name: "search", query: params.get("q") ?? "", back: params.get(BACK_PARAM) };
  if (path.startsWith("history")) return { name: "history", query: queryString ?? "" };
  if (path.startsWith("roadmap")) return { name: "roadmap", query: queryString ?? "" };
  if (path.startsWith("reports")) return { name: "reports", query: queryString ?? "" };
  if (path.startsWith("skills")) return { name: "skills", query: queryString ?? "" };
  if (path.startsWith("settings")) return { name: "settings", back: params.get(BACK_PARAM) };
  if (path.startsWith("help")) return { name: "help" };
  if (path.startsWith("intakes/"))
    return {
      name: "intake",
      id: safeDecode(path.slice("intakes/".length)),
      back: params.get(BACK_PARAM),
      draft: params.get("draft"),
    };
  if (path.replace(/\/$/, "") === "intakes") return { name: "intakes", query: queryString ?? "" };
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
  const screenKey =
    route.name === "project" ? `project:${route.id}` : route.name === "intake" ? `intake:${route.id}` : route.name;
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

  // 편집 중에 떠나면 묻는다 (TODO 162). 화면 안 이동은 주소가 이미 바뀐 뒤에 알 수 있으므로,
  // 머물기로 하면 **바뀐 주소를 되돌린다**(history 를 쌓지 않게 replaceState — hashchange 가 다시 나지 않는다).
  // 되돌릴 주소는 이벤트의 oldURL — 조건을 바꿀 때 쓰는 replaceState 까지 반영된 직전 주소다.
  useEffect(() => {
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!hasUnsaved()) return;
      event.preventDefault();
      event.returnValue = LEAVE_MESSAGE;
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, []);

  useEffect(() => {
    const onHashChange = (event: HashChangeEvent) => {
      if (!confirmLeave()) {
        const before = event.oldURL.includes("#") ? event.oldURL.slice(event.oldURL.indexOf("#")) : "#/";
        window.history.replaceState(null, "", before);
        return;
      }
      const next = readRoute();
      setRoute(next);
      // 검색 결과를 떠나면 검색창을 비운다 (TODO 115). 지난 검색어가 남아 있으면
      // 다음 화면에서 그것이 지금 걸린 조건처럼 보인다.
      setTerm(next.name === "search" ? next.query : "");
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
  // 162 때 브라우저 안에 남은 쓰던 글을 데이터 폴더로 옮긴다 — 한 번, 조용히 (TODO 170)
  useEffect(() => {
    void migrateBrowserDrafts();
  }, []);

  // 브라우저 탭 제목 (TODO 169) — 과제 · 접수를 여러 탭으로 열어도 구분되게. 과제 · 접수 화면은
  // 제목을 알고 나서 스스로 고친다(pageTitle).
  useEffect(() => {
    if (route.name === "project" || route.name === "intake") return;
    setPageTitle(SCREEN_TITLES[route.name] ?? "");
  }, [route.name]);

  if (error)
    return (
      <div className="app-error">
        <p>{error}</p>
        <button
          onClick={() => {
            setError(null);
            loadMeta();
          }}
        >
          다시 시도
        </button>
      </div>
    );
  if (!meta) return <div className="app-loading">불러오는 중…</div>;

  return (
    <div className="app">
      <header className="app-header" ref={headerRef}>
        <a className="brand" href="#/">
          <img className="brand-mark" src="/favicon.svg" alt="" width="22" height="22" />
          느린 나이테
        </a>
        <nav className="nav">
          <a href="#/" className={route.name === "home" ? "active" : undefined}>
            홈
          </a>
          {/* 접수 → 과제 순서 (TODO 136). 팀의 일이 그 순서로 흐른다. */}
          <a href="#/intakes" className={route.name === "intakes" || route.name === "intake" ? "active" : undefined}>
            접수
          </a>
          <a href="#/projects" className={route.name === "list" ? "active" : undefined}>
            과제목록
          </a>
          {/* 다년도 과제의 줄기를 한 화면에 (TODO 174) — 과제목록 바로 뒤: 과제를 다른 모양으로 보는 자리다 */}
          <a href="#/roadmap" className={route.name === "roadmap" ? "active" : undefined}>
            로드맵
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
        {/* 화면 하나가 그리다 멈춰도 메뉴는 살아 있게 (TODO 166) */}
        <ErrorBoundary resetKey={screenKey}>
        {route.name === "project" && (
          <ProjectDetail
            projectId={route.id}
            meta={meta}
            onMetaChange={loadMeta}
            openReportId={route.reportId}
            openEntryId={route.entryId}
            back={route.back}
            edit={route.edit}
            openDraft={route.draft}
          />
        )}
        {route.name === "reports" && <ReportCandidates meta={meta} query={route.query} />}
        {route.name === "history" && <ReportHistory meta={meta} query={route.query} />}
        {route.name === "roadmap" && <Roadmap meta={meta} query={route.query} />}
        {route.name === "settings" && <Settings meta={meta} onSaved={loadMeta} back={route.back} />}
        {route.name === "search" && <SearchResults query={route.query} meta={meta} back={route.back} />}
        {route.name === "list" && <ProjectList meta={meta} onMetaChange={loadMeta} query={route.query} />}
        {route.name === "home" && <Home meta={meta} onMetaChange={loadMeta} />}
        {route.name === "skills" && <Skills meta={meta} query={route.query} />}
        {route.name === "help" && <Help />}
        {route.name === "intakes" && <IntakePool meta={meta} query={route.query} />}
        {route.name === "intake" && (
          <IntakeDetail
            key={route.id}
            intakeId={route.id}
            meta={meta}
            back={route.back}
            onMetaChange={loadMeta}
            openDraft={route.draft}
          />
        )}
        </ErrorBoundary>
      </main>
      <Toast />
      {/* 화면마다 따로 두지 않는다 — 요청의 핵심이 "어디서나 같은 자리"다. */}
      <ScrollTop />
    </div>
  );
}
