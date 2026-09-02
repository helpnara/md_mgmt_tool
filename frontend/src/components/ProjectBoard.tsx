import { useState } from "react";
import type { Meta, Project } from "../types";
import { dueLabel, formatDate } from "../util";
import { TypeBadge } from "./StatusBadge";

interface Props {
  meta: Meta;
  projects: Project[];
}

export default function ProjectBoard({ meta, projects }: Props) {
  // 완료·중단은 기본으로 접어 둔다 (평소에는 볼 일이 적다).
  const [collapsed, setCollapsed] = useState<Set<string>>(
    () => new Set(meta.statuses.filter((status) => status.collapsed).map((status) => status.key)),
  );

  function toggle(key: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <div className="board">
      {meta.statuses.map((status) => {
        const items = projects.filter((project) => project.status === status.key);
        const isCollapsed = collapsed.has(status.key);
        return (
          <section
            key={status.key}
            className={`board-column${isCollapsed ? " collapsed" : ""}`}
          >
            <header onClick={() => toggle(status.key)}>
              <span className={`status status-${status.key}`}>{status.label}</span>
              <span className="count">{items.length}</span>
            </header>
            {!isCollapsed && (
              <div className="board-cards">
                {items.map((project) => {
                  const due = dueLabel(project.due_date, project.status);
                  return (
                    <article
                      key={project.id}
                      className="board-card"
                      onClick={() => (window.location.hash = `#/projects/${project.id}`)}
                    >
                      <span className="project-id">{project.id}</span>
                      <h3>{project.title}</h3>
                      <div className="board-meta">
                        {project.type && <TypeBadge type={project.type} meta={meta} />}
                        {project.group && <span className="chip">{project.group}</span>}
                        {project.owners.length > 0 && (
                          <span className="owner-chip">{project.owners.join(", ")}</span>
                        )}
                        {project.tags.map((tag) => (
                          <span key={tag} className="tag">
                            {tag}
                          </span>
                        ))}
                      </div>
                      <div className="board-foot">
                        {due ? <span className={`due due-${due.tone}`}>{due.text}</span> : <span />}
                        <span className="muted">
                          기록 {project.entry_count}건 · {formatDate(project.updated_at)}
                        </span>
                      </div>
                    </article>
                  );
                })}
                {items.length === 0 && <p className="board-empty">없음</p>}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
