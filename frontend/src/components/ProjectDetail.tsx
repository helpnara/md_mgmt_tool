import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { filesBase, renderMarkdown } from "../markdown";
import type { Entry, Meta, Project } from "../types";
import type { Attachment } from "../upload";
import { formatBytes } from "../upload";
import { dueLabel, formatDate } from "../util";
import AttachmentList from "./AttachmentList";
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
  // 첨부 때문에 편집 도중 먼저 만들어진 기록. 편집기 아래 타임라인에 중복 표시하지 않는다.
  const [draftEntryId, setDraftEntryId] = useState<number | null>(null);
  const [editingEntryId, setEditingEntryId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [files, setFiles] = useState<{ items: Attachment[]; total_bytes: number; orphan_count: number }>(
    { items: [], total_bytes: 0, orphan_count: 0 },
  );
  const [showFiles, setShowFiles] = useState(false);

  const load = useCallback(() => {
    Promise.all([
      api.getProject(projectId),
      api.listEntries(projectId),
      api.projectAttachments(projectId),
    ])
      .then(([loadedProject, loadedEntries, loadedFiles]) => {
        setProject(loadedProject);
        setEntries(loadedEntries);
        setFiles(loadedFiles);
      })
      .catch((err: Error) => setError(err.message));
  }, [projectId]);

  useEffect(load, [load]);

  if (error) return <p className="form-error">{error}</p>;
  if (!project) return <div className="app-loading">불러오는 중…</div>;

  const due = dueLabel(project.due_date);
  const base = filesBase(project.dir_name);
  const visibleEntries = entries.filter((entry) => entry.id !== draftEntryId);

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
                dangerouslySetInnerHTML={{ __html: renderMarkdown(overviewDraft, base) }}
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
            dangerouslySetInnerHTML={{ __html: renderMarkdown(project.body ?? "", base) }}
          />
        )}
      </div>

      <div className="card">
        <div className="card-head">
          <h2>
            첨부 자료 {files.items.length}건 · {formatBytes(files.total_bytes)}
            {files.orphan_count > 0 && (
              <span className="orphan-tag">본문에서 쓰지 않는 파일 {files.orphan_count}건</span>
            )}
          </h2>
          <button className="ghost" onClick={() => setShowFiles((value) => !value)}>
            {showFiles ? "접기" : "펼치기"}
          </button>
        </div>
        {showFiles && (
          <AttachmentList
            attachments={files.items}
            onDelete={async (attachment) => {
              if (!window.confirm(`${attachment.orig_name} 을(를) 보관함으로 옮길까요?`)) return;
              await api.deleteAttachment(attachment.id);
              load();
            }}
          />
        )}
      </div>

      <div className="card-head timeline-head">
        <h2>수행 이력 ({entries.length}건)</h2>
        <button onClick={() => setCreatingEntry(true)}>기록 추가</button>
      </div>

      {creatingEntry && (
        <EntryEditor
          projectId={project.id}
          dirName={project.dir_name}
          onCancel={() => {
            setCreatingEntry(false);
            setDraftEntryId(null);
            load();
          }}
          onSaved={(entry, options) => {
            if (options.close) {
              setCreatingEntry(false);
              setDraftEntryId(null);
            } else {
              setDraftEntryId(entry.id);
            }
            load();
            onMetaChange();
          }}
        />
      )}

      <ol className="timeline">
        {visibleEntries.map((entry) =>
          editingEntryId === entry.id ? (
            <li key={entry.id}>
              <EntryEditor
                projectId={project.id}
                dirName={project.dir_name}
                initial={entry}
                onCancel={() => {
                  setEditingEntryId(null);
                  load();
                }}
                onSaved={(_saved, options) => {
                  if (options.close) setEditingEntryId(null);
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
                dangerouslySetInnerHTML={{ __html: renderMarkdown(entry.body ?? "", base) }}
              />
            </li>
          ),
        )}
        {visibleEntries.length === 0 && !creatingEntry && (
          <li className="empty card">아직 기록이 없습니다. [기록 추가]로 첫 진행 내용을 남겨 보세요.</li>
        )}
      </ol>
    </section>
  );
}
