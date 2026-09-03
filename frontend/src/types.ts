export interface StatusInfo {
  key: string;
  label: string;
  candidate: boolean;
  collapsed: boolean;
}

export interface TypeInfo {
  key: string;
  label: string;
}

export interface Meta {
  statuses: StatusInfo[];
  types: TypeInfo[];
  groups: string[];
  tags: string[];
  owners: string[];
  audiences: string[];
  /** 담당자 명부 — 자동완성이 먼저 쓰는 표준 이름 목록 */
  people: string[];
  /** 과제 번호의 팀·부문 코드 (비면 2026-001) */
  project_code: string;
  /** 주간 보고 요일 (0=월 … 6=일) */
  report_weekday: number;
  vault: string;
  report_cycle_days: number;
}

export interface Project {
  id: string;
  title: string;
  status: string;
  type: string | null;
  group: string | null;
  owners: string[];
  start_date: string | null;
  due_date: string | null;
  created_at: string | null;
  updated_at: string | null;
  last_reported_at: string | null;
  /** 과제 효과 (억원/년). 기대효과는 착수 시, 실증효과는 끝난 뒤 채운다. */
  effect_expected: number | null;
  effect_verified: number | null;
  /** 과제를 등록한 사람. 담당자(누가 하는가)와 다르다. */
  created_by?: string | null;
  tags: string[];
  entry_count: number;
  body?: string;
  dir_name?: string;
  /** 상세 조회에서만 채워지는 요약용 수치 */
  unreported_entries?: number;
  report_count?: number;
  attachment_count?: number;
  attachment_bytes?: number;
  /** 새 진행일지를 시작할 서식 (설정에서 속성별로 바꿀 수 있다) */
  entry_template?: string;
}

export interface Entry {
  id: number;
  project_id: string;
  rel_path: string;
  date: string;
  title: string;
  author: string | null;
  body?: string;
  created_at: string | null;
  updated_at: string | null;
  tags: string[];
  /** 이 기록이 담긴 확정 보고의 날짜. 없으면 아직 보고 전이다. */
  reported_on?: string | null;
}

export interface SearchResults {
  query: string;
  projects: {
    id: string;
    title: string;
    status: string;
    group: string | null;
    updated_at: string | null;
    snippet: string;
  }[];
  entries: {
    id: number;
    project_id: string;
    project_title: string;
    date: string;
    title: string;
    snippet: string;
  }[];
  /** 보고 문서 (제목·본문·피보고자로 찾는다) */
  reports: {
    id: number;
    project_id: string;
    project_title: string;
    report_date: string;
    title: string | null;
    audience: string | null;
    frozen: boolean;
    snippet: string;
  }[];
  attachments: {
    id: number;
    project_id: string;
    project_title: string;
    orig_name: string;
    rel_path: string;
    size_bytes: number | null;
  }[];
  total: number;
}

export interface Report {
  id: number;
  project_id: string;
  report_date: string;
  title: string;
  author: string | null;
  audience: string | null;
  rel_path: string;
  doc_dir: string;
  covers_from: string | null;
  covers_to: string | null;
  frozen_at: string | null;
  frozen: boolean;
  entry_count: number;
  body?: string;
}

export interface ReportCandidate {
  id: string;
  title: string;
  status: string;
  type: string | null;
  group: string | null;
  due_date: string | null;
  last_reported_at: string | null;
  /** 마지막으로 확정한 보고의 피보고자·회의체. 날짜만으로는 보고 수준을 알 수 없다. */
  last_report_audience: string | null;
  /** 그 보고 문서. 눌러서 바로 열 수 있게 한다. */
  last_report_id: number | null;
  /** 담당자. 보고 대상 표에서 거르기에 쓴다. */
  owners: string[];
  days_since_report: number | null;
  unreported_entries: number;
  latest_entry_date: string | null;
  never_reported: boolean;
}

export interface SpreadsheetPreview {
  orig_name: string;
  sheets: { name: string; rows: string[][]; images: string[] }[];
  truncated: boolean;
}


export interface Person {
  name: string;
  employee_id: string;
  account: string;
  used?: number;
}

export interface AppSettings {
  /** 지금은 설정에서 정한 사용자, 나중에는 로그인한 사용자가 된다. */
  author: string;
  /** 과제 속성별 진행일지 서식. "" 키가 공통 서식. */
  entry_templates: Record<string, string>;
  /** 보고 초안 서식. {summary} 자리에 미보고 진행일지가 들어간다. */
  report_template: string;
  /** 담당자 명부 (설정 파일에 저장되는 원본) */
  people: Person[];
  /** 과제 번호의 팀·부문 코드. 비우면 2026-001. */
  project_code: string;
  /** 주간 보고 요일 (0=월 … 6=일). 보고 예정일과 알림이 함께 따라간다. */
  report_weekday: number;
}

export interface TrashItem {
  trash_name: string;
  kind: string | null;
  kind_label: string | null;
  label: string;
  project_id: string | null;
  deleted_at: string | null;
  origin: string | null;
  restorable: boolean;
  is_folder: boolean;
}

export interface DashboardCount {
  key: string;
  label: string;
  count: number;
}

/** 메인 상단 대시보드. 지금 무엇을 봐야 하는지만 담는다. */
export interface Dashboard {
  total: number;
  statuses: DashboardCount[];
  types: DashboardCount[];
  /** 담당자별 과제 수. 한 과제에 여러 명일 수 있어 합이 total 보다 클 수 있다. */
  owners: DashboardCount[];
  due_soon: number;
  due_soon_days: number;
  overdue: number;
  report_date: string;
  /** 오늘이 선정일·보고일일 때만 채워진다. 매일 뜨면 곧 안 보게 된다. */
  reminder: ReportReminder | null;
  candidates: ReportCandidate[];
}

/** 보고 주기 알림 (T12). */
export interface ReportReminder {
  /** select = 오늘 고르는 날, report = 오늘 보고하는 날 */
  phase: "select" | "report";
  report_date: string;
  /** 그 날짜로 만들어 둔 초안 수 */
  drafts: number;
  /** 그 날짜로 이미 확정한 보고 수 */
  done: number;
  /** 아직 보고에 담기지 않은 진행일지를 가진 과제 수 */
  pending: number;
}

/** 과제를 가로질러 본 보고 한 건 (T13). 본문은 담지 않는다. */
export interface ReportHistoryItem {
  id: number;
  project_id: string;
  project_title: string;
  project_status: string;
  project_type: string | null;
  report_date: string;
  title: string | null;
  audience: string | null;
  author: string | null;
  frozen_at: string | null;
  frozen: boolean;
  covers_from: string | null;
  covers_to: string | null;
  entry_count: number;
  excerpt: string;
}

/** 지난 보고 대비 변경분 (T11). */
export interface ReportDiff {
  previous: { id: number; report_date: string; title: string | null; audience: string | null } | null;
  added: number;
  removed: number;
  lines: { kind: "add" | "del" | "same" | "gap"; text: string }[];
}

/** 과제 번호 일괄 변경 미리보기. */
export interface RenumberPlan {
  code: string;
  total: number;
  changes: {
    id: string;
    title: string;
    new_id: string;
    dir_name: string;
    new_dir_name: string;
    renumbered: boolean;
  }[];
  skipped: { id: string; title: string; skip: string }[];
}

/** 오류 기록 한 줄. 과제 내용은 담기지 않는다 — 동작과 오류 종류뿐이다. */
export interface ErrorEntry {
  at: string;
  /** 실패한 동작. 예: "PATCH /api/reports/3" */
  action: string;
  status: number | null;
  error: string | null;
  detail: string | null;
  /** 실패 직전에 한 동작 3개. "왜 그 상태가 됐는지"의 단서다. */
  trail: string[];
}
