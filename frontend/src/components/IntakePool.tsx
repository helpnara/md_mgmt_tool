import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { backTarget, screenLink, useAddressBar } from "../nav";
import type { Intake, IntakeListing, Meta } from "../types";
import { effectNumber } from "../util";
import IntakeForm from "./IntakeForm";

/**
 * 과제 접수 풀 (TODO 136).
 *
 * **풀은 줄 세운 대기열이 아니라 골라 쓰는 못이다.** 아직 판정이 안 났거나 보류된 접수를
 * 담아 두고, 요청부서·중요도·체류일로 걸러 보다가 연초·분기에 골라 착수시킨다.
 * 기본 정렬이 *오래 기다린 순* 인 것은, 요청자에게 가장 나쁜 것이 **답이 없는 것**이기 때문이다.
 *
 * 과제 목록과 **섞지 않는다.** 접수는 과제가 아니다 — 착수가 정해지면 승격해서 과제가 된다.
 */
interface Props {
  meta: Meta;
  query: string;
}

const DEFAULTS = {
  scope: "pool",
  status: "",
  nature: "",
  category: "",
  priority: "",
  team: "",
  year: "",
  picked: "",
  stale: "",
  decided_year: "",
  q: "",
  sort: "age",
  back: "",
};
type Filters = typeof DEFAULTS;

function readFilters(params: URLSearchParams): Filters {
  const out = { ...DEFAULTS };
  for (const key of Object.keys(out) as (keyof Filters)[]) out[key] = params.get(key) ?? DEFAULTS[key];
  return out;
}

export default function IntakePool({ meta, query }: Props) {
  const [filters, setFilters] = useState<Filters>(() => readFilters(new URLSearchParams(query)));
  const [data, setData] = useState<IntakeListing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(() => new URLSearchParams(query).get("new") === "1");
  const [term, setTerm] = useState(filters.q);

  const load = useCallback(() => {
    const { back: _back, ...rest } = filters;
    api
      .intakes(rest)
      .then((result) => {
        setData(result);
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  }, [filters]);
  useEffect(load, [load]);

  useAddressBar(
    "intakes",
    Object.fromEntries(
      Object.entries(filters).filter(([key, value]) => value !== DEFAULTS[key as keyof Filters]),
    ) as Record<string, string>,
    (params) => setFilters(readFilters(params)),
  );

  const set = (patch: Partial<Filters>) => setFilters((prev) => ({ ...prev, ...patch }));
  const statusLabel = (key: string) => meta.intake_statuses.find((s) => s.key === key)?.label ?? key;
  const summary = data?.summary;
  const narrowed = Object.entries(filters).some(
    ([key, value]) => !["sort", "back", "scope"].includes(key) && value !== DEFAULTS[key as keyof Filters],
  );

  async function togglePicked(item: Intake) {
    try {
      await api.updateIntake(item.id, { picked: !item.picked });
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <section className="intake-pool">
      {filters.back && (
        <a className="back" href={backTarget(filters.back).href}>
          ← {backTarget(filters.back).label}
        </a>
      )}
      <div className="page-head">
        <div>
          <h1>접수</h1>
          <p className="hint">
            현업 요청을 받아 검토하고, 착수가 정해지면 <b>과제로 승격</b>합니다. 과제 번호는 승격할 때 붙습니다.
          </p>
        </div>
        {!creating && (
          <button onClick={() => setCreating(true)} className="intake-new">
            + 접수 등록
          </button>
        )}
      </div>

      {creating && (
        <div className="card">
          <h2>새 접수</h2>
          <IntakeForm
            meta={meta}
            submitLabel="접수 등록"
            onCancel={() => setCreating(false)}
            onSubmit={async (payload) => {
              const made = await api.createIntake(payload);
              setCreating(false);
              window.location.hash = screenLink(`intakes/${made.id}`);
            }}
          />
        </div>
      )}

      {summary && (
        <div className="card intake-summary">
          <div className="intake-summary-row">
            <button
              className={`stat-chip ${filters.scope === "pool" && !filters.status && !filters.stale ? "on" : ""}`}
              onClick={() => set({ scope: "pool", status: "", stale: "", decided_year: "" })}
            >
              풀 <b>{summary.pool}</b>
            </button>
            {meta.intake_statuses
              .filter((s) => s.pool)
              .map((s) => (
                <button
                  key={s.key}
                  className={`stat-chip ${filters.status === s.key ? "on" : ""}`}
                  onClick={() => set({ status: filters.status === s.key ? "" : s.key, stale: "", decided_year: "" })}
                >
                  {s.label} <b>{summary.counts[s.key] ?? 0}</b>
                </button>
              ))}
            <button
              className={`stat-chip warn ${filters.stale ? "on" : ""} ${summary.stale ? "" : "quiet"}`}
              onClick={() => set({ stale: filters.stale ? "" : "1", status: "", scope: "pool", decided_year: "" })}
              title={`접수 후 ${summary.stale_days}일이 지나도 판정이 없는 것 — 보류는 세지 않습니다`}
            >
              묵힘 <b>{summary.stale}</b>
              <span className="muted"> ({summary.stale_days}일↑)</span>
            </button>
          </div>
          <div className="intake-summary-row muted">
            <span>{summary.year}년 판정 —</span>
            {(["started", "rejected", "transferred", "merged"] as const).map((key) => (
              <button
                key={key}
                className={`linkish ${filters.status === key && filters.decided_year === summary.year ? "on" : ""}`}
                onClick={() => set({ scope: "closed", status: key, decided_year: summary.year, stale: "" })}
              >
                {statusLabel(key)} {summary.decided[key] ?? 0}
              </button>
            ))}
            <span>· 올해 접수 {summary.received_this_year}</span>
          </div>
        </div>
      )}

      <div className="toolbar">
        <div className="filters">
          <select value={filters.scope} onChange={(e) => set({ scope: e.target.value, status: "", decided_year: "" })} aria-label="범위">
            <option value="pool">풀 (판정 전 · 보류)</option>
            <option value="closed">판정이 난 것</option>
            <option value="all">전체</option>
          </select>
          <select value={filters.status} onChange={(e) => set({ status: e.target.value })} aria-label="상태">
            <option value="">상태 전체</option>
            {meta.intake_statuses.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
          {meta.classifications
            .filter((info) => info.key === "nature" || info.key === "category")
            .map((info) => (
              <select
                key={info.key}
                value={filters[info.key as "nature" | "category"]}
                onChange={(e) => set({ [info.key]: e.target.value } as Partial<Filters>)}
                aria-label={info.label}
              >
                <option value="">{info.label} 전체</option>
                {info.items.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
                <option value="none">미지정</option>
              </select>
            ))}
          <select value={filters.priority} onChange={(e) => set({ priority: e.target.value })} aria-label="중요도">
            <option value="">중요도 전체</option>
            <option value="상">상</option>
            <option value="중">중</option>
            <option value="하">하</option>
            <option value="none">정하지 않음</option>
          </select>
          {(data?.teams.length ?? 0) > 0 && (
            <select value={filters.team} onChange={(e) => set({ team: e.target.value })} aria-label="소속">
              <option value="">소속 전체</option>
              {data!.teams.map((team) => (
                <option key={team} value={team}>
                  {team}
                </option>
              ))}
            </select>
          )}
          {(data?.years.length ?? 0) > 0 && (
            <select value={filters.year} onChange={(e) => set({ year: e.target.value })} aria-label="접수 연도">
              <option value="">접수 연도 전체</option>
              {data!.years.map((year) => (
                <option key={year} value={year}>
                  {year}년 접수
                </option>
              ))}
            </select>
          )}
          <label className="check-label picked-filter">
            <input type="checkbox" checked={filters.picked === "1"} onChange={(e) => set({ picked: e.target.checked ? "1" : "" })} />
            ★ 착수 후보만
          </label>
          <form
            className="inline-search"
            onSubmit={(e) => {
              e.preventDefault();
              set({ q: term.trim() });
            }}
          >
            <input
              type="search"
              value={term}
              onChange={(e) => setTerm(e.target.value)}
              placeholder="접수 번호·과제명·과제리더·소속·본문"
              aria-label="접수 찾기"
            />
          </form>
          <select value={filters.sort} onChange={(e) => set({ sort: e.target.value })} aria-label="정렬">
            <option value="age">오래 기다린 순</option>
            <option value="received">최근 접수순</option>
            <option value="priority">중요도순</option>
            <option value="effect">요청 효과 큰 순</option>
            <option value="decided">최근 판정순</option>
            <option value="id">접수 번호순</option>
          </select>
          {narrowed && (
            <button
              className="ghost small"
              onClick={() => {
                setTerm("");
                setFilters({ ...DEFAULTS, back: filters.back });
              }}
            >
              조건 지우기
            </button>
          )}
        </div>
      </div>

      {error && <p className="error">{error}</p>}

      {data && data.items.length === 0 && (
        <div className="card empty-card">
          {narrowed || filters.scope !== "pool" ? (
            <p className="hint">조건에 맞는 접수가 없습니다.</p>
          ) : (
            <>
              <p>
                <b>풀이 비어 있습니다.</b>
              </p>
              <p className="hint">
                현업에서 받은 과제정의서를 <b>[+ 접수 등록]</b>으로 받아 두세요. 인터뷰 기록을 쌓다가 착수가 정해지면
                상세 화면의 <b>[착수 · 과제로 승격]</b>으로 과제를 만듭니다. 반려·보류도 사유와 함께 남습니다.
              </p>
            </>
          )}
        </div>
      )}

      {data && data.items.length > 0 && (
        <div className="card table-card">
          <div className="table-scroll">
            <table className="intake-table">
              <thead>
                <tr>
                  <th className="pick-col" title="착수 후보">★</th>
                  <th>접수 번호</th>
                  <th>과제명</th>
                  <th>과제리더 · 소속</th>
                  <th>성격 · 분류</th>
                  <th>중요도</th>
                  <th>상태</th>
                  <th>접수일</th>
                  <th className="num">경과</th>
                  <th className="num">검토</th>
                  <th className="num" title="요청자 추정 — 과제로 옮기지 않습니다">요청 효과</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={item.id} className={item.stale ? "stale-row" : undefined} data-intake={item.id}>
                    <td className="pick-col">
                      {item.in_pool ? (
                        <button
                          className={`star ${item.picked ? "on" : ""}`}
                          onClick={() => togglePicked(item)}
                          title={item.picked ? "착수 후보에서 빼기" : "착수 후보로 표시"}
                          aria-label={item.picked ? "착수 후보에서 빼기" : "착수 후보로 표시"}
                        >
                          {item.picked ? "★" : "☆"}
                        </button>
                      ) : (
                        item.picked && <span className="star on">★</span>
                      )}
                    </td>
                    <td className="project-id">
                      <a href={screenLink(`intakes/${item.id}`)}>{item.id}</a>
                    </td>
                    <td>
                      <a className="intake-title" href={screenLink(`intakes/${item.id}`)}>
                        {item.title}
                      </a>
                      {item.status === "started" && item.project_id && (
                        <span className="muted"> → {item.project_id}</span>
                      )}
                    </td>
                    <td>
                      {item.leader ?? <span className="muted">—</span>}
                      {item.leader_team && <span className="muted"> · {item.leader_team}</span>}
                    </td>
                    <td className="muted">{[item.nature, item.category].filter(Boolean).join(" · ") || "—"}</td>
                    <td>{item.priority ? <span className={`priority priority-${item.priority}`}>{item.priority}</span> : <span className="muted">—</span>}</td>
                    <td>
                      <span className={`intake-status intake-${item.status}`}>{item.status_label}</span>
                    </td>
                    <td className="muted">{item.received_on ?? "—"}</td>
                    <td className={`num ${item.stale ? "due-danger" : "muted"}`}>
                      {item.in_pool && item.age_days !== null ? `D+${item.age_days}` : "—"}
                    </td>
                    <td className="num muted">{item.log_count}</td>
                    <td className="num muted">{item.effect_request !== null ? effectNumber(item.effect_request) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="hint">
            {data.items.length}건 · 경과는 접수일부터 센 날수입니다. <b>{meta.intake_stale_days}일</b>이 지나도 판정이
            없으면 빨갛게 표시됩니다(보류는 제외).
          </p>
        </div>
      )}
    </section>
  );
}
