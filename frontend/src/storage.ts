import { useEffect, useRef } from "react";

/**
 * 브라우저 보관(localStorage · sessionStorage)을 넘어지지 않게 (TODO 212).
 *
 * 사이트 데이터를 막아 둔 PC · 사생활 보호 창에서는 `localStorage` 를 **읽기만 해도** 예외가 난다.
 * 예전에는 화면들이 그대로 써서, 그런 PC 에서는 목록 하나 여는 순간 화면 전체가 안전망(ErrorBoundary)으로 갔다.
 * 기억은 편의일 뿐이다 — 못 하면 기억 못 하는 것으로 끝낸다.
 */
type Area = "local" | "session";

function area(kind: Area): Storage | null {
  try {
    return kind === "local" ? window.localStorage : window.sessionStorage;
  } catch {
    return null;
  }
}

/** 읽기 — 막혀 있거나 없으면 null */
export function storageGet(key: string, kind: Area = "local"): string | null {
  try {
    return area(kind)?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

/** 쓰기 — 실패하면 조용히 넘어간다(가득 참 · 막힘) */
export function storageSet(key: string, value: string, kind: Area = "local"): void {
  try {
    area(kind)?.setItem(key, value);
  } catch {
    /* 기억하지 못할 뿐이다 */
  }
}

export function storageRemove(key: string, kind: Area = "local"): void {
  try {
    area(kind)?.removeItem(key);
  } catch {
    /* 그대로 둔다 */
  }
}

/** JSON 으로 읽기 — 깨진 값이면 fallback */
export function storageGetJson<T>(key: string, fallback: T, kind: Area = "local"): T {
  const raw = storageGet(key, kind);
  if (raw === null) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

const SCROLL_PREFIX = "md-mgmt:scroll:";

/**
 * 목록의 스크롤 자리를 기억했다가 돌아오면 되살린다 (TODO 210 ③).
 *
 * App 은 화면이 바뀌면 맨 위로 올린다 — 200줄 목록에서 150번째를 열고 [← 과제 목록] 으로 오면 맨 위였다.
 * 열쇠는 **주소(화면 + 조건)** 다: 같은 조건으로 돌아왔을 때만 그 자리로 간다. 창(탭)마다 따로라 sessionStorage.
 *
 * `ready` — 줄이 다 그려진 뒤에 true. 그 전에는 되살리지도 적지도 않는다(App 의 맨 위 올림이 0 을 적지 않게).
 */
export function useScrollMemory(ready: boolean): void {
  const restored = useRef(false);
  useEffect(() => {
    if (!ready) return;
    const keyNow = () => SCROLL_PREFIX + window.location.hash;
    if (!restored.current) {
      restored.current = true;
      const saved = Number(storageGet(keyNow(), "session"));
      if (saved > 0) {
        // 그림이 다 선 다음 프레임에 — 위쪽 카드(대시보드)가 같이 서는 틈을 한 번 더 기다린다
        window.requestAnimationFrame(() => window.requestAnimationFrame(() => window.scrollTo(0, saved)));
      }
    }
    let frame = 0;
    const onScroll = () => {
      if (frame) return;
      frame = window.requestAnimationFrame(() => {
        frame = 0;
        storageSet(keyNow(), String(Math.round(window.scrollY)), "session");
      });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [ready]);
}
