import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { filesBase, renderMarkdown } from "../markdown";
import { backTarget, intakeBackLink, listLink, projectLink, screenLink, setPageTitle } from "../nav";
import { attempt, notifyError } from "../notify";
import { dropDraft, hasDraft, loadDraft, useDrafts, useDraftKeeper, useUnsaved } from "../unsaved";
import type { DemotePlan, Entry, Meta, Project, Report, YearFix } from "../types";
import type { Attachment } from "../upload";
import { formatBytes, uploadAttachment } from "../upload";
import PasteOfferBar from "./PasteOffer";
import { type PasteOffer, handleEditorPaste, spliceAtCaret } from "../table";
import { todayIso, daysUntil, dueLabel, effectText, EFFECT_UNIT, formatDate, formatDateTime, periodText, scrollEditorIntoView } from "../util";
import AttachmentList from "./AttachmentList";
import EntryEditor from "./EntryEditor";
import VersionPanel from "./VersionPanel";
import ExportMenu from "./ExportMenu";
import ReportEditor from "./ReportEditor";
import PreviewToggle, { usePreview } from "./PreviewToggle";
import ProjectForm from "./ProjectForm";
import StatusBadge, { TypeBadge } from "./StatusBadge";
import { leftLabel } from "../people";
import StageBand from "./StageBand";

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
  /** 과제 복제 직후처럼 정보 수정 칸을 열어 둔 채 들어온다 (TODO 109). */
  edit?: boolean;
  /** 홈의 "작성 중이던 글" 에서 왔다 — 그 편집기를 열어 둔다 (TODO 170): entry-new · entry-<번호> · overview */
  openDraft?: string | null;
}

/** 그 조건으로 걸러진 과제 목록. 홈의 것과 같은 규칙이다. */
/**
 * 번호의 연도가 시작일과 어긋났다는 알림 (TODO 95).
 *
 * 지난해 과제를 올해 뒤늦게 등록하면 그때까지는 `2026-…` 이 붙었다. 연도를 가르는 기준이
 * **번호 앞 네 자리**라, 그 과제는 홈·대시보드·목록에서 전부 올해 것으로 세인다.
 * 만들 때는 이제 시작일을 보지만, **시작일을 나중에 채우거나 고치는 일**이 남는다.
 *
 * 그때 번호를 소리 없이 따라 움직이게 하지 않는다 — 번호는 이미 보고 자리에서 불린
 * 이름이다. 어긋났다는 사실만 알리고, 옮기는 것은 사용자가 누를 때만 한다.
 */
function YearFixNote({ project, onMoved }: { project: Project; onMoved: (newId: string) => void }) {
  const [plan, setPlan] = useState<YearFix | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .yearFixPlan(project.id)
      // 옮길 것이 없으면 (이미 맞거나 시작일이 비었으면) 아무것도 띄우지 않는다.
      .then((row) => alive && setPlan(row.new_id ? row : null))
      .catch(() => alive && setPlan(null));
    return () => {
      alive = false;
    };
  }, [project.id, project.start_date]);

  if (!plan?.new_id) return null;

  return (
    <div className="year-fix">
      <span className="year-fix-text">
        과제 번호는 <b>{plan.from_year}년</b>인데 시작일은 <b>{plan.to_year}년</b>입니다.
        번호의 연도는 <b>착수년도</b>라, 이대로 두면 이 과제가 {plan.from_year}년 것으로 세입니다.
        {plan.renumbered && (
          <> 옮기면 일련번호도 {plan.to_year}년의 다음 번호로 다시 붙습니다.</>
        )}
      </span>
      <button
        className="ghost small"
        disabled={busy}
        onClick={async () => {
          const ok = window.confirm(
            `과제 번호를 ${plan.id} → ${plan.new_id} 로 옮깁니다.\n\n` +
              "과제 폴더 이름도 함께 바뀝니다. 진행일지·보고·첨부는 폴더째 따라옵니다.\n" +
              "다만 이미 보고 문서에 적어 둔 옛 번호는 그대로 남습니다.\n\n계속할까요?",
          );
          if (!ok) return;
          setBusy(true);
          setError(null);
          try {
            const done = await api.yearFixApply(project.id);
            if (done.new_id) onMoved(done.new_id);
          } catch (err) {
            setError((err as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "옮기는 중…" : `${plan.new_id} 로 옮기기`}
      </button>
      {error && <span className="year-fix-error">{error}</span>}
    </div>
  );
}

export default function ProjectDetail({
  projectId,
  meta,
  onMetaChange,
  openReportId,
  openEntryId,
  back,
  edit,
  openDraft,
}: Props) {
  const [project, setProject] = useState<Project | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [editingProject, setEditingProject] = useState(Boolean(edit));
  const [editingOverview, setEditingOverview] = useState(false);
  const [showOverviewVersions, setShowOverviewVersions] = useState(false);
  const [preview, togglePreview] = usePreview();
  const overviewRef = useRef<HTMLDivElement>(null);
  // 개요에 직접 붙이는 첨부 — 효과 산출 근거(엑셀·PPT)를 위한 자리다.
  const overviewFileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [overviewDraft, setOverviewDraft] = useState("");
  // 개요 저장 중 — 두 번 누르면 두 번 저장되던 것을 막는다 (TODO 161)
  const [savingOverview, setSavingOverview] = useState(false);
  // 저장하지 않고 남았던 글을 되살렸다 (TODO 162)
  const [overviewRestored, setOverviewRestored] = useState(false);
  // 개요 편집기 — 붙여넣기·첨부 링크를 커서 자리에 끼우려고 잡아 둔다 (TODO 137)
  const overviewAreaRef = useRef<HTMLTextAreaElement>(null);
  const [pasteOffer, setPasteOffer] = useState<PasteOffer | null>(null);
  const closeOffer = useCallback(() => setPasteOffer(null), []);
  const [creatingEntry, setCreatingEntry] = useState(false);
  // [이어쓰기]로 시작하면 지난 기록의 내용을 담아 온다. 없으면 서식에서 시작한다.
  const [entrySeed, setEntrySeed] = useState<string | null>(null);
  // 첨부 때문에 편집 도중 먼저 만들어진 기록. 편집기 아래 타임라인에 중복 표시하지 않는다.
  const [draftEntryId, setDraftEntryId] = useState<number | null>(null);
  const [editingEntryId, setEditingEntryId] = useState<number | null>(null);
  // 편집을 닫으면 배치가 다시 2단으로 돌아가므로, 고치던 기록 자리로 되돌려 놓는다.
  const lastEditedEntry = useRef<number | null>(null);
  // 접수에서 온 과제를 지우려 할 때 — [중단]을 먼저 권한다 (TODO 145)
  const [confirmingArchive, setConfirmingArchive] = useState(false);
  // 접수로 되돌리기 미리보기 (TODO 171) — 판이 열려 있으면 그 내용
  const [demotePlan, setDemotePlan] = useState<DemotePlan | null>(null);
  const [demoting, setDemoting] = useState(false);
  // [이 과제로 새 과제] 의 미리 채운 값 (TODO 173) — 있으면 새 과제 칸이 열려 있다. 아직 아무것도 만들지 않았다.
  const [cloneDraft, setCloneDraft] = useState<Partial<Project> | null>(null);
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
  // 요약 바의 [미보고 N건] 을 누르면 미보고 기록만 남는다 (TODO 106-D).
  const [onlyUnreported, setOnlyUnreported] = useState(false);
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
  // 브라우저 탭 제목 (TODO 169)
  useEffect(() => {
    if (project) setPageTitle(`${project.id} ${project.title}`);
  }, [project]);

  // 과제 개요 편집 — 떠날 때 묻고, 쓰던 글은 임시 보관한다 (TODO 162)
  const overviewKey = `overview:${projectId}`;
  const overviewOriginal = project?.body ?? "";
  const overviewDirty = editingOverview && overviewDraft !== overviewOriginal;
  useUnsaved(overviewKey, overviewDirty);
  useDraftKeeper(editingOverview ? overviewKey : null, overviewDraft, overviewDraft === overviewOriginal);
  // 남은 임시 보관 — [기록 추가] 옆 · 카드의 "작성 중" 표시가 본다. 다른 창에서 쓴 것도 창으로 돌아오면 다시 읽는다 (TODO 170)
  useDrafts();

  /** 개요 [수정] — 남은 글이 있으면 되살린다 */
  async function startOverviewEdit() {
    if (!project) return;
    const original = project.body ?? "";
    const kept = await loadDraft<string>(overviewKey, (content) => content === original);
    setOverviewDraft(typeof kept === "string" ? kept : original);
    setOverviewRestored(typeof kept === "string");
    setEditingOverview(true);
  }

  // 홈의 "작성 중이던 글" 에서 왔으면 그 편집기를 연다 — 과제를 처음 읽었을 때 한 번만
  const draftOpened = useRef<string | null>(null);
  useEffect(() => {
    if (!project || !openDraft || draftOpened.current === `${projectId}:${openDraft}`) return;
    draftOpened.current = `${projectId}:${openDraft}`;
    if (openDraft === "entry-new") setCreatingEntry(true);
    else if (openDraft === "overview") void startOverviewEdit();
    else if (openDraft.startsWith("entry-")) {
      const id = Number(openDraft.slice("entry-".length));
      if (Number.isFinite(id)) {
        setExpandedIds((prev) => new Set(prev).add(id));
        setEditingEntryId(id);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project, openDraft, projectId]);

  async function saveOverview() {
    if (!project || savingOverview) return;
    setSavingOverview(true);
    const saved = await attempt(() => api.updateProject(project.id, { body: overviewDraft }));
    setSavingOverview(false);
    if (!saved) return; // 실패 — 편집기를 열어 둔 채 알림만 (쓰던 글은 그대로 남는다)
    dropDraft(overviewKey);
    setOverviewRestored(false);
    setEditingOverview(false);
    load();
  }
  // 다른 과제로 옮겨 오면 같은 부품이 그대로 쓰이므로 첫 상태만으로는 안 열린다 (TODO 109).
  // 앞 과제에서 열어 둔 판(새 과제 칸 · 접수로 되돌리기)은 닫는다 — 다른 과제의 것이다 (TODO 173).
  useEffect(() => {
    if (edit) setEditingProject(true);
    setCloneDraft(null);
    setDemotePlan(null);
  }, [projectId, edit]);

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
        if (editingOverview) {
          // 편집 중이면 **편집기의 커서 자리**에 끼운다. 예전에는 서버의 개요 끝에 붙여 저장했는데,
          // 열려 있던 편집기의 [저장] 이 그 위를 덮어 링크가 사라졌다 (TODO 138).
          setOverviewDraft((prev) => spliceAtCaret(overviewAreaRef.current, prev, `\n${links.join("\n")}\n`));
          return;
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
    [project, load, editingOverview],
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
        <div className={missing ? "card" : "card load-error"}>
          <h2>{missing ? "이 과제를 찾을 수 없습니다" : "과제를 불러오지 못했습니다"}</h2>
          <p className="hint">
            <code>{projectId}</code>
            {missing ? (
              <>
                {" "}번 과제가 없습니다. <b>과제 번호가 바뀌었거나</b> 삭제 보관함으로 옮겨졌을 수
                있습니다.
                <br />
                번호를 일괄로 바꾸면 예전 주소·즐겨찾기는 더 이상 맞지 않습니다.
                과제 목록에서 이름으로 찾아 주세요.
                <br />
                탐색기·다른 편집기로 과제 파일을 고쳤다면 <b>파일을 읽지 못했을 수도</b> 있습니다 —
                [다시 읽기] 를 누르면 무엇이 문제인지 알려 줍니다 (TODO 164).
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
            {missing && (
              <button
                className="ghost"
                onClick={async () => {
                  if (await attempt(() => api.reindex())) load();
                }}
              >
                다시 읽기
              </button>
            )}
            <a className="button-like primary-link" href="#/projects">
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
  const visibleEntries = (needle ? kept.filter(matches) : kept).filter(
    (entry) => !onlyUnreported || !entry.reported_on,
  );
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
            <h1>
              {project.title} <StageBand stage={project.stage} />
            </h1>
            <div className="meta-line">
              <StatusBadge status={project.status} meta={meta} />
              {project.type && <TypeBadge type={project.type} meta={meta} />}
              {/* 과제 분류 넷 (TODO 136). 누르면 같은 분류의 과제만 걸러 본다. */}
              {meta.classifications.map((info) => {
                const value = project[info.key];
                return value ? (
                  <a key={info.key} className="chip class-chip" href={listLink({ [info.key]: value, year: "all" })}
                     title={`${info.label} — 같은 ${info.label}의 과제 보기`}>
                    <span className="class-chip-label">{info.label}</span> {value}
                  </a>
                ) : null;
              })}
              {project.group && <span className="chip">{project.group}</span>}
              {project.tags.map((tag) => (
                <span key={tag} className="tag">
                  {tag}
                </span>
              ))}
            </div>
            <div className="meta-line muted">
              <span>{periodText(project.start_date, project.due_date)}</span>
              {project.completed_at && <span>완료 {project.completed_at}</span>}
              {due && <span className={`due due-${due.tone}`}>{due.text}</span>}
              {project.owners.length > 0 && (
                <span>
                  담당{" "}
                  {project.owners.map((name, i) => (
                    <span key={name}>
                      {i > 0 && ", "}
                      {name}
                      {/* 떠난 사람이면 딱지. 이름은 지우지 않는다 (TODO 122) */}
                      {leftLabel(meta, name) && (
                        <span className="tag left-tag">{leftLabel(meta, name)}</span>
                      )}
                    </span>
                  ))}
                </span>
              )}
              <span>최근 업데이트 {formatDate(project.updated_at)}</span>
            </div>
            {/* 이 과제가 온 접수 · 이 과제에 병합된 접수 (TODO 136) — 양쪽 링크의 과제 쪽 끝 */}
            {(project.intakes ?? []).length > 0 && (
              <div className="meta-line intake-line">
                <span className="muted">접수</span>
                {(project.intakes ?? []).map((item) => (
                  <a key={item.id} className="intake-link" href={intakeBackLink(item.id)}>
                    {item.relation === "started" ? "← " : "⇠ "}
                    <span className="intake-link-id">{item.id}</span> {item.title}
                    <span className="muted"> · {item.relation === "started" ? "여기서 승격" : "병합됨"}</span>
                    {item.precheck_score != null && <span className="muted"> · 사전점검 {item.precheck_score}점</span>}
                  </a>
                ))}
              </div>
            )}
            {/* 다년도 과제의 줄기 (TODO 172) — 이어진 과제를 단계별로. 한 단계에 여럿일 수 있다 */}
            {/* 유관부서 (TODO 92). 누르면 그 팀·사람과 함께 하는 과제만 걸러 본다 —
                "설비기술팀이랑 뭐뭐 하고 있더라" 가 실제로 자주 하는 물음이다. */}
            {(project.partners ?? []).length > 0 && (
              <div className="meta-line partner-line">
                <span className="muted">유관부서</span>
                {project.partners.map((partner) => (
                  <span key={partner.team} className="partner-chip">
                    <a href={listLink({ partner: partner.team })}>{partner.team}</a>
                    {partner.people.length > 0 ? (
                      partner.people.map((name) => (
                        <a key={name} className="partner-person" href={listLink({ partner: name })}>
                          {name}
                        </a>
                      ))
                    ) : (
                      <span className="partner-person muted">담당자 미정</span>
                    )}
                  </span>
                ))}
              </div>
            )}
          </div>
          <div className="detail-actions">
            <ExportMenu projectId={project.id} />
            <button className="ghost" onClick={() => setEditingProject((value) => !value)}>
              {editingProject ? "닫기" : "과제 정보 수정"}
            </button>
            {/* 끝난 과제의 후속 과제 (TODO 109). 개요·담당자·태그가 넘어오고 이력은 남지 않는다.
                누르면 **미리 채운 새 과제 칸**만 연다 — [만들기] 를 눌러야 생긴다 (TODO 173). */}
            <button
              className={cloneDraft ? "ghost on" : "ghost"}
              title="이 과제의 개요·담당자·태그를 가져와 새 과제 칸을 엽니다. 진행일지·보고는 넘어오지 않습니다."
              onClick={async () => {
                if (cloneDraft) {
                  setCloneDraft(null);
                  return;
                }
                try {
                  setCloneDraft(await api.cloneDraft(project.id));
                } catch (err) {
                  setError((err as Error).message);
                }
              }}
            >
              이 과제로 새 과제
            </button>
            {/* 접수를 거치지 않고 만든 스마트과제를 풀로 (TODO 171) — 무엇이 어디로 가는지 판에서 먼저 보인다 */}
            {(project.intakes ?? []).length === 0 && project.type === meta.classified_type && (
              <button
                className={demotePlan ? "ghost on" : "ghost"}
                title="이 과제를 접수로 되돌려 풀에서 검토 · 사전점검 · 판정을 받게 합니다"
                onClick={async () => {
                  if (demotePlan) {
                    setDemotePlan(null);
                    return;
                  }
                  try {
                    setDemotePlan(await api.toIntakePlan(project.id));
                  } catch (err) {
                    setError((err as Error).message);
                  }
                }}
              >
                접수로 되돌리기
              </button>
            )}
            <button
              className="ghost danger"
              onClick={async () => {
                // 접수에서 온 과제면 확인창 대신 판을 연다 — 지우면 접수가 풀로 돌아간다는 것과
                // 그만둔 과제는 [중단]이 맞다는 것을 함께 말해야 한다 (TODO 145)
                if ((project.intakes ?? []).length > 0) {
                  setConfirmingArchive((value) => !value);
                  return;
                }
                if (!window.confirm("이 과제를 삭제 보관함으로 옮길까요?\n\n설정 → 삭제 보관함에서 되돌릴 수 있습니다.")) return;
                if (!(await attempt(() => api.archiveProject(project.id)))) return;
                // 보관한 과제는 사라진다. 온 곳이 목록 성격이면 그리로 돌려보낸다.
                window.location.hash = backTarget(back).href;
              }}
            >
              {/* 이름은 **삭제** — 기록·접수·첨부의 삭제와 같은 말. 모두 보관함으로 옮길 뿐이다 (TODO 147) */}
              삭제
            </button>
          </div>
        </div>

        {/* 다년도 과제의 단계 흐름 (TODO 172 · 176). 한 줄 띠는 한 단계에 과제가 여럿이면 꺾여 어느 과제가 몇 단계인지
            흐려졌다 — 단계마다 칸 하나, 같은 단계의 과제는 그 칸 안에 위아래로. 머리 아래 카드 폭 전체를 쓴다. */}
        {project.lineage?.stage != null && (
          <div className="stage-flow" aria-label="다년도 과제의 단계">
            <div className="stage-flow-head">
              <b>다년도 과제</b>
              <span className="muted">
                {project.lineage.stages.length}단계 중 <b className="stage-flow-now">{project.lineage.stage}단계</b>
              </span>
              <a className="lineage-roadmap" href={screenLink("roadmap", { focus: project.id })}>
                로드맵에서 보기 →
              </a>
            </div>
            <div className="stage-flow-columns">
              {project.lineage.stages.map((group, index) => (
                <Fragment key={group.stage}>
                  {index > 0 && (
                    <span className="stage-flow-arrow" aria-hidden="true">
                      →
                    </span>
                  )}
                  <div className={group.stage === project.lineage?.stage ? "stage-flow-col current" : "stage-flow-col"}>
                    <div className="stage-flow-name">
                      {group.stage}단계
                      <span className="muted">{stageYears(group.items)}</span>
                    </div>
                    {group.items.map((item) =>
                      item.missing ? (
                        <div key={item.id} className="stage-flow-item missing" title="삭제 보관함에 있거나 찾을 수 없는 과제입니다">
                          <span className="project-id">{item.id}</span>
                          <span className="stage-flow-title">찾을 수 없음</span>
                        </div>
                      ) : (
                        <a
                          key={item.id}
                          className={item.here ? "stage-flow-item here" : "stage-flow-item"}
                          href={item.here ? undefined : projectLink(item.id)}
                          title={`${item.id} ${item.title ?? ""}${item.here ? " — 지금 보고 있는 과제" : ""}`}
                          aria-current={item.here ? "page" : undefined}
                        >
                          <span className="stage-flow-top">
                            <span className="project-id">{item.id}</span>
                            {item.status && <StatusBadge status={item.status} meta={meta} />}
                          </span>
                          <span className="stage-flow-title">{item.title}</span>
                        </a>
                      ),
                    )}
                  </div>
                </Fragment>
              ))}
            </div>
          </div>
        )}

        {cloneDraft && (
          <div className="card clone-panel">
            <h2>새 과제 — {project.id} 를 바탕으로</h2>
            <p className="hint">
              과제명 · 담당자 · 유관부서 · 태그 · 분류와 <b>개요</b>가 넘어오고, 이 과제가 <b>선행 과제</b>로 이어집니다. 진행일지 ·
              보고 · 첨부 · 효과 금액 · 기간은 넘어오지 않습니다. <b>[만들기]</b>를 눌러야 과제가 생깁니다 — [취소]하면 아무것도
              남지 않습니다.
            </p>
            <ProjectForm
              meta={meta}
              onMetaChange={onMetaChange}
              initial={cloneDraft}
              submitLabel="만들기"
              onCancel={() => setCloneDraft(null)}
              onSubmit={async (payload) => {
                const created = await api.createProject({ ...payload, body: cloneDraft.body });
                setCloneDraft(null);
                onMetaChange();
                window.location.hash = projectLink(created.id);
              }}
            />
          </div>
        )}

        {demotePlan && (
          <div className="archive-panel demote-panel">
            {demotePlan.eligible ? (
              <>
                <p>
                  이 과제를 접수 <b>{demotePlan.next_intake_id}</b>(검토중)로 되돌려 <b>풀에서 관리</b>합니다.
                </p>
                <ul className="hint">
                  <li>과제 개요 → 요청 내용 · 분류와 기대효과 → 그대로(기대효과는 요청 효과 자리에)</li>
                  <li>진행일지 {demotePlan.entries}건 → 검토 기록 · 첨부 {demotePlan.attachments}개 → 복사</li>
                  <li>
                    접수일은 처음 과제로 등록한 날({demotePlan.received_on})이 됩니다 — 풀의 경과가 실제로 기다린 날수가 되게
                  </li>
                  <li>
                    과제 <b>{project.id}</b> 는 삭제 보관함으로 갑니다. 이 번호는 다시 쓰지 않고, 접수에서 다시 착수하면 새 번호가
                    붙습니다.
                  </li>
                  {demotePlan.successors > 0 && (
                    <li className="warn-text">
                      이 과제를 선행으로 둔 후속 과제가 {demotePlan.successors}건 있습니다 — 그쪽 줄기에는 "찾을 수 없음" 으로
                      남습니다.
                    </li>
                  )}
                </ul>
                <div className="form-actions left">
                  <button
                    disabled={demoting}
                    onClick={async () => {
                      setDemoting(true);
                      try {
                        const done = await api.toIntake(project.id);
                        onMetaChange();
                        window.location.hash = `#/intakes/${encodeURIComponent(done.intake_id)}`;
                      } catch (err) {
                        notifyError((err as Error).message);
                      } finally {
                        setDemoting(false);
                      }
                    }}
                  >
                    {demoting ? "되돌리는 중…" : "접수로 되돌리기"}
                  </button>
                  <button className="ghost" onClick={() => setDemotePlan(null)}>
                    취소
                  </button>
                </div>
              </>
            ) : (
              <>
                <p>{demotePlan.reason}</p>
                <div className="form-actions left">
                  <button className="ghost" onClick={() => setDemotePlan(null)}>
                    닫기
                  </button>
                </div>
              </>
            )}
          </div>
        )}

        {confirmingArchive && (
          <div className="archive-panel">
            <p>
              이 과제는 접수{" "}
              <b>{(project.intakes ?? []).map((item) => item.id).join(", ")}</b> 와(과) 이어져 있습니다. 보관함으로
              삭제하면(삭제 보관함으로) 그 접수는 <b>검토중으로 풀에 돌아갑니다</b>(검토 기록에 한 줄 남습니다).
            </p>
            <p className="hint">
              <b>하다가 그만둔 과제</b>라면 지우지 말고 상태를 <b>중단</b>으로 두세요 — 요청이 어떻게 끝났는지가
              기록에 남습니다. 삭제는 <b>잘못 만든 과제</b>를 치울 때 씁니다.
            </p>
            <div className="form-actions left">
              {project.status !== "dropped" && (
                <button
                  onClick={async () => {
                    try {
                      await api.updateProject(project.id, { status: "dropped" });
                      setConfirmingArchive(false);
                      load();
                    } catch (err) {
                      setError((err as Error).message);
                    }
                  }}
                >
                  중단으로 바꾸기
                </button>
              )}
              <button
                className="ghost danger"
                onClick={async () => {
                  try {
                    await api.archiveProject(project.id);
                    window.location.hash = backTarget(back).href;
                  } catch (err) {
                    setError((err as Error).message);
                  }
                }}
              >
                그래도 삭제
              </button>
              <button className="ghost" onClick={() => setConfirmingArchive(false)}>
                취소
              </button>
            </div>
          </div>
        )}

        {/* 번호의 연도가 시작일과 어긋났으면 여기서 알린다 (TODO 95) */}
        <YearFixNote
          project={project}
          onMoved={(newId) => {
            // projectLink 가 지금 주소의 back 을 그대로 실어 준다 — 온 곳을 잃지 않는다.
            window.location.hash = projectLink(newId);
            onMetaChange();
          }}
        />

        {/* 지난 보고에서 받고 아직 답하지 않은 지시 (TODO 107). 다음 초안이 이것을 맨 위에 문다. */}
        {(project.open_feedback?.length ?? 0) > 0 && (
          <div className="feedback-band" data-testid="open-feedback">
            <b>답하지 않은 지시 {project.open_feedback!.length}건</b>
            <ul>
              {project.open_feedback!.map((item) => (
                <li key={item.id}>
                  <a href={projectLink(project.id, { report: item.id })}>
                    {formatDate(item.report_date)}
                    {item.audience && ` · ${item.audience}`}
                  </a>
                  <span className="feedback-excerpt">{item.feedback}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* 최근 진행일지의 계획 칸 — 다음 할 일 (TODO 112). 진행일지가 알려 주는 것을 위로 올린다. */}
        {project.next_plan && (
          <p className="next-plan" data-testid="next-plan">
            <span className="muted">다음 할 일</span>{" "}
            <a href={projectLink(project.id, { entry: project.next_plan.entry_id })} title={`${formatDate(project.next_plan.date)} 진행일지의 계획`}>
              {project.next_plan.text}
            </a>
            <span className="muted"> · {formatDate(project.next_plan.date)}</span>
          </p>
        )}

        <dl className="summary-bar">
          <div>
            <dt>수행 이력</dt>
            <dd>{project.entry_count}건</dd>
          </div>
          <div>
            <dt>미보고</dt>
            <dd className={(project.unreported_entries ?? 0) > 0 ? "accent" : undefined}>
              {(project.unreported_entries ?? 0) > 0 ? (
                <button
                  className={`linkish${onlyUnreported ? " on" : ""}`}
                  title={onlyUnreported ? "모든 기록 보기" : "미보고 기록만 보기"}
                  onClick={() => setOnlyUnreported((value) => !value)}
                >
                  {project.unreported_entries}건
                </button>
              ) : (
                "0건"
              )}
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
          <h2>
            과제 개요
            {/* 서식 그대로면 진짜 내용처럼 보인다 — 아직 안 썼다고 말해 준다 (TODO 106-B) */}
            {project.overview_blank && !editingOverview && (
              <span className="tag blank-tag" title="아래 안내 문장은 서식입니다. [수정]을 눌러 채워 주세요.">
                아직 작성 전
              </span>
            )}
            {/* 쓰다 만 개요가 데이터 폴더에 남아 있다 — [수정] 을 누르면 되살아난다 (TODO 170) */}
            {!editingOverview && hasDraft(overviewKey) && (
              <span className="draft-waiting" title="저장하지 않은 개요가 남아 있습니다 — [수정] 을 누르면 되살아납니다">
                작성 중
              </span>
            )}
          </h2>
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
                if (editingOverview) {
                  // [취소] — 쓴 것이 있으면 버릴지 묻는다 (TODO 162)
                  if (overviewDirty && !window.confirm("저장하지 않은 개요를 버릴까요?")) return;
                  dropDraft(overviewKey);
                  setOverviewRestored(false);
                  setEditingOverview(false);
                  return;
                }
                void startOverviewEdit();
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
                ref={overviewAreaRef}
                value={overviewDraft}
                onChange={(event) => setOverviewDraft(event.target.value)}
                onKeyDown={(event) => {
                  // 다른 편집기와 같이 Ctrl+S 로 저장 (TODO 162)
                  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
                    event.preventDefault();
                    void saveOverview();
                  }
                }}
                onPaste={(event) =>
                  // 다른 편집기와 같은 판 — 표는 커서 자리에, 캡처는 첨부로 (TODO 137)
                  handleEditorPaste(event, {
                    onInsert: (snippet) =>
                      setOverviewDraft((prev) => spliceAtCaret(overviewAreaRef.current, prev, snippet)),
                    onFiles: (files) => void attachToOverview(files),
                    onOffer: setPasteOffer,
                  })
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
            <PasteOfferBar
              offer={pasteOffer}
              area={overviewAreaRef.current}
              setValue={setOverviewDraft}
              onFiles={(files) => void attachToOverview(files)}
              onClose={closeOffer}
            />
            {overviewRestored && (
              <p className="hint restored">
                저장하지 않은 작성 중 내용을 복구했습니다.{" "}
                <button
                  className="ghost small"
                  onClick={() => {
                    dropDraft(overviewKey);
                    setOverviewDraft(project.body ?? "");
                    setOverviewRestored(false);
                  }}
                >
                  복구한 내용 버리기
                </button>
              </p>
            )}
            <div className="form-actions">
              <span className="hint">Ctrl+S 로도 저장됩니다</span>
              <button disabled={savingOverview} onClick={() => void saveOverview()}>
                {savingOverview ? "저장 중…" : "저장"}
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
                  {!report.frozen && hasDraft(`report:${report.id}`) && <span className="draft-waiting">작성 중</span>}
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
                    비활성 단추로 두면 "지울 수 있나?" 를 한 번 생각하게 하므로 아예 세우지
                    않는다 (TODO 103-F). 지우려면 [확정 해제] 를 먼저 누르게 한다. */}
                {!report.frozen && (
                <button
                  className="ghost small danger"
                  onClick={async () => {
                    if (!window.confirm(`${report.report_date} 보고를 삭제 보관함으로 옮길까요?`)) return;
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
                )}
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
              if (!window.confirm(`${attachment.orig_name} 을(를) 삭제 보관함으로 옮길까요?`)) return;
              if (!(await attempt(() => api.deleteAttachment(attachment.id)))) return;
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
          {onlyUnreported && !needle && (
            <button className="linkish small" onClick={() => setOnlyUnreported(false)}>
              · 미보고만 보는 중 — 모두 보기
            </button>
          )}
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
          {/* 쓰다 만 새 기록이 브라우저에 남아 있으면 알린다 — 전에는 편집기를 열어야 알 수 있었다 (TODO 162) */}
          {!creatingEntry && hasDraft(`entry:new-${projectId}`) && (
            <span className="draft-waiting" title="저장하지 않고 남은 기록이 있습니다 — [기록 추가] 를 누르면 되살아납니다">
              작성 중이던 기록 있음
            </span>
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
              }${entry.tags.includes("상태변경") ? " status-change" : ""}`}
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
                  {/* 고치다 만 글이 남아 있다 — [수정] 을 누르면 되살아난다 (TODO 170) */}
                  {hasDraft(`entry:${entry.id}`) && (
                    <span className="draft-waiting" title="저장하지 않은 고친 내용이 남아 있습니다 — [수정] 을 누르면 되살아납니다">
                      작성 중
                    </span>
                  )}
                  <button className="ghost" onClick={() => setEditingEntryId(entry.id)}>
                    수정
                  </button>
                  <button
                    className="ghost danger"
                    onClick={async () => {
                      if (!window.confirm("이 기록을 삭제 보관함으로 옮길까요?")) return;
                      if (!(await attempt(() => api.deleteEntry(entry.id)))) return;
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

/** 단계 칸 머리의 연도 — 그 단계 과제들의 시작 ~ 끝 연도 (TODO 176) */
function stageYears(items: { start_date?: string | null; end_date?: string | null; missing?: boolean }[]): string {
  const years = items
    .filter((item) => !item.missing)
    .flatMap((item) => [item.start_date, item.end_date])
    .filter((text): text is string => Boolean(text && /^\d{4}/.test(text)))
    .map((text) => Number(text.slice(0, 4)));
  if (years.length === 0) return "";
  const first = Math.min(...years);
  const last = Math.max(...years);
  return first === last ? String(first) : `${first}~${String(last).slice(2)}`;
}
