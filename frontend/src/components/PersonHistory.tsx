import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { copyText, COPY_FAILED } from "../clipboard";
import { getMe } from "../me";
import { backTarget, projectLink, setPageTitle } from "../nav";
import { notifyError } from "../notify";
import { toTsv } from "../tsv";
import type { Meta, PersonHistory as History, PersonProject } from "../types";
import { effectText } from "../util";
import Explain from "./Explain";
import { RetroText } from "./RetroText";
import StatusBadge from "./StatusBadge";

/**
 * 사람별 이력 (TODO 238 ①) — 한 사람이 맡은(지금 · 예전) 과제를 **맡기 시작한 해**별로, 역할 · 담당 기간 · 회고 · 그 밖의 성과와 교육 · 행사 이력.
 *
 * 237 로 과제마다 쌓기 시작한 기록을 사람 기준으로 모아 본다. 누구나 본다(238-3) — 과제 상세 · 팀원역량에서 이미 보이는 것뿐이고 면담은 없다.
 * **이력 정리 복사**(238 ②) — 고른 과제를 글(문서 정리) 또는 표(엑셀)로. 금액은 넣지 않는다.
 */

function period(item: PersonProject): string {
  const end = item.to ?? (item.status === "dropped" ? "중단" : item.current ? "지금" : "?");
  return `${item.from ?? "?"} ~ ${end}`;
}

/**
 * 이력 채움 정도 (TODO 242 B1) — 역할 · 맡은 부분 · 기술 · 도구 · 회고 · 그 밖의 성과(끝난 과제만) 가운데 찬 칸.
 * 진행 중 과제의 회고 · 성과는 아직 쓸 때가 아니라 빈 칸으로 세지 않는다.
 */
export function fillOf(item: PersonProject): { filled: number; total: number } {
  const done = item.status === "done";
  const slots = [Boolean(item.role), Boolean(item.part), item.skills.length > 0, ...(done ? [hasRetro(item), Boolean(item.outcome)] : [])];
  return { filled: slots.filter(Boolean).length, total: slots.length };
}

type Gap = "" | "retro" | "skills" | "role" | "part";
const GAPS: { key: Exclude<Gap, "">; label: string; test: (item: PersonProject) => boolean }[] = [
  { key: "retro", label: "회고 빈 과제", test: (item) => item.status === "done" && !hasRetro(item) },
  { key: "skills", label: "기술 · 도구 빈 과제", test: (item) => item.skills.length === 0 },
  { key: "role", label: "역할 빈 과제", test: (item) => !item.role },
  { key: "part", label: "맡은 부분 빈 과제", test: (item) => !item.part },
];

function hasRetro(item: PersonProject): boolean {
  return Boolean(item.did || item.result);
}

const RETRO_LINES: { key: "did" | "result"; label: string }[] = [
  { key: "did", label: "내가 한 일" },
  { key: "result", label: "결과" },
];

/** 글로 — 과제마다 머리 한 줄 + 회고 · 성과 */
export function historyText(items: PersonProject[]): string {
  return items
    .map((item) => {
      const head = [`${item.title} (${period(item)})`, item.role, item.part].filter(Boolean).join(" · ");
      const lines = [`■ ${head}`];
      if (item.skills.length > 0) lines.push(`  - 기술 · 도구: ${item.skills.join(", ")}`);
      for (const line of RETRO_LINES) {
        const text = item[line.key].trim();
        if (!text) continue;
        // 여러 줄(글머리표)이면 아래로 들여 쓴다 (TODO 240) — 한 줄로 이으면 긴 글이 읽히지 않는다
        if (text.includes("\n")) lines.push(`  - ${line.label}:`, ...text.split("\n").filter((row) => row.trim()).map((row) => `      ${row.trim()}`));
        else lines.push(`  - ${line.label}: ${text}`);
      }
      if (item.outcome) lines.push(`  - 그 밖의 성과: ${item.outcome}`);
      return lines.join("\n");
    })
    .join("\n\n") + "\n";
}

export const HISTORY_HEADERS = ["과제 번호", "과제명", "기간", "역할", "맡은 부분", "기술 · 도구", "내가 한 일", "결과", "그 밖의 성과"];

export function historyRows(items: PersonProject[]): string[][] {
  return items.map((item) => [
    item.id, item.title, period(item), item.role, item.part, item.skills.join(", "), item.did, item.result, item.outcome,
  ]);
}

/**
 * 다듬기 프롬프트 (TODO 239 ③) — 고른 과제로 업무 이력 문장을 다듬어 달라는 글. **먼저 보여 주고** 복사한다(71 과 같은 원칙).
 * 사람 이름 · 효과 금액은 넣지 않는다. 기록에 없는 내용 · 숫자를 만들지 말라고 적는다.
 */
export function refinePrompt(items: PersonProject[]): string {
  const head = [
    "아래는 한 사람이 맡았던 과제의 기록입니다. 업무 이력 · 성과 정리에 쓸 문장으로 다듬어 주세요.",
    "",
    "[부탁]",
    "- 과제마다 2~3줄로, 무엇을 · 어떻게 · 결과(숫자)가 드러나게 써 주세요.",
    "- 기록에 없는 내용이나 숫자는 만들지 마세요. 모르는 것은 비워 두세요.",
    "- 사내 시스템 이름 · 금액 · 다른 사람 이름은 쓰지 마세요.",
    "- 문장 끝은 \"~함 · ~했음\" 같은 짧은 개조식으로 써 주세요.",
    "",
    "[기록]",
  ];
  const body = items.map((item, index) => {
    const lines = [`${index + 1}. 과제: ${item.title} (${period(item)})`];
    const facts = [item.role && `역할: ${item.role}`, item.part && `맡은 부분: ${item.part}`,
      item.skills.length > 0 && `기술 · 도구: ${item.skills.join(", ")}`].filter(Boolean);
    if (facts.length > 0) lines.push(`   ${facts.join(" / ")}`);
    for (const line of RETRO_LINES) if (item[line.key]) lines.push(`   ${line.label}: ${item[line.key].replace(/\s*\n\s*/g, " / ")}`);
    if (item.outcome) lines.push(`   그 밖의 성과: ${item.outcome}`);
    return lines.join("\n");
  });
  return [...head, ...body].join("\n") + "\n";
}

export default function PersonHistory({ meta, name, back }: { meta: Meta; name: string; back: string | null }) {
  const [data, setData] = useState<History | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [year, setYear] = useState("all");
  // 빈 칸 거르기 (TODO 242 B1)
  const [gap, setGap] = useState<Gap>("");
  // 고른 과제 — 처음에는 회고를 적은 과제 전부
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [copied, setCopied] = useState<string | null>(null);
  // 다듬기 프롬프트 — 열면 고른 과제로 만든 글을 먼저 보인다 (TODO 239 ③)
  const [showPrompt, setShowPrompt] = useState(false);

  useEffect(() => {
    setPageTitle(`${name} — 이력`);
    api
      .personHistory(name)
      .then((loaded) => {
        setData(loaded);
        setPicked(new Set(loaded.projects.filter(hasRetro).map((item) => item.id)));
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  }, [name]);

  const years = useMemo(() => [...new Set((data?.projects ?? []).map((item) => item.year))].sort().reverse(), [data]);
  const gapTest = GAPS.find((item) => item.key === gap)?.test;
  const shown = useMemo(
    () => (data?.projects ?? []).filter((item) => (year === "all" || item.year === year) && (!gapTest || gapTest(item))),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data, year, gap],
  );
  const chosen = shown.filter((item) => picked.has(item.id));
  const me = getMe();
  const mine = (me.role === "member" && me.name === name) || (me.role === "owner" && meta.leader === name);
  const canWrite = me.role === "owner" || mine;
  const kindLabel = (key: string) => meta.activity_kinds.find((item) => item.key === key)?.label ?? key;

  async function copy(kind: "text" | "table" | "prompt") {
    if (chosen.length === 0) return;
    const text =
      kind === "text" ? historyText(chosen) : kind === "table" ? toTsv(HISTORY_HEADERS, historyRows(chosen)) : refinePrompt(chosen);
    const ok = await copyText(text);
    if (!ok) {
      notifyError(COPY_FAILED);
      return;
    }
    setCopied(kind);
    window.setTimeout(() => setCopied(null), 1500);
  }

  const toggle = (id: string) =>
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  if (error) return <section className="person-history"><div className="card"><p className="error">{error}</p></div></section>;
  if (!data) return <section className="person-history"><p className="muted">불러오는 중…</p></section>;

  const groups = years
    .filter((item) => year === "all" || item === year)
    .map((item) => ({ year: item, items: shown.filter((project) => project.year === item) }));

  return (
    <section className="person-history">
      <a className="back" href={backTarget(back).href}>
        ← {backTarget(back).label}
      </a>
      <div className="card person-head">
        <h1>
          {data.name}
          {data.leader && <span className="tag leader-tag">팀장</span>}
          {data.left_on && <span className="tag left-tag">떠남 {data.left_on}</span>}
          <span className="muted person-head-sub"> — 이력</span>
        </h1>
        {data.skills.length > 0 && (
          <div className="skill-chips person-top-skills" title="많이 쓴 기술 · 도구 — 숫자는 과제 수">
            <span className="muted">많이 쓴 기술 · 도구</span>
            {data.skills.map((item) => (
              <span key={item.name} className="skill-chip">
                {item.name}
                {item.count > 1 && <span className="skill-count">{item.count}</span>}
              </span>
            ))}
          </div>
        )}
        <div className="person-stats">
          <span><b>{data.summary.projects}</b> 과제</span>
          <span><b>{data.summary.current}</b> 진행 중</span>
          <span><b>{data.summary.lead}</b> 주관</span>
          <span title="끝난 과제 가운데 회고를 적은 것">회고 <b>{data.summary.retro_written}</b> / {data.summary.done}</span>
          <span><b>{data.summary.activities}</b> 교육 · 행사</span>
          {/* 보고에 올라간 내 과제 (TODO 242 A1) — 비교는 나의 지난해와만 */}
          <span title="확정한 보고에 내 과제가 올라간 횟수">
            올해 보고 <b>{data.summary.reports_this_year ?? 0}</b>번
            {(data.summary.reports_last_year ?? 0) > 0 && <span className="muted"> · 지난해 {data.summary.reports_last_year}번</span>}
          </span>
        </div>
        {/* 채울 칸 (TODO 242 B1) — 누르면 그 과제만 */}
        {GAPS.some((item) => data.projects.some(item.test)) && (
          <div className="gap-bar">
            <span className="muted">채울 칸</span>
            {GAPS.map((item) => {
              const count = data.projects.filter(item.test).length;
              return count > 0 ? (
                <button
                  key={item.key}
                  type="button"
                  className={gap === item.key ? "gap-chip on" : "gap-chip"}
                  aria-pressed={gap === item.key}
                  onClick={() => setGap(gap === item.key ? "" : item.key)}
                >
                  {item.label} {count}
                </button>
              ) : null;
            })}
            {gap && (
              <button type="button" className="linkish" onClick={() => setGap("")}>
                모두 보기
              </button>
            )}
          </div>
        )}
        <Explain
          id="person-history"
          lead={<>맡았던 과제(지금 · 예전)를 <b>맡기 시작한 해</b>별로 모았습니다. 과제를 골라 <b>[글로 복사]</b> · <b>[표로 복사]</b>로 업무 이력 · 성과를 정리할 수 있습니다.</>}
        >
          역할 · 맡은 부분 · 회고는 과제 상세의 [담당과 역할]에서 적습니다. 복사에는 효과 금액을 넣지 않습니다. 면담 기록은 여기에 나오지 않습니다.
          {data.summary.entry_only > 0 && <> 담당은 아니지만 진행일지를 쓴 과제가 {data.summary.entry_only}건 더 있습니다.</>}
        </Explain>
      </div>

      <div className="card person-projects">
        <div className="card-head">
          <h2>맡은 과제 {shown.length}건</h2>
          <div className="person-tools">
            <label className="inline-label">
              맡기 시작한 해
              <select value={year} onChange={(event) => setYear(event.target.value)} aria-label="맡기 시작한 해">
                <option value="all">전체</option>
                {years.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <span className="muted">{chosen.length}건 고름</span>
            <button className="ghost" disabled={chosen.length === 0} onClick={() => void copy("text")}>
              {copied === "text" ? "복사됨 ✓" : "글로 복사"}
            </button>
            <button className="ghost" disabled={chosen.length === 0} onClick={() => void copy("table")}>
              {copied === "table" ? "복사됨 ✓" : "표로 복사"}
            </button>
            <button
              className={showPrompt ? "ghost on" : "ghost"}
              disabled={chosen.length === 0}
              aria-expanded={showPrompt}
              onClick={() => setShowPrompt((value) => !value)}
              title="고른 과제로 업무 이력 문장을 다듬어 달라는 글을 만듭니다 — 먼저 보고 복사합니다"
            >
              다듬기 프롬프트
            </button>
          </div>
        </div>
        {showPrompt && chosen.length > 0 && (
          <div className="refine-panel">
            <p className="hint">
              사내 AI 에 붙여넣을 글입니다 — <b>무엇이 담기는지 읽어 보고</b> 복사하세요. 이름 · 효과 금액은 넣지 않았습니다. 과제명에 대외비가 있으면 고친 뒤 붙이세요.
            </p>
            <textarea className="refine-text" readOnly value={refinePrompt(chosen)} aria-label="다듬기 프롬프트" />
            <div className="form-actions">
              <button onClick={() => void copy("prompt")}>{copied === "prompt" ? "복사됨 ✓" : "복사"}</button>
            </div>
          </div>
        )}
        {shown.length === 0 ? (
          <p className="muted">맡은 과제가 없습니다.</p>
        ) : (
          groups.map((group) => (
            <div key={group.year} className="person-year">
              <h3>{group.year}</h3>
              <ul className="person-project-list">
                {group.items.map((item) => {
                  const effect = item.no_effect ? null : effectText(item.effect_expected, item.effect_verified);
                  return (
                    <li key={item.id} className={item.current ? "person-project" : "person-project former"} data-project={item.id}>
                      <div className="person-project-head">
                        <input
                          type="checkbox"
                          checked={picked.has(item.id)}
                          onChange={() => toggle(item.id)}
                          aria-label={`${item.title} 고르기`}
                        />
                        <StatusBadge status={item.status} meta={meta} />
                        <a href={projectLink(item.id)} className="person-project-title">{item.title}</a>
                        <span className="muted">{item.id}</span>
                        <span className="grow" />
                        {(item.reports ?? 0) > 0 && <span className="report-count" title="확정한 보고에 올라간 횟수">보고 {item.reports}회</span>}
                        {(() => {
                          const fill = fillOf(item);
                          return (
                            <span className={fill.filled === fill.total ? "fill-chip full" : "fill-chip"} title="역할 · 맡은 부분 · 기술 · 도구 · (끝난 과제는) 회고 · 그 밖의 성과 가운데 찬 칸">
                              채움 {fill.filled}/{fill.total}
                            </span>
                          );
                        })()}
                        <span className="contrib-period">{period(item)}{item.derived && <span className="muted"> · 시작일부터</span>}</span>
                      </div>
                      <div className="person-project-meta">
                        <span className={item.role ? undefined : "muted"}>{item.role || "역할 미정"}</span>
                        {item.part && <span>{item.part}</span>}
                        {item.skills.map((skill) => (
                          <span key={skill} className="skill-chip">{skill}</span>
                        ))}
                        {!item.current && <span className="tag former-tag">예전 담당</span>}
                        {item.outcome && <span>그 밖의 성과 · {item.outcome}</span>}
                        {effect && <span className="muted">효과 {effect.text}{effect.verified ? "" : " · 기대"}</span>}
                      </div>
                      {item.praise && (
                        <p className="praise-line">
                          <span className="praise-label">팀장</span>“{item.praise}”
                          {item.praise_at && <span className="muted"> · {item.praise_at}</span>}
                        </p>
                      )}
                      {hasRetro(item) ? (
                        <dl className="contrib-retro">
                          {RETRO_LINES.map((line) =>
                            item[line.key] ? (
                              <div key={line.key}>
                                <dt>{line.label}</dt>
                                <dd><RetroText text={item[line.key]} /></dd>
                              </div>
                            ) : null,
                          )}
                        </dl>
                      ) : item.status === "done" ? (
                        <p className="person-retro-missing">
                          회고 비어 있음
                          {canWrite && (
                            <a href={projectLink(item.id, mine ? { retro: "me" } : {})}>
                              {mine ? " · 적기 →" : " · 과제에서 적기 →"}
                            </a>
                          )}
                        </p>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            </div>
          ))
        )}
      </div>

      <div className="card person-activities">
        <h2>교육 · 행사 {data.activities.length}건</h2>
        {data.activities.length === 0 ? (
          <p className="muted">팀원역량에 적은 기록이 없습니다.</p>
        ) : (
          <ul className="home-stale person-activity-list">
            {data.activities.map((item) => (
              <li key={item.id}>
                <span className="due">{item.end_date ? `${item.date} ~ ${item.end_date}` : item.date}</span>
                {item.planned && <span className="tag">예정</span>}
                <b>{item.title}</b>
                <span className="muted">
                  {kindLabel(item.kind)}
                  {item.host ? ` · ${item.host}` : ""}
                  {item.hours ? ` · ${item.hours}시간` : ""}
                </span>
                {item.takeaway && <span className="person-takeaway">{item.takeaway}</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
