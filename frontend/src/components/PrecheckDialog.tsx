import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { isReadonly } from "../readonly";
import type { IntakeDetail, Meta, PrecheckBand } from "../types";
import { useUnsaved } from "../unsaved";

/**
 * 사전점검 체크리스트 대화상자 (TODO 155).
 *
 * 분류마다 한 묶음, 항목마다 한 줄 — 단계를 **점수가 적힌 칩**으로 고른다(누른 칩을 다시 누르면 지운다).
 * 근거 한 줄은 선택. 아래 줄이 늘 보이며 합계 · 구간 · *평가 7/10* 을 바로 고쳐 보인다.
 * 다 매기기 전에는 합계를 내지 않는다 — 세 항목만 매긴 30점과 다 매긴 30점은 같은 수가 아니다.
 * 판정이 난 접수는 볼 수만 있다.
 */
const SEP = "␟";
const key = (group: string, item: string) => `${group}${SEP}${item}`;

export function BandChip({ band }: { band: PrecheckBand | null }) {
  if (!band) return null;
  return <span className={`precheck-band band-${band.key}`}>{band.label}</span>;
}

export function bandOf(score: number | null, meta: Meta): PrecheckBand | null {
  if (score === null) return null;
  const [high, low] = meta.precheck.thresholds;
  const [go, fix, hold] = meta.precheck.bands;
  const picked = score >= high ? go : score >= low ? fix : hold;
  return picked as PrecheckBand;
}

export default function PrecheckDialog({
  intake,
  meta,
  onClose,
  onSaved,
}: {
  intake: IntakeDetail;
  meta: Meta;
  onClose: () => void;
  onSaved: (next: IntakeDetail) => void;
}) {
  // 판정이 난 접수는 그때의 점수로 굳는다. 읽기 전용 공유(208)에서도 같은 모양 — 보기만 한다.
  const shared = isReadonly();
  const readOnly = !intake.in_pool || shared;
  const items = meta.precheck.items;
  const initial = useMemo(() => {
    const out: Record<string, { choice: string | null; note: string }> = {};
    for (const answer of intake.precheck.items) out[key(answer.group, answer.item)] = { choice: answer.choice, note: answer.note ?? "" };
    return out;
  }, [intake.precheck.items]);
  const [answers, setAnswers] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dirty = JSON.stringify(answers) !== JSON.stringify(initial);
  // 창을 연 채 메뉴를 누르거나 새로고침하면 묻는다 (TODO 162)
  useUnsaved(`precheck:${intake.id}`, dirty && !readOnly);

  // 합계는 **지금 고른 것**으로 바로 — 저장 전에 결과를 본다
  let raw = 0;
  let max = 0;
  let rated = 0;
  const groups: { group: string; rows: typeof items; score: number; max: number }[] = [];
  for (const item of items) {
    let entry = groups.find((g) => g.group === item.group);
    if (!entry) {
      entry = { group: item.group, rows: [], score: 0, max: 0 };
      groups.push(entry);
    }
    entry.rows.push(item);
    const top = Math.max(...item.choices.map(([, score]) => score));
    entry.max += top;
    const choice = answers[key(item.group, item.item)]?.choice;
    const picked = item.choices.find(([label]) => label === choice);
    if (picked) {
      rated += 1;
      raw += picked[1];
      max += top;
      entry.score += picked[1];
    }
  }
  const complete = rated === items.length && max > 0;
  const score = complete ? Math.round((raw * 100) / max) : null;
  // 근거만 적고 단계를 고르지 않은 줄 — 예전에는 말없이 버렸다. 이제 서버가 400 이라 화면이 먼저 막는다 (TODO 214 D17)
  const noteOnly = readOnly
    ? []
    : items
        .map((item) => key(item.group, item.item))
        .filter((itemKey) => (answers[itemKey]?.note ?? "").trim() !== "" && !answers[itemKey]?.choice);

  function close() {
    if (dirty && !readOnly && !window.confirm("저장하지 않은 점수가 있습니다. 닫을까요?")) return;
    onClose();
  }

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  function pick(itemKey: string, label: string) {
    if (readOnly) return;
    setAnswers((prev) => {
      const current = prev[itemKey] ?? { choice: null, note: "" };
      // 고른 칩을 다시 누르면 지운다 — 잘못 누른 것을 되돌릴 길
      return { ...prev, [itemKey]: { ...current, choice: current.choice === label ? null : label } };
    });
  }

  async function save() {
    if (noteOnly.length > 0) return;
    setBusy(true);
    setError(null);
    try {
      const payload = items.map((item) => {
        const answer = answers[key(item.group, item.item)];
        return { group: item.group, item: item.item, choice: answer?.choice ?? null, note: answer?.note?.trim() || null };
      });
      onSaved(await api.savePrecheck(intake.id, payload));
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="사전점검 체크리스트" onClick={close}>
      <div className="modal precheck-dialog" onClick={(event) => event.stopPropagation()}>
        <div className="card-head">
          <div>
            <h2>사전점검 체크리스트</h2>
            <p className="hint">
              {intake.id} {intake.title} — 항목마다 단계를 고릅니다. 고른 칩을 다시 누르면 지워집니다. 근거는 선택입니다.
            </p>
          </div>
          <button className="ghost" onClick={close}>
            닫기
          </button>
        </div>
        {intake.precheck.stale && (
          <p className="warn-text precheck-stale">
            지금 체크리스트와 <b>다른 기준</b>으로 매긴 점수입니다(항목·점수가 설정에서 바뀌었습니다). 다시 매겨 저장하면 지금
            기준으로 바뀝니다.
          </p>
        )}
        {readOnly && (
          <p className="hint">
            {shared ? "읽기 전용 공유라 볼 수만 있습니다 — 점수는 서버 PC 에서 매깁니다." : "판정이 난 접수라 볼 수만 있습니다 — 그때의 점수로 굳어 있습니다."}
          </p>
        )}

        {groups.map((group) => (
          <section key={group.group} className="precheck-group">
            <h3>
              {group.group}
              <span className="precheck-subtotal">
                {group.score} / {group.max}
              </span>
            </h3>
            {group.rows.map((item) => {
              const itemKey = key(item.group, item.item);
              const answer = answers[itemKey];
              const scores = item.choices.map(([, s]) => s);
              const top = Math.max(...scores);
              const bottom = Math.min(...scores);
              const missingChoice = noteOnly.includes(itemKey);
              return (
                <div
                  key={itemKey}
                  className={`precheck-row${answer?.choice ? "" : " unrated"}${missingChoice ? " precheck-row-invalid" : ""}`}
                >
                  <div className="precheck-item">{item.item}</div>
                  <div className="precheck-choices" role="radiogroup" aria-label={item.item}>
                    {item.choices.map(([label, value]) => {
                      const on = answer?.choice === label;
                      const tone = value === top ? "high" : value === bottom ? "low" : "mid";
                      return (
                        <button
                          key={label}
                          type="button"
                          role="radio"
                          aria-checked={on}
                          disabled={readOnly && !on}
                          className={`precheck-choice tone-${tone}${on ? " on" : ""}`}
                          onClick={() => pick(itemKey, label)}
                        >
                          {label} <b>{value}</b>
                        </button>
                      );
                    })}
                  </div>
                  <input
                    className="precheck-note"
                    value={answer?.note ?? ""}
                    readOnly={readOnly}
                    onChange={(event) =>
                      setAnswers((prev) => ({
                        ...prev,
                        [itemKey]: { choice: prev[itemKey]?.choice ?? null, note: event.target.value },
                      }))
                    }
                    placeholder={readOnly ? "" : "근거 한 줄 (선택) — 예: 9/12 사업부장 회의"}
                    aria-label={`${item.item} 근거`}
                    aria-invalid={missingChoice ? true : undefined}
                  />
                  {missingChoice && (
                    <span className="form-warn precheck-note-error">단계를 골라 주세요 — 근거만 적은 줄은 저장할 수 없습니다.</span>
                  )}
                </div>
              );
            })}
          </section>
        ))}

        {error && <p className="error form-error">{error}</p>}
        {noteOnly.length > 0 && (
          <p className="hint warn-text form-blocker">
            근거만 적고 단계를 고르지 않은 항목이 {noteOnly.length}개 있습니다 — 단계를 고르거나 근거를 지워야 저장할 수 있습니다.
          </p>
        )}
        <div className="form-actions precheck-foot">
          <span className="precheck-total">
            합계{" "}
            {score !== null ? (
              <>
                <b>{score}</b>점 / 100 <BandChip band={bandOf(score, meta)} />
              </>
            ) : (
              <span className="muted">— 다 매기면 나옵니다</span>
            )}
            <span className="muted">
              {" "}
              · 평가 {rated}/{items.length}
            </span>
          </span>
          {!readOnly && (
            <>
              <button className="ghost" onClick={close} disabled={busy}>
                취소
              </button>
              <button onClick={() => void save()} disabled={busy || !dirty || noteOnly.length > 0}>
                {busy ? "저장 중…" : "저장"}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
