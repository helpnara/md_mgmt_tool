import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../api";
import { notifyError } from "../notify";
import type { Meta, TeamSkillTarget, TeamSkillTool, TeamSkills as Data } from "../types";
import { axisLabel } from "../util";
import CopyTableButton from "./CopyTableButton";

/**
 * 팀 역량 · 기술 스택 (TODO 284 · 290) — 팀원역량 → [팀 역량] 탭(팀장 · 관리자만).
 *
 * 290 — 팀장이 한눈에: **요약 → 변동 → 모양 → 위험 → 자세히** 순서(번호 = 화면 순서).
 * 1 한눈에(숫자 다섯 · 인사이트 문장) 2 지난해와 비교(중분류 지난해 → 올해 · 새로 생김 · 늘어남 · 줄어듦 · 끊김 · 축마다 다섯 해)
 * 3 팀 모양(축별 막대 | 기술 스택, 반반) 4 위험 · 빈 곳(한 사람에게만 | 목표, 반반) 5 역량 지도(중분류 줄 — 눌러 펼침)
 * ▸ 자세히 보기(과제 분류 × 역량 · 처음 나온 해) ▸ 데이터 점검(완성도). 세는 경험은 구조화 · 확정, 칸 = 경험 수(수준 · Lv 아님).
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
            <button className="ghost" disabled={!data} onClick={() => setPrinting(true)}>인쇄 · PDF</button>
          </div>
        </div>
        <p className="hint">
          세는 것은 <b>구조화 · 확정 경험</b>(초안은 뺌) — 숫자는 <b>경험 수</b>이고 수준 · 평가가 아닙니다. <b>범위</b>({periodLabel})는 3 ~ 5 와 자세히 보기에, <b>2 지난해와 비교</b>는 늘 올해 · 지난해로 셉니다.
          팀에 나눌 때는 <b>이름 가리기</b>를 켜고 인쇄하세요.
        </p>
      </div>
      {data && <Body data={data} show={show} interactive meta={meta} onTargets={load} />}
      {printing && data && createPortal(
        <div className="ts-print-root" aria-hidden>
          <h1 className="ts-print-title">팀 역량 · 기술 스택 — {data.change.last} → {data.change.this} · 범위 {periodLabel}</h1>
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
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [picked, setPicked] = useState<TeamSkillTool | null>(null);
  const classes = meta.classifications.filter((c) => data.by_class[c.key]);
  const [classKey, setClassKey] = useState(classes[0]?.key ?? "nature");
  const names = data.people.map((p) => p.name);
  const k = data.kpis;
  const ch = data.change;
  const c = data.completeness;
  const issues = c.unknown_tags + c.unlisted_tools.length + c.no_layer_tools.length;
  const maxShape = Math.max(1, ...data.shape.map((s) => s.experiences));
  const maxTrend = Math.max(1, ...ch.axes_trend.flatMap((a) => a.years.map((y) => y.count)));
  const go = (id: string) => document.querySelector(`[data-testid=${id}]`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  const text = (t: string) => t.replace(/\{([^}]+)\}/g, (_, n: string) => show(n));

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
    <>
      <section className="card ts-section" data-testid="ts-summary">
        <h3>1. 한눈에</h3>
        <div className="ts-kpis">
          <div className="ts-kpi"><b>{k.skills_held}<small>/{k.skills_total}</small></b><span>가진 역량</span>{k.skills_new > 0 && <em className="ts-up">올해 +{k.skills_new}</em>}</div>
          <div className="ts-kpi"><b>{k.tools}</b><span>보유 기술</span>{k.tools_new > 0 && <em className="ts-up">올해 +{k.tools_new}</em>}</div>
          <button type="button" className="ts-kpi link" onClick={() => go("ts-risk")} disabled={!interactive}><b className={k.only_one ? "warn-text" : ""}>{k.only_one}</b><span>한 사람에게만</span></button>
          <button type="button" className="ts-kpi link" onClick={() => go("ts-risk")} disabled={!interactive}><b className={k.target_gaps ? "warn-text" : ""}>{k.target_gaps}</b><span>목표 모자람</span></button>
          <div className="ts-kpi"><b>{k.experiences}</b><span>세는 경험</span></div>
        </div>
        {data.insights.length > 0 ? (
          <ul className="ts-insights" data-testid="ts-insights">
            {data.insights.map((ins, i) => (
              <li key={i}>{interactive ? <button type="button" className="link-button" onClick={() => go(ins.target)}>{text(ins.text)}</button> : text(ins.text)}</li>
            ))}
          </ul>
        ) : <p className="muted">아직 짚을 만한 변동이 없습니다 — 경험이 구조화 · 확정되면 문장이 생깁니다.</p>}
      </section>

      <section className="card ts-section" data-testid="ts-change">
        <h3>2. 지난해와 비교 <span className="muted">— {ch.last} → {ch.this}, 그 해에 걸친 경험 수(보유 기술은 쓴 사람 수)</span></h3>
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
        <section className="card ts-section" data-testid="ts-shape">
          <h3>3. 팀 모양 — 축별</h3>
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
        <section className="card ts-section" data-testid="ts-stack">
          <h3>3. 팀 모양 — 기술 스택 <span className="muted">칩 = 쓴 사람 수</span></h3>
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
                    <a href={u.kind === "project" ? `#/projects/${encodeURIComponent(u.id)}` : `#/experience/${encodeURIComponent(u.id)}`}>{u.title}</a>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      </div>

      <div className="ts-half" data-testid="ts-risk">
        <section className="card ts-section" data-testid="ts-only-one">
          <h3>4. 위험 — 한 사람에게만 있는 것 <span className="muted">대신할 사람이 없음</span></h3>
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
        <section className="card ts-section">
          <Targets data={data} interactive={interactive} onSaved={onTargets} />
        </section>
      </div>

      <section className="card ts-section" data-testid="ts-skill-map">
        <div className="card-head">
          <h3>5. 역량 지도 <span className="muted">— 중분류 × 사람, 칸 = 경험 수. 줄을 누르면 그 안의 역량</span></h3>
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
                        <th scope="row" className="ts-map-name ts-indent">{r.name}{!r.known && <span className="tag warn-tag" title="역량 사전에 없는 태그">사전에 없음</span>}</th>
                        {names.map((n) => {
                          const cell = r.cells[n];
                          return <td key={n} className={`ts-cell lv${level(cell?.count ?? 0)}`} title={cell ? `${show(n)} · 경험 ${cell.count}건${cell.last ? ` · 마지막 ${cell.last}` : ""}` : ""}>{cell?.count ?? ""}</td>;
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

      <details className="card ts-section ts-fold" data-testid="ts-details" open={!interactive || undefined}>
        <summary><b>자세히 보기</b> <span className="muted">— 과제 분류 × 역량 · 처음 나온 해</span></summary>
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
      </details>

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
                  <th scope="row">{interactive ? <a href={`#/person/${encodeURIComponent(p.name)}`}>{show(p.name)}</a> : show(p.name)}</th>
                  <td>{p.확정}</td><td>{p.구조화}</td><td>{p.초안}</td><td>{p.unknown_tags || ""}</td><td>{p.empty_tools || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </>
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
        <h3>4. 빈 곳 — 목표 vs 지금</h3>
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
