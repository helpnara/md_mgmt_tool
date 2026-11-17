import type { EditDiff, EditDiffLine, EditItem } from "../types";

/**
 * 팀원이 고친 곳 (TODO 305) — 홈 "팀원이 고친 것" 의 줄 → 과제 화면에서 바뀐 곳 표시.
 *
 * * 비교 — 그 줄의 첫 수정 직전 보관본 ↔ 지금(서버 `/api/edits/diff`). 더한 줄 초록 · 고친 줄 노랑(고치기 전은 취소선) · 지운 줄 취소선.
 * * 본 것(C) — 이 브라우저에 줄의 열쇠(사람 · 과제 · 일지 · 무엇 · 마지막 시각)를 적어 둔다. 그 뒤 또 고치면 마지막 시각이 바뀌어 다시 "안 봄".
 */

/** 과제 화면 주소에 싣는 값 — App 이 읽어 ProjectDetail 의 `changed` 로 넘긴다 */
export function changeLinkParams(item: EditItem): Record<string, string | number | undefined> {
  return {
    chg: item.name,
    what: item.action,
    since: item.first_real || item.first_at || item.at,
    base: item.first_base || undefined,
    from: item.first_at || item.at,
    to: item.at,
    n: item.count > 1 ? item.count : undefined,
    entry: item.entry_id && item.action !== "진행일지 삭제" ? item.entry_id : undefined,
  };
}

export interface ChangeMark {
  by: string;
  what: string;
  since: string;
  base: string;
  from: string;
  to: string;
  count: number;
  entry?: number;
}

export function changeFromParams(params: URLSearchParams): ChangeMark | undefined {
  const by = params.get("chg");
  if (!by) return undefined;
  const entry = params.get("entry");
  return {
    by, what: params.get("what") ?? "", since: params.get("since") ?? "", base: params.get("base") ?? "",
    from: params.get("from") ?? "", to: params.get("to") ?? "", count: Number(params.get("n") ?? 1) || 1,
    entry: entry ? Number(entry) : undefined,
  };
}

export function diffQuery(projectId: string, mark: ChangeMark): Record<string, string | number | undefined> {
  return { project: projectId, action: mark.what, since: mark.since, person: mark.by, base: mark.base,
    first_at: mark.from, last_at: mark.to, entry: mark.entry };
}

export function itemDiffQuery(item: EditItem): Record<string, string | number | undefined> {
  return { project: item.project_id ?? "", action: item.action, since: item.first_real || item.first_at || item.at, person: item.name,
    base: item.first_base || undefined, first_at: item.first_at || item.at, last_at: item.at, entry: item.entry_id ?? undefined };
}

/** "더함 2 · 고침 1 · 지움 1" */
export function diffCounts(diff: EditDiff): string {
  if (diff.kind === "new" && diff.new_entries.length) return `새 일지 ${diff.new_entries.length}건`;
  const parts = [diff.added ? `더함 ${diff.added}줄` : "", diff.changed ? `고침 ${diff.changed}줄` : "", diff.removed ? `지움 ${diff.removed}줄` : ""].filter(Boolean);
  return parts.join(" · ") || "글은 그대로(정보만 바뀜)";
}

const MARK: Record<EditDiffLine["op"], string> = { same: " ", add: "+", del: "−", old: "−", new: "+", gap: "…" };

/** 줄마다 색 — `limit` 이면 바뀐 줄 위주로 앞에서 몇 줄만(홈 미리보기) */
export function DiffLines({ lines, limit }: { lines: EditDiffLine[]; limit?: number }) {
  const shown = limit ? lines.filter((line) => line.op !== "same" && line.op !== "gap").slice(0, limit) : lines;
  const rest = limit ? lines.filter((line) => line.op !== "same" && line.op !== "gap").length - shown.length : 0;
  return (
    <ol className="edit-diff" data-testid="edit-diff">
      {shown.map((line, index) => (
        <li key={index} className={`edit-diff-${line.op}`}>
          <span className="edit-diff-mark" aria-hidden>{MARK[line.op]}</span>
          <span className="edit-diff-text">{line.op === "gap" ? "(같은 줄 생략)" : line.text || " "}</span>
        </li>
      ))}
      {rest > 0 && <li className="edit-diff-gap"><span className="edit-diff-mark">…</span><span className="edit-diff-text">바뀐 줄 {rest}개 더</span></li>}
    </ol>
  );
}

// ── 본 것 (C) ─────────────────────────────────────────────────────────────
const SEEN_KEY = "md-mgmt-edit-seen";
const SEEN_MAX = 500;

export function loadSeen(): Set<string> {
  try {
    const raw = window.localStorage.getItem(SEEN_KEY);
    return new Set(raw ? (JSON.parse(raw) as string[]) : []);
  } catch {
    return new Set();
  }
}

export function saveSeen(seen: Set<string>): void {
  try {
    window.localStorage.setItem(SEEN_KEY, JSON.stringify([...seen].slice(-SEEN_MAX)));
  } catch {
    /* 저장할 수 없는 브라우저 — 이번 화면에서만 기억 */
  }
}
