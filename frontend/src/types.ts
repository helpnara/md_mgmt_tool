export interface StatusInfo {
  key: string;
  label: string;
  candidate: boolean;
  collapsed: boolean;
}

export interface Meta {
  statuses: StatusInfo[];
  groups: string[];
  tags: string[];
  vault: string;
  report_cycle_days: number;
}

export interface Project {
  id: string;
  title: string;
  status: string;
  group: string | null;
  owner: string | null;
  start_date: string | null;
  due_date: string | null;
  created_at: string | null;
  updated_at: string | null;
  last_reported_at: string | null;
  tags: string[];
  entry_count: number;
  body?: string;
  dir_name?: string;
}

export interface Entry {
  id: number;
  project_id: string;
  rel_path: string;
  date: string;
  title: string;
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
