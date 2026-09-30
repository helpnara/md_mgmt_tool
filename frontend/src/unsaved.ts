import { useEffect, useState } from "react";

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

// ── 임시 보관 (TODO 162) ────────────────────────────────────────────────
// 진행일지 편집기처럼 **브라우저 안에** 쓰던 글을 남긴다 — 확인창을 지나쳐 창을 닫았거나 PC 가 꺼져도
// 다시 열면 돌아온다. 저장하거나 버리면 지운다. 브라우저 밖으로는 나가지 않는다.
const DRAFT_PREFIX = "md-mgmt:draft:";

function readStore(key: string): string | null {
  try {
    return localStorage.getItem(DRAFT_PREFIX + key);
  } catch {
    return null;
  }
}

/** 편집기를 열 때 — 저장하지 않고 남은 글이 있으면(원문과 다르면) 돌려준다 */
export function takeDraft(key: string, original: string): string | null {
  const stored = readStore(key);
  return stored !== null && stored !== original ? stored : null;
}

/** 이 글에 임시 보관이 있나 — [기록 추가] 옆 표시 같은 데 쓴다 */
export function hasDraft(key: string): boolean {
  return readStore(key) !== null;
}

export function dropDraft(key: string): void {
  try {
    localStorage.removeItem(DRAFT_PREFIX + key);
  } catch {
    /* 저장소를 못 쓰는 브라우저 — 임시 보관 없이 간다 */
  }
}

/** 편집 중인 글을 잠시 뒤(0.4초) 임시 보관한다. `key` 가 null 이면(편집 중이 아니면) 아무것도 안 한다. */
export function useDraftKeeper(key: string | null, text: string, original: string): void {
  useEffect(() => {
    if (key === null) return;
    const timer = window.setTimeout(() => {
      try {
        if (text === original) localStorage.removeItem(DRAFT_PREFIX + key);
        else localStorage.setItem(DRAFT_PREFIX + key, text);
      } catch {
        /* 저장소가 꽉 찼거나 막혔다 — 확인창이 남은 안전망이다 */
      }
    }, 400);
    return () => window.clearTimeout(timer);
  }, [key, text, original]);
}

/**
 * 입력 양식(새 과제 · 새 접수 · 역량 기록 …)용 — 처음 모양과 지금 모양을 견준다.
 * 보내는 중(`busy`)에는 빼 둔다: 저장이 끝나 다른 화면으로 옮겨 갈 때 "떠날까요?" 가 뜨면 안 된다.
 */
export function useFormUnsaved(key: string, current: unknown, busy: boolean): void {
  const [initial] = useState(() => JSON.stringify(current));
  useUnsaved(key, !busy && JSON.stringify(current) !== initial);
}
