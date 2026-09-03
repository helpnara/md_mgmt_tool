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
  candidates: ReportCandidate[];
}
