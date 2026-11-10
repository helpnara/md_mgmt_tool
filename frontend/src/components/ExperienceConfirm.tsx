import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import type { ConsistencyWarning, Experience, ExperienceQuant } from "../types";
import IconTitle from "./IconTitle";

/**
 * 4단계 부품 (TODO 260 · 253 의 4단계, 원본 UX S-05) — 경험 상세가 쓴다.
 *
 * * [확정하기 (조건 n개 남음)] — 꺼진 회색으로만 두지 않는다. 누르면 남은 조건을 펼친다.
 * * 확인 필요 질문마다 답 · 반영할 곳 · [반영] · [해당 없음](원본 FR-C8).
 * * 정합성 경고마다 [확인함](원본 FR-F2 — 누가 · 언제를 남긴다).
 */

/** [반영] 할 곳 — 칸 이름 또는 `quant:<번호>`(그 정량의 기준) */
export type AnswerTarget = string;

const TEXT_TARGETS: [string, string][] = [
  ["result_qual", "결과(정성)"], ["role", "역할"], ["situation", "상황"], ["goal", "목표"], ["actions", "행동(새 줄)"],
  ["impact", "업무 영향"], ["lesson", "교훈"],
];

/** 질문 글에서 반영할 곳을 짐작한다(원본 S-05 — "기본값은 질문 문장에서 추정") */
export function guessTarget(question: string, quants: ExperienceQuant[]): AnswerTarget {
  if (/기준/.test(question) && quants.length) {
    const hit = quants.findIndex((q) => q.metric && question.includes(q.metric));
    const byValue = quants.findIndex((q) => q.value && question.includes(q.value));
    return `quant:${hit >= 0 ? hit : byValue >= 0 ? byValue : 0}`;
  }
  if (/몫|기여/.test(question)) return "result_qual";
  if (/역할|직접|주체|수행/.test(question)) return "role";
  if (/상황|배경/.test(question)) return "situation";
  if (/목표/.test(question)) return "goal";
  if (/교훈|배운/.test(question)) return "lesson";
  return "result_qual";
}

/** 답에서 기준 종류를 짐작 — 1단계 파서의 낱말과 같게. 모르면 미확인(사람이 고른다) */
export function guessKind(text: string): ExperienceQuant["baseline_kind"] {
  if (/대비|기존|전년|이전|→|비교|보다/.test(text)) return "비교";
  if (/누적|연간|총|정원|건수|합계|월간|평균/.test(text)) return "집계";
  if (/가정|조건|환산|주간|격주|개월|기간/.test(text)) return "조건";
  return "미확인";
}

export function ConfirmBar({ item, dirty, busy, onConfirm, onUnconfirm }: {
  item: Experience;
  dirty: boolean;
  busy: boolean;
  onConfirm: () => void;
  onUnconfirm: () => void;
}) {
  const [open, setOpen] = useState(false);
  if (item.status === "확정") {
    return (
      <span className="exp-confirm-bar">
        <span className="muted">확정 {item.confirmed_at.slice(0, 10)}{item.confirmed_by ? ` (${item.confirmed_by})` : ""}</span>
        <button className="ghost" disabled={busy} onClick={onUnconfirm}>구조화로 되돌림</button>
      </span>
    );
  }
  const left = item.confirm_missing.length;
  return (
    <span className="exp-confirm-bar">
      <button className={left ? "ghost" : ""} disabled={busy} aria-expanded={left ? open : undefined}
        title={dirty ? "고친 것을 먼저 저장하세요" : left ? "누르면 남은 조건을 봅니다" : "확정합니다 — 업무 이력 파일에 들어갑니다(5단계)"}
        onClick={() => (left ? setOpen((value) => !value) : dirty ? undefined : onConfirm())}>
        {left ? `확정하기 (조건 ${left}개 남음)` : "확정하기"}
      </button>
      {left > 0 && open && (
        <ul className="exp-missing" data-testid="confirm-missing">
          {item.confirm_missing.map((reason) => <li key={reason}>{reason}</li>)}
        </ul>
      )}
      {!left && dirty && <span className="form-warn">고친 것을 먼저 저장하세요</span>}
    </span>
  );
}

export function QuestionAnswers({ questions, quants, editable, onApply, onDrop }: {
  questions: string[];
  quants: ExperienceQuant[];
  editable: boolean;
  onApply: (question: string, answer: string, target: AnswerTarget) => void;
  onDrop: (question: string) => void;
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [targets, setTargets] = useState<Record<string, AnswerTarget>>({});
  if (!editable || questions.length === 0) return null;
  return (
    <ol className="exp-answers">
      {questions.map((question) => {
        const target = targets[question] ?? guessTarget(question, quants);
        const answer = answers[question] ?? "";
        return (
          <li key={question} data-question={question}>
            <span className="exp-question">{question}</span>
            <span className="exp-answer-row">
              <input aria-label="답" placeholder="답" value={answer} onChange={(event) => setAnswers({ ...answers, [question]: event.target.value })} />
              <select aria-label="반영할 곳" value={target} onChange={(event) => setTargets({ ...targets, [question]: event.target.value })}>
                {quants.map((q, index) => <option key={`q${index}`} value={`quant:${index}`}>정량 기준 — {q.metric || `${index + 1}번`}</option>)}
                {TEXT_TARGETS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
              <button type="button" className="ghost small" disabled={!answer.trim()} onClick={() => onApply(question, answer.trim(), target)}>반영</button>
              <button type="button" className="ghost small" onClick={() => onDrop(question)} title="질문만 지웁니다 — 이전 버전에 남습니다">해당 없음</button>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export function ConsistencyCard({ warnings, editable, busy, onAck }: {
  warnings: ConsistencyWarning[];
  editable: boolean;
  busy: boolean;
  onAck: (warning: ConsistencyWarning) => void;
}) {
  if (warnings.length === 0) return null;
  const open = warnings.filter((w) => !w.acknowledged).length;
  return (
    <div className={open ? "card experience-consistency has" : "card experience-consistency"} data-testid="consistency">
      <IconTitle icon={ShieldCheck}>정합성 경고 {open}건{warnings.length > open ? ` · 확인함 ${warnings.length - open}` : ""}</IconTitle>
      <p className="hint">저장은 막지 않고 확정만 막습니다 — 고치거나, 맞는 내용이면 [확인함]으로 넘깁니다. 내용이 바뀌면 다시 묻습니다.</p>
      <ul className="exp-consistency-list">
        {warnings.map((w) => (
          <li key={`${w.code}|${w.key}`} className={w.acknowledged ? "done" : ""} data-code={w.code}>
            <span className="exp-code">{w.code}</span>
            <span className="exp-consistency-text">{w.message}</span>
            {w.acknowledged ? (
              <span className="muted">확인함 {w.ack_at.slice(0, 10)}{w.ack_by ? ` (${w.ack_by})` : ""}</span>
            ) : (
              editable && <button type="button" className="ghost small" disabled={busy} onClick={() => onAck(w)}>확인함</button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
