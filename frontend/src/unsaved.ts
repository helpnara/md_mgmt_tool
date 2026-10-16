import { useEffect, useRef, useState } from "react";
import { notifyError } from "./notify";

/**
 * 저장하지 않은 편집 (TODO 162).
 *
 * 과제 개요 · 보고 초안 · 접수 요청 내용 · 검토 기록 · 새 과제 · 새 접수를 쓰다가 메뉴를 누르거나
 * 새로고침하면 **경고 없이 사라졌다.** 편집기마다 "지금 저장 안 한 것이 있다" 를 여기에 알리고,
 * 떠날 때(App 의 주소 바뀜 · 창 닫기) 한 번 묻는다.
 */
const dirty = new Set<string>();

export function hasUnsaved(): boolean {
  return dirty.size > 0;
}

export function clearUnsaved(): void {
  dirty.clear();
}

/** 편집기가 부른다 — `on` 이면 저장 안 한 것이 있다. 편집기가 닫히면 저절로 빠진다. */
export function useUnsaved(key: string, on: boolean): void {
  useEffect(() => {
    if (on) dirty.add(key);
    else dirty.delete(key);
    return () => {
      dirty.delete(key);
    };
  }, [key, on]);
}

export const LEAVE_MESSAGE = "저장하지 않은 내용이 있습니다. 이 화면을 떠나면 사라집니다. 떠날까요?";

/** 사용자가 떠나기로 했는가 — 저장 안 한 것이 없으면 묻지 않고 true */
export function confirmLeave(): boolean {
  if (!hasUnsaved()) return true;
  if (window.confirm(LEAVE_MESSAGE)) {
    clearUnsaved();
    return true;
  }
  return false;
}

// ── 임시 보관 (TODO 162 · 170) ──────────────────────────────────────────
// 쓰던 글을 **데이터 폴더**(`vault/.drafts/`, 이 PC 의 파일)에 남긴다. 처음(162)에는 브라우저 안에 두었는데,
// 브라우저 보관은 창 · 프로필 · 주소마다 따로이고 이미 열린 화면은 다시 읽지 않아 "작성 중이던 기록 있음" 이
// 안 뜨는 일이 있었다(v7 B-6). 이제 어느 창에서 열어도 같은 글이 돌아오고, 홈이 모아 보여 준다.
// 밖으로 나가는 것은 없다 — 이 PC 의 도구(127.0.0.1)와 주고받을 뿐이다.

export interface DraftItem {
  key: string;
  kind: string;
  label: string;
  where: string;
  link: string | null;
  missing: boolean;
  updated_at: string | null;
}

const draftUrl = (key: string) => `/api/drafts/${encodeURIComponent(key)}`;

// 남은 임시 보관 목록 — 화면들이 나눠 본다(표시 · 홈). 창으로 돌아올 때마다 다시 읽는다:
// 다른 창에서 쓴 글도 바로 보이게 (B-6 에서 빠졌던 것).
let items: DraftItem[] = [];
const listeners = new Set<() => void>();
let loading: Promise<void> | null = null;

export function refreshDrafts(): Promise<void> {
  if (loading) return loading;
  // 읽기 전용 공유 (191) — 바깥에는 쓰다 만 글이 닫혀 있다. 묻지 않는다(403 이 콘솔에 쌓이지 않게).
  if (document.body.classList.contains("readonly")) {
    items = [];
    return Promise.resolve();
  }
  loading = fetch("/api/drafts")
    .then((response) => (response.ok ? response.json() : { items: [] }))
    .then((data: { items?: DraftItem[] }) => {
      items = Array.isArray(data.items) ? data.items : [];
      for (const listener of listeners) listener();
    })
    .catch(() => undefined)
    .finally(() => {
      loading = null;
    });
  return loading;
}

if (typeof window !== "undefined") {
  window.addEventListener("focus", () => void refreshDrafts());
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") void refreshDrafts();
  });
}

/** 남은 임시 보관 목록을 보고, 바뀌면 다시 그린다 */
export function useDrafts(): DraftItem[] {
  const [, setTick] = useState(0);
  useEffect(() => {
    const listener = () => setTick((tick) => tick + 1);
    listeners.add(listener);
    void refreshDrafts();
    return () => {
      listeners.delete(listener);
    };
  }, []);
  return items;
}

/** 이 글에 임시 보관이 있나 — 표시("작성 중") 에 쓴다. 목록을 보려면 그리는 쪽에서 useDrafts() 를 불러 둔다. */
export function hasDraft(key: string): boolean {
  return items.some((item) => item.key === key);
}

/** 편집기를 열 때 — 남은 글을 가져온다(원문과 같으면 null) */
export async function loadDraft<T = unknown>(key: string, isOriginal: (content: T) => boolean): Promise<T | null> {
  try {
    const response = await fetch(draftUrl(key));
    if (!response.ok) return null;
    const record = (await response.json()) as { content: T | null };
    if (record.content === null || record.content === undefined) return null;
    return isOriginal(record.content) ? null : record.content;
  } catch {
    return null;
  }
}

// 창을 닫는 순간 아직 보내지 못한 글 — pagehide 에서 keepalive 로 마저 보낸다
const pending = new Map<string, unknown>();

// 같은 열쇠의 지우기를 겹쳐 보내지 않는다 (TODO 215). 기록을 고쳐 저장하면 같은 `entry:186` 에 DELETE 가 동시에
// 두 번 가서, 윈도우에서는 뒤의 것이 `WinError 5 액세스 거부` 로 최근 오류에 쌓였다.
//  - deleting — 지금 가고 있는 지우기(열쇠 → 요청). 같은 열쇠면 그것을 같이 기다린다
//  - dropped  — 이미 지운 열쇠. 그 뒤로 새로 남긴 것(PUT)이 없으면 지우기를 다시 보내지 않는다
//    (편집기의 임시 보관 지킴이가 저장 직후 "원문으로 돌아왔다" 며 한 번 더 지우려 한다)
const deleting = new Map<string, Promise<unknown>>();
const dropped = new Set<string>();
// 보내는 중인 요청 수 — 다 끝났을 때 목록을 **한 번만** 다시 읽는다 (지우기 둘이면 GET 도 둘이던 것)
let inFlight = 0;

function settle(): void {
  inFlight -= 1;
  if (inFlight > 0) return;
  // 이미 읽는 중이면 그 요청은 지우기 전 목록일 수 있다 — 끝난 뒤 한 번 더
  if (loading) void loading.then(() => refreshDrafts());
  else void refreshDrafts();
}

function send(key: string, content: unknown | null, keepalive = false): Promise<unknown> {
  pending.delete(key);
  if (content === null) {
    const running = deleting.get(key);
    if (running) return running;
    if (dropped.has(key)) return Promise.resolve();
    dropped.add(key);
    inFlight += 1;
    const request = fetch(draftUrl(key), { method: "DELETE", keepalive })
      .catch(() => undefined)
      .finally(() => {
        deleting.delete(key);
        settle();
      });
    deleting.set(key, request);
    return request;
  }
  dropped.delete(key);
  inFlight += 1;
  return fetch(draftUrl(key), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
    keepalive,
  })
    .catch(() => undefined)
    .finally(settle);
}

if (typeof window !== "undefined") {
  window.addEventListener("pagehide", () => {
    for (const [key, content] of pending) void send(key, content, true);
  });
}

/** 임시 보관을 지운다 — 같은 열쇠의 지우기가 이미 가고 있거나 막 지웠으면 다시 보내지 않는다 (TODO 215) */
export function dropDraft(key: string): void {
  items = items.filter((item) => item.key !== key);
  for (const listener of listeners) listener();
  // 저장 · 버리기는 "지금 남은 것을 지워라" 다 — 다른 창이 그사이 남긴 것도 지우도록, 막 지운 표시는 무시한다
  if (!deleting.has(key)) dropped.delete(key);
  void send(key, null);
}

/**
 * 편집 중인 글을 잠시 뒤(0.7초) 데이터 폴더에 남긴다. `key` 가 null 이면(편집 중이 아니면) 아무것도 안 한다.
 * 원문과 같아지면 지운다. `content` 는 글 하나든 {date, title, body, tags} 같은 묶음이든 된다.
 */
export function useDraftKeeper(key: string | null, content: unknown, isOriginal: boolean): void {
  const signature = JSON.stringify(content);
  // 이 편집에서 한 번이라도 남겼는가 — 편집기를 막 열어 원문 그대로일 때 지우기를 보내면, 되살리기 전에
  // **남아 있던 글을 지워 버린다.** 지우는 것은 이번에 쓴 뒤 원문으로 되돌린 때만(저장 · 버리기는 dropDraft 가 한다).
  const wrote = useRef(false);
  useEffect(() => {
    if (key === null) {
      wrote.current = false;
      return;
    }
    if (isOriginal && !wrote.current) return;
    if (!isOriginal) wrote.current = true;
    const value = isOriginal ? null : content;
    pending.set(key, value);
    const timer = window.setTimeout(() => void send(key, value), 700);
    return () => window.clearTimeout(timer);
    // content 는 매번 새 객체일 수 있어 내용(signature)으로 본다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, signature, isOriginal]);

  // 편집기가 닫히면(메뉴로 떠남 · 화면 이동) 기다리던 것을 **바로** 보낸다 — 0.7초 안에 메뉴를 누르면
  // 마지막 글이 보관되지 않았다. 창을 닫을 때는 pagehide 가 같은 일을 한다.
  const lastKey = useRef(key);
  lastKey.current = key;
  useEffect(
    () => () => {
      const leaving = lastKey.current;
      if (leaving !== null && pending.has(leaving)) void send(leaving, pending.get(leaving) ?? null);
    },
    [],
  );
}

/**
 * 162 때 브라우저 안에 남은 글을 데이터 폴더로 옮긴다(한 번). 열쇠 모양이 바뀌었다 —
 * 진행일지는 `md-mgmt:draft:new-<과제>` · `md-mgmt:draft:<번호>` → `entry:…`.
 */
export async function migrateBrowserDrafts(): Promise<void> {
  if (document.body.classList.contains("readonly")) return; // 읽기 전용 공유 — 서버에 올릴 수 없다 (191)
  let keys: string[] = [];
  try {
    keys = Object.keys(localStorage).filter((key) => key.startsWith("md-mgmt:draft:"));
  } catch {
    return;
  }
  for (const old of keys) {
    const rest = old.slice("md-mgmt:draft:".length);
    const key = /^(new-.+|\d+)$/.test(rest) ? `entry:${rest}` : rest;
    let content: unknown = null;
    try {
      const raw = localStorage.getItem(old) ?? "";
      content = key.startsWith("entry:") ? JSON.parse(raw) : raw;
    } catch {
      content = null;
    }
    const exists = await fetch(draftUrl(key)).then((response) => response.ok).catch(() => true);
    if (content !== null && !exists) {
      const ok = await fetch(draftUrl(key), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      })
        .then((response) => response.ok)
        .catch(() => false);
      if (!ok) continue; // 옮기지 못했으면 브라우저 것을 지우지 않는다
    }
    try {
      localStorage.removeItem(old);
    } catch {
      /* 그대로 둔다 */
    }
  }
  void refreshDrafts();
}

/**
 * 입력 양식(새 과제 · 새 접수 · 역량 기록 …)용 — 처음 모양과 지금 모양을 견준다.
 * 보내는 중(`busy`)에는 빼 둔다: 저장이 끝나 다른 화면으로 옮겨 갈 때 "떠날까요?" 가 뜨면 안 된다.
 */
export function useFormUnsaved(key: string, current: unknown, busy: boolean): void {
  const [initial] = useState(() => JSON.stringify(current));
  useUnsaved(key, !busy && JSON.stringify(current) !== initial);
}

// ── 편집 한 번의 장부 (TODO 213) ──────────────────────────────────────────
// 편집기 안의 몇몇 동작(첨부 · 붙여넣은 그림 · 첨부 삭제)은 [저장] 을 기다리지 않고 바로 서버에 쓴다. [닫기] → 버리기가
// 그것을 모르면 "버렸는데 남는다"(사용자 제보). 편집기가 열린 동안 바로 쓴 것을 여기에 적어 두고 —
//   · 이번에 올린 첨부(uploaded) — 버리면 지운다(삭제 보관함으로)
//   · 지우기로 한 첨부(doomed)   — [저장] 할 때 지운다. 버리면 아무 일도 없다
// 메뉴 이동 · 창 닫기로 떠날 때(useUnsaved 의 "떠날까요?")는 지우지 않는다 — 임시 보관(draft)이 남아 다시 이어 쓰므로,
// 그 글이 가리키는 첨부도 남아야 한다(TODO 213 의 남는 것).

export interface EditLedger<K> {
  uploaded: K[];
  doomed: K[];
  /** 지우기로 한 것 중 이번에 올린 것이 아닌 것 — 버리면 "그대로 남는" 것 */
  doomedExisting: K[];
  /** 장부가 비었나 — 비어 있지 않으면 쓴 글이 그대로여도 [닫기] 가 묻는다 */
  empty: boolean;
  addUploaded: (key: K) => void;
  /** [삭제] ↔ [되살리기] */
  toggleDoomed: (key: K) => void;
  isDoomed: (key: K) => boolean;
  /** [저장] 뒤 — 지우기로 한 것을 지우고 장부를 비운다. 이번에 올린 것은 이제 저장된 것이다. */
  commit: (remove: (key: K) => Promise<unknown>) => Promise<void>;
  /** 버리기 — 이번에 올린 것을 지우고 장부를 비운다. 지우기로 한 것은 그대로 둔다. */
  rollback: (remove: (key: K) => Promise<unknown>) => Promise<void>;
  /** 아무것도 지우지 않고 비운다 — [이전 버전] 으로 되돌려 편집기가 닫힐 때처럼 */
  clear: () => void;
}

export function useEditLedger<K extends string | number>(): EditLedger<K> {
  const [state, setState] = useState<{ uploaded: K[]; doomed: K[] }>({ uploaded: [], doomed: [] });
  // 비동기 저장 · 자동 저장 타이머가 최신 장부를 보게 — 값은 ref 에, 화면은 state 로
  const ref = useRef(state);
  const update = (next: { uploaded: K[]; doomed: K[] }) => {
    ref.current = next;
    setState(next);
  };
  const removeAll = async (keys: K[], remove: (key: K) => Promise<unknown>) => {
    const failed: string[] = [];
    for (const key of keys) {
      try {
        await remove(key);
      } catch (err) {
        // 이미 없으면(404) 지운 것과 같다
        const message = (err as Error)?.message ?? "";
        if (!message.includes("찾을 수 없")) failed.push(message);
      }
    }
    if (failed.length > 0) notifyError(`첨부 ${failed.length}건을 지우지 못했습니다 — ${failed[0]}`);
  };
  return {
    uploaded: state.uploaded,
    doomed: state.doomed,
    doomedExisting: state.doomed.filter((key) => !state.uploaded.includes(key)),
    empty: state.uploaded.length === 0 && state.doomed.length === 0,
    addUploaded: (key) => {
      if (!ref.current.uploaded.includes(key)) update({ ...ref.current, uploaded: [...ref.current.uploaded, key] });
    },
    toggleDoomed: (key) => {
      const doomed = ref.current.doomed.includes(key)
        ? ref.current.doomed.filter((item) => item !== key)
        : [...ref.current.doomed, key];
      update({ ...ref.current, doomed });
    },
    isDoomed: (key) => state.doomed.includes(key),
    commit: async (remove) => {
      const doomed = ref.current.doomed;
      update({ uploaded: [], doomed: [] });
      await removeAll(doomed, remove);
    },
    rollback: async (remove) => {
      const uploaded = ref.current.uploaded;
      update({ uploaded: [], doomed: [] });
      await removeAll(uploaded, remove);
    },
    clear: () => update({ uploaded: [], doomed: [] }),
  };
}

/**
 * [닫기] · [취소] 가 묻는 말 — 편집기마다 같은 말로, **사실대로** (TODO 213 ⑤).
 * `what` 은 "기록을" · "개요를" 처럼 조사까지. 이 편집에서 저장한 적이 있으면 "마지막 (자동) 저장 이후" 로 묻는다 —
 * 그 앞의 것은 이미 저장돼 버려지지 않는다.
 */
export function discardQuestion(options: {
  what: string;
  savedAt?: string | null;
  auto?: boolean;
  createdEntry?: boolean;
  uploaded?: number;
  doomed?: number;
}): string {
  const { what, savedAt, auto, createdEntry, uploaded = 0, doomed = 0 } = options;
  const lines = [
    savedAt ? `마지막 ${auto ? "자동 저장" : "저장"}(${savedAt}) 이후 고친 것을 버릴까요?` : `저장하지 않은 ${what} 버릴까요?`,
  ];
  if (createdEntry && uploaded > 0)
    lines.push(`첨부를 올리느라 먼저 만든 기록과 이번에 올린 첨부 ${uploaded}건도 함께 지웁니다(삭제 보관함으로).`);
  else if (createdEntry) lines.push("첨부를 올리느라 먼저 만든 기록도 함께 지웁니다(삭제 보관함으로).");
  else if (uploaded > 0) lines.push(`이번에 올린 첨부 ${uploaded}건도 함께 지웁니다(삭제 보관함으로).`);
  if (doomed > 0) lines.push(`지울 예정이던 첨부 ${doomed}건은 지우지 않고 그대로 둡니다.`);
  return lines.join("\n");
}

/** 지금 시각 "10:42" — 저장 표시 · 묻는 말에 쓴다 */
export function clockNow(): string {
  return new Date().toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
}
