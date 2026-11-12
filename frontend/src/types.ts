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
  /** 역량 이력의 구분 (교육·세미나·박람회·학회·자격). 과제의 속성과 다른 축이다. */
  activity_kinds: TypeInfo[];
  /** 팀원 면담의 구분 · 주기(일) (TODO 182) */
  meeting_kinds: string[];
  meeting_cycle_days: number;
  groups: string[];
  /** 그룹을 안 적은 과제가 있는가 — 거르기 상자에 [미지정] 을 세울지 정한다 (TODO 96) */
  groups_none: boolean;
  /** 어디든(과제·진행일지) 실제로 붙어 있는 태그 — 자동완성용 */
  tags: string[];
  /** **과제에** 붙어 있는 태그만 — 과제 목록의 거르기 상자용 (TODO 96) */
  project_tags: string[];
  /** 과제가 실제로 있는 해, 최근 것부터. 거르기 상자는 이것만 세운다 (TODO 96) */
  years: string[];
  owners: string[];
  /** 지금 돌고 있는 배포본 — 배포본-정보.txt (TODO 117). 저장소에서 실행하면 null */
  build?: { name: string; built?: string; source?: string } | null;
  /** 명부에서 떠난 사람 — 딱지와 자동완성 순서에 쓴다 (TODO 122) */
  people_left?: Person[];
  /** 명부의 팀장 (TODO 235) — "팀장" 딱지 · 면담 상대에서 뺀다. 고르지 않았으면 빈칸 */
  leader?: string;
  /** 지금까지 적어 둔 유관부서와 그쪽 담당자 — 자동완성과 거르기에 쓴다 (TODO 92) */
  partner_teams: string[];
  partner_people: string[];
  audiences: string[];
  /** 담당자 명부 — 자동완성이 먼저 쓰는 표준 이름 목록 */
  people: string[];
  /** 과제 번호의 팀·부문 코드 (비면 2026-001) */
  project_code: string;
  /** 주간 보고 요일 (0=월 … 6=일) */
  report_weekday: number;
  vault: string;
  /** 읽기 전용 공유로 보고 있는가 — 바깥에서 온 브라우저 (TODO 191). 서버가 쓰기를 막고, 화면은 쓰기 단추를 숨긴다 */
  readonly?: boolean;
  /** 공유를 켠 주인(서버 PC)에게만 — 팀원에게 알려 줄 주소와 오늘 접속 수 (TODO 192) */
  share?: { url: string; visitors: number; requests: number } | null;
  report_cycle_days: number;
  /** 과제 분류 넷 — 성격 · 분류 · 수행 방식 · 비용구분 (TODO 136). 목록은 설정에서 고친다 */
  classifications: ClassificationInfo[];
  /** 분류 칸을 입력 화면에 세우는 속성 (스마트과제) */
  classified_type: string;
  /** 접수 상태 — pool 은 "풀에 담겨 있는가" (TODO 136) */
  intake_statuses: { key: string; label: string; pool: boolean }[];
  /** 접수 후 이 날수가 지나도 판정이 없으면 묵힌 것이다 */
  intake_stale_days: number;
  /** 사전점검 체크리스트 (TODO 155) */
  precheck: PrecheckMeta;
  /** 마지막으로 vault 를 훑었을 때 읽지 못한 파일 · 값 (TODO 164) */
  problems?: { path: string; reason: string }[];
}

export interface PrecheckItemDef {
  group: string;
  item: string;
  /** [단계, 점수] */
  choices: [string, number][];
}

export interface PrecheckMeta {
  items: PrecheckItemDef[];
  /** [착수 권장 이상, 보완 필요 이상] */
  thresholds: [number, number];
  max: number;
  bands: { key: string; label: string }[];
}

export interface PrecheckBand {
  key: "go" | "fix" | "hold";
  label: string;
}

export interface PrecheckAnswer {
  group: string;
  item: string;
  choice: string;
  score: number;
  max: number;
  note: string | null;
}

export interface PrecheckSummary {
  on: string | null;
  items: PrecheckAnswer[];
  rated: number;
  total_items: number;
  raw: number;
  max: number;
  /** 다 매겼을 때만 — 100점 환산 */
  score: number | null;
  band: PrecheckBand | null;
  /** 지금 체크리스트와 다른 기준으로 매긴 점수 */
  stale: boolean;
  groups: { group: string; score: number; max: number; rated: number; count: number }[];
}

export type ClassificationKey = "nature" | "category" | "delivery" | "cost_kind";

export interface ClassificationInfo {
  key: ClassificationKey;
  label: string;
  items: string[];
}

/** 함께 일하는 팀 하나와 그쪽 담당자들 (TODO 92). */
export interface Partner {
  team: string;
  /** 아직 정해지지 않았으면 빈 목록 — 팀만 정해진 상태도 사실이다 */
  people: string[];
}

export interface Project {
  id: string;
  title: string;
  status: string;
  type: string | null;
  group: string | null;
  owners: string[];
  /** 유관부서와 그쪽 담당자 (TODO 92) */
  partners: Partner[];
  start_date: string | null;
  due_date: string | null;
  /** 완료일 (TODO 104). 상태가 완료가 되는 순간 자동으로 남고, 손으로 고칠 수 있다. */
  completed_at?: string | null;
  created_at: string | null;
  updated_at: string | null;
  last_reported_at: string | null;
  /** 과제 효과 (억원/년). 기대효과는 착수 시, 실증효과는 끝난 뒤 채운다. */
  effect_expected: number | null;
  effect_verified: number | null;
  /** 별도 보고가 필요 없는 과제 — 보고 대상 후보에서만 빠진다 (TODO 80) */
  no_report?: boolean;
  /** 효과 금액으로 관리하지 않는 과제 (TODO 125) */
  no_effect?: boolean;
  /** 과제를 등록한 사람. 담당자(누가 하는가)와 다르다. */
  created_by?: string | null;
  /** 과제 분류 넷 (TODO 136) — 값은 글자 그대로다 */
  nature?: string | null;
  category?: string | null;
  delivery?: string | null;
  cost_kind?: string | null;
  /** 이 과제가 승격된 접수 번호 (TODO 136). 직접 만든 과제는 null */
  intake_id?: string | null;
  /** 선행 과제 번호들 — 다년도 과제의 앞 단계, 여럿일 수 있다 (TODO 172) */
  predecessors?: string[];
  /** 다년도 과제의 단계 — 이어진 과제가 없으면 null (TODO 175) */
  stage?: number | null;
  /** 효과 금액을 세는 해 — 끝나는 해 (TODO 181). 과제목록에서만 온다 */
  effect_year?: string | null;
  /** 그 해의 상태 — 그 해 뒤에 끝났으면 진행중 (TODO 184). 과제목록에서만 온다. `status` 는 지금 상태 */
  year_status?: string | null;
  /** 다년도 과제의 줄기 (상세 조회에서만, TODO 172) */
  lineage?: Lineage;
  /** 이 과제로 승격된 접수 · 이 과제에 병합된 접수 (상세 조회에서만) */
  intakes?: IntakeLink[];
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
  /** 개요가 아직 서식 그대로인가 (TODO 106-B) */
  overview_blank?: boolean;
  /** 지난 보고에서 받고 아직 답하지 않은 지시 (TODO 107) */
  open_feedback?: OpenFeedback[];
  /** 최근 진행일지의 `## 계획` — 다음 할 일 (TODO 112). 없으면 null */
  next_plan?: NextPlan | null;
  /** 만들 때만 — 같은 이름 과제가 있다 등 막지는 않는 알림 (TODO 205) */
  warnings?: string[];
}

/** 진행일지 서식의 계획 칸에서 뽑은 다음 할 일 (TODO 112). */
export interface NextPlan {
  entry_id: number;
  date: string;
  text: string;
}

/** 확정된 보고에 적어 둔 지시 중 아직 답하지 않은 것 (TODO 107). */
export interface OpenFeedback {
  id: number;
  report_date: string;
  audience: string | null;
  feedback: string;
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
  /** 갈래마다 상한이 있어 잘렸는지 — 화면이 "N건" 대신 "N건 이상"이라고 말하는 근거 */
  truncated: { projects?: boolean; entries?: boolean; reports?: boolean; attachments?: boolean; intakes?: boolean; contributions?: boolean; activities?: boolean };
  query: string;
  /** 읽은 질의 (TODO 254) — 낱말 · 빼기 · 칸 · 종류 */
  parsed?: { words: string[]; excludes: string[]; fields: Record<string, string[]>; kinds: string[]; synonyms?: Record<string, string[]> };
  /** 담당과 역할 · 회고 (TODO 254) */
  contributions?: { project_id: string; project_title: string; name: string; role: string; snippet: string }[];
  /** 팀원역량 기록 — 교육 · 행사 (TODO 254) */
  activities?: { id: number; person: string; date: string; kind: string; title: string; host: string; snippet: string }[];
  projects: {
    id: string;
    title: string;
    stage?: number | null;
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
  /** 과제 접수 (TODO 144) — 반려·이관된 것까지 찾는다 */
  intakes?: {
    id: string;
    title: string;
    status: string;
    status_label: string;
    leader: string | null;
    leader_team: string | null;
    received_on: string | null;
    project_id: string | null;
    snippet: string;
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
  /** 보고 뒤에 받은 지시 (TODO 107). 확정된 보고에서도 쓸 수 있다. */
  feedback?: string | null;
  /** 지시에 답한 날. 비어 있으면 아직 답하지 않은 지시다. */
  feedback_done?: string | null;
}

export interface ReportCandidate {
  id: string;
  title: string;
  stage?: number | null;
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
  /** 착수일이 아직 오지 않았다 — 경과일을 숫자로 보여 주지 않는다 (TODO 70). */
  not_started: boolean;
}

export interface SpreadsheetPreview {
  orig_name: string;
  sheets: { name: string; rows: string[][]; images: string[] }[];
  truncated: boolean;
}


export interface Person {
  name: string;
  employee_id: string;
  /** 예전에 쓰던 칸 (TODO 126). 화면에서는 빼고 파일의 값은 그대로 둔다 */
  account?: string;
  used?: number;
  /** 아직 끝나지 않은 과제 중 이 사람이 담당인 수 (TODO 122) */
  unfinished?: number;
  /** 떠난 날. 비어 있으면 지금 있는 사람이다 (TODO 122) */
  left_on?: string;
  /** 전배 · 퇴사 (TODO 122) */
  left_reason?: string;
  /** 팀장 (TODO 235) — 명부에 한 명 */
  leader?: boolean;
  /** 이 사람의 PC 주소 (TODO 233) — 여기서 연 화면은 이 사람으로 본다(담당 과제의 진행일지 · 첨부 · 개요를 고친다) */
  ips?: string[];
  /** 과제 담당 말고 이 이름이 적힌 기록 수 — 면담 · 교육 · 경험 · 접수 리더 · 담당과 역할 (TODO 275) */
  records?: number;
  /** 화면에서 이름 칸을 고쳤으면 옛 이름 — 서버가 계정 · PC 주소를 물려준다 (TODO 275) */
  former?: string;
}

/** 지금 누구인가 (TODO 233) — `/api/me` */
export interface Me {
  /** owner = 관리자(서버 PC) · leader = 팀장(명부의 팀장 IP, TODO 247) · member = 팀원 · viewer = 읽기 */
  role: "owner" | "leader" | "member" | "viewer";
  name: string;
  /** 팀원이면 담당인 과제 번호 — 그 과제에서만 [수정] 이 선다 */
  projects: string[];
  /** 팀장 · 팀원 PC 의 주소 — 머리의 "팀장 · 10.x.x.x" (TODO 247) */
  ip?: string;
  /** 공유를 켰나 — 켰을 때만 서버 PC 머리에 "관리자" 를 보인다 */
  share?: boolean;
}

/** 오늘 바깥에서 접속한 주소 (TODO 233) — 설정 → 명부 */
export interface Visitor {
  ip: string;
  last_at: string;
  requests: number;
  /** 등록한 IP 면 그 사람, 아니면 빈칸 */
  name: string;
}

/** 팀원이 고친 것 한 줄 (TODO 233 ⑥) — 같은 날 같은 사람 · 과제 · 무엇은 묶어 횟수로 */
export interface EditItem {
  at: string;
  name: string;
  action: string;
  project_id: string | null;
  project_title: string | null;
  entry_id: number | null;
  count: number;
  /** 팀장이 노트북 IP 로 고친 것 (TODO 235 ②) */
  leader?: boolean;
}

export interface AppSettings {
  /** 설정의 작성자 칸 — 명부에서 팀장을 고르면 쓰지 않는다 (TODO 235) */
  author: string;
  /** 명부의 팀장 (TODO 235). 있으면 서버 PC 에서 쓴 기록의 작성자는 이 이름 */
  leader?: string;
  /** 설정 파일에서 읽지 못해 기본값을 쓰는 열쇠 — "*" 는 파일 전체 (TODO 163, 읽을 때만 온다) */
  unreadable?: string[];
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
  /** 자동 백업 폴더. 비면 꺼진 것이다. */
  backup_dir: string;
  backup_keep: number;
  /** 주 단위로 남길 벌 수 (TODO 119) */
  backup_keep_weekly: number;
  /** 월 단위로 남길 벌 수 (TODO 119) */
  backup_keep_monthly: number;
  backup_every_hours: number;
  /** AI 요약 프롬프트의 앞뒤에 붙일 글 (TODO 71). 도구가 AI 를 부르지는 않는다. */
  ai_prompt_prefix: string;
  ai_prompt_suffix: string;
  /** 과제 분류 넷의 목록. null 이면 기본 목록을 쓴다 (TODO 136) */
  classifications: Record<string, string[]> | null;
  /** 접수 본문 서식. 비우면 기본 서식 */
  intake_template: string;
  /** 묵힘 기준일 */
  intake_stale_days: number;
  /** 사전점검 항목 — null 이면 기본 목록. 저장할 때는 설정 칸의 글(한 줄에 하나)로도 보낸다 (TODO 155) */
  precheck_items: PrecheckItemDef[] | string | null;
  precheck_thresholds: [number, number];
  /** 팀원 면담 구분 — null 이면 기본 목록. 저장할 때는 한 줄에 하나인 글로도 (TODO 182) */
  meeting_kinds: string[] | string | null;
  meeting_cycle_days: number;
  /** 역량 사전 (TODO 260) — null 이면 기본(46개). 빈 목록을 보내면 기본으로 */
  skill_dictionary?: SkillEntry[] | null;
  /** 보유 기술 사전 (TODO 273) — 빈 목록이면 기본 */
  tool_dictionary?: ToolEntry[] | null;
  /** 업무 이력 파일 익명화 치환표 (TODO 262) */
  anonymize_rules?: { rules: AnonymizeRule[]; patterns?: { kind: string; regex: string; to: string }[] } | null;
  /** 자동 백업에서 첨부를 빼고 문서만 (TODO 202 · 197 ③) — 서버가 아직 모르면 없다 */
  backup_skip_assets?: boolean;
  /** 이전 버전을 남기지 못한 문서 (TODO 206 ㉕) — 읽을 때만 온다 */
  version_keep_failures?: VersionKeepFailure[];
}

/** 이전 버전 보관에 실패한 문서 하나 (TODO 206 ㉕) */
export interface VersionKeepFailure {
  path: string;
  reason: string;
  at?: string;
}

/** `/api/health` — 설정 › 점검 (TODO 204 · 206). 새 칸은 서버가 아직 안 줄 수도 있어 모두 선택 */
export interface Health {
  status: string;
  vault?: string;
  /** 첨부 전체 용량 · 개수 (TODO 204 · 197 ③) */
  attachments_total_bytes?: number;
  attachments_count?: number;
  version_keep_failures?: VersionKeepFailure[];
  /** 큰 작업 파일(백업 · 되살리기) 자리 · 그 드라이브의 남은 자리 (TODO 267) */
  workspace?: { work_dir: string; free_bytes: number | null };
}

/** 전체 백업 작업 (TODO 266) */
export interface BackupJob {
  id: string;
  assets: boolean;
  state: "running" | "done" | "error" | "cancelled";
  files_done: number;
  files_total: number;
  bytes_done: number;
  bytes_total: number;
  elapsed: number;
  eta: number | null;
  error: string;
  filename: string;
  size: number;
}
/** 되살리기 작업 (TODO 268) — 단계별 진행 */
export type RestoreStage = "check" | "safety" | "extract" | "swap" | "index";
export interface RestoreJob {
  id: string;
  state: "running" | "done" | "error" | "cancelled";
  stage: RestoreStage;
  stages: RestoreStage[];
  stages_done: RestoreStage[];
  cancellable: boolean;
  files_done: number;
  files_total: number;
  bytes_done: number;
  bytes_total: number;
  elapsed: number;
  eta: number | null;
  error: string;
  result: RestoreResult | null;
}
/** 지금 도는 오래 걸리는 일 (TODO 268 — /api/running) */
export interface RunningTask {
  id: string;
  label: string;
  key: string;
  phase: string;
  state: "running" | "done" | "error";
  done: number;
  total: number;
  bytes_done: number;
  bytes_total: number;
  elapsed: number;
  eta: number | null;
}
export interface BackupEstimate {
  files: number;
  bytes: number;
  docs_bytes: number;
  assets_bytes: number;
  free_bytes: number | null;
  work_dir: string;
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
  /** 함께 옮긴 첨부의 이름 (TODO 218) — 기록을 지울 때 그 기록에만 쓰인 첨부. 되돌리면 함께 돌아온다 */
  attachments?: string[];
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
  /** 지금 보고 있는 연도 (없으면 전체) */
  year: string | null;
  /** 그 연도 밖인데 아직 끝나지 않은 과제 수 — 걸러 두면 숨는다 */
  other_year_active: number;
  /** 오늘이 선정일·보고일일 때만 채워진다. 매일 뜨면 곧 안 보게 된다. */
  reminder: ReportReminder | null;
  /** 화면에 세우는 상위 몇 건. 개수를 말할 때 이것을 세면 안 된다 */
  candidates: ReportCandidate[];
  /** 자르기 전 **전체** 후보 수 (TODO 82). "N건 보기"는 이 수를 쓴다 */
  candidate_total: number;
}

/** 아직 확정되지 않은 보고 한 건. 배너와 보고 대상 화면이 여기로 곧장 간다 (TODO 91). */
export interface OpenDraft {
  id: number;
  project_id: string;
  project_title: string;
  audience: string | null;
  /** 보고 대상의 확정 대기 카드는 모든 날짜의 초안을 세우므로 날짜가 함께 온다 (TODO 103-A) */
  report_date?: string;
  overdue_days?: number;
}

/** 보고 주기 알림 (T12). */
export interface ReportReminder {
  /** select = 오늘 고르는 날, report = 오늘 보고하는 날 */
  phase: "select" | "report";
  report_date: string;
  /** 그 날짜로 만들어 둔 초안 수 */
  drafts: number;
  /** 그 초안들이 무엇인지. 개수만으로는 갈 곳을 만들 수 없다 (최대 10건) */
  draft_items: OpenDraft[];
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
  /** 지시가 적혀 있고 아직 답하지 않았다 (TODO 107) */
  feedback_open?: boolean;
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
/** 깨진 첨부 링크 정리 결과 (TODO 116). applied=false 면 세기만 한 것이다. */
export interface LinkFixReport {
  applied: boolean;
  documents: {
    project_id: string;
    project_title: string;
    kind: "overview" | "entry" | "report";
    rel_path: string;
    links: number;
    frozen: boolean;
  }[];
  document_count: number;
  link_count: number;
  /** 확정된 보고라 건너뛴 문서 수 — 포함하겠다고 하면 0 이 된다 */
  skipped_frozen: number;
}

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

/** 한 문서의 이전 버전 한 벌 (TODO 37-1). */
export interface DocumentVersion {
  /** 파일 이름이자 시각 키 (2026-09-03_142205) */
  stamp: string;
  /** 사람이 읽는 시각 */
  saved_at: string;
  size_bytes: number;
  /** 그 다음 저장이 본문을 바꿨는가 — 아니면 정보(과제명·상태 …)만 바뀐 저장이다 (TODO 152) */
  body_changed?: boolean;
}

/** 자동 백업 현황 (T21). */
export interface BackupStatus {
  directory: string;
  enabled: boolean;
  /** 폴더에 실제로 닿는가 (네트워크 드라이브가 끊겼을 수 있다) */
  reachable: boolean;
  /** 층을 합쳐 남기는 수 (TODO 119) */
  keep: number;
  keep_daily: number;
  keep_weekly: number;
  keep_monthly: number;
  every_hours: number;
  count: number;
  /** 폴더 전체 용량. 화면에 세우는 몇 개가 아니라 전부를 더한 값이다 */
  total_bytes: number;
  /** 가장 오래된 백업의 날짜 — 되돌릴 수 있는 범위 */
  oldest: string | null;
  recent: { name: string; size_bytes: number; at: string }[];
  last: { at: string; ok: boolean; file?: string; error?: string } | null;
}

/** 홈(첫 화면) 집계 (TODO 56). 연도 기준이 둘이라는 점은 home.py 주석 참고. */
export interface HomeTeam {
  total: number;
  done: number;
  in_progress: number;
  /** 확정된 보고의 수. 연도는 **보고일** 기준이다. */
  reports: number;
  /** 억원/년. 기대와 실증을 절대 합치지 않는다 — 합치면 확정 여부를 알 수 없다. */
  effect_expected: number;
  effect_verified: number;
  /** 그 금액이 **몇 건에서 나왔는지**. 없으면 화살표가 달성률로 읽힌다 (TODO 86) */
  /** 효과 금액으로 관리하는 과제 수 — total 과 같으면 비대상이 없다 (TODO 125) */
  effect_managed?: number;
  effect_expected_projects?: number;
  effect_verified_projects?: number;
  /** 실증 합계 가운데 진행중 과제의 중간 결산 — 금액 · 건수 (TODO 217) */
  effect_verified_interim?: number;
  effect_verified_interim_projects?: number;
  /** 완료일 기준으로 센 완료 수 (TODO 104). done 은 번호의 연도 기준이라 둘이 다르다. */
  done_in_year?: number;
  /** 그 해에 새로 착수한 과제 — 번호의 연도 (TODO 181) */
  new?: number;
  /** 완료했는데 실증효과를 안 적은 과제 수 (TODO 106-C) */
  done_unverified?: number;
}

export interface HomeMember extends HomeTeam {
  name: string;
  /** 그 해 역량 이력 건수. 0 이면 그 자체가 면담 이야깃거리다 (TODO 89) */
  activities: number;
  /** 상태 여섯 칸 (예정·검토중·진행중·보류·완료·중단). 합은 total 과 같다. */
  by_status: Record<string, number>;
  /** 연도와 무관한 실제 마지막 보고일 */
  last_reported_at: string | null;
}

/** 속성별·그룹별 표의 한 줄. 두 표는 **같은 모양**이다 (TODO 90). */
export interface HomeSlice {
  key: string;
  label: string;
  count: number;
  /** 팀원별과 **같은 모양**이다. 한 화면에서 같은 것을 다르게 세지 않는다. */
  by_status: Record<string, number>;
  done: number;
  effect_expected: number;
  effect_verified: number;
}

/** 성격별·분류별 표의 한 줄 (TODO 136). 목록으로 이어 줄 거르기 조건을 서버가 함께 준다 —
 * *미지정* 줄은 "스마트과제인데 비어 있는 것" 이라 조건이 둘이다. 세는 곳과 거르는 곳이 같아야 한다. */
export interface HomeClassSlice extends HomeSlice {
  listed: boolean;
  filter: Record<string, string>;
}

/** 과제 × 월 표의 재료 (TODO 77). 열두 칸으로 나누는 일은 화면이 한다. */
export interface MonthGrid {
  /** 줄 = (그 해 번호의 과제) ∪ (그 해에 보고가 있었던 과제). 보고 불필요 과제는 빠진다 */
  projects: { id: string; title: string; status: string }[];
  reports: { id: number; project_id: string; date: string; audience: string | null }[];
  /** 보고 불필요로 표시해 뺀 과제 수 — 몇 건이 빠졌는지 화면이 밝힌다 */
  skipped: number;
}

export interface Home {
  year: string | null;
  years: string[];
  today: string;
  /** 반기·분기 (TODO 110). 연도 전체면 null. 날짜가 있는 숫자만 이것을 따른다 */
  period: string | null;
  this_week: {
    report_date: string;
    candidates: number;
    due_soon: number;
    overdue: number;
    stale: ReportCandidate[];
    /** 오래 방치된 과제의 **자르기 전** 수 — 위 목록은 앞의 몇 건이다 (TODO 103-B) */
    stale_total: number;
    /** 아직 확정하지 않은 보고 수 — 날짜를 가리지 않는다 (TODO 101) */
    drafts: number;
    /** 그중 **보고일이 이미 지난** 것 — 진짜 밀린 것이다 */
    drafts_overdue: number;
    /** 앞의 몇 건. 건수를 말할 때 이 길이를 세면 안 된다 */
    draft_items: UnfinishedDraft[];
    /** 과제별 다음 할 일 — 최근 진행일지의 계획 칸 (TODO 112). 앞의 몇 건 */
    plans: HomePlan[];
    plans_total: number;
    /** 떠난 담당자가 남아 있는 끝나지 않은 과제 (TODO 122). 건수는 **과제 수** 다 */
    owner_gaps: OwnerGap[];
    owner_gaps_total: number;
    /** 앞으로 days 일 안의 팀원 역량 예정 · 그 뒤 건수 (TODO 221) */
    team_upcoming?: { days: number; items: ActivityBrief[]; later: number };
    /** 예정으로 적었는데 날짜가 지나고 손대지 않은 것 — 2주 동안 (TODO 221) */
    team_missed?: ActivityBrief[];
  };
  team: HomeTeam;
  /** 최근 몇 해를 나란히. 왼쪽이 과거다. */
  /** 과제가 있는 모든 해 — 지난해 · 올해 · 미래 (TODO 228). 왼쪽이 과거다 */
  compare: (HomeTeam & { year: string; when?: "past" | "current" | "future" })[];
  /** 담당 중복 포함 — 합이 team 보다 클 수 있다 */
  members: HomeMember[];
  types: HomeSlice[];
  /** 그룹(주제)별. 속성별과 같은 모양이고, 자유 입력이라 수가 늘 수 있다 (TODO 90) */
  groups: HomeSlice[];
  /** 성격별 · 분류별 (TODO 136) */
  natures: HomeClassSlice[];
  /** 스마트과제가 아닌데 성격 · 분류가 적힌 과제 수 (TODO 229) */
  classified_outside?: { nature: number; category: number };
  categories: HomeClassSlice[];
  /** 기대효과를 비용구분으로 나눈 것 — 적힌 과제만 (TODO 136) */
  effect_by_cost: { key: string; count: number; effect_expected: number; effect_verified: number }[];
  /** 접수 풀 요약 — 과제 집계와 섞지 않는다 (TODO 136) */
  intakes: IntakeSummary;
}

// ── 과제 접수 풀 (TODO 136) ────────────────────────────────────────────────

export interface IntakeSummary {
  /** 풀에 담긴 수 — 접수 · 검토중 · 보류 */
  pool: number;
  counts: Record<string, number>;
  /** 접수 후 stale_days 가 지나도 판정이 없는 것 (보류는 세지 않는다) */
  stale: number;
  stale_days: number;
  year: string;
  /** 그 해에 판정이 난 수 — 착수 · 반려 · 이관 · 병합 */
  decided: Record<string, number>;
  received_this_year: number;
}

export interface Intake {
  id: string;
  dir_name: string;
  title: string;
  status: string;
  status_label: string;
  in_pool: boolean;
  leader: string | null;
  leader_team: string | null;
  nature: string | null;
  category: string | null;
  delivery: string | null;
  cost_kind: string | null;
  start_date: string | null;
  due_date: string | null;
  /** 요청자가 적은 기대효과 — **과제로 옮기지 않는다** (참고용) */
  effect_request: number | null;
  priority: string | null;
  priority_note: string | null;
  /** 풀에서 골라 둔 착수 후보 */
  picked: boolean;
  received_on: string | null;
  decided_on: string | null;
  decision_note: string | null;
  project_id: string | null;
  merged_into: string | null;
  tags: string[];
  created_by: string | null;
  created_at: string | null;
  updated_at: string | null;
  log_count: number;
  attachment_count: number;
  last_log_date: string | null;
  age_days: number | null;
  stale: boolean;
  /** 사전점검 — 점수는 다 매겼을 때만 (TODO 155) */
  precheck_score: number | null;
  precheck_rated: number | null;
  precheck_total: number | null;
  precheck_band: PrecheckBand | null;
  /** 사전점검을 지금과 다른 기준으로 매겼나 (TODO 276 ⑤ — 목록에서만) */
  precheck_stale?: boolean;
}

export interface IntakeLog {
  name: string;
  date: string;
  title: string;
  author: string | null;
  tags: string[];
  body: string;
  mtime?: number;
  broken: boolean;
}

export interface IntakeAttachment {
  rel_path: string;
  orig_name: string;
  mime: string;
  size_bytes: number;
  is_image: boolean;
  url: string;
  /** 요청 본문에 넣을 링크 / 검토 기록에 넣을 링크 — 기준 폴더가 다르다 */
  markdown: string;
  markdown_log: string;
  /** 엑셀이면 [내용 보기] 주소 (TODO 138) */
  preview_url?: string | null;
}

export interface IntakeDetail extends Intake {
  /** 직접 만든 과제를 되돌린 접수면 그 과제 번호 (TODO 171) */
  demoted_from?: string | null;
  body: string;
  file_mtime: number;
  logs: IntakeLog[];
  attachments: IntakeAttachment[];
  linked_project: { id: string; title?: string; status?: string; missing?: boolean } | null;
  precheck: PrecheckSummary;
}

export interface IntakeListing {
  items: Intake[];
  summary: IntakeSummary;
  /** 접수에 적혀 있는데 설정 목록에 없는 옛 분류 값 (TODO 275) */
  unlisted?: Record<string, string[]>;
  teams: string[];
  years: string[];
}

export interface IntakeLink {
  id: string;
  title: string;
  status: string;
  status_label: string;
  /** started = 이 과제로 승격 · merged = 이 과제에 병합 */
  relation: "started" | "merged";
  received_on: string | null;
  precheck_score?: number | null;
}

export interface PromotionPlan {
  title: string;
  type: string;
  status: string;
  owners: string[];
  partners: Partner[];
  leader: string;
  leader_team: string;
  /** 과제리더가 명부에 있는가 — 있으면 담당자로, 없으면 유관부서로 간다 */
  leader_in_roster: boolean;
  start_date: string | null;
  due_date: string | null;
  effect_request: number | null;
  nature: string | null;
  category: string | null;
  delivery: string | null;
  cost_kind: string | null;
  tags: string[];
  body_preview: string;
  matched_sections: string[];
  leftover_sections: string[];
  attachments: string[];
  next_project_id: string;
}

/** 대체 담당자를 정해야 하는 과제 한 줄 (TODO 122). */
export interface OwnerGap {
  id: string;
  title: string;
  status: string;
  owner: string;
  left_reason: string;
  left_on: string;
}

/** 홈에 서는 과제별 다음 할 일 (TODO 112). */
export interface HomePlan extends NextPlan {
  project_id: string;
  project_title: string;
}

/** 팀원 역량 이력 한 건 (TODO 72). 기록 단위는 **사람**이다. */
export interface Activity {
  id: number;
  /** 같은 행사를 가리키는 열쇠 — 날짜·구분·제목이 같으면 한 행사다 (TODO 85) */
  event_key: string;
  person: string;
  /** 시작일. 연도 집계도 이 날짜를 본다 */
  date: string;
  /** 여러 날에 걸친 교육의 종료일. 하루짜리면 비어 있다 */
  end_date: string | null;
  kind: string;
  title: string;
  host: string | null;
  place: string | null;
  /** 시간·비용은 옵션이다. 비어 있는 것이 정상이다. */
  hours: number | null;
  cost: number | null;
  /** 면담에서 실제로 읽게 되는 한 줄 */
  takeaway: string | null;
  /** 수료증·자료가 있는 사내 공유 폴더 주소 등 */
  link: string | null;
  body: string | null;
  author: string | null;
  updated_at: string | null;
  /** 예정 — 시작일이 오늘보다 뒤 (TODO 221). 그날이 지나면 저절로 이력이 된다 */
  planned?: boolean;
}

/** 홈의 다가오는 팀원 일정 · 지난 예정 확인 한 줄 (TODO 221) */
export interface ActivityBrief {
  id: number;
  person: string;
  date: string;
  end_date: string | null;
  kind: string;
  title: string;
  place: string | null;
  /** 시작까지 남은 날 — 오늘이면 0 (TODO 226). 다가오는 일정에만 */
  days_left?: number;
  /** 이미 시작해 아직 끝나지 않은 여러 날 일정 (TODO 226 ③) */
  ongoing?: boolean;
}

export interface ActivityPerson {
  name: string;
  /** 지나간 것만 — 예정은 planned 에 따로 (TODO 221) */
  count: number;
  planned?: number;
  hours: number;
  cost: number;
  /** 시간·비용을 실제로 채운 건수 — 합계가 몇 건에서 나온 값인지 밝힌다 */
  with_hours: number;
  with_cost: number;
  by_kind: Record<string, number>;
  /** 최근 몇 해의 건수. 한 해만 보면 늘고 주는 것을 알 수 없다 */
  trend: Record<string, number>;
  last_date: string | null;
  days_since: number | null;
  /** 그 해 기록이 없거나 오래 뜸한 사람 — 면담에서 먼저 꺼낼 줄 */
  quiet: boolean;
  /** 명부에서 떠난 사람 (TODO 122 · 194) — 줄은 남고 면담 대상에서는 빠진다 */
  left?: boolean;
  /** 명부의 팀장 (TODO 235) — 면담 대상에서 빠진다(면담 칸은 비어 온다) */
  leader?: boolean;
  left_on?: string | null;
  left_reason?: string;
  /** 면담 (TODO 182) — 역량 이력과 따로 센다 */
  meetings: number;
  last_meeting: string | null;
  meeting_days_since: number | null;
  open_followups: number;
  next_meeting: string | null;
  /** 정한 다음 면담일이 지났거나, 마지막 면담에서 주기가 지났다 */
  meeting_due: boolean;
}

export interface ActivitySummary {
  year: string | null;
  years: string[];
  trend_years: string[];
  quiet_days: number;
  meeting_cycle_days: number;
  /** count 는 **참여 연인원**, events 는 **행사 수**다. 둘은 다르다 (TODO 85) */
  team: { count: number; events: number; hours: number; cost: number; people: number; planned?: number };
  people: ActivityPerson[];
}

/**
 * 과제 번호의 연도를 착수년도에 맞추기 (TODO 95).
 *
 * 옮길 것이 없으면 `new_id` 가 null 이고 `reason` 이 왜 그런지 말한다
 * ("이미 맞습니다." · "시작일이 비어 있습니다." · "번호 형태가 아니라 옮길 수 없습니다.").
 */
export interface YearFix {
  id: string;
  title?: string;
  new_id: string | null;
  dir_name?: string;
  new_dir_name?: string;
  start_date?: string;
  from_year?: string;
  to_year?: string;
  /** 옮겨 갈 해에 그 번호가 이미 있어서 일련번호까지 밀린 경우 */
  renumbered?: boolean;
  reason: string | null;
  done?: boolean;
}

/** 폴더 하나 (TODO 97). */
export interface FolderEntry {
  name: string;
  path: string;
}

/**
 * 그 자리에서 보이는 폴더들 (TODO 97).
 *
 * `path` 가 비면 처음 자리(드라이브·내 폴더)다. `parent` 가 빈 문자열이면 한 단계 위가
 * 처음 자리라는 뜻이고, null 이면 이미 처음 자리다.
 */
export interface FolderListing {
  path: string;
  parent: string | null;
  /** 그 폴더에 쓸 수 있나 — 백업 폴더는 쓸 수 있어야 뜻이 있다 */
  writable: boolean;
  folders: FolderEntry[];
  /** 폴더가 너무 많아 앞의 것만 실었다 */
  truncated: boolean;
}

/** 설정에서 다루는 과제 속성 한 줄 (TODO 100). */
export interface ProjectTypeRow {
  /** 과제 파일에 남는 값. 새 줄은 비어 있고 저장할 때 서버가 이름에서 짓는다. */
  key: string;
  /** 화면에 보이는 이름. 고쳐도 과제가 속성을 잃지 않는다. */
  label: string;
  /** 이 속성을 쓰는 과제 수 — 0건일 때만 뺄 수 있다. */
  count: number;
}

/** 쓰다 만 보고 한 건 (TODO 101). 홈이 그 편집기로 곧장 데려간다. */
export interface UnfinishedDraft {
  id: number;
  project_id: string;
  project_title: string;
  audience: string | null;
  report_date: string;
  /** 보고일이 지났으면 며칠이나 지났는지. 아직 안 지났으면 0 */
  overdue_days: number;
}


/** 다년도 과제의 줄기 (TODO 172) — 앞 단계들(오래된 것부터) · 바로 다음 단계 · 이 과제의 단계 번호 */
export interface LineageItem {
  id: string;
  title: string | null;
  status: string | null;
  start_date?: string | null;
  /** 기간의 끝 — 끝난 과제는 끝낸 날, 아니면 마감일 (TODO 176) */
  end_date?: string | null;
  /** 보관함에 있거나 찾을 수 없는 과제 */
  missing?: boolean;
  /** 지금 보고 있는 과제 */
  here?: boolean;
}
export interface Lineage {
  /** 이 과제의 단계 — 이어진 과제가 없으면(단년도) null */
  stage: number | null;
  /** 이어진 과제 전부를 단계별로 — 한 단계에 여럿일 수 있다 */
  stages: { stage: number; items: LineageItem[] }[];
  predecessors: string[];
  successors: string[];
}

/** 과제 → 접수로 되돌리기 미리보기 (TODO 171) */
export interface DemotePlan {
  project_id: string;
  title: string;
  eligible: boolean;
  reason: string | null;
  entries: number;
  attachments: number;
  reports: number;
  successors: number;
  received_on: string;
  next_intake_id: string;
}

/** 로드맵 (TODO 174) — 선행으로 이어진 줄기 하나의 과제 한 줄 */
export interface RoadmapProject {
  id: string;
  title: string | null;
  status: string | null;
  type?: string | null;
  group?: string | null;
  owners?: string[];
  start_date?: string | null;
  due_date?: string | null;
  completed_at?: string | null;
  /** 막대의 끝 — 끝난 과제는 끝낸 날, 아니면 마감일 */
  end_date?: string | null;
  effect_expected?: number | null;
  effect_verified?: number | null;
  stage: number;
  predecessors: string[];
  successors: string[];
  /** 보관함에 있거나 찾을 수 없는 선행 */
  missing: boolean;
}

export interface RoadmapWarning {
  project_id: string;
  kind: "overdue" | "pred_dropped" | "missing" | "pred_open" | "no_dates" | "next_open";
  level: "warn" | "info";
  text: string;
}

export interface RoadmapLineage {
  key: string;
  title: string;
  state: "active" | "planned" | "ended";
  stage_count: number;
  current_stage: number | null;
  start_date: string | null;
  end_date: string | null;
  effect_expected: number;
  effect_verified: number;
  projects: RoadmapProject[];
  warnings: RoadmapWarning[];
}

export interface Roadmap {
  today: string;
  lineages: RoadmapLineage[];
  summary: { lineages: number; projects: number; active: number; warn: number; next_open: number };
}

/** 팀원 면담 (TODO 182) — 하기로 한 것 하나 */
export interface MeetingFollowup {
  text: string;
  /** 끝낸 날 — 비어 있으면 아직 열려 있다 */
  done: string | null;
}

export interface Meeting {
  id: number;
  person: string;
  date: string;
  kind: string | null;
  summary: string;
  followups: MeetingFollowup[];
  open_followups: number;
  next_date: string | null;
  body: string | null;
  author: string | null;
  updated_at: string | null;
}

export interface MeetingListing {
  items: Meeting[];
  open_followups: { meeting_id: number; index: number; person: string; date: string; text: string }[];
}

// ── TODO 214 — 서버가 새로 주는 칸 (아직 안 올 수도 있다, 인터페이스 합치기) ─────────────
export interface Meta {
  /** 효과 금액 확인 기준선 (D4, 억원/년). 0 이면 묻지 않는다 · 없으면 100 */
  effect_confirm_over?: number | null;
}
export interface Entry {
  /** 저장은 했지만 알릴 것 — 과제 기간 밖 날짜 등 (D5) */
  warnings?: string[];
}

// ── TODO 214 · 216 사람 · 면담 · 설정 (화면 2) — 서버가 새로 주는 칸, 아직 안 올 수도 있다 ─────────────
export interface AppSettings {
  /** 효과 금액 확인 기준선 (D4, 억원/년). 0 이면 묻지 않는다 · 없으면 100 */
  effect_confirm_over?: number | null;
}

/** [다른 이름으로 통일] · [넘기기] 의 결과 (TODO 214 D9) — 과제 말고도 유관부서 · 역량 · 면담 · 접수 과제리더의 수 */
export interface PeopleChangeResult {
  count: number;
  changed: string[];
  /** 종류별 바꾼 수 — 모양은 서버를 따른다(없을 수도 있다) */
  counts?: Record<string, unknown>;
  [key: string]: unknown;
}

/** 입력 확인으로 돌려보낸 요청 한 건 (TODO 216) — 고장이 아니라 "최근 오류" 에 세우지 않는다 */
export interface InputRejection {
  at: string;
  action: string;
  detail: string | null;
}

/** `/api/errors` — 고장(items)과 입력 확인(inputs)을 따로 (TODO 216) */
export interface ErrorListing {
  items: ErrorEntry[];
  keep_months: number;
  input_count?: number;
  input_today?: number;
  inputs?: InputRejection[];
}

// TODO 214 D2 · 217 — 목록 줄이 실어 오는 "세는 금액"(효과 관리 안 함은 0, 진행중 과제의 중간 결산은 센다). 합계 줄이 홈과 같은 수를 더하게
export interface Project {
  effect_counted_expected?: number | null;
  effect_counted_verified?: number | null;
}

// ── TODO 237 — 담당과 역할 · 금액 아닌 성과 ─────────────────────────────────────
/** 한 사람의 역할 · 맡은 부분 · 담당 기간 · 회고(내가 한 일 · 결과). 팀원이 나중에 업무 이력 · 성과를 정리할 재료 */
export interface Contribution {
  name: string;
  /** 주관 · 참여 · 지원, 비어 있을 수 있다 */
  role: string;
  part: string;
  from: string | null;
  to: string | null;
  did: string;
  result: string;
  /** 기술 · 도구 (TODO 239) */
  skills: string[];
  /** 기록이 없어 시작일부터로 읽은 줄 */
  derived: boolean;
  /** 지금 담당인가 — 아니면 예전 담당 */
  current: boolean;
}
export interface Project {
  /** 금액 아닌 성과 한 줄 — "작업 시간 40% 단축" */
  outcome?: string | null;
  /** 상세 조회에서만 */
  contributions?: Contribution[];
  /** 팀 안에서 쓴 기술 · 도구 — 많이 쓴 것부터 (상세 조회에서만, TODO 239) */
  known_skills?: string[];
}
export interface RetroDue {
  name: string;
  items: { id: string; title: string; completed_at: string }[];
}

// ── TODO 238 — 사람별 이력 ───────────────────────────────────────────────────
export interface PersonProject {
  id: string;
  title: string;
  status: string;
  /** 맡기 시작한 해 */
  year: string;
  from: string | null;
  /** 담당 끝 · 과제 완료일 — 없으면 아직(화면이 "지금") */
  to: string | null;
  current: boolean;
  derived: boolean;
  role: string;
  part: string;
  did: string;
  result: string;
  skills: string[];
  outcome: string;
  effect_expected: number | null;
  effect_verified: number | null;
  no_effect: boolean;
}
export interface PersonActivity {
  id: number;
  date: string;
  end_date: string | null;
  kind: string;
  title: string;
  host: string | null;
  hours: number | null;
  takeaway: string;
  planned: boolean;
}
export interface PersonHistory {
  name: string;
  in_roster: boolean;
  leader: boolean;
  left_on: string | null;
  summary: {
    projects: number; current: number; lead: number; done: number; retro_written: number; activities: number; entry_only: number;
    /** 확정한 보고에 올라간 내 과제 — 올해 · 지난해 (TODO 242 A1) */
    reports_this_year?: number; reports_last_year?: number; year?: string;
  };
  /** 많이 쓴 기술 · 도구 — 과제 수 (TODO 239) */
  skills: { name: string; count: number }[];
  projects: PersonProject[];
  activities: PersonActivity[];
}

// ── TODO 242 — 팀원의 내 할 일 · 인정 한 줄 · 보고 횟수 ──────────────────────────
export interface Contribution {
  /** 팀장의 인정 한 줄 — 그 사람과 팀장에게만 온다(다른 사람에게는 빈 글) */
  praise?: string;
  praise_at?: string | null;
  /** 중간 성과 — 날짜 + 한 줄, 날짜 순 (TODO 243) */
  milestones?: Milestone[];
}
export interface Milestone {
  date: string;
  text: string;
}
/** 성과 후보 일지 — `★성과` 태그가 붙은 진행일지 (TODO 243) */
export interface StarEntry {
  id: number;
  date: string;
  title: string;
  author: string;
  first_line: string;
}
export interface Project {
  /** 상세 조회에서만 — 성과 후보 일지 */
  star_entries?: StarEntry[];
}
export interface PersonProject {
  milestones?: Milestone[];
  star_entries?: StarEntry[];
  praise?: string;
  praise_at?: string | null;
  /** 확정한 보고에 올라간 횟수 */
  reports?: number;
}
export interface MyWorkProject {
  id: string;
  title: string;
  status: string;
  role: string;
  due_date: string | null;
  days_left: number | null;
  last_entry: string | null;
  days_since_entry: number | null;
  /** 진행중 · 검토중인데 마지막 일지가 stale_days 를 넘었다 */
  stale: boolean;
}
export interface MyWork {
  name: string;
  projects: MyWorkProject[];
  retro_due: { id: string; title: string; completed_at: string }[];
  praises: { project_id: string; title: string; praise: string; praise_at: string | null; new: boolean }[];
  stale_days: number;
}

// ── TODO 244 — 나의 한 해 · 마친 과제 · STAR 의 상황 · 과제 ─────────────────────────
export interface YearNumbers {
  projects: number;
  done: number;
  lead: number;
  entries: number;
  reports: number;
  milestones: number;
  activities: number;
  hours: number;
}
export interface YearReview extends YearNumbers {
  name: string;
  year: string;
  last: YearNumbers;
  new_skills: string[];
  outcomes: { id: string; title: string; outcome: string }[];
  done_projects: { id: string; title: string; completed_at: string | null }[];
}
export interface DoneSummary {
  start: string | null;
  end: string | null;
  months: number | null;
  entries: number;
  reports: number;
  people: number;
  milestones: number;
  outcome: string;
  effect_verified: number | null;
}
export interface Project {
  done_summary?: DoneSummary | null;
}
export interface PersonProject {
  /** 과제 개요의 배경 · 목표 — STAR 의 상황 · 과제 */
  context?: { background: string; goal: string };
}
export interface MyWork {
  recent_done?: { id: string; title: string; completed_at: string }[];
}

/** 전체 백업 ZIP 살펴보기 (TODO 246) */
export interface RestoreCounts {
  projects: number;
  people: number;
  intakes: number;
  assets: number;
}
export interface RestoreReport extends RestoreCounts {
  token: string | null;
  filename: string;
  date: string | null;
  files: number;
  bytes: number;
  zip_bytes: number;
  settings: boolean;
  with_assets: boolean;
  wrapped: string | null;
  ok: boolean;
  problems: string[];
  current: RestoreCounts & { has_data: boolean };
}
export interface RestoreResult {
  projects: number;
  people: number;
  intakes: number;
  files: number;
  problems: { path: string; reason: string }[];
  safety_backup: string | null;
  backup_dir_missing: string | null;
}

// ── 팀원별 경험 (TODO 257 · 253 의 2단계) ─────────────────────────────────────
export interface ExperienceQuant {
  metric: string;
  value: string;
  baseline: string;
  baseline_kind: "비교" | "집계" | "조건" | "미확인";
  when: string;
}
export interface ExperienceSkill {
  axis: "기술" | "업무" | "리더십" | "문제해결";
  name: string;
}
export interface ExperienceEvidence {
  type: string;
  text: string;
  year?: string;
  file?: string;
}
export interface ExperienceProblem {
  code: string;
  field: string;
  message: string;
  level: "오류" | "경고";
}
export interface ExperienceSummary {
  id: string;
  person: string;
  title: string;
  project: string;
  project_title: string;
  project_gone: boolean;
  start: string;
  end: string;
  status: "초안" | "구조화" | "확정";
  open_count: number;
  warn_count: number;
  source: string;
  updated_at: string;
}
export interface ExperienceListing {
  person: string;
  items: ExperienceSummary[];
  counts: Record<string, number>;
  total: number;
  /** 사람별 역량 칩 (TODO 260) */
  skills: { axis: ExperienceSkill["axis"]; name: string; count: number; known: boolean }[];
  /** 보유 기술 요약 (TODO 273) — 과제(담당과 역할)와 경험을 합쳐. last = 마지막으로 쓴 해 */
  tools: { name: string; projects: number; experiences: number; last: string; known: boolean }[];
}
/** 보유 기술 사전 (TODO 273) */
export interface ToolEntry {
  name: string;
  aliases: string[];
}
export interface ToolDictionary {
  dictionary: ToolEntry[];
  usage: Record<string, number>;
  custom: boolean;
  /** 사전에 없는데 과제 · 경험에 쓰인 이름. skill_like = 역량 사전에 있는 이름(보유 기술이 아니라 역량) */
  unlisted: { name: string; count: number; skill_like: boolean }[];
}
/** 정합성 경고 (TODO 260 · 4단계.md 3절) */
export interface ConsistencyWarning {
  code: string;
  key: string;
  label: string;
  message: string;
  acknowledged: boolean;
  ack_at: string;
  ack_by: string;
}
export interface SkillEntry {
  axis: ExperienceSkill["axis"];
  name: string;
  aliases: string[];
}
export interface SkillDictionary {
  dictionary: SkillEntry[];
  usage: Record<string, number>;
  custom: boolean;
}
export interface Experience {
  id: string;
  person: string;
  title: string;
  project: string;
  project_title: string;
  project_gone: boolean;
  project_text: string;
  affiliation: string;
  start: string;
  end: string;
  role: string;
  kind: string;
  status: "초안" | "구조화" | "확정";
  situation: string;
  goal: string;
  actions: string[];
  result_qual: string;
  impact: string;
  lesson: string;
  lesson_source: string;
  open_questions: string[];
  skills: ExperienceSkill[];
  quants: ExperienceQuant[];
  evidences: ExperienceEvidence[];
  related: string[];
  materials: string[];
  source: string;
  created_at: string;
  updated_at: string;
  created_by: string;
  problems: ExperienceProblem[];
  confirm_missing: string[];
  // 4단계 (TODO 260)
  consistency: ConsistencyWarning[];
  skills_unknown: string[];
  /** 확정 전에 알릴 것 (TODO 273) — 보유 기술이 비었거나 글에 나오는데 칸에 없다. 막지 않는다 */
  tool_notes?: string[];
  acknowledged: { code: string; key: string; at: string; by: string }[];
  confirmed_at: string;
  confirmed_by: string;
  // 5단계 (TODO 262)
  tools: string[];
  edited_by_member_at: string;
}
/** 사전에 없는 태그 — 태그 정리함 (TODO 262 · 역량태그입력.md) */
export interface UnknownTag {
  axis: ExperienceSkill["axis"];
  name: string;
  count: number;
  experiences: string[];
  people: string[];
  suggest: { axis: ExperienceSkill["axis"]; name: string }[];
  tool_like: boolean;
  /** 282 C — 그 태그가 붙은 경험(5건까지): 제목 · 사람 · 상태 · 행동 첫 줄 */
  uses?: { id: string; title: string; person: string; status: string; line: string }[];
}
export type TagAction = "alias" | "new" | "tool" | "drop";
export interface TagDecision {
  axis: string;
  name: string;
  action: TagAction;
  target_axis?: string;
  target_name?: string;
}
export interface TagProposal extends Partial<TagDecision> {
  axis: string;
  name: string;
  unsure: boolean;
  raw: string;
  problem: string;
}
export interface ExportOptions {
  scope: "all" | "period" | "pick";
  start?: string;
  end?: string;
  ids?: string[];
  structured?: boolean;
  ids_in?: boolean;
  money?: boolean;
  anonymize?: boolean;
}
export interface ExportResult {
  text: string;
  filename: string;
  chars: number;
  warnings: string[];
  ids: string[];
  summary: {
    experiences: number; confirmed: number; structured: number; period: string; projects: number;
    axes: Record<string, number>; top_skills: string[]; quants: number; quants_compared: number; replaced: Record<string, number>;
  };
}
export interface AnonymizeRule { kind: string; from: string; to: string }
export interface AnonymizeCandidates {
  items: { kind: string; text: string; suggest: string; in_rules: boolean }[];
  rules: AnonymizeRule[];
  patterns: { kind: string; regex: string; to: string }[];
}
export interface ExportLogRow {
  at: string; by: string; role: string; person: string; how: string; count: number; chars: number;
  options: { scope: string; start: string; end: string; structured: boolean; ids_in: boolean; money: boolean; anonymize: boolean };
}

// ── 응답 되받기 (TODO 258 · 253 의 3단계) ───────────────────
export interface ExperiencePromptChoice {
  id: string;
  title: string;
  period: string;
  retro: boolean;
  structured: boolean;
  default: boolean;
  /** 이 과제의 경험(초안 포함)이 있나 — 없으면 "초안 먼저" (TODO 259) */
  has_experience: boolean;
}

export interface ExperiencePrompt {
  person: string;
  text: string;
  chars: number;
  projects: string[];
  existing: number;
  choices: ExperiencePromptChoice[];
}

/** 블록을 경험 칸으로 옮긴 모양 — 미리보기의 [펼치기] · 칸 비교가 쓴다 */
export interface ImportFields {
  title: string;
  start: string;
  end: string;
  role: string;
  kind: string;
  situation: string;
  goal: string;
  actions: string[];
  result_qual: string;
  impact: string;
  lesson: string;
  lesson_source: string;
  open_questions: string[];
  skills: ExperienceSkill[];
  quants: ExperienceQuant[];
  affiliation: string;
  evidences: ExperienceEvidence[];
}

export type ImportAction = "새로" | "이어서" | "버림";

export interface ImportBlock {
  index: number;
  first_line: number;
  fields: ImportFields;
  continues: string;
  continues_known: boolean;
  project: string;
  action: ImportAction;
  target: string;
  /** 기본값의 근거 (TODO 259) — continues · single · title · "" / continues · draft · shared · "" */
  project_reason: string;
  action_reason: string;
  counts: { open: number; quant: number; skill: number; action: number };
  warnings: { code: string; message: string }[];
  bad_lines: { line: number; text: string; reason: string }[];
  unknown: string[];
}

/** 이어 붙일 수 있는 경험 — 칸 비교용 값(기간은 "시작 ~ 끝" 한 칸) */
export interface ImportTarget {
  id: string;
  title: string;
  project: string;
  status: string;
  source: string;
  touched: boolean;
  [field: string]: string | boolean;
}

export interface ImportPreview {
  response: string;
  person: string;
  projects: string[];
  blocks: ImportBlock[];
  notice: string;
  found_fence: boolean;
  duplicates: [number, number][];
  outside_lines: number;
  stripped_markers: number;
  stripped_controls: number;
  chars: number;
  lines: number;
  bad_count: number;
  unknown_count: number;
  targets: ImportTarget[];
  project_choices: { id: string; title: string }[];
}

export interface ImportDecision {
  index: number;
  action: ImportAction;
  target?: string;
  project?: string;
  choose?: Record<string, "old" | "new">;
}

export interface ExperienceResponseFile {
  name: string;
  person: string;
  created_at: string;
  created_by: string;
  projects: string[];
  blocks: number;
  saved: string[];
  text: string;
}

/** 연말 회고 카드 (TODO 285) */
export interface YearCardProject {
  id: string; title: string; status: string; role: string; did: string; result: string; praise: string; done_this_year: boolean;
  /** 286 — 원본 줄(담당과 역할 · 경험)과 카드에 나갈 두 줄 */
  did_lines: string[]; result_lines: string[]; did_lines_card?: string[]; result_lines_card?: string[]; edited?: boolean; skills: string[];
}
export type YearCardLines = Record<string, { did?: string[]; result?: string[] }>;
export interface YearCard {
  name: string; year: string; leader: boolean;
  numbers: { projects: number; done: number; milestones: number; activities: number; hours: number; reports: number };
  new_skills: string[]; candidates: YearCardProject[]; picked: YearCardProject[]; chosen: string[];
  skills: string[]; tools: string[]; skill_options: string[]; tool_options: string[];
  message: string; headline: string; updated_at: string; saved: boolean; missing: string[]; signer: string;
}
export interface YearCardListing {
  year: string; message_max: number; line_count: number; line_max: number;
  people: { name: string; leader: boolean; left_on: string; left: boolean; left_reason: string; saved: boolean; missing: string[]; picked: number; has_message: boolean }[];
}

