import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { Meta, Project } from "../types";
import { dueLabel, formatDate } from "../util";
import ProjectForm from "./ProjectForm";
import StatusBadge from "./StatusBadge";

interface Props {
  meta: Meta;
  onMetaChange: () => void;
}

export default function ProjectList({ meta, onMetaChange }: Props) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [filters, setFilters] = useState({ status: "", group: "", tag: "", sort: "updated" });
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
          <select value={filters.sort} onChange={(event) => setFilter("sort", event.target.value)}>
            <option value="updated">최근 업데이트순</option>
            <option value="due">마감일순</option>
            <option value="created">생성순</option>
            <option value="title">이름순</option>
          </select>
        </div>
        <div className="toolbar-actions">
          <button
            className="ghost"
            onClick={() => api.reindex().then(load).then(onMetaChange)}
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
              await api.createProject(payload);
              setCreating(false);
              load();
              onMetaChange();
            }}
          />
        </div>
      )}

      {error && <p className="form-error">{error}</p>}

      <table className="grid">
        <thead>
          <tr>
            <th>과제</th>
            <th>상태</th>
            <th>그룹</th>
            <th>태그</th>
            <th>마감</th>
            <th>기록</th>
            <th>최근 업데이트</th>
          </tr>
        </thead>
        <tbody>
          {projects.map((project) => {
            const due = dueLabel(project.due_date);
            return (
              <tr key={project.id} onClick={() => (window.location.hash = `#/projects/${project.id}`)}>
                <td>
                  <span className="project-id">{project.id}</span>
                  <span className="project-title">{project.title}</span>
                </td>
                <td>
                  <StatusBadge status={project.status} meta={meta} />
                </td>
                <td>{project.group ?? "—"}</td>
                <td className="tags">
                  {project.tags.map((tag) => (
                    <span key={tag} className="tag">
                      {tag}
                    </span>
                  ))}
                </td>
                <td>
                  {due ? <span className={`due due-${due.tone}`}>{due.text}</span> : "—"}
                  <span className="due-date">{formatDate(project.due_date)}</span>
                </td>
                <td>{project.entry_count}건</td>
                <td>{formatDate(project.updated_at)}</td>
              </tr>
            );
          })}
          {projects.length === 0 && (
            <tr>
              <td colSpan={7} className="empty">
                과제가 없습니다. [과제 추가]로 시작하세요.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </section>
  );
}
