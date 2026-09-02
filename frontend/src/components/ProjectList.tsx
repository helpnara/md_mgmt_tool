import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { Meta, Project } from "../types";
import { dueLabel, formatDate } from "../util";
import Dashboard from "./Dashboard";
import ProjectBoard from "./ProjectBoard";
import ProjectForm from "./ProjectForm";
import StatusBadge, { TypeBadge } from "./StatusBadge";

interface Props {
  meta: Meta;
  onMetaChange: () => void;
}

export default function ProjectList({ meta, onMetaChange }: Props) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [filters, setFilters] = useState({
    status: "", type: "", group: "", tag: "", owner: "", due: "", sort: "updated",
  });
  const [view, setView] = useState<"table" | "board">(
    () => (localStorage.getItem("md-mgmt:view") === "board" ? "board" : "table"),
  );
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [problems, setProblems] = useState<{ path: string; reason: string }[]>([]);
  // 과제가 늘거나 다시 읽었을 때 대시보드도 같이 갱신한다.
  const [refreshKey, setRefreshKey] = useState(0);

  const load = useCallback(() => {
    api
      .listProjects(filters)
      .then(setProjects)
      .catch((err: Error) => setError(err.message));
  }, [filters]);

  useEffect(load, [load]);

  const setFilter = (key: string, value: string) =>
    setFilters((prev) => ({ ...prev, [key]: value }));

  return (
    <section className="project-list">
      <Dashboard
        refreshKey={refreshKey}
        filters={filters}
        onFilter={(key, value) => setFilter(key, value)}
      />

      <div className="toolbar">
        <div className="filters">
          <select value={filters.status} onChange={(event) => setFilter("status", event.target.value)}>
            <option value="">상태 전체</option>
            {meta.statuses.map((status) => (
              <option key={status.key} value={status.key}>
                {status.label}
              </option>
            ))}
          </select>
          <select value={filters.type} onChange={(event) => setFilter("type", event.target.value)}>
            <option value="">속성 전체</option>
            <option value="none">미지정</option>
            {meta.types.map((type) => (
              <option key={type.key} value={type.key}>
                {type.label}
              </option>
            ))}
          </select>
          <select value={filters.group} onChange={(event) => setFilter("group", event.target.value)}>
            <option value="">그룹 전체</option>
            {meta.groups.map((group) => (
              <option key={group} value={group}>
                {group}
              </option>
            ))}
          </select>
          <select value={filters.tag} onChange={(event) => setFilter("tag", event.target.value)}>
            <option value="">태그 전체</option>
            {meta.tags.map((tag) => (
              <option key={tag} value={tag}>
                {tag}
              </option>
            ))}
          </select>
          <select value={filters.owner} onChange={(event) => setFilter("owner", event.target.value)}>
            <option value="">담당자 전체</option>
            {meta.owners.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <select value={filters.due} onChange={(event) => setFilter("due", event.target.value)}>
            <option value="">마감 전체</option>
            <option value="overdue">기한 초과</option>
            <option value="7">7일 이내</option>
            <option value="14">14일 이내</option>
            <option value="30">30일 이내</option>
          </select>
          <select value={filters.sort} onChange={(event) => setFilter("sort", event.target.value)}>
            <option value="updated">최근 업데이트순</option>
            <option value="due">마감일순</option>
            <option value="reported">보고 경과일순</option>
            <option value="created">생성순</option>
            <option value="title">이름순</option>
          </select>
        </div>
        <div className="toolbar-actions">
          <div className="view-switch">
            {(["table", "board"] as const).map((option) => (
              <button
                key={option}
                className={view === option ? "active" : "ghost"}
                onClick={() => {
                  setView(option);
                  localStorage.setItem("md-mgmt:view", option);
                }}
              >
                {option === "table" ? "표" : "보드"}
              </button>
            ))}
          </div>
          <button
            className="ghost"
            onClick={async () => {
              const result = await api.reindex();
              setProblems(result.problems);
              load();
              onMetaChange();
              setRefreshKey((value) => value + 1);
            }}
            title="폴더를 직접 수정했을 때 다시 읽어들입니다"
          >
            다시 읽기
          </button>
          <button onClick={() => setCreating(true)}>과제 추가</button>
        </div>
      </div>

      {creating && (
        <div className="card">
          <h2>새 과제</h2>
          <ProjectForm
            meta={meta}
            submitLabel="만들기"
            onCancel={() => setCreating(false)}
            onSubmit={async (payload) => {
              const created = await api.createProject(payload);
              setCreating(false);
              onMetaChange();
              setRefreshKey((value) => value + 1);
              // 만들면 대개 곧바로 개요나 첫 기록을 쓴다. 상세로 데려간다.
              window.location.hash = `#/projects/${created.id}`;
            }}
          />
        </div>
      )}

      {error && <p className="form-error">{error}</p>}

      {problems.length > 0 && (
        <div className="card problems">
          <div className="card-head">
            <h2>읽지 못한 파일 {problems.length}건</h2>
            <button className="ghost small" onClick={() => setProblems([])}>
              닫기
            </button>
          </div>
          <p className="hint">
            md 파일 맨 위의 설정(front matter) 형식이 어긋났습니다. 아래 파일을 열어 고친 뒤 다시 읽어 주세요.
            나머지 과제는 정상적으로 표시됩니다.
          </p>
          <ul className="problem-list">
            {problems.map((problem) => (
              <li key={problem.path}>
                <code>{problem.path}</code>
                <span className="muted">{problem.reason}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {view === "board" && <ProjectBoard meta={meta} projects={projects} />}

      {view === "table" && (
      <table className="grid">
        <thead>
          <tr>
            <th>과제</th>
            <th>상태</th>
            <th>속성</th>
            <th>그룹</th>
            <th>담당자</th>
            <th>태그</th>
            <th>마감</th>
            <th>기록</th>
            <th>최근 업데이트</th>
          </tr>
        </thead>
        <tbody>
          {projects.map((project) => {
            const due = dueLabel(project.due_date, project.status);
            return (
              <tr key={project.id} onClick={() => (window.location.hash = `#/projects/${project.id}`)}>
                <td>
                  <span className="project-id">{project.id}</span>
                  <span className="project-title">{project.title}</span>
                </td>
                <td>
                  <StatusBadge status={project.status} meta={meta} />
                </td>
                <td>
                  <TypeBadge type={project.type} meta={meta} />
                </td>
                <td>{project.group ?? "—"}</td>
                <td className="owners">
                  {project.owners.length > 0 ? project.owners.join(", ") : "—"}
                </td>
                <td className="tags">
                  {project.tags.map((tag) => (
                    <span key={tag} className="tag">
                      {tag}
                    </span>
                  ))}
                </td>
                <td>
                  {/* 끝난 과제는 남은 날짜 없이 마감일만 보여 준다 */}
                  {due && <span className={`due due-${due.tone}`}>{due.text}</span>}
                  <span className="due-date">{formatDate(project.due_date)}</span>
                </td>
                <td>{project.entry_count}건</td>
                <td>{formatDate(project.updated_at)}</td>
              </tr>
            );
          })}
          {projects.length === 0 && (
            <tr>
              <td colSpan={9} className="empty">
                과제가 없습니다. [과제 추가]로 시작하세요.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      )}
    </section>
  );
}
