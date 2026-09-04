import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { filesBase, renderMarkdown } from "../markdown";
import { backTarget, projectLink } from "../nav";
import type { Entry, Meta, Project, Report } from "../types";
import type { Attachment } from "../upload";
import { formatBytes, uploadAttachment } from "../upload";
import { pasteAsTable } from "../table";
import { todayIso, daysUntil, dueLabel, effectText, EFFECT_UNIT, formatDate, formatDateTime, periodText, scrollEditorIntoView } from "../util";
import AttachmentList from "./AttachmentList";
import EntryEditor from "./EntryEditor";
import VersionPanel from "./VersionPanel";
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
  /** 어느 화면에서 들어왔는지 (nav.ts). 뒤로 가기가 그리로 돌아간다. */
  back?: string | null;
}

export default function ProjectDetail({
  projectId,
  meta,
  onMetaChange,
  openReportId,
  openEntryId,
  back,
}: Props) {
  const [project, setProject] = useState<Project | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [editingProject, setEditingProject] = useState(false);
  const [editingOverview, setEditingOverview] = useState(false);
  const [showOverviewVersions, setShowOverviewVersions] = useState(false);
  const [preview, togglePreview] = usePreview();
  const overviewRef = useRef<HTMLDivElement>(null);
  // 개요에 직접 붙이는 첨부 — 효과 산출 근거(엑셀·PPT)를 위한 자리다.
  const overviewFileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [overviewDraft, setOverviewDraft] = useState("");
  const [creatingEntry, setCreatingEntry] = useState(false);
  // [이어쓰기]로 시작하면 지난 기록의 내용을 담아 온다. 없으면 서식에서 시작한다.
  const [entrySeed, setEntrySeed] = useState<string | null>(null);
  // 첨부 때문에 편집 도중 먼저 만들어진 기록. 편집기 아래 타임라인에 중복 표시하지 않는다.
  const [draftEntryId, setDraftEntryId] = useState<number | null>(null);
  const [editingEntryId, setEditingEntryId] = useState<number | null>(null);
  // 편집을 닫으면 배치가 다시 2단으로 돌아가므로, 고치던 기록 자리로 되돌려 놓는다.
  const lastEditedEntry = useRef<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [files, setFiles] = useState<{ items: Attachment[]; total_bytes: number; orphan_count: number }>(
    { items: [], total_bytes: 0, orphan_count: 0 },
  );
  const [showFiles, setShowFiles] = useState(false);
  const [reports, setReports] = useState<Report[]>([]);
  const [openReport, setOpenReport] = useState<number | null>(openReportId ?? null);
  // 보고 초안을 만들 때 쓸 날짜. 기본값은 다음 보고 예정일(주간 기준 화요일)이고
  // 그대로 두면 지금까지와 같지만, 여기서 바꿔 만들 수 있다.
  const [draftDate, setDraftDate] = useState("");
  const [reportError, setReportError] = useState<string | null>(null);
  // 기록이 쌓이면 전부 펼쳐져 스크롤이 길어진다. 최근 것만 펼쳐 둔다.
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
  const [expandAll, setExpandAll] = useState(false);
  const [entryFind, setEntryFind] = useState("");
  const [highlightEntryId, setHighlightEntryId] = useState<number | null>(null);

  const load = useCallback(() => {
    Promise.all([
      api.getProject(projectId),
      api.listEntries(projectId),
      api.projectAttachments(projectId),
      api.listReports(projectId),
    ])
      .then(([loadedProject, loadedEntries, loadedFiles, loadedReports]) => {
        setError(null);
        setProject(loadedProject);
        setEntries(loadedEntries);
        setFiles(loadedFiles);
        setReports(loadedReports);
      })
      .catch((err: Error) => setError(err.message));
  }, [projectId]);

  useEffect(load, [load]);
  useEffect(() => setOpenReport(openReportId ?? null), [openReportId]);

  // 다음 보고 예정일을 기본값으로 채워 둔다 (서버가 주간 주기로 계산한다).
  useEffect(() => {
    if (draftDate) return;
    api
      .reportCandidates()
      .then((data) => setDraftDate(data.default_report_date))
      .catch(() => setDraftDate(todayIso()));
  }, [draftDate]);

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

  // 개요에 파일을 붙이고, 링크를 개요 본문 끝에 이어 붙인다.
  const attachToOverview = useCallback(
    async (files: File[]) => {
      if (files.length === 0 || !project) return;
      setUploadError(null);
      const links: string[] = [];
      try {
        for (const file of files) {
          setUploading(file.name);
          const saved = await uploadAttachment(
            `/api/projects/${project.id}/attachments`,
            file,
            () => undefined,
          ).promise;
          links.push(saved.markdown);
        }
        const body = `${(project.body ?? "").replace(/\s*$/, "")}\n\n${links.join("\n")}\n`;
        await api.updateProject(project.id, { body });
        load();
      } catch (err) {
        setUploadError((err as Error).message);
      } finally {
        setUploading(null);
      }
    },
    [project, load],
  );

  // 개요 편집을 열면 그 카드로 데려간다 (좌측 칸이 맨 위로 올라오기 때문).
  useEffect(() => {
    if (editingOverview) scrollEditorIntoView(overviewRef.current);
  }, [editingOverview]);

  // 진행일지 편집을 닫으면 2단으로 되돌아가면서 그 기록이 다시 아래로 내려간다.
  // 방금 고치던 자리로 데려다 놓는다.
  useEffect(() => {
    if (editingEntryId !== null) {
      lastEditedEntry.current = editingEntryId;
      return;
    }
    const entryId = lastEditedEntry.current;
    if (entryId === null) return;
    lastEditedEntry.current = null;
    scrollEditorIntoView(document.getElementById(`entry-${entryId}`), "center");
  }, [editingEntryId]);

  if (error) {
    // 과제 번호를 일괄로 바꾸면 예전 주소(즐겨찾기·열어 둔 탭)가 없는 과제를 가리킨다.
    // 빈 오류만 띄우면 사용자는 자료가 사라진 줄 안다. 무슨 일이 있었는지 알려 준다.
    const missing = error.includes("찾을 수 없");
    return (
      <section className="project-detail">
        <a className="back" href={backTarget(back).href}>
          ← {backTarget(back).label}
        </a>
        <div className="card">
          <h2>{missing ? "이 과제를 찾을 수 없습니다" : "과제를 불러오지 못했습니다"}</h2>
          <p className="hint">
            <code>{projectId}</code>
            {missing ? (
              <>
                {" "}번 과제가 없습니다. <b>과제 번호가 바뀌었거나</b> 보관함으로 옮겨졌을 수
                있습니다.
                <br />
                번호를 일괄로 바꾸면 예전 주소·즐겨찾기는 더 이상 맞지 않습니다.
                과제 목록에서 이름으로 찾아 주세요.
              </>
            ) : (
              <> — {error}</>
            )}
          </p>
          <div className="form-actions">
            {!missing && (
              <button className="ghost" onClick={load}>
                다시 시도
              </button>
            )}
            <a className="button-like primary-link" href="#/">
              과제 목록으로
            </a>
          </div>
        </div>
      </section>
    );
  }
  if (!project) return <div className="app-loading">불러오는 중…</div>;

  const due = dueLabel(project.due_date, project.status);
  // 개요(index.md)는 과제 폴더 바로 아래에 있어 첨부 링크가 assets/… 이고,
  // 진행일지는 logs/ 안에 있어 ../assets/… 이다. 기준 경로가 서로 다르다.
  // renderEntry 는 아래에 선언된 함수라 project 가 null 이 아님을 스스로 알지 못한다.
  // 여기서 좁혀진 값을 붙잡아 넘긴다.
  const current = project;
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
  const kept = entries.filter((entry) => entry.id !== draftEntryId);
  // 이 과제 안에서만 찾는다. 접힌 기록은 화면에 글자 자체가 없어 브라우저 찾기로도
  // 안 걸리기 때문이다 (TODO 68). 걸린 기록은 아래에서 자동으로 펼친다.
  const needle = entryFind.trim().toLowerCase();
  const matches = (entry: Entry) =>
    !needle ||
    `${entry.title} ${entry.body ?? ""} ${entry.tags.join(" ")} ${entry.date}`
      .toLowerCase()
      .includes(needle);
  const visibleEntries = needle ? kept.filter(matches) : kept;
  // 가장 최근 확정 보고에 담긴 기록 중 목록에서 맨 위에 오는 것 — 그 위에 선을 긋는다.
  const latestReportBoundary = project.last_reported_at
    ? visibleEntries.find((entry) => entry.reported_on === project.last_reported_at)?.id ?? null
    : null;

  const AUTO_OPEN = 5;
  const isOpen = (entry: Entry, index: number) =>
    // 찾는 중이면 걸린 기록을 모두 펼친다 — 접힌 채로는 왜 걸렸는지 알 수 없다.
    Boolean(needle) || expandAll || index < AUTO_OPEN || expandedIds.has(entry.id);
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
      {/* 온 곳이 주소에 실려 있으면 그리로, 없으면 지금까지처럼 과제 목록으로. */}
      <a className="back" href={backTarget(back).href}>
        ← {backTarget(back).label}
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
                // 보관한 과제는 사라진다. 온 곳이 목록 성격이면 그리로 돌려보낸다.
                window.location.hash = backTarget(back).href;
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
            <dt>효과 <span className="muted">{EFFECT_UNIT}</span></dt>
            <dd>
              {(() => {
                const effect = effectText(project.effect_expected, project.effect_verified);
                if (!effect) return <span className="muted">미입력</span>;
                return (
                  <span className={effect.verified ? "accent" : undefined}>
                    {effect.text}
                    {!effect.verified && <span className="muted"> · 기대</span>}
                  </span>
                );
              })()}
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
            onMetaChange={onMetaChange}
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

      <div
        className="card"
        ref={overviewRef}
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          void attachToOverview(Array.from(event.dataTransfer.files));
        }}
      >
        <div className="card-head">
          <h2>과제 개요</h2>
          <div className="overview-actions">
            <input
              ref={overviewFileRef}
              type="file"
              multiple
              hidden
              onChange={(event) => {
                void attachToOverview(Array.from(event.target.files ?? []));
                event.target.value = "";
              }}
            />
            <button
              className="attach-button"
              disabled={uploading !== null}
              onClick={() => overviewFileRef.current?.click()}
              title="효과 산출 근거 등 과제에 딸린 자료를 붙입니다 (엑셀·PPT·PDF·이미지)"
            >
              {uploading ? `올리는 중… ${uploading}` : "📎 파일 첨부"}
            </button>
            <button
              className={showOverviewVersions ? "ghost on" : "ghost"}
              onClick={() => setShowOverviewVersions((value) => !value)}
              title="과제 개요의 이전 내용으로 되돌립니다."
            >
              이전 버전
            </button>
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
        </div>
        {uploadError && <p className="form-error">{uploadError}</p>}
        {showOverviewVersions && (
          <VersionPanel
            path={`projects/${project.dir_name}/index.md`}
            onRestored={() => {
              setEditingOverview(false);
              load();
            }}
          />
        )}
        {editingOverview ? (
          <>
            <PreviewToggle on={preview} onToggle={togglePreview} />
            <div className={preview ? "split" : "split solo"}>
              <textarea
                value={overviewDraft}
                onChange={(event) => setOverviewDraft(event.target.value)}
                onPaste={(event) =>
                  pasteAsTable(event, (snippet) =>
                    setOverviewDraft((prev) => `${prev.replace(/\s*$/, "")}\n${snippet}`),
                  )
                }
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
          <div className="draft-controls">
            <input
              type="date"
              value={draftDate}
              onChange={(event) => setDraftDate(event.target.value)}
              title="이 날짜로 보고 초안을 만듭니다. 만든 뒤에도 바꿀 수 있습니다."
            />
            <button
              disabled={!draftDate}
              onClick={async () => {
                setReportError(null);
                try {
                  const draft = await api.createDraft(project.id, draftDate);
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
                    /* 확정 시각까지 적으면 줄이 길어지고, 정작 중요한 것은 '보고일'이다.
                       확정 시각은 마우스를 올리면 보인다. */
                    <span
                      className="report-done"
                      title={`확정 ${formatDateTime(report.frozen_at)}`}
                    >
                      보고 완료
                    </span>
                  ) : (
                    <span className="draft-tag">작성 중</span>
                  )}
                  <span className="muted">진행일지 {report.entry_count}건</span>
                </button>
                {/* 확정된 보고는 여기서도 못 지운다 — 편집기와 말이 맞아야 한다 (TODO 61).
                    지우려면 [확정 해제] 를 먼저 누르게 한다. */}
                <button
                  className="ghost small danger"
                  disabled={report.frozen}
                  title={
                    report.frozen
                      ? "확정된 보고는 지울 수 없습니다. 열어서 [확정 해제]를 먼저 눌러 주세요."
                      : undefined
                  }
                  onClick={async () => {
                    if (!window.confirm(`${report.report_date} 보고를 보관함으로 옮길까요?`)) return;
                    try {
                      await api.deleteReport(report.id);
                      setOpenReport(null);
                      load();
                    } catch (err) {
                      setReportError((err as Error).message);
                    }
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
          docPath={`projects/${project.dir_name}/${
            reports.find((item) => item.id === openReport)?.rel_path ?? ""
          }`}
          onChanged={load}
          onClose={() => setOpenReport(null)}
          onDeleted={() => {
            setOpenReport(null);
            // 주소에 지운 보고가 남아 있으면 새로고침했을 때 없는 문서를 열려 한다.
            // projectLink 가 온 곳(back)은 그대로 두고 report 만 뗀다.
            window.history.replaceState(null, "", projectLink(project.id));
            load();
          }}
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
        <h2>
          수행 이력 ({entries.length}건)
          {needle && <span className="muted"> · 찾은 것 {visibleEntries.length}건</span>}
        </h2>
        <div className="timeline-actions">
          {/* 이 과제 안에서만 찾는다. 상단 검색은 전체를 훑지만, 여기서는
              "이 과제의 그 기록" 하나를 찾는 일이 더 흔하다 (TODO 68). */}
          <input
            type="search"
            className="entry-find"
            value={entryFind}
            onChange={(event) => setEntryFind(event.target.value)}
            placeholder="이 과제에서 찾기"
            aria-label="이 과제의 진행일지에서 찾기"
          />
          {collapsedCount > 0 && !needle && (
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
          knownTags={meta.tags}
          dirName={project.dir_name}
          initial={{ body: entrySeed ?? project.entry_template ?? "" }}
          onCancel={() => {
            setCreatingEntry(false);
            setEntrySeed(null);
            setDraftEntryId(null);
            load();
          }}
          onSaved={(entry, options) => {
            if (options.close) {
              setCreatingEntry(false);
              setEntrySeed(null);
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
        {visibleEntries.map((entry, index) => (
          <Fragment key={entry.id}>
            {/* 선은 **가장 최근 보고 하나만** 긋는다 (TODO 35).
                보고마다 그으면 이력이 쌓일수록 선이 늘어 정작 경계가 안 보인다.
                그 아래에서 개별 기록의 보고 여부는 각 기록의 [미보고] 딱지가 말해 준다. */}
            {entry.id === latestReportBoundary && (
              <li className="report-marker" aria-hidden="true">
                <span>여기까지 {entry.reported_on} 보고함</span>
              </li>
            )}
            {renderEntry(entry, index)}
          </Fragment>
        ))}
        {visibleEntries.length === 0 && !creatingEntry && (
          <li className="empty card">
            {needle
              ? `"${entryFind.trim()}" 이(가) 든 기록이 없습니다.`
              : "아직 기록이 없습니다. [기록 추가]로 첫 진행 내용을 남겨 보세요."}
          </li>
        )}
      </ol>

      </div>
      </div>
    </section>
  );

  function renderEntry(entry: Entry, index: number) {
    return (
        editingEntryId === entry.id ? (
            <li key={entry.id}>
              <EntryEditor
                projectId={current.id}
                knownTags={meta.tags}
                dirName={current.dir_name}
                initial={entry}
                docPath={`projects/${current.dir_name}/${entry.rel_path}`}
                onRestored={() => {
                  setEditingEntryId(null);
                  load();
                }}
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
                  {/* 보고 여부는 기록 자체에 붙인다 (TODO 35).
                      선만으로는 "8/25 보고 뒤에 8/20 자로 쓴 기록"을 표현할 수 없다 —
                      날짜순으로는 선 아래에 놓이는데 실제로는 미보고이기 때문이다. */}
                  {!entry.reported_on && (
                    <span className="tag unreported" title="아직 확정된 보고에 담기지 않았습니다.">
                      미보고
                    </span>
                  )}
                  {entry.tags.map((tag) => (
                    <span key={tag} className="tag">
                      {tag}
                    </span>
                  ))}
                </div>
                <div className="entry-actions">
                  <button
                    className="ghost"
                    title="이 기록의 내용을 가져와 오늘 날짜로 새 기록을 씁니다"
                    onClick={(event) => {
                      event.stopPropagation();
                      setEntrySeed(entry.body ?? "");
                      setCreatingEntry(true);
                    }}
                  >
                    이어쓰기
                  </button>
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
          )
    );
  }
}


function ReportEditorLoader({
  reportId,
  dirName,
  audiences,
  onChanged,
  onClose,
  onDeleted,
  docPath,
}: {
  reportId: number;
  dirName?: string;
  audiences: string[];
  onChanged: () => void;
  onClose: () => void;
  onDeleted: () => void;
  docPath?: string;
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
      onDeleted={onDeleted}
      docPath={docPath}
    />
  );
}
