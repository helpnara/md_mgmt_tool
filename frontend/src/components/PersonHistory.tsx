import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { copyText, COPY_FAILED } from "../clipboard";
import { getMe, isManager, isMember } from "../me";
import { backTarget, projectLink, setPageTitle } from "../nav";
import { notifyError } from "../notify";
import { toTsv } from "../tsv";
import type { Meta, PersonHistory as History, PersonProject } from "../types";
import { effectText } from "../util";
import Explain from "./Explain";
import { RetroText } from "./RetroText";
import { ContributionForm } from "./ContributionsCard";
import YearCard from "./YearCard";
import type { Project } from "../types";
import StatusBadge from "./StatusBadge";
import ExperienceCard, { experienceLink } from "./ExperienceCard";

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
 * 업무 이력 · 성과 정리 프롬프트 — STAR (TODO 244 B6, 239 ③ 을 고도화). 241 실험의 v2 를 화면 자료로 옮겼다.
 * **먼저 보여 주고** 복사한다(71 과 같은 원칙). 사람 이름 · 효과 금액은 넣지 않는다 — 기록에 없는 숫자를 만들지 말라고 적는다.
 * 고른 과제가 여럿이면 과제마다 한 묶음씩 정리해 달라고 한다(사람 · 숫자가 섞이지 않게).
 */
export function refinePrompt(items: PersonProject[]): string {
  const head = [
    "[역할]",
    "당신은 제조 · 데이터 분석 업무를 잘 아는 업무 성과 정리 코치입니다.",
    "아래 [기록]은 사내 과제 관리 도구에 한 사람이 남긴 과제 기록입니다. 이 사람이 직접 한 일을 STAR(상황 · 과제 · 행동 · 결과)로 정리해 주세요.",
    items.length > 1 ? `과제가 ${items.length}개입니다 — 과제마다 아래 [출력 형식]을 한 묶음씩 따로 써 주세요.` : "",
    "",
    "[기록 읽는 법]",
    "- 배경 → S(상황), 목표 → T(과제). 역할 · 맡은 부분 · 내가 한 일 → A(행동). 결과 · 중간 성과 · 그 밖의 성과 → R(결과).",
    "- 성과 후보 일지는 본인이 성과로 표시한 진행일지입니다. 행동 · 결과의 근거로 쓰세요.",
    "- 기간이 '~ 지금'이면 진행 중인 과제입니다. 끝난 성과처럼 쓰지 마세요.",
    "",
    "[반드시 지킬 것]",
    "1. 기록에 있는 사실과 숫자만 씁니다. 숫자를 만들거나 부풀리지 않습니다. 필요한데 없는 숫자는 [확인 필요]에 적습니다.",
    "2. 결과는 가능하면 전 → 후(건수 · % · 시간)로. 비율을 계산했다면 계산식을 [확인 필요]에 함께 적습니다.",
    "3. 팀 성과와 본인 몫을 가릅니다. 팀 결과를 쓸 때는 \"팀 성과 중 본인 담당: …\" 처럼 본인 몫을 밝힙니다.",
    "4. 사람 이름 · 부서명 · 라인 번호 · 사내 시스템명은 일반화합니다(예: \"냉연 2라인\" → \"냉연 공정 라인\"). 금액은 쓰지 않습니다.",
    "5. 업무 나열이 아니라 성과 중심으로. \"~ 담당\" · \"~ 참여\" 로 끝나는 불릿, \"기여함\" · \"효과가 있었다\" 같은 막연한 말은 쓰지 않습니다.",
    "6. 불릿은 명사형 개조식(~구축, ~단축, ~달성), 한 줄 50~80자, 과제당 3~5개. 형식은 \"[무엇을] [어떻게(방법 · 도구)] → [결과(수치)]\".",
    "",
    "[출력 형식] — 마크다운으로, 과제마다",
    "1. 한 줄 요약 (50자 이내 — 무엇을 해서 어떤 숫자를 바꿨는지)",
    "2. 머리 표 (프로젝트명 · 기간 · 역할 · 기술 · 도구)",
    "3. STAR 표 (단계 | 내용 1~2줄 | 근거 — 기록의 어느 칸)",
    "4. 불릿 3~5개",
    "5. 말로 설명할 때 (60~90초 분량, 말하듯이)",
    "6. 확인 필요 (기록만으로 확정할 수 없는 것 · 계산한 비율의 식 · 일반화한 이름)",
    "",
    "[출력 전 점검] 모든 숫자가 기록에 있는가 · 남의 일을 본인 행동으로 쓰지 않았는가 · 이름 · 금액이 남지 않았는가 · 불릿이 \"~담당 · ~참여\" 로 끝나지 않는가",
    "",
    "[기록]",
  ].filter((line, index, all) => line !== "" || all[index - 1] !== "");
  const body = items.map((item, index) => {
    const lines = [`## 과제 ${index + 1}. ${item.title}`, `- 기간: ${period(item)}${item.status === "done" ? " (완료)" : ""}`];
    if (item.context?.background) lines.push(`- 배경: ${item.context.background}`);
    if (item.context?.goal) lines.push(`- 목표: ${item.context.goal}`);
    if (item.role) lines.push(`- 역할: ${item.role}`);
    if (item.part) lines.push(`- 맡은 부분: ${item.part}`);
    if (item.skills.length > 0) lines.push(`- 기술 · 도구: ${item.skills.join(", ")}`);
    if ((item.milestones?.length ?? 0) > 0) {
      lines.push("- 중간 성과:");
      for (const m of item.milestones!) lines.push(`  - ${m.date} ${m.text}`);
    }
    if ((item.star_entries?.length ?? 0) > 0) {
      lines.push("- 성과 후보 일지:");
      for (const e of item.star_entries!) lines.push(`  - ${e.date} ${e.title}${e.first_line ? ` — ${e.first_line}` : ""}`);
    }
    for (const line of RETRO_LINES) {
      const text = item[line.key].trim();
      if (!text) continue;
      if (text.includes("\n")) lines.push(`- ${line.label}:`, ...text.split("\n").filter((row) => row.trim()).map((row) => `  ${row.trim().startsWith("- ") ? row.trim() : `- ${row.trim()}`}`));
      else lines.push(`- ${line.label}: ${text}`);
    }
    if (item.outcome) lines.push(`- 그 밖의 성과: ${item.outcome}`);
    return lines.join("\n");
  });
  return [...head, ...body].join("\n").replace(/\n{3,}/g, "\n\n") + "\n";
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
  // STAR 정리 프롬프트 — 열면 고른 과제로 만든 글을 먼저 보인다 (TODO 239 ③ · 244 B6)
  const [showPrompt, setShowPrompt] = useState(false);
  // 이력 화면에서 바로 고치기 (TODO 243 B4) — 과제를 받아 와 같은 양식을 그 자리에 연다
  const [editing, setEditing] = useState<{ id: string; project: Project } | null>(null);
  // 경험 (TODO 257) — 경험이 이미 있는 과제(그 과제 줄에는 [경험 초안] 을 세우지 않는다)
  const [expProjects, setExpProjects] = useState<Set<string> | null>(null);
  const [expReload, setExpReload] = useState(0);
  const [drafting, setDrafting] = useState<string | null>(null);
  async function draftOne(projectId: string) {
    setDrafting(projectId);
    try {
      const result = await api.draftExperiences(name, [projectId]);
      if (result.made.length) window.location.hash = experienceLink(result.made[0]);
      else setExpReload((n) => n + 1);
    } catch (error) {
      notifyError((error as Error).message);
    } finally {
      setDrafting(null);
    }
  }
  const [opening, setOpening] = useState<string | null>(null);

  async function openEdit(id: string) {
    setOpening(id);
    try {
      setEditing({ id, project: await api.getProject(id) });
    } catch (err) {
      notifyError((err as Error).message);
    } finally {
      setOpening(null);
    }
  }

  function reload() {
    api.personHistory(name).then((loaded) => setData(loaded)).catch((err: Error) => notifyError(err.message));
  }

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
  const mine = (me.role === "member" && me.name === name) || (isManager(me) && meta.leader === name);
  const canWrite = isManager(me) || mine;
  const canEditRow = (id: string) => isManager(me) || (mine && me.projects.includes(id));
  // 팀원 PC 의 **자기** 이력 (TODO 243 B4) — 과제 상세(233)처럼 이 화면에서만 읽기 전용을 풀어 [적기] 가 보이게.
  // 팀장 단추([data-owner-only])는 그대로 숨는다. 숨기는 것은 편의 — 막는 것은 서버(자기 줄만, 담당 과제만)
  const memberOwn = me.role === "member" && mine && me.projects.length > 0;
  useEffect(() => {
    if (!memberOwn) return;
    document.body.classList.remove("readonly");
    document.body.classList.add("member-editing");
    return () => {
      document.body.classList.add("readonly");
      document.body.classList.remove("member-editing");
    };
  }, [memberOwn]);
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

      {/* 271 — 경험이 맨 위: 정리해 낸 결론이고, 아래(나의 한 해 · 과제 · 교육)는 그 근거다(사용자 2026-11-11) */}
      {/* 팀원별 경험 (TODO 257) — 관리자 · 팀장, 그리고 팀원 PC 의 자기 이력에서만. 읽기 전용 공유 바깥에는 없다(면담과 같은 결) */}
      {(isManager(me) || (isMember() && me.name === name)) && (
        <ExperienceCard
          name={name}
          retroProjects={data.projects.filter((item) => hasRetro(item)).map((item) => item.id)}
          reloadKey={expReload}
          onChanged={(listing) => setExpProjects(new Set(listing.items.map((item) => item.project).filter(Boolean)))}
        />
      )}

      {/* 나의 한 해 (TODO 244 A3) */}
      <YearCard name={data.name} years={[...years, ...data.activities.map((item) => item.date.slice(0, 4))]} />

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
              title="고른 과제를 STAR(상황 · 과제 · 행동 · 결과)로 정리해 달라는 글을 만듭니다 — 먼저 보고 복사합니다"
            >
              STAR 정리 프롬프트
            </button>
          </div>
        </div>
        {showPrompt && chosen.length > 0 && (
          <div className="refine-panel">
            <p className="hint">
              사내 AI 에 붙여넣을 글입니다 — <b>무엇이 담기는지 읽어 보고</b> 복사하세요. 이름 · 효과 금액은 넣지 않았습니다. 과제명에 대외비가 있으면 고친 뒤 붙이세요.
            </p>
            <textarea className="refine-text" readOnly value={refinePrompt(chosen)} aria-label="STAR 정리 프롬프트" />
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
                        {isManager(me) && expProjects !== null && !expProjects.has(item.id) && (
                          <button className="ghost small" disabled={drafting === item.id} onClick={() => void draftOne(item.id)}
                            title="이 과제의 담당과 역할 · 회고 · 개요 · 효과 금액으로 경험 초안을 만듭니다 (TODO 257)">
                            {drafting === item.id ? "만드는 중…" : "경험 초안"}
                          </button>
                        )}
                        {canEditRow(item.id) && editing?.id !== item.id && (
                          <button data-write className="ghost small" disabled={opening === item.id} onClick={() => void openEdit(item.id)}>
                            {opening === item.id ? "여는 중…" : item.role || item.part || hasRetro(item) ? "고치기" : "적기"}
                          </button>
                        )}
                      </div>
                      {(item.milestones?.length ?? 0) > 0 && editing?.id !== item.id && (
                        <ul className="milestone-list">
                          {item.milestones!.map((m) => (
                            <li key={`${m.date}-${m.text}`}><span className="due">{m.date}</span>{m.text}</li>
                          ))}
                        </ul>
                      )}
                      {editing?.id === item.id && (() => {
                        const row = (editing.project.contributions ?? []).find((c) => c.name === name);
                        return row ? (
                          <ContributionForm
                            project={editing.project}
                            row={row}
                            ownerView={isManager(me)}
                            praiseEditable={isManager(me) && !data.leader}
                            justDone={false}
                            onCancel={() => setEditing(null)}
                            onSaved={() => {
                              setEditing(null);
                              reload();
                            }}
                          />
                        ) : (
                          <p className="error">이 과제의 담당자 줄을 찾지 못했습니다 — 담당자가 바뀌었을 수 있습니다.</p>
                        );
                      })()}
                      <div className="person-project-meta" hidden={editing?.id === item.id}>
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
                      {editing?.id === item.id ? null : hasRetro(item) ? (
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
                          {canEditRow(item.id) ? (
                            <button type="button" className="linkish" onClick={() => void openEdit(item.id)}> · 적기</button>
                          ) : canWrite ? (
                            <a href={projectLink(item.id, { retro: "me" })}> · 과제에서 적기 →</a>
                          ) : null}
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
