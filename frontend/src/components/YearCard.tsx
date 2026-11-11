import { useEffect, useState } from "react";
import { api } from "../api";
import { copyText, COPY_FAILED } from "../clipboard";
import { projectLink } from "../nav";
import { notifyError } from "../notify";
import type { DoneSummary, YearNumbers, YearReview } from "../types";
import { effectNumber } from "../util";

/**
 * 나의 한 해 (TODO 244 A3) — 이력 화면 위. 그 해에 맡은 과제 · 마친 과제 · 주관 · 내가 쓴 일지 · 보고 · 중간 성과 · 교육,
 * 새로 쓴 기술 · 도구, 마친 과제의 그 밖의 성과. 숫자 옆의 작은 글은 **나의 지난해** — 다른 사람과는 비교하지 않는다(242).
 */

const STATS: { key: keyof YearNumbers; label: string; unit: string }[] = [
  { key: "projects", label: "맡은 과제", unit: "건" },
  { key: "done", label: "마친 과제", unit: "건" },
  { key: "lead", label: "주관", unit: "건" },
  { key: "entries", label: "내가 쓴 일지", unit: "건" },
  { key: "reports", label: "보고에 올라감", unit: "번" },
  { key: "milestones", label: "중간 성과", unit: "건" },
  { key: "activities", label: "교육 · 행사", unit: "건" },
];

export function yearText(review: YearReview): string {
  const lines = [`■ ${review.year}년 — ${review.name}`];
  lines.push(
    STATS.map((stat) => `${stat.label} ${review[stat.key]}${stat.unit}`).join(" · ") +
      (review.hours ? ` (교육 ${review.hours}시간)` : ""),
  );
  if (review.done_projects.length) lines.push(`마친 과제: ${review.done_projects.map((item) => item.title).join(", ")}`);
  if (review.outcomes.length) {
    lines.push("그 밖의 성과:");
    for (const item of review.outcomes) lines.push(`  - ${item.title} — ${item.outcome}`);
  }
  if (review.new_skills.length) lines.push(`새로 쓴 기술 · 도구: ${review.new_skills.join(", ")}`);
  return lines.join("\n") + "\n";
}

export default function YearCard({ name, years }: { name: string; years: string[] }) {
  const thisYear = String(new Date().getFullYear());
  const choices = [...new Set([thisYear, ...years])].sort().reverse();
  // 처음엔 늘 올해 (TODO 269) — 다음 해에 시작하는 과제가 있어도 맨 위(가장 큰 해)가 아니라 오늘의 해. 사람을 바꾸면 다시 올해로
  const [year, setYear] = useState(thisYear);
  useEffect(() => setYear(thisYear), [name]); // eslint-disable-line react-hooks/exhaustive-deps
  const [review, setReview] = useState<YearReview | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setReview(null);
    api.yearReview(name, year).then(setReview).catch((err: Error) => notifyError(err.message));
  }, [name, year]);

  return (
    <div className="card year-card" data-year-card>
      <div className="card-head">
        <h2>
          <select value={year} onChange={(event) => setYear(event.target.value)} aria-label="나의 한 해 — 해 고르기" className="year-pick">
            {choices.map((item) => (
              <option key={item} value={item}>
                {item}년
              </option>
            ))}
          </select>
          나의 한 해
        </h2>
        <button
          className="ghost small"
          disabled={!review}
          onClick={async () => {
            if (!review) return;
            if (!(await copyText(yearText(review)))) return notifyError(COPY_FAILED);
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1500);
          }}
        >
          {copied ? "복사됨 ✓" : "한 해 글로 복사"}
        </button>
      </div>
      {!review ? (
        <p className="muted">불러오는 중…</p>
      ) : (
        <>
          <div className="year-stats">
            {STATS.map((stat) => (
              <div key={stat.key} className="year-stat">
                <span className="year-stat-label">{stat.label}</span>
                <strong>
                  {review[stat.key]}
                  <small>{stat.unit}</small>
                </strong>
                <span className="year-last" title={`${Number(year) - 1}년`}>
                  지난해 {review.last[stat.key]}
                </span>
              </div>
            ))}
          </div>
          {review.hours > 0 && <p className="hint">교육 · 행사 {review.hours}시간 (지난해 {review.last.hours}시간)</p>}
          {review.done_projects.length > 0 && (
            <p className="year-line">
              <span className="muted">마친 과제</span>
              {review.done_projects.map((item) => (
                <a key={item.id} href={projectLink(item.id)}>
                  {item.title}
                </a>
              ))}
            </p>
          )}
          {review.outcomes.length > 0 && (
            <ul className="year-outcomes">
              {review.outcomes.map((item) => (
                <li key={item.id}>
                  <b>{item.outcome}</b> <span className="muted">— {item.title}</span>
                </li>
              ))}
            </ul>
          )}
          {review.new_skills.length > 0 && (
            <div className="skill-chips">
              <span className="muted">새로 쓴 기술 · 도구</span>
              {review.new_skills.map((item) => (
                <span key={item} className="skill-chip">
                  {item}
                </span>
              ))}
            </div>
          )}
          {review.projects === 0 && review.activities === 0 && <p className="muted">이 해에 맡은 과제 · 교육 기록이 없습니다.</p>}
        </>
      )}
    </div>
  );
}

/** 마친 과제 띠 (TODO 244 A4) — 완료된 과제의 [담당과 역할] 위. 방금 완료로 바꿨으면 "수고하셨습니다" 로 강조 */
export function DoneCard({ summary, fresh }: { summary: DoneSummary; fresh: boolean }) {
  const parts = [
    summary.months ? `${summary.months}개월` : null,
    `일지 ${summary.entries}건`,
    summary.reports ? `보고 ${summary.reports}번` : null,
    `담당 ${summary.people}명`,
    summary.milestones ? `중간 성과 ${summary.milestones}건` : null,
    summary.effect_verified ? `실증 효과 ${effectNumber(summary.effect_verified)}억원/년` : null,
  ].filter(Boolean);
  return (
    <div className={fresh ? "done-card fresh" : "done-card"} data-done-card>
      <div className="done-card-head">
        <b>{fresh ? "과제를 마쳤습니다 — 수고하셨습니다" : "마친 과제"}</b>
        <span className="muted">
          {summary.start ?? "?"} ~ {summary.end ?? "?"}
        </span>
      </div>
      <div className="done-card-stats">{parts.join(" · ")}</div>
      {summary.outcome && <div className="done-card-outcome">{summary.outcome}</div>}
    </div>
  );
}
