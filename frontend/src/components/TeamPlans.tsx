import { useEffect, useState } from "react";
import { api } from "../api";
import { renderMarkdown } from "../markdown";
import { attempt, notifyError } from "../notify";
import { experienceLink } from "../nav";
import type { Growth, GrowthGoal, Snapshot, SnapshotCompare, SnapshotItem, Succession, SuccessionPlan } from "../types";

/**
 * 292 2차 — 팀장이 "그래서 누구를 · 언제까지 · 어떻게" 를 적고, 나중에 됐는지 보는 칸.
 *
 * * G 해마다 남기는 기록 — [올해 기록 남기기] · 기록 보기 · 지난해 말 기록 ↔ 지금(변화 카드 위).
 * * B 승계 · 짝 계획 — 위험 카드 · 떠나면 잃는 것의 [계획으로] → 배울 사람 · 방법 · 기한. 배울 사람에게 경험이 생기면 저절로 "됨".
 * * C 개인 육성 목표 — 면담 탭에서 사람마다 해마다 키울 역량 1 ~ 3개. 팀원은 자기 것을 보기만.
 * 모두 팀장이 득과 실을 판단하는 자료 — 수준 · 점수 없음, 평가에 쓰지 않는다(292 J).
 */

// ── G 해마다 남기는 기록 ──────────────────────────────────────────────────────

export function SnapshotBar({ items, year, onSaved }: { items: SnapshotItem[]; year: string; onSaved: () => void }) {
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<Snapshot | null>(null);
  const has = items.some((item) => item.year === year);
  async function save() {
    if (has && !window.confirm(`${year}년 기록이 이미 있습니다. 지금 그림으로 다시 남길까요? (이전 것은 이전 버전에 남습니다)`)) return;
    setBusy(true);
    const done = await attempt(() => api.saveSnapshot(year));
    setBusy(false);
    if (done) onSaved();
  }
  async function view(y: string) {
    try {
      setOpen(await api.snapshot(y));
    } catch (error) {
      notifyError((error as Error).message);
    }
  }
  return (
    <div className="ts-snapshots" data-testid="ts-snapshots">
      <button type="button" className="ghost" disabled={busy} onClick={() => void save()} data-testid="ts-snapshot-save">
        {has ? `${year}년 기록 다시 남기기` : `${year}년 기록 남기기`}
      </button>
      <span className="muted">남긴 기록</span>
      {items.length === 0 ? <span className="muted">없음 — 12월에 한 번 남기면 다음 해에 "그때 ↔ 지금" 을 견줍니다.</span>
        : items.map((item) => (
          <button key={item.year} type="button" className="link-button" onClick={() => void view(item.year)}
            title={`${item.saved_at.replace("T", " ").slice(0, 16)}${item.auto ? " · 저절로 남김" : ""}`}>
            {item.year}{item.auto ? "(저절로)" : ""}
          </button>
        ))}
      {open && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label={`${open.year} 팀 역량 기록`} onClick={() => setOpen(null)}>
          <div className="modal ts-snapshot-view" data-testid="ts-snapshot-view" onClick={(e) => e.stopPropagation()}>
            <div className="card-head">
              <h3>{open.year}년 팀 역량 기록 <span className="muted">{open.saved_at.replace("T", " ").slice(0, 16)}{open.auto ? " · 저절로" : ""}</span></h3>
              <button type="button" className="ghost small" onClick={() => setOpen(null)}>닫기</button>
            </div>
            <div className="markdown-body" dangerouslySetInnerHTML={{ __html: renderMarkdown(open.body) }} />
          </div>
        </div>
      )}
    </div>
  );
}

/** 변화 카드 위 — 지난해 말 기록 ↔ 지금(가진 사람 수로) */
export function SnapshotCompareLine({ cmp, chip, show }: {
  cmp: SnapshotCompare; chip: (name: string, kind: "skill" | "tool", note?: string) => JSX.Element; show: (n: string) => string;
}) {
  const s = cmp.skills;
  const t = cmp.tools;
  return (
    <div className="ts-snap-cmp" data-testid="ts-snapshot-compare">
      <p className="ts-answer">
        <span className="ts-tag small">기준</span> <b>{cmp.year}년 말 기록</b> ↔ 지금 —
        사람 {cmp.people.last}→{cmp.people.this} · 역량 새로 <b>{s.counts.new}</b> · 사라짐 <b>{s.counts.lost}</b> · 가진 사람 늘어남 <b>{s.counts.up}</b> · 줄어듦 <b>{s.counts.down}</b>
        {" "}· 혼자만 가진 것 {cmp.only_one.last}→{cmp.only_one.this}
      </p>
      <dl className="ts-change-mini">
        {s.new.length + t.new.length > 0 && <><dt>새로 가짐</dt><dd>{[...s.new.slice(0, 4).map((x) => chip(x, "skill")), ...t.new.slice(0, 2).map((x) => chip(x, "tool"))]}</dd></>}
        {s.lost.length + t.lost.length > 0 && <><dt>사라짐</dt><dd>{[...s.lost.slice(0, 4).map((x) => chip(x, "skill")), ...t.lost.slice(0, 2).map((x) => chip(x, "tool"))]}</dd></>}
        {s.up.length > 0 && <><dt>사람 늘어남</dt><dd>{s.up.slice(0, 4).map((x) => chip(x.name, "skill", `${x.last}→${x.this}명`))}</dd></>}
        {cmp.only_one.resolved.length > 0 && <><dt>혼자만 → 풀림</dt><dd className="muted">{cmp.only_one.resolved.slice(0, 4).join(", ")}</dd></>}
        {(cmp.people.joined.length > 0 || cmp.people.left.length > 0) && (
          <><dt>사람</dt><dd className="muted">{cmp.people.joined.length ? `들어옴 ${cmp.people.joined.map(show).join(", ")}` : ""}{cmp.people.joined.length && cmp.people.left.length ? " · " : ""}{cmp.people.left.length ? `빠짐 ${cmp.people.left.map(show).join(", ")}` : ""}</dd></>
        )}
      </dl>
      <p className="muted ts-snap-note">아래 숫자는 경험 날짜로 센 올해 ↔ 지난해입니다.</p>
    </div>
  );
}

// ── B 승계 · 짝 계획 ──────────────────────────────────────────────────────────

export interface PlanSeed { kind: "역량" | "보유 기술"; name: string; holders: string[]; candidates: string[] }

export function useSuccession(): [Succession | null, () => void] {
  const [data, setData] = useState<Succession | null>(null);
  const load = () => { api.succession().then(setData).catch(() => setData(null)); };
  useEffect(load, []);
  return [data, load];
}

/** 위험 줄 옆 — 진행 중인 계획이 있으면 "계획 있음 · 이준호 · 2027-06", 없으면 [계획으로] */
export function PlanTag({ plans, kind, name, show, onPlan }: {
  plans: SuccessionPlan[]; kind: string; name: string; show: (n: string) => string; onPlan?: () => void;
}) {
  const found = plans.find((p) => p.state === "진행" && p.kind === kind && p.name === name);
  if (found) return <span className={`ts-plan-tag${found.overdue ? " overdue" : ""}`} title={found.note || undefined}>계획 있음 · {show(found.learner)} · {found.due.slice(0, 7)}</span>;
  if (!onPlan) return null;
  return <button type="button" className="link-button ts-plan-add" onClick={onPlan}>계획으로</button>;
}

export function SuccessionCard({ data, people, leader, show, seed, onSeedUsed, onChanged }: {
  data: Succession | null; people: string[]; leader?: string; show: (n: string) => string; seed: PlanSeed | null; onSeedUsed: () => void; onChanged: () => void;
}) {
  const blank: { kind: "역량" | "보유 기술"; name: string; holders: string[]; learner: string; way: string; due: string; note: string } =
    { kind: "역량", name: "", holders: [], learner: "", way: "짝 과제", due: "", note: "" };
  const [form, setForm] = useState<typeof blank | null>(null);
  const [candidates, setCandidates] = useState<string[]>([]);
  const [showDone, setShowDone] = useState(false);
  useEffect(() => {
    if (!seed) return;
    // 미리 고르는 배울 사람은 팀원 후보 첫째(팀장은 건너뜀 — 고르려면 목록에서 직접)
    setForm({ ...blank, kind: seed.kind, name: seed.name, holders: seed.holders, learner: seed.candidates.find((n) => n !== leader) ?? "" });
    setCandidates(seed.candidates);
    onSeedUsed();
    window.setTimeout(() => document.querySelector("[data-testid=ts-succession]")?.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
  }, [seed]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!data) return null;
  async function add() {
    if (!form) return;
    const made = await attempt(() => api.addPlan({ ...form, due: form.due || undefined }));
    if (made) { setForm(null); onChanged(); }
  }
  async function change(plan: SuccessionPlan, patch: Partial<SuccessionPlan>) {
    if (await attempt(() => api.updatePlan(plan.id, patch))) onChanged();
  }
  async function remove(plan: SuccessionPlan) {
    if (!window.confirm(`${plan.name} → ${plan.learner} 계획을 지울까요? (이전 버전에는 남습니다)`)) return;
    if (await attempt(() => api.deletePlan(plan.id))) onChanged();
  }
  const open = data.plans.filter((p) => p.state === "진행");
  const closed = data.plans.filter((p) => p.state !== "진행");
  const row = (p: SuccessionPlan) => (
    <tr key={p.id} className={p.overdue ? "ts-plan-overdue" : undefined} data-plan={p.id}>
      <td><span className="ts-tag small">{p.kind}</span> <b>{p.name}</b></td>
      <td>{p.holders.map(show).join(", ") || "—"} → <b>{show(p.learner)}</b></td>
      <td>{p.way}{p.note && <div className="muted">{p.note}</div>}</td>
      <td className={p.overdue ? "warn-text" : undefined}>{p.due}{p.overdue && " · 지남"}</td>
      <td>
        {p.state === "진행" ? <span className="muted">진행</span>
          : p.state === "됨" ? <span className="ts-plan-done">됨 {p.done_at}{p.done_by === "경험" && p.evidence
            ? <> · <a href={experienceLink(p.evidence.id)}>{p.evidence.title}</a></> : p.done_by === "직접" ? " · 직접 표시" : ""}</span>
          : <span className="muted">그만둠</span>}
      </td>
      <td className="ts-plan-actions">
        {p.state === "진행" ? (
          <>
            <button type="button" className="ghost small" onClick={() => void change(p, { state: "됨" })}>됨</button>
            <button type="button" className="ghost small" onClick={() => { const due = window.prompt("새 기한(YYYY-MM-DD)", p.due); if (due) void change(p, { due }); }}>기한</button>
            <button type="button" className="ghost small" onClick={() => void change(p, { state: "그만둠" })}>그만둠</button>
          </>
        ) : <button type="button" className="ghost small" onClick={() => void change(p, { state: "진행" })}>다시 진행</button>}
        <button type="button" className="ghost small danger" onClick={() => void remove(p)}>지우기</button>
      </td>
    </tr>
  );
  return (
    <section className="card ts-section" data-testid="ts-succession">
      <div className="card-head">
        <h3>승계 · 짝 계획 <span className="muted">진행 {data.counts["진행"] ?? 0} · 됨 {data.counts["됨"] ?? 0}{data.overdue ? ` · 기한 지남 ${data.overdue}` : ""}</span></h3>
        <button type="button" className={form ? "ghost on" : "ghost"} onClick={() => { setForm(form ? null : blank); setCandidates([]); }}>새 계획</button>
      </div>
      <p className="hint">혼자만 가진 것 · 떠나면 잃는 것을 <b>누가 언제까지</b> 배울지 적습니다. 위험 카드의 <b>[계획으로]</b>에서 시작하면 채워져 있습니다.
        배울 사람에게 그 역량 · 보유 기술의 경험(구조화 · 확정)이 생기면 <b>저절로 "됨"</b> 이 됩니다. 배울 사람 본인에게는 보이지 않습니다(팀장 화면).</p>
      {form && (
        <div className="ts-plan-form" data-testid="ts-plan-form">
          <label>구분
            <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as typeof form.kind })}>
              <option value="역량">역량</option><option value="보유 기술">보유 기술</option>
            </select>
          </label>
          <label>무엇을 <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="예: 공정 데이터 분석" aria-label="배울 것" /></label>
          <label>가진 사람 <span className="muted">{form.holders.map(show).join(", ") || "—"}</span></label>
          <label>배울 사람
            <select value={form.learner} onChange={(e) => setForm({ ...form, learner: e.target.value })} aria-label="배울 사람">
              <option value="">— 고르세요 —</option>
              {candidates.length > 0 && <optgroup label="후보(같은 묶음 · 층)">{candidates.map((n) => <option key={`c-${n}`} value={n}>{show(n)}</option>)}</optgroup>}
              <optgroup label="모두">{people.filter((n) => !form.holders.includes(n)).map((n) => <option key={n} value={n}>{show(n)}</option>)}</optgroup>
            </select>
          </label>
          <label>방법
            <select value={form.way} onChange={(e) => setForm({ ...form, way: e.target.value })}>{data.ways.map((w) => <option key={w}>{w}</option>)}</select>
          </label>
          <label>기한 <span className="muted">(비우면 {data.default_months}개월 뒤)</span>
            <input type="date" value={form.due} onChange={(e) => setForm({ ...form, due: e.target.value })} aria-label="기한" />
          </label>
          <label className="ts-plan-note">메모 <input value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} placeholder="예: 불량 예측 과제에 짝으로" /></label>
          <div className="form-actions">
            <button type="button" className="ghost" onClick={() => setForm(null)}>취소</button>
            <button type="button" onClick={() => void add()} data-testid="ts-plan-save">계획 저장</button>
          </div>
        </div>
      )}
      {open.length === 0 && !form ? <p className="muted">진행 중인 계획이 없습니다.</p> : open.length > 0 && (
        <table className="grid ts-compact ts-plans"><thead><tr><th>무엇</th><th>가진 사람 → 배울 사람</th><th>방법</th><th>기한</th><th>상태</th><th /></tr></thead>
          <tbody>{open.map(row)}</tbody></table>
      )}
      {closed.length > 0 && (
        <>
          <button type="button" className="link-button" onClick={() => setShowDone((on) => !on)}>끝난 계획 {closed.length}개 {showDone ? "▴" : "▾"}</button>
          {showDone && <table className="grid ts-compact ts-plans"><tbody>{closed.map(row)}</tbody></table>}
        </>
      )}
    </section>
  );
}

// ── C 개인 육성 목표 ──────────────────────────────────────────────────────────

export function GrowthCard({ person, readonly }: { person: string; readonly: boolean }) {
  const [data, setData] = useState<Growth | null>(null);
  const [draft, setDraft] = useState<GrowthGoal[] | null>(null);
  const [skillNames, setSkillNames] = useState<string[]>([]);
  useEffect(() => {
    if (draft === null || skillNames.length) return;
    api.experienceSkills().then((d) => setSkillNames(d.dictionary.map((e) => e.name))).catch(() => undefined);
  }, [draft, skillNames.length]);
  const [showLast, setShowLast] = useState(false);
  const load = () => { api.growth(person).then(setData).catch(() => setData(null)); };
  useEffect(() => { setDraft(null); load(); }, [person]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!data) return null;
  async function save() {
    if (!draft || !data) return;
    const goals = draft.filter((g) => g.skill.trim()).map(({ skill, way, note, mark }) => ({ skill, way, note, mark }));
    const saved = await attempt(() => api.saveGrowth(person, data.year, goals));
    if (saved) { setDraft(null); load(); }
  }
  const editing = draft !== null;
  const setGoal = (i: number, patch: Partial<GrowthGoal>) => setDraft((now) => (now ?? []).map((g, j) => (j === i ? { ...g, ...patch } : g)));
  return (
    <div className="card wide growth-card" data-testid="growth-card">
      <div className="card-head">
        <h3>{data.year} 육성 목표 <span className="muted">{data.goals.length ? `${data.goals.length}개 중 ${data.started}개 시작` : "아직 없음"}</span></h3>
        {!readonly && !editing && <button type="button" className="ghost small" onClick={() => setDraft(data.goals.length ? data.goals.map((g) => ({ ...g })) : [{ skill: "", way: "과제", note: "", mark: "" }])}>{data.goals.length ? "고치기" : "목표 적기"}</button>}
      </div>
      <p className="hint">
        {readonly ? "팀장과 면담에서 정한 올해 키울 역량입니다 — 보기만 됩니다." : <>사람마다 올해 키울 역량 <b>1 ~ {data.max}개</b>와 경로를 적습니다. 그 해 경험(구조화 · 확정)에 그 역량이 생기면 저절로 "시작함" 이 됩니다. 본인도 볼 수 있습니다 — 검색 · 내보내기 · 연말카드에는 넣지 않습니다.</>}
      </p>
      {editing ? (
        <div className="growth-form">
          {draft!.map((g, i) => (
            <div key={i} className="growth-row">
              <input list="growth-skills" value={g.skill} onChange={(e) => setGoal(i, { skill: e.target.value })} placeholder="역량 (사전에서 고름)" aria-label={`목표 ${i + 1} 역량`} />
              <select value={g.way} onChange={(e) => setGoal(i, { way: e.target.value })} aria-label={`목표 ${i + 1} 경로`}>{data.ways.map((w) => <option key={w}>{w}</option>)}</select>
              <input value={g.note} onChange={(e) => setGoal(i, { note: e.target.value })} placeholder="경로 메모 — 예: 불량 예측 과제에서" aria-label={`목표 ${i + 1} 메모`} />
              <select value={g.mark} onChange={(e) => setGoal(i, { mark: e.target.value as GrowthGoal["mark"] })} aria-label={`목표 ${i + 1} 표시`}>
                <option value="">표시 없음</option><option value="이룸">이룸</option><option value="미룸">미룸</option>
              </select>
              <button type="button" className="ghost small danger" onClick={() => setDraft((now) => (now ?? []).filter((_, j) => j !== i))}>빼기</button>
            </div>
          ))}
          <datalist id="growth-skills">{skillNames.map((n) => <option key={n} value={n} />)}</datalist>
          <div className="form-actions">
            <button type="button" className="ghost" disabled={draft!.length >= data.max} onClick={() => setDraft((now) => [...(now ?? []), { skill: "", way: "과제", note: "", mark: "" }])}>목표 더하기</button>
            <span className="grow" />
            <button type="button" className="ghost" onClick={() => setDraft(null)}>취소</button>
            <button type="button" onClick={() => void save()} data-testid="growth-save">저장</button>
          </div>
        </div>
      ) : data.goals.length === 0 ? <p className="muted">{readonly ? "올해 육성 목표가 아직 없습니다." : "올해 육성 목표가 없습니다 — 면담에서 정해 적어 두세요."}</p> : (
        <ul className="growth-list">
          {data.goals.map((g) => (
            <li key={g.skill}>
              <b>{g.skill}</b> <span className="muted">{g.way}{g.note ? ` · ${g.note}` : ""}</span>
              {g.mark ? <span className={`tag ${g.mark === "이룸" ? "growth-done" : ""}`}>{g.mark}</span>
                : g.started ? <span className="tag growth-started">시작함 · 경험 {g.experiences}{g.confirmed ? ` · 확정 ${g.confirmed}` : ""}</span>
                : <span className="tag">시작 전</span>}
              {(g.evidence ?? []).slice(0, 2).map((e) => <a key={e.id} className="growth-evidence" href={experienceLink(e.id)}>{e.title}</a>)}
            </li>
          ))}
        </ul>
      )}
      {data.last_year.goals.length > 0 && (
        <>
          <button type="button" className="link-button" onClick={() => setShowLast((on) => !on)}>{data.last_year.year} 목표 {data.last_year.goals.length}개 {showLast ? "▴" : "▾"}</button>
          {showLast && <ul className="growth-list muted">{data.last_year.goals.map((g) => <li key={g.skill}>{g.skill} · {g.way}{g.mark ? ` · ${g.mark}` : ""}</li>)}</ul>}
        </>
      )}
    </div>
  );
}
