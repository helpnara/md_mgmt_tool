import type { Entry, Meta, Project } from "./types";

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
  reindex: () => request<{ indexed: number }>("/api/reindex", { method: "POST" }),
};
