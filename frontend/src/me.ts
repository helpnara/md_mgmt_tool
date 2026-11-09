import type { Me } from "./types";

/**
 * 지금 누구인가 (TODO 233). App 이 켤 때 `/api/me` 로 받아 둔다.
 *
 * * 관리자(owner) — 서버 PC. 모든 단추 + 서버 운영(데이터 위치 · 자동 백업 폴더 · 되살리기 · 팀장 지정과 팀장 PC 주소).
 * * 팀장(leader) — 명부의 팀장 IP (TODO 247). 서버 운영만 빼고 관리자와 같다 — `isManager`.
 * * 팀원(member) — 설정 → 명부에 IP 를 등록한 PC. 화면 전체는 읽기 전용(body.readonly)이고,
 *   **담당 과제의 상세에서만** 진행일지 · 첨부 · 개요 단추가 선다(`canEditProject`). 본인 면담은 보기만.
 * * 읽기(viewer) — 그 밖. 지금(191)의 읽기 전용 그대로.
 *
 * **숨기는 것은 편의다. 막는 것은 서버다**(readonly.ts 와 같은 원칙) — 단추가 보여도 허용 목록 밖의 쓰기는 403 이다.
 */
let current: Me = { role: "owner", name: "", projects: [], ip: "", share: false };

export function setMe(me: Me): void {
  current = me;
  document.body.classList.toggle("member", me.role === "member");
  // 팀장 PC (TODO 247) — 서버 운영 칸([data-admin-only])을 숨긴다
  document.body.classList.toggle("leader", me.role === "leader");
}

export function getMe(): Me {
  return current;
}

/** 팀을 맡은 쪽 — 관리자(서버 PC) · 팀장(팀장 PC, TODO 247). 모든 과제 · 명부 · 면담 · 설정 */
export function isManager(me: Me = current): boolean {
  return me.role === "owner" || me.role === "leader";
}

/** 서버 운영 칸(데이터 위치 · 자동 백업 폴더 · 되살리기 · 팀장 지정과 팀장 PC 주소)을 다룰 수 있나 — 서버 PC 만 (TODO 247) */
export function isAdmin(me: Me = current): boolean {
  return me.role === "owner";
}

export function isMember(): boolean {
  return current.role === "member";
}

/** 이 과제를 고칠 수 있나 — 팀장이면 늘, 팀원이면 담당일 때만 */
export function canEditProject(projectId: string): boolean {
  return isManager() || (current.role === "member" && current.projects.includes(projectId));
}

/** 이 진행일지를 고치거나 지울 수 있나 — 팀원은 **본인이 쓴 것만** (TODO 233 ③) */
export function canEditEntry(projectId: string, author: string | null | undefined): boolean {
  if (isManager()) return true;
  return canEditProject(projectId) && (author ?? "") === current.name;
}
