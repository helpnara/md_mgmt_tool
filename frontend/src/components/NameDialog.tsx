import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { LIMITS, lengthState, personNameProblem } from "../inputRules";
import { useEscape } from "../util";

/**
 * 이름 하나를 받는 작은 창 (TODO 214 D9 · F6) — [넘기기] · [다른 이름으로 통일] 이 쓰던 브라우저 `prompt()` 대신.
 *
 * `prompt()` 는 아무것도 검사하지 않아 `"가, 나"` 가 한 사람으로 굳고 `../x` 도 들어갔다. 여기서는
 * 서버와 같은 이름 규칙(쉼표 · `/ \ ..` · 줄바꿈 금지, 40자)을 칸 옆에 먼저 보이고, 명부 이름을 자동완성으로 내준다.
 * 서버가 답하면 **종류별로 무엇을 몇 건 바꿨는지**(과제 담당 · 유관부서 · 역량 · 면담 · 접수 과제리더)를 창 안에 보인다.
 */
export interface NameDialogProps {
  title: string;
  /** 무엇이 바뀌고 무엇이 그대로인지 — 확인 창이 하던 말 */
  message?: ReactNode;
  /** 바꾸기 전 이름 — 같으면 막는다 */
  from: string;
  initial?: string;
  label?: string;
  confirmLabel: string;
  /** 자동완성 — 지금 있는 사람 */
  roster: string[];
  /** 떠난 사람 — 고르면 경고(막지는 않는다) */
  departed?: Set<string>;
  /** 명부에 없는 이름이면 경고할까 (넘기기) */
  warnUnknown?: boolean;
  /** 서버에 보내고 결과 줄을 돌려준다. 던지면 창 안에 사유를 보인다 */
  onSubmit: (name: string) => Promise<string[]>;
  onClose: () => void;
}

export default function NameDialog({
  title,
  message,
  from,
  initial = "",
  label = "새 이름",
  confirmLabel,
  roster,
  departed,
  warnUnknown = false,
  onSubmit,
  onClose,
}: NameDialogProps) {
  const [name, setName] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string[] | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);
  const close = useCallback(() => {
    if (!busy) onClose();
  }, [busy, onClose]);
  useEscape(close);

  const text = name.trim();
  const problem = !text
    ? "이름을 적어 주세요."
    : personNameProblem(name) ?? (text === from.trim() ? "지금 이름과 같습니다 — 다른 이름을 적어 주세요." : null);
  const warn =
    !problem && departed?.has(text)
      ? `${text} — 명부에서 떠난 사람입니다. 그래도 이 이름으로 할까요?`
      : !problem && warnUnknown && roster.length > 0 && !roster.includes(text) && !departed?.has(text)
        ? `${text} — 명부에 없는 이름입니다. 오타가 아닌지 확인해 주세요.`
        : null;
  const { left } = lengthState(text, LIMITS.name);

  async function submit() {
    if (problem || busy || done) return;
    setBusy(true);
    setError(null);
    try {
      setDone(await onSubmit(text));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label={title} onClick={close}>
      <div
        className="modal name-dialog"
        onClick={(event) => event.stopPropagation()}
        onKeyDown={(event) => {
          // 창 안의 Enter 는 창의 것이다 — 바깥 카드의 [저장](U9)으로 새지 않게 막는다
          if (event.key !== "Enter" || event.nativeEvent.isComposing || event.keyCode === 229) return;
          event.preventDefault();
          event.stopPropagation();
          if (done) onClose();
          else void submit();
        }}
      >
        <h2>{title}</h2>
        {message && <div className="hint name-dialog-message">{message}</div>}
        {done ? (
          <div className="name-dialog-done" role="status">
            {done.map((line) => (
              <p key={line}>{line}</p>
            ))}
          </div>
        ) : (
          <label className="stack-label">
            {label} *
            <input
              ref={inputRef}
              list="name-dialog-roster"
              value={name}
              maxLength={LIMITS.name + 20}
              onChange={(event) => setName(event.target.value)}
              aria-invalid={problem && name ? true : undefined}
            />
            <datalist id="name-dialog-roster">
              {roster.map((item) => (
                <option key={item} value={item} />
              ))}
            </datalist>
            {problem && name ? (
              <span className="field-error name-dialog-error">{problem}</span>
            ) : warn ? (
              <span className="form-warn name-dialog-warn">{warn}</span>
            ) : (
              <span className="hint">쉼표 · / \ 없이 한 사람, {LIMITS.name}자까지{left <= 10 ? ` · ${left}자 남음` : ""}</span>
            )}
          </label>
        )}
        {error && <p className="form-error">{error}</p>}
        <div className="form-actions">
          {done ? (
            <button onClick={onClose}>닫기</button>
          ) : (
            <>
              <button className="ghost" disabled={busy} onClick={close}>
                취소
              </button>
              <button disabled={Boolean(problem) || busy} onClick={() => void submit()}>
                {busy ? "바꾸는 중…" : confirmLabel}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/** 서버가 준 종류별 수의 이름 (TODO 214 D9) — 모양이 달라도(묶음 `counts` 또는 평평한 칸) 읽는다 */
const KIND_LABELS: [string[], string][] = [
  [["projects", "owners", "project_owners"], "과제 담당"],
  [["partners", "partner_people", "partner_persons"], "유관부서 담당"],
  [["activities"], "역량 기록"],
  [["meetings"], "면담 기록"],
  [["intakes", "intake_leaders", "leaders"], "접수 과제리더"],
];

/** 결과를 "과제 담당 3건 · 면담 기록 2건" 처럼 */
export function changeCounts(result: unknown): string {
  const body = (result ?? {}) as Record<string, unknown>;
  const counts = body.counts && typeof body.counts === "object" ? (body.counts as Record<string, unknown>) : null;
  const read = (value: unknown): number | null =>
    typeof value === "number" ? value : Array.isArray(value) ? value.length : null;
  const parts: string[] = [];
  for (const [keys, label] of KIND_LABELS) {
    let found: number | null = null;
    for (const key of keys) {
      found = read(counts?.[key]) ?? (key === "projects" || key === "owners" ? null : read(body[key]));
      if (found !== null) break;
    }
    // 과제 수는 예전부터 `count` 로 온다
    if (found === null && label === "과제 담당") found = read(body.count);
    if (found) parts.push(`${label} ${found}건`);
  }
  return parts.length > 0 ? parts.join(" · ") : "바꾼 기록이 없습니다";
}
