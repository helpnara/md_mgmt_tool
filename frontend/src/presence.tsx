import { useEffect, useState } from "react";
import { api } from "./api";
import type { PresencePerson } from "./types";

/**
 * 지금 고치는 중 (TODO 317) — 편집기가 열려 있는 동안 15초마다 서버에 알리고, 같은 글을 고치는 다른 창을 받는다.
 *
 * * 열쇠는 쓰다 만 글과 같다(`entry:<번호>` · `overview:<과제>` · `report:<번호>` · `intake:<번호>` …) — `useDraftKeeper` 가 알린다.
 * * 내 창은 창마다 다른 값(`client`)으로 뺀다 — 같은 사람이 창 두 개로 열어도 서로 보인다.
 * * 과제 · 접수 화면은 `usePresenceList()` 로 모두 받아 목록 줄에 연필을 붙인다.
 */
const BEAT_MS = 15000;

export const presenceClient: string = (() => {
  try {
    const kept = window.sessionStorage.getItem("md-mgmt-presence-client");
    if (kept) return kept;
    const made = Math.random().toString(36).slice(2, 12);
    window.sessionStorage.setItem("md-mgmt-presence-client", made);
    return made;
  } catch {
    return Math.random().toString(36).slice(2, 12);
  }
})();

// 편집기가 받은 "같이 고치는 사람" — 편집기 부품이 아닌 곳(경고 띠)도 같은 값을 그린다
const others = new Map<string, PresencePerson[]>();
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((fn) => fn());

/** 이 대상을 고치는 중이라고 알린다(`target` 이 null 이면 아무것도 안 함). 닫히면 떠났다고 알린다. */
export function usePresenceBeat(target: string | null): void {
  useEffect(() => {
    if (!target) return;
    let alive = true;
    const beat = () => {
      api.presenceBeat(target, presenceClient)
        .then((d) => { if (alive) { others.set(target, d.others); emit(); } })
        .catch(() => { /* 읽기 전용 PC · 서버 다시 켜는 중 — 알림은 덤이라 조용히 */ });
    };
    beat();
    const timer = window.setInterval(beat, BEAT_MS);
    const away = () => { void api.presenceLeave(target, presenceClient).catch(() => {}); };
    window.addEventListener("pagehide", away);
    return () => {
      alive = false;
      window.clearInterval(timer);
      window.removeEventListener("pagehide", away);
      others.delete(target);
      emit();
      away();
    };
  }, [target]);
}

export function useOthersEditing(target: string | null): PresencePerson[] {
  const [, setTick] = useState(0);
  useEffect(() => {
    const fn = () => setTick((n) => n + 1);
    listeners.add(fn);
    return () => { listeners.delete(fn); };
  }, []);
  return target ? others.get(target) ?? [] : [];
}

/** 편집기 위 경고 띠 — 같은 글을 다른 창에서도 고치는 중 */
export function EditingNow({ target }: { target: string | null }) {
  const people = useOthersEditing(target);
  if (people.length === 0) return null;
  const names = people.map((p) => `${p.name}${p.minutes > 0 ? `(${p.minutes}분째)` : ""}`).join(" · ");
  return (
    <p className="editing-now" data-testid="editing-now" role="status">
      <span className="editing-pencil" aria-hidden>✏️</span>
      <b>{names}</b> 님도 지금 이 글을 고치고 있습니다 — 함께 저장하면 나중에 저장하는 쪽이 다시 합쳐야 합니다. 한 사람이 먼저 저장한 뒤 이어서 고치세요.
    </p>
  );
}

/** 과제 · 접수 화면 — 모든 "고치는 중"(내 창 빼고). 15초마다 다시 받는다 */
export function usePresenceList(enabled = true): Map<string, PresencePerson[]> {
  const [items, setItems] = useState<Map<string, PresencePerson[]>>(new Map());
  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    const load = () => api.presenceList(presenceClient)
      .then((d) => { if (alive) setItems(new Map(d.items.map((i) => [i.target, i.people]))); })
      .catch(() => {});
    void load();
    const timer = window.setInterval(load, BEAT_MS);
    return () => { alive = false; window.clearInterval(timer); };
  }, [enabled]);
  return items;
}

/** 목록 줄 옆 연필 — "○○ 님이 고치는 중" */
export function PencilBadge({ people, label = "고치는 중" }: { people?: PresencePerson[]; label?: string }) {
  if (!people || people.length === 0) return null;
  const names = people.map((p) => p.name).join(" · ");
  return (
    <span className="pencil-badge" data-testid="pencil-badge" title={`${names} 님이 지금 ${label}`}>
      <span className="editing-pencil" aria-hidden>✏️</span>{names} {label}
    </span>
  );
}
