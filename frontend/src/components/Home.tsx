import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { Home as HomeData, Meta } from "../types";
import { projectLink } from "../nav";
import { effectNumber } from "../util";
import LoadError from "./LoadError";

/**
 * 홈(첫 화면) — TODO 56 · ROADMAP R1.
 *
 * 대시보드가 "지금 무엇을 봐야 하는가"라면 홈은 **"우리 팀이 올해 무엇을 했는가"**다.
 *
 * 지키는 것 셋.
 *  1. **모든 수는 눌러서 그 조건의 목록으로 이어진다** (DESIGN 5.8). 이어지지 않는 수는 넣지 않는다.
 *  2. **기대효과와 실증효과를 절대 합치지 않는다.** 합쳐 놓으면 "그거 확정된 숫자입니까"에 답할 수 없다.
 *  3. **담당 중복을 숨기지 않는다.** 사람별로 더하면 팀 합계를 넘는다. 그 사실을 글자로 적는다.
 */

const ALL_YEARS = "all";
/** 억원/년. 목록·과제 상세와 **같은 규칙**으로 적는다 (util.ts effectNumber, TODO 76). */
function money(value: number): string {
  return value ? effectNumber(value) : "—";
}

/**
 * 상태 여섯 칸 (예정·검토중·진행중·보류·완료·중단).
 *
 * **순서는 `meta.statuses` 를 그대로 따른다.** 화면에 순서를 다시 적으면 나중에 상태를
 * 하나 더할 때 두 곳이 어긋난다. 팀원별·속성별 두 표가 이 부품을 나눠 쓰므로,
 * 한 화면에서 같은 것을 다르게 세는 일이 생기지 않는다 (TODO 75).
 */
function StatusHead({ meta }: { meta: Meta }) {
  return (
    <>
      {meta.statuses.map((status) => (
        <th key={status.key}>{status.label}</th>
      ))}
    </>
  );
}

function StatusCells({
  meta,
  counts,
  link,
}: {
  meta: Meta;
  counts: Record<string, number>;
  /** 그 칸이 가리킬 목록 주소. 0 인 칸은 갈 곳이 없으므로 링크를 걸지 않는다. */
  link: (statusKey: string) => string;
}) {
  return (
    <>
      {meta.statuses.map((status) => {
        const count = counts?.[status.key] ?? 0;
        return (
          // 0 은 흐리게. 어디가 비었는지가 이 표의 요점이다.
          <td key={status.key} className={count ? undefined : "zero"}>
            {count ? <a href={link(status.key)}>{count}</a> : 0}
          </td>
        );
      })}
    </>
  );
}

function listLink(params: Record<string, string>): string {
  const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v));
  const text = query.toString();
  return `#/projects${text ? `?${text}` : ""}`;
}

export default function Home({ meta }: { meta: Meta }) {
  const thisYear = String(new Date().getFullYear());
  const [year, setYear] = useState(thisYear);
  const [data, setData] = useState<HomeData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .home(year === ALL_YEARS ? "" : year)
      .then((next) => {
        setData(next);
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  }, [year]);

  useEffect(load, [load]);

  if (error) return <LoadError message={error} onRetry={load} />;
  if (!data) return <p className="hint">불러오는 중…</p>;

  const yearParam = year === ALL_YEARS ? "" : year;
  const { team, this_week: week } = data;
  const memberSum = data.members.reduce((sum, item) => sum + item.total, 0);
  const maxCompare = Math.max(1, ...data.compare.map((item) => item.total));
  return (
    <section className="home">
      <div className="home-head">
        <h1>과제 수행 현황</h1>
        <label className="home-year">
          기준 연도
          <select value={year} onChange={(event) => setYear(event.target.value)}>
            {!data.years.includes(thisYear) && <option value={thisYear}>{thisYear}년</option>}
            {data.years.map((item) => (
              <option key={item} value={item}>
                {item}년
              </option>
            ))}
            <option value={ALL_YEARS}>전체</option>
          </select>
        </label>
      </div>

      {/* ── 이번 주 할 일 · 팀 현황 ───────────────────────────────────────
          홈을 매일 여는 이유는 지표가 아니라 "이번 주 할 일" 이다. 그래서 맨 위에 둔다.
          둘을 **나란히** 놓는다 — 세로로 쌓으면 오른쪽이 통째로 비고, 정작 중요한 것을
          보려고 스크롤해야 한다 (TODO 78). 좁은 화면에서는 다시 한 줄씩 선다. */}
      <div className="home-top">
      <div className="card home-week">
        <h2>
          이번 주 할 일
          <span className="hint"> · 보고 예정일 {week.report_date}</span>
        </h2>
        <div className="home-week-row">
          <a className="home-stat go" href="#/reports">
            <span className="home-stat-label">보고 대상</span>
            <strong>{week.candidates}건</strong>
          </a>
          <a
            className={week.overdue ? "home-stat go danger" : "home-stat go"}
            href={listLink({ due: "overdue", year: yearParam })}
          >
            <span className="home-stat-label">기한 초과</span>
            <strong>{week.overdue}건</strong>
          </a>
          <a
            className={week.due_soon ? "home-stat go warn" : "home-stat go"}
            href={listLink({ due: "7", year: yearParam })}
          >
            <span className="home-stat-label">마감 임박 (7일)</span>
            <strong>{week.due_soon}건</strong>
          </a>
        </div>
        {week.stale.length > 0 && (
          <>
            <p className="hint">
              <b>오래 보고되지 않은 과제</b> — 이번 주에 할 일이라기보다, 이미 새어 나간 것입니다.
            </p>
            <ul className="home-stale">
              {week.stale.map((item) => (
                <li key={item.id}>
                  <a href={projectLink(item.id)}>{item.title}</a>
                  <span className="due due-danger">D+{item.days_since_report}</span>
                  <span className="muted">
                    {item.never_reported ? "보고 이력 없음" : `마지막 보고 ${item.last_reported_at}`}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>

      {/* ── 팀 현황 ──────────────────────────────────────────────────── */}
      <div className="card home-team">
        <h2>{year === ALL_YEARS ? "전체" : `${year}년`} 팀 현황</h2>
        <div className="home-stats">
          <a className="home-stat" href={listLink({ year: yearParam })}>
            <span className="home-stat-label">과제</span>
            <strong>{team.total}건</strong>
          </a>
          <a className="home-stat" href={listLink({ status: "in_progress", year: yearParam })}>
            <span className="home-stat-label">진행중</span>
            <strong>{team.in_progress}건</strong>
          </a>
          <a className="home-stat" href={listLink({ status: "done", year: yearParam })}>
            <span className="home-stat-label">완료</span>
            <strong>{team.done}건</strong>
          </a>
          <a className="home-stat" href={`#/history${yearParam ? `?from=${yearParam}-01-01&to=${yearParam}-12-31` : ""}`}>
            <span className="home-stat-label">보고 횟수</span>
            <strong>{team.reports}회</strong>
          </a>
          <div className="home-stat effect">
            <span className="home-stat-label">효과 금액 (억원/년)</span>
            <strong>
              기대 {money(team.effect_expected)}
              <span className="home-arrow"> → </span>
              실증 {money(team.effect_verified)}
            </strong>
          </div>
        </div>
        <p className="hint">
          과제 수·완료·효과 금액은 <b>과제 번호의 연도</b>로, 보고 횟수는 <b>보고한 날의 연도</b>로 셉니다.
          {" "}보고 횟수는 <b>확정된 보고</b>만 셉니다 — 초안은 아직 보고한 것이 아닙니다.
        </p>
      </div>
      </div>

      {/* ── 연도 비교 ────────────────────────────────────────────────
          한 해만 보면 늘고 있는지 줄고 있는지 알 수 없다. */}
      {data.compare.length > 1 && (
        <div className="card home-compare">
          <h2>연도별 추이</h2>
          <div className="bar-row">
            {data.compare.map((item) => (
              <a
                key={item.year}
                className={item.year === year ? "bar-col on" : "bar-col"}
                href={listLink({ year: item.year })}
                title={`${item.year}년 과제 ${item.total}건 · 완료 ${item.done}건 · 보고 ${item.reports}회`}
              >
                <span className="bar-value">{item.total}</span>
                <span className="bar" style={{ height: `${(item.total / maxCompare) * 100}%` }}>
                  <span
                    className="bar-done"
                    style={{ height: `${item.total ? (item.done / item.total) * 100 : 0}%` }}
                  />
                </span>
                <span className="bar-label">{item.year}</span>
              </a>
            ))}
          </div>
          <p className="hint">
            막대는 과제 수, 진한 부분이 <b>완료</b>입니다. 누르면 그 해 과제 목록으로 갑니다.
          </p>
        </div>
      )}

      {/* ── 팀원별 성과 (ROADMAP R1 의 실체) ───────────────────────── */}
      <div className="card home-members wide">
        <h2>팀원별 성과</h2>
        {data.members.length === 0 ? (
          <p className="hint">담당자가 지정된 과제가 없습니다.</p>
        ) : (
          <>
            <div className="table-scroll">
              <table className="grid home-member-table">
                <thead>
                  <tr>
                    <th>담당자</th>
                    <th>담당 과제</th>
                    <StatusHead meta={meta} />
                    <th>
                      기대효과
                      <span className="th-unit">억원/년</span>
                    </th>
                    <th>
                      실증효과
                      <span className="th-unit">억원/년</span>
                    </th>
                    <th>보고 횟수</th>
                    <th>마지막 보고</th>
                  </tr>
                </thead>
                <tbody>
                  {data.members.map((member) => (
                    <tr key={member.name}>
                      <td>
                        <a href={listLink({ owner: member.name, year: yearParam })}>{member.name}</a>
                      </td>
                      <td>{member.total}</td>
                      <StatusCells
                        meta={meta}
                        counts={member.by_status}
                        link={(status) => listLink({ owner: member.name, status, year: yearParam })}
                      />
                      <td>{money(member.effect_expected)}</td>
                      <td>{money(member.effect_verified)}</td>
                      <td>{member.reports}</td>
                      <td className="muted">{member.last_reported_at ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {/* 이 문구는 수가 어긋날 때만 띄우면 안 된다. 담당자 없는 과제가 중복분을
                상쇄해 **우연히 합이 맞는 순간**이 가장 위험하기 때문이다 — 그때야말로
                합계가 맞는 줄 알고 그대로 보고하게 된다. 그래서 늘 밝힌다. */}
            <p className="hint">
              <b>담당 중복 포함</b> — 한 과제에 담당자가 여럿이면 양쪽에 잡힙니다.
              {memberSum !== team.total && (
                <>
                  {" "}그래서 이 표의 합({memberSum}건)은 팀 과제 수({team.total}건)와 다릅니다.
                </>
              )}{" "}
              <b>효과 금액도 마찬가지로 중복 합산</b>되므로, 팀 합계는 위의 &ldquo;팀 현황&rdquo;에 있는
              과제 기준 숫자를 쓰십시오.
            </p>
          </>
        )}
      </div>

      {/* ── 속성별 ─────────────────────────────────────────────────── */}
      {data.types.length > 0 && (
        <div className="card home-types">
          <h2>속성별</h2>
          <div className="table-scroll">
            <table className="grid home-member-table">
              <thead>
                <tr>
                  <th>속성</th>
                  <th>과제</th>
                  <StatusHead meta={meta} />
                  <th>
                    기대효과<span className="th-unit">억원/년</span>
                  </th>
                  <th>
                    실증효과<span className="th-unit">억원/년</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.types.map((item) => (
                  <tr key={item.key}>
                    <td>
                      <a href={listLink({ type: item.key, year: yearParam })}>{item.label}</a>
                    </td>
                    <td>{item.count}</td>
                    <StatusCells
                      meta={meta}
                      counts={item.by_status}
                      link={(status) => listLink({ type: item.key, status, year: yearParam })}
                    />
                    <td>{money(item.effect_expected)}</td>
                    <td>{money(item.effect_verified)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="hint">
            과제마다 속성은 하나뿐이라 이 표의 합은 <b>팀 과제 수와 정확히 맞습니다.</b>
            (담당 중복이 있는 위쪽 팀원별 표와 다른 점입니다)
          </p>
        </div>
      )}

    </section>
  );
}
