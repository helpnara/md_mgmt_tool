import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { filesBase, renderMarkdown } from "../markdown";
import type { Entry, Meta, Project, Report } from "../types";
import type { Attachment } from "../upload";
import { formatBytes } from "../upload";
import { daysUntil, dueLabel, formatDate, formatDateTime, periodText } from "../util";
import AttachmentList from "./AttachmentList";
import EntryEditor from "./EntryEditor";
import ExportMenu from "./ExportMenu";
import ReportEditor from "./ReportEditor";
import PreviewToggle, { usePreview } from "./PreviewToggle";
import ProjectForm from "./ProjectForm";
import StatusBadge, { TypeBadge } from "./StatusBadge";

interface Props {
  projectId: string;
  meta: Meta;
  onMetaChange: () => void;
  /** 보고 대상 화면에서 초안을 만들고 넘어온 경우 그 보고를 바로 연다. */
  openReportId?: number;
  /** 검색 결과에서 넘어온 경우 그 진행일지로 이동해 잠깐 강조한다. */
  openEntryId?: number;
}

export default function ProjectDetail({
  projectId,
  meta,
  onMetaChange,
  openReportId,
  openEntryId,
}: Props) {
  const [project, setProject] = useState<Project | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [editingProject, setEditingProject] = useState(false);
  const [editingOverview, setEditingOverview] = useState(false);
  const [preview, togglePreview] = usePreview();
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
  // 기록이 쌓이면 전부 펼쳐져 스크롤이 길어진다. 최근 것만 펼쳐 둔다.
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
  const [expandAll, setExpandAll] = useState(false);
  const [highlightEntryId, setHighlightEntryId] = useState<number | null>(null);

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

  // 검색 결과에서 넘어왔다면 그 기록을 펼치고 화면에 보이게 한다.
  useEffect(() => {
    if (!openEntryId || entries.length === 0) return;
    setExpandedIds((prev) => new Set(prev).add(openEntryId));
    setHighlightEntryId(openEntryId);
    const timer = window.setTimeout(() => {
      document.getElementById(`entry-${openEntryId}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 100);
    const clear = window.setTimeout(() => setHighlightEntryId(null), 2600);
    return () => {
      window.clearTimeout(timer);
      window.clearTimeout(clear);
    };
  }, [openEntryId, entries.length]);

  if (error) return <p className="form-error">{error}</p>;
  if (!project) return <div className="app-loading">불러오는 중…</div>;

  const due = dueLabel(project.due_date, project.status);
  // 개요(index.md)는 과제 폴더 바로 아래에 있어 첨부 링크가 assets/… 이고,
  // 진행일지는 logs/ 안에 있어 ../assets/… 이다. 기준 경로가 서로 다르다.
  const base = filesBase(project.dir_name);
  const entryBase = filesBase(project.dir_name, "logs");
  // 편집기를 연 동안에는 2단을 잠시 1단으로 돌려 전체 폭을 쓴다.
  const editingSide: "left" | "right" | null =
    creatingEntry || editingEntryId !== null
      ? "right"
      : editingOverview || openReport !== null
        ? "left"
        : null;
  // 마지막 보고로부터 며칠 지났는지 (요약 바에 표시)
  const sinceLastReport = project.last_reported_at
    ? Math.max(0, -(daysUntil(project.last_reported_at) ?? 0))
    : null;
  const visibleEntries = entries.filter((entry) => entry.id !== draftEntryId);
  const AUTO_OPEN = 5;
  const isOpen = (entry: Entry, index: number) =>
    expandAll || index < AUTO_OPEN || expandedIds.has(entry.id);
  const collapsedCount = Math.max(0, visibleEntries.length - AUTO_OPEN);
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

      <div className="card detail-header">
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
              <span>{periodText(project.start_date, project.due_date)}</span>
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

        <dl className="summary-bar">
          <div>
            <dt>수행 이력</dt>
            <dd>{project.entry_count}건</dd>
          </div>
          <div>
            <dt>미보고</dt>
            <dd className={(project.unreported_entries ?? 0) > 0 ? "accent" : undefined}>
              {project.unreported_entries ?? 0}건
            </dd>
          </div>
          <div>
            <dt>보고 이력</dt>
            <dd>{project.report_count ?? 0}건</dd>
          </div>
          <div>
            <dt>마지막 보고</dt>
            <dd>
              {project.last_reported_at ? (
                <>
                  {formatDate(project.last_reported_at)}
                  {sinceLastReport !== null && <span className="muted"> · D+{sinceLastReport}</span>}
                </>
              ) : (
                <span className="muted">없음</span>
              )}
            </dd>
          </div>
          <div>
            <dt>첨부</dt>
            <dd>
              {project.attachment_count ?? 0}건
              <span className="muted"> · {formatBytes(project.attachment_bytes ?? 0)}</span>
            </dd>
          </div>
        </dl>

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

      <div className={`detail-columns${editingSide ? ` editing editing-${editingSide}` : ""}`}>
      <div className="detail-left">

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
            <PreviewToggle on={preview} onToggle={togglePreview} />
            <div className={preview ? "split" : "split solo"}>
              <textarea
                value={overviewDraft}
                onChange={(event) => setOverviewDraft(event.target.value)}
                spellCheck={false}
              />
              {preview && (
                <div
                  className="preview markdown"
                  dangerouslySetInnerHTML={{ __html: renderMarkdown(overviewDraft, base) }}
                />
              )}
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
                  {report.audience ? (
                    <span className="report-audience" title={report.audience}>{report.audience}</span>
                  ) : (
                    <span className="report-audience missing">(피보고자 미입력)</span>
                  )}
                  {report.frozen ? (
                    <span className="report-done" title={`보고 완료(${formatDateTime(report.frozen_at)})`}>
                      보고 완료({formatDateTime(report.frozen_at)})
                    </span>
                  ) : (
                    <span className="draft-tag">작성 중</span>
                  )}
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
          audiences={meta.audiences}
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

      </div>
      <div className="detail-right">

      <div className="card-head timeline-head">
        <h2>수행 이력 ({entries.length}건)</h2>
        <div className="timeline-actions">
          {collapsedCount > 0 && (
            <button className="ghost small" onClick={() => setExpandAll((value) => !value)}>
              {expandAll ? `최근 ${AUTO_OPEN}건만 보기` : `모두 펼치기 (+${collapsedCount})`}
            </button>
          )}
          <button onClick={() => setCreatingEntry(true)}>기록 추가</button>
        </div>
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
        {visibleEntries.map((entry, index) =>
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
            <li
              key={entry.id}
              id={`entry-${entry.id}`}
              className={`card entry${isOpen(entry, index) ? "" : " collapsed"}${
                highlightEntryId === entry.id ? " highlight" : ""
              }`}
            >
              <div
                className="entry-head"
                onClick={() =>
                  setExpandedIds((prev) => {
                    const next = new Set(prev);
                    if (next.has(entry.id)) next.delete(entry.id);
                    else next.add(entry.id);
                    return next;
                  })
                }
              >
                <div>
                  <span className="entry-date">
                    {entry.date}
                    {entry.author && <span className="entry-author">{entry.author}</span>}
                  </span>
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
              {isOpen(entry, index) && (
                <div
                  className="markdown"
                  dangerouslySetInnerHTML={{ __html: renderMarkdown(entry.body ?? "", entryBase) }}
                />
              )}
              {isOpen(entry, index) && (filesByEntry.get(entry.id) ?? []).length > 0 && (
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

      </div>
      </div>
    </section>
  );
}


function ReportEditorLoader({
  reportId,
  dirName,
  audiences,
  onChanged,
  onClose,
}: {
  reportId: number;
  dirName?: string;
  audiences: string[];
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
      audiences={audiences}
      onChanged={() => {
        reload();
        onChanged();
      }}
      onClose={onClose}
    />
  );
}
