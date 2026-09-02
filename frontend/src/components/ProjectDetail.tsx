import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { filesBase, renderMarkdown } from "../markdown";
import type { Entry, Meta, Project, Report } from "../types";
import type { Attachment } from "../upload";
import { formatBytes } from "../upload";
import { dueLabel, formatDate } from "../util";
import AttachmentList from "./AttachmentList";
import EntryEditor from "./EntryEditor";
import ExportMenu from "./ExportMenu";
import ReportEditor from "./ReportEditor";
import ProjectForm from "./ProjectForm";
import StatusBadge, { TypeBadge } from "./StatusBadge";

interface Props {
  projectId: string;
  meta: Meta;
  onMetaChange: () => void;
  /** 보고 대상 화면에서 초안을 만들고 넘어온 경우 그 보고를 바로 연다. */
  openReportId?: number;
}

export default function ProjectDetail({ projectId, meta, onMetaChange, openReportId }: Props) {
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
  const [reports, setReports] = useState<Report[]>([]);
  const [openReport, setOpenReport] = useState<number | null>(openReportId ?? null);
  const [reportError, setReportError] = useState<string | null>(null);

  const load = useCallback(() => {
    Promise.all([
      api.getProject(projectId),
      api.listEntries(projectId),
      api.projectAttachments(projectId),
      api.listReports(projectId),
    ])
      .then(([loadedProject, loadedEntries, loadedFiles, loadedReports]) => {
        setProject(loadedProject);
        setEntries(loadedEntries);
        setFiles(loadedFiles);
        setReports(loadedReports);
      })
      .catch((err: Error) => setError(err.message));
  }, [projectId]);

  useEffect(load, [load]);
  useEffect(() => setOpenReport(openReportId ?? null), [openReportId]);

  if (error) return <p className="form-error">{error}</p>;
  if (!project) return <div className="app-loading">불러오는 중…</div>;

  const due = dueLabel(project.due_date);
  const base = filesBase(project.dir_name);
  const visibleEntries = entries.filter((entry) => entry.id !== draftEntryId);
  // 기록마다 붙은 첨부를 타임라인에서 바로 확인할 수 있게 묶어 둔다.
  const filesByEntry = new Map<number, Attachment[]>();
  for (const file of files.items) {
    if (file.entry_id === null) continue;
    const list = filesByEntry.get(file.entry_id) ?? [];
    list.push(file);
    filesByEntry.set(file.entry_id, list);
  }

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
              {project.type && <TypeBadge type={project.type} meta={meta} />}
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
              {project.owners.length > 0 && <span>담당 {project.owners.join(", ")}</span>}
              <span>최근 업데이트 {formatDate(project.updated_at)}</span>
            </div>
          </div>
          <div className="detail-actions">
            <ExportMenu projectId={project.id} />
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

      <div className="card reports-card">
        <div className="card-head">
          <h2>
            보고 이력 {reports.length}건
            {project.last_reported_at && (
              <span className="muted"> · 마지막 보고 {formatDate(project.last_reported_at)}</span>
            )}
          </h2>
          <button
            onClick={async () => {
              setReportError(null);
              try {
                const draft = await api.createDraft(project.id);
                setOpenReport(draft.id);
                load();
              } catch (err) {
                setReportError((err as Error).message);
              }
            }}
          >
            보고 초안 만들기
          </button>
        </div>
        {reportError && <p className="form-error">{reportError}</p>}
        {reports.length === 0 ? (
          <p className="hint">아직 보고 이력이 없습니다. 마지막 보고 이후의 진행일지로 초안을 만들 수 있습니다.</p>
        ) : (
          <ul className="report-list">
            {reports.map((report) => (
              <li key={report.id} className={report.frozen ? "frozen" : "draft"}>
                <button className="report-open" onClick={() => setOpenReport(report.id === openReport ? null : report.id)}>
                  <span className="report-date">{report.report_date}</span>
                  <span className="report-title">{report.title}</span>
                  <span className={report.frozen ? "frozen-tag" : "draft-tag"}>
                    {report.frozen ? "확정" : "작성 중"}
                  </span>
                  <span className="muted">진행일지 {report.entry_count}건</span>
                </button>
                <button
                  className="ghost small danger"
                  onClick={async () => {
                    if (!window.confirm(`${report.report_date} 보고를 보관함으로 옮길까요?`)) return;
                    await api.deleteReport(report.id);
                    setOpenReport(null);
                    load();
                  }}
                >
                  삭제
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {openReport !== null && reports.some((report) => report.id === openReport) && (
        <ReportEditorLoader
          reportId={openReport}
          dirName={project.dir_name}
          onChanged={load}
          onClose={() => setOpenReport(null)}
        />
      )}

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
              {(filesByEntry.get(entry.id) ?? []).length > 0 && (
                <div className="entry-files">
                  <span className="muted">첨부</span>
                  {(filesByEntry.get(entry.id) ?? []).map((file) => (
                    <a key={file.id} href={file.url} target="_blank" rel="noreferrer" className="file-chip">
                      {file.is_image ? "🖼" : "📄"} {file.orig_name}
                      <span className="muted">{formatBytes(file.size_bytes)}</span>
                    </a>
                  ))}
                </div>
              )}
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


function ReportEditorLoader({
  reportId,
  dirName,
  onChanged,
  onClose,
}: {
  reportId: number;
  dirName?: string;
  onChanged: () => void;
  onClose: () => void;
}) {
  const [report, setReport] = useState<Report | null>(null);

  const reload = useCallback(() => {
    api.getReport(reportId).then(setReport).catch(() => undefined);
  }, [reportId]);

  useEffect(reload, [reload]);

  if (!report) return null;
  return (
    <ReportEditor
      report={report}
      dirName={dirName}
      onChanged={() => {
        reload();
        onChanged();
      }}
      onClose={onClose}
    />
  );
}
