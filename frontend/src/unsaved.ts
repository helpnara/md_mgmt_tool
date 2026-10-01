import { useEffect, useRef, useState } from "react";

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

function send(key: string, content: unknown | null, keepalive = false): Promise<unknown> {
  pending.delete(key);
  const request =
    content === null
      ? fetch(draftUrl(key), { method: "DELETE", keepalive })
      : fetch(draftUrl(key), {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content }),
          keepalive,
        });
  return request.then(() => refreshDrafts()).catch(() => undefined);
}

if (typeof window !== "undefined") {
  window.addEventListener("pagehide", () => {
    for (const [key, content] of pending) void send(key, content, true);
  });
}

export function dropDraft(key: string): void {
  items = items.filter((item) => item.key !== key);
  for (const listener of listeners) listener();
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
