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
  tags: string[];
  entry_count: number;
  body?: string;
  dir_name?: string;
  /** 상세 조회에서만 채워지는 요약용 수치 */
  unreported_entries?: number;
  report_count?: number;
  attachment_count?: number;
  attachment_bytes?: number;
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
  days_since_report: number | null;
  unreported_entries: number;
  latest_entry_date: string | null;
  score: number;
  never_reported: boolean;
}

export interface SpreadsheetPreview {
  orig_name: string;
  sheets: { name: string; rows: string[][]; images: string[] }[];
  truncated: boolean;
}


export interface AppSettings {
  /** 지금은 설정에서 정한 사용자, 나중에는 로그인한 사용자가 된다. */
  author: string;
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
  candidates: ReportCandidate[];
}
