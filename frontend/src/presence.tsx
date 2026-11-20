import { useEffect, useState } from "react";
import { api } from "./api";
import type { PresenceHolder, PresencePerson } from "./types";

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

// 318 — 마지막 입력 시각(이 창 전체). 10분 동안 입력이 없으면 서버가 잠금을 내준다
let lastInput = Date.now();
if (typeof window !== "undefined") {
  const touch = () => { lastInput = Date.now(); };
  window.addEventListener("keydown", touch, true);
  window.addEventListener("input", touch, true);
  window.addEventListener("paste", touch, true);
}

// 편집기가 받은 "같이 고치는 사람" — 편집기 부품이 아닌 곳(경고 띠)도 같은 값을 그린다
const others = new Map<string, PresencePerson[]>();
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((fn) => fn());

/** 이 대상을 고치는 중이라고 알린다(`target` 이 null 이면 아무것도 안 함). 닫히면 떠났다고 알린다. */
export function usePresenceBeat(target: string | null): void {
  useEffect(() => {
    if (!target) return;
    let alive = true;
    const opened = Date.now();
    const beat = () => {
      const idle = (Date.now() - Math.max(lastInput, opened)) / 1000;
      api.presenceBeat(target, presenceClient, idle)
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

/**
 * 318 — 부드러운 잠금. [수정]을 누르면 먼저 서버에 묻고, 다른 사람이 먼저 고치는 중이면 편집기를 열지 않고
 * "○○ 님이 고치는 중이므로 읽기 모드로만 볼 수 있습니다" 를 그 자리에 띄운다. [그래도 고치기](확인)로 열 수 있고,
 * 그 사람이 끝나면(저장 · 닫기 · 10분 입력 없음) 안내가 "이제 고칠 수 있습니다 [수정]" 으로 바뀐다.
 */
export function useEditGate() {
  const [gate, setGate] = useState<{ target: string; holder: PresenceHolder; open: () => void } | null>(null);
  useEffect(() => {
    if (!gate) return;
    const timer = window.setInterval(() => {
      api.presenceLock(gate.target, presenceClient)
        .then((d) => setGate((g) => (g && g.target === gate.target ? { ...g, holder: d.holder ?? { ...g.holder, minutes: -1 } } : g)))
        .catch(() => {});
    }, BEAT_MS);
    return () => window.clearInterval(timer);
  }, [gate?.target]); // eslint-disable-line react-hooks/exhaustive-deps

  const tryEdit = async (target: string, open: () => void) => {
    try {
      const d = await api.presenceLock(target, presenceClient);
      if (d.holder) { setGate({ target, holder: d.holder, open }); return; }
    } catch {
      /* 서버에 못 물으면 막지 않는다 — 저장 겹침은 409 가 받친다 */
    }
    setGate(null);
    open();
  };

  const noticeFor = (target: string) => {
    if (!gate || gate.target !== target) return null;
    const free = gate.holder.minutes < 0;
    const go = () => { const open = gate.open; setGate(null); open(); };
    return (
      <div className={free ? "lock-notice free" : "lock-notice"} data-testid="lock-notice" role="status">
        {free ? (
          <>
            <span>{gate.holder.name} 님이 끝냈습니다 — 이제 고칠 수 있습니다.</span>
            <button type="button" onClick={go}>수정</button>
          </>
        ) : (
          <>
            <span className="editing-pencil" aria-hidden>✏️</span>
            <span><b>{gate.holder.name}</b> 님이 고치는 중이므로 읽기 모드로만 볼 수 있습니다{gate.holder.minutes > 0 ? ` (${gate.holder.minutes}분째)` : ""}.
              끝나면 이 자리에 알려 드립니다.</span>
            <button type="button" className="ghost small" onClick={() => {
              if (window.confirm(`${gate.holder.name} 님이 지금 고치는 중입니다.\n\n함께 고치면 나중에 저장하는 쪽이 내용을 다시 합쳐야 합니다. 그래도 열까요?`)) go();
            }}>그래도 고치기</button>
          </>
        )}
        <button type="button" className="ghost small" onClick={() => setGate(null)} aria-label="안내 닫기">닫기</button>
      </div>
    );
  };
  return { tryEdit, noticeFor };
}
