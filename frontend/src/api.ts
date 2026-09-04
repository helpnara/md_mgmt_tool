import type { AppSettings, Dashboard, DocumentVersion, Entry, ErrorEntry, Meta, Project, RenumberPlan, Report, ReportCandidate, ReportDiff, ReportHistoryItem, SearchResults, SpreadsheetPreview, Person, TrashItem } from "./types";
import type { Attachment } from "./upload";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(detail.detail ?? "요청에 실패했습니다.");
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

export const api = {
  meta: () => request<Meta>("/api/meta"),
  dashboard: () => request<Dashboard>("/api/dashboard"),
  listProjects: (params: Record<string, string>) => {
    const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v));
    return request<Project[]>(`/api/projects?${query.toString()}`);
  },
  createProject: (payload: Partial<Project>) =>
    request<Project>("/api/projects", { method: "POST", body: JSON.stringify(payload) }),
  getProject: (id: string) => request<Project>(`/api/projects/${id}`),
  updateProject: (id: string, payload: Partial<Project>) =>
    request<Project>(`/api/projects/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  archiveProject: (id: string) => request<void>(`/api/projects/${id}/archive`, { method: "POST" }),
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
    request<{ entry_template: string; report_template: string }>("/api/settings/defaults"),
  people: () => request<{ people: Person[]; unregistered: { name: string; used: number }[] }>("/api/people"),
  savePeople: (people: Person[]) =>
    request<{ people: Person[] }>("/api/people", { method: "PUT", body: JSON.stringify({ people }) }),
  addPerson: (name: string) =>
    request<{ people: Person[] }>("/api/people", { method: "POST", body: JSON.stringify({ name }) }),
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
    payload: { title?: string; body?: string; audience?: string; report_date?: string },
  ) =>
    request<Report>(`/api/reports/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  freezeReport: (id: number) => request<Report>(`/api/reports/${id}/freeze`, { method: "POST" }),
  unfreezeReport: (id: number) => request<Report>(`/api/reports/${id}/unfreeze`, { method: "POST" }),
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
  }) => {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value) params.set(key, value);
    }
    const query = params.toString();
    return request<ReportHistoryItem[]>(`/api/reports${query ? `?${query}` : ""}`);
  },
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
    return request<{ cycle_days: number; default_report_date: string; items: ReportCandidate[] }>(
      `/api/report-candidates?${params.toString()}`,
    );
  },
  spreadsheetPreview: (attachmentId: number) =>
    request<SpreadsheetPreview>(`/api/attachments/${attachmentId}/preview`),
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
  errors: () => request<{ items: ErrorEntry[]; keep_months: number }>("/api/errors"),
  clearErrors: () => request<{ removed_files: number }>("/api/errors", { method: "DELETE" }),
  reindex: () =>
    request<{ indexed: number; problems: { path: string; reason: string }[] }>("/api/reindex", {
      method: "POST",
    }),
};
