import type { YearCard, YearCardListing, YearCardLines, ToolDictionary, RestoreJob, RunningTask, DemotePlan, Roadmap, Meeting, MeetingListing, Activity, ActivitySummary, AppSettings, BackupStatus, Dashboard, Home, MonthGrid, DocumentVersion, Entry, ErrorEntry, LinkFixReport, Meta, OpenDraft, Project, RenumberPlan, Report, ReportCandidate, ReportDiff, ReportHistoryItem, SearchResults, SpreadsheetPreview, Person, ProjectTypeRow, TrashItem, YearFix, FolderListing, Intake, IntakeDetail, IntakeListing, PromotionPlan, Partner, Experience, ExperienceListing, ExperiencePrompt, ExperienceResponseFile, ImportDecision, ImportPreview, SkillDictionary, UnknownTag, TagDecision, TagProposal, ExportOptions, ExportResult, ExportLogRow, AnonymizeCandidates, BackupJob, BackupEstimate } from "./types";
import type { Attachment } from "./upload";
import type { Contribution, EditItem, Health, Me, MyWork, PersonHistory, RestoreResult, RetroDue, Visitor, YearReview } from "./types";
import { notifyError } from "./notify";

/**
 * 선행 과제 고르기용 가벼운 목록 (TODO 212) — 과제 폼이 열릴 때마다 전체 과제(200+ 줄, 모든 칸)를 받던 것을
 * **창마다 한 번** 받아 번호 · 제목만 들고 있는다. 과제를 만들거나 · 고치거나 · 지우거나 · 번호를 바꾸면 비운다.
 */
let projectOptionsCache: Promise<{ id: string; title: string }[]> | null = null;

export function forgetProjectOptions(): void {
  projectOptionsCache = null;
}

/** 쓰기 요청이 끝나면 목록 기억을 비운다 — 실패해도(일부만 바뀌었을 수 있다) */
function invalidating<T>(work: Promise<T>): Promise<T> {
  return work.finally(forgetProjectOptions);
}

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
  // 서버가 사람 말로 한 줄 정리해 주면 그것이 먼저 (TODO 205) — 422 의 `message` 는 "기대효과: 숫자로 적어 주세요" 처럼 항목 이름이 든다
  const message = (body as { message?: unknown } | null)?.message;
  if (typeof message === "string" && message.trim()) return message;
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    // 사유 목록의 msg 도 이제 한국어다 — 한글이 든 것만 이어 쓴다(영어 기본 문구 "Field required" 같은 것은
    // 아래의 "항목: …" 안내가 낫다)
    const messages = [
      ...new Set(
        detail
          .map((item) => (typeof item?.msg === "string" ? item.msg.trim() : ""))
          .filter((text): text is string => /[가-힣]/.test(text)),
      ),
    ];
    if (messages.length > 0) return messages.join(" · ");
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
  // 전체 백업에서 되살리기 (TODO 246) — 살펴보기는 파일 올리기라 RestoreCard 가 uploadAttachment 로 부른다
  restoreBackup: (token: string) =>
    request<RestoreResult>("/api/backup/restore", { method: "POST", body: JSON.stringify({ token }) }),
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
    invalidating(
      request<{ project_id: string; intake: IntakeDetail }>(`/api/intakes/${encodeURIComponent(id)}/promote`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    ),
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
  /** 지난 예정을 [다녀옴] 으로 확인 (TODO 231) — 확인한 날만 적는다 */
  checkActivityPlan: (id: number) => request<{ plan_checked: string }>(`/api/activities/${id}/plan-check`, { method: "POST" }),
  // 팀원 면담 (TODO 182)
  meetings: (person?: string) =>
    request<MeetingListing>(`/api/meetings${person ? `?person=${encodeURIComponent(person)}` : ""}`),
  createMeeting: (payload: Partial<Meeting>) =>
    request<{ id: number }>("/api/meetings", { method: "POST", body: JSON.stringify(payload) }),
  updateMeeting: (id: number, payload: Partial<Meeting>) =>
    request<{ ok: boolean }>(`/api/meetings/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteMeeting: (id: number) => request<void>(`/api/meetings/${id}`, { method: "DELETE" }),
  listProjects: (params: Record<string, string>) => {
    // `year=all` 은 **주소의 말**이다(연도 전체). 서버는 네 자리 연도나 빈 값만 받는다 —
    // 부르는 쪽마다 바꾸게 두면 한 곳이 빠진다(TODO 140: 병합 칸이 422 로 빈 목록을 보였다).
    const query = new URLSearchParams(
      Object.entries(params).filter(([key, v]) => v && !(key === "year" && v === "all")),
    );
    return request<Project[]>(`/api/projects?${query.toString()}`);
  },
  /**
   * 과제 만들기. 서버가 막지는 않지만 알릴 것(같은 이름 과제 등, `warnings`)을 주면 아래 알림으로 띄운다 (TODO 205 · 212) —
   * 만드는 길이 여럿(새 과제 · 이 과제로 새 과제)이라 한 자리에서.
   */
  createProject: (payload: Partial<Project>) =>
    invalidating(request<Project>("/api/projects", { method: "POST", body: JSON.stringify(payload) })).then((created) => {
      for (const warning of Array.isArray(created?.warnings) ? created.warnings : []) {
        // 같은 이름 · 효과 · 선행 과제 연도는 과제 폼이 저장 **전에** 보였다 — 두 번 알리지 않는다 (TODO 214 D11)
        if (typeof warning === "string" && warning.trim() && !/같은 이름|효과|선행 과제/.test(warning))
          notifyError(`만들었습니다 — ${warning}`);
      }
      return created;
    }),
  /** 선행 과제 자동완성용 번호 · 제목 (TODO 212) — 창마다 한 번, 바뀌면 다시 */
  projectOptions: () => {
    if (!projectOptionsCache) {
      projectOptionsCache = request<Project[]>("/api/projects")
        .then((rows) => rows.map((row) => ({ id: row.id, title: row.title })))
        .catch((err: unknown) => {
          projectOptionsCache = null; // 실패는 기억하지 않는다 — 다음에 다시
          throw err;
        });
    }
    return projectOptionsCache;
  },
  getProject: (id: string) => request<Project>(`/api/projects/${id}`),
  updateProject: (id: string, payload: Partial<Project> & { base_updated_at?: string }) =>
    invalidating(request<Project>(`/api/projects/${id}`, { method: "PATCH", body: JSON.stringify(payload) })),
  /** 담당과 역할 한 사람 줄 (TODO 237) — 보낸 칸만 바뀐다. 팀원은 자기 줄만, 기간은 팀장만 */
  updateContribution: (
    id: string,
    name: string,
    payload: Partial<Pick<Contribution, "role" | "part" | "from" | "to" | "did" | "result" | "skills" | "praise" | "milestones">> & { base_updated_at?: string },
  ) =>
    request<Project>(`/api/projects/${encodeURIComponent(id)}/contributions/${encodeURIComponent(name)}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  /** 사람별 이력 — 맡은 과제(역할 · 기간 · 회고) · 교육 이력 (TODO 238) */
  // ── 팀원별 경험 (TODO 257) ──────────────────────────
  experiences: (person: string) => request<ExperienceListing>(`/api/experiences?person=${encodeURIComponent(person)}`),
  experience: (id: string) => request<Experience>(`/api/experiences/${encodeURIComponent(id)}`),
  createExperience: (payload: Partial<Experience>) =>
    request<Experience>("/api/experiences", { method: "POST", body: JSON.stringify(payload) }),
  updateExperience: (id: string, payload: Partial<Experience> & { base_updated_at?: string }) =>
    request<Experience>(`/api/experiences/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteExperience: (id: string) => request<void>(`/api/experiences/${encodeURIComponent(id)}`, { method: "DELETE" }),
  draftExperiences: (person: string, projects?: string[]) =>
    request<{ made: string[]; skipped: { project: string; reason: string }[] }>("/api/experiences/draft", {
      method: "POST", body: JSON.stringify({ person, projects }),
    }),
  // ── 역량 사전 · 정합성 · 확정 (TODO 260) ─────────────
  experienceSkills: () => request<SkillDictionary>("/api/experiences/skills"),
  // 연말 회고 카드 (TODO 285)
  yearCards: (year: string) => request<YearCardListing>(`/api/yearcards?year=${year}`),
  yearCard: (name: string, year: string) => request<YearCard>(`/api/yearcards/card?name=${encodeURIComponent(name)}&year=${year}`),
  yearCardsMany: (year: string, names: string[]) =>
    request<{ year: string; cards: YearCard[] }>(`/api/yearcards/cards?year=${year}&names=${encodeURIComponent(names.join(","))}`),
  saveYearCard: (name: string, year: string, body: {
    message: string; headline: string; projects: string[]; lines: YearCardLines; skills: string[]; tools: string[];
  }) =>
    request<YearCard>(`/api/yearcards/card?name=${encodeURIComponent(name)}&year=${year}`, { method: "PUT", body: JSON.stringify(body) }),
  // 보유 기술 사전 (TODO 273)
  experienceTools: () => request<ToolDictionary>("/api/experiences/tools"),
  // 분류 넷의 값 정리 · 역량 이름 바꾸기 (TODO 275)
  classificationUsage: () =>
    request<{ usage: Record<string, { value: string; projects: number; intakes: number; listed: boolean }[]> }>("/api/settings/classifications/usage"),
  renameClassification: (field: string, old: string, next: string) =>
    request<{ field: string; old: string; new: string; merged: boolean; projects: number; intakes: number }>("/api/settings/classifications/rename", {
      method: "POST", body: JSON.stringify({ field, old, new: next }),
    }),
  renameSkillTags: (source: { axis: string; name: string }, target: { axis: string; name: string }) =>
    request<{ changed: string[] }>("/api/experiences/skills/rename", { method: "POST", body: JSON.stringify({ source, target }) }),
  rematchTools: () => request<{ changed: string[] }>("/api/experiences/tools/rematch", { method: "POST" }),
  mergeSkill: (source: { axis: string; name: string }, target: { axis: string; name: string }) =>
    request<{ changed: string[] }>("/api/experiences/skills/merge", { method: "POST", body: JSON.stringify({ source, target }) }),
  rematchSkills: (person: string) =>
    request<{ changed: string[] }>("/api/experiences/skills/rematch", { method: "POST", body: JSON.stringify({ person }) }),
  confirmExperience: (id: string) => request<Experience>(`/api/experiences/${encodeURIComponent(id)}/confirm`, { method: "POST" }),
  unconfirmExperience: (id: string) => request<Experience>(`/api/experiences/${encodeURIComponent(id)}/unconfirm`, { method: "POST" }),
  acknowledgeWarning: (id: string, code: string, key: string) =>
    request<Experience>(`/api/experiences/${encodeURIComponent(id)}/acknowledge`, { method: "POST", body: JSON.stringify({ code, key }) }),
  // ── 태그 정리함 · 업무 이력 파일 (TODO 262) ─────────
  unknownTags: () => request<{ items: UnknownTag[] }>("/api/experiences/skills/unknown"),
  cleanupTags: (actions: TagDecision[]) =>
    request<{ changed: string[]; dictionary: number; failed?: { id: string; person: string; reason: string }[]; left?: number }>("/api/experiences/skills/cleanup", { method: "POST", body: JSON.stringify({ actions }) }),
  tagPrompt: () => request<{ text: string; chars: number; tags: number }>("/api/experiences/skills/prompt"),
  tagAnswer: (text: string) =>
    request<{ items: TagProposal[] }>("/api/experiences/skills/answer", { method: "POST", body: JSON.stringify({ text }) }),
  addSuggestedAliases: () => request<{ added: number }>("/api/experiences/skills/suggest", { method: "POST" }),
  exportFile: (person: string, o: ExportOptions) => {
    const q = new URLSearchParams({ person, scope: o.scope });
    if (o.start) q.set("start", o.start);
    if (o.end) q.set("end", o.end);
    if (o.ids?.length) q.set("ids", o.ids.join(","));
    for (const key of ["structured", "ids_in", "money", "anonymize"] as const) if (o[key] !== undefined) q.set(key, String(o[key]));
    return request<ExportResult>(`/api/experiences/export?${q.toString()}`);
  },
  logExport: (person: string, o: ExportOptions, how: "저장" | "복사") =>
    request<{ logged: boolean }>("/api/experiences/export/log", { method: "POST", body: JSON.stringify({ person, ...o, how }) }),
  exportLog: (person: string) => request<{ items: ExportLogRow[] }>(`/api/experiences/export/log?person=${encodeURIComponent(person)}`),
  anonymizeCandidates: (person: string) =>
    request<AnonymizeCandidates>(`/api/experiences/anonymize/candidates?person=${encodeURIComponent(person)}`),
  // ── 응답 되받기 (TODO 258) ──────────────────────────
  experiencePrompt: (person: string, projects?: string[]) =>
    request<ExperiencePrompt>(
      `/api/experiences/prompt?person=${encodeURIComponent(person)}` +
        (projects ? `&projects=${encodeURIComponent(projects.join(","))}` : ""),
    ),
  readExperienceResponse: (payload: { person: string; text: string; projects: string[]; append_to?: string }) =>
    request<ImportPreview>("/api/experiences/read", { method: "POST", body: JSON.stringify(payload) }),
  importExperiences: (payload: { person: string; response: string; items: ImportDecision[] }) =>
    request<{ made: string[]; merged: string[]; dropped: number }>("/api/experiences/import", {
      method: "POST", body: JSON.stringify(payload),
    }),
  experienceResponse: (person: string, name: string) =>
    request<ExperienceResponseFile>(`/api/experiences/responses/${encodeURIComponent(person)}/${encodeURIComponent(name)}`),
  experienceResponseSummary: (person: string, name: string) =>
    request<{ text: string }>(`/api/experiences/responses/${encodeURIComponent(person)}/${encodeURIComponent(name)}/summary`),
  personHistory: (name: string) => request<PersonHistory>(`/api/person-history?name=${encodeURIComponent(name)}`),
  /** 나의 한 해 (TODO 244) */
  yearReview: (name: string, year: string) =>
    request<YearReview>(`/api/person-history/year?name=${encodeURIComponent(name)}&year=${year}`),
  /** 내 할 일 — 내 진행 과제 · 일지 알림 · 회고를 적을 과제 · 인정 한 줄 (TODO 242) */
  myWork: () => request<MyWork>("/api/projects/my-work"),
  /** 회고를 적을 과제 — 내 것, 끝난 지 1년 안 (TODO 237) */
  retroDue: () => request<RetroDue>("/api/projects/retro-due"),
  archiveProject: (id: string) => invalidating(request<void>(`/api/projects/${id}/archive`, { method: "POST" })),
  /** 접수로 되돌리기 (TODO 171) — 미리보기 · 실행 */
  toIntakePlan: (id: string) => request<DemotePlan>(`/api/projects/${encodeURIComponent(id)}/to-intake`),
  toIntake: (id: string) =>
    invalidating(request<{ intake_id: string }>(`/api/projects/${encodeURIComponent(id)}/to-intake`, { method: "POST" })),
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
  yearFixApply: (id: string) => invalidating(request<YearFix>(`/api/projects/${id}/year-fix`, { method: "POST" })),
  /** 끝난 과제를 바탕으로 새 과제를 만든다 (TODO 109). 개요·담당자·태그가 넘어오고 이력은 남지 않는다. */
  // 다년도 과제 로드맵 (TODO 174)
  roadmap: () => request<Roadmap>("/api/roadmap"),
  // 미리 채울 값만 — 만들지 않는다. [만들기] 가 createProject 를 부른다 (TODO 173)
  cloneDraft: (id: string) => request<Partial<Project>>(`/api/projects/${encodeURIComponent(id)}/clone`),
  listEntries: (projectId: string) => request<Entry[]>(`/api/projects/${projectId}/entries`),
  createEntry: (projectId: string, payload: Partial<Entry>) =>
    request<Entry>(`/api/projects/${projectId}/entries`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateEntry: (id: number, payload: Partial<Entry> & { base_updated_at?: string }) =>
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
  // 오늘 바깥에서 접속한 주소 (TODO 233)
  peopleVisitors: () => request<{ items: Visitor[] }>("/api/people/visitors"),
  // 지금 누구인가 (TODO 233)
  me: () => request<Me>("/api/me"),
  // 팀원이 고친 것 — 팀장 홈 (TODO 233 ⑥)
  recentEdits: () => request<{ days: number; items: EditItem[] }>("/api/edits/recent"),
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
    invalidating(
      request<{ restored_to: string; label: string; attachments_left?: string[] }>(
        `/api/trash/${encodeURIComponent(name)}/restore`,
        { method: "POST" },
      ),
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
    invalidating(
      request<{ code: string; changed: { id: string; new_id: string; title: string }[] }>(
        "/api/settings/project-code/renumber",
        { method: "POST", body: JSON.stringify({ code }) },
      ),
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
  search: (query: string, sort: "relevance" | "recent" = "relevance", limit?: number) =>
    request<SearchResults>(`/api/search?q=${encodeURIComponent(query)}${sort === "recent" ? "&sort=recent" : ""}${limit ? `&limit=${limit}` : ""}`),
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
    invalidating(
      request<{ indexed: number; problems: { path: string; reason: string }[] }>("/api/reindex", {
        method: "POST",
      }),
    ),
  /** 점검 (TODO 204 · 206) — 첨부 전체 용량 · 이전 버전 보관 실패. 새 칸은 서버가 아직 안 줄 수도 있다 */
  health: () => request<Health>("/api/health"),
  // 전체 백업 진행 표시 (TODO 266)
  backupEstimate: (assets: boolean) => request<BackupEstimate>(`/api/backup/estimate?assets=${assets ? "all" : "none"}`),
  startBackupJob: (assets: boolean) => request<BackupJob>("/api/backup/jobs", { method: "POST", body: JSON.stringify({ assets }) }),
  currentBackupJob: () => request<{ job: BackupJob | null }>("/api/backup/jobs/current"),
  backupJob: (id: string) => request<BackupJob>(`/api/backup/jobs/${id}`),
  cancelBackupJob: (id: string) => request<BackupJob>(`/api/backup/jobs/${id}/cancel`, { method: "POST" }),
  // 되살리기를 뒤에서 · 단계별 진행 (TODO 268)
  startRestoreJob: (token: string) =>
    request<RestoreJob>("/api/backup/restore/jobs", { method: "POST", body: JSON.stringify({ token }) }),
  currentRestoreJob: () => request<{ job: RestoreJob | null }>("/api/backup/restore/jobs/current"),
  restoreJob: (id: string) => request<RestoreJob>(`/api/backup/restore/jobs/${id}`),
  cancelRestoreJob: (id: string) => request<RestoreJob>(`/api/backup/restore/jobs/${id}/cancel`, { method: "POST" }),
  // 지금 도는 오래 걸리는 일 (TODO 268)
  running: (key = "") => request<{ tasks: RunningTask[] }>(`/api/running${key ? `?key=${encodeURIComponent(key)}` : ""}`),
};

// ── TODO 214 D11 — 같은 이름 과제를 저장 **전에** 묻는다 ─────────────────────────────
/** 같은 제목의 과제들. 서버가 아직 이 길을 모르거나 실패하면 빈 목록 — 묻지 못해도 저장은 막지 않는다 */
export function projectTitleCheck(title: string, exclude?: string | null): Promise<{ id: string; title: string }[]> {
  const params = new URLSearchParams({ title });
  if (exclude) params.set("exclude", exclude);
  return request<{ same?: unknown }>(`/api/projects/title-check?${params.toString()}`)
    .then((data) =>
      Array.isArray(data?.same)
        ? (data.same as { id?: unknown; title?: unknown }[])
            .filter((row) => typeof row?.id === "string")
            .map((row) => ({ id: String(row.id), title: String(row.title ?? "") }))
        : [],
    )
    .catch(() => []);
}
