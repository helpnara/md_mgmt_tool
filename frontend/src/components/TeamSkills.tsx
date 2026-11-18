import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../api";
import { notifyError } from "../notify";
import type { Meta, TeamSkillTarget, TeamSkillTool, TeamSkills as Data } from "../types";
import { experienceLink, personLink, projectLink } from "../nav";
import { axisLabel } from "../util";
import CopyTableButton from "./CopyTableButton";
import { PlanTag, SnapshotBar, SnapshotCompareLine, SuccessionCard, useSuccession } from "./TeamPlans";
import type { PlanSeed } from "./TeamPlans";
import type { SuccessionPlan } from "../types";

/**
 * 팀 역량 · 기술 스택 (TODO 284 · 290) — 팀원역량 → [팀 역량] 탭(팀장 · 관리자만).
 *
 * 291 — 팀장의 질문 여섯에 답하는 카드(강점 · 빈 곳 · 위험 · 변화 · 성장 · 할 일, 번호 없음) + 한 줄 결론 · 숫자 다섯.
 * 290 의 표 · 막대 · 지도는 "근거 자료"(접힘)로 — 카드의 [근거 보기]가 펼쳐 그 자리로 간다.
 * (290 — 팀장이 한눈에: **요약 → 변동 → 모양 → 위험 → 자세히** 순서(번호 = 화면 순서).
 * 1 한눈에(숫자 다섯 · 인사이트 문장) 2 지난해와 비교(중분류 지난해 → 올해 · 새로 생김 · 늘어남 · 줄어듦 · 끊김 · 축마다 다섯 해)
 * 3 팀 모양(축별 막대 | 기술 스택, 반반) 4 위험 · 빈 곳(한 사람에게만 | 목표, 반반) 5 역량 지도(중분류 줄 — 눌러 펼침)
 * ▸ 자세히 보기(과제 분류 × 역량 · 처음 나온 해) ▸ 데이터 점검(완성도). 세는 경험은 구조화 · 확정, 칸 = 경험 수(수준 · Lv 아님).)
 */
const PERIODS: { key: Data["period"]; label: string }[] = [
  { key: "year", label: "올해" },
  { key: "3y", label: "최근 3년" },
  { key: "all", label: "전체" },
];

const level = (n: number) => (n >= 5 ? 4 : n >= 3 ? 3 : n >= 2 ? 2 : n >= 1 ? 1 : 0);
const letter = (i: number) => (i < 26 ? String.fromCharCode(65 + i) : `${String.fromCharCode(65 + Math.floor(i / 26) - 1)}${String.fromCharCode(65 + (i % 26))}`);
const delta = (n: number) => (n > 0 ? <span className="ts-up">▲{n}</span> : n < 0 ? <span className="ts-down">▼{-n}</span> : <span className="muted">–</span>);

export default function TeamSkills({ meta }: { meta: Meta }) {
  const [period, setPeriod] = useState<Data["period"]>("year");
  const [left, setLeft] = useState(false);
  const [mask, setMask] = useState(false);
  const [data, setData] = useState<Data | null>(null);
  const [printing, setPrinting] = useState(false);
  // 291 — 인쇄는 질문 카드 여섯 한 장, 근거 자료는 고를 때만
  const [printEvidence, setPrintEvidence] = useState(false);
  // 292 B — 승계 · 짝 계획(위험 카드의 [계획으로]가 채워 둔 새 계획)
  const [succession, loadSuccession] = useSuccession();
  const [seed, setSeed] = useState<PlanSeed | null>(null);

  const load = () => api.teamSkills(period, left).then(setData).catch((error: Error) => notifyError(error.message));
  useEffect(() => { void load(); }, [period, left]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!printing) return;
    document.body.classList.add("ts-printing");
    const done = () => { document.body.classList.remove("ts-printing"); setPrinting(false); };
    window.addEventListener("afterprint", done, { once: true });
    const timer = window.setTimeout(() => window.print(), 300);
    return () => { window.clearTimeout(timer); window.removeEventListener("afterprint", done); document.body.classList.remove("ts-printing"); };
  }, [printing]);

  const names = data?.people.map((p) => p.name) ?? [];
  const show = (name: string) => (mask ? `팀원 ${letter(names.indexOf(name) < 0 ? names.length : names.indexOf(name))}` : name);
  const held = data?.skills.filter((r) => r.holders > 0) ?? [];
  const periodLabel = PERIODS.find((p) => p.key === period)?.label ?? "";

  return (
    <div className="team-skills" data-testid="team-skills">
      <div className="card ts-headcard">
        <div className="card-head">
          <h2>팀 역량 · 기술 스택</h2>
          <div className="person-tools ts-tools">
            <label className="check-label">범위
              <select aria-label="기간" value={period} onChange={(e) => setPeriod(e.target.value as Data["period"])}>
                {PERIODS.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
              </select>
            </label>
            <label className="check-label"><input type="checkbox" checked={left} onChange={(e) => setLeft(e.target.checked)} /> 떠난 사람 포함</label>
            <label className="check-label"><input type="checkbox" checked={mask} onChange={(e) => setMask(e.target.checked)} /> 이름 가리기</label>
            <CopyTableButton label="표 복사 · 역량" headers={["축", "중분류", "역량", ...names.map(show), "가진 사람"]}
              rows={() => held.map((r) => [axisLabel(r.axis), r.group, r.name, ...names.map((n) => r.cells[n]?.count ?? ""), r.holders])} />
            <CopyTableButton label="표 복사 · 변동" headers={["축", "중분류", `${data?.change.last ?? ""}`, `${data?.change.this ?? ""}`, "차이"]}
              rows={() => (data?.change.groups ?? []).map((g) => [axisLabel(g.axis), g.group, g.last, g.this, g.delta])} />
            <CopyTableButton label="표 복사 · 기술" headers={["층", "보유 기술", "쓴 사람 수", "과제 수", "경험 수", "쓴 사람"]}
              rows={() => (data?.stack ?? []).flatMap((l) => l.tools.map((t) => [l.layer, t.name, t.person_count, t.project_count, t.experience_count, t.people.map(show).join(", ")]))} />
            <label className="check-label"><input type="checkbox" checked={printEvidence} onChange={(e) => setPrintEvidence(e.target.checked)} /> 근거도 인쇄</label>
            <button className="ghost" disabled={!data} onClick={() => setPrinting(true)}>인쇄 · PDF</button>
          </div>
        </div>
        <p className="hint">
          팀장의 질문 여섯 — <b>강점 · 빈 곳 · 위험 · 변화 · 성장 · 할 일</b> — 에 답합니다. 카드마다 답이 먼저, [근거 보기]를 누르면 아래 근거 자료로 갑니다.
          세는 것은 <b>구조화 · 확정 경험</b>, 숫자는 <b>경험 수</b>(수준 · 평가 아님). 변화 · 성장은 늘 올해 · 지난해, 나머지는 <b>범위</b>({periodLabel}). 팀에 나눌 때는 <b>이름 가리기</b>를 켜고 인쇄하세요.
        </p>
        {/* 292 G — 해마다 남기는 기록 */}
        {data && <SnapshotBar items={data.snapshots ?? []} year={data.year} onSaved={load} />}
        <p className="ts-notice" data-testid="ts-notice">팀장이 팀의 득과 실을 판단하는 자료입니다 — 평가 · 다른 사람과의 비교에 쓰지 않습니다. 숫자는 경험 수이고, 점(●)은 수준이 아니라 <b>근거가 얼마나 단단한가</b>입니다(●●● 확정 + 정량 결과 · ●● 확정 · ● 구조화만).</p>
      </div>
      {data && <Body data={data} show={show} interactive meta={meta} onTargets={load} plans={succession?.plans ?? []} onPlan={setSeed} />}
      {data && <SuccessionCard data={succession} people={names} show={show} seed={seed} onSeedUsed={() => setSeed(null)} onChanged={loadSuccession} />}
      {printing && data && createPortal(
        <div className="ts-print-root" aria-hidden>
          <h1 className="ts-print-title">팀 역량 · 기술 스택 — {data.change.last} → {data.change.this} · 범위 {periodLabel}</h1>
          <Body data={data} show={show} interactive={false} meta={meta} withEvidence={printEvidence} />
          <p className="ts-print-foot">팀장 판단용 — 평가 · 다른 사람과의 비교에 쓰지 않습니다. ● 근거의 단단함(수준 아님): ●●● 확정 + 정량 · ●● 확정 · ● 구조화만</p>
        </div>,
        document.body,
      )}
    </div>
  );
}

function Body({ data, show, interactive, meta, onTargets, withEvidence, plans = [], onPlan }: {
  data: Data; show: (name: string) => string; interactive: boolean; meta: Meta; onTargets?: () => void; withEvidence?: boolean;
  plans?: SuccessionPlan[]; onPlan?: (seed: PlanSeed) => void;
}) {
  const [evidence, setEvidence] = useState(false);
  // 292 A — 떠나면 무엇을 잃나(위험 카드에서 사람을 고른다)
  const [leaving, setLeaving] = useState("");
  const leave = leaving ? data.leave[leaving] : undefined;
  const k = data.kpis;
  const ch = data.change;
  const text = (t: string) => t.replace(/\{([^}]+)\}/g, (_, n: string) => show(n));
  const people = data.people.length || 1;
  const openEvidence = (id: string) => {
    setEvidence(true);
    window.setTimeout(() => document.querySelector(`[data-testid=${id}]`)?.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
  };
  const more = (id: string, label = "근거 보기") => interactive && (
    <button type="button" className="link-button ts-more" onClick={() => openEvidence(id)}>{label} →</button>
  );
  const chip = (name: string, kind: "skill" | "tool", note?: string) => (
    <span key={`${kind}-${name}`} className={`ts-new ${kind}`}>{name}{note && <small>{note}</small>}</span>
  );
  const s = data.strengths;
  const w = data.weak;
  const r = data.risk;
  const grown = data.growth.filter((g) => g.count > 0);
  const changeTotal = (key: "new" | "up" | "down" | "stopped") => ch.skills.counts[key] + ch.tools.counts[key];

  return (
    <>
      <section className="card ts-section ts-summary" data-testid="ts-summary">
        <p className="ts-headline" data-testid="ts-headline">{data.headline ? text(data.headline) : "아직 짚을 만한 내용이 없습니다 — 경험이 구조화 · 확정되면 결론이 생깁니다."}</p>
        <div className="ts-kpis">
          <div className="ts-kpi"><b>{k.skills_held}<small>/{k.skills_total}</small></b><span>가진 역량</span>{k.skills_new > 0 && <em className="ts-up">올해 +{k.skills_new}</em>}</div>
          <div className="ts-kpi"><b>{k.tools}</b><span>보유 기술</span>{k.tools_new > 0 && <em className="ts-up">올해 +{k.tools_new}</em>}</div>
          <div className="ts-kpi"><b className={k.only_one ? "warn-text" : ""}>{k.only_one}</b><span>혼자만 가진 것</span></div>
          <div className="ts-kpi"><b className={k.target_gaps ? "warn-text" : ""}>{k.target_gaps}</b><span>목표 모자람</span></div>
          <div className="ts-kpi"><b>{k.experiences}</b><span>세는 경험</span></div>
        </div>
      </section>

      <div className="ts-qgrid">
        <section className="card ts-q" data-testid="ts-q-strength">
          <div className="ts-q-head"><span className="ts-tag good">강점</span><h3>우리 팀이 잘하는 것</h3></div>
          <p className="ts-answer">{s.skills[0] ? <>가장 두터운 역량은 <b>{s.skills[0].name}</b> — {s.skills[0].holders}명 · 경험 {s.skills[0].experiences}건</> : "아직 셀 역량이 없습니다."}</p>
          <ul className="ts-bars">
            {s.skills.map((x) => (
              <li key={x.name}><span className="ts-bar-label">{x.name} <Dots level={data.skills.find((r) => r.name === x.name)?.evidence} /></span>
                <span className="ts-bar"><span className="ts-bar-fill" style={{ width: `${(x.holders / people) * 100}%` }} /></span>
                <span className="ts-bar-num">{x.holders}명 · {x.experiences}건</span></li>
            ))}
          </ul>
          {s.tools.length > 0 && <p className="ts-line">보유 기술 {s.tools.map((t) => chip(t.name, "tool", `${t.people}명`))}</p>}
          {more("ts-skill-map", "역량 지도")}
        </section>

        <section className="card ts-q" data-testid="ts-q-weak">
          <div className="ts-q-head"><span className="ts-tag warn">빈 곳</span><h3>약하거나 비어 있는 것</h3></div>
          <p className="ts-answer">
            {w.empty.length > 0 ? <>아무도 경험이 없는 묶음 <b>{w.empty.length}개</b></> : w.low[0] ? <>가장 얇은 묶음은 <b>{w.low[0].group}</b> — {w.low[0].experiences}건</> : "고르게 채워져 있습니다."}
            {w.gaps.length > 0 && <> · 목표 모자람 <b>{w.gaps.length}</b></>}
          </p>
          {w.low.length > 0 && (
            <ul className="ts-bars">
              {w.low.map((g) => (
                <li key={g.group}><span className="ts-bar-label">{g.group}</span>
                  <span className="ts-bar"><span className="ts-bar-fill warn" style={{ width: `${(g.held / Math.max(1, g.total)) * 100}%` }} /></span>
                  <span className="ts-bar-num">{g.experiences}건 · 역량 {g.held}/{g.total}</span></li>
              ))}
            </ul>
          )}
          {w.empty.length > 0 && <p className="ts-line">비어 있음 {w.empty.map((g) => chip(g.group, "tool"))}</p>}
          {w.gaps.length > 0 && <p className="ts-line">목표 {w.gaps.map((t) => chip(t.name, t.kind === "역량" ? "skill" : "tool", `${t.have ?? 0}/${t.want}명`))}</p>}
          {more("ts-targets", "목표 보기 · 고치기")}
        </section>

        <section className="card ts-q" data-testid="ts-q-risk">
          <div className="ts-q-head"><span className="ts-tag warn">위험</span><h3>누가 빠지면 끊기나</h3></div>
          {interactive && (
            <label className="check-label ts-leave-pick">이 사람이 떠나면
              <select aria-label="떠나면 무엇을 잃나" value={leaving} onChange={(e) => setLeaving(e.target.value)}>
                <option value="">— 팀 전체 보기 —</option>
                {data.people.map((p) => <option key={p.name} value={p.name}>{show(p.name)}</option>)}
              </select>
            </label>
          )}
          {leave ? (
            <div className="ts-leave" data-testid="ts-leave">
              <p className="ts-answer"><b>{show(leaving)}</b> 님이 떠나면 — 잃는 것 <b>{leave.lost.length}</b> · 얇아지는 것 <b>{leave.thin.length}</b> · 맡은 진행 중 과제 <b>{leave.projects.length}</b></p>
              {leave.lost.length === 0 ? <p className="muted">혼자만 가진 역량 · 기술이 없습니다.</p> : (
                <ul className="ts-leave-list">
                  {leave.lost.slice(0, 6).map((x) => (
                    <li key={`${x.kind}-${x.name}`}>
                      {chip(x.name, x.kind === "역량" ? "skill" : "tool")}
                      <span className="muted">{x.candidates.length ? `이어받을 후보(같은 ${x.kind === "역량" ? "묶음" : "층"}): ${x.candidates.map(show).join(", ")}` : "이어받을 후보 없음 — 배울 사람을 정해야 합니다"}</span>
                      {interactive && <PlanTag plans={plans} kind={x.kind} name={x.name} show={show}
                        onPlan={onPlan && (() => onPlan({ kind: x.kind, name: x.name, holders: [leaving], candidates: x.candidates }))} />}
                    </li>
                  ))}
                  {leave.lost.length > 6 && <li className="muted">외 {leave.lost.length - 6}개 — 근거 자료의 혼자만 가진 것</li>}
                </ul>
              )}
              {leave.thin.length > 0 && <p className="ts-line">얇아짐(한 명만 남음) {leave.thin.slice(0, 6).map((x) => chip(x.name, x.kind === "역량" ? "skill" : "tool", `→ ${show(x.remaining)}`))}</p>}
              {leave.projects.length > 0 && (
                <div className="ts-leave-projects" data-testid="ts-leave-projects">
                  <span className="muted">맡은 진행 중 과제 {leave.projects.length}</span>
                  {/* 294 — 칩으로 이어 붙이지 않고 한 줄에 과제 하나씩, 왼쪽 맞춤 */}
                  <ul>
                    {leave.projects.map((p) => (
                      <li key={p.id}><a href={projectLink(p.id)}>{p.title}</a> <span className="muted">{p.id}</span></li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : <>
          <p className="ts-answer">{r.people[0] ? <>혼자만 가진 것 <b>{k.only_one}개</b> — 그중 {r.people[0].count}개가 <b>{show(r.people[0].person)}</b> 님에게</> : "혼자만 가진 역량 · 기술이 없습니다."}</p>
          <ul className="ts-bars">
            {r.people.slice(0, 4).map((p) => (
              <li key={p.person}><span className="ts-bar-label">{show(p.person)}</span>
                <span className="ts-chip-wrap">{p.items.slice(0, 3).map((it) => (
                  <span key={`${it.kind}-${it.name}`} className="ts-risk-item">
                    {chip(it.name, it.kind === "역량" ? "skill" : "tool")}
                    {interactive && <PlanTag plans={plans} kind={it.kind} name={it.name} show={show}
                      onPlan={onPlan && (() => onPlan({ kind: it.kind as PlanSeed["kind"], name: it.name, holders: [p.person], candidates: data.leave[p.person]?.lost.find((l) => l.name === it.name)?.candidates ?? [] }))} />}
                  </span>
                ))}{p.count > 3 && <span className="muted">외 {p.count - 3}</span>}</span></li>
            ))}
          </ul>
          {r.tools.length > 0 && <p className="ts-line">많이 쓰는데 1명뿐 {r.tools.map((t) => chip(t.name, "tool", `${show(t.person)} · ${t.uses}곳`))}</p>}
          </>}
          {more("ts-only-one")}
        </section>

        <section className="card ts-q" data-testid="ts-q-change">
          <div className="ts-q-head"><span className="ts-tag">변화</span><h3>올해 무엇이 달라졌나 <span className="muted">{ch.last} → {ch.this}</span></h3></div>
          {interactive && data.snapshot_compare && <SnapshotCompareLine cmp={data.snapshot_compare} chip={chip} show={show} />}
          <p className="ts-answer">새로 생김 <b>{changeTotal("new")}</b> · 늘어남 <b>{changeTotal("up")}</b> · 줄어듦 <b>{changeTotal("down")}</b> · 끊김 <b>{changeTotal("stopped")}</b></p>
          <dl className="ts-change-mini">
            <dt>새로 생김</dt><dd>{[...ch.skills.new.slice(0, 3).map((x) => chip(x, "skill")), ...ch.tools.new.slice(0, 2).map((x) => chip(x, "tool"))]}{changeTotal("new") === 0 && <span className="muted">없음</span>}</dd>
            <dt>늘어남</dt><dd>{ch.skills.up.slice(0, 3).map((x) => chip(x.name, "skill", `${x.last}→${x.this}`))}{ch.skills.up.length === 0 && <span className="muted">없음</span>}</dd>
            <dt>줄어듦</dt><dd>{ch.skills.down.slice(0, 3).map((x) => chip(x.name, "skill", `${x.last}→${x.this}`))}{ch.skills.down.length === 0 && <span className="muted">없음</span>}</dd>
            <dt>끊김</dt><dd>{ch.skills.stopped.slice(0, 3).map((x) => chip(x.name, "skill", `${x.last}→0`))}{ch.skills.stopped.length === 0 && <span className="muted">없음</span>}</dd>
          </dl>
          {more("ts-change")}
        </section>

        <section className="card ts-q" data-testid="ts-q-growth">
          <div className="ts-q-head"><span className="ts-tag good">성장</span><h3>누가 넓어졌나 <span className="muted">본인 지난해와만</span></h3></div>
          <p className="ts-answer">올해 새 역량 · 기술을 쓴 사람 <b>{grown.length}</b> / {data.growth.length}명</p>
          <table className="grid ts-compact ts-growth">
            <tbody>
              {data.growth.map((g) => (
                <tr key={g.person}>
                  <th scope="row">{show(g.person)}</th>
                  <td className="ts-num">{g.count ? <b>+{g.count}</b> : <span className="muted">0</span>}<small className="muted"> (지난해 +{g.last})</small></td>
                  <td>{[...g.skills, ...g.tools].slice(0, 3).join(", ")}{g.count > 3 ? " …" : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="card ts-q" data-testid="ts-q-actions">
          <div className="ts-q-head"><span className="ts-tag">할 일</span><h3>그래서 무엇을 하나 <span className="muted">제안 — 규칙으로 만듦</span></h3></div>
          {data.actions.length === 0 ? <p className="muted">지금 제안할 일이 없습니다.</p> : (
            <ul className="ts-actions">
              {data.actions.map((a, i) => <li key={i}><span className="ts-tag small">{a.kind}</span> {text(a.text)}</li>)}
            </ul>
          )}
        </section>
      </div>

      {(interactive || withEvidence) && <details className="card ts-section ts-fold" data-testid="ts-evidence" open={!interactive ? (withEvidence || undefined) : (evidence || undefined)}
        onToggle={(e) => interactive && setEvidence((e.target as HTMLDetailsElement).open)}>
        <summary><b>근거 자료</b> <span className="muted">— 지난해와 비교 · 팀 모양 · 기술 스택 · 혼자만 가진 것 · 목표 · 역량 지도 · 과제 분류 · 처음 나온 해</span></summary>
        {(evidence || !interactive) && <Evidence data={data} show={show} interactive={interactive} meta={meta} onTargets={onTargets} />}
      </details>}

      {(interactive || withEvidence) && <Completeness data={data} show={show} interactive={interactive} />}
    </>
  );
}

/** 근거의 단단함(292 F) — 수준이 아니다. ●●● 확정 + 정량 결과 · ●● 확정 · ● 구조화만 */
function Dots({ level }: { level?: { confirmed: number; quant: number; level: number } }) {
  if (!level || !level.level) return null;
  return (
    <span className={`ts-dots l${level.level}`} title={`근거 — 확정 ${level.confirmed}건 · 정량 결과 ${level.quant}건`} aria-label={`근거 ${level.level}단계`}>
      {"●".repeat(level.level)}
    </span>
  );
}

/** 근거 자료 — 290 의 표 · 막대 · 지도(접어 둔 곳). 질문 카드의 [근거 보기]가 여기로 */
function Evidence({ data, show, interactive, meta, onTargets }: {
  data: Data; show: (name: string) => string; interactive: boolean; meta: Meta; onTargets?: () => void;
}) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [picked, setPicked] = useState<TeamSkillTool | null>(null);
  const classes = meta.classifications.filter((c) => data.by_class[c.key]);
  const [classKey, setClassKey] = useState(classes[0]?.key ?? "nature");
  const names = data.people.map((p) => p.name);
  const ch = data.change;
  const maxShape = Math.max(1, ...data.shape.map((s) => s.experiences));
  const maxTrend = Math.max(1, ...ch.axes_trend.flatMap((a) => a.years.map((y) => y.count)));

  // 역량 지도 — 축 · 중분류마다 사람별 합. 줄을 누르면 그 안의 역량
  const held = data.skills.filter((r) => r.holders > 0);
  const groupKeys = [...new Map(held.map((r) => [`${r.axis}|${r.group}`, { axis: r.axis, group: r.group }])).values()];
  // 한 사람에게만 — 사람마다 묶음
  const byPerson = new Map<string, { kind: string; name: string }[]>();
  for (const o of data.only_one) byPerson.set(o.person, [...(byPerson.get(o.person) ?? []), { kind: o.kind, name: o.name }]);
  const personRows = [...byPerson.entries()].sort((a, b) => b[1].length - a[1].length);

  const chip = (name: string, kind: "skill" | "tool", note?: string) => (
    <span key={`${kind}-${name}`} className={`ts-new ${kind}`}>{name}{note && <small>{note}</small>}</span>
  );
  const box = (label: string, key: "new" | "up" | "down" | "stopped", tone: string) => {
    const sk = ch.skills[key]; const tl = ch.tools[key];
    const n = ch.skills.counts[key] + ch.tools.counts[key];
    return (
      <div className={`ts-change-box ${tone}`} data-box={key}>
        <div className="ts-change-head"><b>{label}</b> <span className="muted">{n}</span></div>
        {n === 0 && <span className="muted">없음</span>}
        <div className="ts-chip-wrap">
          {key === "new"
            ? [...(sk as string[]).map((x) => chip(x, "skill")), ...(tl as string[]).map((x) => chip(x, "tool"))]
            : [...(sk as { name: string; last: number; this: number }[]).map((x) => chip(x.name, "skill", `${x.last}→${x.this}`)),
              ...(tl as { name: string; last: number; this: number }[]).map((x) => chip(x.name, "tool", `${x.last}→${x.this}명`))]}
        </div>
      </div>
    );
  };

  return (
    <div className="ts-evidence">
      <section className="ts-sub" data-testid="ts-change">
        <h3>지난해와 비교 <span className="muted">— {ch.last} → {ch.this}, 그 해에 걸친 경험 수(보유 기술은 쓴 사람 수)</span></h3>
        <div className="ts-two">
          <div className="table-scroll">
            <table className="grid ts-compact ts-change-table">
              <thead><tr><th>중분류</th><th>{ch.last}</th><th>{ch.this}</th><th>차이</th></tr></thead>
              <tbody>
                {ch.groups.map((g) => (
                  <tr key={`${g.axis}-${g.group}`} className={g.delta ? undefined : "ts-flat"}>
                    <th scope="row">{g.group} <span className="muted">{axisLabel(g.axis)}</span></th>
                    <td>{g.last || ""}</td><td>{g.this || ""}</td><td>{delta(g.delta)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="ts-change-grid">
            {box("새로 생김", "new", "good")}
            {box("늘어남", "up", "good")}
            {box("줄어듦", "down", "warn")}
            {box("끊김", "stopped", "warn")}
            <p className="hint ts-legend"><span className="ts-new skill">역량</span> <span className="ts-new tool">보유 기술</span> · 숫자는 지난해 → 올해</p>
          </div>
        </div>
      </section>

      <div className="ts-half">
        <section className="ts-sub" data-testid="ts-shape">
          <h3>축별 팀 모양</h3>
          <div className="ts-shape">
            {data.shape.map((s) => (
              <div key={s.axis} className="ts-shape-row" data-axis={s.axis}>
                <span className="ts-shape-name">{axisLabel(s.axis)}</span>
                <span className="ts-bar"><span className="ts-bar-fill" style={{ width: `${(s.experiences / maxShape) * 100}%` }} /></span>
                <span className="ts-shape-num"><b>{s.experiences}</b>건 · 역량 {s.held}/{s.total} · {s.people}명</span>
              </div>
            ))}
          </div>
          <h4 className="ts-trend-title">축마다 다섯 해 <span className="muted">그 해에 걸친 경험 수</span></h4>
          <div className="ts-trend" data-testid="ts-trend">
          {ch.axes_trend.map((a) => (
            <div key={a.axis} className="ts-trend-axis">
              <span className="ts-trend-name">{axisLabel(a.axis)}</span>
              <span className="ts-trend-bars">
                {a.years.map((y) => (
                  <span key={y.year} className="ts-trend-col" title={`${y.year} · ${y.count}건`}>
                    <span className="ts-trend-bar" style={{ height: `${Math.max(2, (y.count / maxTrend) * 100)}%` }} />
                    <small>{y.year.slice(2)}</small>
                  </span>
                ))}
              </span>
            </div>
          ))}
        </div>
        </section>
        <section className="ts-sub" data-testid="ts-stack">
          <h3>기술 스택 <span className="muted">칩 = 쓴 사람 수</span></h3>
          {data.stack.length === 0 && <p className="muted">보유 기술이 아직 없습니다.</p>}
          <div className="ts-stack">
            {data.stack.map((layer) => (
              <div key={layer.layer} className={layer.unlayered ? "ts-layer unlayered" : "ts-layer"} data-layer={layer.layer}>
                <span className="ts-layer-name">{layer.layer}</span>
                <span className="ts-layer-tools">
                  {layer.tools.map((t) => {
                    const body = <>{t.name} <b>{t.person_count}</b></>;
                    return interactive ? (
                      <button key={t.name} type="button" className={`ts-tool${picked?.name === t.name ? " on" : ""}`} aria-pressed={picked?.name === t.name}
                        title={`${t.person_count}명 · 과제 ${t.project_count} · 경험 ${t.experience_count}`} onClick={() => setPicked(picked?.name === t.name ? null : t)}>{body}</button>
                    ) : <span key={t.name} className="ts-tool">{body}</span>;
                  })}
                </span>
              </div>
            ))}
          </div>
          {interactive && picked && (
            <div className="ts-uses" data-testid="ts-uses">
              <b>{picked.name}</b> — 쓴 사람 {picked.people.map(show).join(", ")} · 과제 {picked.project_count} · 경험 {picked.experience_count}
              <ul>
                {picked.uses.map((u, i) => (
                  <li key={i}>
                    {show(u.person)} · {u.kind === "project" ? "과제" : "경험"}{" "}
                    <a href={u.kind === "project" ? projectLink(u.id) : experienceLink(u.id)}>{u.title}</a>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      </div>

      <div className="ts-half" data-testid="ts-risk">
        <section className="ts-sub" data-testid="ts-only-one">
          <h3>혼자만 가진 것 <span className="muted">대신할 사람이 없음</span></h3>
          {personRows.length === 0 ? <p className="muted">없습니다.</p> : (
            <ul className="ts-person-risk">
              {personRows.map(([person, items]) => (
                <li key={person}>
                  <b>{show(person)}</b> <span className="muted">{items.length}개</span>
                  <span className="ts-chip-wrap">{items.map((it) => chip(it.name, it.kind === "역량" ? "skill" : "tool"))}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="ts-sub">
          <Targets data={data} interactive={interactive} onSaved={onTargets} />
        </section>
      </div>

      <section className="ts-sub" data-testid="ts-skill-map">
        <div className="card-head">
          <h3>역량 지도 <span className="muted">— 중분류 × 사람, 칸 = 경험 수. 줄을 누르면 그 안의 역량</span></h3>
          {interactive && groupKeys.length > 0 && (
            <button type="button" className="ghost small" onClick={() => {
              const all = groupKeys.every((g) => open[`${g.axis}|${g.group}`]);
              setOpen(Object.fromEntries(groupKeys.map((g) => [`${g.axis}|${g.group}`, !all])));
            }}>{groupKeys.every((g) => open[`${g.axis}|${g.group}`]) ? "모두 접기" : "모두 펼치기"}</button>
          )}
        </div>
        {held.length === 0 ? <p className="muted">세는 경험에 역량 태그가 아직 없습니다.</p> : (
          <div className="table-scroll">
            <table className="grid ts-map ts-compact">
              <thead>
                <tr><th className="ts-map-name">중분류 · 역량</th>{names.map((n) => <th key={n} className="ts-map-person">{show(n)}</th>)}<th>가진 사람</th></tr>
              </thead>
              <tbody>
                {groupKeys.map((g) => {
                  const key = `${g.axis}|${g.group}`;
                  const rows = held.filter((r) => r.axis === g.axis && r.group === g.group);
                  const isOpen = !!open[key];
                  const sum = (n: string) => rows.reduce((acc, r) => acc + (r.cells[n]?.count ?? 0), 0);
                  const holders = names.filter((n) => sum(n) > 0).length;
                  return [
                    <tr key={key} className="ts-group-line" data-group={g.group || "(중분류 없음)"}>
                      <th scope="row" className="ts-map-name">
                        {interactive ? (
                          <button type="button" className="link-button ts-group-toggle" aria-expanded={isOpen} onClick={() => setOpen({ ...open, [key]: !isOpen })}>
                            {isOpen ? "▾" : "▸"} {g.group || "(중분류 없음)"}
                          </button>
                        ) : (g.group || "(중분류 없음)")}
                        <span className="muted"> {axisLabel(g.axis)} · {rows.length}</span>
                      </th>
                      {names.map((n) => { const v = sum(n); return <td key={n} className={`ts-cell lv${level(v)}`}>{v || ""}</td>; })}
                      <td className={holders === 1 ? "ts-holders one" : "ts-holders"}>{holders}</td>
                    </tr>,
                    ...(isOpen ? rows.map((r) => (
                      <tr key={`${key}-${r.name}`} className="ts-skill-line" data-skill={r.name}>
                        <th scope="row" className="ts-map-name ts-indent">{r.name} <Dots level={r.evidence} />{!r.known && <span className="tag warn-tag" title="역량 사전에 없는 태그">사전에 없음</span>}</th>
                        {names.map((n) => {
                          const cell = r.cells[n];
                          return <td key={n} className={`ts-cell lv${level(cell?.count ?? 0)}`} title={cell ? `${show(n)} · 경험 ${cell.count}건(확정 ${cell.confirmed ?? 0} · 정량 ${cell.quant ?? 0})${cell.last ? ` · 마지막 ${cell.last}` : ""}` : ""}>{cell?.count ?? ""}</td>;
                        })}
                        <td className={r.holders === 1 ? "ts-holders one" : "ts-holders"}>{r.holders}</td>
                      </tr>
                    )) : []),
                  ];
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div className="ts-sub" data-testid="ts-details">
        
        <div data-testid="ts-by-class" className="ts-sub">
          <h4>과제 분류 × 역량 <span className="muted">과제에 이은 경험 수</span></h4>
          {interactive && (
            <div className="dict-axes" role="group" aria-label="과제 분류">
              {classes.map((cl) => (
                <button key={cl.key} type="button" className={classKey === cl.key ? "chip on" : "chip"} aria-pressed={classKey === cl.key} onClick={() => setClassKey(cl.key)}>{cl.label}</button>
              ))}
            </div>
          )}
          {(interactive ? classes.filter((cl) => cl.key === classKey) : classes).map((cl) => {
            const block = data.by_class[cl.key];
            if (!block || block.rows.length === 0) return <p key={cl.key} className="muted">{cl.label} — 과제에 이은 경험이 없거나 과제의 {cl.label} 칸이 비었습니다.</p>;
            return (
              <div key={cl.key} className="table-scroll">
                {!interactive && <p className="ts-print-sub">{cl.label}</p>}
                <table className="grid ts-map ts-compact">
                  <thead><tr><th className="ts-map-name">역량</th>{block.values.map((v) => <th key={v} className="ts-map-person">{v}</th>)}<th>합</th></tr></thead>
                  <tbody>
                    {block.rows.slice(0, 20).map((r) => (
                      <tr key={`${r.axis}-${r.name}`}>
                        <th scope="row" className="ts-map-name">{r.name} <span className="muted">{axisLabel(r.axis)}</span></th>
                        {block.values.map((v) => { const n = r.cells[v] ?? 0; return <td key={v} className={`ts-cell lv${level(n)}`}>{n || ""}</td>; })}
                        <td className="ts-holders">{r.total}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {block.rows.length > 20 && <p className="muted">많이 나온 20개만 — 나머지 {block.rows.length - 20}개</p>}
              </div>
            );
          })}
        </div>
        <div data-testid="ts-new-by-year" className="ts-sub">
          <h4>처음 나온 해 <span className="muted">팀에 처음 나온 역량 · 보유 기술과 가져온 사람</span></h4>
          <div className="ts-years">
            {data.new_by_year.map((y) => (
              <div key={y.year} className="ts-year-row" data-year={y.year}>
                <span className="ts-layer-name">{y.year} <span className="muted">{y.items.length}</span></span>
                <span className="ts-chip-wrap">
                  {y.items.length === 0 && <span className="muted">없음</span>}
                  {y.items.map((item) => chip(item.name, item.kind === "역량" ? "skill" : "tool", item.people.map(show).join(", ")))}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

    </div>
  );
}

/** 데이터 점검 — 맨 아래 접힘 */
function Completeness({ data, show, interactive }: { data: Data; show: (name: string) => string; interactive: boolean }) {
  const k = data.kpis;
  const c = data.completeness;
  const issues = c.unknown_tags + c.unlisted_tools.length + c.no_layer_tools.length;
  return (
      <details className="card ts-section ts-fold" data-testid="ts-completeness" open={!interactive || undefined}>
        <summary>
          <b>데이터 점검</b>{issues > 0 && <span className="warn-text" title="사전에 없음 · 층 없음이 있습니다"> ●</span>}
          <span className="muted"> — 세는 경험 {k.experiences}건 · 사전에 없는 역량 태그 {c.unknown_tags} · 사전에 없는 보유 기술 {c.unlisted_tools.length} · 층 없는 보유 기술 {c.no_layer_tools.length}</span>
        </summary>
        <p className="ts-summary">
          {c.unlisted_tools.length > 0 && <>사전에 없는 보유 기술: {c.unlisted_tools.slice(0, 10).join(", ")}{c.unlisted_tools.length > 10 ? " …" : ""} · </>}
          기술 칸이 빈 담당 {c.empty_tool_projects}
          {interactive && <> · <a href="#/settings?tab=class">설정 → 역량 · 보유 기술 사전</a></>}
        </p>
        <div className="table-scroll">
          <table className="grid ts-complete-table ts-compact">
            <thead><tr><th>사람</th><th>확정</th><th>구조화</th><th>초안</th><th>사전에 없는 태그</th><th>기술 칸 빈 담당</th></tr></thead>
            <tbody>
              {c.people.map((p) => (
                <tr key={p.name} className={p.확정 + p.구조화 === 0 ? "ts-weak" : undefined}>
                  <th scope="row">{interactive ? <a href={personLink(p.name)}>{show(p.name)}</a> : show(p.name)}</th>
                  <td>{p.확정}</td><td>{p.구조화}</td><td>{p.초안}</td><td>{p.unknown_tags || ""}</td><td>{p.empty_tools || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
  );
}

/** 목표 — 팀이 갖출 역량 · 보유 기술과 사람 수. 지금 가진 사람과 견준다(빈 곳) */
function Targets({ data, interactive, onSaved }: { data: Data; interactive: boolean; onSaved?: () => void }) {
  const [editing, setEditing] = useState<TeamSkillTarget[] | null>(null);
  const [busy, setBusy] = useState(false);
  const skillNames = data.skills.map((r) => r.name);
  const toolNames = data.stack.flatMap((l) => l.tools.map((t) => t.name));
  const rows = data.targets;

  async function save() {
    if (!editing) return;
    setBusy(true);
    try {
      await api.saveTeamTargets(editing.filter((t) => t.name.trim()).map((t) => ({ kind: t.kind, name: t.name.trim(), want: Number(t.want) || 1 })));
      setEditing(null);
      onSaved?.();
    } catch (error) {
      notifyError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const set = (i: number, patch: Partial<TeamSkillTarget>) => setEditing((list) => list!.map((t, j) => (j === i ? { ...t, ...patch } : t)));

  return (
    <section className="ts-sub" data-testid="ts-targets">
      <div className="card-head">
        <h3>목표 vs 지금</h3>
        {interactive && !editing && <button type="button" className="ghost small" onClick={() => setEditing(rows.map(({ kind, name, want }) => ({ kind, name, want })))}>목표 고치기</button>}
      </div>
      {!editing && rows.length === 0 && <p className="muted">적어 둔 목표가 없습니다{interactive ? " — [목표 고치기]로 팀이 갖출 역량 · 보유 기술과 사람 수를 적으세요" : ""}.</p>}
      {!editing && rows.length > 0 && (
        <div className="table-scroll">
          <table className="grid ts-targets ts-compact">
            <thead><tr><th>구분</th><th>이름</th><th>목표</th><th>지금</th><th>모자람</th></tr></thead>
            <tbody>
              {rows.map((t) => (
                <tr key={`${t.kind}-${t.name}`} className={t.gap ? "ts-gap" : undefined}>
                  <td>{t.kind}</td>
                  <td>{t.name}{t.matched && t.matched !== t.name ? <span className="muted"> ({t.matched})</span> : null}</td>
                  <td>{t.want}명</td><td>{t.have ?? 0}명</td>
                  <td>{t.gap ? <b className="warn-text">{t.gap}명</b> : "✓"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editing && (
        <div className="ts-target-edit">
          {editing.map((t, i) => (
            <div key={i} className="ts-target-row">
              <select aria-label="목표 구분" value={t.kind} onChange={(e) => set(i, { kind: e.target.value as TeamSkillTarget["kind"] })}>
                <option value="역량">역량</option><option value="보유 기술">보유 기술</option>
              </select>
              <input aria-label="목표 이름" value={t.name} maxLength={60} list={t.kind === "역량" ? "ts-skill-names" : "ts-tool-names"}
                placeholder={t.kind === "역량" ? "역량 이름" : "보유 기술 이름"} onChange={(e) => set(i, { name: e.target.value })} />
              <input aria-label="목표 사람 수" type="number" min={1} max={99} value={t.want} onChange={(e) => set(i, { want: Number(e.target.value) })} />
              <span className="muted">명</span>
              <button type="button" className="ghost small" aria-label={`${t.name || "이 줄"} 빼기`} onClick={() => setEditing(editing.filter((_, j) => j !== i))}>×</button>
            </div>
          ))}
          <datalist id="ts-skill-names">{skillNames.map((n) => <option key={n} value={n} />)}</datalist>
          <datalist id="ts-tool-names">{toolNames.map((n) => <option key={n} value={n} />)}</datalist>
          <div className="form-actions">
            <button type="button" className="ghost small" onClick={() => setEditing([...editing, { kind: "역량", name: "", want: 2 }])}>+ 목표</button>
            <button type="button" className="ghost" onClick={() => setEditing(null)}>취소</button>
            <button type="button" disabled={busy} onClick={() => void save()}>{busy ? "저장 중…" : "저장"}</button>
          </div>
        </div>
      )}
    </section>
  );
}
