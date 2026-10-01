import type { DemotePlan, Activity, ActivitySummary, AppSettings, BackupStatus, Dashboard, Home, MonthGrid, DocumentVersion, Entry, ErrorEntry, LinkFixReport, Meta, OpenDraft, Project, RenumberPlan, Report, ReportCandidate, ReportDiff, ReportHistoryItem, SearchResults, SpreadsheetPreview, Person, ProjectTypeRow, TrashItem, YearFix, FolderListing, Intake, IntakeDetail, IntakeListing, PromotionPlan, Partner } from "./types";
import type { Attachment } from "./upload";

/** 서버에 닿지 못했을 때 (TODO 165) — 브라우저의 영어 `Failed to fetch` 대신 */
export const OFFLINE_MESSAGE =
  "프로그램에 연결하지 못했습니다 — 느린 나이테 창(run.bat)이 켜져 있는지 확인하세요.";

/**
 * 서버가 돌려준 실패를 사람이 읽을 한 줄로 (TODO 165).
 *
 * 사유는 대개 글이지만 입력 검사(422)는 **목록**으로 온다 — 그대로 `new Error` 에 넣으면 `[object Object]`
 * 가 됐다(140 의 병합 칸). 글이 아닌 500 은 `Internal Server Error` 대신 오류 기록 자리를 알려 준다.
 */
export function errorText(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const fields = detail
      .map((item) => (Array.isArray(item?.loc) ? item.loc[item.loc.length - 1] : null))
      .filter((field): field is string => typeof field === "string" && field !== "body");
    const unique = [...new Set(fields)];
    return `입력값을 서버가 받지 못했습니다${unique.length ? ` (항목: ${unique.join(", ")})` : ""}.`;
  }
  if (status >= 500) return "서버에서 오류가 났습니다 — 설정 › 최근 오류에 남았습니다.";
  if (status === 404) return "찾을 수 없습니다 — 지워졌거나 번호가 바뀌었을 수 있습니다.";
  return `요청에 실패했습니다 (${status}).`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new Error(OFFLINE_MESSAGE);
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(errorText(response.status, body));
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

export const api = {
  meta: () => request<Meta>("/api/meta"),
  // ── 과제 접수 풀 (TODO 136) ─────────────────────────
  intakes: (params: Record<string, string>) => {
    const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v));
    return request<IntakeListing>(`/api/intakes?${query.toString()}`);
  },
  nextIntakeId: (receivedOn: string) =>
    request<{ id: string }>(
      `/api/intakes/next-id${receivedOn ? `?received_on=${encodeURIComponent(receivedOn)}` : ""}`,
    ),
  createIntake: (payload: Partial<Intake> & { body?: string }) =>
    request<IntakeDetail>("/api/intakes", { method: "POST", body: JSON.stringify(payload) }),
  getIntake: (id: string) => request<IntakeDetail>(`/api/intakes/${encodeURIComponent(id)}`),
  updateIntake: (id: string, payload: Partial<Intake> & { body?: string }) =>
    request<IntakeDetail>(`/api/intakes/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  setIntakeStatus: (id: string, status: string, note?: string, mergedInto?: string) =>
    request<IntakeDetail>(`/api/intakes/${encodeURIComponent(id)}/status`, {
      method: "POST",
      body: JSON.stringify({ status, note: note || null, merged_into: mergedInto || null }),
    }),
  promotionPlan: (id: string) => request<PromotionPlan>(`/api/intakes/${encodeURIComponent(id)}/promote`),
  promoteIntake: (
    id: string,
    payload: Omit<Partial<PromotionPlan>, "partners"> & { partners?: Partner[]; effect_expected?: number | null; decision_note?: string },
  ) =>
    request<{ project_id: string; intake: IntakeDetail }>(`/api/intakes/${encodeURIComponent(id)}/promote`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  /** 사전점검을 매긴다 (TODO 155) — 서버가 지금의 체크리스트로 채점한다 */
  savePrecheck: (id: string, items: { group: string; item: string; choice: string | null; note: string | null }[]) =>
    request<IntakeDetail>(`/api/intakes/${encodeURIComponent(id)}/precheck`, {
      method: "PUT",
      body: JSON.stringify({ items }),
    }),
  archiveIntake: (id: string) =>
    request<void>(`/api/intakes/${encodeURIComponent(id)}/archive`, { method: "POST" }),
  createIntakeLog: (id: string, payload: { date: string; title: string; body: string }) =>
    request<{ name: string; intake: IntakeDetail }>(`/api/intakes/${encodeURIComponent(id)}/logs`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateIntakeLog: (id: string, name: string, payload: { date?: string; title?: string; body?: string; mtime?: number }) =>
    request<{ name: string; intake: IntakeDetail }>(
      `/api/intakes/${encodeURIComponent(id)}/logs/${encodeURIComponent(name)}`,
      { method: "PATCH", body: JSON.stringify(payload) },
    ),
  deleteIntakeLog: (id: string, name: string) =>
    request<void>(`/api/intakes/${encodeURIComponent(id)}/logs/${encodeURIComponent(name)}`, { method: "DELETE" }),
  deleteIntakeAttachment: (id: string, relPath: string) =>
    request<void>(
      `/api/intakes/${encodeURIComponent(id)}/attachments?path=${encodeURIComponent(relPath)}`,
      { method: "DELETE" },
    ),
  dashboard: (year?: string) =>
    request<Dashboard>(`/api/dashboard${year ? `?year=${year}` : ""}`),
  home: (year?: string, period?: string) => {
    const params = new URLSearchParams();
    if (year) params.set("year", year);
    if (year && period) params.set("period", period);
    const query = params.toString();
    return request<Home>(`/api/home${query ? `?${query}` : ""}`);
  },
  // 팀원 역량 이력 (TODO 72)
  activities: (params: Record<string, string>) => {
    const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v));
    return request<Activity[]>(`/api/activities?${query.toString()}`);
  },
  /** 과제 × 월 보고 표 (보고 이력 화면) */
  monthGrid: (year: string) => request<MonthGrid>(`/api/report-month-grid?year=${year}`),
  activitySummary: (year?: string) =>
    request<ActivitySummary>(`/api/activities/summary${year ? `?year=${year}` : ""}`),
  /** 여러 명을 한 번에 넣을 수 있다 — 서버가 사람 수만큼 기록을 만든다 (count 로 알려 준다). */
  createActivity: (payload: Partial<Activity>) =>
    request<{ ids: number[]; count: number; id: number }>("/api/activities", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateActivity: (id: number, payload: Partial<Activity>) =>
    request<{ ok: boolean }>(`/api/activities/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteActivity: (id: number) => request<void>(`/api/activities/${id}`, { method: "DELETE" }),
  listProjects: (params: Record<string, string>) => {
    // `year=all` 은 **주소의 말**이다(연도 전체). 서버는 네 자리 연도나 빈 값만 받는다 —
    // 부르는 쪽마다 바꾸게 두면 한 곳이 빠진다(TODO 140: 병합 칸이 422 로 빈 목록을 보였다).
    const query = new URLSearchParams(
      Object.entries(params).filter(([key, v]) => v && !(key === "year" && v === "all")),
    );
    return request<Project[]>(`/api/projects?${query.toString()}`);
  },
  createProject: (payload: Partial<Project>) =>
    request<Project>("/api/projects", { method: "POST", body: JSON.stringify(payload) }),
  getProject: (id: string) => request<Project>(`/api/projects/${id}`),
  updateProject: (id: string, payload: Partial<Project>) =>
    request<Project>(`/api/projects/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  archiveProject: (id: string) => request<void>(`/api/projects/${id}/archive`, { method: "POST" }),
  /** 접수로 되돌리기 (TODO 171) — 미리보기 · 실행 */
  toIntakePlan: (id: string) => request<DemotePlan>(`/api/projects/${encodeURIComponent(id)}/to-intake`),
  toIntake: (id: string) =>
    request<{ intake_id: string }>(`/api/projects/${encodeURIComponent(id)}/to-intake`, { method: "POST" }),
  /**
   * 이 시작일로 만들면 어떤 번호가 붙는지 (TODO 95).
   * 번호의 연도는 **등록한 날이 아니라 착수년도**다 — 적어 두기보다 실제 번호를 보여 준다.
   */
  nextProjectId: (startDate: string) =>
    request<{ id: string; year: number }>(
      `/api/projects/next-id${startDate ? `?start_date=${encodeURIComponent(startDate)}` : ""}`,
    ),
  /** 번호의 연도가 시작일과 어긋났는지, 옮기면 몇 번이 되는지. 파일은 건드리지 않는다. */
  yearFixPlan: (id: string) => request<YearFix>(`/api/projects/${id}/year-fix`),
  /** 미리보기대로 이 과제 하나의 번호를 옮긴다. */
  yearFixApply: (id: string) => request<YearFix>(`/api/projects/${id}/year-fix`, { method: "POST" }),
  /** 끝난 과제를 바탕으로 새 과제를 만든다 (TODO 109). 개요·담당자·태그가 넘어오고 이력은 남지 않는다. */
  cloneProject: (id: string) => request<Project>(`/api/projects/${id}/clone`, { method: "POST" }),
  listEntries: (projectId: string) => request<Entry[]>(`/api/projects/${projectId}/entries`),
  createEntry: (projectId: string, payload: Partial<Entry>) =>
    request<Entry>(`/api/projects/${projectId}/entries`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateEntry: (id: number, payload: Partial<Entry>) =>
    request<Entry>(`/api/entries/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteEntry: (id: number) => request<void>(`/api/entries/${id}`, { method: "DELETE" }),
  listEntryAttachments: (entryId: number) =>
    request<Attachment[]>(`/api/entries/${entryId}/attachments`),
  projectAttachments: (projectId: string) =>
    request<{ items: Attachment[]; total_bytes: number; orphan_count: number }>(
      `/api/projects/${projectId}/attachments`,
    ),
  deleteAttachment: (id: number) => request<void>(`/api/attachments/${id}`, { method: "DELETE" }),
  settings: () => request<AppSettings>("/api/settings"),
  settingsDefaults: () =>
    request<{
      entry_template: string;
      report_template: string;
      ai_prompt_prefix: string;
      intake_template: string;
      precheck_items: string;
      precheck_thresholds: [number, number];
    }>(
      "/api/settings/defaults",
    ),
  /** 이 보고를 AI 에게 넘길 글. **서버가 AI 를 부르지는 않는다** (TODO 71). */
  aiPrompt: (reportId: number) => request<{ text: string }>(`/api/reports/${reportId}/ai-prompt`),
  people: () => request<{ people: Person[]; unregistered: { name: string; used: number }[] }>("/api/people"),
  savePeople: (people: Person[]) =>
    request<{ people: Person[] }>("/api/people", { method: "PUT", body: JSON.stringify({ people }) }),
  addPerson: (name: string) =>
    request<{ people: Person[] }>("/api/people", { method: "POST", body: JSON.stringify({ name }) }),
  /** 담당자를 넘긴다 (TODO 122). 표기 통일과 달리 **명부는 그대로** 두고, 끝난 과제는 뺀다. */
  handover: (old: string, next: string, includeFinished = false) =>
    request<{ count: number; changed: string[] }>("/api/people/handover", {
      method: "POST",
      body: JSON.stringify({ old, new: next, include_finished: includeFinished }),
    }),
  renameOwner: (old: string, next: string) =>
    request<{ count: number; changed: string[] }>("/api/people/rename", {
      method: "POST",
      body: JSON.stringify({ old, new: next }),
    }),
  trash: () => request<TrashItem[]>("/api/trash"),
  restoreFromTrash: (name: string) =>
    request<{ restored_to: string; label: string }>(
      `/api/trash/${encodeURIComponent(name)}/restore`,
      { method: "POST" },
    ),
  saveSettings: (payload: Partial<AppSettings>) =>
    request<AppSettings>("/api/settings", { method: "PUT", body: JSON.stringify(payload) }),
  listReports: (projectId: string) => request<Report[]>(`/api/projects/${projectId}/reports`),
  createDraft: (projectId: string, reportDate?: string, audience?: string) =>
    request<Report>(`/api/projects/${projectId}/reports/draft`, {
      method: "POST",
      body: JSON.stringify({ report_date: reportDate ?? null, audience: audience ?? null }),
    }),
  getReport: (id: number) => request<Report>(`/api/reports/${id}`),
  updateReport: (
    id: number,
    payload: { title?: string; body?: string; audience?: string; report_date?: string; feedback?: string },
  ) =>
    request<Report>(`/api/reports/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  freezeReport: (id: number) => request<Report>(`/api/reports/${id}/freeze`, { method: "POST" }),
  unfreezeReport: (id: number) => request<Report>(`/api/reports/${id}/unfreeze`, { method: "POST" }),
  /** 보고 지시사항에 답했다/아직 (TODO 107). */
  feedbackDone: (id: number, done = true) =>
    request<Report>(`/api/reports/${id}/feedback-done`, {
      method: "POST",
      body: JSON.stringify({ done }),
    }),
  deleteReport: (id: number) => request<void>(`/api/reports/${id}`, { method: "DELETE" }),
  listReportAttachments: (id: number) => request<Attachment[]>(`/api/reports/${id}/attachments`),
  /** 지난 보고 대비 변경분 (T11). */
  reportDiff: (id: number) => request<ReportDiff>(`/api/reports/${id}/diff`),
  /** 과제를 가로질러 보고를 찾는다 (T13). */
  searchReports: (filters: {
    audience?: string;
    from?: string;
    to?: string;
    q?: string;
    state?: string;
    feedback?: string;
  }) => {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value) params.set(key, value);
    }
    const query = params.toString();
    return request<ReportHistoryItem[]>(`/api/reports${query ? `?${query}` : ""}`);
  },
  /**
   * 폴더 고르기 (TODO 97) — 브라우저는 고른 폴더의 실제 경로를 주지 않으므로
   * 서버가 목록을 주고 화면에서 눌러 들어간다. 내주는 것은 폴더 이름과 경로뿐이다.
   */
  listFolders: (path: string) =>
    request<FolderListing>(`/api/folders${path ? `?path=${encodeURIComponent(path)}` : ""}`),
  createFolder: (parent: string, name: string) =>
    request<{ path: string }>("/api/folders", {
      method: "POST",
      body: JSON.stringify({ parent, name }),
    }),
  /**
   * 과제 속성 목록 (TODO 100). 줄마다 **그 속성을 쓰는 과제 수**가 함께 온다 —
   * 쓰고 있는 속성은 뺄 수 없으므로 화면이 그 사실을 알아야 한다.
   */
  projectTypes: () =>
    request<{ types: ProjectTypeRow[]; orphans: { key: string; count: number }[] }>(
      "/api/settings/project-types",
    ),
  saveProjectTypes: (types: { key: string; label: string }[]) =>
    request<{ types: ProjectTypeRow[]; orphans: { key: string; count: number }[] }>(
      "/api/settings/project-types",
      { method: "PUT", body: JSON.stringify({ types }) },
    ),
  /** 과제 번호를 새 팀 코드로 한 번에 맞춘다. preview 는 파일을 건드리지 않는다. */
  renumberPreview: (code: string) =>
    request<RenumberPlan>("/api/settings/project-code/renumber/preview", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),
  renumberApply: (code: string) =>
    request<{ code: string; changed: { id: string; new_id: string; title: string }[] }>(
      "/api/settings/project-code/renumber",
      { method: "POST", body: JSON.stringify({ code }) },
    ),
  reportCandidates: (options: {
    includeInactive?: boolean;
    status?: string;
    type?: string;
    owner?: string;
    sort?: string;
    order?: string;
  } = {}) => {
    const params = new URLSearchParams({ include_inactive: String(options.includeInactive ?? false) });
    for (const key of ["status", "type", "owner", "sort", "order"] as const) {
      if (options[key]) params.set(key, options[key] as string);
    }
    return request<{
      cycle_days: number;
      default_report_date: string;
      /** 확정을 기다리는 초안. 후보보다 먼저 걸리는 일이라 함께 받는다 (TODO 91) */
      drafts: OpenDraft[];
      items: ReportCandidate[];
    }>(`/api/report-candidates?${params.toString()}`);
  },
  spreadsheetPreview: (attachmentId: number) =>
    request<SpreadsheetPreview>(`/api/attachments/${attachmentId}/preview`),
  /** 첨부가 알려 준 미리보기 주소로 — 과제 첨부와 접수 첨부가 주소만 다르다 (TODO 138) */
  spreadsheetPreviewAt: (url: string) => request<SpreadsheetPreview>(url),
  search: (query: string) => request<SearchResults>(`/api/search?q=${encodeURIComponent(query)}`),
  /** 이 문서의 이전 버전 (TODO 37-1). path 는 vault 기준 상대경로. */
  versions: (path: string) =>
    request<{ path: string; items: DocumentVersion[] }>(
      `/api/versions?path=${encodeURIComponent(path)}`,
    ),
  versionContent: (path: string, stamp: string) =>
    request<{ text: string }>(
      `/api/versions/content?path=${encodeURIComponent(path)}&stamp=${encodeURIComponent(stamp)}`,
    ),
  restoreVersion: (path: string, stamp: string) =>
    request<{ restored_from: string }>("/api/versions/restore", {
      method: "POST",
      body: JSON.stringify({ path, stamp }),
    }),
  versionsOverview: () =>
    request<{ versions: number; documents: number; total_bytes: number; keep_days: number }>(
      "/api/versions/overview",
    ),
  backupStatus: () => request<BackupStatus>("/api/settings/backup/status"),
  backupNow: () =>
    request<{ file: string; bytes: number; directory: string }>("/api/settings/backup/run", {
      method: "POST",
    }),
  errors: () => request<{ items: ErrorEntry[]; keep_months: number }>("/api/errors"),
  /** 깨진 첨부 링크 정리 (TODO 116). 먼저 세고, 그다음 고친다. */
  linkFixScan: (includeFrozen: boolean) =>
    request<LinkFixReport>(`/api/maintenance/link-fix${includeFrozen ? "?include_frozen=true" : ""}`),
  linkFixApply: (includeFrozen: boolean) =>
    request<LinkFixReport>("/api/maintenance/link-fix", {
      method: "POST",
      body: JSON.stringify({ include_frozen: includeFrozen }),
    }),
  clearErrors: () => request<{ removed_files: number }>("/api/errors", { method: "DELETE" }),
  reindex: () =>
    request<{ indexed: number; problems: { path: string; reason: string }[] }>("/api/reindex", {
      method: "POST",
    }),
};
