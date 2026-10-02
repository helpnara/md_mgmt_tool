import { useState } from "react";
import { projectLink } from "../nav";
import type { Meta, Project } from "../types";
import { dueLabel, formatDate } from "../util";
import { TypeBadge, shownStatus } from "./StatusBadge";
import StageBand from "./StageBand";

interface Props {
  meta: Meta;
  projects: Project[];
  /** 고른 연도 — 있으면 칸은 그 해의 상태로 나뉜다 (TODO 184) */
  year?: string;
}

export default function ProjectBoard({ meta, projects, year }: Props) {
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
        // 연도를 고르면 그 해의 상태로 칸을 나눈다 — 목록의 상태 칸 · 홈의 숫자와 같은 기준 (TODO 184)
        const items = projects.filter((project) => shownStatus(project) === status.key);
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
                      onClick={() => (window.location.hash = projectLink(project.id))}
                    >
                      <div className="board-card-top">
                      <span className="project-id">{project.id}</span>
                      {shownStatus(project) !== project.status && (
                        <span
                          className="year-status-now"
                          title={`${year ? `${year}년` : "그 해"} 말에는 아직 ${status.label}이었습니다`}
                        >
                          → 지금 {meta.statuses.find((item) => item.key === project.status)?.label ?? project.status}
                        </span>
                      )}
                      </div>
                      <h3>
                        {project.title} <StageBand stage={project.stage} />
                      </h3>
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
