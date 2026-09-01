import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import ProjectDetail from "./components/ProjectDetail";
import ProjectList from "./components/ProjectList";
import type { Meta } from "./types";

function readRoute(): string | null {
  const hash = window.location.hash.replace(/^#\/?/, "");
  return hash.startsWith("projects/") ? hash.slice("projects/".length) : null;
}

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [route, setRoute] = useState<string | null>(readRoute());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onHashChange = () => setRoute(readRoute());
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
        <span className="vault-path" title="데이터 위치">
          {meta.vault}
        </span>
      </header>
      <main>
        {route ? (
          <ProjectDetail projectId={route} meta={meta} onMetaChange={loadMeta} />
        ) : (
          <ProjectList meta={meta} onMetaChange={loadMeta} />
        )}
      </main>
    </div>
  );
}
