import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { renderMarkdown } from "../markdown";
import type { Entry, Meta, Project } from "../types";
import { dueLabel, formatDate } from "../util";
import EntryEditor from "./EntryEditor";
import ProjectForm from "./ProjectForm";
import StatusBadge from "./StatusBadge";

interface Props {
  projectId: string;
  meta: Meta;
  onMetaChange: () => void;
}

export default function ProjectDetail({ projectId, meta, onMetaChange }: Props) {
  const [project, setProject] = useState<Project | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [editingProject, setEditingProject] = useState(false);
  const [editingOverview, setEditingOverview] = useState(false);
  const [overviewDraft, setOverviewDraft] = useState("");
  const [creatingEntry, setCreatingEntry] = useState(false);
  const [editingEntryId, setEditingEntryId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    Promise.all([api.getProject(projectId), api.listEntries(projectId)])
      .then(([loadedProject, loadedEntries]) => {
        setProject(loadedProject);
        setEntries(loadedEntries);
      })
      .catch((err: Error) => setError(err.message));
  }, [projectId]);

  useEffect(load, [load]);

  if (error) return <p className="form-error">{error}</p>;
  if (!project) return <div className="app-loading">불러오는 중…</div>;

  const due = dueLabel(project.due_date);

  return (
    <section className="project-detail">
      <a className="back" href="#/">
        ← 과제 목록
      </a>

      <div className="card">
        <div className="detail-head">
          <div>
            <span className="project-id">{project.id}</span>
            <h1>{project.title}</h1>
            <div className="meta-line">
              <StatusBadge status={project.status} meta={meta} />
              {project.group && <span className="chip">{project.group}</span>}
              {project.tags.map((tag) => (
                <span key={tag} className="tag">
                  {tag}
                </span>
              ))}
            </div>
            <div className="meta-line muted">
              기간 {formatDate(project.start_date)} ~ {formatDate(project.due_date)}
              {due && <span className={`due due-${due.tone}`}>{due.text}</span>}
              {project.owner && <span>담당 {project.owner}</span>}
              <span>최근 업데이트 {formatDate(project.updated_at)}</span>
            </div>
          </div>
          <div className="detail-actions">
            <button className="ghost" onClick={() => setEditingProject((value) => !value)}>
              {editingProject ? "닫기" : "과제 정보 수정"}
            </button>
            <button
              className="ghost danger"
              onClick={async () => {
                if (!window.confirm("이 과제를 보관함(.trash)으로 옮길까요?")) return;
                await api.archiveProject(project.id);
                window.location.hash = "#/";
              }}
            >
              보관
            </button>
          </div>
        </div>

        {editingProject && (
          <ProjectForm
            meta={meta}
            initial={project}
            submitLabel="저장"
            onCancel={() => setEditingProject(false)}
            onSubmit={async (payload) => {
              await api.updateProject(project.id, payload);
              setEditingProject(false);
              load();
              onMetaChange();
            }}
          />
        )}
      </div>

      <div className="card">
        <div className="card-head">
          <h2>과제 개요</h2>
          <button
            className="ghost"
            onClick={() => {
              setOverviewDraft(project.body ?? "");
              setEditingOverview((value) => !value);
            }}
          >
            {editingOverview ? "취소" : "수정"}
          </button>
        </div>
        {editingOverview ? (
          <>
            <div className="split">
              <textarea
                value={overviewDraft}
                onChange={(event) => setOverviewDraft(event.target.value)}
                spellCheck={false}
              />
              <div
                className="preview markdown"
                dangerouslySetInnerHTML={{ __html: renderMarkdown(overviewDraft) }}
              />
            </div>
            <div className="form-actions">
              <button
                onClick={async () => {
                  await api.updateProject(project.id, { body: overviewDraft });
                  setEditingOverview(false);
                  load();
                }}
              >
                저장
              </button>
            </div>
          </>
        ) : (
          <div
            className="markdown"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(project.body ?? "") }}
          />
        )}
      </div>

      <div className="card-head timeline-head">
        <h2>수행 이력 ({entries.length}건)</h2>
        <button onClick={() => setCreatingEntry(true)}>기록 추가</button>
      </div>

      {creatingEntry && (
        <EntryEditor
          onCancel={() => setCreatingEntry(false)}
          onSave={async (payload) => {
            await api.createEntry(project.id, payload);
            setCreatingEntry(false);
            load();
            onMetaChange();
          }}
        />
      )}

      <ol className="timeline">
        {entries.map((entry) =>
          editingEntryId === entry.id ? (
            <li key={entry.id}>
              <EntryEditor
                initial={entry}
                onCancel={() => setEditingEntryId(null)}
                onSave={async (payload) => {
                  await api.updateEntry(entry.id, payload);
                  setEditingEntryId(null);
                  load();
                  onMetaChange();
                }}
              />
            </li>
          ) : (
            <li key={entry.id} className="card entry">
              <div className="entry-head">
                <div>
                  <span className="entry-date">{entry.date}</span>
                  <h3>{entry.title}</h3>
                  {entry.tags.map((tag) => (
                    <span key={tag} className="tag">
                      {tag}
                    </span>
                  ))}
                </div>
                <div className="entry-actions">
                  <button className="ghost" onClick={() => setEditingEntryId(entry.id)}>
                    수정
                  </button>
                  <button
                    className="ghost danger"
                    onClick={async () => {
                      if (!window.confirm("이 기록을 보관함으로 옮길까요?")) return;
                      await api.deleteEntry(entry.id);
                      load();
                    }}
                  >
                    삭제
                  </button>
                </div>
              </div>
              <div
                className="markdown"
                dangerouslySetInnerHTML={{ __html: renderMarkdown(entry.body ?? "") }}
              />
            </li>
          ),
        )}
        {entries.length === 0 && !creatingEntry && (
          <li className="empty card">아직 기록이 없습니다. [기록 추가]로 첫 진행 내용을 남겨 보세요.</li>
        )}
      </ol>
    </section>
  );
}
