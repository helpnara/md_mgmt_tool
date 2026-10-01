import { type CSSProperties, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import type { Meta, Roadmap as RoadmapData, RoadmapLineage, RoadmapProject, RoadmapWarning } from "../types";
import { backTarget, projectLink, useAddressBar } from "../nav";
import { effectNumber } from "../util";
import CopyTableButton from "./CopyTableButton";
import LoadError from "./LoadError";

/**
 * 다년도 과제 로드맵 (TODO 174).
 *
 * 과제 상세의 단계 줄기(172)는 과제 **하나에서** 앞뒤를 본다. 관리자에게 필요한 것은 반대다 — 팀이 끌고 가는
 * 다년도 과제가 **모두** 어디쯤 와 있고, 어느 줄기가 늦거나 끊겼고, 내년에 이어 세울 단계가 무엇인지.
 *
 * * 줄기(선행으로 이어진 과제 묶음) 하나가 한 덩어리 — 머리에 단계 수 · 기간 · 지금 단계 · 효과 합계.
 * * 줄마다 과제 하나, 단계 순 → 시작일 순. 막대는 시작일 ~ 마감일(끝났으면 끝낸 날), 색은 상태.
 * * 화살표는 선행 → 후속. 마감이 지났는데 안 끝난 과제는 마감 뒤로 **붉은 빗금**이 오늘까지 늘어난다.
 * * **살펴볼 것** — 늦은 과제 · 끊긴 선행 · 중단된 선행 위의 후속 · 다음 단계가 없는 올해의 마지막 단계.
 *
 * 거른 조건은 주소에 둔다(다른 목록 화면과 같다) — 과제를 열어 보고 돌아와도 그대로다.
 */
interface Props {
  meta: Meta;
  query: string;
}

const ROW = 32; // 한 줄 높이(px) — 왼쪽 이름 칸과 오른쪽 막대 칸이 같은 높이로 맞물린다
const DAY = 86400000;

function toTime(text: string | null | undefined): number | null {
  if (!text || !/^\d{4}-\d{2}-\d{2}/.test(text)) return null;
  const time = Date.parse(`${text.slice(0, 10)}T00:00:00`);
  return Number.isNaN(time) ? null : time;
}

function yearOf(text: string | null | undefined): number | null {
  return text && /^\d{4}/.test(text) ? Number(text.slice(0, 4)) : null;
}

/** 줄기가 걸러 낸 조건에 드는가 */
function matches(lineage: RoadmapLineage, filters: { state: string; owner: string; group: string; q: string; warn: string }): boolean {
  if (filters.state === "" && lineage.state === "ended") return false;
  if (filters.state === "ended" && lineage.state !== "ended") return false;
  if (filters.warn && lineage.warnings.length === 0) return false;
  const present = lineage.projects.filter((item) => !item.missing);
  if (filters.owner && !present.some((item) => (item.owners ?? []).includes(filters.owner))) return false;
  if (filters.group && !present.some((item) => item.group === filters.group)) return false;
  const q = filters.q.trim().toLowerCase();
  if (q && !lineage.projects.some((item) => `${item.id} ${item.title ?? ""}`.toLowerCase().includes(q))) return false;
  return true;
}

export default function Roadmap({ meta, query }: Props) {
  const initial = new URLSearchParams(query);
  // 상태 — 비면 끝나지 않은 줄기(진행 · 예정), all 이면 전부, ended 면 끝난 줄기만
  const [state, setState] = useState(() => initial.get("state") ?? (initial.get("focus") ? "all" : ""));
  const [owner, setOwner] = useState(() => initial.get("owner") ?? "");
  const [group, setGroup] = useState(() => initial.get("group") ?? "");
  const [q, setQ] = useState(() => initial.get("q") ?? "");
  const [warn, setWarn] = useState(() => initial.get("warn") ?? "");
  const [from, setFrom] = useState(() => initial.get("from") ?? "");
  const [to, setTo] = useState(() => initial.get("to") ?? "");
  const [focus] = useState(() => initial.get("focus") ?? "");
  const [back] = useState(() => initial.get("back") ?? "");
  const [data, setData] = useState<RoadmapData | null>(null);
  // 마우스를 올린 과제 — 그 과제의 앞 · 뒤 과제만 선으로 잇고 나머지는 흐리게 (TODO 180)
  const [active, setActive] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    api
      .roadmap()
      .then((result) => {
        setData(result);
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  useEffect(() => {
    load();
  }, []);

  useAddressBar("roadmap", { state, owner, group, q, warn, from, to, focus, back }, (params) => {
    setState(params.get("state") ?? "");
    setOwner(params.get("owner") ?? "");
    setGroup(params.get("group") ?? "");
    setQ(params.get("q") ?? "");
    setWarn(params.get("warn") ?? "");
    setFrom(params.get("from") ?? "");
    setTo(params.get("to") ?? "");
  });

  const lineages = useMemo(
    () => (data?.lineages ?? []).filter((item) => matches(item, { state, owner, group, q, warn })),
    [data, state, owner, group, q, warn],
  );

  // 보이는 기간 — 고르지 않으면 걸러진 줄기의 처음부터 끝까지(오늘이 늘 들어가게)
  const thisYear = data ? Number(data.today.slice(0, 4)) : new Date().getFullYear();
  const auto = useMemo(() => {
    const years: number[] = [thisYear];
    for (const lineage of lineages) {
      for (const item of lineage.projects) {
        for (const text of [item.start_date, item.end_date]) {
          const year = yearOf(text);
          if (year) years.push(year);
        }
      }
    }
    return { from: Math.min(...years), to: Math.max(...years) };
  }, [lineages, thisYear]);
  const fromYear = Number(from) || auto.from;
  const toYear = Math.max(Number(to) || auto.to, fromYear);
  const rangeStart = new Date(fromYear, 0, 1).getTime();
  const rangeEnd = new Date(toYear + 1, 0, 1).getTime();
  const span = rangeEnd - rangeStart;
  const pct = (time: number) => Math.min(1, Math.max(0, (time - rangeStart) / span));
  const today = toTime(data?.today) ?? Date.now();
  const years = Array.from({ length: toYear - fromYear + 1 }, (_, index) => fromYear + index);
  const yearChoices = useMemo(() => {
    const all = new Set<number>([thisYear - 1, thisYear, thisYear + 1, thisYear + 2]);
    for (const year of meta.years) all.add(Number(year));
    for (let year = auto.from; year <= auto.to; year += 1) all.add(year);
    return [...all].filter(Boolean).sort((a, b) => a - b);
  }, [meta.years, auto, thisYear]);

  // 화살표는 px 로 그린다 — 막대 칸의 폭을 재 둔다(창 크기가 바뀌면 다시)
  const axisRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const element = axisRef.current;
    if (!element) return;
    const measure = () => setWidth(element.getBoundingClientRect().width);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [data]);

  // 과제 상세의 [로드맵에서 보기] 로 왔으면 그 줄기로 내려간다
  useEffect(() => {
    if (!focus || !data) return;
    const target = document.querySelector(`[data-project="${CSS.escape(focus)}"]`);
    target?.scrollIntoView({ block: "center" });
  }, [focus, data]);

  const warnings = lineages.flatMap((lineage) => lineage.warnings.map((item) => ({ lineage, item })));
  const heavy = warnings.filter((entry) => entry.item.level === "warn");
  const projectCount = lineages.reduce((total, lineage) => total + lineage.projects.filter((item) => !item.missing).length, 0);
  const filtered = Boolean(state || owner || group || q || warn || from || to);
  const ownerChoices = [...new Set([...meta.people, ...meta.owners])];

  return (
    <section className="roadmap">
      {back && (
        <a className="back" href={backTarget(back).href}>
          ← {backTarget(back).label}
        </a>
      )}
      <div className="page-head">
        <h1>로드맵</h1>
        <p className="hint page-desc">
          선행 과제로 이어진 다년도 과제를 줄기별로 — 단계가 어떻게 이어져 진행되는지, 어디가 늦거나 끊겼는지 한눈에 봅니다.
          줄기는 과제 정보 수정의 <b>선행 과제</b>로 만들어집니다.
        </p>
      </div>

      <div className="toolbar roadmap-toolbar">
        <div className="filters">
          <select value={state} onChange={(event) => setState(event.target.value)} aria-label="줄기 상태">
            <option value="">진행 · 예정 줄기</option>
            <option value="all">전체 줄기</option>
            <option value="ended">끝난 줄기</option>
          </select>
          <select value={owner} onChange={(event) => setOwner(event.target.value)} aria-label="담당자">
            <option value="">담당자 전체</option>
            {ownerChoices.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          {meta.groups.length > 0 && (
            <select value={group} onChange={(event) => setGroup(event.target.value)} aria-label="그룹">
              <option value="">그룹 전체</option>
              {meta.groups.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          )}
          <input value={q} onChange={(event) => setQ(event.target.value)} placeholder="과제 번호 · 이름" aria-label="검색어" />
          <span className="roadmap-range">
            <select value={from} onChange={(event) => setFrom(event.target.value)} aria-label="보이는 기간 처음">
              <option value="">{auto.from}년(자동)</option>
              {yearChoices.map((year) => (
                <option key={year} value={year}>
                  {year}년
                </option>
              ))}
            </select>
            ~
            <select value={to} onChange={(event) => setTo(event.target.value)} aria-label="보이는 기간 끝">
              <option value="">{auto.to}년(자동)</option>
              {yearChoices.map((year) => (
                <option key={year} value={year}>
                  {year}년
                </option>
              ))}
            </select>
          </span>
          <label className="roadmap-check">
            <input type="checkbox" checked={warn === "1"} onChange={(event) => setWarn(event.target.checked ? "1" : "")} />
            살펴볼 것이 있는 줄기만
          </label>
          {filtered && (
            <button
              className="ghost small"
              onClick={() => {
                setState("");
                setOwner("");
                setGroup("");
                setQ("");
                setWarn("");
                setFrom("");
                setTo("");
              }}
            >
              조건 지우기
            </button>
          )}
        </div>
        <CopyTableButton
          headers={["줄기", "단계", "번호", "과제명", "상태", "시작일", "마감일", "완료일", "담당자", "기대효과", "살펴볼 것"]}
          rows={() =>
            lineages.flatMap((lineage) =>
              lineage.projects
                .filter((item) => !item.missing)
                .map((item) => [
                  lineage.title,
                  `${item.stage}단계`,
                  item.id,
                  item.title,
                  meta.statuses.find((status) => status.key === item.status)?.label ?? item.status,
                  item.start_date,
                  item.due_date,
                  item.completed_at,
                  (item.owners ?? []).join(", "),
                  item.effect_expected,
                  lineage.warnings
                    .filter((w) => w.project_id === item.id)
                    .map((w) => w.text)
                    .join(" / "),
                ]),
            )
          }
        />
      </div>

      {error && <LoadError message={error} onRetry={load} />}
      {!data && !error && <p className="hint">불러오는 중…</p>}

      {data && (
        <>
          <div className="roadmap-summary">
            <span className="summary-chip">
              줄기 <b>{lineages.length}</b>
              {lineages.length !== data.summary.lineages && <span className="muted"> / {data.summary.lineages}</span>}
            </span>
            <span className="summary-chip">
              진행 중 <b>{lineages.filter((item) => item.state === "active").length}</b>
            </span>
            <span className="summary-chip">
              과제 <b>{projectCount}</b>
            </span>
            <span className={heavy.length > 0 ? "summary-chip warn" : "summary-chip"}>
              늦음 · 끊김 <b>{heavy.length}</b>
            </span>
            <span className="summary-chip">
              다음 단계 미정 <b>{warnings.filter((entry) => entry.item.kind === "next_open").length}</b>
            </span>
            <span className="roadmap-legend">
              {["planned", "reviewing", "in_progress", "on_hold", "done", "dropped"].map((key) => (
                <span key={key} className="legend-item">
                  <i className={`rm-swatch rm-status-${key}`} />
                  {meta.statuses.find((status) => status.key === key)?.label ?? key}
                </span>
              ))}
              <span className="legend-item">
                <i className="rm-swatch rm-delay-swatch" />
                마감 지남
              </span>
              <span className="legend-item">
                <i className="rm-today-swatch" />
                오늘
              </span>
              <span className="legend-item rm-hover-hint">막대에 마우스를 올리면 앞 · 뒤 과제가 이어집니다</span>
            </span>
          </div>

          {warnings.length > 0 && (
            <details className="card roadmap-warnings" open={heavy.length > 0}>
              <summary>
                살펴볼 것 {warnings.length}건
                {heavy.length > 0 && <span className="warn-text"> — 늦음 · 끊김 {heavy.length}건</span>}
              </summary>
              <ul>
                {[...heavy, ...warnings.filter((entry) => entry.item.level !== "warn")].map(({ lineage, item }) => (
                  <WarningRow key={`${lineage.key}-${item.project_id}-${item.kind}`} lineage={lineage} warning={item} />
                ))}
              </ul>
            </details>
          )}

          {data.lineages.length === 0 ? (
            <div className="card empty-roadmap">
              <p>아직 선행 과제로 이어진 과제가 없습니다.</p>
              <p className="hint">
                다년도 과제라면 2단계 과제의 <b>과제 정보 수정 → 선행 과제</b>에 1단계 과제 번호를 넣거나, 1단계 과제에서{" "}
                <b>[이 과제로 새 과제]</b>로 다음 단계를 만드세요. 이어진 과제가 여기에 줄기로 섭니다.
              </p>
            </div>
          ) : lineages.length === 0 ? (
            <p className="hint">조건에 맞는 줄기가 없습니다.</p>
          ) : (
            <div className="roadmap-scroll">
              {/* 한 단계에 과제가 여럿인 줄기가 있으면 이름 칸에 "← 앞 과제" 를 적을 자리를 더 준다 (TODO 180) */}
              <div
                className="roadmap-grid"
                style={lineages.some(isBranching) ? ({ "--rm-label": "270px" } as CSSProperties) : undefined}
                onMouseLeave={() => setActive(null)}
              >
                <div className="rm-head-label">단계 · 과제 번호</div>
                <div className="rm-axis" ref={axisRef}>
                  {years.map((year) => (
                    <div key={year} className={year === thisYear ? "rm-year this-year" : "rm-year"} style={{ width: `${100 / years.length}%` }}>
                      <span>{year}</span>
                      {years.length <= 4 && (
                        <div className="rm-quarters">
                          {["1분기", "2분기", "3분기", "4분기"].map((label) => (
                            <span key={label}>{years.length <= 2 ? label : label.slice(0, 1)}</span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                  {today >= rangeStart && today < rangeEnd && (
                    <span className="rm-today-label" style={{ left: `${pct(today) * 100}%` }}>
                      오늘
                    </span>
                  )}
                </div>
                {lineages.map((lineage) => (
                  <LineageBlock
                    key={lineage.key}
                    lineage={lineage}
                    meta={meta}
                    years={years}
                    pct={pct}
                    today={today}
                    inRange={today >= rangeStart && today < rangeEnd}
                    width={width}
                    focus={focus}
                    active={active}
                    onActive={setActive}
                  />
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}

function WarningRow({ lineage, warning }: { lineage: RoadmapLineage; warning: RoadmapWarning }) {
  const project = lineage.projects.find((item) => item.id === warning.project_id);
  return (
    <li className={`rm-warning ${warning.level}`}>
      <span className="rm-warning-mark" aria-hidden="true">
        {warning.level === "warn" ? "!" : "·"}
      </span>
      <a href={projectLink(warning.project_id)}>
        <span className="project-id">{warning.project_id}</span> {project?.title}
      </a>
      <span className="muted">{lineage.title} 줄기</span>
      <span>{warning.text}</span>
    </li>
  );
}

/** 한 단계에 과제가 둘 이상인 줄기 — 막대 위치만으로는 누가 누구를 이었는지 모른다 (TODO 180) */
function isBranching(lineage: RoadmapLineage): boolean {
  const counts = new Map<number, number>();
  for (const item of lineage.projects) {
    if (!item.missing) counts.set(item.stage, (counts.get(item.stage) ?? 0) + 1);
  }
  return [...counts.values()].some((count) => count > 1);
}

function periodText(start: string | null | undefined, end: string | null | undefined): string {
  if (!start && !end) return "기간 미정";
  const short = (text: string | null | undefined) => (text ? text.slice(0, 7).replace("-", ".") : "?");
  return `${short(start)} ~ ${short(end)}`;
}

function LineageBlock({
  lineage,
  meta,
  years,
  pct,
  today,
  inRange,
  width,
  focus,
  active,
  onActive,
}: {
  lineage: RoadmapLineage;
  meta: Meta;
  years: number[];
  pct: (time: number) => number;
  today: number;
  inRange: boolean;
  width: number;
  focus: string;
  active: string | null;
  onActive: (id: string | null) => void;
}) {
  const rows = lineage.projects;
  const rowOf = new Map(rows.map((item, index) => [item.id, index]));
  const height = rows.length * ROW;
  const heavy = lineage.warnings.filter((item) => item.level === "warn").length;
  const focused = Boolean(focus) && rows.some((item) => item.id === focus);
  const effect = lineage.effect_verified > 0 ? lineage.effect_verified : lineage.effect_expected;
  const branching = isBranching(lineage);

  // 마우스를 올린 과제의 줄 — 앞으로(선행의 선행 …) · 뒤로(후속의 후속 …) 이어진 과제 전부 (TODO 180)
  let chain: Set<string> | null = null;
  if (active && rowOf.has(active)) {
    chain = new Set([active]);
    const byId = new Map(rows.map((item) => [item.id, item]));
    const walk = (id: string, next: (item: RoadmapProject) => string[]) => {
      for (const other of next(byId.get(id) as RoadmapProject)) {
        if (!chain!.has(other) && byId.has(other)) {
          chain!.add(other);
          walk(other, next);
        }
      }
    };
    walk(active, (item) => item.predecessors);
    walk(active, (item) => item.successors);
  }

  // 선행 → 후속 화살표 — **평소에는 그리지 않는다**(선이 겹쳐 지저분했다, TODO 180). 마우스를 올린 과제의 줄만. 선행의 끝(없으면 시작) 에서 후속의 시작으로.
  const links: { key: string; d: string; broken: boolean }[] = [];
  if (width > 0 && chain) {
    for (const item of rows) {
      if (!chain.has(item.id)) continue;
      const start = toTime(item.start_date) ?? toTime(item.end_date);
      if (start === null || item.missing) continue;
      for (const predId of item.predecessors) {
        const pred = rows.find((row) => row.id === predId);
        const predIndex = rowOf.get(predId);
        if (!pred || predIndex === undefined || pred.missing || !chain.has(predId)) continue;
        const predEnd = toTime(pred.end_date) ?? toTime(pred.start_date);
        if (predEnd === null) continue;
        const x1 = pct(predEnd) * width;
        const y1 = predIndex * ROW + ROW / 2;
        const x2 = pct(start) * width;
        const y2 = (rowOf.get(item.id) ?? 0) * ROW + ROW / 2;
        // 선행 막대의 **아래 끝**에서 출발해 내려가며 후속 막대의 앞으로 — 막대 오른쪽에 쓴 과제명을 가리지 않게 (TODO 177)
        const sx = Math.max(x1 - 4, 2);
        const sy = y1 + 11;
        const bend = Math.max(18, Math.abs(x2 - sx) / 2);
        links.push({
          key: `${predId}-${item.id}`,
          d: `M ${sx} ${sy} C ${sx} ${(sy + y2) / 2 + 4}, ${x2 - bend} ${y2}, ${x2 - 2} ${y2}`,
          broken: pred.status === "dropped",
        });
      }
    }
  }

  return (
    <div className={focused ? "rm-lineage focused" : "rm-lineage"} data-lineage={lineage.key}>
      <div className="rm-lineage-head">
        <b>{lineage.title}</b>
        <span className="stage-band">{lineage.stage_count}단계</span>
        <span className="muted">{periodText(lineage.start_date, lineage.end_date)}</span>
        {lineage.state === "ended" ? (
          <span className="muted">끝난 줄기</span>
        ) : (
          lineage.current_stage && <span>지금 {lineage.current_stage}단계</span>
        )}
        {effect > 0 && (
          <span className="muted">
            {lineage.effect_verified > 0 ? "실증효과" : "기대효과"} 합 {effectNumber(effect)}억원/년
          </span>
        )}
        {heavy > 0 && <span className="warn-text">늦음 · 끊김 {heavy}</span>}
      </div>
      <div className="rm-labels" style={{ height }}>
        {rows.map((item, index) => {
          const firstOfStage = index === 0 || rows[index - 1].stage !== item.stage;
          const marks = lineage.warnings.filter((w) => w.project_id === item.id);
          return (
            <div
              key={item.id}
              className={`rm-label${item.id === focus ? " here" : ""}${firstOfStage && index > 0 ? " stage-start" : ""}${
                item.stage % 2 === 0 ? " even" : ""
              }${chain ? (chain.has(item.id) ? " lit" : " dim") : ""}`}
              style={{ height: ROW }}
              data-project={item.id}
              onMouseEnter={() => onActive(item.id)}
            >
              <span className="rm-stage">{firstOfStage ? `${item.stage}단계` : ""}</span>
              {item.missing ? (
                <span className="muted" title="삭제 보관함에 있거나 찾을 수 없는 과제입니다">
                  <span className="project-id">{item.id}</span> 찾을 수 없음
                </span>
              ) : (
                <>
                  {/* 이름은 막대에 싣는다(TODO 177) — 여기는 단계 · 번호 · 상태 점만. 이름 칸에 과제명을 두면 칸이 좁아 잘렸다 */}
                  <a className="rm-name" href={projectLink(item.id)} title={`${item.id} ${item.title ?? ""}`}>
                    {item.id}
                  </a>
                  {/* 한 단계에 여럿인 줄기만 — 누가 누구를 이었는지 글자로 (TODO 180) */}
                  {branching && item.predecessors.length > 0 && (
                    <span className="rm-preds" title={`앞 과제: ${item.predecessors.join(", ")}`}>
                      ← {item.predecessors.join(", ")}
                    </span>
                  )}
                  {item.status && (
                    <i
                      className={`rm-dot rm-status-${item.status}`}
                      title={meta.statuses.find((status) => status.key === item.status)?.label ?? item.status}
                    />
                  )}
                  {marks.length > 0 && (
                    <span
                      className={marks.some((w) => w.level === "warn") ? "rm-mark warn" : "rm-mark"}
                      title={marks.map((w) => w.text).join("\n")}
                    >
                      {marks.some((w) => w.level === "warn") ? "!" : "·"}
                    </span>
                  )}
                </>
              )}
            </div>
          );
        })}
      </div>
      <div className="rm-track" style={{ height }}>
        {/* 단계마다 줄 바탕을 번갈아 — 선 없이도 단계 묶음이 보이게 (TODO 180) */}
        {rows.map((item, index) =>
          item.stage % 2 === 0 ? <span key={`band-${item.id}`} className="rm-band" style={{ top: index * ROW, height: ROW }} /> : null,
        )}
        {years.map((year, index) => (
          <span key={year} className="rm-gridline" style={{ left: `${(index / years.length) * 100}%` }} />
        ))}
        {rows.map((item, index) => (
          <Bar
            key={item.id}
            item={item}
            index={index}
            pct={pct}
            today={today}
            meta={meta}
            width={width}
            dim={Boolean(chain && !chain.has(item.id))}
            onActive={onActive}
          />
        ))}
        {inRange && <span className="rm-today" style={{ left: `${pct(today) * 100}%` }} />}
        {width > 0 && (
          <svg className="rm-links" width={width} height={height} aria-hidden="true">
            <defs>
              <marker id={`arrow-${lineage.key}`} viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">
                <path d="M0,0 L8,4 L0,8 z" />
              </marker>
            </defs>
            {links.map((link) => (
              <path
                key={link.key}
                d={link.d}
                className={link.broken ? "broken" : undefined}
                markerEnd={`url(#arrow-${lineage.key})`}
              />
            ))}
          </svg>
        )}
      </div>
    </div>
  );
}

let measure: CanvasRenderingContext2D | null = null;
/** 막대 글자의 폭(px) — 막대 안에 들어가는지 재는 데만 쓴다 */
function textWidth(text: string): number {
  try {
    measure ??= document.createElement("canvas").getContext("2d");
    if (!measure) return text.length * 12;
    measure.font = `600 12px ${getComputedStyle(document.body).fontFamily}`;
    return measure.measureText(text).width;
  } catch {
    return text.length * 12;
  }
}

function Bar({
  item,
  index,
  pct,
  today,
  meta,
  width,
  dim,
  onActive,
}: {
  item: RoadmapProject;
  index: number;
  pct: (time: number) => number;
  today: number;
  meta: Meta;
  /** 막대 칸의 폭(px) — 과제명을 막대 안에 둘지 밖에 둘지 정한다 */
  width: number;
  /** 다른 과제에 마우스를 올려 이 과제가 그 줄에 들지 않을 때 흐리게 */
  dim: boolean;
  onActive: (id: string | null) => void;
}) {
  if (item.missing) return null;
  const top = index * ROW + 5;
  const start = toTime(item.start_date);
  const end = toTime(item.end_date);
  const due = toTime(item.due_date);
  const label = meta.statuses.find((status) => status.key === item.status)?.label ?? item.status;
  const tip = [
    `${item.id} ${item.title}`,
    `${label} · ${item.start_date ?? "시작일 없음"} ~ ${item.end_date ?? "마감일 없음"}`,
    (item.owners ?? []).length ? `담당 ${(item.owners ?? []).join(", ")}` : "",
    item.effect_expected != null ? `기대효과 ${effectNumber(item.effect_expected)}억원/년` : "",
    item.predecessors.length ? `앞 과제 ${item.predecessors.join(", ")}` : "",
  ]
    .filter(Boolean)
    .join("\n");
  const go = () => (window.location.hash = projectLink(item.id));
  // 마우스 · 키보드(Tab) 모두 — 올리면 그 과제의 줄이 이어진다
  const hover = {
    onMouseEnter: () => onActive(item.id),
    onFocus: () => onActive(item.id),
    onBlur: () => onActive(null),
  };
  const fade = dim ? " dim" : "";
  const alive = item.status !== "done" && item.status !== "dropped";

  const name = item.title ?? item.id;

  if (start === null && end === null) {
    return (
      <button type="button" className={`rm-nodate${fade}`} style={{ top }} title={tip} onClick={go} {...hover}>
        기간 미정 · {name}
      </button>
    );
  }
  if (start === null && end !== null) {
    // 마감만 있으면 마감에 점 하나, 이름은 그 오른쪽에
    return (
      <>
        <button
          type="button"
          className={`rm-point rm-status-${item.status}${fade}`}
          style={{ top, left: `${pct(end) * 100}%` }}
          title={tip}
          aria-label={item.id}
          onClick={go}
          {...hover}
        />
        <button
          type="button"
          className={`rm-bar-label outside${fade}`}
          style={{ top, left: `calc(${pct(end) * 100}% + 12px)` }}
          title={tip}
          onClick={go}
          {...hover}
        >
          {name}
        </button>
      </>
    );
  }
  const from = start as number;
  // 마감이 없으면 오늘까지(흐려지며) — 끝이 정해지지 않았다는 것이 보이게
  const openEnd = end === null;
  const until = openEnd ? Math.max(today, from + 30 * DAY) : (end as number);
  const left = pct(from) * 100;
  const right = pct(until) * 100;
  const overdue = alive && due !== null && due < today;
  const delayLeft = overdue ? pct(due as number) * 100 : 0;
  const delayRight = overdue ? pct(today) * 100 : 0;
  // 과제명이 막대에 다 들어가면 안에, 아니면 막대(늦은 빗금까지) 오른쪽 밖에, 오른쪽도 모자라면 왼쪽 밖에.
  // 어디에도 모자라면 막대 안에서 말줄임 — 전체 이름은 마우스를 올리면 보인다 (TODO 177)
  const need = textWidth(name) + 16;
  const barPx = ((right - left) / 100) * width;
  const tailPx = (Math.max(right, delayRight) / 100) * width;
  const headPx = (left / 100) * width;
  const place: "inside" | "right" | "left" =
    width === 0 || barPx >= need ? "inside" : tailPx + need + 4 <= width ? "right" : headPx - need - 4 >= 0 ? "left" : "inside";
  return (
    <>
      <button
        type="button"
        className={`rm-bar rm-status-${item.status}${openEnd ? " open-end" : ""}${overdue ? " overdue" : ""}${fade}`}
        style={{ top, left: `${left}%`, width: `${Math.max(right - left, 0.4)}%` }}
        title={tip}
        onClick={go}
        {...hover}
      >
        {place === "inside" && <span>{name}</span>}
      </button>
      {place !== "inside" && (
        <button
          type="button"
          className={`rm-bar-label outside${fade}`}
          {...hover}
          style={
            place === "right"
              ? { top, left: `${tailPx + 6}px` }
              : { top, left: `${headPx - need - 2}px`, width: `${need}px`, textAlign: "right" }
          }
          title={tip}
          onClick={go}
        >
          {name}
        </button>
      )}
      {overdue && delayRight > delayLeft && (
        <span
          className={`rm-delay${fade}`}
          style={{ top, left: `${delayLeft}%`, width: `${delayRight - delayLeft}%` }}
          title={`마감 ${item.due_date} 이 지났습니다`}
        />
      )}
    </>
  );
}
