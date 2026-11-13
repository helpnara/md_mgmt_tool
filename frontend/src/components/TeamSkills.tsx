import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../api";
import { notifyError } from "../notify";
import type { Meta, TeamSkillTarget, TeamSkillTool, TeamSkills as Data } from "../types";
import { axisLabel } from "../util";
import CopyTableButton from "./CopyTableButton";

/**
 * 팀 역량 · 기술 스택 (TODO 284) — 팀원역량 → [팀 역량] 탭(팀장 · 관리자만).
 *
 * 맨 위 완성도 띠(그림을 믿고 쓸 수 있나) → ① 역량 지도(역량 × 사람, 칸 = 경험 수) → ② 기술 스택(층마다 보유 기술)
 * → ④ 한 사람에게만 있는 것. 세는 경험은 구조화 · 확정, 기간은 기본 최근 3년. 수준(Lv)은 넣지 않는다.
 * [이름 가리기] — 사람 이름을 "팀원 A · B …" 로(팀 공유 · 발표용). [인쇄 · PDF](A4 가로) · [표 복사].
 *
 * 2단계: ③ 축별 팀 모양 · 역량 지도의 중분류 묶음 · ⑤ 해마다 새로 생긴 것 · ⑥ 과제 분류 × 역량 · ⑦ 목표(있는 것 vs 필요한 것).
 */
const PERIODS: { key: Data["period"]; label: string }[] = [
  { key: "3y", label: "최근 3년" },
  { key: "year", label: "올해" },
  { key: "all", label: "전체" },
];

const level = (n: number) => (n >= 5 ? 4 : n >= 3 ? 3 : n >= 2 ? 2 : n >= 1 ? 1 : 0);
const letter = (i: number) => (i < 26 ? String.fromCharCode(65 + i) : `${String.fromCharCode(65 + Math.floor(i / 26) - 1)}${String.fromCharCode(65 + (i % 26))}`);

export default function TeamSkills({ meta }: { meta: Meta }) {
  const [period, setPeriod] = useState<Data["period"]>("3y");
  const [left, setLeft] = useState(false);
  const [mask, setMask] = useState(false);
  const [data, setData] = useState<Data | null>(null);
  const [printing, setPrinting] = useState(false);

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
      <div className="card">
        <div className="card-head">
          <h2>팀 역량 · 기술 스택</h2>
          <div className="person-tools ts-tools">
            <select aria-label="기간" value={period} onChange={(e) => setPeriod(e.target.value as Data["period"])}>
              {PERIODS.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
            </select>
            <label className="check-label"><input type="checkbox" checked={left} onChange={(e) => setLeft(e.target.checked)} /> 떠난 사람 포함</label>
            <label className="check-label"><input type="checkbox" checked={mask} onChange={(e) => setMask(e.target.checked)} /> 이름 가리기</label>
            <CopyTableButton label="표 복사 · 역량" headers={["축", "역량", ...names.map(show), "가진 사람"]}
              rows={() => held.map((r) => [axisLabel(r.axis), r.name, ...names.map((n) => r.cells[n]?.count ?? ""), r.holders])} />
            <CopyTableButton label="표 복사 · 기술" headers={["층", "보유 기술", "쓴 사람 수", "과제 수", "경험 수", "쓴 사람"]}
              rows={() => (data?.stack ?? []).flatMap((l) => l.tools.map((t) => [l.layer, t.name, t.person_count, t.project_count, t.experience_count, t.people.map(show).join(", ")]))} />
            <button className="ghost" disabled={!data} onClick={() => setPrinting(true)}>인쇄 · PDF</button>
          </div>
        </div>
        <p className="hint">
          팀원 이력(경험의 역량 태그 · 보유 기술, 과제 담당과 역할의 기술)을 팀 한 장으로 봅니다. 세는 것은 <b>구조화 · 확정 경험</b>(초안은 뺌) · 기간 <b>{periodLabel}</b>(기간이 없는 경험은 늘 셈).
          칸의 숫자는 <b>경험 수</b>입니다 — 수준 · 평가가 아닙니다. 이 화면은 팀장 · 관리자만 봅니다. 팀에 나눌 때는 <b>이름 가리기</b>를 켜고 인쇄하세요.
        </p>
      </div>
      {data && <Body data={data} show={show} interactive meta={meta} onTargets={load} />}
      {printing && data && createPortal(
        <div className="ts-print-root" aria-hidden>
          <h1 className="ts-print-title">팀 역량 · 기술 스택 — {periodLabel} ({data.year}년 기준)</h1>
          <Body data={data} show={show} interactive={false} meta={meta} />
        </div>,
        document.body,
      )}
    </div>
  );
}

function Body({ data, show, interactive, meta, onTargets }: {
  data: Data; show: (name: string) => string; interactive: boolean; meta: Meta; onTargets?: () => void;
}) {
  const [emptyOpen, setEmptyOpen] = useState(false);
  const classes = meta.classifications.filter((c) => data.by_class[c.key]);
  const [classKey, setClassKey] = useState(classes[0]?.key ?? "nature");
  const maxShape = Math.max(1, ...data.shape.map((s) => s.experiences));
  const [picked, setPicked] = useState<TeamSkillTool | null>(null);
  const names = data.people.map((p) => p.name);
  const c = data.completeness;
  const counted = c.people.reduce((sum, p) => sum + p.구조화 + p.확정, 0);
  const drafts = c.people.reduce((sum, p) => sum + p.초안, 0);
  const rows = data.skills.filter((r) => r.holders > 0 || (interactive && emptyOpen));
  const empty = data.skills.filter((r) => r.holders === 0).length;
  const axes = [...new Set(rows.map((r) => r.axis))];
  const maxPeople = Math.max(1, ...data.stack.flatMap((l) => l.tools.map((t) => t.person_count)));

  return (
    <>
      <section className="card ts-section" data-testid="ts-completeness">
        <h3>믿고 쓸 수 있나 — 완성도</h3>
        <p className="ts-summary">
          세는 경험 <b>{counted}</b>건(초안 {drafts}건은 세지 않음) ·{" "}
          <span className={c.unknown_tags ? "warn-text" : ""}>사전에 없는 역량 태그 {c.unknown_tags}</span> ·{" "}
          <span className={c.unlisted_tools.length ? "warn-text" : ""}>사전에 없는 보유 기술 {c.unlisted_tools.length}</span>
          {c.unlisted_tools.length > 0 && <span className="muted"> ({c.unlisted_tools.slice(0, 6).join(", ")}{c.unlisted_tools.length > 6 ? " …" : ""})</span>} ·{" "}
          <span className={c.no_layer_tools.length ? "warn-text" : ""}>층 없는 보유 기술 {c.no_layer_tools.length}</span> ·{" "}
          기술 칸이 빈 담당 {c.empty_tool_projects}
          {interactive && <> · <a href="#/settings?tab=class">설정 → 역량 · 보유 기술 사전</a></>}
        </p>
        <div className="table-scroll">
          <table className="grid ts-complete-table fit-cols">
            <thead><tr><th>사람</th><th>확정</th><th>구조화</th><th>초안</th><th>사전에 없는 태그</th><th>기술 칸 빈 담당</th></tr></thead>
            <tbody>
              {c.people.map((p) => (
                <tr key={p.name} className={p.확정 + p.구조화 === 0 ? "ts-weak" : undefined}>
                  <th scope="row">{interactive ? <a href={`#/person/${encodeURIComponent(p.name)}`}>{show(p.name)}</a> : show(p.name)}</th>
                  <td>{p.확정}</td><td>{p.구조화}</td><td>{p.초안}</td><td>{p.unknown_tags || ""}</td><td>{p.empty_tools || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card ts-section" data-testid="ts-shape">
        <h3>③ 축별 팀 모양 <span className="muted">— 경험 수 · 가진 역량 가짓수 / 사전 · 가진 사람</span></h3>
        <div className="ts-shape">
          {data.shape.map((s) => (
            <div key={s.axis} className="ts-shape-row" data-axis={s.axis}>
              <span className="ts-shape-name">{axisLabel(s.axis)}</span>
              <span className="ts-bar"><span className="ts-bar-fill" style={{ width: `${(s.experiences / maxShape) * 100}%` }} /></span>
              <span className="ts-shape-num"><b>{s.experiences}</b> 경험 · 역량 {s.held} / {s.total} · {s.people}명</span>
            </div>
          ))}
        </div>
      </section>

      <section className="card ts-section" data-testid="ts-skill-map">
        <h3>① 역량 지도 <span className="muted">— 칸 = 경험 수(진할수록 많음) · 마지막 해</span></h3>
        {rows.length === 0 ? <p className="muted">세는 경험에 역량 태그가 아직 없습니다.</p> : (
          <div className="table-scroll">
            <table className="grid ts-map">
              <thead>
                <tr><th className="ts-map-name">역량</th>{names.map((n) => <th key={n} className="ts-map-person">{show(n)}</th>)}<th>가진 사람</th></tr>
              </thead>
              <tbody>
                {axes.map((axis) => [
                  <tr key={`axis-${axis}`} className="ts-axis-row"><th colSpan={names.length + 2}>{axisLabel(axis)}</th></tr>,
                  ...[...new Set(rows.filter((r) => r.axis === axis).map((r) => r.group))].flatMap((group) => [
                    ...(group ? [<tr key={`group-${axis}-${group}`} className="ts-group-row"><th colSpan={names.length + 2}>{group}</th></tr>] : []),
                  ...rows.filter((r) => r.axis === axis && r.group === group).map((r) => (
                    <tr key={`${axis}-${r.name}`} data-skill={r.name}>
                      <th scope="row" className="ts-map-name">{r.name}{!r.known && <span className="tag warn-tag" title="역량 사전에 없는 태그">사전에 없음</span>}</th>
                      {names.map((n) => {
                        const cell = r.cells[n];
                        return (
                          <td key={n} className={`ts-cell lv${level(cell?.count ?? 0)}`} title={cell ? `${show(n)} · 경험 ${cell.count}건${cell.last ? ` · 마지막 ${cell.last}` : ""}` : ""}>
                            {cell ? <><b>{cell.count}</b>{cell.last && <small>’{cell.last.slice(2)}</small>}</> : ""}
                          </td>
                        );
                      })}
                      <td className={r.holders === 1 ? "ts-holders one" : "ts-holders"}>{r.holders}</td>
                    </tr>
                  )),
                  ]),
                ])}
              </tbody>
            </table>
          </div>
        )}
        {interactive && empty > 0 && (
          <button type="button" className="link-button" onClick={() => setEmptyOpen(!emptyOpen)}>
            {emptyOpen ? "아직 아무도 없는 역량 접기" : `아직 아무도 없는 역량 ${empty}개 보기`}
          </button>
        )}
      </section>

      <section className="card ts-section" data-testid="ts-stack">
        <h3>② 기술 스택 <span className="muted">— 층마다 보유 기술 · 칩 = 쓴 사람 수 · 과제 수</span></h3>
        {data.stack.length === 0 && <p className="muted">세는 경험 · 과제에 보유 기술이 아직 없습니다.</p>}
        <div className="ts-stack">
          {data.stack.map((layer) => (
            <div key={layer.layer} className={layer.unlayered ? "ts-layer unlayered" : "ts-layer"} data-layer={layer.layer}>
              <span className="ts-layer-name">{layer.layer}</span>
              <span className="ts-layer-tools">
                {layer.tools.map((t) => {
                  const size = t.person_count / maxPeople >= 0.6 ? "l" : t.person_count / maxPeople >= 0.3 ? "m" : "s";
                  const body = <><b>{t.name}</b><small>{t.person_count}명 · 과제 {t.project_count}{t.experience_count ? ` · 경험 ${t.experience_count}` : ""}</small></>;
                  return interactive ? (
                    <button key={t.name} type="button" className={`ts-tool ${size}${picked?.name === t.name ? " on" : ""}`} aria-pressed={picked?.name === t.name}
                      onClick={() => setPicked(picked?.name === t.name ? null : t)}>{body}</button>
                  ) : <span key={t.name} className={`ts-tool ${size}`}>{body}</span>;
                })}
              </span>
            </div>
          ))}
        </div>
        {interactive && picked && (
          <div className="ts-uses" data-testid="ts-uses">
            <b>{picked.name}</b> — 쓴 사람 {picked.people.map(show).join(", ")}
            <ul>
              {picked.uses.map((u, i) => (
                <li key={i}>
                  {show(u.person)} · {u.kind === "project" ? "과제" : "경험"}{" "}
                  <a href={u.kind === "project" ? `#/projects/${encodeURIComponent(u.id)}` : `#/experience/${encodeURIComponent(u.id)}`}>{u.title}</a>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section className="card ts-section" data-testid="ts-only-one">
        <h3>④ 한 사람에게만 있는 것 <span className="muted">— 대신할 사람이 없는 역량 · 보유 기술</span></h3>
        {data.only_one.length === 0 ? <p className="muted">없습니다.</p> : (
          <div className="table-scroll">
            <table className="grid fit-cols">
              <thead><tr><th>구분</th><th>묶음</th><th>이름</th><th>가진 사람</th></tr></thead>
              <tbody>
                {data.only_one.map((o) => (
                  <tr key={`${o.kind}-${o.name}`}><td>{o.kind}</td><td>{o.kind === "역량" ? axisLabel(o.group) : o.group}</td><td>{o.name}</td><td>{show(o.person)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card ts-section" data-testid="ts-new-by-year">
        <h3>⑤ 해마다 새로 생긴 것 <span className="muted">— 팀에 처음 나온 해(기간과 상관없이 전체로) · 누가 처음 가져왔나</span></h3>
        <div className="ts-years">
          {data.new_by_year.map((y) => (
            <div key={y.year} className="ts-year-row" data-year={y.year}>
              <span className="ts-layer-name">{y.year}</span>
              <span className="ts-layer-tools">
                {y.items.length === 0 && <span className="muted">없음</span>}
                {y.items.map((item) => (
                  <span key={`${item.kind}-${item.name}`} className={item.kind === "역량" ? "ts-new skill" : "ts-new tool"} title={`${item.kind} · ${item.people.map(show).join(", ")}`}>
                    {item.name} <small>{item.people.map(show).join(", ")}</small>
                  </span>
                ))}
              </span>
            </div>
          ))}
        </div>
        <p className="hint"><span className="ts-new skill">역량</span> <span className="ts-new tool">보유 기술</span>{data.new_earlier ? ` · 그보다 앞서 생긴 것 ${data.new_earlier}개` : ""}</p>
      </section>

      <section className="card ts-section" data-testid="ts-by-class">
        <h3>⑥ 과제 분류 × 역량 <span className="muted">— 과제에 이은 경험의 역량 · 칸 = 경험 수</span></h3>
        {interactive && (
          <div className="dict-axes" role="group" aria-label="과제 분류">
            {classes.map((c) => (
              <button key={c.key} type="button" className={classKey === c.key ? "chip on" : "chip"} aria-pressed={classKey === c.key} onClick={() => setClassKey(c.key)}>{c.label}</button>
            ))}
          </div>
        )}
        {(interactive ? classes.filter((c) => c.key === classKey) : classes).map((c) => {
          const block = data.by_class[c.key];
          if (!block || block.rows.length === 0) return <p key={c.key} className="muted">{c.label} — 과제에 이은 경험이 없거나 과제의 {c.label} 칸이 비었습니다.</p>;
          return (
            <div key={c.key} className="table-scroll">
              {!interactive && <p className="ts-print-sub">{c.label}</p>}
              <table className="grid ts-map">
                <thead><tr><th className="ts-map-name">역량</th>{block.values.map((v) => <th key={v} className="ts-map-person">{v}</th>)}<th>합</th></tr></thead>
                <tbody>
                  {block.rows.slice(0, 20).map((r) => (
                    <tr key={`${r.axis}-${r.name}`}>
                      <th scope="row" className="ts-map-name">{r.name} <span className="muted">{axisLabel(r.axis)}</span></th>
                      {block.values.map((v) => {
                        const n = r.cells[v] ?? 0;
                        return <td key={v} className={`ts-cell lv${level(n)}`}>{n || ""}</td>;
                      })}
                      <td className="ts-holders">{r.total}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {block.rows.length > 20 && <p className="muted">많이 나온 20개만 — 나머지 {block.rows.length - 20}개</p>}
            </div>
          );
        })}
      </section>

      <Targets data={data} interactive={interactive} onSaved={onTargets} />
    </>
  );
}

/** ⑦ 목표 — 팀이 갖출 역량 · 보유 기술과 사람 수. 지금 가진 사람과 견준다(빈 곳) */
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
    <section className="card ts-section" data-testid="ts-targets">
      <div className="card-head">
        <h3>⑦ 목표 — 있는 것 vs 필요한 것 <span className="muted">— 팀이 갖출 역량 · 보유 기술과 사람 수</span></h3>
        {interactive && !editing && <button type="button" className="ghost small" onClick={() => setEditing(rows.map(({ kind, name, want }) => ({ kind, name, want })))}>목표 고치기</button>}
      </div>
      {!editing && rows.length === 0 && <p className="muted">적어 둔 목표가 없습니다{interactive ? " — [목표 고치기]로 팀이 갖출 역량 · 보유 기술과 사람 수를 적으세요" : ""}.</p>}
      {!editing && rows.length > 0 && (
        <div className="table-scroll">
          <table className="grid fit-cols ts-targets">
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
